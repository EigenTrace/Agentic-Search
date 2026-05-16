# Agentic Search Engine — Full Implementation Spec

> **Context**: This is a coding challenge submission for Naget (naget.com), an AI search startup founded by Chris Samarinas, a PhD student at UMass Amherst specializing in information retrieval, conversational search, proactive language models, and nugget-based RAG evaluation. The evaluator deeply cares about retrieval quality, source attribution, and agentic autonomy. Read the accompanying `challenge.md` for the official requirements. This document specifies everything beyond the minimum.

---

## 1. Project Overview

Build an **agentic search system** that takes a topic query (e.g., "AI startups in healthcare") and produces a structured table of discovered entities with relevant attributes, sourced from the web. The system goes beyond basic search+extract by being truly agentic: it infers schemas, expands queries, fills gaps autonomously, resolves entities across sources, and traces every cell value back to its source.

### Tech Stack (locked in — do not change)

| Layer | Technology | Why |
|---|---|---|
| Backend | **Python 3.11+ / FastAPI** | Async-native, great for parallel I/O |
| Search API | **Brave Search API** | Free tier (2k queries/mo), clean JSON API |
| Scraping | **httpx** (async) + **trafilatura** for content extraction | Fast, reliable main-content extraction |
| Scraping fallback | **playwright** (async) | For JS-rendered pages when trafilatura returns thin content |
| LLM | **Anthropic API (Claude Sonnet 4)** via `anthropic` Python SDK | Excellent at structured extraction |
| Cache | **SQLite** via `aiosqlite` | Zero-config, portable, async-compatible |
| Frontend | **React 18 + Vite + Tailwind CSS** | Fast dev, polished output |
| Deployment | **Docker + docker-compose** | Single `docker-compose up` for reviewers |

### API Keys Required (via `.env`)

```
ANTHROPIC_API_KEY=...
BRAVE_SEARCH_API_KEY=...
```

---

## 2. Repository Structure

```
agentic-search/
├── README.md
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings, env vars, constants
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── planner.py           # Query understanding + schema inference
│   │   ├── searcher.py          # Brave Search API + query expansion
│   │   ├── scraper.py           # httpx + trafilatura + playwright fallback
│   │   ├── extractor.py         # LLM extraction: per-chunk + merge
│   │   ├── gap_filler.py        # Multi-hop: detect gaps, search to fill
│   │   └── pipeline.py          # Orchestrates the full agent loop
│   ├── models/
│   │   ├── __init__.py
│   │   └── schema.py            # All Pydantic models
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── templates.py         # All LLM prompt templates (centralized)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── cache.py             # SQLite caching layer
│   │   ├── chunker.py           # Text chunking with source metadata
│   │   ├── confidence.py        # Per-cell confidence scoring
│   │   └── dedup.py             # Entity deduplication / fuzzy matching
│   └── eval/
│       ├── benchmark.py         # Evaluation harness
│       └── test_queries.json    # 8-10 diverse test queries
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── tailwind.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js               # SSE client + REST helpers
│       ├── components/
│       │   ├── SearchBar.jsx
│       │   ├── ResultsTable.jsx
│       │   ├── SourcePanel.jsx
│       │   ├── SchemaEditor.jsx
│       │   ├── CostDashboard.jsx
│       │   ├── StatusFeed.jsx   # Shows pipeline progress messages
│       │   └── QuerySuggestions.jsx
│       └── hooks/
│           └── useSearch.js     # Hook managing SSE stream + state
└── eval_results/                # Checked-in example outputs
    ├── ai_healthcare_startups.json
    ├── pizza_brooklyn.json
    └── open_source_databases.json
```

---

## 3. Data Models (backend/models/schema.py)

Define these Pydantic models. They are the contract between every component.

