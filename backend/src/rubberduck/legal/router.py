"""API routes for the legal drafting module."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from rubberduck.db.models import LegalDocument
from rubberduck.db.sqlite import get_db
from rubberduck.legal import service as legal_service
from rubberduck.legal.template_engine import list_templates
from rubberduck.schemas.legal import (
    GapAnalysis,
    GoogleOrderRequest,
    GoogleOrderResponse,
    LegalDocCreate,
    LegalDocDetailResponse,
    LegalDocResponse,
    LegalDocUpdate,
    TemplateInfo,
)

router = APIRouter(prefix="/api/legal", tags=["legal"])


# ── Templates ─────────────────────────────────────────────


@router.get("/templates", response_model=list[TemplateInfo])
def get_templates():
    """List all available legal document templates."""
    raw = list_templates()
    return [
        TemplateInfo(
            name=t["name"],
            doc_type=_infer_doc_type(t["name"]),
            description=f"Legal template: {t['name']}",
        )
        for t in raw
    ]


# ── Documents CRUD ────────────────────────────────────────


@router.post("/documents", response_model=LegalDocResponse)
def create_document(body: LegalDocCreate, db: Session = Depends(get_db)):
    """Create a new legal document, optionally rendering from a template."""
    doc = legal_service.create_document(
        db,
        case_id=body.case_id,
        doc_type=body.doc_type,
        title=body.title,
        template_name=body.template_name,
        provider=body.provider,
        parameters=body.parameters,
    )
    return doc


@router.get("/documents", response_model=list[LegalDocResponse])
def list_documents(
    case_id: str | None = None,
    doc_type: str | None = None,
    provider: str | None = None,
    db: Session = Depends(get_db),
):
    """List legal documents with optional filters."""
    query = db.query(LegalDocument)
    if case_id:
        query = query.filter(LegalDocument.case_id == case_id)
    if doc_type:
        query = query.filter(LegalDocument.doc_type == doc_type)
    if provider:
        query = query.filter(LegalDocument.provider == provider)
    docs = query.order_by(LegalDocument.updated_at.desc()).all()
    return docs


@router.get("/documents/{doc_id}", response_model=LegalDocDetailResponse)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    """Get a legal document with its rendered content."""
    doc = db.query(LegalDocument).get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Legal document not found")
    return doc


@router.patch("/documents/{doc_id}", response_model=LegalDocResponse)
def update_document(
    doc_id: str,
    body: LegalDocUpdate,
    db: Session = Depends(get_db),
):
    """Update editable fields on a legal document."""
    doc = db.query(LegalDocument).get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Legal document not found")

    update_data = body.model_dump(exclude_unset=True)

    # Handle parameters specially: serialize to JSON string
    if "parameters" in update_data and update_data["parameters"] is not None:
        update_data["parameters"] = json.dumps(update_data["parameters"])

    for key, value in update_data.items():
        setattr(doc, key, value)

    db.commit()
    db.refresh(doc)
    return doc


# ── Render ────────────────────────────────────────────────


@router.post("/documents/{doc_id}/render", response_model=LegalDocDetailResponse)
def render_document(doc_id: str, db: Session = Depends(get_db)):
    """Re-render a document from its template and current parameters."""
    try:
        doc = legal_service.render_document(db, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return doc


# ── Gap Analysis ──────────────────────────────────────────


@router.get("/gap-analysis/{case_id}", response_model=GapAnalysis)
def gap_analysis(case_id: str, db: Session = Depends(get_db)):
    """Run evidence gap analysis for a case."""
    return legal_service.get_gap_analysis(db, case_id)


# ── Google Order Builder ──────────────────────────────────


@router.post("/google-order", response_model=GoogleOrderResponse)
def build_google_order(body: GoogleOrderRequest, db: Session = Depends(get_db)):
    """Build Google supplemental order drafts."""
    return legal_service.build_google_order_from_request(db, body)


# ── Helpers ───────────────────────────────────────────────


def _infer_doc_type(template_name: str) -> str:
    """Best-effort doc_type from a template filename."""
    name_lower = template_name.lower()
    if "order" in name_lower:
        return "proposed_order"
    if "declaration" in name_lower:
        return "declaration"
    if "exhibit" in name_lower:
        return "exhibit_list"
    if "petition" in name_lower:
        return "petition"
    if "memo" in name_lower:
        return "memo"
    if "service" in name_lower:
        return "service_instructions"
    return "other"
