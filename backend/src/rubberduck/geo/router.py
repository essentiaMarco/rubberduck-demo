"""API routes for geospatial intelligence."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from rubberduck.db.sqlite import get_db
from rubberduck.geo import service as geo_service

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/locations")
def list_locations(
    entity_id: str | None = Query(None),
    source_type: str | None = Query(None),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """List all geographic locations with optional filters."""
    return geo_service.get_locations(
        db, entity_id=entity_id, source_type=source_type,
        date_start=date_start, date_end=date_end, limit=limit,
    )


@router.get("/locations/radius")
def radius_search(
    lat: float = Query(..., description="Center latitude"),
    lon: float = Query(..., description="Center longitude"),
    radius_km: float = Query(5.0, description="Search radius in kilometers"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Find locations within a radius of a given point."""
    return geo_service.radius_search(db, lat, lon, radius_km, limit)


@router.get("/heatmap")
def get_heatmap(db: Session = Depends(get_db)):
    """Location density data for heatmap rendering."""
    return geo_service.get_heatmap_data(db)


@router.get("/tracks/{entity_id}")
def get_track(entity_id: str, db: Session = Depends(get_db)):
    """Movement track as GeoJSON LineString for an entity."""
    return geo_service.get_movement_track(db, entity_id)


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Geolocation statistics."""
    return geo_service.get_stats(db)


@router.post("/extract")
def extract_locations(db: Session = Depends(get_db)):
    """Extract location data from all parsed evidence files."""
    return geo_service.extract_locations_from_evidence(db)
