"""API routes for report generation."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from rubberduck.db.sqlite import get_db
from rubberduck.jobs.manager import job_manager
from rubberduck.reports.generator import REPORT_TYPES, REPORTS_DIR

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/templates")
def list_report_templates():
    """List available report types."""
    return [
        {"id": key, "name": info["name"], "description": info["description"]}
        for key, info in REPORT_TYPES.items()
    ]


@router.get("")
def list_reports():
    """List previously generated reports."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(REPORTS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "items": [
            {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "created_at": f.stat().st_mtime,
                "format": f.suffix.lstrip("."),
            }
            for f in files[:50]
        ],
        "total": len(files),
    }


@router.post("/generate")
def generate_report(
    report_type: str = Query("investigation_summary", description="Report type ID"),
    case_id: str | None = Query(None, description="Case ID (optional)"),
    db: Session = Depends(get_db),
):
    """Generate a report as a background job. Returns job_id."""
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    def _generate_job(thread_db: Session, job_id: str) -> dict:
        gen_fn = REPORT_TYPES[report_type]["generator"]
        if "case_id" in gen_fn.__code__.co_varnames:
            path = gen_fn(thread_db, case_id=case_id)
        else:
            path = gen_fn(thread_db)
        return {"filename": path.name, "path": str(path), "format": path.suffix.lstrip(".")}

    jid = job_manager.submit(db, "report_generation", _generate_job, params={"report_type": report_type})
    return {"job_id": jid, "message": f"Generating {REPORT_TYPES[report_type]['name']} report..."}


@router.get("/download/{filename}")
def download_report(filename: str):
    """Download a generated report file."""
    path = REPORTS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    # Prevent path traversal
    if not path.resolve().is_relative_to(REPORTS_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")

    media_type = "application/pdf" if path.suffix == ".pdf" else "text/html"
    return FileResponse(str(path), filename=filename, media_type=media_type)
