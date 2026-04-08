"""Routes for cross-tester synthesis and report viewing."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from rubberduck_analyzer.web.models import create_job
from rubberduck_analyzer.web.tasks import run_synthesis

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

SESSIONS_DIR = Path("data/sessions")
REPORTS_DIR = Path("data/reports")


@router.get("/", response_class=HTMLResponse)
async def synthesis_page(request: Request):
    """Show synthesis page with inline report and download links."""
    # Downloadable files (exclude .gitkeep and patterns.json)
    downloads = []
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.glob("*"), reverse=True):
            if f.name in (".gitkeep", "patterns.json"):
                continue
            downloads.append({"name": f.name, "size": f.stat().st_size})

    # Read the markdown report inline, convert to HTML
    report_html = None
    report_path = REPORTS_DIR / "engineering_report.md"
    if report_path.is_file():
        import markdown
        md_text = report_path.read_text(encoding="utf-8")
        report_html = markdown.markdown(md_text, extensions=["extra", "nl2br"])

    session_count = len(list(SESSIONS_DIR.glob("*.json"))) if SESSIONS_DIR.exists() else 0

    return templates.TemplateResponse(request, "synthesis.html", {
        "downloads": downloads,
        "report_html": report_html,
        "session_count": session_count,
    })


@router.post("/run")
async def run_synthesis_job(request: Request, background_tasks: BackgroundTasks):
    """Trigger a new cross-tester synthesis."""
    job_id = f"syn_{uuid.uuid4().hex[:8]}"
    create_job(job_id, "synthesis")
    background_tasks.add_task(
        run_synthesis,
        job_id=job_id,
        sessions_dir=str(SESSIONS_DIR),
        output_dir=str(REPORTS_DIR),
    )
    return templates.TemplateResponse(request, "_job_submitted.html", {
        "job_id": job_id,
        "milestone": "Synthesis",
    })


@router.get("/report/{filename}")
async def download_report(filename: str):
    """Download a generated report file."""
    path = REPORTS_DIR / filename
    if not path.exists():
        return HTMLResponse("<h1>Report not found</h1>", status_code=404)
    return FileResponse(str(path), filename=filename)


@router.delete("/report/{filename}")
async def delete_report(filename: str):
    """Delete a generated report file."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return HTMLResponse("Invalid filename", status_code=400)
    path = (REPORTS_DIR / filename).resolve()
    if not str(path).startswith(str(REPORTS_DIR.resolve())):
        return HTMLResponse("Invalid path", status_code=400)
    if not path.exists():
        return HTMLResponse("Report not found", status_code=404)
    path.unlink()
    return HTMLResponse(
        '<tr><td colspan="3" style="color: var(--success);">Report deleted.</td></tr>'
    )
