"""Pydantic schemas for the forensic alerts and watchlist module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ForensicAlertResponse(BaseModel):
    id: str
    case_id: str | None = None
    alert_type: str
    severity: str
    title: str
    description: str | None = None
    evidence_file_id: str | None = None
    entity_id: str | None = None
    auto_generated: bool = True
    rule_name: str | None = None
    dismissed: bool = False
    dismissed_at: datetime | None = None
    dismiss_reason: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AlertDismissRequest(BaseModel):
    dismiss_reason: str | None = None


class AlertStatsResponse(BaseModel):
    total: int = 0
    unreviewed: int = 0
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}


class WatchlistEntryResponse(BaseModel):
    id: str
    case_id: str | None = None
    term: str
    is_regex: bool = False
    category: str | None = None
    severity: str = "high"
    notes: str | None = None
    active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class WatchlistEntryCreate(BaseModel):
    case_id: str | None = None
    term: str
    is_regex: bool = False
    category: str | None = None
    severity: str = "high"
    notes: str | None = None
