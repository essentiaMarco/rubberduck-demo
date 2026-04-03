"""API routes for timeline queries and management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from rubberduck.db.duckdb_conn import get_duckdb
from rubberduck.jobs.manager import job_manager
from rubberduck.schemas.timeline import TimelineEventResponse, TimelineStats
from rubberduck.timeline import service as timeline_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


@router.get("/events", response_model=dict)
def list_events(
    start: str | None = Query(None, description="Start of date range (ISO 8601)"),
    end: str | None = Query(None, description="End of date range (ISO 8601)"),
    event_types: list[str] | None = Query(None, description="Filter by event types"),
    entity_ids: list[str] | None = Query(None, description="Filter by entity IDs"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
):
    """Query timeline events with optional filters and pagination."""
    return timeline_service.get_events(
        start=start,
        end=end,
        event_types=event_types,
        entity_ids=entity_ids,
        page=page,
        page_size=page_size,
    )


@router.get("/events/{event_id}", response_model=TimelineEventResponse)
def get_event(event_id: str):
    """Retrieve a single event by ID."""
    conn = get_duckdb()
    try:
        result = conn.execute(
            "SELECT * FROM events WHERE event_id = ? LIMIT 1", [event_id]
        )
        columns = [desc[0] for desc in result.description]
        row = result.fetchone()
    except Exception:
        raise HTTPException(status_code=500, detail="Error querying events")
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    return dict(zip(columns, row))


@router.get("/stats", response_model=TimelineStats)
def get_stats():
    """Return aggregate timeline statistics."""
    return timeline_service.get_stats()


@router.post("/rebuild")
def rebuild_timeline():
    """Trigger a full timeline rebuild from parsed evidence files.

    Runs as a background job and returns the job ID immediately.
    """
    from rubberduck.db.sqlite import SessionLocal

    db = SessionLocal()
    try:
        job_id = job_manager.submit(
            db,
            "timeline_rebuild",
            _rebuild_job,
            params={"action": "rebuild_timeline"},
        )
        return {"job_id": job_id, "message": "Timeline rebuild started"}
    finally:
        db.close()


def _rebuild_job(db, job_id: str) -> dict:
    """Background job wrapper for timeline rebuild."""
    return timeline_service.rebuild()
