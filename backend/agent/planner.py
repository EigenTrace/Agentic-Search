"""Query planner: infers an entity schema and expands the query."""
from __future__ import annotations

import logging
from datetime import datetime

from models.schema import InferredSchema, SearchPlan
from prompts.templates import (
    DEFAULT_FALLBACK_COLUMN_DESCRIPTIONS,
    DEFAULT_FALLBACK_SCHEMA_COLUMNS,
    PLANNER_PROMPT,
)
from utils.llm import CostTracker, call_llm, parse_json_loose

logger = logging.getLogger(__name__)


async def plan_search(query: str, cost: CostTracker) -> SearchPlan:
    """Generate a structured search plan: schema + expanded queries."""
    prompt = PLANNER_PROMPT.format(query=query.strip())

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            raw = await call_llm(prompt, cost=cost, max_tokens=1200)
            data = parse_json_loose(raw)
            schema = _build_schema(data)
            expanded = _normalise_queries(data.get("expanded_queries", []), query)
            return SearchPlan(
                original_query=query,
                expanded_queries=expanded,
                schema=schema,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Planner attempt %d failed: %s", attempt + 1, e)
            last_err = e

    logger.error("Planner falling back to default schema after failure: %s", last_err)
    return SearchPlan(
        original_query=query,
        expanded_queries=_default_expansions(query),
        schema=InferredSchema(
            entity_type="entity",
            columns=DEFAULT_FALLBACK_SCHEMA_COLUMNS,
            column_descriptions=dict(DEFAULT_FALLBACK_COLUMN_DESCRIPTIONS),
        ),
    )


def _build_schema(data: dict) -> InferredSchema:
    entity_type = (data.get("entity_type") or "entity").strip().lower() or "entity"
    columns = [c.strip() for c in data.get("columns") or [] if isinstance(c, str) and c.strip()]
    if "name" not in columns:
        columns = ["name", *columns]
    # Dedup preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for c in columns:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    columns = deduped[:10]
    descriptions_raw = data.get("column_descriptions") or {}
    descriptions = {c: str(descriptions_raw.get(c, "")).strip() for c in columns}
    if not descriptions["name"]:
        descriptions["name"] = "Proper name of the entity"
    return InferredSchema(
        entity_type=entity_type,
        columns=columns,
        column_descriptions=descriptions,
    )


def _normalise_queries(queries: list, original: str) -> list[str]:
    cleaned = []
    seen = set()
    for q in queries:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q or q.lower() in seen:
            continue
        seen.add(q.lower())
        cleaned.append(q)
    if not cleaned:
        cleaned = _default_expansions(original)
    return cleaned[:6]


def _default_expansions(query: str) -> list[str]:
    year = datetime.utcnow().year
    return [
        query,
        f"best {query} {year}",
        f"top {query} list",
        f"{query} reviews",
        f"{query} comparison",
    ]
