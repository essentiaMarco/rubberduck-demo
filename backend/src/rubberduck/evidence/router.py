"""API routes for evidence management."""

import shutil
import tempfile
from pathlib import Path

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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

    def _ingest_with_cleanup(thread_db, job_id, **kw):
        """Wrapper that cleans up the temp file regardless of success or failure."""
        try:
            return IngestService.ingest_upload(thread_db, job_id, **kw)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass  # best-effort cleanup

    job_id = job_manager.submit(
        db,
        "ingest",
        _ingest_with_cleanup,
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
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
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
    if date_start:
        query = query.filter(FileModel.created_at >= date_start)
    if date_end:
        query = query.filter(FileModel.created_at <= date_end)

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
        raise HTTPException(status_code=404, detail="File not found")

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
def get_file_content(
    file_id: str,
    max_bytes: int = Query(500_000, ge=0, le=10_000_000, description="Max content bytes to return (0 = unlimited)"),
    offset: int = Query(0, ge=0, description="Byte offset to start reading from"),
    db: Session = Depends(get_db),
):
    f = db.query(FileModel).get(file_id)
    if not f or not f.parsed_path:
        raise HTTPException(status_code=404, detail="Parsed content not available")

    content_path = Path(f.parsed_path) / "content.txt"
    if not content_path.exists():
        return {"content": "", "file_id": file_id, "total_size": 0, "truncated": False}

    total_size = content_path.stat().st_size

    if max_bytes == 0:
        # Unlimited — read the whole file (use with caution on large files)
        content = content_path.read_text(encoding="utf-8", errors="replace")
        return {"content": content, "file_id": file_id, "total_size": total_size, "truncated": False}

    # Read a bounded chunk to avoid memory issues on large files (e.g. 7GB mbox)
    with open(content_path, "r", encoding="utf-8", errors="replace") as fh:
        if offset > 0:
            fh.seek(offset)
        content = fh.read(max_bytes)

    truncated = (offset + len(content.encode("utf-8"))) < total_size

    return {
        "content": content,
        "file_id": file_id,
        "total_size": total_size,
        "truncated": truncated,
        "offset": offset,
    }


@router.get("/files/{file_id}/content/search")
def search_file_content(
    file_id: str,
    q: str = Query(..., min_length=1, description="Search query to find within the file"),
    context_chars: int = Query(300, ge=50, le=2000, description="Characters of context around each match"),
    max_matches: int = Query(20, ge=1, le=100, description="Maximum matches to return"),
    db: Session = Depends(get_db),
):
    """Search within a specific file's content and return matching sections.

    Returns contextual snippets around each match with the search term
    highlighted in ``<mark>`` tags.  This is far more useful than sequential
    reading for large files like mbox archives (500 MB+).
    """
    f = db.query(FileModel).get(file_id)
    if not f or not f.parsed_path:
        raise HTTPException(status_code=404, detail="Parsed content not available")

    content_path = Path(f.parsed_path) / "content.txt"
    if not content_path.exists():
        return {"matches": [], "total_matches": 0, "query": q, "file_id": file_id}

    total_size = content_path.stat().st_size

    # For very large files, read in chunks and search
    matches = []
    pattern = re.compile(re.escape(q), re.IGNORECASE)

    # Read file in manageable chunks (2 MB) with overlap to catch matches at boundaries
    chunk_size = 2 * 1024 * 1024
    overlap = context_chars + len(q)
    file_offset = 0

    with open(content_path, "r", encoding="utf-8", errors="replace") as fh:
        carry = ""
        while len(matches) < max_matches:
            raw = fh.read(chunk_size)
            if not raw:
                # Search the remaining carry
                if carry:
                    for m in pattern.finditer(carry):
                        if len(matches) >= max_matches:
                            break
                        start = max(0, m.start() - context_chars)
                        end = min(len(carry), m.end() + context_chars)
                        snippet = carry[start:end]
                        highlighted = pattern.sub(
                            lambda x: f"<mark>{x.group()}</mark>", snippet
                        )
                        matches.append({
                            "snippet": highlighted,
                            "byte_offset": file_offset - len(carry) + m.start(),
                            "match_index": len(matches),
                        })
                break

            text_block = carry + raw
            # Keep the last `overlap` chars for the next iteration to handle boundary matches
            searchable = text_block[:-overlap] if len(text_block) > overlap else text_block
            carry = text_block[len(searchable):]

            for m in pattern.finditer(searchable):
                if len(matches) >= max_matches:
                    break
                start = max(0, m.start() - context_chars)
                end = min(len(searchable), m.end() + context_chars)
                snippet = searchable[start:end]
                highlighted = pattern.sub(
                    lambda x: f"<mark>{x.group()}</mark>", snippet
                )
                matches.append({
                    "snippet": highlighted,
                    "byte_offset": file_offset + m.start(),
                    "match_index": len(matches),
                })

            file_offset += len(searchable)

    # Count total matches (approximate for huge files — just use what we found)
    total_matches = len(matches)

    return {
        "matches": matches,
        "total_matches": total_matches,
        "query": q,
        "file_id": file_id,
        "total_size": total_size,
    }


@router.get("/files/{file_id}/original")
def get_file_original(file_id: str, db: Session = Depends(get_db)):
    f = db.query(FileModel).get(file_id)
    if not f or not f.stored_path:
        raise HTTPException(status_code=404, detail="Original not available")

    stored = Path(f.stored_path)
    if stored.exists():
        return FileResponse(stored, filename=f.file_name, media_type=f.mime_type)
    raise HTTPException(status_code=404, detail="File not found on disk")


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
