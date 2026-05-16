"""Web scraper: httpx + trafilatura, with optional Playwright fallback for JS pages."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib import robotparser
from urllib.parse import urlparse

import httpx
import trafilatura

from config import SCRAPE_CONCURRENCY, USER_AGENT
from models.schema import ScrapedPage
from utils.cache import CacheDB
from utils.llm import CostTracker

logger = logging.getLogger(__name__)

THIN_CONTENT_THRESHOLD = 200


async def scrape_urls(
    urls: list[str],
    cost: CostTracker,
    cache: CacheDB | None = None,
    *,
    use_playwright_fallback: bool = True,
) -> list[ScrapedPage]:
    """Scrape every URL concurrently. Cached pages bypass the network."""
    semaphore = asyncio.Semaphore(SCRAPE_CONCURRENCY)
    robots_cache: dict[str, robotparser.RobotFileParser | None] = {}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    ) as client:
        tasks = [
            _scrape_one(
                url,
                client,
                semaphore,
                cache,
                robots_cache,
                use_playwright_fallback=use_playwright_fallback,
            )
            for url in urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    pages = [r for r in results if r is not None and r.content]
    cost.pages_scraped += len(pages)
    return pages


async def _scrape_one(
    url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    cache: CacheDB | None,
    robots_cache: dict[str, robotparser.RobotFileParser | None],
    *,
    use_playwright_fallback: bool,
) -> Optional[ScrapedPage]:
    if cache is not None:
        cached = await cache.get_page(url)
        if cached is not None:
            logger.info("scrape cache: %s [%s]", url, "hit" if cached.content else "neg")
            return cached if cached.content else None

    if not await _robots_allows(url, client, robots_cache):
        logger.info("robots.txt disallows %s", url)
        if cache is not None:
            await cache.set_page(
                url,
                ScrapedPage(
                    url=url, title="", content="", scraped_at=_now_iso(),
                    method="robots_blocked", content_length=0,
                ),
                status="failed",
            )
        return None

    async with semaphore:
        page = await _fetch_with_httpx(url, client)
        if (page is None or len(page.content) < THIN_CONTENT_THRESHOLD) and use_playwright_fallback:
            pw_page = await _fetch_with_playwright(url)
            if pw_page is not None and len(pw_page.content) >= THIN_CONTENT_THRESHOLD:
                page = pw_page

    if page is None or not page.content:
        if cache is not None:
            await cache.set_page(
                url,
                ScrapedPage(
                    url=url, title="", content="", scraped_at=_now_iso(),
                    method="failed", content_length=0,
                ),
                status="failed",
            )
        return None

    if cache is not None:
        await cache.set_page(url, page, status="success")
    return page


async def _fetch_with_httpx(url: str, client: httpx.AsyncClient) -> Optional[ScrapedPage]:
    try:
        resp = await client.get(url)
    except Exception as e:  # noqa: BLE001
        logger.info("httpx fetch failed %s: %s", url, e)
        return None
    if resp.status_code >= 400:
        logger.info("HTTP %s for %s", resp.status_code, url)
        return None
    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return None
    try:
        extracted = trafilatura.extract(
            resp.text,
            include_tables=True,
            include_links=False,
            include_comments=False,
            favor_recall=True,
        ) or ""
    except Exception as e:  # noqa: BLE001
        logger.info("trafilatura failed %s: %s", url, e)
        extracted = ""
    title = _extract_title(resp.text)
    return ScrapedPage(
        url=url,
        title=title,
        content=extracted.strip(),
        scraped_at=_now_iso(),
        method="httpx",
        content_length=len(extracted),
    )


async def _fetch_with_playwright(url: str) -> Optional[ScrapedPage]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("Playwright not installed; skipping JS fallback for %s", url)
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(user_agent=USER_AGENT)
                page = await ctx.new_page()
                await page.goto(url, wait_until="networkidle", timeout=20000)
                html = await page.content()
                title = await page.title()
            finally:
                await browser.close()
    except Exception as e:  # noqa: BLE001
        logger.info("Playwright failed %s: %s", url, e)
        return None
    try:
        extracted = trafilatura.extract(
            html,
            include_tables=True,
            include_links=False,
            include_comments=False,
            favor_recall=True,
        ) or ""
    except Exception:  # noqa: BLE001
        extracted = ""
    return ScrapedPage(
        url=url,
        title=title or "",
        content=extracted.strip(),
        scraped_at=_now_iso(),
        method="playwright",
        content_length=len(extracted),
    )


async def _robots_allows(
    url: str,
    client: httpx.AsyncClient,
    cache: dict[str, robotparser.RobotFileParser | None],
) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in cache:
        rp = robotparser.RobotFileParser()
        try:
            resp = await client.get(f"{base}/robots.txt", timeout=8.0)
            if resp.status_code < 400 and resp.text:
                rp.parse(resp.text.splitlines())
            else:
                rp = None  # No robots.txt; treat as allowed
        except Exception:  # noqa: BLE001
            rp = None
        cache[base] = rp
    rp = cache[base]
    if rp is None:
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:  # noqa: BLE001
        return True


_TITLE_RE = None


def _extract_title(html: str) -> str:
    global _TITLE_RE
    if _TITLE_RE is None:
        import re
        _TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
    m = _TITLE_RE.search(html or "")
    if not m:
        return ""
    return m.group(1).strip().replace("\n", " ")[:200]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
