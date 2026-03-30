"""API routes for entity browsing, resolution, and management."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from rubberduck.db.models import (
    Entity,
    EntityAlias,
    EntityMention,
    File,
    Relationship,
)
from rubberduck.db.sqlite import get_db
from rubberduck.entities.service import (
    extract_and_resolve,
    get_entity_relationships,
    merge_entities,
)
from rubberduck.jobs.manager import job_manager
from rubberduck.schemas.entities import (
    AliasResponse,
    EntityDetailResponse,
    EntityMergeRequest,
    EntityResponse,
    MentionResponse,
    RelationshipResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/entities", tags=["entities"])


# ── List entities ─────────────────────────────────────────────


@router.get("/", response_model=dict)
def list_entities(
    entity_type: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List entities with optional type filter and pagination."""
    query = db.query(Entity)

    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)

    if search:
        pattern = f"%{search}%"
        query = query.filter(Entity.canonical_name.ilike(pattern))

    total = query.count()

    entities = (
        query.order_by(Entity.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for e in entities:
        mention_count = db.query(EntityMention).filter(EntityMention.entity_id == e.id).count()
        alias_count = db.query(EntityAlias).filter(EntityAlias.entity_id == e.id).count()
        items.append(
            EntityResponse(
                id=e.id,
                entity_type=e.entity_type,
                canonical_name=e.canonical_name,
                properties=e.properties,
                mention_count=mention_count,
                alias_count=alias_count,
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
        )

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── Entity detail ────────────────────────────────────────────


@router.get("/{entity_id}", response_model=EntityDetailResponse)
def get_entity(entity_id: str, db: Session = Depends(get_db)):
    """Get entity detail with aliases, recent mentions, and relationship count."""
    entity = db.query(Entity).get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    aliases = db.query(EntityAlias).filter(EntityAlias.entity_id == entity_id).all()
    mentions = (
        db.query(EntityMention)
        .filter(EntityMention.entity_id == entity_id)
        .order_by(EntityMention.created_at.desc())
        .limit(20)
        .all()
    )

    # Enrich mentions with file names
    mention_responses = []
    for m in mentions:
        f = db.query(File).get(m.file_id)
        mention_responses.append(
            MentionResponse(
                id=m.id,
                file_id=m.file_id,
                file_name=f.file_name if f else None,
                extractor=m.extractor,
                mention_text=m.mention_text,
                context_snippet=m.context_snippet,
                char_offset=m.char_offset,
                confidence=m.confidence,
                created_at=m.created_at,
            )
        )

    relationship_count = (
        db.query(Relationship)
        .filter(
            or_(
                Relationship.source_entity_id == entity_id,
                Relationship.target_entity_id == entity_id,
            )
        )
        .count()
    )

    return EntityDetailResponse(
        id=entity.id,
        entity_type=entity.entity_type,
        canonical_name=entity.canonical_name,
        properties=entity.properties,
        mention_count=db.query(EntityMention).filter(EntityMention.entity_id == entity_id).count(),
        alias_count=len(aliases),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        aliases=[AliasResponse.model_validate(a) for a in aliases],
        recent_mentions=mention_responses,
        relationship_count=relationship_count,
    )


# ── Update entity ────────────────────────────────────────────


@router.patch("/{entity_id}", response_model=EntityResponse)
def update_entity(
    entity_id: str,
    body: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Update an entity's canonical name."""
    entity = db.query(Entity).get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if "canonical_name" in body:
        entity.canonical_name = body["canonical_name"]

    db.commit()
    db.refresh(entity)

    mention_count = db.query(EntityMention).filter(EntityMention.entity_id == entity_id).count()
    alias_count = db.query(EntityAlias).filter(EntityAlias.entity_id == entity_id).count()

    return EntityResponse(
        id=entity.id,
        entity_type=entity.entity_type,
        canonical_name=entity.canonical_name,
        properties=entity.properties,
        mention_count=mention_count,
        alias_count=alias_count,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── Merge entities ───────────────────────────────────────────


@router.post("/merge")
def merge(body: EntityMergeRequest, db: Session = Depends(get_db)):
    """Merge two entities into one."""
    try:
        result = merge_entities(db, body.source_entity_id, body.target_entity_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Mentions ─────────────────────────────────────────────────


@router.get("/{entity_id}/mentions", response_model=dict)
def list_mentions(
    entity_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List all mentions of an entity with provenance details."""
    entity = db.query(Entity).get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    query = db.query(EntityMention).filter(EntityMention.entity_id == entity_id)
    total = query.count()

    mentions = (
        query.order_by(EntityMention.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for m in mentions:
        f = db.query(File).get(m.file_id)
        items.append(
            MentionResponse(
                id=m.id,
                file_id=m.file_id,
                file_name=f.file_name if f else None,
                extractor=m.extractor,
                mention_text=m.mention_text,
                context_snippet=m.context_snippet,
                char_offset=m.char_offset,
                confidence=m.confidence,
                created_at=m.created_at,
            ).model_dump()
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── Relationships ────────────────────────────────────────────


@router.get("/{entity_id}/relationships", response_model=list[RelationshipResponse])
def list_relationships(entity_id: str, db: Session = Depends(get_db)):
    """List all relationships for an entity."""
    try:
        rels = get_entity_relationships(db, entity_id)
        return [RelationshipResponse(**r) for r in rels]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Trigger extraction ───────────────────────────────────────


@router.post("/extract")
def trigger_extraction(
    body: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Trigger entity extraction on one or more files.

    Accepts ``{"file_ids": ["id1", "id2", ...]}`` in the request body.
    Returns a job_id for tracking progress.
    """
    file_ids = body.get("file_ids", [])
    if not file_ids:
        raise HTTPException(status_code=400, detail="file_ids is required")

    def _extraction_job(thread_db: Session, job_id: str) -> dict:
        total = len(file_ids)
        results = {"total": total, "succeeded": 0, "failed": 0, "details": []}
        for i, fid in enumerate(file_ids):
            try:
                summary = extract_and_resolve(thread_db, fid)
                results["details"].append(summary)
                results["succeeded"] += 1
            except Exception as exc:
                logger.error("Entity extraction failed for file %s: %s", fid, exc)
                results["details"].append({"file_id": fid, "error": str(exc)})
                results["failed"] += 1
            job_manager.update_progress(
                thread_db, job_id, (i + 1) / total, i + 1, total
            )
        return results

    job_id = job_manager.submit(
        db,
        "extract_entities",
        _extraction_job,
        params={"file_ids": file_ids},
    )

    return {"job_id": job_id, "message": f"Entity extraction started for {len(file_ids)} file(s)"}
