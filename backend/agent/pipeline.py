"""End-to-end pipeline orchestrator. Emits SSE events for the frontend."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from agent.extractor import extract_from_chunks, merge_extractions
from agent.gap_filler import fill_gaps
from agent.planner import plan_search
from agent.scraper import scrape_urls
from agent.searcher import search_brave
from config import MAX_CHUNKS_PER_RUN, MIN_CHUNK_LENGTH
from models.schema import (
    EntityRow,
    InferredSchema,
    PipelineCost,
    SearchPlan,
    SearchResult,
)
from prompts.templates import FOLLOWUP_PROMPT
from utils.cache import CacheDB
from utils.chunker import chunk_text
from utils.llm import CostTracker, call_llm, parse_json_loose

logger = logging.getLogger(__name__)


def _sse(event: str, payload: dict) -> dict:
    return {"event": event, "data": json.dumps(payload, default=str)}


async def run_pipeline(
    query: str, cache: CacheDB
) -> AsyncGenerator[dict, None]:
    """Yield Server-Sent-Event dicts (event, data) through the full agent flow."""
    cost = CostTracker()
    started = time.perf_counter()

    try:
        yield _sse("status", {"stage": "planning", "message": "Planning search strategy...", "progress": 0.05})
        plan = await plan_search(query, cost)
        yield _sse("schema", {
            "entity_type": plan.schema.entity_type,
            "columns": plan.schema.columns,
            "column_descriptions": plan.schema.column_descriptions,
            "expanded_queries": plan.expanded_queries,
        })

        yield _sse("status", {
            "stage": "searching",
            "message": f"Running {len(plan.expanded_queries)} web searches...",
            "progress": 0.15,
        })
        hits = await search_brave(plan.expanded_queries, cost, cache)
        if not hits:
            yield _sse("status", {"stage": "searching", "message": "No search results found.", "progress": 0.2})

        yield _sse("status", {
            "stage": "scraping",
            "message": f"Scraping {len(hits)} pages...",
            "progress": 0.3,
        })
        pages = await scrape_urls([h.url for h in hits], cost, cache)
        yield _sse("status", {
            "stage": "scraping",
            "message": f"Scraped {len(pages)} pages successfully.",
            "progress": 0.45,
        })

        yield _sse("status", {"stage": "extracting", "message": "Analyzing content with LLM...", "progress": 0.55})
        chunks = []
        for p in pages:
            chunks.extend(chunk_text(p))
        # Drop very short chunks (likely nav/footer) and cap total to control cost.
        chunks = [c for c in chunks if len(c.text) >= MIN_CHUNK_LENGTH]
        if len(chunks) > MAX_CHUNKS_PER_RUN:
            chunks = chunks[:MAX_CHUNKS_PER_RUN]
        logger.info("Extracting from %d chunks across %d pages", len(chunks), len(pages))
        raw = await extract_from_chunks(chunks, plan.schema, cost)
        logger.info("Pass 1 produced %d raw extractions", len(raw))

        yield _sse("status", {"stage": "resolving", "message": "Resolving entities across sources...", "progress": 0.75})
        entities = merge_extractions(raw, plan.schema)
        yield _sse("partial", {"entities": [e.model_dump() for e in entities]})

        yield _sse("status", {
            "stage": "gap_filling",
            "message": "Filling information gaps...",
            "progress": 0.85,
        })
        entities = await fill_gaps(entities, plan.schema, cost, cache)

        yield _sse("status", {"stage": "synthesizing", "message": "Generating follow-up suggestions...", "progress": 0.95})
        followups = await _generate_followups(query, plan.schema, entities, cost)

        elapsed = time.perf_counter() - started
        cost_summary = PipelineCost(
            total_search_api_calls=cost.search_api_calls,
            total_pages_scraped=cost.pages_scraped,
            total_llm_calls=cost.llm_calls,
            total_input_tokens=cost.input_tokens,
            total_output_tokens=cost.output_tokens,
            estimated_cost_usd=round(cost.estimated_cost_usd, 4),
            wall_clock_seconds=round(elapsed, 2),
        )
        result = SearchResult(
            query=query,
            schema=plan.schema,
            entities=entities,
            suggested_followups=followups,
            cost=cost_summary,
        )
        yield _sse("result", result.model_dump())

    except Exception as e:  # noqa: BLE001
        logger.exception("Pipeline failed")
        yield _sse("error", {"message": str(e)})


async def run_pipeline_sync(query: str, cache: CacheDB) -> SearchResult:
    """Non-streaming version used by benchmarks and tests."""
    cost = CostTracker()
    started = time.perf_counter()
    plan = await plan_search(query, cost)
    hits = await search_brave(plan.expanded_queries, cost, cache)
    pages = await scrape_urls([h.url for h in hits], cost, cache)
    chunks: list = []
    for p in pages:
        chunks.extend(chunk_text(p))
    chunks = [c for c in chunks if len(c.text) >= MIN_CHUNK_LENGTH]
    if len(chunks) > MAX_CHUNKS_PER_RUN:
        chunks = chunks[:MAX_CHUNKS_PER_RUN]
    raw = await extract_from_chunks(chunks, plan.schema, cost)
    entities = merge_extractions(raw, plan.schema)
    entities = await fill_gaps(entities, plan.schema, cost, cache)
    followups = await _generate_followups(query, plan.schema, entities, cost)
    elapsed = time.perf_counter() - started
    return SearchResult(
        query=query,
        schema=plan.schema,
        entities=entities,
        suggested_followups=followups,
        cost=PipelineCost(
            total_search_api_calls=cost.search_api_calls,
            total_pages_scraped=cost.pages_scraped,
            total_llm_calls=cost.llm_calls,
            total_input_tokens=cost.input_tokens,
            total_output_tokens=cost.output_tokens,
            estimated_cost_usd=round(cost.estimated_cost_usd, 4),
            wall_clock_seconds=round(elapsed, 2),
        ),
    )


async def refine_with_schema(
    query: str,
    schema: InferredSchema,
    cache: CacheDB,
) -> SearchResult:
    """Re-run extraction with a user-modified schema, reusing cached scrapes."""
    cost = CostTracker()
    started = time.perf_counter()
    plan_queries = await _quick_expand(query, schema, cost)
    hits = await search_brave(plan_queries, cost, cache)
    pages = await scrape_urls([h.url for h in hits], cost, cache)
    chunks: list = []
    for p in pages:
        chunks.extend(chunk_text(p))
    chunks = [c for c in chunks if len(c.text) >= MIN_CHUNK_LENGTH]
    if len(chunks) > MAX_CHUNKS_PER_RUN:
        chunks = chunks[:MAX_CHUNKS_PER_RUN]
    raw = await extract_from_chunks(chunks, schema, cost)
    entities = merge_extractions(raw, schema)
    entities = await fill_gaps(entities, schema, cost, cache)
    followups = await _generate_followups(query, schema, entities, cost)
    elapsed = time.perf_counter() - started
    return SearchResult(
        query=query,
        schema=schema,
        entities=entities,
        suggested_followups=followups,
        cost=PipelineCost(
            total_search_api_calls=cost.search_api_calls,
            total_pages_scraped=cost.pages_scraped,
            total_llm_calls=cost.llm_calls,
            total_input_tokens=cost.input_tokens,
            total_output_tokens=cost.output_tokens,
            estimated_cost_usd=round(cost.estimated_cost_usd, 4),
            wall_clock_seconds=round(elapsed, 2),
        ),
    )


async def _quick_expand(query: str, schema: InferredSchema, cost: CostTracker) -> list[str]:
    """Cheap query expansion using the same schema (no LLM call)."""
    from datetime import datetime
    year = datetime.utcnow().year
    return [
        query,
        f"top {query} {year}",
        f"{query} {schema.entity_type} list",
        f"best {query} review",
    ]


async def _generate_followups(
    query: str,
    schema: InferredSchema,
    entities: list[EntityRow],
    cost: CostTracker,
) -> list[str]:
    if not entities:
        return []
    names = "\n".join(f"- {e.entity_name}" for e in entities[:10])
    prompt = FOLLOWUP_PROMPT.format(
        query=query,
        entity_type=schema.entity_type,
        entity_names=names,
    )
    try:
        raw = await call_llm(prompt, cost=cost, max_tokens=400)
        parsed = parse_json_loose(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()][:4]
    except Exception as e:  # noqa: BLE001
        logger.info("followup generation failed: %s", e)
    return []
