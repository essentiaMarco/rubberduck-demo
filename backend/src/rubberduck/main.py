"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rubberduck.config import settings
from rubberduck.db.models import Base
from rubberduck.db.sqlite import engine
from rubberduck.jobs.manager import job_manager

logger = logging.getLogger(__name__)


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

    # Create FTS5 table
    from rubberduck.search.indexer import ensure_fts_table
    from rubberduck.db.sqlite import SessionLocal
    db = SessionLocal()
    try:
        ensure_fts_table(db)
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


# ── Health check ──────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
