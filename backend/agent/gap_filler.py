"""Gap filler: detects empty cells in the merged table and fires targeted searches."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from config import EXTRACTOR_MODEL, MAX_GAP_SEARCHES
from models.schema import (
    CellValue,
    Confidence,
    EntityRow,
    InferredSchema,
    SourceReference,
)
from prompts.templates import GAP_FILL_PROMPT
from utils.cache import CacheDB
from utils.chunker import chunk_text
from utils.confidence import overall_confidence, score_cell
from utils.llm import CostTracker, call_llm, parse_json_loose

logger = logging.getLogger(__name__)


async def fill_gaps(
    entities: list[EntityRow],
    schema: InferredSchema,
    cost: CostTracker,
    cache: CacheDB | None,
    *,
    max_gap_searches: int = MAX_GAP_SEARCHES,
    progress_cb=None,
) -> list[EntityRow]:
    """Identify the highest-value gaps and fill them with targeted retrievals."""
    if not entities:
        return entities

    gaps = _rank_gaps(entities, schema, max_gap_searches)
    if not gaps:
        return entities

    # Late import to keep module import-time light.
    from agent.scraper import scrape_urls
    from agent.searcher import search_brave

    completed = 0
    for entity_idx, column in gaps:
        entity = entities[entity_idx]
        col_desc = schema.column_descriptions.get(column, "")
        query = f'"{entity.entity_name}" {column.replace("_", " ")}'.strip()
        if col_desc:
            # Add a hint token from the description to bias the query
            hint = col_desc.split(".")[0].split(",")[0]
            if hint and hint.lower() not in query.lower():
                query = f'{query} {hint}'
        logger.info("gap-fill query: %s", query)

        try:
            hits = await search_brave([query], cost, cache, max_results_per_query=4, max_total_urls=4)
        except Exception as e:  # noqa: BLE001
            logger.warning("gap-fill search failed: %s", e)
            continue
        if not hits:
            continue
        pages = await scrape_urls([h.url for h in hits], cost, cache, use_playwright_fallback=False)
        if not pages:
            continue

        # Look at top 2 pages worth of chunks
        chunks = []
        for p in pages[:2]:
            chunks.extend(chunk_text(p)[:4])  # cap to limit cost
        if not chunks:
            continue

        sources_found: list[SourceReference] = []
        best_value = ""
        for chunk in chunks:
            prompt = GAP_FILL_PROMPT.format(
                entity_name=entity.entity_name,
                column_name=column,
                column_description=col_desc,
                url=chunk.source_url,
                chunk_text=chunk.text[:5000],
            )
            try:
                raw = await call_llm(prompt, cost=cost, max_tokens=400, model=EXTRACTOR_MODEL)
                parsed = parse_json_loose(raw)
                if not isinstance(parsed, dict):
                    continue
                value = str(parsed.get("value") or "").strip()
                evidence = str(parsed.get("evidence") or "").strip()[:150]
                if not value:
                    continue
                if not best_value:
                    best_value = value
                sources_found.append(
                    SourceReference(
                        url=chunk.source_url,
                        page_title=chunk.page_title,
                        quote_snippet=evidence,
                        scraped_at=chunk.scraped_at,
                    )
                )
                if len(sources_found) >= 2:
                    break
            except Exception as e:  # noqa: BLE001
                logger.info("gap-fill LLM failed %s: %s", chunk.source_url, e)
                continue

        if best_value and sources_found:
            cell = CellValue(
                value=best_value,
                confidence=score_cell(best_value, sources_found, None, is_gap_fill=True),
                sources=sources_found,
            )
            entity.cells[column] = cell
            entity.overall_confidence = overall_confidence(
                [c.confidence for c in entity.cells.values()]
            )
            completed += 1
        if progress_cb:
            await progress_cb(completed, len(gaps), entity.entity_name, column)

    return entities


def _rank_gaps(
    entities: list[EntityRow],
    schema: InferredSchema,
    cap: int,
) -> list[tuple[int, str]]:
    """Return (entity_index, column) gap targets ordered by entity richness."""
    indexed = [
        (i, sum(1 for c in e.cells.values() if c.value), e)
        for i, e in enumerate(entities)
    ]
    # Prefer fuller, more confident rows — those are more likely real entities.
    indexed.sort(key=lambda x: (-x[1], -_conf_rank(x[2].overall_confidence)))

    gaps: list[tuple[int, str]] = []
    for i, _filled, e in indexed:
        for col in schema.columns:
            if col == "name":
                continue
            existing = e.cells.get(col)
            if existing is None or not existing.value:
                gaps.append((i, col))
        if len(gaps) >= cap:
            break
    return gaps[:cap]


def _conf_rank(c: Confidence) -> int:
    return {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.UNVERIFIED: 0}[c]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
