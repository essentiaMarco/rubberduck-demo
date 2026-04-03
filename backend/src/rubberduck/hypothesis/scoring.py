"""Confidence scoring engine for hypothesis evaluation.

Calculates a normalized confidence score based on the weight and type of
linked findings, adjusting downward for unresolved evidence gaps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import Hypothesis, HypothesisFinding, HypothesisGap


# ── Confidence thresholds for human-readable labels ───────

_CONFIDENCE_LABELS: list[tuple[float, str]] = [
    (0.85, "high"),
    (0.65, "moderate"),
    (0.40, "low"),
    (0.0, "very low"),
]


def _confidence_label(score: float) -> str:
    """Return a human-readable label for the given 0-1 confidence score."""
    for threshold, label in _CONFIDENCE_LABELS:
        if score >= threshold:
            return label
    return "very low"


# ── Core evaluation ───────────────────────────────────────


def evaluate_hypothesis(db: Session, hypothesis_id: str) -> dict[str, Any]:
    """Score a hypothesis and return a detailed evaluation result.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    hypothesis_id:
        Primary key of the :class:`Hypothesis` to evaluate.

    Returns
    -------
    dict
        Keys: hypothesis_id, confidence, supporting_count,
        disconfirming_count, neutral_count, gap_count,
        rubric_breakdown, summary.
    """
    hypothesis = db.query(Hypothesis).get(hypothesis_id)
    if hypothesis is None:
        raise ValueError(f"Hypothesis {hypothesis_id!r} not found")

    findings: list[HypothesisFinding] = (
        db.query(HypothesisFinding)
        .filter(HypothesisFinding.hypothesis_id == hypothesis_id)
        .all()
    )

    gaps: list[HypothesisGap] = (
        db.query(HypothesisGap)
        .filter(
            HypothesisGap.hypothesis_id == hypothesis_id,
            HypothesisGap.resolved.is_(False),
        )
        .all()
    )

    # ── Bucket findings by type ───────────────────────────
    supporting_weight = 0.0
    disconfirming_weight = 0.0
    neutral_weight = 0.0
    supporting_count = 0
    disconfirming_count = 0
    neutral_count = 0

    for f in findings:
        w = max(f.weight or 1.0, 0.0)
        if f.finding_type == "supporting":
            supporting_weight += w
            supporting_count += 1
        elif f.finding_type == "disconfirming":
            disconfirming_weight += w
            disconfirming_count += 1
        else:
            # neutral and ambiguous both count as neutral
            neutral_weight += w
            neutral_count += 1

    total_weight = supporting_weight + disconfirming_weight + neutral_weight
    gap_count = len(gaps)

    # ── Confidence formula ────────────────────────────────
    # Raw score: (supporting - disconfirming) / total, in [-1, 1]
    # Normalized to [0, 1] via (raw + 1) / 2.
    # Gaps apply a multiplicative penalty: each unresolved gap reduces
    # confidence by 5%, capped so the penalty never exceeds 50%.
    if total_weight > 0:
        raw = (supporting_weight - disconfirming_weight) / total_weight
    else:
        # No findings at all: raw = 0 → normalized would be 0.5, which is
        # misleadingly high.  With zero evidence the confidence should be 0.
        raw = 0.0

    if total_weight > 0:
        normalized = (raw + 1.0) / 2.0
    else:
        # No evidence → no confidence
        normalized = 0.0

    gap_penalty = min(gap_count * 0.05, 0.50)
    confidence = max(normalized * (1.0 - gap_penalty), 0.0)
    confidence = round(min(confidence, 1.0), 4)

    # ── Rubric breakdown ──────────────────────────────────
    rubric_breakdown = {
        "supporting_weight": round(supporting_weight, 4),
        "disconfirming_weight": round(disconfirming_weight, 4),
        "neutral_weight": round(neutral_weight, 4),
        "total_weight": round(total_weight, 4),
        "raw_score": round(raw, 4),
        "normalized_score": round(normalized, 4),
        "gap_penalty": round(gap_penalty, 4),
        "final_confidence": confidence,
    }

    # ── Summary text ──────────────────────────────────────
    label = _confidence_label(confidence)
    parts: list[str] = [
        f"Confidence is {label} ({confidence:.0%}).",
        f"{supporting_count} supporting finding(s) (weight {supporting_weight:.1f}),",
        f"{disconfirming_count} disconfirming (weight {disconfirming_weight:.1f}),",
        f"{neutral_count} neutral/ambiguous (weight {neutral_weight:.1f}).",
    ]
    if gap_count:
        parts.append(
            f"{gap_count} unresolved evidence gap(s) reduce confidence "
            f"by {gap_penalty:.0%}."
        )
    summary = " ".join(parts)

    # ── Persist confidence on the hypothesis row ──────────
    hypothesis.confidence = confidence
    hypothesis.last_evaluated = datetime.now(timezone.utc)
    db.commit()

    return {
        "hypothesis_id": hypothesis_id,
        "confidence": confidence,
        "supporting_count": supporting_count,
        "disconfirming_count": disconfirming_count,
        "neutral_count": neutral_count,
        "gap_count": gap_count,
        "rubric_breakdown": rubric_breakdown,
        "summary": summary,
    }