```python
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

class Confidence(str, Enum):
    HIGH = "high"        # 2+ independent sources agree
    MEDIUM = "medium"    # 1 source, specific value
    LOW = "low"          # 1 source, vague value
    UNVERIFIED = "unverified"  # inferred or gap-filled

class SourceReference(BaseModel):
    url: str
    page_title: str
    quote_snippet: str          # The exact text span supporting this value (max ~150 chars)
    scraped_at: str             # ISO timestamp

class CellValue(BaseModel):
    value: str
    confidence: Confidence
    sources: list[SourceReference]    # Every source that contributed to this value
    conflicts: list[str] | None = None  # Alternative values from disagreeing sources

class EntityRow(BaseModel):
    entity_name: str
    cells: dict[str, CellValue]       # column_name -> CellValue
    overall_confidence: Confidence

class InferredSchema(BaseModel):
    entity_type: str                  # e.g., "company", "restaurant", "tool"
    columns: list[str]                # e.g., ["name", "founded", "funding", ...]
    column_descriptions: dict[str, str]  # column_name -> what it means

class SearchPlan(BaseModel):
    original_query: str
    expanded_queries: list[str]       # 4-6 diverse search queries
    schema: InferredSchema

class PipelineStatus(BaseModel):
    stage: str                        # e.g., "planning", "searching", "scraping", "extracting", "gap_filling"
    message: str
    progress: float | None = None     # 0.0 - 1.0

class PipelineCost(BaseModel):
    total_search_api_calls: int
    total_pages_scraped: int
    total_llm_calls: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    wall_clock_seconds: float

class SearchResult(BaseModel):
    query: str
    schema: InferredSchema
    entities: list[EntityRow]
    suggested_followups: list[str]    # Proactive query suggestions
    cost: PipelineCost
```

---

## 4. Component Specifications

### 4.1 Query Planner (`agent/planner.py`)

**Purpose**: Take a raw user query, infer the entity schema, and generate a search plan.

**Function signature**:
```python
async def plan_search(query: str) -> SearchPlan
```

**LLM Prompt Strategy** (put in `prompts/templates.py`):

```
You are a search planning agent. Given a user's topic query, you must:

1. Identify the TYPE of entity they're looking for (company, restaurant, tool, person, etc.)
2. Infer 6-10 relevant COLUMNS that would make a useful comparison table for these entities. 
   - Always include "name" as the first column.
   - Choose columns that are: specific to this entity type, factual/verifiable, useful for comparison.
   - Include a mix of: identifiers (name, website), categorical (type, category), quantitative (price, rating, funding), descriptive (short description).
3. Generate 4-6 DIVERSE search queries that will surface different relevant results.
   - Vary the phrasing and angle (lists, comparisons, reviews, news).
   - Include at least one query targeting recent/2025-2026 results.
   - Include at least one query targeting a curated list or ranking.

User query: "{query}"

Respond in this exact JSON format (no markdown, no backticks):
{{
  "entity_type": "...",
  "columns": ["name", ...],
  "column_descriptions": {{"name": "...", ...}},
  "expanded_queries": ["...", "...", ...]
}}
```

**Important implementation notes**:
- Use `response_format` or parse JSON from the response. Always wrap in try/except with a retry on parse failure.
- Cap columns at 10 max. If the LLM returns more, truncate.
- If schema inference fails after 2 retries, fall back to a generic schema: `["name", "description", "website", "category", "notable_features"]`.

---

### 4.2 Web Searcher (`agent/searcher.py`)

**Purpose**: Execute search queries via Brave Search API, return deduplicated URLs with snippets.

**Function signature**:
```python
async def search_brave(queries: list[str], max_results_per_query: int = 10) -> list[SearchHit]
```

Where `SearchHit` is:
```python
class SearchHit(BaseModel):
    url: str
    title: str
    snippet: str
    query: str  # which expanded query found this
```

**Implementation details**:
- Use `httpx.AsyncClient` to call `https://api.search.brave.com/res/v1/web/search`
- Headers: `{"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": BRAVE_API_KEY}`
- Query params: `{"q": query, "count": max_results_per_query}`
- Fire ALL queries concurrently with `asyncio.gather`
- Deduplicate results by normalized URL (strip trailing slash, fragment, utm params)
- Prioritize domain diversity: if 5+ results from same domain, keep only the top 2
- Return max 20-25 unique URLs total across all queries
- Handle rate limits gracefully (Brave free tier: 1 req/sec). Add a small delay between requests if needed.

