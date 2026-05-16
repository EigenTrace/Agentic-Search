"""Web searcher: Brave Search API + dedup + domain diversity."""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import httpx

from config import BRAVE_SEARCH_API_KEY, MAX_RESULTS_PER_QUERY, MAX_TOTAL_URLS
from models.schema import SearchHit
from utils.cache import CacheDB
from utils.llm import CostTracker

logger = logging.getLogger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

_TRACKING_PREFIXES = ("utm_", "ref_", "fbclid", "gclid", "mc_eid", "mc_cid", "ref")


def normalize_url(url: str) -> str:
    """Strip tracking params, fragments, trailing slashes."""
    try:
        parsed = urlparse(url.strip())
    except Exception:  # noqa: BLE001
        return url
    if not parsed.scheme:
        return url
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not any(k.lower().startswith(pref) for pref in _TRACKING_PREFIXES)
    ]
    new_query = urlencode(query_pairs)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(
        (parsed.scheme, parsed.netloc.lower(), path, parsed.params, new_query, "")
    )


async def search_brave(
    queries: list[str],
    cost: CostTracker,
    cache: CacheDB | None = None,
    max_results_per_query: int = MAX_RESULTS_PER_QUERY,
    max_total_urls: int = MAX_TOTAL_URLS,
) -> list[SearchHit]:
    """Run all queries (sequentially, to respect Brave's 1 req/sec free tier),
    deduplicate, prefer domain diversity, and return up to max_total_urls hits."""
    if not BRAVE_SEARCH_API_KEY:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is not set")

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    }

    all_hits: list[SearchHit] = []
    api_calls_made = 0
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        for q in queries:
            cached: list[SearchHit] | None = None
            if cache is not None:
                cached = await cache.get_search(q)
            if cached is not None:
                logger.info("search cache hit: %s (%d hits)", q, len(cached))
                all_hits.extend(cached)
                continue

            if api_calls_made > 0:
                # Brave free tier is ~1 req/sec; gentle pacing.
                await asyncio.sleep(1.05)

            try:
                hits = await _execute_query(client, q, max_results_per_query)
            except Exception as e:  # noqa: BLE001
                logger.warning("Brave search failed for %r: %s", q, e)
                continue

            api_calls_made += 1
            cost.search_api_calls += 1
            all_hits.extend(hits)
            if cache is not None:
                await cache.set_search(q, hits)

    return _dedupe_and_diversify(all_hits, max_total_urls)


async def _execute_query(
    client: httpx.AsyncClient, query: str, count: int
) -> list[SearchHit]:
    params = {"q": query, "count": min(count, 20)}
    resp = await client.get(BRAVE_ENDPOINT, params=params)
    resp.raise_for_status()
    data = resp.json()
    web_results = (data.get("web") or {}).get("results") or []
    hits: list[SearchHit] = []
    for item in web_results:
        url = item.get("url")
        if not url:
            continue
        hits.append(
            SearchHit(
                url=normalize_url(url),
                title=(item.get("title") or "").strip(),
                snippet=(item.get("description") or item.get("snippet") or "").strip(),
                query=query,
            )
        )
    return hits


def _dedupe_and_diversify(hits: Iterable[SearchHit], max_total: int) -> list[SearchHit]:
    seen_urls: set[str] = set()
    per_domain: dict[str, int] = {}
    out: list[SearchHit] = []
    for hit in hits:
        if hit.url in seen_urls:
            continue
        domain = urlparse(hit.url).netloc.lower()
        if per_domain.get(domain, 0) >= 2:
            continue
        seen_urls.add(hit.url)
        per_domain[domain] = per_domain.get(domain, 0) + 1
        out.append(hit)
        if len(out) >= max_total:
            break
    return out
