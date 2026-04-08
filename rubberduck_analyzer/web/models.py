"""SQLite job tracking for background analysis tasks."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/jobs.db")


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            milestone TEXT NOT NULL,
            tester_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            progress TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            result_path TEXT,
            error TEXT,
            metadata TEXT
        )
    """)
    conn.commit()
    # Migration: add progress column if missing
    try:
        conn.execute("SELECT progress FROM jobs LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE jobs ADD COLUMN progress TEXT")
        conn.commit()
    return conn


def create_job(job_id: str, milestone: str, tester_name: str | None = None, metadata: dict | None = None) -> dict:
    conn = _get_db()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO jobs (id, milestone, tester_name, status, created_at, updated_at, metadata) VALUES (?, ?, ?, 'pending', ?, ?, ?)",
        (job_id, milestone, tester_name, now, now, json.dumps(metadata or {})),
    )
    conn.commit()
    conn.close()
    return {"id": job_id, "status": "pending", "milestone": milestone}


def update_job(job_id: str, status: str, result_path: str | None = None, error: str | None = None, progress: str | None = None):
    conn = _get_db()
    now = datetime.utcnow().isoformat()
    if progress is not None:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ?, result_path = ?, error = ?, progress = ? WHERE id = ?",
            (status, now, result_path, error, progress, job_id),
        )
    else:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ?, result_path = ?, error = ? WHERE id = ?",
            (status, now, result_path, error, job_id),
        )
    conn.commit()
    conn.close()


def get_job(job_id: str) -> dict | None:
    conn = _get_db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def list_jobs(milestone: str | None = None, limit: int = 50) -> list[dict]:
    conn = _get_db()
    if milestone:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE milestone = ? ORDER BY created_at DESC LIMIT ?",
            (milestone, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> dict:
    """Delete a job record and its uploaded files.

    Returns {"deleted": True} on success, {"error": reason} on failure.
    Refuses to delete jobs with status 'pending' or 'running'.
    """
    job = get_job(job_id)
    if job is None:
        return {"error": "not_found"}
    if job["status"] in ("pending", "running"):
        return {"error": "job_still_active", "status": job["status"]}

    # Remove uploaded files
    upload_dir = Path("data/uploads") / job_id
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir)

    # Remove result file if it exists
    if job.get("result_path"):
        result_path = Path(job["result_path"])
        if result_path.is_file():
            result_path.unlink()

    # Remove DB record
    conn = _get_db()
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    return {"deleted": True, "job_id": job_id}
