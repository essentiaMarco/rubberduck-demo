"""Legal document service — CRUD, rendering, gap analysis, and order building."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import LegalDocument
from rubberduck.legal.gap_analyzer import analyze_gaps
from rubberduck.legal.google_order_builder import build_google_order
from rubberduck.legal.template_engine import render_template
from rubberduck.schemas.legal import GoogleOrderRequest


# ── Create ────────────────────────────────────────────────


def create_document(
    db: Session,
    case_id: str,
    doc_type: str,
    title: str,
    template_name: str | None = None,
    provider: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> LegalDocument:
    """Create a new legal document, optionally rendering from a template.

    If *template_name* is provided the document is rendered immediately
    and stored in ``rendered_content``.
    """
    rendered_content: str | None = None
    if template_name:
        rendered_content = render_template(template_name, parameters)

    doc = LegalDocument(
        case_id=case_id,
        doc_type=doc_type,
        title=title,
        template_name=template_name,
        provider=provider,
        parameters=json.dumps(parameters) if parameters else None,
        rendered_content=rendered_content,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ── Render / re-render ────────────────────────────────────


def render_document(db: Session, doc_id: str) -> LegalDocument:
    """Re-render a document from its template and current parameters.

    Raises
    ------
    ValueError
        If the document has no template_name or cannot be found.
    """
    doc = db.query(LegalDocument).get(doc_id)
    if doc is None:
        raise ValueError(f"LegalDocument {doc_id!r} not found")
    if not doc.template_name:
        raise ValueError(f"Document {doc_id!r} has no template_name for re-rendering")

    params: dict[str, Any] = {}
    if doc.parameters:
        try:
            params = json.loads(doc.parameters) if isinstance(doc.parameters, str) else doc.parameters
        except (json.JSONDecodeError, TypeError):
            pass

    doc.rendered_content = render_template(doc.template_name, params)
    db.commit()
    db.refresh(doc)
    return doc


# ── Gap analysis ──────────────────────────────────────────


def get_gap_analysis(db: Session, case_id: str) -> dict[str, Any]:
    """Run evidence gap analysis for a case.

    Delegates to :func:`rubberduck.legal.gap_analyzer.analyze_gaps`.
    """
    return analyze_gaps(db, case_id)


# ── Google order builder ──────────────────────────────────


def build_google_order_from_request(
    db: Session,
    request: GoogleOrderRequest,
) -> dict[str, Any]:
    """Build Google supplemental order drafts from a request schema.

    The *db* parameter is accepted for interface consistency but is not
    currently used by the order builder itself.
    """
    # Convert Pydantic category models to plain dicts
    categories = [cat.model_dump() for cat in request.categories]

    result = build_google_order(
        case_id=request.case_id,
        accounts=request.accounts,
        categories=categories,
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
    )

    # Respect the request flags for which variants to include
    if not request.include_narrow_variant:
        result["narrow_draft"] = None
    if not request.include_broad_variant:
        result["broad_draft"] = None

    return result
