"""Schemas for entity extraction, resolution, and browsing."""

from datetime import datetime

from pydantic import BaseModel, Field


class EntityResponse(BaseModel):
    id: str
    entity_type: str
    canonical_name: str
    properties: str | None
    mention_count: int = 0
    alias_count: int = 0
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class EntityDetailResponse(EntityResponse):
    aliases: list["AliasResponse"] = []
    recent_mentions: list["MentionResponse"] = []
    relationship_count: int = 0


class AliasResponse(BaseModel):
    id: str
    alias: str
    alias_type: str | None
    confidence: float

    model_config = {"from_attributes": True}


class MentionResponse(BaseModel):
    id: str
    file_id: str
    file_name: str | None = None
    extractor: str
    mention_text: str
    context_snippet: str | None
    char_offset: int | None
    confidence: float
    created_at: datetime | None

    model_config = {"from_attributes": True}


class EntityMergeRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str


class RelationshipResponse(BaseModel):
    id: str
    source_entity_id: str
    source_entity_name: str | None = None
    source_entity_type: str | None = None
    target_entity_id: str
    target_entity_name: str | None = None
    target_entity_type: str | None = None
    rel_type: str
    properties: str | None
    confidence: float
    layer: str | None
    evidence_file_id: str | None
    created_at: datetime | None

    model_config = {"from_attributes": True}
