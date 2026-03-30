"""DuckDB connection manager for analytical queries over Parquet files."""

import duckdb

from rubberduck.config import settings


def get_duckdb() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection configured for our Parquet data."""
    conn = duckdb.connect(str(settings.duckdb_path))
    # Register convenient views over Parquet directories
    parquet_dir = settings.parquet_dir
    events_path = str(parquet_dir / "events" / "*.parquet")
    comms_path = str(parquet_dir / "communications" / "*.parquet")

    conn.execute(f"""
        CREATE OR REPLACE VIEW events AS
        SELECT * FROM read_parquet('{events_path}', union_by_name=true, hive_partitioning=false)
    """)
    conn.execute(f"""
        CREATE OR REPLACE VIEW communications AS
        SELECT * FROM read_parquet('{comms_path}', union_by_name=true, hive_partitioning=false)
    """)
    return conn


def query_events(
    conn: duckdb.DuckDBPyConnection,
    *,
    start: str | None = None,
    end: str | None = None,
    event_types: list[str] | None = None,
    entity_ids: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Query timeline events with filters. Returns list of dicts."""
    conditions = []
    params = []

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

    sql = f"""
        SELECT * FROM events
        {where}
        ORDER BY timestamp_utc
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    try:
        result = conn.execute(sql, params)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except duckdb.IOException:
        # No parquet files yet
        return []
