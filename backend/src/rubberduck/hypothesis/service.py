"""Hypothesis service — CRUD and evaluation orchestration."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import Hypothesis, HypothesisFinding, HypothesisGap
from rubberduck.hypothesis.scoring import evaluate_hypothesis


# ── Create ────────────────────────────────────────────────


def create_hypothesis(
    db: Session,
    case_id: str,
    title: str,
    description: str | None = None,
    scoring_rubric: str | None = None,
) -> Hypothesis:
    """Create a new hypothesis linked to *case_id* and return it."""
    hypothesis = Hypothesis(
        case_id=case_id,
        title=title,
        description=description,
        scoring_rubric=scoring_rubric,
    )
    db.add(hypothesis)
    db.commit()
    db.refresh(hypothesis)
    return hypothesis


# ── Evaluate ──────────────────────────────────────────────


def evaluate(db: Session, hypothesis_id: str) -> dict[str, Any]:
    """Run the scoring engine and persist the updated confidence.

    Returns the full :func:`evaluate_hypothesis` result dict.
    """
    return evaluate_hypothesis(db, hypothesis_id)


# ── Findings ──────────────────────────────────────────────


def add_finding(
    db: Session,
    hypothesis_id: str,
    finding_type: str,
    description: str,
    evidence_file_id: str | None = None,
    entity_id: str | None = None,
    weight: float = 1.0,
) -> HypothesisFinding:
    """Attach a new finding to the hypothesis."""
    # Validate the hypothesis exists
    hypothesis = db.query(Hypothesis).get(hypothesis_id)
    if hypothesis is None:
        raise ValueError(f"Hypothesis {hypothesis_id!r} not found")

    valid_types = {"supporting", "disconfirming", "neutral", "ambiguous"}
    if finding_type not in valid_types:
        raise ValueError(
            f"finding_type must be one of {valid_types!r}, got {finding_type!r}"
        )

    finding = HypothesisFinding(
        hypothesis_id=hypothesis_id,
        finding_type=finding_type,
        description=description,
        evidence_file_id=evidence_file_id,
        entity_id=entity_id,
        weight=weight,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


# ── Detail ────────────────────────────────────────────────


def get_detail(db: Session, hypothesis_id: str) -> dict[str, Any]:
    """Return hypothesis data together with its findings and gaps.

    Returns a dict suitable for serialization into
    ``HypothesisDetailResponse``.
    """
    hypothesis = db.query(Hypothesis).get(hypothesis_id)
    if hypothesis is None:
        raise ValueError(f"Hypothesis {hypothesis_id!r} not found")

    findings = (
        db.query(HypothesisFinding)
        .filter(HypothesisFinding.hypothesis_id == hypothesis_id)
        .order_by(HypothesisFinding.created_at.desc())
        .all()
    )

    gaps = (
        db.query(HypothesisGap)
        .filter(HypothesisGap.hypothesis_id == hypothesis_id)
        .order_by(HypothesisGap.created_at.desc())
        .all()
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
        "finding_count": len(findings),
        "gap_count": len(gaps),
        "findings": [
            {
                "id": f.id,
                "finding_type": f.finding_type,
                "description": f.description,
                "evidence_file_id": f.evidence_file_id,
                "entity_id": f.entity_id,
                "weight": f.weight,
                "auto_generated": f.auto_generated,
                "created_at": f.created_at,
            }
            for f in findings
        ],
        "gaps": [
            {
                "id": g.id,
                "description": g.description,
                "suggested_source": g.suggested_source,
                "priority": g.priority,
                "resolved": g.resolved,
                "created_at": g.created_at,
            }
            for g in gaps
        ],
    }
