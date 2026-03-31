"""API routes for evidence management."""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.db.models import ChainOfCustody, EvidenceSource
from rubberduck.db.models import File as FileModel
from rubberduck.db.sqlite import get_db
from rubberduck.evidence.service import IngestService
from rubberduck.jobs.manager import job_manager
from rubberduck.schemas.evidence import (
    CaseCreate,
    CaseResponse,
    CaseUpdate,
    CustodyEntryResponse,
    EvidenceSourceCreate,
    EvidenceSourceResponse,
    EvidenceStats,
    FileDetailResponse,
    FileResponse as FileResp,
    IngestDirectoryRequest,
    IngestResponse,
)

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


# ── Sources ────────────────────────────────────────────────


@router.post("/sources", response_model=EvidenceSourceResponse)
def create_source(body: EvidenceSourceCreate, db: Session = Depends(get_db)):
    source = EvidenceSource(
        case_id=body.case_id,
        label=body.label,
        source_type=body.source_type,
        received_from=body.received_from,
        notes=body.notes,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/sources")
def list_sources(case_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(EvidenceSource)
    if case_id:
        query = query.filter(EvidenceSource.case_id == case_id)
    sources = query.order_by(EvidenceSource.created_at.desc()).all()
    return [
        {
            **{c.name: getattr(s, c.name) for c in EvidenceSource.__table__.columns},
            "file_count": db.query(FileModel).filter(FileModel.source_id == s.id).count(),
        }
        for s in sources
    ]


class SourceIngestRequest(BaseModel):
    """Create a source and immediately start directory ingestion."""
    case_id: str
    label: str
    source_type: str = "upload"
    received_from: str | None = None
    notes: str | None = None
    path: str  # directory to ingest


@router.post("/sources/ingest", response_model=IngestResponse)
def create_source_and_ingest(body: SourceIngestRequest, db: Session = Depends(get_db)):
    """Create a new evidence source AND start directory ingestion in one call.

    This is a convenience endpoint for setting up separate sources for different
    data types (e.g., "court records" vs "personal Gmail data") and immediately
    ingesting the associated directory.
    """
    from rubberduck.config import settings

    # Validate the path
    resolved = Path(body.path).resolve()
    allowed_bases = (
        [Path(p).resolve() for p in settings.allowed_ingest_paths]
        if settings.allowed_ingest_paths
        else [settings.data_dir.resolve()]
    )
    if not any(resolved == base or resolved.is_relative_to(base) for base in allowed_bases):
        raise HTTPException(
            status_code=403,
            detail="Directory is outside allowed ingest paths",
        )
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    # Create the source
    source = EvidenceSource(
        case_id=body.case_id,
        label=body.label,
        source_type=body.source_type,
        received_from=body.received_from,
        notes=body.notes,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    # Start ingestion
    job_id = job_manager.submit(
        db,
        "ingest",
        IngestService.ingest_directory,
        params={"source_id": source.id, "path": str(resolved)},
        source_id=source.id,
        dir_path=str(resolved),
    )
    return IngestResponse(
        job_id=job_id,
        message=f"Created source '{body.label}' ({source.id}) and started ingesting: {resolved}",
    )


# ── Ingestion ──────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResponse)
def ingest_upload(
    source_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and ingest a file."""
    # Save upload to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}")
    shutil.copyfileobj(file.file, tmp)
    tmp.close()
    tmp_path = Path(tmp.name)

    job_id = job_manager.submit(
        db,
        "ingest",
        IngestService.ingest_upload,
        params={"source_id": source_id, "filename": file.filename},
        source_id=source_id,
        file_path=tmp_path,
        original_name=file.filename,
    )
    return IngestResponse(job_id=job_id, message=f"Ingesting {file.filename}")


@router.post("/ingest/directory", response_model=IngestResponse)
def ingest_directory(body: IngestDirectoryRequest, db: Session = Depends(get_db)):
    """Ingest all files from a local directory."""
    from rubberduck.config import settings

    # Validate the path is within allowed directories to prevent path traversal
    resolved = Path(body.path).resolve()
    allowed_bases = [Path(p).resolve() for p in settings.allowed_ingest_paths] if settings.allowed_ingest_paths else [settings.data_dir.resolve()]
    if not any(resolved == base or resolved.is_relative_to(base) for base in allowed_bases):
        raise HTTPException(
            status_code=403,
            detail="Directory is outside allowed ingest paths",
        )
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    job_id = job_manager.submit(
        db,
        "ingest",
        IngestService.ingest_directory,
        params={"source_id": body.source_id, "path": str(resolved)},
        source_id=body.source_id,
        dir_path=str(resolved),
    )
    return IngestResponse(job_id=job_id, message=f"Ingesting directory: {resolved}")


# ── Files ──────────────────────────────────────────────────


@router.get("/files")
def list_files(
    source_id: str | None = None,
    file_ext: str | None = None,
    parse_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(FileModel)
    if source_id:
        query = query.filter(FileModel.source_id == source_id)
    if file_ext:
        query = query.filter(FileModel.file_ext == file_ext)
    if parse_status:
        query = query.filter(FileModel.parse_status == parse_status)

    total = query.count()
    files = query.order_by(FileModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_file_dict(f) for f in files],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/files/{file_id}")
def get_file(file_id: str, db: Session = Depends(get_db)):
    f = db.query(FileModel).get(file_id)
    if not f:
        return {"error": "File not found"}, 404

    custody = (
        db.query(ChainOfCustody)
        .filter(ChainOfCustody.file_id == file_id)
        .order_by(ChainOfCustody.timestamp)
        .all()
    )
    return {
        **_file_dict(f),
        "custody_chain": [
            {"id": c.id, "action": c.action, "actor": c.actor, "timestamp": str(c.timestamp), "details": c.details}
            for c in custody
        ],
    }


@router.get("/files/{file_id}/content")
def get_file_content(file_id: str, db: Session = Depends(get_db)):
    f = db.query(FileModel).get(file_id)
    if not f or not f.parsed_path:
        return {"error": "Parsed content not available"}, 404

    content_path = Path(f.parsed_path) / "content.txt"
    if content_path.exists():
        return {"content": content_path.read_text(encoding="utf-8"), "file_id": file_id}
    return {"content": "", "file_id": file_id}


@router.get("/files/{file_id}/original")
def get_file_original(file_id: str, db: Session = Depends(get_db)):
    f = db.query(FileModel).get(file_id)
    if not f or not f.stored_path:
        return {"error": "Original not available"}, 404

    stored = Path(f.stored_path)
    if stored.exists():
        return FileResponse(stored, filename=f.file_name, media_type=f.mime_type)
    return {"error": "File not found on disk"}, 404


@router.get("/files/{file_id}/custody")
def get_custody_chain(file_id: str, db: Session = Depends(get_db)):
    entries = (
        db.query(ChainOfCustody)
        .filter(ChainOfCustody.file_id == file_id)
        .order_by(ChainOfCustody.timestamp)
        .all()
    )
    return [
        {"id": e.id, "action": e.action, "actor": e.actor, "timestamp": str(e.timestamp), "details": e.details}
        for e in entries
    ]


# ── Stats ──────────────────────────────────────────────────


@router.get("/stats", response_model=EvidenceStats)
def get_stats(db: Session = Depends(get_db)):
    total = db.query(FileModel).count()
    total_size = db.query(func.sum(FileModel.file_size_bytes)).scalar() or 0

    status_counts = dict(
        db.query(FileModel.parse_status, func.count())
        .group_by(FileModel.parse_status)
        .all()
    )
    type_counts = dict(
        db.query(FileModel.file_ext, func.count())
        .filter(FileModel.file_ext.isnot(None))
        .group_by(FileModel.file_ext)
        .all()
    )
    source_count = db.query(EvidenceSource).count()
    dup_count = db.query(FileModel).filter(FileModel.is_duplicate.is_(True)).count()

    return EvidenceStats(
        total_files=total,
        total_size_bytes=total_size,
        by_status=status_counts,
        by_type=type_counts,
        sources_count=source_count,
        duplicate_count=dup_count,
    )


def _file_dict(f: FileModel) -> dict:
    return {
        "id": f.id,
        "source_id": f.source_id,
        "original_path": f.original_path,
        "file_name": f.file_name,
        "file_ext": f.file_ext,
        "mime_type": f.mime_type,
        "file_size_bytes": f.file_size_bytes,
        "sha256": f.sha256,
        "md5": f.md5,
        "is_archive": f.is_archive,
        "is_duplicate": f.is_duplicate,
        "parse_status": f.parse_status,
        "parse_error": f.parse_error,
        "parser_used": f.parser_used,
        "created_at": str(f.created_at) if f.created_at else None,
        "parsed_at": str(f.parsed_at) if f.parsed_at else None,
    }
