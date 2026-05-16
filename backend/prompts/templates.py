"""Centralised LLM prompt templates."""
from __future__ import annotations


PLANNER_PROMPT = """You are a search planning agent. Given a user's topic query, you must:

1. Identify the TYPE of entity they're looking for (company, restaurant, tool, person, etc.)
2. Infer 6-10 relevant COLUMNS that would make a useful comparison table for these entities.
   - Always include "name" as the first column.
   - Choose columns that are: specific to this entity type, factual/verifiable, useful for comparison.
   - Include a mix of: identifiers (name, website), categorical (type, category), quantitative (price, rating, funding), descriptive (short description).
3. Generate 4-6 DIVERSE search queries that will surface different relevant results.
   - Vary the phrasing and angle (lists, comparisons, reviews, news).
   - Include at least one query targeting recent results (use the current year).
   - Include at least one query targeting a curated list or ranking.

User query: "{query}"

Respond in this exact JSON format (no markdown, no backticks):
{{
  "entity_type": "...",
  "columns": ["name", ...],
  "column_descriptions": {{"name": "...", ...}},
  "expanded_queries": ["...", "...", ...]
}}
"""


EXTRACTION_PROMPT = """You are a precise information extraction agent. Extract structured entity data from the text below.

Entity type: {entity_type}
Columns to extract (with descriptions):
{columns_with_descriptions}

Text (from {url}):
---
{chunk_text}
---

Instructions:
- Extract ALL entities of type "{entity_type}" mentioned in this text.
- For each entity, extract values for as many columns as the text supports. Leave columns empty ("") if no information is found — do NOT fabricate.
- For each extracted value, provide the exact quote snippet (max 150 chars) from the text that supports it.
- Be precise: extract specific values (e.g., "$4.2M Series A in 2023") not vague summaries ("well-funded").
- Do not include "the company" or pronouns as entity_name — extract proper names only.

Respond in this exact JSON format (no markdown, no backticks):
[
  {{
    "entity_name": "...",
    "attributes": {{"column1": "value1", "column2": "value2"}},
    "evidence": {{"column1": "supporting quote", "column2": "supporting quote"}}
  }}
]

If no relevant entities are found, respond with: []
"""


GAP_FILL_PROMPT = """Extract the {column_name} of "{entity_name}" from this text.

Column description: {column_description}

Text (from {url}):
---
{chunk_text}
---

If the text contains the {column_name} for "{entity_name}", respond with JSON:
{{"value": "...", "evidence": "exact quote (max 150 chars) supporting this"}}

If the text does not contain this information, respond with:
{{"value": "", "evidence": ""}}

Respond with JSON only, no markdown.
"""


FOLLOWUP_PROMPT = """The user searched for: "{query}"

We found these entities of type "{entity_type}":
{entity_names}

Suggest 3-4 related follow-up queries the user might want to explore next.
These should be:
- Related but different enough to surface NEW entities
- Specific and actionable (not vague)
- Cover different angles (competitors, deeper dive, adjacent category, recent news)

Respond as a JSON array of strings, no markdown:
["query 1", "query 2", "query 3"]
"""


DEFAULT_FALLBACK_SCHEMA_COLUMNS = [
    "name",
    "description",
    "website",
    "category",
    "notable_features",
]
DEFAULT_FALLBACK_COLUMN_DESCRIPTIONS = {
    "name": "Proper name of the entity",
    "description": "Short description of what this entity is or does",
    "website": "Official website URL",
    "category": "Type or category this entity belongs to",
    "notable_features": "Distinguishing features or attributes",
}
