"""Geospatial service — location extraction, movement tracks, spatial queries."""

import json
import logging
import math
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.db.models import File, GeoLocation

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in kilometers."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def extract_locations_from_evidence(db: Session) -> dict[str, Any]:
    """Scan all parsed evidence for location data and persist GeoLocation records.

    Sources:
    - Image EXIF GPS data (events.json with event_type=location, event_subtype=photo_gps)
    - Google Takeout Location History (events.json with event_subtype=gps_checkin)
    """
    from pathlib import Path

    files = (
        db.query(File)
        .filter(File.parse_status == "completed", File.parsed_path.isnot(None))
        .all()
    )

    stats = {"files_scanned": 0, "locations_extracted": 0, "errors": 0}
    existing_file_ids = {r[0] for r in db.query(GeoLocation.file_id).distinct().all()}

    for f in files:
        if f.id in existing_file_ids:
            continue

        events_path = Path(f.parsed_path) / "events.json"
        if not events_path.exists():
            continue

        stats["files_scanned"] += 1
        try:
            events = json.loads(events_path.read_text(encoding="utf-8"))
            for event in events:
                raw = event.get("raw_data") or {}
                lat = raw.get("lat")
                lon = raw.get("lon")
                if lat is None or lon is None:
                    continue

                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                except (ValueError, TypeError):
                    continue

                # Skip invalid coordinates
                if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                    continue

                source_type = "unknown"
                subtype = event.get("event_subtype", "")
                if subtype == "photo_gps":
                    source_type = "photo_exif"
                elif subtype == "gps_checkin":
                    source_type = "google_location_history"

                # Parse timestamp
                ts = None
                ts_raw = event.get("timestamp_raw", "")
                if ts_raw:
                    try:
                        from rubberduck.timeline.normalizer import normalize
                        normalized = normalize(ts_raw)
                        if normalized.get("utc"):
                            ts = datetime.fromisoformat(normalized["utc"])
                    except Exception:
                        pass

                loc = GeoLocation(
                    file_id=f.id,
                    latitude=lat_f,
                    longitude=lon_f,
                    accuracy_meters=raw.get("accuracy"),
                    timestamp=ts,
                    source_type=source_type,
                    label=event.get("summary", ""),
                    raw_data=json.dumps(raw),
                )
                db.add(loc)
                stats["locations_extracted"] += 1

        except (json.JSONDecodeError, OSError) as e:
            stats["errors"] += 1

    if stats["locations_extracted"]:
        db.commit()

    return stats


def get_locations(
    db: Session,
    *,
    entity_id: str | None = None,
    source_type: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Query locations with optional filters."""
    q = db.query(GeoLocation)
    if entity_id:
        q = q.filter(GeoLocation.entity_id == entity_id)
    if source_type:
        q = q.filter(GeoLocation.source_type == source_type)
    if date_start:
        q = q.filter(GeoLocation.timestamp >= date_start)
    if date_end:
        q = q.filter(GeoLocation.timestamp <= date_end)

    locations = q.order_by(GeoLocation.timestamp.asc().nullslast()).limit(limit).all()
    return [_loc_dict(loc) for loc in locations]


def radius_search(
    db: Session,
    lat: float,
    lon: float,
    radius_km: float,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Find all locations within a radius of a given point.

    Uses bounding box pre-filter then Haversine for accuracy.
    """
    # Bounding box pre-filter (rough, fast)
    lat_delta = radius_km / 111.0  # ~111 km per degree latitude
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))

    candidates = (
        db.query(GeoLocation)
        .filter(
            GeoLocation.latitude.between(lat - lat_delta, lat + lat_delta),
            GeoLocation.longitude.between(lon - lon_delta, lon + lon_delta),
        )
        .limit(limit * 5)  # over-fetch for Haversine filtering
        .all()
    )

    results = []
    for loc in candidates:
        dist = haversine_km(lat, lon, loc.latitude, loc.longitude)
        if dist <= radius_km:
            d = _loc_dict(loc)
            d["distance_km"] = round(dist, 3)
            results.append(d)

    results.sort(key=lambda x: x["distance_km"])
    return results[:limit]


def get_heatmap_data(db: Session, grid_size: float = 0.01) -> list[dict[str, Any]]:
    """Return location density data for heatmap rendering.

    Groups locations into grid cells and returns [lat, lon, weight].
    """
    locations = db.query(GeoLocation.latitude, GeoLocation.longitude).all()
    if not locations:
        return []

    grid: dict[tuple[float, float], int] = {}
    for lat, lon in locations:
        cell = (round(lat / grid_size) * grid_size, round(lon / grid_size) * grid_size)
        grid[cell] = grid.get(cell, 0) + 1

    return [
        {"lat": lat, "lon": lon, "weight": count}
        for (lat, lon), count in sorted(grid.items(), key=lambda x: -x[1])[:2000]
    ]


def get_movement_track(db: Session, entity_id: str) -> dict[str, Any]:
    """Build a GeoJSON LineString for an entity's movement over time."""
    locations = (
        db.query(GeoLocation)
        .filter(GeoLocation.entity_id == entity_id, GeoLocation.timestamp.isnot(None))
        .order_by(GeoLocation.timestamp.asc())
        .all()
    )

    if not locations:
        return {"type": "FeatureCollection", "features": []}

    coordinates = [[loc.longitude, loc.latitude] for loc in locations]
    timestamps = [loc.timestamp.isoformat() if loc.timestamp else None for loc in locations]

    feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "entity_id": entity_id,
            "point_count": len(coordinates),
            "timestamps": timestamps,
            "start": timestamps[0],
            "end": timestamps[-1],
        },
    }

    return {"type": "FeatureCollection", "features": [feature]}


def get_stats(db: Session) -> dict[str, Any]:
    """Geolocation statistics."""
    total = db.query(GeoLocation).count()
    by_source = dict(
        db.query(GeoLocation.source_type, func.count())
        .group_by(GeoLocation.source_type).all()
    )
    date_min = db.query(func.min(GeoLocation.timestamp)).scalar()
    date_max = db.query(func.max(GeoLocation.timestamp)).scalar()

    return {
        "total_locations": total,
        "by_source": by_source,
        "date_range": {
            "start": str(date_min) if date_min else None,
            "end": str(date_max) if date_max else None,
        },
    }


def _loc_dict(loc: GeoLocation) -> dict[str, Any]:
    return {
        "id": loc.id,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "altitude": loc.altitude,
        "accuracy_meters": loc.accuracy_meters,
        "timestamp": loc.timestamp.isoformat() if loc.timestamp else None,
        "source_type": loc.source_type,
        "label": loc.label,
        "entity_id": loc.entity_id,
        "file_id": loc.file_id,
    }
