"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

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
    redirect_slashes=False,  # Prevent 307 redirects that break reverse proxy setups
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
from rubberduck.communications.router import router as communications_router
from rubberduck.phone_analysis.router import router as phone_analysis_router
from rubberduck.forensics.router import router as forensics_router
from rubberduck.financial.router import router as financial_router
from rubberduck.geo.router import router as geo_router

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
app.include_router(communications_router)
app.include_router(phone_analysis_router)
app.include_router(forensics_router)
app.include_router(financial_router)
app.include_router(geo_router)


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

ANALYSIS_STEPS = [
    {"key": "search_reindex", "label": "Building search index", "weight": 0.05},
    {"key": "entity_extraction", "label": "Extracting entities (NER)", "weight": 0.70},
    {"key": "relationship_extraction", "label": "Building relationship graph", "weight": 0.15},
    {"key": "timeline_rebuild", "label": "Rebuilding timeline", "weight": 0.10},
]


@app.post("/api/analysis/run")
def run_full_analysis(db: Session = Depends(get_db)):
    """Run all post-ingestion analysis: search index, entity extraction, timeline rebuild."""
    from rubberduck.db.models import File as FileModel, Job

    # Prevent duplicate: reject if a full_analysis job is already running
    already_running = (
        db.query(Job)
        .filter(Job.job_type == "full_analysis", Job.status == "running")
        .first()
    )
    if already_running:
        # Check if the thread is actually alive
        future = job_manager._futures.get(already_running.id)
        if future and not future.done():
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Analysis is already running (job {already_running.id})",
            )
        else:
            # Thread is dead but DB still says running — mark as failed
            already_running.status = "failed"
            already_running.error = "Background thread died unexpectedly"
            already_running.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.warning("Recovered zombie job %s", already_running.id)

    def _full_analysis_job(thread_db: Session, job_id: str) -> dict:
        import gc
        import os
        import signal
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        import psutil

        results = {"steps": [], "completed_steps": []}

        def _update(step_key: str, step_progress: float, processed: int = 0, total: int = 0):
            """Calculate overall progress from step weights and update."""
            step_info = next((s for s in ANALYSIS_STEPS if s["key"] == step_key), None)
            if not step_info:
                return
            step_idx = ANALYSIS_STEPS.index(step_info)
            # Overall = sum of completed step weights + current step partial
            base = sum(s["weight"] for s in ANALYSIS_STEPS[:step_idx])
            overall = base + step_info["weight"] * step_progress
            job_manager.update_progress(
                thread_db, job_id, overall, processed, total,
                current_step=step_info["label"],
            )

        # ── Step 1: Search reindex ────────────────────────────
        _update("search_reindex", 0.0)
        try:
            from rubberduck.search.indexer import bulk_reindex
            reindex_stats = bulk_reindex(thread_db)
            results["steps"].append({"step": "search_reindex", "status": "ok", "result": reindex_stats})
            results["completed_steps"].append("search_reindex")
        except Exception:
            logger.exception("Search reindex failed")
            results["steps"].append({"step": "search_reindex", "status": "failed"})
        _update("search_reindex", 1.0)

        # ── Step 2: Entity extraction ─────────────────────────
        _update("entity_extraction", 0.0)
        try:
            from rubberduck.db.models import EntityMention
            from rubberduck.entities.service import extract_and_resolve
            from rubberduck.entities.spacy_ner import reload_model as reload_spacy_model

            already_extracted = thread_db.query(EntityMention.file_id).distinct().subquery()
            MAX_FILE_SIZE = 50 * 1024 * 1024
            file_ids = [
                row[0]
                for row in thread_db.query(FileModel.id)
                .filter(
                    FileModel.parse_status == "completed",
                    FileModel.parsed_path.isnot(None),
                    ~FileModel.id.in_(already_extracted),
                    FileModel.file_size_bytes <= MAX_FILE_SIZE,
                )
                .all()
            ]
            total = len(file_ids)
            entity_stats = {"total": total, "succeeded": 0, "failed": 0, "timed_out": 0}

            MICRO_BATCH = 5
            MODEL_RELOAD = 25
            MEM_LIMIT_MB = 1024
            FILE_TIMEOUT = 60  # seconds per file

            process = psutil.Process(os.getpid())

            for i, fid in enumerate(file_ids):
                # Memory gate
                rss_mb = process.memory_info().rss / (1024 * 1024)
                if rss_mb > MEM_LIMIT_MB:
                    logger.warning("Memory %.0f MB > %d MB at file %d/%d — GC", rss_mb, MEM_LIMIT_MB, i + 1, total)
                    thread_db.flush()
                    thread_db.expire_all()
                    reload_spacy_model()
                    gc.collect()

                # Extract with per-file timeout
                try:
                    with ThreadPoolExecutor(max_workers=1) as mini:
                        future = mini.submit(extract_and_resolve, thread_db, fid)
                        future.result(timeout=FILE_TIMEOUT)
                    entity_stats["succeeded"] += 1
                except FuturesTimeout:
                    logger.warning("Entity extraction timed out for file %s (%d/%d)", fid, i + 1, total)
                    entity_stats["timed_out"] += 1
                except Exception:
                    logger.exception("Entity extraction failed for file %s (%d/%d)", fid, i + 1, total)
                    entity_stats["failed"] += 1

                # Micro-batch flush
                if (i + 1) % MICRO_BATCH == 0:
                    thread_db.flush()
                    thread_db.expire_all()
                    gc.collect()

                # Reload spaCy periodically
                if (i + 1) % MODEL_RELOAD == 0:
                    reload_spacy_model()
                    gc.collect()

                # Progress every 5 files
                if (i + 1) % 5 == 0 or i == total - 1:
                    _update("entity_extraction", (i + 1) / max(total, 1), i + 1, total)

            results["steps"].append({"step": "entity_extraction", "status": "ok", "result": entity_stats})
            results["completed_steps"].append("entity_extraction")
        except Exception:
            logger.exception("Entity extraction step failed entirely")
            results["steps"].append({"step": "entity_extraction", "status": "failed"})
        _update("entity_extraction", 1.0)
        gc.collect()

        # ── Step 3: Relationship extraction ───────────────────
        _update("relationship_extraction", 0.0)
        try:
            from rubberduck.graph.relationships import extract_cooccurrence_relationships
            rel_stats = extract_cooccurrence_relationships(thread_db)
            results["steps"].append({"step": "relationship_extraction", "status": "ok", "result": rel_stats})
            results["completed_steps"].append("relationship_extraction")
        except Exception:
            logger.exception("Relationship extraction failed")
            results["steps"].append({"step": "relationship_extraction", "status": "failed"})
        _update("relationship_extraction", 1.0)

        # ── Step 4: Timeline rebuild ──────────────────────────
        _update("timeline_rebuild", 0.0)
        try:
            from rubberduck.timeline.service import rebuild as timeline_rebuild
            timeline_stats = timeline_rebuild()
            results["steps"].append({"step": "timeline_rebuild", "status": "ok", "result": timeline_stats})
            results["completed_steps"].append("timeline_rebuild")
        except Exception:
            logger.exception("Timeline rebuild failed")
            results["steps"].append({"step": "timeline_rebuild", "status": "failed"})
        _update("timeline_rebuild", 1.0)

        return results

    job_id = job_manager.submit(db, "full_analysis", _full_analysis_job, params={})
    return {"job_id": job_id, "message": "Full analysis pipeline started"}


# ── Health check ──────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
