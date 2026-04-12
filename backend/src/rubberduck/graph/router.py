"""API routes for graph exploration and analysis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from rubberduck.db.sqlite import get_db
from rubberduck.graph import service as graph_service
from rubberduck.graph.analyzer import analyze
from rubberduck.graph.builder import build_graph
from rubberduck.graph.relationships import extract_cooccurrence_relationships
from rubberduck.jobs.manager import job_manager
from rubberduck.schemas.graph import (
    GraphAnalysis,
    GraphData,
    GraphExportRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("", response_model=GraphData)
@router.get("/", response_model=GraphData)
def get_full_graph(
    layers: list[str] | None = Query(None, description="Filter by relationship layers"),
    entity_types: list[str] | None = Query(None, description="Filter by entity types"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
    limit: int = Query(500, ge=1, le=5000, description="Max nodes to return"),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return the full entity relationship graph with optional filtering."""
    return graph_service.get_full_graph(
        db,
        layers=layers,
        entity_types=entity_types,
        min_confidence=min_confidence,
        limit=limit,
        date_start=date_start,
        date_end=date_end,
    )


@router.get("/neighborhood/{entity_id}", response_model=GraphData)
def get_neighborhood(
    entity_id: str,
    depth: int = Query(2, ge=1, le=5, description="Number of hops"),
    layers: list[str] | None = Query(None, description="Filter by relationship layers"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
    db: Session = Depends(get_db),
):
    """Return the N-hop neighborhood around a specific entity."""
    result = graph_service.get_neighborhood(
        db,
        entity_id,
        depth=depth,
        layers=layers,
        min_confidence=min_confidence,
    )
    if result.node_count == 0:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id!r} not found in graph")
    return result


@router.get("/path")
def get_shortest_path(
    source: str = Query(..., description="Source entity ID"),
    target: str = Query(..., description="Target entity ID"),
    db: Session = Depends(get_db),
):
    """Find the shortest path between two entities."""
    try:
        path = graph_service.get_shortest_path(db, source, target)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"path": path, "length": len(path) - 1}


@router.get("/analysis", response_model=GraphAnalysis)
def get_analysis(
    layers: list[str] | None = Query(None, description="Filter by relationship layers"),
    entity_types: list[str] | None = Query(None, description="Filter by entity types"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
    db: Session = Depends(get_db),
):
    """Run graph analysis: centrality, communities, bridges, isolated nodes."""
    G = build_graph(db, layers=layers, entity_types=entity_types, min_confidence=min_confidence)
    return analyze(G)


@router.post("/build-relationships")
def build_relationships(db: Session = Depends(get_db)):
    """Trigger co-occurrence relationship extraction as a background job.

    Analyzes entity mentions to find entities that co-occur in the same file,
    and creates Relationship records. This populates the graph with edges.
    """
    def _build_job(thread_db: Session, job_id: str) -> dict:
        return extract_cooccurrence_relationships(thread_db)

    job_id = job_manager.submit(db, "build_relationships", _build_job, params={})
    return {"job_id": job_id, "message": "Relationship extraction started"}


@router.post("/export")
def export_graph(
    body: GraphExportRequest,
    db: Session = Depends(get_db),
):
    """Export the graph as GraphML, CSV, or JSON and return the file."""
    try:
        path = graph_service.export_graph(
            db,
            format=body.format,
            layers=body.layers,
            entity_types=body.entity_types,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Map format to MIME type
    media_types = {
        "graphml": "application/xml",
        "csv": "text/csv",
        "json": "application/json",
    }
    return FileResponse(
        path,
        filename=path.name,
        media_type=media_types.get(body.format, "application/octet-stream"),
    )
