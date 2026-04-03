"""Schemas for evidence ingestion and file management."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Cases ──────────────────────────────────────────────────

class CaseCreate(BaseModel):
    name: str
    description: str | None = None
    case_number: str | None = None
    court: str = "San Francisco Superior Court, Probate Division"
    petitioner_name: str | None = None
    decedent_name: str | None = None
    judge_name: str | None = None
    department: str | None = None


class CaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    case_number: str | None = None
    court: str | None = None
    petitioner_name: str | None = None
    decedent_name: str | None = None
    judge_name: str | None = None
    department: str | None = None


class CaseResponse(BaseModel):
    id: str
    name: str
    description: str | None
    case_number: str | None
    court: str | None
    petitioner_name: str | None
    decedent_name: str | None
    judge_name: str | None
    department: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Evidence Sources ───────────────────────────────────────

class EvidenceSourceCreate(BaseModel):
    case_id: str
    label: str
    source_type: str = "upload"
    received_from: str | None = None
    notes: str | None = None


class EvidenceSourceResponse(BaseModel):
    id: str
    case_id: str
    label: str
    source_type: str
    received_from: str | None
    notes: str | None
    created_at: datetime | None
    file_count: int = 0

    model_config = {"from_attributes": True}


# ── Files ──────────────────────────────────────────────────

class FileResponse(BaseModel):
    id: str
    source_id: str
    original_path: str | None
    file_name: str
    file_ext: str | None
    mime_type: str | None
    file_size_bytes: int | None
    sha256: str | None
    md5: str | None
    is_archive: bool
    is_duplicate: bool
    parent_file_id: str | None
    parse_status: str
    parse_error: str | None
    parser_used: str | None
    created_at: datetime | None
    parsed_at: datetime | None

    model_config = {"from_attributes": True}


class FileDetailResponse(FileResponse):
    custody_chain: list["CustodyEntryResponse"] = []
    entity_mention_count: int = 0


class CustodyEntryResponse(BaseModel):
    id: str
    action: str
    actor: str | None
    timestamp: datetime | None
    details: str | None

    model_config = {"from_attributes": True}


# ── Ingestion ──────────────────────────────────────────────

class IngestDirectoryRequest(BaseModel):
    source_id: str
    path: str


class IngestResponse(BaseModel):
    job_id: str
    message: str


# ── Stats ──────────────────────────────────────────────────

class EvidenceStats(BaseModel):
    total_files: int = 0
    total_size_bytes: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    sources_count: int = 0
    duplicate_count: int = 0
