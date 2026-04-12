"""API routes for the hypothesis testing workspace."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from rubberduck.db.models import Hypothesis, HypothesisFinding
from rubberduck.db.sqlite import get_db
from rubberduck.hypothesis import service as hyp_service
from rubberduck.schemas.hypothesis import (
    EvaluationResult,
    FindingCreate,
    FindingResponse,
    HypothesisCreate,
    HypothesisDetailResponse,
    HypothesisResponse,
    HypothesisUpdate,
)

router = APIRouter(prefix="/api/hypotheses", tags=["hypotheses"])


# ── Create ────────────────────────────────────────────────


@router.post("", response_model=HypothesisResponse)
@router.post("/", response_model=HypothesisResponse)
def create_hypothesis(body: HypothesisCreate, db: Session = Depends(get_db)):
    """Create a new hypothesis for a case."""
    hypothesis = hyp_service.create_hypothesis(
        db,
        case_id=body.case_id,
        title=body.title,
        description=body.description,
        scoring_rubric=body.scoring_rubric,
    )
    return _to_response(hypothesis, db)


# ── List ──────────────────────────────────────────────────


@router.get("", response_model=list[HypothesisResponse])
@router.get("/", response_model=list[HypothesisResponse])
def list_hypotheses(
    case_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List hypotheses, optionally filtered by case and/or status."""
    query = db.query(Hypothesis)
    if case_id:
        query = query.filter(Hypothesis.case_id == case_id)
    if status:
        query = query.filter(Hypothesis.status == status)
    hypotheses = query.order_by(Hypothesis.updated_at.desc()).all()
    return [_to_response(h, db) for h in hypotheses]


# ── Detail ────────────────────────────────────────────────


@router.get("/{hypothesis_id}", response_model=HypothesisDetailResponse)
def get_hypothesis(hypothesis_id: str, db: Session = Depends(get_db)):
    """Get a hypothesis with its findings and gaps."""
    try:
        detail = hyp_service.get_detail(db, hypothesis_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return detail


# ── Update ────────────────────────────────────────────────


@router.patch("/{hypothesis_id}", response_model=HypothesisResponse)
def update_hypothesis(
    hypothesis_id: str,
    body: HypothesisUpdate,
    db: Session = Depends(get_db),
):
    """Update editable fields on a hypothesis."""
    hypothesis = db.query(Hypothesis).get(hypothesis_id)
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(hypothesis, key, value)

    db.commit()
    db.refresh(hypothesis)
    return _to_response(hypothesis, db)


# ── Evaluate ──────────────────────────────────────────────


@router.post("/{hypothesis_id}/evaluate", response_model=EvaluationResult)
def evaluate_hypothesis(hypothesis_id: str, db: Session = Depends(get_db)):
    """Run the confidence scoring engine on a hypothesis."""
    try:
        result = hyp_service.evaluate(db, hypothesis_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return result


# ── Findings ──────────────────────────────────────────────


@router.post("/{hypothesis_id}/findings", response_model=FindingResponse)
def add_finding(
    hypothesis_id: str,
    body: FindingCreate,
    db: Session = Depends(get_db),
):
    """Add a finding to a hypothesis."""
    try:
        finding = hyp_service.add_finding(
            db,
            hypothesis_id=hypothesis_id,
            finding_type=body.finding_type,
            description=body.description,
            evidence_file_id=body.evidence_file_id,
            entity_id=body.entity_id,
            weight=body.weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return finding


@router.delete("/{hypothesis_id}/findings/{finding_id}", status_code=204)
def remove_finding(
    hypothesis_id: str,
    finding_id: str,
    db: Session = Depends(get_db),
):
    """Remove a finding from a hypothesis."""
    finding = (
        db.query(HypothesisFinding)
        .filter(
            HypothesisFinding.id == finding_id,
            HypothesisFinding.hypothesis_id == hypothesis_id,
        )
        .first()
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    db.delete(finding)
    db.commit()


# ── Helpers ───────────────────────────────────────────────


def _to_response(hypothesis: Hypothesis, db: Session) -> dict:
    """Build a response dict with finding/gap counts."""
    finding_count = (
        db.query(HypothesisFinding)
        .filter(HypothesisFinding.hypothesis_id == hypothesis.id)
        .count()
    )
    from rubberduck.db.models import HypothesisGap

    gap_count = (
        db.query(HypothesisGap)
        .filter(HypothesisGap.hypothesis_id == hypothesis.id)
        .count()
    )
    return {
        "id": hypothesis.id,
        "case_id": hypothesis.case_id,
        "title": hypothesis.title,
        "description": hypothesis.description,
        "status": hypothesis.status,
        "confidence": hypothesis.confidence,
        "scoring_rubric": hypothesis.scoring_rubric,
        "created_at": hypothesis.created_at,
        "updated_at": hypothesis.updated_at,
        "last_evaluated": hypothesis.last_evaluated,
        "finding_count": finding_count,
        "gap_count": gap_count,
    }
