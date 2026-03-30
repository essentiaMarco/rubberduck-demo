"""Schemas for legal drafting module."""

from datetime import datetime

from pydantic import BaseModel, Field


class LegalDocCreate(BaseModel):
    case_id: str
    doc_type: str  # proposed_order, declaration, exhibit_list, petition, memo, service_instructions
    title: str
    template_name: str | None = None
    provider: str | None = None  # google, apple, microsoft
    parameters: dict = Field(default_factory=dict)


class LegalDocUpdate(BaseModel):
    title: str | None = None
    parameters: dict | None = None
    status: str | None = None


class LegalDocResponse(BaseModel):
    id: str
    case_id: str
    doc_type: str
    title: str
    template_name: str | None
    provider: str | None
    status: str
    assumptions: str | None
    unresolved_issues: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class LegalDocDetailResponse(LegalDocResponse):
    rendered_content: str | None
    parameters: str | None


class TemplateInfo(BaseModel):
    name: str
    doc_type: str
    description: str
    provider: str | None = None
    parameters_schema: dict = Field(default_factory=dict)


class GapAnalysis(BaseModel):
    case_id: str
    covered_categories: list["CategoryCoverage"] = []
    missing_categories: list["CategoryCoverage"] = []
    recommendations: list[str] = []
    statutory_basis: list["StatutoryEntry"] = []
    unresolved_issues: list[str] = []


class CategoryCoverage(BaseModel):
    provider: str
    category: str
    status: str  # covered, missing, partial
    existing_order: str | None = None
    evidence_basis: str | None = None
    legal_basis: str | None = None
    notes: str | None = None


class StatutoryEntry(BaseModel):
    citation: str
    summary: str
    applicability: str
    notes: str | None = None


# ── Google Order Builder ───────────────────────────────────

class GoogleProductCategory(BaseModel):
    product: str  # YouTube, Maps, Chrome, etc.
    category: str  # watch_history, search_history, location_history, etc.
    description: str
    date_range_start: str | None = None
    date_range_end: str | None = None
    accounts: list[str] = []
    legal_basis: str | None = None
    necessity_statement: str | None = None
    selected: bool = False
    notes: str | None = None


class GoogleOrderRequest(BaseModel):
    case_id: str
    accounts: list[str]
    categories: list[GoogleProductCategory]
    date_range_start: str | None = None
    date_range_end: str | None = None
    include_narrow_variant: bool = True
    include_broad_variant: bool = True


class GoogleOrderResponse(BaseModel):
    narrow_draft: str | None = None
    broad_draft: str | None = None
    necessity_memo: str | None = None
    attachment_checklist: list[str] = []
    evidentiary_gaps: list[str] = []
    assumptions: list[str] = []
