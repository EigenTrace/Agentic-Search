"""Two-pass LLM extraction: per-chunk extraction + cross-page entity merge."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Iterable

from config import EXTRACT_CHUNK_CHAR_LIMIT, EXTRACT_CONCURRENCY, EXTRACTOR_MODEL
from models.schema import (
    CellValue,
    Confidence,
    EntityRow,
    InferredSchema,
    RawExtraction,
    SourceReference,
    TextChunk,
)
from prompts.templates import EXTRACTION_PROMPT
from utils.confidence import overall_confidence, score_cell
from utils.dedup import best_canonical, normalize_name, same_entity
from utils.llm import CostTracker, call_llm, parse_json_loose

logger = logging.getLogger(__name__)


async def extract_from_chunks(
    chunks: list[TextChunk],
    schema: InferredSchema,
    cost: CostTracker,
) -> list[RawExtraction]:
    """Pass 1: extract structured entities from every chunk in parallel."""
    if not chunks:
        return []
    sem = asyncio.Semaphore(EXTRACT_CONCURRENCY)
    tasks = [_extract_one_chunk(c, schema, cost, sem) for c in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    flat: list[RawExtraction] = []
    for batch in results:
        flat.extend(batch)
    return flat


async def _extract_one_chunk(
    chunk: TextChunk,
    schema: InferredSchema,
    cost: CostTracker,
    sem: asyncio.Semaphore,
) -> list[RawExtraction]:
    async with sem:
        cols_with_desc = "\n".join(
            f"- {c}: {schema.column_descriptions.get(c, '')}".rstrip(": ")
            for c in schema.columns
        )
        prompt = EXTRACTION_PROMPT.format(
            entity_type=schema.entity_type,
            columns_with_descriptions=cols_with_desc,
            url=chunk.source_url,
            chunk_text=chunk.text[:EXTRACT_CHUNK_CHAR_LIMIT],
        )
        for attempt in range(2):
            try:
                raw = await call_llm(prompt, cost=cost, max_tokens=1200, model=EXTRACTOR_MODEL)
                parsed = parse_json_loose(raw)
                if not isinstance(parsed, list):
                    raise ValueError("Expected JSON array")
                return _coerce_extractions(parsed, chunk, schema)
            except Exception as e:  # noqa: BLE001
                logger.info(
                    "extract retry chunk %s#%d attempt %d: %s",
                    chunk.source_url, chunk.chunk_index, attempt + 1, e,
                )
        return []


def _coerce_extractions(
    parsed: list, chunk: TextChunk, schema: InferredSchema
) -> list[RawExtraction]:
    out: list[RawExtraction] = []
    valid_cols = {c.lower(): c for c in schema.columns}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = (item.get("entity_name") or item.get("name") or "").strip()
        if not name or normalize_name(name) in {"unknown", "the company", "company", "n a"}:
            continue
        attrs_raw = item.get("attributes") or {}
        evidence_raw = item.get("evidence") or {}
        attrs: dict[str, str] = {}
        evidence: dict[str, str] = {}
        for k, v in attrs_raw.items():
            if not isinstance(k, str):
                continue
            col = valid_cols.get(k.lower())
            if not col:
                continue
            if v is None:
                continue
            sval = str(v).strip()
            if not sval or sval.lower() in {"unknown", "n/a", "none", "null"}:
                continue
            attrs[col] = sval
        for k, v in evidence_raw.items():
            if not isinstance(k, str):
                continue
            col = valid_cols.get(k.lower())
            if col and v:
                evidence[col] = str(v).strip()[:150]
        if not attrs:
            continue
        out.append(
            RawExtraction(
                entity_name=name,
                attributes=attrs,
                evidence=evidence,
                source_url=chunk.source_url,
                page_title=chunk.page_title,
                chunk_index=chunk.chunk_index,
                scraped_at=chunk.scraped_at,
            )
        )
    return out


# ----- Pass 2: merge -----


def merge_extractions(
    raw: list[RawExtraction],
    schema: InferredSchema,
) -> list[EntityRow]:
    """Cluster raw extractions by entity name and merge column values."""
    if not raw:
        return []

    clusters: list[list[RawExtraction]] = []
    for ext in raw:
        placed = False
        for cluster in clusters:
            if same_entity(ext.entity_name, cluster[0].entity_name):
                cluster.append(ext)
                placed = True
                break
        if not placed:
            clusters.append([ext])

    entities: list[EntityRow] = []
    for cluster in clusters:
        # Skip clusters that look like noise (single-mention vague names)
        canonical = best_canonical([e.entity_name for e in cluster])
        cells: dict[str, CellValue] = {}
        for col in schema.columns:
            cell = _merge_column(col, cluster)
            if cell is not None:
                cells[col] = cell

        if not cells or len(cells) == 1 and "name" in cells:
            # No useful attributes — drop.
            continue

        # Ensure name cell exists; set it to canonical.
        if "name" in schema.columns:
            cells["name"] = CellValue(
                value=canonical,
                confidence=cells.get("name").confidence if "name" in cells else Confidence.MEDIUM,
                sources=cells.get("name").sources if "name" in cells else _collect_unique_sources(cluster),
            )

        overall = overall_confidence([c.confidence for c in cells.values()])
        entities.append(EntityRow(
            entity_name=canonical,
            cells=cells,
            overall_confidence=overall,
        ))

    # Order: rows with most filled cells first, then by confidence.
    entities.sort(
        key=lambda e: (
            -_confidence_rank(e.overall_confidence),
            -sum(1 for c in e.cells.values() if c.value),
        )
    )
    return entities


def _merge_column(column: str, cluster: list[RawExtraction]) -> CellValue | None:
    # Collect (value, source) pairs.
    contributions: list[tuple[str, RawExtraction]] = []
    for ext in cluster:
        v = ext.attributes.get(column, "").strip()
        if v:
            contributions.append((v, ext))
    if not contributions:
        return None

    # Bucket by normalized value.
    buckets: dict[str, list[tuple[str, RawExtraction]]] = defaultdict(list)
    for value, ext in contributions:
        key = _norm_value(value)
        # Merge values where one is a substring of another
        absorbed = False
        for existing_key in list(buckets.keys()):
            if key == existing_key:
                buckets[existing_key].append((value, ext))
                absorbed = True
                break
            if key in existing_key or existing_key in key:
                # Prefer the longer key
                if len(key) > len(existing_key):
                    buckets[key] = buckets.pop(existing_key)
                    buckets[key].append((value, ext))
                else:
                    buckets[existing_key].append((value, ext))
                absorbed = True
                break
        if not absorbed:
            buckets[key].append((value, ext))

    # Pick the bucket with most distinct sources; ties → most specific value (longest).
    def bucket_score(b: list[tuple[str, RawExtraction]]) -> tuple[int, int]:
        distinct_domains = {_domain(e.source_url) for _, e in b}
        longest = max(len(v) for v, _ in b)
        return (len(distinct_domains), longest)

    sorted_buckets = sorted(buckets.values(), key=bucket_score, reverse=True)
    winner = sorted_buckets[0]
    # Choose the most specific value within the winning bucket
    best_value = max(winner, key=lambda x: len(x[0]))[0]

    sources: list[SourceReference] = []
    seen_urls: set[str] = set()
    for _, ext in winner:
        if ext.source_url in seen_urls:
            continue
        seen_urls.add(ext.source_url)
        sources.append(
            SourceReference(
                url=ext.source_url,
                page_title=ext.page_title,
                quote_snippet=ext.evidence.get(column, "")[:150],
                scraped_at=ext.scraped_at,
            )
        )

    conflicts: list[str] = []
    if len(sorted_buckets) > 1:
        for b in sorted_buckets[1:]:
            alt = max(b, key=lambda x: len(x[0]))[0]
            if alt and _norm_value(alt) != _norm_value(best_value):
                conflicts.append(alt)
        conflicts = conflicts[:5]

    conf = score_cell(best_value, sources, conflicts or None)
    return CellValue(
        value=best_value,
        confidence=conf,
        sources=sources,
        conflicts=conflicts or None,
    )


def _collect_unique_sources(cluster: list[RawExtraction]) -> list[SourceReference]:
    seen: set[str] = set()
    out: list[SourceReference] = []
    for ext in cluster:
        if ext.source_url in seen:
            continue
        seen.add(ext.source_url)
        out.append(
            SourceReference(
                url=ext.source_url,
                page_title=ext.page_title,
                quote_snippet=next(iter(ext.evidence.values()), "")[:150],
                scraped_at=ext.scraped_at,
            )
        )
    return out


def _norm_value(v: str) -> str:
    return " ".join(v.lower().split())


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return url


def _confidence_rank(c: Confidence) -> int:
    return {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.UNVERIFIED: 0}[c]
