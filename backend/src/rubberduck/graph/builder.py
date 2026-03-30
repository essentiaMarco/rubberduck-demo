"""Graph builder — constructs a NetworkX graph from SQLAlchemy entity and relationship data."""

from __future__ import annotations

import json
import logging

import networkx as nx
from sqlalchemy.orm import Session

from rubberduck.db.models import Entity, Relationship

logger = logging.getLogger(__name__)


def build_graph(
    db: Session,
    *,
    layers: list[str] | None = None,
    entity_types: list[str] | None = None,
    min_confidence: float = 0.0,
) -> nx.Graph:
    """Build a NetworkX graph from the database.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    layers:
        If provided, include only relationships whose ``layer`` is in this list.
    entity_types:
        If provided, include only entities whose ``entity_type`` is in this list.
    min_confidence:
        Minimum confidence threshold for relationships (0.0 to 1.0).

    Returns
    -------
    networkx.Graph with entity nodes and relationship edges.
    """
    G = nx.Graph()

    # ── Load entities (nodes) ─────────────────────────────────
    entity_query = db.query(Entity)
    if entity_types:
        entity_query = entity_query.filter(Entity.entity_type.in_(entity_types))

    entities_by_id: dict[str, Entity] = {}
    for entity in entity_query.all():
        properties = _parse_json(entity.properties)
        G.add_node(
            entity.id,
            label=entity.canonical_name,
            entity_type=entity.entity_type,
            properties=properties,
        )
        entities_by_id[entity.id] = entity

    # ── Load relationships (edges) ────────────────────────────
    rel_query = db.query(Relationship)
    if layers:
        rel_query = rel_query.filter(Relationship.layer.in_(layers))
    if min_confidence > 0.0:
        rel_query = rel_query.filter(Relationship.confidence >= min_confidence)

    for rel in rel_query.all():
        source_id = rel.source_entity_id
        target_id = rel.target_entity_id

        # Skip edges where one endpoint was filtered out
        if source_id not in G or target_id not in G:
            # If entity_types filtering removed one side, add it back only if
            # we are not filtering by entity type (i.e., layers-only filter)
            if entity_types:
                continue
            # Ensure both endpoints exist as nodes
            for eid in (source_id, target_id):
                if eid not in G:
                    ent = entities_by_id.get(eid) or db.query(Entity).get(eid)
                    if ent is None:
                        continue
                    G.add_node(
                        ent.id,
                        label=ent.canonical_name,
                        entity_type=ent.entity_type,
                        properties=_parse_json(ent.properties),
                    )

        if source_id in G and target_id in G:
            G.add_edge(
                source_id,
                target_id,
                id=rel.id,
                rel_type=rel.rel_type,
                weight=rel.confidence or 1.0,
                layer=rel.layer,
                evidence_file_id=rel.evidence_file_id,
            )

    logger.info(
        "Built graph with %d nodes and %d edges (layers=%s, entity_types=%s, min_confidence=%.2f)",
        G.number_of_nodes(),
        G.number_of_edges(),
        layers,
        entity_types,
        min_confidence,
    )
    return G


def _parse_json(value: str | None) -> dict:
    """Safely parse a JSON string, returning an empty dict on failure."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
