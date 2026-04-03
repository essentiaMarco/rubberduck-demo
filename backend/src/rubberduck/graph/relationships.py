"""Co-occurrence based relationship extraction.

Analyzes entity mentions to find entities that co-occur in the same file,
creating relationships between them. This populates the Relationship table
so the graph visualization has edges to display.

Uses a single batch SQL query for performance on large datasets (198K+ entities).
"""

import json
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from rubberduck.db.models import Relationship

logger = logging.getLogger(__name__)

# Relationship types inferred from entity type pairs
_REL_TYPE_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("person", "person"): ("associated_with", "communications"),
    ("person", "org"): ("affiliated_with", "legal"),
    ("person", "email"): ("uses_email", "digital_activity"),
    ("person", "phone"): ("uses_phone", "communications"),
    ("person", "location"): ("located_at", "movements"),
    ("person", "ip"): ("used_ip", "digital_activity"),
    ("person", "url"): ("accessed", "digital_activity"),
    ("person", "device"): ("uses_device", "digital_activity"),
    ("person", "account"): ("owns_account", "financial"),
    ("org", "org"): ("related_to", "legal"),
    ("org", "location"): ("located_at", "movements"),
    ("org", "email"): ("uses_email", "digital_activity"),
    ("email", "email"): ("communicated_with", "communications"),
    ("email", "ip"): ("sent_from_ip", "digital_activity"),
}


def extract_cooccurrence_relationships(
    db: Session,
    *,
    min_cooccurrences: int = 2,
    max_pairs: int = 10000,
    max_mentions_per_file: int = 500,
) -> dict:
    """Build relationships from entity co-occurrence within files.

    Uses a two-phase approach to avoid the quadratic self-join blowup:
    1. Pre-filter to only files with a manageable number of mentions
    2. Run the self-join on this reduced set

    Parameters
    ----------
    db:
        SQLAlchemy session.
    min_cooccurrences:
        Minimum shared files for a pair to create a relationship.
    max_pairs:
        Maximum relationship pairs to create.
    max_mentions_per_file:
        Skip files with more mentions than this (hub files create
        billions of pairs and are uninformative).
    """
    logger.info(
        "Starting co-occurrence extraction (min_cooccurrences=%d, max_mentions_per_file=%d)",
        min_cooccurrences, max_mentions_per_file,
    )

    # Step 1: Find co-occurring entity pairs.
    # Key optimization: exclude files with too many mentions (hub files).
    # A file with 70K mentions would produce 2.5B pair comparisons.
    cooccurrence_sql = text("""
        WITH filtered_mentions AS (
            SELECT em.entity_id, em.file_id
            FROM entity_mentions em
            JOIN entities e ON e.id = em.entity_id
            WHERE e.entity_type IN ('person', 'org', 'email', 'phone', 'ip', 'location', 'device', 'account')
              AND em.file_id IN (
                  SELECT file_id FROM entity_mentions
                  GROUP BY file_id
                  HAVING COUNT(*) <= :max_mentions_per_file
              )
        )
        SELECT
            a.entity_id AS entity_a,
            b.entity_id AS entity_b,
            COUNT(DISTINCT a.file_id) AS shared_files,
            MIN(a.file_id) AS sample_file_id
        FROM filtered_mentions a
        JOIN filtered_mentions b
            ON a.file_id = b.file_id
            AND a.entity_id < b.entity_id
        GROUP BY a.entity_id, b.entity_id
        HAVING COUNT(DISTINCT a.file_id) >= :min_cooccurrences
        ORDER BY shared_files DESC
        LIMIT :max_pairs
    """)

    logger.info("Executing co-occurrence query (excluding files with >%d mentions)...", max_mentions_per_file)
    rows = db.execute(cooccurrence_sql, {
        "min_cooccurrences": min_cooccurrences,
        "max_pairs": max_pairs,
        "max_mentions_per_file": max_mentions_per_file,
    }).fetchall()
    logger.info("Found %d co-occurring entity pairs", len(rows))

    if not rows:
        return {"relationships_created": 0, "pairs_evaluated": 0, "skipped_hub_files": 0}

    # Step 2: Get entity types for involved entities
    entity_ids = set()
    for r in rows:
        entity_ids.add(r[0])
        entity_ids.add(r[1])

    # Batch fetch in chunks (SQLite has a parameter limit)
    entity_types = {}
    id_list = list(entity_ids)
    CHUNK = 500
    for start in range(0, len(id_list), CHUNK):
        chunk = id_list[start : start + CHUNK]
        placeholders = ", ".join([f":id_{i}" for i in range(len(chunk))])
        params = {f"id_{i}": eid for i, eid in enumerate(chunk)}
        type_rows = db.execute(
            text(f"SELECT id, entity_type FROM entities WHERE id IN ({placeholders})"),
            params,
        ).fetchall()
        for r in type_rows:
            entity_types[r[0]] = r[1]

    # Step 3: Check existing relationships via SQL (NOT loaded into Python memory).
    # Use INSERT ... WHERE NOT EXISTS pattern instead of loading 2M+ rows.

    # Step 4: Create Relationship records, skipping existing via SQL check
    relationships_created = 0
    skipped_existing = 0

    for row in rows:
        entity_a, entity_b, shared_file_count, sample_file_id = row[0], row[1], row[2], row[3]

        # Check if relationship exists via quick SQL instead of huge in-memory set
        exists = db.execute(
            text("""
                SELECT 1 FROM relationships
                WHERE (source_entity_id = :a AND target_entity_id = :b)
                   OR (source_entity_id = :b AND target_entity_id = :a)
                LIMIT 1
            """),
            {"a": entity_a, "b": entity_b},
        ).fetchone()

        if exists:
            skipped_existing += 1
            continue

        type_a = entity_types.get(entity_a, "other")
        type_b = entity_types.get(entity_b, "other")

        rel_info = _REL_TYPE_MAP.get((type_a, type_b))
        if rel_info is None:
            rel_info = _REL_TYPE_MAP.get((type_b, type_a))
            if rel_info is None:
                rel_info = ("co_occurs_with", "digital_activity")

        rel_type, layer = rel_info
        confidence = min(1.0, 0.3 + 0.05 * shared_file_count)

        rel = Relationship(
            id=str(uuid.uuid4()),
            source_entity_id=entity_a,
            target_entity_id=entity_b,
            rel_type=rel_type,
            properties=json.dumps({"cooccurrence_count": shared_file_count}),
            evidence_file_id=sample_file_id,
            confidence=confidence,
            layer=layer,
        )
        db.add(rel)
        relationships_created += 1

        if relationships_created % 500 == 0:
            db.flush()
            logger.info("Created %d relationships so far...", relationships_created)

    db.commit()

    logger.info(
        "Relationship extraction complete: %d created, %d skipped existing, %d pairs evaluated",
        relationships_created, skipped_existing, len(rows),
    )

    return {
        "relationships_created": relationships_created,
        "skipped_existing": skipped_existing,
        "pairs_evaluated": len(rows),
    }