---

### 4.3 Web Scraper (`agent/scraper.py`)

**Purpose**: Fetch and extract main content from URLs.

**Function signatures**:
```python
async def scrape_urls(urls: list[str], cache: CacheDB) -> list[ScrapedPage]
```

Where `ScrapedPage` is:
```python
class ScrapedPage(BaseModel):
    url: str
    title: str
    content: str           # Clean main-content text
    scraped_at: str
    method: str            # "httpx" or "playwright"
    content_length: int
```

**Implementation details**:

1. **Check cache first**: For each URL, check SQLite. If cached and < 24h old, use cached version.

2. **Primary path (httpx + trafilatura)**:
   ```python
   async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
       response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 ..."})
   content = trafilatura.extract(response.text, include_tables=True, include_links=True)
   ```

3. **Thin content detection**: If `trafilatura.extract` returns `None` or < 200 characters, flag for playwright fallback.

4. **Playwright fallback** (for JS-rendered pages):
   ```python
   async with async_playwright() as p:
       browser = await p.chromium.launch(headless=True)
       page = await browser.new_page()
       await page.goto(url, wait_until="networkidle", timeout=20000)
       html = await page.content()
       content = trafilatura.extract(html, ...)
   ```

5. **Concurrency**: Scrape up to 5 URLs concurrently with `asyncio.Semaphore(5)`.

6. **Error handling**: Catch timeouts, 403s, 404s, connection errors. Log and skip failed URLs. Never crash the pipeline.

7. **robots.txt**: Check robots.txt before scraping. Skip disallowed URLs. Use `urllib.robotparser`.

8. **Cache all results** in SQLite (both successes and failures to avoid re-trying broken URLs).

---

### 4.4 Text Chunker (`utils/chunker.py`)

**Purpose**: Split scraped content into overlapping chunks with metadata.

**Function signature**:
```python
def chunk_text(page: ScrapedPage, chunk_size: int = 1500, overlap: int = 200) -> list[TextChunk]
```

Where:
```python
class TextChunk(BaseModel):
    text: str
    source_url: str
    page_title: str
    chunk_index: int
    scraped_at: str
```

**Notes**:
- Chunk on paragraph boundaries when possible (split on `\n\n` first, then merge small paragraphs until hitting `chunk_size` chars).
- Each chunk carries full source metadata — this is how we achieve per-cell attribution.
- `chunk_size` is in characters, not tokens. 1500 chars ≈ ~375 tokens.

---

### 4.5 LLM Extractor (`agent/extractor.py`)

This is the most critical component. It runs in **two passes**.

#### Pass 1: Per-Chunk Extraction

**Function signature**:
```python
async def extract_from_chunks(
    chunks: list[TextChunk], 
    schema: InferredSchema
) -> list[RawExtraction]
```

Where:
```python
class RawExtraction(BaseModel):
    entity_name: str
    attributes: dict[str, str]           # column_name -> extracted value
    evidence: dict[str, str]             # column_name -> quote snippet from text
    source_url: str
    page_title: str
    chunk_index: int
```

**LLM Prompt for Pass 1** (in `prompts/templates.py`):

```
You are a precise information extraction agent. Extract structured entity data from the text below.

Entity type: {entity_type}
Columns to extract: {columns_with_descriptions}

Text (from {url}):
---
{chunk_text}
---

Instructions:
- Extract ALL entities of type "{entity_type}" mentioned in this text.
- For each entity, extract values for as many columns as the text supports. Leave columns empty ("") if no information is found — do NOT fabricate.
- For each extracted value, provide the exact quote snippet (max 150 chars) from the text that supports it.
- Be precise: extract specific values (e.g., "$4.2M Series A in 2023") not vague summaries ("well-funded").

Respond in this exact JSON format (no markdown, no backticks):
[
  {{
    "entity_name": "...",
    "attributes": {{"column1": "value1", "column2": "value2", ...}},
    "evidence": {{"column1": "supporting quote", "column2": "supporting quote", ...}}
  }},
  ...
]

If no relevant entities are found, respond with: []
```

