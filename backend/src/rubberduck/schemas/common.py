"""Shared schemas: pagination, error responses, base models."""

from datetime import datetime

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None


class TimestampMixin(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None
