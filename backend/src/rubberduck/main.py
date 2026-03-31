"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from rubberduck.config import settings
from rubberduck.db.models import Base
from rubberduck.db.sqlite import engine
from rubberduck.jobs.manager import job_manager

logger = logging.getLogger(__name__)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Require a bearer token on all API endpoints when configured."""

    EXEMPT_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        if not settings.api_token:
            return await call_next(request)
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {settings.api_token}":
            return await call_next(request)

        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.info("Starting Rubberduck...")

    # Create data directories
    settings.ensure_directories()

    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")

    # Create FTS5 table and recover stale jobs
    from rubberduck.search.indexer import ensure_fts_table
    from rubberduck.db.sqlite import SessionLocal
    db = SessionLocal()
    try:
        ensure_fts_table(db)
        job_manager.recover_stale_jobs(db)
    finally:
        db.close()

    logger.info("Rubberduck ready")
    yield

    # Shutdown
    job_manager.shutdown()
    logger.info("Rubberduck stopped")


app = FastAPI(
    title="Rubberduck",
    description="Local-first digital forensic investigative platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Bearer token authentication (must be added before CORS so it runs after CORS in the middleware stack)
app.add_middleware(BearerTokenMiddleware)

# CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────

from rubberduck.evidence.router import router as evidence_router
from rubberduck.search.router import router as search_router
from rubberduck.entities.router import router as entities_router
from rubberduck.timeline.router import router as timeline_router
from rubberduck.graph.router import router as graph_router
from rubberduck.hypothesis.router import router as hypothesis_router
from rubberduck.legal.router import router as legal_router
from rubberduck.osint.router import router as osint_router
from rubberduck.reports.router import router as reports_router
from rubberduck.jobs.router import router as jobs_router

app.include_router(evidence_router)
app.include_router(search_router)
app.include_router(entities_router)
app.include_router(timeline_router)
app.include_router(graph_router)
app.include_router(hypothesis_router)
app.include_router(legal_router)
app.include_router(osint_router)
app.include_router(reports_router)
app.include_router(jobs_router)


# ── Cases router (inline for simplicity) ──────────────────

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from rubberduck.db.sqlite import get_db
from rubberduck.db.models import Case
from rubberduck.schemas.evidence import CaseCreate, CaseUpdate, CaseResponse

cases_router = APIRouter(prefix="/api/cases", tags=["cases"])


@cases_router.post("", response_model=CaseResponse)
def create_case(body: CaseCreate, db: Session = Depends(get_db)):
    case = Case(**body.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@cases_router.get("")
def list_cases(db: Session = Depends(get_db)):
    return [CaseResponse.model_validate(c) for c in db.query(Case).order_by(Case.created_at.desc()).all()]


@cases_router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).get(case_id)
    if not case:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@cases_router.patch("/{case_id}", response_model=CaseResponse)
def update_case(case_id: str, body: CaseUpdate, db: Session = Depends(get_db)):
    case = db.query(Case).get(case_id)
    if not case:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Case not found")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(case, key, val)
    db.commit()
    db.refresh(case)
    return case


app.include_router(cases_router)


# ── Full analysis pipeline ────────────────────────────────

@app.post("/api/analysis/run")
def run_full_analysis(db: Session = Depends(get_db)):
    """Run all post-ingestion analysis: search index, entity extraction, timeline rebuild."""
    from rubberduck.db.models import File as FileModel, Job
    from rubberduck.entities.service import extract_and_resolve
    from rubberduck.search.indexer import bulk_reindex
    from rubberduck.timeline.service import rebuild as timeline_rebuild

    # Prevent duplicate: reject if a full_analysis job is already running
    already_running = (
        db.query(Job)
        .filter(Job.job_type == "full_analysis", Job.status == "running")
        .first()
    )
    if already_running:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=409,
            detail=f"Analysis is already running (job {already_running.id})",
        )

    def _full_analysis_job(thread_db: Session, job_id: str) -> dict:
        import gc

        results = {"steps": []}

        # Step 1: Search reindex
        job_manager.update_progress(thread_db, job_id, 0.0, 0, 3)
        reindex_stats = bulk_reindex(thread_db)
        results["steps"].append({"step": "search_reindex", "result": reindex_stats})
        job_manager.update_progress(thread_db, job_id, 0.33, 1, 3)

        # Step 2: Entity extraction — process in batches to manage memory
        # Only fetch IDs first, not full ORM objects
        file_ids = [
            row[0]
            for row in thread_db.query(FileModel.id)
            .filter(FileModel.parse_status == "completed", FileModel.parsed_path.isnot(None))
            .all()
        ]
        total = len(file_ids)
        entity_stats = {"total": total, "succeeded": 0, "failed": 0}
        BATCH_SIZE = 100
        for i, fid in enumerate(file_ids):
            try:
                extract_and_resolve(thread_db, fid)
                entity_stats["succeeded"] += 1
            except Exception:
                entity_stats["failed"] += 1
            if (i + 1) % 20 == 0:
                progress = 0.33 + (0.34 * (i + 1) / total)
                job_manager.update_progress(thread_db, job_id, progress, 1, 3)
            # Flush and expire ORM cache every batch to free memory
            if (i + 1) % BATCH_SIZE == 0:
                thread_db.flush()
                thread_db.expire_all()
                gc.collect()
        results["steps"].append({"step": "entity_extraction", "result": entity_stats})
        job_manager.update_progress(thread_db, job_id, 0.67, 2, 3)
        gc.collect()

        # Step 3: Timeline rebuild
        timeline_stats = timeline_rebuild()
        results["steps"].append({"step": "timeline_rebuild", "result": timeline_stats})
        job_manager.update_progress(thread_db, job_id, 1.0, 3, 3)

        return results

    job_id = job_manager.submit(db, "full_analysis", _full_analysis_job, params={})
    return {"job_id": job_id, "message": "Full analysis pipeline started (search index + entities + timeline)"}


# ── Health check ──────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
