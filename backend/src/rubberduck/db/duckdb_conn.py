"""DuckDB connection manager for analytical queries over Parquet files."""

import logging

import duckdb

from rubberduck.config import settings

logger = logging.getLogger(__name__)


def get_duckdb() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection configured for our Parquet data.

    Gracefully handles the case where Parquet directories are empty or
    missing — this is normal before the first timeline rebuild.
    """
    conn = duckdb.connect(str(settings.duckdb_path))
    parquet_dir = settings.parquet_dir
    events_path = str(parquet_dir / "events" / "*.parquet")
    comms_path = str(parquet_dir / "communications" / "*.parquet")

    # Register views only if matching parquet files exist.
    # DuckDB throws IOException when the glob matches zero files.
    try:
        conn.execute("""
            CREATE OR REPLACE VIEW events AS
            SELECT * FROM read_parquet($1, union_by_name=true, hive_partitioning=false)
        """, [events_path])
    except duckdb.IOException:
        logger.debug("No event parquet files found at %s — creating empty events view", events_path)
        conn.execute("""
            CREATE OR REPLACE VIEW events AS
            SELECT
                NULL::VARCHAR AS event_id,
                NULL::VARCHAR AS case_id,
                NULL::VARCHAR AS file_id,
                NULL::VARCHAR AS file_name,
                NULL::VARCHAR AS event_type,
                NULL::VARCHAR AS event_subtype,
                NULL::VARCHAR AS timestamp_utc,
                NULL::VARCHAR AS timestamp_orig,
                NULL::VARCHAR AS timezone_orig,
                NULL::VARCHAR AS actor_entity_id,
                NULL::VARCHAR AS actor_name,
                NULL::VARCHAR AS target_entity_id,
                NULL::VARCHAR AS target_name,
                NULL::VARCHAR AS summary,
                NULL::VARCHAR AS raw_data,
                NULL::DOUBLE  AS confidence
            WHERE false
        """)

    try:
        conn.execute("""
            CREATE OR REPLACE VIEW communications AS
            SELECT * FROM read_parquet($1, union_by_name=true, hive_partitioning=false)
        """, [comms_path])
    except duckdb.IOException:
        logger.debug("No communications parquet files found at %s — creating empty view", comms_path)
        conn.execute("CREATE OR REPLACE VIEW communications AS SELECT 1 WHERE false")

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
