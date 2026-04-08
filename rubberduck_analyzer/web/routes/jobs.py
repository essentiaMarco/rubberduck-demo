"""Routes for polling job status (used by HTMX)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from fastapi.responses import JSONResponse

from rubberduck_analyzer.web.models import get_job, delete_job

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/{job_id}", response_class=HTMLResponse)
async def job_status(request: Request, job_id: str):
    """Return job status as an HTMX-swappable fragment."""
    job = get_job(job_id)
    if job is None:
        return HTMLResponse('<span class="status error">Job not found</span>', status_code=404)

    return templates.TemplateResponse(request, "_job_status.html", {
        "job": job,
    })


@router.delete("/{job_id}")
async def delete_job_endpoint(job_id: str):
    """Delete a job and its associated files."""
    result = delete_job(job_id)
    if result.get("error") == "not_found":
        return JSONResponse({"error": "Job not found"}, status_code=404)
    if result.get("error") == "job_still_active":
        return JSONResponse({"error": f"Cannot delete {result['status']} job"}, status_code=409)
    return JSONResponse(result)
