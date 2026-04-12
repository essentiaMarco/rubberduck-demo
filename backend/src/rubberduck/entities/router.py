"""API routes for entity browsing, resolution, and management."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, text
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


@router.get("", response_model=dict)
@router.get("/", response_model=dict)
def list_entities(
    entity_type: str | None = None,
    search: str | None = None,
    source_id: str | None = None,
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    sort_by: str = Query("mentions", description="Sort by: mentions, aliases, name, updated"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List entities with optional type filter, sorting, and pagination.

    Sorting options:
      - mentions: most mentions first (default)
      - aliases: most aliases first
      - name: alphabetical by canonical_name
      - updated: most recently updated first

    Uses raw SQL for performance on large datasets (198K+ entities, 3M+ mentions).
    """
    # Build WHERE clauses and parameters
    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if entity_type:
        where_clauses.append("e.entity_type = :entity_type")
        params["entity_type"] = entity_type
    if search:
        where_clauses.append("e.canonical_name LIKE :search")
        params["search"] = f"%{search}%"
    if source_id:
        where_clauses.append(
            "e.id IN (SELECT DISTINCT em2.entity_id FROM entity_mentions em2 "
            "JOIN files f ON em2.file_id = f.id WHERE f.source_id = :source_id)"
        )
        params["source_id"] = source_id
    if date_start:
        where_clauses.append("e.created_at >= :date_start")
        params["date_start"] = date_start
    if date_end:
        where_clauses.append("e.created_at <= :date_end")
        params["date_end"] = date_end

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Fast total count on base table
    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM entities e {where_sql}"), params
    ).scalar()
    total = count_row or 0

    # For count-based sorts on large datasets, use a pre-aggregated join
    # which SQLite can sort efficiently. For column-based sorts, query directly.
    sort_join = ""
    sort_order = ""
    if sort_by == "name":
        sort_order = "ORDER BY e.canonical_name ASC"
    elif sort_by == "updated":
        sort_order = "ORDER BY e.updated_at DESC"
    elif sort_by == "aliases":
        sort_join = (
            "LEFT JOIN (SELECT entity_id, COUNT(*) as cnt "
            "FROM entity_aliases GROUP BY entity_id) sc ON e.id = sc.entity_id"
        )
        sort_order = "ORDER BY COALESCE(sc.cnt, 0) DESC"
    else:  # mentions (default)
        sort_join = (
            "LEFT JOIN (SELECT entity_id, COUNT(*) as cnt "
            "FROM entity_mentions GROUP BY entity_id) sc ON e.id = sc.entity_id"
        )
        sort_order = "ORDER BY COALESCE(sc.cnt, 0) DESC"

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    # Phase 1: get the page of entity IDs (fast with GROUP BY + index)
    id_rows = db.execute(
        text(
            f"SELECT e.id FROM entities e {sort_join} {where_sql} "
            f"{sort_order} LIMIT :limit OFFSET :offset"
        ),
        params,
    ).fetchall()

    if not id_rows:
        return {"items": [], "total": total, "page": page, "page_size": page_size}

    entity_ids = [r[0] for r in id_rows]

    # Phase 2: fetch full entity data + counts for just this page
    placeholders = ", ".join([f":id_{i}" for i in range(len(entity_ids))])
    id_params = {f"id_{i}": eid for i, eid in enumerate(entity_ids)}

    rows = db.execute(
        text(
            f"SELECT e.id, e.entity_type, e.canonical_name, e.properties, "
            f"e.created_at, e.updated_at, "
            f"(SELECT COUNT(*) FROM entity_mentions em WHERE em.entity_id = e.id) AS mention_count, "
            f"(SELECT COUNT(*) FROM entity_aliases ea WHERE ea.entity_id = e.id) AS alias_count "
            f"FROM entities e WHERE e.id IN ({placeholders})"
        ),
        id_params,
    ).fetchall()

    # Re-sort to match the original ordering from Phase 1
    id_order = {eid: idx for idx, eid in enumerate(entity_ids)}
    rows = sorted(rows, key=lambda r: id_order.get(r[0], 0))

    items = []
    for r in rows:
        items.append(
            EntityResponse(
                id=r[0],
                entity_type=r[1],
                canonical_name=r[2],
                properties=r[3],
                mention_count=r[6],
                alias_count=r[7],
                created_at=r[4],
                updated_at=r[5],
            ).model_dump()
        )

    return {
        "items": items,
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


@router.post("/re-extract-all")
def re_extract_all_entities(db: Session = Depends(get_db)):
    """Clear ALL existing entities and re-extract from parsed content.

    This is useful after improving the NER pipeline (e.g. better noise
    filtering, HTML stripping fixes) to replace garbage entities with
    clean ones.

    Runs as a background job.
    """
    def _reextract_job(thread_db: Session, job_id: str) -> dict:
        from rubberduck.db.models import Entity, EntityAlias, EntityMention, Relationship

        # Step 1: Clear all existing entity data
        logger.info("Clearing all existing entity data...")
        thread_db.execute(text("DELETE FROM relationships"))
        thread_db.execute(text("DELETE FROM entity_mentions"))
        thread_db.execute(text("DELETE FROM entity_aliases"))
        thread_db.execute(text("DELETE FROM entities"))
        thread_db.commit()
        logger.info("Entity data cleared")

        # Step 2: Re-extract from all parsed files
        files = (
            thread_db.query(File)
            .filter(File.parse_status == "completed", File.parsed_path.isnot(None))
            .all()
        )
        total = len(files)
        results = {"total": total, "succeeded": 0, "failed": 0}

        for i, f in enumerate(files):
            try:
                extract_and_resolve(thread_db, f.id)
                results["succeeded"] += 1
            except Exception as exc:
                logger.error("Re-extraction failed for file %s: %s", f.id, exc)
                results["failed"] += 1
            if (i + 1) % 50 == 0 or i == total - 1:
                job_manager.update_progress(
                    thread_db, job_id, (i + 1) / total, i + 1, total
                )
        return results

    job_id = job_manager.submit(
        db,
        "re_extract_all_entities",
        _reextract_job,
        params={},
    )
    return {"job_id": job_id, "message": "Full entity re-extraction started"}


@router.post("/cleanup-noise")
def cleanup_noise_entities(db: Session = Depends(get_db)):
    """Delete entities that match known noise patterns (fonts, CSS, HTML artifacts).

    This is a fast cleanup that removes garbage without full re-extraction.
    Deletes the entity and cascades to mentions, aliases, and relationships.
    """
    from rubberduck.entities.spacy_ner import _BLOCKLIST, _is_noise

    all_entities = db.query(Entity).all()
    deleted = 0
    deleted_names = []

    for entity in all_entities:
        name = entity.canonical_name or ""
        if _is_noise(name) or len(name) <= 2:
            # Delete mentions first (FK constraint)
            db.query(EntityMention).filter(EntityMention.entity_id == entity.id).delete()
            db.query(Relationship).filter(
                (Relationship.source_entity_id == entity.id) | (Relationship.target_entity_id == entity.id)
            ).delete(synchronize_session=False)
            from rubberduck.db.models import EntityAlias
            db.query(EntityAlias).filter(EntityAlias.entity_id == entity.id).delete()
            db.delete(entity)
            deleted += 1
            if deleted <= 20:
                deleted_names.append(name)

    db.commit()
    return {
        "deleted": deleted,
        "sample_deleted": deleted_names,
        "remaining": db.query(Entity).count(),
    }