**Implementation notes**:
- Process chunks in batches of 5 concurrently using `asyncio.Semaphore(5)`.
- Use `model="claude-sonnet-4-20250514"`, `max_tokens=2000`, `temperature=0`.
- Parse JSON response. On parse failure, retry once. On second failure, skip that chunk and log a warning.
- Track token usage from the API response for cost reporting.

#### Pass 2: Entity Resolution & Merging

**Function signature**:
```python
async def merge_extractions(
    raw: list[RawExtraction], 
    schema: InferredSchema
) -> list[EntityRow]
```

**Logic (implement in Python, not via LLM)**:

1. **Group by entity name** using fuzzy matching:
   - Normalize names: lowercase, strip "Inc.", "LLC", "Corp.", etc.
   - Use `thefuzz` (fuzzywuzzy) library: `fuzz.token_sort_ratio(a, b) > 85` → same entity
   - Build clusters of RawExtractions that refer to the same entity

2. **Merge within each cluster**:
   - For each column, collect all non-empty values across all RawExtractions in the cluster
   - If all values agree (or are substrings of each other) → use the most specific/longest value
   - If values conflict → pick the one with the most sources supporting it, and store the others in `CellValue.conflicts`
   - Build the `sources` list for each cell from all contributing RawExtractions

3. **Build CellValue with confidence** (delegate to `utils/confidence.py`)

4. **Compute overall entity confidence** as the average across cells

5. **Sort entities by overall_confidence descending** (most confident first)

---

### 4.6 Confidence Scoring (`utils/confidence.py`)

**Function signature**:
```python
def score_cell(value: str, sources: list[SourceReference], conflicts: list[str] | None) -> Confidence
```

**Logic**:
```
if len(sources) >= 2 and no conflicts:
    return HIGH
elif len(sources) == 1 and value is specific (contains numbers, dates, or proper nouns):
    return MEDIUM
elif len(sources) == 1 and value is vague:
    return LOW
else:  # has conflicts or is gap-filled
    return UNVERIFIED if gap-filled else MEDIUM
```

"Specific" heuristic: value matches regex for numbers, dollar amounts, dates, or is < 50 chars and contains a capitalized proper noun.

---

### 4.7 Gap Filler — Multi-Hop Agent (`agent/gap_filler.py`)

This is the key differentiator. After the first extraction + merge, many cells will be empty. The gap filler autonomously searches to fill them.

**Function signature**:
```python
async def fill_gaps(
    entities: list[EntityRow],
    schema: InferredSchema,
    cache: CacheDB,
    max_gap_searches: int = 10
) -> list[EntityRow]
```

**Logic**:

