"""Pydantic schemas for the forensic secrets module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ForensicSecretResponse(BaseModel):
    id: str
    file_id: str
    entity_id: str | None = None
    secret_type: str
    secret_category: str
    severity: str
    masked_value: str | None = None
    context_snippet: str | None = None
    char_offset: int | None = None
    detection_method: str | None = None
    confidence: float = 0.9
    is_reviewed: bool = False
    review_notes: str | None = None
    dismissed: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SecretDetailResponse(ForensicSecretResponse):
    """Includes the unmasked value — use with caution."""
    detected_value: str


class SecretReviewRequest(BaseModel):
    is_reviewed: bool = True
    review_notes: str | None = None
    dismissed: bool = False


class SecretStatsResponse(BaseModel):
    total: int = 0
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_type: dict[str, int] = {}
    unreviewed: int = 0
    dismissed: int = 0
