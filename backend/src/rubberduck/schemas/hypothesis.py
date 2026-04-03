"""Schemas for hypothesis testing workspace."""

from datetime import datetime

from pydantic import BaseModel, Field


class HypothesisCreate(BaseModel):
    case_id: str
    title: str
    description: str | None = None
    scoring_rubric: str | None = None  # JSON


class HypothesisUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    scoring_rubric: str | None = None


class HypothesisResponse(BaseModel):
    id: str
    case_id: str
    title: str
    description: str | None
    status: str
    confidence: float | None
    scoring_rubric: str | None
    created_at: datetime | None
    updated_at: datetime | None
    last_evaluated: datetime | None
    finding_count: int = 0
    gap_count: int = 0

    model_config = {"from_attributes": True}


class HypothesisDetailResponse(HypothesisResponse):
    findings: list["FindingResponse"] = []
    gaps: list["GapResponse"] = []


class FindingCreate(BaseModel):
    finding_type: str  # supporting, disconfirming, neutral, ambiguous
    description: str
    evidence_file_id: str | None = None
    entity_id: str | None = None
    weight: float = 1.0


class FindingResponse(BaseModel):
    id: str
    finding_type: str
    description: str
    evidence_file_id: str | None
    entity_id: str | None
    weight: float
    auto_generated: bool
    created_at: datetime | None

    model_config = {"from_attributes": True}


class GapResponse(BaseModel):
    id: str
    description: str
    suggested_source: str | None
    priority: str
    resolved: bool
    created_at: datetime | None

    model_config = {"from_attributes": True}


class EvaluationResult(BaseModel):
    hypothesis_id: str
    confidence: float
    supporting_count: int
    disconfirming_count: int
    neutral_count: int
    gap_count: int
    rubric_breakdown: dict = Field(default_factory=dict)
    summary: str
