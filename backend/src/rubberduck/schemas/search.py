"""Schemas for full-text search."""

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    file_types: list[str] | None = None
    source_ids: list[str] | None = None
    entity_ids: list[str] | None = None
    date_start: str | None = None
    date_end: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class SearchResult(BaseModel):
    file_id: str
    file_name: str
    file_ext: str | None
    source_label: str | None = None
    score: float
    snippet: str
    mime_type: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str
    page: int
    page_size: int


class SearchSuggestion(BaseModel):
    term: str
    count: int
