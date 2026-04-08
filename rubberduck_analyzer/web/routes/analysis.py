"""Routes for triggering M1/M2/M3 analysis with metadata enrichment."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from rubberduck_analyzer.web.models import create_job
from rubberduck_analyzer.web.tasks import run_m1_analysis, run_m2_analysis, run_m3_analysis
from rubberduck_analyzer.web.metadata import enrich_upload, extract_from_filename

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

UPLOAD_DIR = Path("data/uploads")


async def _save_upload(file: UploadFile, job_id: str, name: str) -> str:
    """Save an uploaded file and return the path."""
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / name
    content = await file.read()
    dest.write_bytes(content)
    return str(dest)


# ---------------------------------------------------------------------------
# Preview endpoint — extract metadata before analysis
# ---------------------------------------------------------------------------

@router.post("/preview", response_class=HTMLResponse)
async def preview_metadata(
    request: Request,
    transcript: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    written: UploadFile | None = File(None),
):
    """Extract and display metadata from uploaded files before analysis."""
    preview_id = f"preview_{uuid.uuid4().hex[:6]}"

    transcript_path = None
    video_path = None
    written_path = None

    if transcript and transcript.filename:
        transcript_path = await _save_upload(transcript, preview_id, transcript.filename)
    if video and video.filename:
        video_path = await _save_upload(video, preview_id, video.filename)
    if written and written.filename:
        written_path = await _save_upload(written, preview_id, written.filename)

    meta = enrich_upload(
        transcript_path=transcript_path,
        video_path=video_path,
        written_path=written_path,
        transcript_filename=transcript.filename if transcript else None,
        video_filename=video.filename if video else None,
    )

    return templates.TemplateResponse(request, "_metadata_preview.html", {
        "meta": meta,
    })


@router.post("/preview/filename")
async def preview_filename(filename: str = Form("")):
    """Quick filename-only metadata extraction (no file upload needed)."""
    if not filename:
        return JSONResponse({"error": "no filename"})
    return JSONResponse(extract_from_filename(filename))


# ---------------------------------------------------------------------------
# Upload form
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    """Show the upload form for all milestone types."""
    return templates.TemplateResponse(request, "upload.html")


# ---------------------------------------------------------------------------
# M1 Analysis
# ---------------------------------------------------------------------------

@router.post("/m1")
async def analyze_m1(
    request: Request,
    background_tasks: BackgroundTasks,
    transcript: UploadFile = File(...),
    video: UploadFile | None = File(None),
    tester_name: str = Form(""),
    facilitator_is_first: bool = Form(True),
):
    """Submit an M1 analysis job with auto-enriched metadata."""
    job_id = f"m1_{uuid.uuid4().hex[:8]}"
    transcript_path = await _save_upload(transcript, job_id, transcript.filename or "transcript.txt")
    video_path = await _save_upload(video, job_id, video.filename or "video.mp4") if video and video.filename else None

    # Auto-enrich metadata from files
    meta = enrich_upload(
        transcript_path=transcript_path,
        video_path=video_path,
        transcript_filename=transcript.filename,
        video_filename=video.filename if video else None,
    )

    # Use extracted tester name if user didn't provide one
    effective_name = tester_name or meta.get("tester_name")

    create_job(job_id, "M1", tester_name=effective_name, metadata=meta)
    background_tasks.add_task(
        run_m1_analysis,
        job_id=job_id,
        transcript_path=transcript_path,
        video_path=video_path,
        tester_name=effective_name,
        facilitator_is_first=facilitator_is_first,
    )

    return templates.TemplateResponse(request, "_job_submitted.html", {
        "job_id": job_id,
        "milestone": "M1",
        "meta": meta,
    })


# ---------------------------------------------------------------------------
# M2 Analysis
# ---------------------------------------------------------------------------

@router.post("/m2")
async def analyze_m2(
    request: Request,
    background_tasks: BackgroundTasks,
    written: UploadFile = File(...),
    video: UploadFile | None = File(None),
    transcript: UploadFile | None = File(None),
    tester_name: str = Form(""),
):
    """Submit an M2 analysis job with auto-enriched metadata."""
    job_id = f"m2_{uuid.uuid4().hex[:8]}"
    written_path = await _save_upload(written, job_id, written.filename or "written.txt")
    video_path = await _save_upload(video, job_id, video.filename or "video.mp4") if video and video.filename else None
    transcript_path = await _save_upload(transcript, job_id, transcript.filename or "transcript.txt") if transcript and transcript.filename else None

    meta = enrich_upload(
        transcript_path=transcript_path,
        video_path=video_path,
        written_path=written_path,
        transcript_filename=transcript.filename if transcript else None,
        video_filename=video.filename if video else None,
    )

    effective_name = tester_name or meta.get("tester_name")

    create_job(job_id, "M2", tester_name=effective_name, metadata=meta)
    background_tasks.add_task(
        run_m2_analysis,
        job_id=job_id,
        written_path=written_path,
        video_path=video_path,
        transcript_path=transcript_path,
        tester_name=effective_name,
    )

    return templates.TemplateResponse(request, "_job_submitted.html", {
        "job_id": job_id,
        "milestone": "M2",
        "meta": meta,
    })


# ---------------------------------------------------------------------------
# M3 Analysis
# ---------------------------------------------------------------------------

@router.post("/m3")
async def analyze_m3(
    request: Request,
    background_tasks: BackgroundTasks,
    video_without: UploadFile = File(...),
    video_with: UploadFile = File(...),
    comparison: UploadFile = File(...),
    proposal: UploadFile = File(...),
    tester_name: str = Form(""),
):
    """Submit an M3 analysis job with auto-enriched metadata."""
    job_id = f"m3_{uuid.uuid4().hex[:8]}"
    vw_path = await _save_upload(video_without, job_id, video_without.filename or "video_without.mp4")
    vr_path = await _save_upload(video_with, job_id, video_with.filename or "video_with.mp4")
    comp_path = await _save_upload(comparison, job_id, comparison.filename or "comparison.txt")
    prop_path = await _save_upload(proposal, job_id, proposal.filename or "proposal.txt")

    meta = enrich_upload(
        video_path=vw_path,
        written_path=comp_path,
        video_filename=video_without.filename,
    )

    effective_name = tester_name or meta.get("tester_name")

    create_job(job_id, "M3", tester_name=effective_name, metadata=meta)
    background_tasks.add_task(
        run_m3_analysis,
        job_id=job_id,
        video_without_path=vw_path,
        video_with_path=vr_path,
        comparison_path=comp_path,
        proposal_path=prop_path,
        tester_name=effective_name,
    )

    return templates.TemplateResponse(request, "_job_submitted.html", {
        "job_id": job_id,
        "milestone": "M3",
        "meta": meta,
    })
