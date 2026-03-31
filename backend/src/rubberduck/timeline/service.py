"""Timeline service — event ingestion, Parquet storage, and DuckDB queries."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rubberduck.config import settings
from rubberduck.db.duckdb_conn import get_duckdb, query_events
from rubberduck.timeline.normalizer import normalize

logger = logging.getLogger(__name__)

# Arrow schema for timeline events
_EVENT_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string()),
        pa.field("case_id", pa.string()),
        pa.field("file_id", pa.string()),
        pa.field("file_name", pa.string()),
        pa.field("event_type", pa.string()),
        pa.field("event_subtype", pa.string()),
        pa.field("timestamp_utc", pa.string()),
        pa.field("timestamp_orig", pa.string()),
        pa.field("timezone_orig", pa.string()),
        pa.field("actor_entity_id", pa.string()),
        pa.field("actor_name", pa.string()),
        pa.field("target_entity_id", pa.string()),
        pa.field("target_name", pa.string()),
        pa.field("summary", pa.string()),
        pa.field("raw_data", pa.string()),
        pa.field("confidence", pa.float64()),
    ]
)


def process_events(
    file_id: str,
    case_id: str,
    raw_events: list[dict],
) -> dict:
    """Normalize timestamps and write events to a Parquet file.

    Parameters
    ----------
    file_id:
        Identifier for the source file that produced these events.
    case_id:
        Case the events belong to.
    raw_events:
        List of dicts, each containing at least ``timestamp`` and ``event_type``.

    Returns
    -------
    dict with ``file_id``, ``events_written``, and ``parquet_path``.
    """
    events_dir = settings.parquet_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    rows: dict[str, list] = {field.name: [] for field in _EVENT_SCHEMA}

    for raw in raw_events:
        ts_raw = raw.get("timestamp") or raw.get("timestamp_utc") or raw.get("date")
        if ts_raw is None:
            logger.warning("Skipping event without timestamp in file %s", file_id)
            continue

        norm = normalize(ts_raw)
        if norm["utc"] is None:
            logger.warning(
                "Skipping event with unparseable timestamp %r in file %s",
                ts_raw,
                file_id,
            )
            continue

        event_id = raw.get("event_id") or str(uuid.uuid4())

        rows["event_id"].append(event_id)
        rows["case_id"].append(case_id)
        rows["file_id"].append(file_id)
        rows["file_name"].append(raw.get("file_name"))
        rows["event_type"].append(raw.get("event_type", "unknown"))
        rows["event_subtype"].append(raw.get("event_subtype"))
        rows["timestamp_utc"].append(norm["utc"])
        rows["timestamp_orig"].append(norm["original"])
        rows["timezone_orig"].append(norm["timezone"])
        rows["actor_entity_id"].append(raw.get("actor_entity_id"))
        rows["actor_name"].append(raw.get("actor_name"))
        rows["target_entity_id"].append(raw.get("target_entity_id"))
        rows["target_name"].append(raw.get("target_name"))
        rows["summary"].append(raw.get("summary", ""))
        rows["raw_data"].append(
            json.dumps(raw.get("raw_data")) if raw.get("raw_data") else None
        )
        rows["confidence"].append(float(raw.get("confidence", 1.0)))

    if not rows["event_id"]:
        return {"file_id": file_id, "events_written": 0, "parquet_path": None}

    batch = pa.RecordBatch.from_pydict(rows, schema=_EVENT_SCHEMA)
    parquet_path = events_dir / f"{file_id}.parquet"
    pq.write_table(pa.Table.from_batches([batch]), str(parquet_path))

    logger.info(
        "Wrote %d events for file %s to %s",
        len(rows["event_id"]),
        file_id,
        parquet_path,
    )
    return {
        "file_id": file_id,
        "events_written": len(rows["event_id"]),
        "parquet_path": str(parquet_path),
    }


def get_events(
    *,
    start: str | None = None,
    end: str | None = None,
    event_types: list[str] | None = None,
    entity_ids: list[str] | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict:
    """Query timeline events with pagination.

    Returns a dict with ``items``, ``total``, ``page``, and ``page_size``.
    """
    conn = get_duckdb()
    try:
        offset = (page - 1) * page_size
        items = query_events(
            conn,
            start=start,
            end=end,
            event_types=event_types,
            entity_ids=entity_ids,
            limit=page_size,
            offset=offset,
        )

        # Get total count for pagination
        total = _count_events(conn, start=start, end=end, event_types=event_types, entity_ids=entity_ids)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        conn.close()


def get_stats() -> dict:
    """Return aggregate statistics over all timeline events.

    Returns
    -------
    dict with ``total_events``, ``date_range_start``, ``date_range_end``,
    ``by_type`` (dict), and ``by_day`` (list of dicts).
    """
    conn = get_duckdb()
    try:
        stats: dict = {
            "total_events": 0,
            "date_range_start": None,
            "date_range_end": None,
            "by_type": {},
            "by_day": [],
        }

        # Total events and date range
        try:
            row = conn.execute(
                "SELECT COUNT(*), MIN(timestamp_utc), MAX(timestamp_utc) FROM events"
            ).fetchone()
            if row:
                stats["total_events"] = row[0] or 0
                stats["date_range_start"] = str(row[1]) if row[1] else None
                stats["date_range_end"] = str(row[2]) if row[2] else None
        except duckdb.IOException:
            return stats

        # By type
        try:
            type_rows = conn.execute(
                "SELECT event_type, COUNT(*) AS cnt FROM events GROUP BY event_type ORDER BY cnt DESC"
            ).fetchall()
            stats["by_type"] = {r[0]: r[1] for r in type_rows}
        except duckdb.IOException:
            pass

        # By day
        try:
            day_rows = conn.execute(
                "SELECT CAST(timestamp_utc AS DATE) AS day, COUNT(*) AS cnt "
                "FROM events GROUP BY day ORDER BY day"
            ).fetchall()
            stats["by_day"] = [{"date": str(r[0]), "count": r[1]} for r in day_rows]
        except duckdb.IOException:
            pass

        return stats
    finally:
        conn.close()


def rebuild() -> dict:
    """Re-derive the full timeline from all parsed files' events.json.

    Scans the parsed data directory for ``events.json`` files, processes them,
    and rewrites the Parquet event store.

    Returns
    -------
    dict with ``files_processed`` and ``total_events``.
    """
    parsed_dir = settings.parsed_dir
    events_dir = settings.parquet_dir / "events"

    # Clear existing event parquet files
    if events_dir.exists():
        for pf in events_dir.glob("*.parquet"):
            pf.unlink()

    files_processed = 0
    total_events = 0

    for events_file in sorted(parsed_dir.rglob("events.json")):
        try:
            data = json.loads(events_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable events file %s: %s", events_file, exc)
            continue

        # Derive file_id and case_id from the directory structure
        # Expected: parsed/<file_id>/events.json
        file_id = events_file.parent.name

        # Look up case_id from database
        from rubberduck.db.sqlite import SessionLocal
        from rubberduck.db.models import File, EvidenceSource

        db = SessionLocal()
        try:
            file_rec = db.query(File).get(file_id)
            if file_rec:
                source = db.query(EvidenceSource).get(file_rec.source_id)
                case_id = source.case_id if source else "unknown"
            else:
                case_id = "unknown"
        finally:
            db.close()

        # events.json from parsers is always a list; handle dict as fallback
        if isinstance(data, list):
            events_list = data
        elif isinstance(data, dict):
            events_list = data.get("events", [])
        else:
            logger.warning("Unexpected events.json format in %s", events_file)
            continue

        result = process_events(file_id, case_id, events_list)
        files_processed += 1
        total_events += result.get("events_written", 0)

    logger.info("Timeline rebuild complete: %d files, %d events", files_processed, total_events)
    return {"files_processed": files_processed, "total_events": total_events}


# ── Internal helpers ──────────────────────────────────────────


def _count_events(
    conn: duckdb.DuckDBPyConnection,
    *,
    start: str | None = None,
    end: str | None = None,
    event_types: list[str] | None = None,
    entity_ids: list[str] | None = None,
) -> int:
    """Count events matching the given filters."""
    conditions: list[str] = []
    params: list = []

    if start:
        conditions.append("timestamp_utc >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp_utc <= ?")
        params.append(end)
    if event_types:
        placeholders = ", ".join(["?"] * len(event_types))
        conditions.append(f"event_type IN ({placeholders})")
        params.extend(event_types)
    if entity_ids:
        placeholders = ", ".join(["?"] * len(entity_ids))
        conditions.append(
            f"(actor_entity_id IN ({placeholders}) OR target_entity_id IN ({placeholders}))"
        )
        params.extend(entity_ids)
        params.extend(entity_ids)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT COUNT(*) FROM events {where}"

    try:
        result = conn.execute(sql, params).fetchone()
        return result[0] if result else 0
    except duckdb.IOException:
        return 0
