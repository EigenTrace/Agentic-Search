"""SQLite-backed cache for scrape results and search results."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from config import CACHE_DB_PATH, SCRAPE_CACHE_TTL, SEARCH_CACHE_TTL
from models.schema import ScrapedPage, SearchHit

logger = logging.getLogger(__name__)


SCHEMA_SQL = [
    """CREATE TABLE IF NOT EXISTS scrape_cache (
        url TEXT PRIMARY KEY,
        title TEXT,
        content TEXT,
        method TEXT,
        scraped_at TEXT,
        cached_at REAL NOT NULL,
        status TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS search_cache (
        query TEXT PRIMARY KEY,
        results_json TEXT NOT NULL,
        cached_at REAL NOT NULL
    )""",
]


class CacheDB:
    def __init__(self, db_path: str = CACHE_DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        for ddl in SCHEMA_SQL:
            await self._db.execute(ddl)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def get_page(self, url: str) -> Optional[ScrapedPage]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT title, content, method, scraped_at, cached_at, status FROM scrape_cache WHERE url = ?",
            (url,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        title, content, method, scraped_at, cached_at, status = row
        if time.time() - cached_at > SCRAPE_CACHE_TTL:
            return None
        if status != "success" or not content:
            # Negative cache: tell caller we tried and failed — avoid retry.
            return ScrapedPage(
                url=url,
                title=title or "",
                content="",
                scraped_at=scraped_at or _now_iso(),
                method=method or "failed",
                content_length=0,
            )
        return ScrapedPage(
            url=url,
            title=title or "",
            content=content,
            scraped_at=scraped_at or _now_iso(),
            method=method or "httpx",
            content_length=len(content),
        )

    async def set_page(self, url: str, page: ScrapedPage, *, status: str = "success") -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO scrape_cache
               (url, title, content, method, scraped_at, cached_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                url,
                page.title,
                page.content,
                page.method,
                page.scraped_at,
                time.time(),
                status,
            ),
        )
        await self._db.commit()

    async def get_search(self, query: str) -> Optional[list[SearchHit]]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT results_json, cached_at FROM search_cache WHERE query = ?",
            (query,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        results_json, cached_at = row
        if time.time() - cached_at > SEARCH_CACHE_TTL:
            return None
        try:
            payload = json.loads(results_json)
            return [SearchHit(**item) for item in payload]
        except Exception as e:  # noqa: BLE001
            logger.warning("Corrupt search cache row for %r: %s", query, e)
            return None

    async def set_search(self, query: str, hits: list[SearchHit]) -> None:
        assert self._db is not None
        payload = json.dumps([h.model_dump() for h in hits])
        await self._db.execute(
            "INSERT OR REPLACE INTO search_cache (query, results_json, cached_at) VALUES (?, ?, ?)",
            (query, payload, time.time()),
        )
        await self._db.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
