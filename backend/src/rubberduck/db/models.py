"""SQLAlchemy ORM models — the canonical schema for all SQLite-backed data."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Cases ──────────────────────────────────────────────────


class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text)
    case_number = Column(String)
    court = Column(String, default="San Francisco Superior Court, Probate Division")
    petitioner_name = Column(String)
    decedent_name = Column(String)
    judge_name = Column(String)
    department = Column(String)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    sources = relationship("EvidenceSource", back_populates="case")
    hypotheses = relationship("Hypothesis", back_populates="case")
    legal_documents = relationship("LegalDocument", back_populates="case")


# ── Evidence ───────────────────────────────────────────────


class EvidenceSource(Base):
    __tablename__ = "evidence_sources"

    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    label = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # upload, osint_capture, manual, provider_response
    received_from = Column(String)
    received_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=_utcnow)

    case = relationship("Case", back_populates="sources")
    files = relationship("File", back_populates="source")


class File(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, default=_uuid)
    source_id = Column(String, ForeignKey("evidence_sources.id"), nullable=False)
    original_path = Column(String)  # path within source archive/directory
    stored_path = Column(String)  # path in data/originals/
    parsed_path = Column(String)  # path in data/parsed/
    file_name = Column(String, nullable=False)
    file_ext = Column(String)
    mime_type = Column(String)
    file_size_bytes = Column(Integer)
    sha256 = Column(String)
    md5 = Column(String)
    is_archive = Column(Boolean, default=False)
    parent_file_id = Column(String, ForeignKey("files.id"))
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_id = Column(String, ForeignKey("files.id"))
    parse_status = Column(String, default="pending")  # pending, processing, completed, failed, unsupported
    parse_error = Column(Text)
    parser_used = Column(String)
    created_at = Column(DateTime, default=_utcnow)
    parsed_at = Column(DateTime)

    source = relationship("EvidenceSource", back_populates="files")
    parent = relationship("File", remote_side=[id], foreign_keys=[parent_file_id])
    custody_entries = relationship("ChainOfCustody", back_populates="file")
    entity_mentions = relationship("EntityMention", back_populates="file")

    __table_args__ = (
        Index("ix_files_source_id", "source_id"),
        Index("ix_files_sha256", "sha256"),
        Index("ix_files_ext", "file_ext"),
        Index("ix_files_status", "parse_status"),
    )


class EmailMessage(Base):
    """Individual email extracted from EML/MBOX files.

    Stores per-email metadata so investigators can filter by sender,
    subject, date, spam classification, and communication type instead
    of wading through a monolithic MBOX text dump.
    """
    __tablename__ = "email_messages"

    id = Column(String, primary_key=True, default=_uuid)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    message_index = Column(Integer, default=0)  # position within MBOX
    message_id = Column(String)  # RFC Message-ID header
    in_reply_to = Column(String)  # threading
    email_from = Column(String)
    email_to = Column(String)
    email_cc = Column(String)
    email_subject = Column(String)
    email_date = Column(DateTime)
    email_date_raw = Column(String)  # original Date header string
    body_preview = Column(Text)  # first ~500 chars of body for quick preview
    body_length = Column(Integer, default=0)
    has_attachments = Column(Boolean, default=False)
    attachment_count = Column(Integer, default=0)
    # Spam detection
    is_spam = Column(Boolean, default=False)
    spam_score = Column(Float, default=0.0)  # 0-1, higher = more likely spam
    spam_reasons = Column(Text)  # JSON list of reasons
    # Classification
    classification = Column(String, default="inbox")  # inbox, sent, spam, newsletter, notification, personal, unknown
    # Communication type for triangulation
    comm_type = Column(String, default="email")  # email, chat, sms, call, whatsapp, etc.
    created_at = Column(DateTime, default=_utcnow)

    file = relationship("File", backref="email_messages")

    __table_args__ = (
        Index("ix_email_file_id", "file_id"),
        Index("ix_email_from", "email_from"),
        Index("ix_email_date", "email_date"),
        Index("ix_email_is_spam", "is_spam"),
        Index("ix_email_classification", "classification"),
        Index("ix_email_comm_type", "comm_type"),
    )


class ChainOfCustody(Base):
    __tablename__ = "chain_of_custody"

    id = Column(String, primary_key=True, default=_uuid)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    action = Column(String, nullable=False)  # received, hashed, stored, parsed, indexed, exported
    actor = Column(String, default="rubberduck")
    timestamp = Column(DateTime, default=_utcnow)
    details = Column(Text)  # JSON string
    prev_entry_id = Column(String, ForeignKey("chain_of_custody.id"))

    file = relationship("File", back_populates="custody_entries")


# ── Entities ───────────────────────────────────────────────


class Entity(Base):
    __tablename__ = "entities"

    id = Column(String, primary_key=True, default=_uuid)
    entity_type = Column(String, nullable=False)  # person, org, email, phone, ip, url, device, location, app, account
    canonical_name = Column(String, nullable=False)
    properties = Column(Text)  # JSON
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    aliases = relationship("EntityAlias", back_populates="entity", cascade="all, delete-orphan")
    mentions = relationship("EntityMention", back_populates="entity", cascade="all, delete-orphan")
    source_relationships = relationship(
        "Relationship",
        foreign_keys="Relationship.source_entity_id",
        back_populates="source_entity",
    )
    target_relationships = relationship(
        "Relationship",
        foreign_keys="Relationship.target_entity_id",
        back_populates="target_entity",
    )

    __table_args__ = (
        Index("ix_entities_type", "entity_type"),
        Index("ix_entities_name", "canonical_name"),
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id = Column(String, primary_key=True, default=_uuid)
    entity_id = Column(String, ForeignKey("entities.id"), nullable=False)
    alias = Column(String, nullable=False)
    alias_type = Column(String)  # name, email_variant, nickname, handle
    confidence = Column(Float, default=1.0)

    entity = relationship("Entity", back_populates="aliases")

    __table_args__ = (Index("ix_alias_text", "alias"),)


class EntityMention(Base):
    __tablename__ = "entity_mentions"

    id = Column(String, primary_key=True, default=_uuid)
    entity_id = Column(String, ForeignKey("entities.id"), nullable=False)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    extractor = Column(String, nullable=False)  # spacy_ner, regex_email, regex_phone, etc.
    mention_text = Column(String, nullable=False)
    context_snippet = Column(Text)  # surrounding text for provenance
    char_offset = Column(Integer)
    page_number = Column(Integer)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=_utcnow)

    entity = relationship("Entity", back_populates="mentions")
    file = relationship("File", back_populates="entity_mentions")

    __table_args__ = (
        Index("ix_mentions_entity", "entity_id"),
        Index("ix_mentions_file", "file_id"),
    )


# ── Relationships (Graph Edges) ────────────────────────────


class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(String, primary_key=True, default=_uuid)
    source_entity_id = Column(String, ForeignKey("entities.id"), nullable=False)
    target_entity_id = Column(String, ForeignKey("entities.id"), nullable=False)
    rel_type = Column(String, nullable=False)  # owns, sent, received, accessed, located_at, etc.
    properties = Column(Text)  # JSON: timestamp, details
    evidence_file_id = Column(String, ForeignKey("files.id"))
    confidence = Column(Float, default=1.0)
    layer = Column(String)  # communications, movements, digital_activity, legal, financial, media, osint
    created_at = Column(DateTime, default=_utcnow)

    source_entity = relationship("Entity", foreign_keys=[source_entity_id])
    target_entity = relationship("Entity", foreign_keys=[target_entity_id])

    __table_args__ = (
        Index("ix_rel_source", "source_entity_id"),
        Index("ix_rel_target", "target_entity_id"),
        Index("ix_rel_type", "rel_type"),
        Index("ix_rel_layer", "layer"),
    )


# ── Hypotheses ─────────────────────────────────────────────


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="active")  # active, supported, refuted, inconclusive
    confidence = Column(Float)
    scoring_rubric = Column(Text)  # JSON
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_evaluated = Column(DateTime)

    case = relationship("Case", back_populates="hypotheses")
    findings = relationship("HypothesisFinding", back_populates="hypothesis", cascade="all, delete-orphan")
    gaps = relationship("HypothesisGap", back_populates="hypothesis", cascade="all, delete-orphan")


class HypothesisFinding(Base):
    __tablename__ = "hypothesis_findings"

    id = Column(String, primary_key=True, default=_uuid)
    hypothesis_id = Column(String, ForeignKey("hypotheses.id"), nullable=False)
    finding_type = Column(String, nullable=False)  # supporting, disconfirming, neutral, ambiguous
    description = Column(Text, nullable=False)
    evidence_file_id = Column(String, ForeignKey("files.id"))
    entity_id = Column(String, ForeignKey("entities.id"))
    weight = Column(Float, default=1.0)
    auto_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)

    hypothesis = relationship("Hypothesis", back_populates="findings")


class HypothesisGap(Base):
    __tablename__ = "hypothesis_gaps"

    id = Column(String, primary_key=True, default=_uuid)
    hypothesis_id = Column(String, ForeignKey("hypotheses.id"), nullable=False)
    description = Column(Text, nullable=False)
    suggested_source = Column(Text)
    priority = Column(String, default="medium")  # low, medium, high, critical
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)

    hypothesis = relationship("Hypothesis", back_populates="gaps")


# ── Legal Documents ────────────────────────────────────────


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    doc_type = Column(String, nullable=False)  # proposed_order, declaration, exhibit_list, petition, memo
    title = Column(String, nullable=False)
    template_name = Column(String)
    parameters = Column(Text)  # JSON: template fill values
    rendered_content = Column(Text)  # HTML or markdown
    status = Column(String, default="draft")  # draft, review, finalized_externally
    provider = Column(String)  # google, apple, microsoft
    assumptions = Column(Text)  # JSON: list of assumptions made
    unresolved_issues = Column(Text)  # JSON
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    case = relationship("Case", back_populates="legal_documents")


# ── OSINT Research ─────────────────────────────────────────


class ResearchPlan(Base):
    __tablename__ = "research_plans"

    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    targets = Column(Text)  # JSON: list of URLs/queries
    rationale = Column(Text)
    status = Column(String, default="draft")  # draft, approved, executing, completed, cancelled
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime)


class ResearchCapture(Base):
    __tablename__ = "research_captures"

    id = Column(String, primary_key=True, default=_uuid)
    plan_id = Column(String, ForeignKey("research_plans.id"))
    url = Column(String, nullable=False)
    capture_timestamp = Column(DateTime, default=_utcnow)
    page_title = Column(String)
    extracted_text = Column(Text)
    html_snapshot_path = Column(String)
    screenshot_path = Column(String)
    http_status = Column(Integer)
    content_hash = Column(String)  # SHA-256 of captured content
    provenance_notes = Column(Text)


# ── Phone CDR Records ─────────────────────────────────────


class PhoneRecord(Base):
    """Individual call/SMS record extracted from phone bills (CDR data)."""

    __tablename__ = "phone_records"

    id = Column(String, primary_key=True, default=_uuid)
    file_id = Column(String, ForeignKey("files.id"))
    record_index = Column(Integer, default=0)

    # Subscriber info (from bill header)
    subscriber_number = Column(String)  # e.g. "7356117700"
    subscriber_name = Column(String)  # e.g. "GOUTHAM VIJAYAKUMAR"

    # Call metadata
    caller_number = Column(String)  # normalized phone number (source)
    called_number = Column(String)  # normalized phone number (destination)
    call_datetime = Column(DateTime)
    call_datetime_raw = Column(String)  # original string from PDF
    duration_seconds = Column(Integer, default=0)
    duration_raw = Column(String)  # original "Min:Sec" string
    charges = Column(Float, default=0.0)

    # Classification
    call_type = Column(String)  # outgoing_local, outgoing_std, incoming, sms_outgoing, sms_incoming

    # Bill context
    bill_period_start = Column(DateTime)
    bill_period_end = Column(DateTime)
    bill_number = Column(String)
    bill_plan = Column(String)  # tariff plan name

    # Anomaly detection
    is_anomaly = Column(Boolean, default=False)
    anomaly_score = Column(Float, default=0.0)
    anomaly_reasons = Column(Text)  # JSON list of reasons

    created_at = Column(DateTime, default=_utcnow)

    # Relationships
    file = relationship("File", backref="phone_records")

    __table_args__ = (
        Index("ix_phone_file_id", "file_id"),
        Index("ix_phone_caller", "caller_number"),
        Index("ix_phone_called", "called_number"),
        Index("ix_phone_datetime", "call_datetime"),
        Index("ix_phone_call_type", "call_type"),
        Index("ix_phone_is_anomaly", "is_anomaly"),
        Index("ix_phone_subscriber", "subscriber_number"),
    )


# ── Background Jobs ────────────────────────────────────────


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=_uuid)
    job_type = Column(String, nullable=False)  # ingest, parse, extract_entities, build_graph, osint, legal_render
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    progress = Column(Float, default=0.0)  # 0.0 to 1.0
    total_items = Column(Integer)
    processed_items = Column(Integer, default=0)
    current_step = Column(String)  # Human-readable label for current pipeline step
    params = Column(Text)  # JSON
    result = Column(Text)  # JSON
    error = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow)


# ── Notebook / Case Memos ──────────────────────────────────


class NotebookEntry(Base):
    __tablename__ = "notebook_entries"

    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text)  # Markdown with source citations
    pinned_evidence = Column(Text)  # JSON: list of {file_id, quote, offset}
    tags = Column(Text)  # JSON: list of tags
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Saved Queries ──────────────────────────────────────────


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id = Column(String, primary_key=True, default=_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    name = Column(String, nullable=False)
    query_type = Column(String, nullable=False)  # search, timeline, entity, graph
    parameters = Column(Text, nullable=False)  # JSON
    description = Column(Text)
    created_at = Column(DateTime, default=_utcnow)
