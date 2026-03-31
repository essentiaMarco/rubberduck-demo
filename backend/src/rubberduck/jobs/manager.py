"""Background job manager using ThreadPoolExecutor."""

import json
import logging
import traceback
from asyncio import Queue
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from rubberduck.config import settings
from rubberduck.db.models import Job

logger = logging.getLogger(__name__)


class JobManager:
    """Manages background jobs with progress tracking and SSE broadcasting."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=settings.max_workers)
        self._futures: dict[str, Future] = {}
        self._subscribers: list[Queue] = []

    def recover_stale_jobs(self, db: Session) -> int:
        """Mark any 'running' or 'pending' jobs as 'failed' on startup.

        These are leftovers from a previous process crash where the
        _wrapper never got to run the except/finally blocks.
        """
        stale = (
            db.query(Job)
            .filter(Job.status.in_(["running", "pending"]))
            .all()
        )
        count = 0
        for job in stale:
            job.status = "failed"
            job.error = "Server restarted while job was in progress"
            job.completed_at = datetime.now(timezone.utc)
            count += 1
        if count:
            db.commit()
            logger.info("Recovered %d stale jobs from previous run", count)
        return count

    def submit(
        self,
        db: Session,
        job_type: str,
        callable_fn: Callable,
        params: dict | None = None,
        *args,
        **kwargs,
    ) -> str:
        """Submit a background job. Returns the job ID."""
        job = Job(
            job_type=job_type,
            status="pending",
            params=json.dumps(params or {}),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        job_id = job.id

        def _wrapper():
            # Create a new session for the background thread
            from rubberduck.db.sqlite import SessionLocal

            thread_db = SessionLocal()
            try:
                thread_job = thread_db.query(Job).get(job_id)
                thread_job.status = "running"
                thread_job.started_at = datetime.now(timezone.utc)
                thread_db.commit()
                self._broadcast(job_id, "running", 0.0)

                result = callable_fn(thread_db, job_id, *args, **kwargs)

                thread_job = thread_db.query(Job).get(job_id)
                thread_job.status = "completed"
                thread_job.progress = 1.0
                thread_job.completed_at = datetime.now(timezone.utc)
                if result:
                    thread_job.result = json.dumps(result) if isinstance(result, dict) else str(result)
                thread_db.commit()
                self._broadcast(job_id, "completed", 1.0)
                return result
            except Exception as e:
                thread_job = thread_db.query(Job).get(job_id)
                thread_job.status = "failed"
                thread_job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                thread_job.completed_at = datetime.now(timezone.utc)
                thread_db.commit()
                self._broadcast(job_id, "failed", thread_job.progress or 0.0)
                logger.error(f"Job {job_id} failed: {e}", exc_info=True)
                raise
            finally:
                thread_db.close()

        future = self._executor.submit(_wrapper)
        self._futures[job_id] = future
        return job_id

    def update_progress(self, db: Session, job_id: str, progress: float, processed: int = 0, total: int = 0):
        """Update job progress from within a running job."""
        job = db.query(Job).get(job_id)
        if job:
            job.progress = min(progress, 1.0)
            job.processed_items = processed
            job.total_items = total
            db.commit()
            self._broadcast(job_id, "running", progress)

    def cancel(self, db: Session, job_id: str) -> bool:
        """Attempt to cancel a job."""
        future = self._futures.get(job_id)
        if future and not future.done():
            future.cancel()
            job = db.query(Job).get(job_id)
            if job:
                job.status = "cancelled"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
            self._broadcast(job_id, "cancelled", 0.0)
            return True
        return False

    def subscribe(self) -> Queue:
        """Subscribe to job events via SSE."""
        q: Queue = Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: Queue):
        """Remove an SSE subscriber."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _broadcast(self, job_id: str, status: str, progress: float):
        """Send job status update to all SSE subscribers."""
        event = {"job_id": job_id, "status": status, "progress": progress}
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def shutdown(self):
        """Graceful shutdown."""
        self._executor.shutdown(wait=False, cancel_futures=True)


# Singleton instance
job_manager = JobManager()
