"""Graph service — high-level operations for graph querying, analysis, and export."""

from __future__ import annotations

import csv
import json
import logging
import uuid
from io import StringIO
from pathlib import Path

import networkx as nx
from sqlalchemy.orm import Session

from rubberduck.config import settings
from rubberduck.db.models import Entity
from rubberduck.graph.analyzer import analyze
from rubberduck.graph.builder import build_graph
from rubberduck.schemas.graph import GraphData, GraphEdge, GraphNode

logger = logging.getLogger(__name__)


def get_full_graph(
    db: Session,
    *,
    layers: list[str] | None = None,
    entity_types: list[str] | None = None,
    min_confidence: float = 0.0,
    limit: int = 500,
) -> GraphData:
    """Build and return the full graph, optionally truncated to *limit* nodes.

    Nodes are kept in descending order of degree so the most connected
    entities are always included when the graph is truncated.
    """
    G = build_graph(db, layers=layers, entity_types=entity_types, min_confidence=min_confidence)
    return _graph_to_data(G, limit=limit)


def get_neighborhood(
    db: Session,
    entity_id: str,
    *,
    depth: int = 2,
    layers: list[str] | None = None,
    min_confidence: float = 0.0,
) -> GraphData:
    """Return the N-hop neighborhood of a specific entity."""
    G = build_graph(db, layers=layers, min_confidence=min_confidence)

    if entity_id not in G:
        return GraphData()

    # Collect all nodes within *depth* hops
    neighborhood_nodes = {entity_id}
    frontier = {entity_id}
    for _ in range(depth):
        next_frontier: set[str] = set()
        for node in frontier:
            for neighbor in G.neighbors(node):
                if neighbor not in neighborhood_nodes:
                    next_frontier.add(neighbor)
                    neighborhood_nodes.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    subgraph = G.subgraph(neighborhood_nodes).copy()
    return _graph_to_data(subgraph)


def get_shortest_path(
    db: Session,
    source_id: str,
    target_id: str,
) -> list[str]:
    """Return the shortest path (list of entity IDs) between two entities.

    Raises ``ValueError`` if no path exists or either entity is missing.
    """
    G = build_graph(db)

    if source_id not in G:
        raise ValueError(f"Source entity {source_id!r} not found in graph")
    if target_id not in G:
        raise ValueError(f"Target entity {target_id!r} not found in graph")

    try:
        return nx.shortest_path(G, source=source_id, target=target_id)
    except nx.NetworkXNoPath:
        raise ValueError(
            f"No path between {source_id!r} and {target_id!r}"
        ) from None


def export_graph(
    db: Session,
    *,
    format: str = "graphml",
    layers: list[str] | None = None,
    entity_types: list[str] | None = None,
) -> Path:
    """Export the graph to a file and return the file path.

    Supported formats: ``graphml``, ``csv``, ``json``.
    """
    G = build_graph(db, layers=layers, entity_types=entity_types)
    exports_dir = settings.exports_dir / "graph"
    exports_dir.mkdir(parents=True, exist_ok=True)

    export_id = str(uuid.uuid4())[:8]

    if format == "graphml":
        path = exports_dir / f"graph_{export_id}.graphml"
        # NetworkX graphml writer needs all attributes to be simple types
        _sanitize_for_graphml(G)
        nx.write_graphml(G, str(path))

    elif format == "csv":
        path = exports_dir / f"graph_{export_id}.csv"
        _export_csv(G, path)

    elif format == "json":
        path = exports_dir / f"graph_{export_id}.json"
        _export_json(G, path)

    else:
        raise ValueError(f"Unsupported export format: {format!r}")

    logger.info("Exported graph (%d nodes, %d edges) to %s", G.number_of_nodes(), G.number_of_edges(), path)
    return path


# ── Internal helpers ──────────────────────────────────────────


def _graph_to_data(G: nx.Graph, limit: int | None = None) -> GraphData:
    """Convert a NetworkX graph to the ``GraphData`` schema."""
    # Optionally limit by top-degree nodes
    if limit and G.number_of_nodes() > limit:
        top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:limit]
        G = G.subgraph(top_nodes).copy()

    nodes = []
    for node_id, attrs in G.nodes(data=True):
        nodes.append(
            GraphNode(
                id=node_id,
                label=attrs.get("label", str(node_id)),
                entity_type=attrs.get("entity_type", "unknown"),
                properties=attrs.get("properties", {}),
                degree=G.degree(node_id),
            )
        )

    edges = []
    for u, v, attrs in G.edges(data=True):
        edges.append(
            GraphEdge(
                id=attrs.get("id", f"{u}-{v}"),
                source=u,
                target=v,
                rel_type=attrs.get("rel_type", "related"),
                weight=attrs.get("weight", 1.0),
                layer=attrs.get("layer"),
                evidence_file_id=attrs.get("evidence_file_id"),
            )
        )

    return GraphData(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


def _sanitize_for_graphml(G: nx.Graph) -> None:
    """Ensure all node/edge attributes are GraphML-compatible (strings, ints, floats)."""
    for _, attrs in G.nodes(data=True):
        for key, val in list(attrs.items()):
            if isinstance(val, dict):
                attrs[key] = json.dumps(val)
            elif not isinstance(val, (str, int, float, bool)):
                attrs[key] = str(val)

    for _, _, attrs in G.edges(data=True):
        for key, val in list(attrs.items()):
            if isinstance(val, dict):
                attrs[key] = json.dumps(val)
            elif not isinstance(val, (str, int, float, bool)):
                attrs[key] = str(val)


def _export_csv(G: nx.Graph, path: Path) -> None:
    """Export edges as CSV with source/target labels."""
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["source_id", "source_label", "target_id", "target_label", "rel_type", "weight", "layer"])

    for u, v, attrs in G.edges(data=True):
        writer.writerow([
            u,
            G.nodes[u].get("label", u),
            v,
            G.nodes[v].get("label", v),
            attrs.get("rel_type", ""),
            attrs.get("weight", 1.0),
            attrs.get("layer", ""),
        ])

    path.write_text(buf.getvalue(), encoding="utf-8")


def _export_json(G: nx.Graph, path: Path) -> None:
    """Export graph as a JSON document with nodes and edges."""
    data = _graph_to_data(G)
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
