"""Schemas for timeline events."""

from datetime import datetime

from pydantic import BaseModel


class TimelineEventResponse(BaseModel):
    event_id: str
    case_id: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    event_type: str
    event_subtype: str | None = None
    timestamp_utc: datetime | str
    timestamp_orig: str | None = None
    timezone_orig: str | None = None
    actor_entity_id: str | None = None
    actor_name: str | None = None
    target_entity_id: str | None = None
    target_name: str | None = None
    summary: str
    raw_data: str | None = None
    confidence: float = 1.0


class TimelineQueryParams(BaseModel):
    start: str | None = None
    end: str | None = None
    event_types: list[str] | None = None
    entity_ids: list[str] | None = None
    page: int = 1
    page_size: int = 100


class TimelineStats(BaseModel):
    total_events: int = 0
    date_range_start: str | None = None
    date_range_end: str | None = None
    by_type: dict[str, int] = {}
    by_day: list[dict] = []
