"""Evaluation harness — runs the pipeline against a fixed query set and reports metrics."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path

# Make 'backend' importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.pipeline import run_pipeline_sync  # noqa: E402
from utils.cache import CacheDB  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_one(query: str, cache: CacheDB) -> dict:
    result = await run_pipeline_sync(query, cache)
    n_entities = len(result.entities)
    n_cells = sum(len(e.cells) for e in result.entities)
    filled = sum(
        1 for e in result.entities for cv in e.cells.values() if cv.value
    )
    total_cells = n_entities * len(result.schema.columns)
    confs = Counter(cv.confidence.value for e in result.entities for cv in e.cells.values() if cv.value)
    return {
        "query": query,
        "entity_type": result.schema.entity_type,
        "columns": result.schema.columns,
        "n_entities": n_entities,
        "fill_rate": round(filled / total_cells, 3) if total_cells else 0.0,
        "confidence_distribution": dict(confs),
        "cost_usd": result.cost.estimated_cost_usd,
        "latency_s": result.cost.wall_clock_seconds,
        "llm_calls": result.cost.total_llm_calls,
        "pages_scraped": result.cost.total_pages_scraped,
        "result": result.model_dump(),
    }


def render_markdown(reports: list[dict]) -> str:
    header = (
        "| Query | Type | # Entities | Fill rate | High | Med | Low | Unverif | Cost | Latency | LLM calls |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for r in reports:
        c = r["confidence_distribution"]
        rows.append(
            f"| {r['query']} | {r['entity_type']} | {r['n_entities']} | {r['fill_rate']*100:.0f}% | "
            f"{c.get('high', 0)} | {c.get('medium', 0)} | {c.get('low', 0)} | {c.get('unverified', 0)} | "
            f"${r['cost_usd']:.3f} | {r['latency_s']:.1f}s | {r['llm_calls']} |"
        )
    return header + "\n".join(rows) + "\n"


async def main(out_dir: Path, queries_path: Path, limit: int | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with queries_path.open() as f:
        queries = json.load(f)
    if limit:
        queries = queries[:limit]

    cache = CacheDB()
    await cache.init()

    reports: list[dict] = []
    try:
        for q in queries:
            logger.info("=== running: %s ===", q["query"])
            try:
                report = await run_one(q["query"], cache)
            except Exception as e:  # noqa: BLE001
                logger.exception("Failed on %s", q["query"])
                report = {"query": q["query"], "error": str(e)}
            reports.append(report)
            # Write per-query result
            slug = "".join(c if c.isalnum() else "_" for c in q["query"].lower())[:60]
            (out_dir / f"{slug}.json").write_text(json.dumps(report, indent=2, default=str))
    finally:
        await cache.close()

    md = render_markdown([r for r in reports if "error" not in r])
    (out_dir / "benchmark_report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "eval_results")
    parser.add_argument("--queries", type=Path, default=Path(__file__).resolve().parent / "test_queries.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.out, args.queries, args.limit))
