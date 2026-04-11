"""API routes for phone analysis -- browse, filter, and analyze CDR records."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.db.models import PhoneRecord
from rubberduck.db.sqlite import get_db

router = APIRouter(prefix="/api/phone-analysis", tags=["phone-analysis"])


# ── Helper ────────────────────────────────────────────────────


def _record_dict(r: PhoneRecord, full: bool = False) -> dict:
    """Convert a PhoneRecord ORM instance to an API-safe dict."""
    d = {
        "id": r.id,
        "caller_number": r.caller_number,
        "called_number": r.called_number,
        "call_datetime": str(r.call_datetime) if r.call_datetime else None,
        "duration_seconds": r.duration_seconds,
        "duration_raw": r.duration_raw,
        "call_type": r.call_type,
        "charges": r.charges,
        "is_anomaly": r.is_anomaly,
        "anomaly_score": r.anomaly_score,
    }
    if full:
        d["call_datetime_raw"] = r.call_datetime_raw
        d["subscriber_number"] = r.subscriber_number
        d["subscriber_name"] = r.subscriber_name
        d["bill_number"] = r.bill_number
        d["bill_plan"] = r.bill_plan
        d["bill_period_start"] = str(r.bill_period_start) if r.bill_period_start else None
        d["bill_period_end"] = str(r.bill_period_end) if r.bill_period_end else None
        d["anomaly_reasons"] = json.loads(r.anomaly_reasons) if r.anomaly_reasons else []
        d["file_id"] = r.file_id
    return d


# ── Endpoints ────────────────────────────────────────────────


@router.get("/records")
def list_records(
    phone_number: str | None = Query(None, description="Filter caller or called (partial match)"),
    call_type: str | None = Query(None, description="Filter by call type"),
    date_start: str | None = Query(None, description="Start date filter (ISO)"),
    date_end: str | None = Query(None, description="End date filter (ISO)"),
    anomaly_only: bool = Query(False, description="Only show anomalies"),
    sort_by: str | None = Query("date", description="Sort: date, duration, charges, anomaly_score"),
    sort_dir: str | None = Query("desc", description="Sort direction: asc, desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List CDR records with filtering and pagination."""
    q = db.query(PhoneRecord)

    if phone_number:
        q = q.filter(
            (PhoneRecord.caller_number.ilike(f"%{phone_number}%"))
            | (PhoneRecord.called_number.ilike(f"%{phone_number}%"))
        )
    if call_type:
        q = q.filter(PhoneRecord.call_type == call_type)
    if date_start:
        q = q.filter(PhoneRecord.call_datetime >= date_start)
    if date_end:
        q = q.filter(PhoneRecord.call_datetime <= date_end)
    if anomaly_only:
        q = q.filter(PhoneRecord.is_anomaly == True)  # noqa: E712

    total = q.count()

    # Sorting
    sort_map = {
        "duration": PhoneRecord.duration_seconds,
        "charges": PhoneRecord.charges,
        "anomaly_score": PhoneRecord.anomaly_score,
    }
    order_col = sort_map.get(sort_by, PhoneRecord.call_datetime)

    if sort_dir == "asc":
        q = q.order_by(order_col.asc().nullslast())
    else:
        q = q.order_by(order_col.desc().nullslast())

    records = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_record_dict(r) for r in records],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/records/{record_id}")
def get_record(record_id: str, db: Session = Depends(get_db)):
    """Get a single CDR record with all fields."""
    record = db.query(PhoneRecord).get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Phone record not found")
    return _record_dict(record, full=True)


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Overall phone analysis statistics."""
    total = db.query(PhoneRecord).count()
    if total == 0:
        return {
            "total_records": 0,
            "unique_contacts": 0,
            "date_range": {"start": None, "end": None},
            "by_call_type": {},
            "by_month": [],
            "total_duration_seconds": 0,
            "anomaly_count": 0,
            "subscriber_info": [],
        }

    # Unique contacts (union of caller and called numbers)
    caller_nums = {
        r[0]
        for r in db.query(PhoneRecord.caller_number)
        .filter(PhoneRecord.caller_number.isnot(None))
        .distinct()
        .all()
    }
    called_nums = {
        r[0]
        for r in db.query(PhoneRecord.called_number)
        .filter(PhoneRecord.called_number.isnot(None))
        .distinct()
        .all()
    }
    unique_contacts = len(caller_nums | called_nums)

    # Date range
    date_min = db.query(func.min(PhoneRecord.call_datetime)).scalar()
    date_max = db.query(func.max(PhoneRecord.call_datetime)).scalar()

    # By call type
    by_call_type = dict(
        db.query(PhoneRecord.call_type, func.count())
        .group_by(PhoneRecord.call_type)
        .all()
    )

    # By month (SQL aggregation instead of loading all rows into memory)
    month_rows = (
        db.query(
            func.strftime("%Y-%m", PhoneRecord.call_datetime).label("month"),
            func.count().label("cnt"),
        )
        .filter(PhoneRecord.call_datetime.isnot(None))
        .group_by("month")
        .order_by("month")
        .all()
    )
    by_month = [{"month": r.month, "count": r.cnt} for r in month_rows]

    # Total duration
    total_duration = (
        db.query(func.sum(PhoneRecord.duration_seconds)).scalar() or 0
    )

    # Anomaly count
    anomaly_count = (
        db.query(PhoneRecord)
        .filter(PhoneRecord.is_anomaly == True)  # noqa: E712
        .count()
    )

    # Subscriber info
    subscribers = (
        db.query(
            PhoneRecord.subscriber_number,
            PhoneRecord.subscriber_name,
            func.count().label("record_count"),
        )
        .group_by(PhoneRecord.subscriber_number, PhoneRecord.subscriber_name)
        .all()
    )
    subscriber_info = [
        {
            "number": s.subscriber_number,
            "name": s.subscriber_name,
            "record_count": s.record_count,
        }
        for s in subscribers
    ]

    return {
        "total_records": total,
        "unique_contacts": unique_contacts,
        "date_range": {
            "start": str(date_min) if date_min else None,
            "end": str(date_max) if date_max else None,
        },
        "by_call_type": by_call_type,
        "by_month": by_month,
        "total_duration_seconds": total_duration,
        "anomaly_count": anomaly_count,
        "subscriber_info": subscriber_info,
    }


@router.get("/contacts")
def get_contacts(db: Session = Depends(get_db)):
    """Contact frequency analysis."""
    from rubberduck.phone_analysis.analyzer import get_contact_frequency

    return get_contact_frequency(db)


@router.get("/heatmap")
def get_heatmap(db: Session = Depends(get_db)):
    """Hourly x day-of-week call heatmap."""
    from rubberduck.phone_analysis.analyzer import get_hourly_heatmap

    return get_hourly_heatmap(db)


@router.get("/anomalies")
def get_anomalies(
    min_score: float = Query(0.1, description="Minimum anomaly score"),
    db: Session = Depends(get_db),
):
    """All anomalous phone records."""
    from rubberduck.phone_analysis.analyzer import get_anomalies as _get_anomalies

    return _get_anomalies(db, min_score=min_score)


@router.get("/monthly")
def get_monthly(db: Session = Depends(get_db)):
    """Monthly summary with call counts and unique contacts."""
    from rubberduck.phone_analysis.analyzer import get_monthly_summary

    return get_monthly_summary(db)


@router.get("/new-contacts")
def get_new_contacts(db: Session = Depends(get_db)):
    """New contacts appearing each month -- forensically critical."""
    from rubberduck.phone_analysis.analyzer import get_new_contacts_by_month

    return get_new_contacts_by_month(db)


@router.get("/pattern-changes")
def get_pattern_changes(db: Session = Depends(get_db)):
    """Months where daily call rate deviates >50% from the overall average."""
    from rubberduck.phone_analysis.analyzer import get_call_pattern_changes

    return get_call_pattern_changes(db)


@router.get("/number/{phone_number}")
def get_number_timeline(phone_number: str, db: Session = Depends(get_db)):
    """Full call timeline for a specific phone number."""
    from rubberduck.phone_analysis.analyzer import get_number_timeline as _get_timeline

    return _get_timeline(db, phone_number)


@router.post("")
@router.post("/")
def ingest_phone_bills(
    folder_path: str = Query(..., description="Path to folder containing PDF bills"),
    reprocess: bool = Query(False, description="Re-extract even if records exist"),
    db: Session = Depends(get_db),
):
    """Ingest Vodafone bill PDFs from a folder and extract CDR records."""
    from pathlib import Path
    from rubberduck.config import settings

    # Validate path is within allowed directories to prevent path traversal
    resolved = Path(folder_path).resolve()
    allowed_bases = (
        [Path(p).resolve() for p in settings.allowed_ingest_paths]
        if settings.allowed_ingest_paths
        else [settings.data_dir.resolve()]
    )
    if not any(resolved == base or resolved.is_relative_to(base) for base in allowed_bases):
        raise HTTPException(
            status_code=403,
            detail="Directory is outside allowed ingest paths",
        )
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    from rubberduck.phone_analysis.extractor import extract_all_phone_bills

    result = extract_all_phone_bills(db, str(resolved), reprocess=reprocess)
    return result
