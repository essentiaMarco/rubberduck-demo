"""Search service — ranked full-text retrieval and autocomplete via FTS5."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import EvidenceSource, File
from rubberduck.search.indexer import FTS_TABLE, ensure_fts_table

logger = logging.getLogger(__name__)

# Maximum snippet size returned by SQLite snippet()
_SNIPPET_TOKENS = 32


def search(
    db: Session,
    query: str,
    file_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Run a full-text search against the FTS5 index.

    Returns a dict compatible with ``SearchResponse`` containing ranked results
    with BM25 scores and highlighted snippets.
    """
    ensure_fts_table(db)
    raw = db.get_bind().raw_connection()

    try:
        cursor = raw.cursor()

        # Build the base query joining FTS5 results with the files table.
        # We use bm25() for ranking (lower = better match in SQLite FTS5)
        # and snippet() for highlighted context.
        base_select = f"""
            SELECT
                fts.file_id,
                fts.chunk_index,
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
            WHERE {FTS_TABLE} MATCH ?
        """

        params: list[Any] = [query]

        if file_types:
            placeholders = ", ".join("?" for _ in file_types)
            base_select += f" AND f.file_ext IN ({placeholders})"
            params.extend(file_types)

        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            base_select += f" AND f.source_id IN ({placeholders})"
            params.extend(source_ids)

        # Count total matching rows (deduplicated by file_id)
        count_sql = f"""
            SELECT COUNT(DISTINCT fts.file_id)
            FROM {FTS_TABLE} fts
            JOIN files f ON f.id = fts.file_id
            LEFT JOIN evidence_sources es ON es.id = f.source_id
            WHERE {FTS_TABLE} MATCH ?
        """
        count_params: list[Any] = [query]
        if file_types:
            placeholders = ", ".join("?" for _ in file_types)
            count_sql += f" AND f.file_ext IN ({placeholders})"
            count_params.extend(file_types)
        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            count_sql += f" AND f.source_id IN ({placeholders})"
            count_params.extend(source_ids)

        cursor.execute(count_sql, count_params)
        total = cursor.fetchone()[0]

        # Fetch ranked results with pagination.
        # Group by file_id and take the best-scoring chunk per file.
        ranked_sql = f"""
            SELECT file_id, file_name, file_ext, mime_type, source_id,
                   source_label, MIN(score) AS score, snippet
            FROM ({base_select})
            GROUP BY file_id
            ORDER BY score ASC
            LIMIT ? OFFSET ?
        """
        offset = (page - 1) * page_size
        params.extend([page_size, offset])

        cursor.execute(ranked_sql, params)
        rows = cursor.fetchall()

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
        raw.close()


def suggest(db: Session, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return autocomplete suggestions matching *prefix*.

    Uses the FTS5 vocabulary table to find terms that start with the given
    prefix, ordered by document frequency.
    """
    ensure_fts_table(db)
    raw = db.get_bind().raw_connection()

    try:
        cursor = raw.cursor()

        # FTS5 vocab tables provide term-level statistics.
        # The instance vocabulary gives per-term document counts.
        vocab_table = f"{FTS_TABLE}_vocab"

        # Check if vocab table exists; create if needed
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (vocab_table,),
        )
        if not cursor.fetchone():
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
        raw.close()
