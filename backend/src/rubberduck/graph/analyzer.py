"""Graph analysis — centrality, community detection, bridge identification."""

from __future__ import annotations

import logging

import networkx as nx

logger = logging.getLogger(__name__)


def analyze(G: nx.Graph) -> dict:
    """Run a suite of graph analyses.

    Parameters
    ----------
    G:
        A NetworkX graph (undirected).

    Returns
    -------
    dict with keys:
        centrality  – degree centrality scores keyed by node ID
        communities – list of communities (each a list of node IDs)
        bridges     – list of bridge edge tuples (as node ID pairs)
        isolated    – list of isolated node IDs (degree 0)
    """
    result: dict = {
        "centrality": {},
        "communities": [],
        "bridges": [],
        "isolated": [],
    }

    if G.number_of_nodes() == 0:
        return result

    # ── Degree centrality ─────────────────────────────────────
    result["centrality"] = nx.degree_centrality(G)

    # ── Community detection ───────────────────────────────────
    # greedy_modularity_communities requires at least one edge
    if G.number_of_edges() > 0:
        try:
            communities = nx.community.greedy_modularity_communities(G)
            result["communities"] = [sorted(c) for c in communities]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Community detection failed: %s", exc)
            result["communities"] = []
    else:
        # Each connected component (isolated node) is its own community
        result["communities"] = [sorted(c) for c in nx.connected_components(G)]

    # ── Bridges ───────────────────────────────────────────────
    # Bridges are edges whose removal disconnects the graph
    if G.number_of_edges() > 0:
        try:
            result["bridges"] = [
                {"source": u, "target": v} for u, v in nx.bridges(G)
            ]
        except nx.NetworkXError:
            # bridges() only works on undirected graphs; should not happen here
            result["bridges"] = []

    # ── Isolated nodes ────────────────────────────────────────
    result["isolated"] = sorted(nx.isolates(G))

    logger.info(
        "Graph analysis: %d nodes, %d edges, %d communities, %d bridges, %d isolated",
        G.number_of_nodes(),
        G.number_of_edges(),
        len(result["communities"]),
        len(result["bridges"]),
        len(result["isolated"]),
    )
    return result
