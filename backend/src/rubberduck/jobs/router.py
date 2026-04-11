"""API routes for background jobs."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from rubberduck.db.models import Job
from rubberduck.db.sqlite import get_db
from rubberduck.jobs.manager import job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    status: str | None = None,
    job_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    if job_type:
        query = query.filter(Job.job_type == job_type)
    total = query.count()
    jobs = query.order_by(desc(Job.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_job_dict(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/stream")
async def job_stream():
    """SSE endpoint for real-time job updates."""
    queue = job_manager.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(asyncio.to_thread(queue.get), timeout=30.0)
                    yield {"event": "job_update", "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            job_manager.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    success = job_manager.cancel(db, job_id)
    return {"cancelled": success}


def _job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "total_items": job.total_items,
        "processed_items": job.processed_items,
        "current_step": job.current_step,
        "error": job.error,
        "created_at": str(job.created_at) if job.created_at else None,
        "started_at": str(job.started_at) if job.started_at else None,
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }
