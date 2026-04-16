"""API routes for forensic alerts, watchlists, and secrets."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.db.models import File as FileModel, ForensicAlert, ForensicSecret, WatchlistEntry
from rubberduck.db.sqlite import get_db
from rubberduck.forensics.alerts import run_alert_rules
from rubberduck.schemas.alerts import (
    AlertDismissRequest,
    AlertStatsResponse,
    ForensicAlertResponse,
    WatchlistEntryCreate,
    WatchlistEntryResponse,
)
from rubberduck.schemas.secrets import (
    ForensicSecretResponse,
    SecretDetailResponse,
    SecretReviewRequest,
    SecretStatsResponse,
)

router = APIRouter(tags=["forensics"])


# ── Secrets ──────────────────────────────────────────────────


@router.get("/api/secrets", response_model=dict)
def list_secrets(
    severity: str | None = Query(None),
    secret_category: str | None = Query(None),
    secret_type: str | None = Query(None),
    file_id: str | None = Query(None),
    dismissed: bool | None = Query(None),
    is_reviewed: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List discovered secrets with filtering and pagination."""
    q = db.query(ForensicSecret)
    if severity:
        q = q.filter(ForensicSecret.severity == severity)
    if secret_category:
        q = q.filter(ForensicSecret.secret_category == secret_category)
    if secret_type:
        q = q.filter(ForensicSecret.secret_type == secret_type)
    if file_id:
        q = q.filter(ForensicSecret.file_id == file_id)
    if dismissed is not None:
        q = q.filter(ForensicSecret.dismissed == dismissed)
    if is_reviewed is not None:
        q = q.filter(ForensicSecret.is_reviewed == is_reviewed)

    total = q.count()
    secrets = (
        q.order_by(
            # Critical first, then high, then medium, then low
            ForensicSecret.severity.asc(),
            ForensicSecret.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Enrich with file names so investigators can locate the source
    file_ids = {s.file_id for s in secrets}
    file_names = {}
    if file_ids:
        for f in db.query(FileModel.id, FileModel.file_name, FileModel.original_path).filter(FileModel.id.in_(file_ids)).all():
            file_names[f.id] = {"file_name": f.file_name, "original_path": f.original_path}

    items = []
    for s in secrets:
        d = ForensicSecretResponse.model_validate(s).model_dump()
        finfo = file_names.get(s.file_id, {})
        d["file_name"] = finfo.get("file_name")
        d["original_path"] = finfo.get("original_path")
        items.append(d)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/secrets/stats", response_model=SecretStatsResponse)
def secret_stats(db: Session = Depends(get_db)):
    """Aggregate secret statistics."""
    total = db.query(ForensicSecret).count()
    by_severity = dict(
        db.query(ForensicSecret.severity, func.count())
        .group_by(ForensicSecret.severity).all()
    )
    by_category = dict(
        db.query(ForensicSecret.secret_category, func.count())
        .group_by(ForensicSecret.secret_category).all()
    )
    by_type = dict(
        db.query(ForensicSecret.secret_type, func.count())
        .group_by(ForensicSecret.secret_type).all()
    )
    unreviewed = db.query(ForensicSecret).filter(
        ForensicSecret.is_reviewed == False, ForensicSecret.dismissed == False
    ).count()
    dismissed = db.query(ForensicSecret).filter(ForensicSecret.dismissed == True).count()

    return SecretStatsResponse(
        total=total, by_severity=by_severity, by_category=by_category,
        by_type=by_type, unreviewed=unreviewed, dismissed=dismissed,
    )


@router.post("/api/secrets/clear")
def clear_secrets(db: Session = Depends(get_db)):
    """Clear all forensic secrets (for re-scanning after improving patterns)."""
    from sqlalchemy import text
    count = db.query(ForensicSecret).count()
    db.execute(text("DELETE FROM forensic_secrets"))
    db.commit()
    return {"deleted": count, "message": f"Cleared {count} secrets"}


@router.post("/api/secrets/scan")
def trigger_secret_scan(db: Session = Depends(get_db)):
    """Run secret scanner across all parsed files that haven't been scanned yet.

    Also runs alert rules after scanning to generate alerts for new findings.
    """
    from rubberduck.db.models import File as FileModel
    from rubberduck.jobs.manager import job_manager

    def _scan_job(thread_db, job_id):
        from rubberduck.entities.secret_scanner import scan_secrets
        from rubberduck.entities.secret_scanner import mask_secret as _mask

        # Find files with parsed content that have no secrets yet
        already_scanned = thread_db.query(ForensicSecret.file_id).distinct().subquery()
        files = (
            thread_db.query(FileModel)
            .filter(
                FileModel.parse_status == "completed",
                FileModel.parsed_path.isnot(None),
                ~FileModel.id.in_(already_scanned),
            )
            .all()
        )
        total = len(files)
        stats = {"total_files": total, "secrets_found": 0, "files_with_secrets": 0, "errors": 0}

        for i, f in enumerate(files):
            try:
                from pathlib import Path
                content_path = Path(f.parsed_path) / "content.txt"
                if not content_path.exists():
                    continue
                text = content_path.read_text(encoding="utf-8")
                if not text.strip():
                    continue

                # Cap at 2MB like the entity pipeline
                if len(text) > 2 * 1024 * 1024:
                    text = text[:2 * 1024 * 1024]

                results = scan_secrets(text, file_id=f.id)
                if results:
                    stats["files_with_secrets"] += 1
                    for sm in results:
                        ctx_start = max(0, sm.get("char_offset", 0) - 80)
                        ctx_end = min(len(text), sm.get("char_offset", 0) + len(sm["text"]) + 80)
                        secret = ForensicSecret(
                            file_id=f.id,
                            secret_type=sm.get("secret_type", sm["entity_type"]),
                            secret_category=sm["entity_type"],
                            severity=sm.get("severity", "medium"),
                            detected_value=sm["text"],
                            masked_value=_mask(sm["text"]),
                            context_snippet=text[ctx_start:ctx_end],
                            char_offset=sm.get("char_offset"),
                            detection_method=sm.get("detection_method", "regex"),
                            confidence=sm.get("confidence", 0.9),
                        )
                        thread_db.add(secret)
                        stats["secrets_found"] += 1
                    thread_db.commit()
            except Exception as e:
                stats["errors"] += 1

            if (i + 1) % 10 == 0 or i == total - 1:
                job_manager.update_progress(thread_db, job_id, (i + 1) / max(total, 1), i + 1, total)

        # Run alert rules after scanning
        from rubberduck.forensics.alerts import run_alert_rules
        alert_result = run_alert_rules(thread_db)
        stats["alerts"] = alert_result
        return stats

    job_id = job_manager.submit(db, "secret_scan", _scan_job, params={})
    return {"job_id": job_id, "message": "Secret scan started across all parsed evidence"}


@router.get("/api/secrets/{secret_id}", response_model=SecretDetailResponse)
def get_secret(secret_id: str, db: Session = Depends(get_db)):
    """Get a single secret with unmasked value."""
    secret = db.query(ForensicSecret).get(secret_id)
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    return secret


@router.patch("/api/secrets/{secret_id}/review", response_model=ForensicSecretResponse)
def review_secret(
    secret_id: str,
    body: SecretReviewRequest,
    db: Session = Depends(get_db),
):
    """Mark a secret as reviewed or dismissed."""
    secret = db.query(ForensicSecret).get(secret_id)
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")

    secret.is_reviewed = body.is_reviewed
    secret.review_notes = body.review_notes
    secret.dismissed = body.dismissed
    db.commit()
    db.refresh(secret)
    return secret


# ── Hidden Content Scan ──────────────────────────────────────


@router.post("/api/forensics/hidden-content-scan")
def trigger_hidden_content_scan(db: Session = Depends(get_db)):
    """Scan all evidence for encrypted files, type mismatches, hidden DOCX content."""
    from rubberduck.forensics.hidden_content import scan_hidden_content
    result = scan_hidden_content(db)
    return result


# ── Alerts ───────────────────────────────────────────────────


@router.get("/api/alerts", response_model=dict)
def list_alerts(
    severity: str | None = Query(None),
    alert_type: str | None = Query(None),
    dismissed: bool | None = Query(False),
    case_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List forensic alerts with filtering."""
    q = db.query(ForensicAlert)
    if severity:
        q = q.filter(ForensicAlert.severity == severity)
    if alert_type:
        q = q.filter(ForensicAlert.alert_type == alert_type)
    if dismissed is not None:
        q = q.filter(ForensicAlert.dismissed == dismissed)
    if case_id:
        q = q.filter(ForensicAlert.case_id == case_id)

    total = q.count()
    alerts = (
        q.order_by(ForensicAlert.severity.asc(), ForensicAlert.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Enrich with file names
    file_ids = {a.evidence_file_id for a in alerts if a.evidence_file_id}
    file_names = {}
    if file_ids:
        for f in db.query(FileModel.id, FileModel.file_name, FileModel.original_path).filter(FileModel.id.in_(file_ids)).all():
            file_names[f.id] = {"file_name": f.file_name, "original_path": f.original_path}

    items = []
    for a in alerts:
        d = ForensicAlertResponse.model_validate(a).model_dump()
        finfo = file_names.get(a.evidence_file_id, {})
        d["file_name"] = finfo.get("file_name")
        d["original_path"] = finfo.get("original_path")
        items.append(d)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/alerts/stats", response_model=AlertStatsResponse)
def alert_stats(db: Session = Depends(get_db)):
    """Aggregate alert statistics."""
    total = db.query(ForensicAlert).count()
    unreviewed = db.query(ForensicAlert).filter(ForensicAlert.dismissed == False).count()
    by_severity = dict(
        db.query(ForensicAlert.severity, func.count())
        .group_by(ForensicAlert.severity).all()
    )
    by_type = dict(
        db.query(ForensicAlert.alert_type, func.count())
        .group_by(ForensicAlert.alert_type).all()
    )
    return AlertStatsResponse(
        total=total, unreviewed=unreviewed, by_severity=by_severity, by_type=by_type,
    )


@router.get("/api/alerts/{alert_id}", response_model=ForensicAlertResponse)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    """Get a single alert."""
    alert = db.query(ForensicAlert).get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/api/alerts/{alert_id}/dismiss", response_model=ForensicAlertResponse)
def dismiss_alert(
    alert_id: str,
    body: AlertDismissRequest,
    db: Session = Depends(get_db),
):
    """Dismiss an alert with optional reason."""
    alert = db.query(ForensicAlert).get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.dismissed = True
    alert.dismissed_at = datetime.now(timezone.utc)
    alert.dismiss_reason = body.dismiss_reason
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/api/alerts/run")
def trigger_alert_scan(
    case_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Manually trigger all alert rules."""
    result = run_alert_rules(db, case_id=case_id)
    return result


# ── Watchlist ────────────────────────────────────────────────


@router.get("/api/watchlist", response_model=list[WatchlistEntryResponse])
def list_watchlist(
    case_id: str | None = None,
    active: bool | None = True,
    db: Session = Depends(get_db),
):
    """List watchlist entries."""
    q = db.query(WatchlistEntry)
    if case_id:
        q = q.filter(WatchlistEntry.case_id == case_id)
    if active is not None:
        q = q.filter(WatchlistEntry.active == active)
    return q.order_by(WatchlistEntry.created_at.desc()).all()


@router.post("/api/watchlist", response_model=WatchlistEntryResponse)
def add_watchlist_entry(body: WatchlistEntryCreate, db: Session = Depends(get_db)):
    """Add a new watchlist term."""
    entry = WatchlistEntry(**body.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/api/watchlist/{entry_id}", status_code=204)
def remove_watchlist_entry(entry_id: str, db: Session = Depends(get_db)):
    """Remove a watchlist entry."""
    entry = db.query(WatchlistEntry).get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    db.delete(entry)
    db.commit()
