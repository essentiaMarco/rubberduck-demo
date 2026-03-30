"""Schemas for graph exploration and analysis."""

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    entity_type: str
    properties: dict = Field(default_factory=dict)
    degree: int = 0


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    rel_type: str
    weight: float = 1.0
    layer: str | None = None
    evidence_file_id: str | None = None


class GraphData(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_count: int = 0
    edge_count: int = 0


class GraphNeighborhoodRequest(BaseModel):
    entity_id: str
    depth: int = Field(2, ge=1, le=5)
    layers: list[str] | None = None
    min_confidence: float = 0.0


class GraphAnalysis(BaseModel):
    centrality: dict[str, float] = {}
    communities: list[list[str]] = []
    bridges: list[str] = []
    isolated: list[str] = []


class GraphExportRequest(BaseModel):
    format: str = "graphml"  # graphml, csv, json
    layers: list[str] | None = None
    entity_types: list[str] | None = None
