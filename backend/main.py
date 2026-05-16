"""FastAPI app entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from agent.pipeline import refine_with_schema, run_pipeline, run_pipeline_sync
from models.schema import InferredSchema, RefineRequest
from utils.cache import CacheDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = CacheDB()
    await cache.init()
    app.state.cache = cache
    logger.info("Cache initialized")
    try:
        yield
    finally:
        await cache.close()


app = FastAPI(title="Agentic Search Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/search")
async def search_stream(q: str = Query(..., description="Topic query")):
    """SSE endpoint that streams status, partial, and final result events."""
    if not q.strip():
        raise HTTPException(400, "q is required")
    cache: CacheDB = app.state.cache
    return EventSourceResponse(run_pipeline(q.strip(), cache))


@app.get("/api/search/sync")
async def search_sync(q: str = Query(..., description="Topic query")):
    """Non-streaming version: returns the full result as JSON. Useful for benchmarks."""
    if not q.strip():
        raise HTTPException(400, "q is required")
    cache: CacheDB = app.state.cache
    result = await run_pipeline_sync(q.strip(), cache)
    return result.model_dump()


@app.post("/api/search/refine")
async def refine(payload: RefineRequest):
    """Re-run extraction with a user-modified schema. Uses cached scrapes."""
    if not payload.query.strip():
        raise HTTPException(400, "query is required")
    if not payload.columns:
        raise HTTPException(400, "columns must be non-empty")
    schema = InferredSchema(
        entity_type=payload.entity_type or "entity",
        columns=payload.columns,
        column_descriptions=payload.column_descriptions or {c: "" for c in payload.columns},
    )
    cache: CacheDB = app.state.cache
    result = await refine_with_schema(payload.query.strip(), schema, cache)
    return result.model_dump()
