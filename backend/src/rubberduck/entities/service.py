"""Entity service — orchestrates extraction, resolution, and management."""

import gc
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from rubberduck.db.models import (
    Entity,
    EntityAlias,
    EntityMention,
    File,
    Relationship,
)
from rubberduck.entities.regex_extractors import extract_all as regex_extract_all
from rubberduck.entities.resolver import resolve_mentions
from rubberduck.entities.spacy_ner import extract_entities as spacy_extract

logger = logging.getLogger(__name__)


def extract_and_resolve(db: Session, file_id: str) -> dict[str, Any]:
    """Run NER + regex extraction on a file's parsed text, then resolve all mentions.

    Reads the ``content.txt`` written by the parser for the given file,
    runs both the spaCy NER pipeline and the regex extractors, and
    resolves all resulting mentions to canonical Entity records.

    Returns a summary dict with counts.
    """
    file_record = db.query(File).get(file_id)
    if not file_record:
        raise ValueError(f"File not found: {file_id}")

    if not file_record.parsed_path:
        raise ValueError(f"File {file_id} has not been parsed yet")

    content_path = Path(file_record.parsed_path) / "content.txt"
    if not content_path.exists():
        raise ValueError(f"Parsed content not found at {content_path}")

    text = content_path.read_text(encoding="utf-8")
    if not text.strip():
        return {"file_id": file_id, "spacy_mentions": 0, "regex_mentions": 0, "resolved": 0}

    # Cap text at 2 MB to prevent spaCy from consuming excessive memory
    MAX_TEXT_LEN = 2 * 1024 * 1024
    if len(text) > MAX_TEXT_LEN:
        logger.warning("Truncating file %s content from %d to %d chars for NER", file_id, len(text), MAX_TEXT_LEN)
        text = text[:MAX_TEXT_LEN]

    # Run extractors
    spacy_mentions = spacy_extract(text, file_id=file_id)
    regex_mentions = regex_extract_all(text, file_id=file_id)

    all_mentions = spacy_mentions + regex_mentions

    # Resolve against existing entities
    resolved = resolve_mentions(db, all_mentions, file_id, source_text=text)

    result = {
        "file_id": file_id,
        "spacy_mentions": len(spacy_mentions),
        "regex_mentions": len(regex_mentions),
        "resolved": len(resolved),
    }

    # Explicitly free large objects to reduce memory pressure
    del text, spacy_mentions, regex_mentions, all_mentions, resolved
    gc.collect()

    return result


def merge_entities(db: Session, source_id: str, target_id: str) -> dict[str, Any]:
    """Merge *source_id* entity into *target_id*.

    Moves all aliases, mentions, and relationships from the source entity
    to the target entity, then deletes the source.

    Returns a summary of what was merged.
    """
    source = db.query(Entity).get(source_id)
    target = db.query(Entity).get(target_id)

    if not source:
        raise ValueError(f"Source entity not found: {source_id}")
    if not target:
        raise ValueError(f"Target entity not found: {target_id}")
    if source_id == target_id:
        raise ValueError("Cannot merge an entity into itself")

    # Move aliases
    aliases_moved = 0
    for alias in source.aliases:
        # Check for duplicate alias on target
        existing = (
            db.query(EntityAlias)
            .filter(EntityAlias.entity_id == target_id, EntityAlias.alias == alias.alias)
            .first()
        )
        if existing:
            db.delete(alias)
        else:
            alias.entity_id = target_id
            aliases_moved += 1

    # Move mentions
    mentions_moved = (
        db.query(EntityMention)
        .filter(EntityMention.entity_id == source_id)
        .update({"entity_id": target_id})
    )

    # Move relationships (both directions)
    rels_source = (
        db.query(Relationship)
        .filter(Relationship.source_entity_id == source_id)
        .update({"source_entity_id": target_id})
    )
    rels_target = (
        db.query(Relationship)
        .filter(Relationship.target_entity_id == source_id)
        .update({"target_entity_id": target_id})
    )

    # Delete the source entity (aliases cascaded via relationship config)
    db.delete(source)
    db.commit()

    logger.info(
        "Merged entity %s into %s: %d aliases, %d mentions, %d relationships moved",
        source_id,
        target_id,
        aliases_moved,
        mentions_moved,
        rels_source + rels_target,
    )

    return {
        "source_id": source_id,
        "target_id": target_id,
        "aliases_moved": aliases_moved,
        "mentions_moved": mentions_moved,
        "relationships_moved": rels_source + rels_target,
    }


def get_entity_relationships(db: Session, entity_id: str) -> list[dict[str, Any]]:
    """Get all relationships where *entity_id* is source or target.

    Returns dicts with full entity name/type info for both ends.
    """
    entity = db.query(Entity).get(entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_id}")

    # Use aliased joins to fetch source and target entity names in a
    # single query instead of issuing 2 * N individual queries (N+1 problem).
    from sqlalchemy.orm import aliased

    SrcEntity = aliased(Entity, name="src_entity")
    TgtEntity = aliased(Entity, name="tgt_entity")

    rows = (
        db.query(Relationship, SrcEntity, TgtEntity)
        .outerjoin(SrcEntity, Relationship.source_entity_id == SrcEntity.id)
        .outerjoin(TgtEntity, Relationship.target_entity_id == TgtEntity.id)
        .filter(
            or_(
                Relationship.source_entity_id == entity_id,
                Relationship.target_entity_id == entity_id,
            )
        )
        .all()
    )

    results: list[dict[str, Any]] = []
    for rel, src, tgt in rows:
        results.append(
            {
                "id": rel.id,
                "source_entity_id": rel.source_entity_id,
                "source_entity_name": src.canonical_name if src else None,
                "source_entity_type": src.entity_type if src else None,
                "target_entity_id": rel.target_entity_id,
                "target_entity_name": tgt.canonical_name if tgt else None,
                "target_entity_type": tgt.entity_type if tgt else None,
                "rel_type": rel.rel_type,
                "properties": rel.properties,
                "confidence": rel.confidence,
                "layer": rel.layer,
                "evidence_file_id": rel.evidence_file_id,
                "created_at": rel.created_at,
            }
        )

    return results
