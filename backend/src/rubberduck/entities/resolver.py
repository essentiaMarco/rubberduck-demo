"""Entity resolution — match extracted mentions to canonical entities.

For each mention, normalize the surface text, look up existing aliases,
and either link to an existing entity or create a new one.
"""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import Entity, EntityAlias, EntityMention

logger = logging.getLogger(__name__)

# Characters to strip beyond normal whitespace
_STRIP_CHARS = "\t\n\r\x0b\x0c"


def _normalize(text: str, entity_type: str) -> str:
    """Produce a canonical comparison form for a mention.

    - General: lowercase, collapse whitespace, strip.
    - email: lowercase entire string.
    - phone: digits only (strip formatting).
    """
    text = text.strip(_STRIP_CHARS).strip()

    if entity_type == "email":
        return text.lower()

    if entity_type == "phone":
        digits = re.sub(r"\D", "", text)
        # Normalize US numbers: strip leading 1 if 11 digits
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits

    # Default normalization
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _context_snippet(text: str | None, offset: int | None, window: int = 80) -> str | None:
    """Extract a context window around a mention for provenance."""
    if text is None or offset is None:
        return None
    start = max(0, offset - window)
    end = min(len(text), offset + window)
    return text[start:end]


def resolve_mentions(
    db: Session,
    mentions: list[dict[str, Any]],
    file_id: str,
    source_text: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve a batch of extracted mentions to Entity records.

    For each mention dict (as produced by spacy_ner or regex_extractors):
    1. Normalize the surface text.
    2. Look for an existing EntityAlias with that normalized form.
    3. If found, link the mention to the existing Entity.
    4. If not found, create a new Entity + EntityAlias + EntityMention.

    Returns a list of resolution result dicts for logging/auditing.
    """
    results: list[dict[str, Any]] = []

    for mention in mentions:
        surface = mention["text"]
        entity_type = mention["entity_type"]
        normalized = _normalize(surface, entity_type)

        if not normalized:
            continue

        # Look up existing alias
        existing_alias = (
            db.query(EntityAlias)
            .join(Entity, EntityAlias.entity_id == Entity.id)
            .filter(EntityAlias.alias == normalized, Entity.entity_type == entity_type)
            .first()
        )

        if existing_alias:
            entity = existing_alias.entity
            action = "linked"
        else:
            # Create new entity
            entity = Entity(
                entity_type=entity_type,
                canonical_name=surface.strip(),
            )
            db.add(entity)
            db.flush()  # get entity.id

            # Create the alias
            alias = EntityAlias(
                entity_id=entity.id,
                alias=normalized,
                alias_type=_alias_type_for(entity_type),
                confidence=mention.get("confidence", 1.0),
            )
            db.add(alias)
            action = "created"

        # Create the mention record
        context = _context_snippet(source_text, mention.get("char_offset"))
        em = EntityMention(
            entity_id=entity.id,
            file_id=file_id,
            extractor=mention.get("extractor", "unknown"),
            mention_text=surface,
            context_snippet=context,
            char_offset=mention.get("char_offset"),
            confidence=mention.get("confidence", 1.0),
        )
        db.add(em)

        results.append(
            {
                "entity_id": entity.id,
                "entity_type": entity_type,
                "canonical_name": entity.canonical_name,
                "mention_text": surface,
                "action": action,
            }
        )

    db.commit()
    return results


def _alias_type_for(entity_type: str) -> str:
    """Map entity type to a default alias type."""
    mapping = {
        "email": "email_variant",
        "phone": "phone_variant",
        "person": "name",
        "org": "name",
        "location": "name",
        "ip": "address",
        "url": "url",
        "device": "name",
    }
    return mapping.get(entity_type, "name")
