"""Search service — ranked full-text retrieval and autocomplete via FTS5."""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import EvidenceSource, File
from rubberduck.search.indexer import FTS_TABLE, ensure_fts_table, _get_raw_conn

logger = logging.getLogger(__name__)

# Maximum snippet size returned by SQLite snippet()
_SNIPPET_TOKENS = 32

# Whitelist pattern for FTS table-derived identifiers (alphanumeric + underscore)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def search(
    db: Session,
    query: str,
    file_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Run a full-text search against the FTS5 index.

    Returns a dict compatible with ``SearchResponse`` containing ranked results
    with BM25 scores and highlighted snippets.
    """
    ensure_fts_table(db)
    raw = _get_raw_conn(db)
    cursor = raw.cursor()

    try:
        # Build the FTS5 MATCH query directly on the FTS table.
        # bm25() and snippet() are FTS5 auxiliary functions that must be
        # called directly on the FTS table (not inside a subquery).
        #
        # Strategy: query the FTS table directly with MATCH, join files
        # for metadata, use ORDER BY rank (built-in FTS5 ranking).
        # To deduplicate chunks from the same file, we use a two-phase
        # approach: first get best chunk per file via rowid, then fetch.

        # Phase 1: Get the best-ranking rowid per file_id
        match_where = f"WHERE {FTS_TABLE} MATCH ?"
        params: list[Any] = [query]
        join_filters = ""

        if file_types:
            placeholders = ", ".join("?" for _ in file_types)
            join_filters += f" AND f.file_ext IN ({placeholders})"
            params.extend(file_types)

        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            join_filters += f" AND f.source_id IN ({placeholders})"
            params.extend(source_ids)

        if date_start:
            join_filters += " AND f.created_at >= ?"
            params.append(date_start)
        if date_end:
            join_filters += " AND f.created_at <= ?"
            params.append(date_end)

        # Count total matching files (deduplicated)
        count_sql = f"""
            SELECT COUNT(DISTINCT fts.file_id)
            FROM {FTS_TABLE} fts
            JOIN files f ON f.id = fts.file_id
            {match_where} {join_filters}
        """
        cursor.execute(count_sql, list(params))
        total = cursor.fetchone()[0]

        # Phase 2: Get best chunk per file using MIN(rank) grouping on rowid,
        # then join back to get bm25/snippet on those specific rows.
        # We select from FTS table with MATCH, rank by bm25, and use
        # GROUP BY on file_id keeping the best row.
        offset = (page - 1) * page_size

        # Direct query: bm25() and snippet() on the FTS table with MATCH
        # FTS5 ORDER BY rank is optimized and uses the built-in ranking.
        ranked_sql = f"""
            SELECT
                fts.file_id,
                f.file_name,
                f.file_ext,
                f.mime_type,
                f.source_id,
                es.label AS source_label,
                bm25({FTS_TABLE}) AS score,
                snippet({FTS_TABLE}, 2, '<mark>', '</mark>', '...', {_SNIPPET_TOKENS}) AS snippet
            FROM {FTS_TABLE} fts
            JOIN files f ON f.id = fts.file_id
            LEFT JOIN evidence_sources es ON es.id = f.source_id
            {match_where} {join_filters}
            ORDER BY rank
            LIMIT ? OFFSET ?
        """
        ranked_params = list(params) + [page_size * 5, 0]  # overfetch for dedup

        cursor.execute(ranked_sql, ranked_params)
        all_rows = cursor.fetchall()

        # Deduplicate by file_id (keep first = best-scoring chunk per file)
        seen_files: set[str] = set()
        rows = []
        for row in all_rows:
            fid = row[0]
            if fid in seen_files:
                continue
            seen_files.add(fid)
            rows.append(row)

        # Apply pagination on deduplicated results
        rows = rows[offset:offset + page_size]

        results = []
        for row in rows:
            results.append(
                {
                    "file_id": row[0],
                    "file_name": row[1],
                    "file_ext": row[2],
                    "mime_type": row[3],
                    "source_label": row[5],
                    "score": abs(row[6]),  # bm25() returns negative; invert for display
                    "snippet": row[7],
                }
            )

        return {
            "results": results,
            "total": total,
            "query": query,
            "page": page,
            "page_size": page_size,
        }
    except Exception:
        logger.exception("Search failed for query=%r", query)
        raise
    finally:
        cursor.close()


def suggest(db: Session, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return autocomplete suggestions matching *prefix*.

    Uses the FTS5 vocabulary table to find terms that start with the given
    prefix, ordered by document frequency.
    """
    ensure_fts_table(db)
    raw = _get_raw_conn(db)
    cursor = raw.cursor()

    try:
        # FTS5 vocab tables provide term-level statistics.
        # The instance vocabulary gives per-term document counts.
        vocab_table = f"{FTS_TABLE}_vocab"

        # Validate the derived table name to prevent SQL injection.
        # FTS_TABLE is a module constant, but defence-in-depth is warranted
        # since the value is interpolated into DDL.
        if not _SAFE_IDENTIFIER.match(vocab_table):
            raise ValueError(f"Unsafe vocab table identifier: {vocab_table!r}")

        # Check if vocab table exists; create if needed
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (vocab_table,),
        )
        if not cursor.fetchone():
            # Use parameterised check above; the CREATE must use a validated
            # identifier since DDL does not support parameter binding for
            # table names.
            cursor.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {vocab_table} USING fts5vocab({FTS_TABLE}, row)"
            )
            raw.commit()

        cursor.execute(
            f"""
            SELECT term, doc AS count
            FROM {vocab_table}
            WHERE term LIKE ? || '%'
            ORDER BY doc DESC
            LIMIT ?
            """,
            (prefix.lower(), limit),
        )
        rows = cursor.fetchall()
        return [{"term": row[0], "count": row[1]} for row in rows]
    except Exception:
        logger.exception("Suggest failed for prefix=%r", prefix)
        return []
    finally:
        cursor.close()
