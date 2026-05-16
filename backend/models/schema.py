"""Pydantic data models — the contract between every component in the pipeline."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    HIGH = "high"          # 2+ independent sources agree
    MEDIUM = "medium"      # 1 source, specific value
    LOW = "low"            # 1 source, vague value
    UNVERIFIED = "unverified"  # inferred or gap-filled


class SourceReference(BaseModel):
    url: str
    page_title: str
    quote_snippet: str
    scraped_at: str


class CellValue(BaseModel):
    value: str
    confidence: Confidence
    sources: list[SourceReference] = Field(default_factory=list)
    conflicts: list[str] | None = None


class EntityRow(BaseModel):
    entity_name: str
    cells: dict[str, CellValue] = Field(default_factory=dict)
    overall_confidence: Confidence = Confidence.LOW


class InferredSchema(BaseModel):
    entity_type: str
    columns: list[str]
    column_descriptions: dict[str, str] = Field(default_factory=dict)


class SearchPlan(BaseModel):
    original_query: str
    expanded_queries: list[str]
    schema: InferredSchema


class PipelineStatus(BaseModel):
    stage: str
    message: str
    progress: float | None = None


class PipelineCost(BaseModel):
    total_search_api_calls: int = 0
    total_pages_scraped: int = 0
    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    wall_clock_seconds: float = 0.0


class SearchResult(BaseModel):
    query: str
    schema: InferredSchema
    entities: list[EntityRow]
    suggested_followups: list[str] = Field(default_factory=list)
    cost: PipelineCost


# Internal pipeline types
class SearchHit(BaseModel):
    url: str
    title: str
    snippet: str
    query: str


class ScrapedPage(BaseModel):
    url: str
    title: str
    content: str
    scraped_at: str
    method: str
    content_length: int


class TextChunk(BaseModel):
    text: str
    source_url: str
    page_title: str
    chunk_index: int
    scraped_at: str


class RawExtraction(BaseModel):
    entity_name: str
    attributes: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    source_url: str
    page_title: str
    chunk_index: int
    scraped_at: str


class RefineRequest(BaseModel):
    query: str
    columns: list[str]
    column_descriptions: dict[str, str] | None = None
    entity_type: str | None = None
