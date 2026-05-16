"""Centralised configuration and constants."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root if present
_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(_repo_root / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")

# Two-model setup: Sonnet for the high-leverage planning/synthesis steps,
# Haiku for the high-volume per-chunk extraction (3-5x cheaper).
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")            # planner, followups
EXTRACTOR_MODEL = os.environ.get("EXTRACTOR_MODEL", "claude-haiku-4-5-20251001")  # per-chunk extract, gap fill

# Pricing per 1M tokens (USD). Cost tracker assumes the dominant cost path
# is extraction (Haiku). Slight under/over-estimate is fine for the dashboard.
PRICE_INPUT_PER_MTOK = float(os.environ.get("PRICE_INPUT_PER_MTOK", "1.0"))
PRICE_OUTPUT_PER_MTOK = float(os.environ.get("PRICE_OUTPUT_PER_MTOK", "5.0"))

# Pipeline tuning knobs
MAX_RESULTS_PER_QUERY = 8
MAX_TOTAL_URLS = 15
SCRAPE_CONCURRENCY = 5
EXTRACT_CONCURRENCY = 5
MAX_GAP_SEARCHES = 6
MAX_CHUNKS_PER_RUN = 20
MIN_CHUNK_LENGTH = 300
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
EXTRACT_CHUNK_CHAR_LIMIT = 4000

# Cache TTLs (seconds)
SCRAPE_CACHE_TTL = 24 * 3600
SEARCH_CACHE_TTL = 60 * 60

# Filesystem
DATA_DIR = Path(os.environ.get("DATA_DIR", _repo_root / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DB_PATH = str(DATA_DIR / "cache.db")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 AgenticSearch/0.1"
)
