"""FTS5 index builder for SQLite full-text search.

Creates and maintains an FTS5 virtual table over parsed file content,
with support for chunking large documents and full reindexing.
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from rubberduck.db.models import File

logger = logging.getLogger(__name__)

# Chunking constants
MAX_CONTENT_SIZE = 50 * 1024  # 50 KB
CHUNK_OVERLAP = 200  # characters of overlap between consecutive chunks

FTS_TABLE = "file_content_fts"

_DDL_CREATE = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
    file_id UNINDEXED,
    chunk_index UNINDEXED,
    content,
    tokenize='porter unicode61'
)
"""

_DDL_DROP = f"DROP TABLE IF EXISTS {FTS_TABLE}"


def ensure_fts_table(db: Session) -> None:
    """Create the FTS5 virtual table if it does not already exist."""
    raw = db.get_bind().raw_connection()
    try:
        raw.execute(_DDL_CREATE)
        raw.commit()
    finally:
        raw.close()


def _chunk_text(text: str, max_size: int = MAX_CONTENT_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks of at most *max_size* characters with *overlap*."""
    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def index_file(db: Session, file_id: str, text_content: str) -> int:
    """Insert (or replace) the FTS5 index entries for a single file.

    Large documents are chunked into segments of up to 50 KB with 200-char
    overlap so that snippet extraction works well on any segment boundary.

    Returns the number of chunks indexed.
    """
    raw = db.get_bind().raw_connection()
    try:
        cursor = raw.cursor()
        # Remove any existing rows for this file
        cursor.execute(f"DELETE FROM {FTS_TABLE} WHERE file_id = ?", (file_id,))

        chunks = _chunk_text(text_content)
        for idx, chunk in enumerate(chunks):
            cursor.execute(
                f"INSERT INTO {FTS_TABLE} (file_id, chunk_index, content) VALUES (?, ?, ?)",
                (file_id, idx, chunk),
            )
        raw.commit()
        return len(chunks)
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def remove_file(db: Session, file_id: str) -> None:
    """Remove all FTS5 index entries for a given file."""
    raw = db.get_bind().raw_connection()
    try:
        raw.execute(f"DELETE FROM {FTS_TABLE} WHERE file_id = ?", (file_id,))
        raw.commit()
    finally:
        raw.close()


def bulk_reindex(db: Session) -> dict:
    """Rebuild the entire FTS5 index from all parsed files on disk.

    Reads the ``content.txt`` produced by each parser and indexes it.
    Returns a summary dict with counts of files indexed, skipped, and errored.
    """
    raw = db.get_bind().raw_connection()
    cursor = raw.cursor()

    # Drop and recreate for a clean rebuild
    cursor.execute(_DDL_DROP)
    cursor.execute(_DDL_CREATE)
    raw.commit()

    files = (
        db.query(File)
        .filter(
            File.parse_status == "completed",
            File.parsed_path.isnot(None),
        )
        .all()
    )

    stats = {"indexed": 0, "skipped": 0, "errors": 0, "total_chunks": 0}

    for f in files:
        content_path = Path(f.parsed_path) / "content.txt"
        if not content_path.exists():
            stats["skipped"] += 1
            continue

        try:
            text = content_path.read_text(encoding="utf-8")
            if not text.strip():
                stats["skipped"] += 1
                continue

            chunks = _chunk_text(text)
            for idx, chunk in enumerate(chunks):
                cursor.execute(
                    f"INSERT INTO {FTS_TABLE} (file_id, chunk_index, content) VALUES (?, ?, ?)",
                    (f.id, idx, chunk),
                )
            stats["indexed"] += 1
            stats["total_chunks"] += len(chunks)
        except Exception as exc:
            logger.error("Failed to index file %s: %s", f.id, exc)
            stats["errors"] += 1

    raw.commit()
    raw.close()

    logger.info(
        "Bulk reindex complete: %d files indexed (%d chunks), %d skipped, %d errors",
        stats["indexed"],
        stats["total_chunks"],
        stats["skipped"],
        stats["errors"],
    )
    return stats