1. **Identify gaps**: For each entity, find columns with empty values. Prioritize entities with the most existing data (they're more likely real/important entities worth filling).

2. **Generate targeted queries**: For each gap, create a specific search query:
   - Pattern: `"{entity_name}" {column_name}` 
   - E.g., if "Tempus AI" is missing "funding": search `"Tempus AI" funding raised`
   - Limit to `max_gap_searches` total queries to control cost

3. **Run the search → scrape → extract pipeline** for each targeted query, but scoped:
   - Only extract data for the specific entity + column we're targeting
   - Use a more focused extraction prompt that names the entity and the missing attribute

4. **Merge new extractions** into existing EntityRows. Mark gap-filled cells with `confidence = UNVERIFIED` unless confirmed by a strong source.

5. **Return updated entities**

**Focused extraction prompt for gap filling**:
```
Extract the {column_name} of "{entity_name}" from this text.
Text: {chunk_text}

If found, respond with JSON: {{"value": "...", "evidence": "exact quote supporting this"}}
If not found, respond with: {{"value": "", "evidence": ""}}
```

---

### 4.8 Pipeline Orchestrator (`agent/pipeline.py`)

Ties everything together and emits SSE events for the frontend.

**Function signature**:
```python
async def run_pipeline(query: str) -> AsyncGenerator[ServerSentEvent, None]
```

**Pipeline flow**:
```
1. Emit status: "Planning search strategy..."
2. plan = await plan_search(query)
3. Emit status: "Searching the web..." + emit schema
4. hits = await search_brave(plan.expanded_queries)
5. Emit status: "Scraping {len(hits)} pages..."
6. pages = await scrape_urls([h.url for h in hits], cache)
7. Emit status: "Analyzing content..."
8. chunks = flatten([chunk_text(p) for p in pages])
9. raw = await extract_from_chunks(chunks, plan.schema)
10. Emit status: "Resolving entities..."
11. entities = await merge_extractions(raw, plan.schema)
12. Emit partial results (the initial table)
13. Emit status: "Filling information gaps..."
14. entities = await fill_gaps(entities, plan.schema, cache)
15. Generate followup suggestions via LLM
16. Emit final results + cost summary
```

**SSE Event Types** (JSON payloads):
```
event: status    → {"stage": "...", "message": "...", "progress": 0.3}
event: schema    → {"entity_type": "...", "columns": [...]}
event: partial   → {"entities": [...]}  (after initial extraction)
event: result    → {"entities": [...], "suggested_followups": [...], "cost": {...}}
event: error     → {"message": "..."}
```

---

### 4.9 Cache Layer (`utils/cache.py`)

**SQLite schema**:
```sql
CREATE TABLE IF NOT EXISTS scrape_cache (
    url TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,
    method TEXT,
    scraped_at TEXT,
    status TEXT  -- 'success' or 'failed'
);

CREATE TABLE IF NOT EXISTS search_cache (
    query TEXT PRIMARY KEY,
    results_json TEXT,
    searched_at TEXT
);
```

**Functions**:
```python
class CacheDB:
    async def init(self, db_path: str = "cache.db")
    async def get_page(self, url: str) -> ScrapedPage | None
    async def set_page(self, url: str, page: ScrapedPage)
    async def get_search(self, query: str) -> list[SearchHit] | None
    async def set_search(self, query: str, hits: list[SearchHit])
```

Cache expiry: 24 hours for scraped pages, 1 hour for search results.

---

## 5. FastAPI Routes (`main.py`)

```python
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Agentic Search Engine")

# CORS for frontend
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/search")
async def search(q: str = Query(..., description="Topic query")):
    """
    SSE endpoint. Streams status updates, partial results, and final results.
    """
    return EventSourceResponse(run_pipeline(q))

@app.post("/api/search/refine")
async def refine_search(request: RefineRequest):
    """
    Re-run extraction with a user-modified schema.
    Body: { "query": "...", "schema": { "columns": [...] } }
    Uses cached scrape data, only re-runs extraction.
    """
    ...

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

Install `sse-starlette` for SSE support.

---

## 6. Frontend Specification

### 6.1 Design Direction

**Aesthetic**: Clean, editorial, data-focused. Think "modern Bloomberg terminal meets Notion." NOT generic SaaS. The UI should feel like a professional research tool.

**Color scheme**: Dark mode primary. Use a near-black background (#0a0a0f or similar), with high-contrast white/light-gray text. One strong accent color (electric blue, #3b82f6 or teal #14b8a6) for interactive elements and confidence-HIGH indicators. Amber for MEDIUM, dim gray for LOW.

**Typography**: Use a monospace or semi-monospace font for the data table (JetBrains Mono or similar from Google Fonts). Use a clean sans-serif for the rest (e.g., Instrument Sans, General Sans, or Geist from Google Fonts). Do NOT use Inter or Roboto.

**Key visual elements**:
- The results table should be the hero — large, dominant, well-spaced
- Subtle grid lines, generous cell padding
- Confidence indicators as small colored dots (●) next to each cell value
- Source panel slides in from the right when you click a cell
- Pipeline status shown as an animated step indicator above the table
- Cost dashboard as a small collapsible panel in the bottom-right corner

### 6.2 Component Details

#### `SearchBar.jsx`
- Large centered input on initial load (think Google-style)
- After search starts, shrinks and pins to the top
- Shows 3 example query chips below the input: "AI startups in healthcare", "top pizza places in Brooklyn", "open source database tools"
- Submit on Enter or click search button
- Disabled during active search

#### `StatusFeed.jsx`
- Horizontal step indicator showing pipeline stages: Plan → Search → Scrape → Extract → Fill Gaps → Done
- Current stage is highlighted/animated (pulse or spinner)
- Shows the current status message below the step indicator
- Progress bar for stages that have quantifiable progress (e.g., "Scraping 14/20 pages")

#### `ResultsTable.jsx`
- Renders entities as rows, schema columns as headers
- Each cell shows the value + a small confidence dot (color-coded):
  - HIGH = green (#22c55e)
  - MEDIUM = amber (#f59e0b)
  - LOW = gray (#6b7280)
  - UNVERIFIED = dashed outline dot
- Clicking a cell opens the SourcePanel for that cell
- Columns are sortable (click header to sort)
- Empty cells show a faint dash "—"
- When `partial` results arrive via SSE, render them immediately with a "Still searching..." indicator
- When `result` (final) arrives, update the table with smooth transitions
- Export buttons: "Export JSON" and "Export CSV" in the top-right of the table

#### `SourcePanel.jsx`
- Slides in from the right (panel overlay, not a modal)
- Shows for the selected cell:
  - The value and confidence level
  - Each source: URL (clickable link), page title, quote snippet (highlighted)
  - If conflicts exist: "⚠️ Conflicting information" section showing alternative values with their sources
- Close on click outside or X button

#### `SchemaEditor.jsx`
- Accessible via an "Edit columns" button near the table header
- Shows current columns as editable chips/tags
- User can: remove a column (X button), add a new column (text input + add), reorder (drag or arrows)
- "Re-analyze" button that calls `/api/search/refine` with the modified schema
- This re-uses cached scraped data — only re-runs extraction, so it's fast

#### `CostDashboard.jsx`
- Small collapsible panel, bottom-right corner
- Shows: search API calls, pages scraped, LLM calls, total tokens, estimated cost ($), total time
- Collapsed by default, shows just "⏱ 12.3s | $0.04" — expands on click

#### `QuerySuggestions.jsx`
- After final results, show 3-4 suggested follow-up queries as clickable chips below the table
- Clicking one starts a new search with that query

### 6.3 SSE Client (`api.js`)

```javascript
export function streamSearch(query, { onStatus, onSchema, onPartial, onResult, onError }) {
  const url = `${API_BASE}/api/search?q=${encodeURIComponent(query)}`;
  const eventSource = new EventSource(url);
  
  eventSource.addEventListener('status', (e) => onStatus(JSON.parse(e.data)));
  eventSource.addEventListener('schema', (e) => onSchema(JSON.parse(e.data)));
  eventSource.addEventListener('partial', (e) => onPartial(JSON.parse(e.data)));
  eventSource.addEventListener('result', (e) => {
    onResult(JSON.parse(e.data));
    eventSource.close();
  });
  eventSource.addEventListener('error', (e) => {
    onError(JSON.parse(e.data));
    eventSource.close();
  });
  
  return () => eventSource.close();  // cleanup function
}
```

### 6.4 State Management (`hooks/useSearch.js`)

Use React `useReducer` for state:

```javascript
const initialState = {
  status: 'idle',        // idle | searching | done | error
  query: '',
  schema: null,
  entities: [],
  partialEntities: [],
  suggestedFollowups: [],
  cost: null,
  pipelineStatus: null,  // current stage info
  selectedCell: null,     // { entityIndex, columnName } for source panel
  error: null,
};
```

---

## 7. Proactive Query Suggestions

After the pipeline completes, make one more LLM call to generate follow-up suggestions.

**Prompt**:
```
The user searched for: "{original_query}"
We found these entities: {entity_names_list}

Suggest 3-4 related follow-up queries the user might want to explore next.
These should be:
- Related but different enough to surface new entities
- Specific and actionable (not vague)
- Cover different angles (competitors, deeper dive, adjacent category)

Respond as a JSON array of strings, no markdown:
["query 1", "query 2", "query 3"]
```

---

## 8. Evaluation Harness (`eval/benchmark.py`)

Create a script that runs the pipeline (non-streaming, just final output) against test queries and reports quality metrics.

**Test queries** (`eval/test_queries.json`):
```json
[
  {"query": "AI startups in healthcare", "expected_entity_type": "company"},
  {"query": "top pizza places in Brooklyn", "expected_entity_type": "restaurant"},
  {"query": "open source database tools", "expected_entity_type": "software"},
  {"query": "best universities for computer science", "expected_entity_type": "university"},
  {"query": "electric vehicle companies", "expected_entity_type": "company"},
  {"query": "popular JavaScript frameworks 2025", "expected_entity_type": "framework"},
  {"query": "coworking spaces in San Francisco", "expected_entity_type": "coworking space"},
  {"query": "top venture capital firms", "expected_entity_type": "firm"}
]
```

**Metrics to report per query**:
- Number of entities found
- Average column fill rate (% of non-empty cells)
- Average confidence distribution (% high/medium/low)
- Number of gap-fill searches triggered
- Total cost and latency
- Any extraction errors

**Output**: A markdown table summarizing results across all queries. Save to `eval_results/benchmark_report.md`.

---

## 9. Docker Setup

### `backend/Dockerfile`
```dockerfile
FROM python:3.11-slim

# Install playwright dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 \
    libxkbcommon0 libgbm1 libpango-1.0-0 libcairo2 \
    libasound2 libxshmfence1 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `frontend/Dockerfile`
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### `docker-compose.yml`
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - cache_data:/app/data
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  cache_data:
```

---

## 10. README Structure

Write a polished README.md with these exact sections:

### 1. Hero Section
- Project name + one-line description
- Screenshot/GIF of the UI showing a completed search (add a placeholder note: "TODO: Add demo GIF after first working version")
- Quick start: `docker-compose up` one-liner

### 2. How It Works
- Pipeline diagram (use a mermaid code block or ASCII art)
- Brief description of each stage

### 3. Key Features (Beyond the Basics)
List these with short descriptions:
- Automatic schema inference
- Multi-hop gap filling
- Per-cell source attribution with quote snippets
- Conflict detection
- Confidence scoring
- Streaming results
- Smart scraping with JS fallback
- Caching layer
- Cost transparency dashboard
- Proactive follow-up suggestions

### 4. Architecture & Design Decisions
For each major decision, explain the WHY:
- Why two-pass extraction (single-pass produces duplicates and misses cross-page entities)
- Why fuzzy entity resolution (same entity appears differently across sources)
- Why per-cell confidence (not all data is equally trustworthy)
- Why gap-filling agent loop (first pass rarely gets 100% coverage)
- Why SQLite cache (portable, zero-config, fast enough for this scale)
- Why Brave Search (reliable free tier, clean API, no scraping TOS issues)

### 5. Known Limitations
Be honest:
- JS-heavy SPAs may not scrape well even with Playwright
- Free-tier rate limits (Brave: 2k queries/month, ~1 req/sec)
- Entity resolution uses fuzzy string matching which can fail for ambiguous or very short names
- LLM extraction is not deterministic — results may vary slightly between runs
- No real-time data (results are as fresh as the search index)
- Gap filling adds latency and cost; capped at 10 follow-up searches

### 6. Cost & Latency Analysis
Include actual numbers from benchmark runs (fill in after implementation):
- Average query latency: ~X seconds
- Average cost per query: ~$X.XX
- Token usage breakdown: planning vs extraction vs gap-filling

### 7. Setup Instructions
- Prerequisites: Docker, API keys
- Step-by-step: clone, create .env, docker-compose up
- Alternative: manual setup without Docker (pip install, npm install, etc.)
- How to run the evaluation benchmark

### 8. Example Outputs
Include 2-3 example tables (as markdown tables or screenshots) for the test queries. Check in the raw JSON to `eval_results/`.

---

## 11. Implementation Order for Claude Code

**Implement in this exact order. Each step should be a working checkpoint.**

### Step 1: Project scaffolding
- Create the full directory structure
- Create `requirements.txt` with all dependencies:
  ```
  fastapi==0.115.0
  uvicorn[standard]==0.30.0
  sse-starlette==2.1.0
  httpx==0.27.0
  anthropic==0.40.0
  trafilatura==1.12.0
  playwright==1.48.0
  aiosqlite==0.20.0
  thefuzz[speedup]==0.22.1
  pydantic==2.9.0
  python-dotenv==1.0.1
  ```
- Create `config.py` loading env vars
- Create all Pydantic models in `models/schema.py`
- Create all prompt templates in `prompts/templates.py`
- Create `.env.example`

### Step 2: Core pipeline (backend, no frontend)
- Implement `planner.py` with schema inference
- Implement `searcher.py` with Brave Search
- Implement `scraper.py` with httpx + trafilatura (skip playwright for now)
- Implement `chunker.py`
- Implement `extractor.py` (both passes)
- Implement `confidence.py`
- Implement `dedup.py`
- Implement basic `pipeline.py` (no SSE yet, just returns final result)
- Add a simple test route: `GET /api/search/sync?q=...` that returns JSON
- **Test manually with curl**: `curl "http://localhost:8000/api/search/sync?q=AI+startups+in+healthcare"`

### Step 3: SSE streaming
- Convert pipeline to async generator yielding SSE events
- Implement the SSE `/api/search` endpoint
- Test with curl: `curl -N "http://localhost:8000/api/search?q=AI+startups+in+healthcare"`

### Step 4: Gap filler
- Implement `gap_filler.py`
- Integrate into pipeline (after initial extraction, before final result)
- Mark gap-filled cells as UNVERIFIED confidence

### Step 5: Cache layer
- Implement `cache.py` with SQLite
- Integrate into scraper (check cache before fetching)
- Integrate into searcher (cache search results)

### Step 6: Frontend
- Set up React + Vite + Tailwind project
- Build `SearchBar.jsx` (the landing page state + pinned state)
- Build `useSearch.js` hook with SSE connection
- Build `StatusFeed.jsx` (pipeline progress)
- Build `ResultsTable.jsx` (the main table with confidence dots)
- Build `SourcePanel.jsx` (slide-in panel)
- Build `SchemaEditor.jsx`
- Build `CostDashboard.jsx`
- Build `QuerySuggestions.jsx`
- Wire everything together in `App.jsx`

### Step 7: Playwright fallback
- Add playwright to scraper as fallback for thin content
- Test with a known JS-heavy site

### Step 8: Schema refinement endpoint
- Implement `/api/search/refine` POST endpoint
- Connect to SchemaEditor in frontend

### Step 9: Polish & documentation
- Write the full README.md per the structure above
- Create Docker files and docker-compose.yml
- Test full docker-compose flow

### Step 10: Evaluation
- Implement `eval/benchmark.py`
- Run against all test queries
- Save results to `eval_results/`
- Update README with actual cost/latency numbers

---

## 12. Critical Quality Notes

### What will differentiate this submission:

1. **Agentic behavior**: The system makes autonomous decisions (schema inference, query expansion, gap filling). Most candidates will build a linear pipeline. This is a loop.

2. **Source attribution at cell level**: Every single cell value traces back to a URL + quote. This directly mirrors Chris Samarinas's research on nugget-based evaluation — he will notice and appreciate this.

3. **Conflict transparency**: When sources disagree, showing both values (rather than silently picking one) demonstrates intellectual honesty about retrieval uncertainty.

4. **Cost awareness**: The cost dashboard shows this was built with production constraints in mind, not just as a demo.

5. **Documentation quality**: The README should read like a technical blog post, not just setup instructions.

### Common pitfalls to avoid:

- Do NOT hardcode schemas or column names for specific query types
- Do NOT ignore error handling — every external call (search API, scraper, LLM) can fail
- Do NOT make synchronous blocking calls — everything I/O-bound should be async
- Do NOT skip source attribution — it's the single most important quality signal for this evaluator
- Do NOT leave the frontend unstyled — visual polish matters in a demo
- Do NOT forget to handle the case where the LLM returns malformed JSON — always have fallback parsing
