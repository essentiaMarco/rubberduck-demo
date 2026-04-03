"""Forensic analysis engine for phone CDR data.

Provides frequency analysis, temporal heatmaps, anomaly queries,
new-contact detection, and pattern-change flagging over PhoneRecord rows.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from rubberduck.db.models import PhoneRecord


def get_contact_frequency(db: Session) -> list[dict]:
    """Return contact frequency stats sorted by call count descending.

    Each entry contains the phone number, total calls, total and average
    duration, date range, and the set of call types observed.
    """
    # Union caller and called into a single "contact number" column.
    # For each record the *other* party is the contact.
    rows = db.query(PhoneRecord).all()

    contacts: dict[str, dict] = {}
    for r in rows:
        # Determine the "other" number
        number = r.called_number or r.caller_number
        if not number:
            continue

        if number not in contacts:
            contacts[number] = {
                "number": number,
                "call_count": 0,
                "total_duration_seconds": 0,
                "first_call": r.call_datetime,
                "last_call": r.call_datetime,
                "call_types": set(),
            }

        c = contacts[number]
        c["call_count"] += 1
        c["total_duration_seconds"] += r.duration_seconds or 0
        if r.call_datetime:
            if c["first_call"] is None or r.call_datetime < c["first_call"]:
                c["first_call"] = r.call_datetime
            if c["last_call"] is None or r.call_datetime > c["last_call"]:
                c["last_call"] = r.call_datetime
        if r.call_type:
            c["call_types"].add(r.call_type)

    result = []
    for c in contacts.values():
        avg_dur = (
            c["total_duration_seconds"] / c["call_count"]
            if c["call_count"]
            else 0
        )
        result.append(
            {
                "number": c["number"],
                "call_count": c["call_count"],
                "total_duration_seconds": c["total_duration_seconds"],
                "avg_duration": round(avg_dur, 1),
                "first_call": str(c["first_call"]) if c["first_call"] else None,
                "last_call": str(c["last_call"]) if c["last_call"] else None,
                "call_types": sorted(c["call_types"]),
            }
        )

    result.sort(key=lambda x: x["call_count"], reverse=True)
    return result


def get_hourly_heatmap(db: Session) -> list[dict]:
    """Return a 24x7 heatmap (hour 0-23 x day-of-week 0-6) of call counts.

    Uses SQL extract() for hour and dow.  Returns a flat list of
    ``{hour, day_of_week, count}`` dicts.
    """
    rows = (
        db.query(
            extract("hour", PhoneRecord.call_datetime).label("hour"),
            extract("dow", PhoneRecord.call_datetime).label("day_of_week"),
            func.count().label("count"),
        )
        .filter(PhoneRecord.call_datetime.isnot(None))
        .group_by("hour", "day_of_week")
        .all()
    )

    # Build a full 24x7 grid initialised to zero
    grid: dict[tuple[int, int], int] = {}
    for h in range(24):
        for d in range(7):
            grid[(h, d)] = 0

    for row in rows:
        h = int(row.hour) if row.hour is not None else 0
        d = int(row.day_of_week) if row.day_of_week is not None else 0
        grid[(h, d)] = row.count

    return [
        {"hour": h, "day_of_week": d, "count": cnt}
        for (h, d), cnt in sorted(grid.items())
    ]


def get_monthly_summary(db: Session) -> list[dict]:
    """Per-month summary: call count, total duration, unique contacts, avg daily calls."""
    rows = db.query(PhoneRecord).filter(PhoneRecord.call_datetime.isnot(None)).all()

    months: dict[str, dict] = {}
    for r in rows:
        key = r.call_datetime.strftime("%Y-%m")
        if key not in months:
            months[key] = {
                "month": key,
                "call_count": 0,
                "total_duration": 0,
                "contacts": set(),
                "days": set(),
            }
        m = months[key]
        m["call_count"] += 1
        m["total_duration"] += r.duration_seconds or 0
        contact = r.called_number or r.caller_number
        if contact:
            m["contacts"].add(contact)
        m["days"].add(r.call_datetime.date())

    result = []
    for m in sorted(months.values(), key=lambda x: x["month"]):
        num_days = len(m["days"]) or 1
        result.append(
            {
                "month": m["month"],
                "call_count": m["call_count"],
                "total_duration": m["total_duration"],
                "unique_contacts": len(m["contacts"]),
                "avg_daily_calls": round(m["call_count"] / num_days, 1),
            }
        )
    return result


def get_anomalies(db: Session, min_score: float = 0.1) -> list[dict]:
    """Return all anomalous phone records ordered by score descending."""
    records = (
        db.query(PhoneRecord)
        .filter(
            PhoneRecord.is_anomaly == True,  # noqa: E712
            PhoneRecord.anomaly_score >= min_score,
        )
        .order_by(PhoneRecord.anomaly_score.desc())
        .all()
    )

    import json as _json

    return [
        {
            "id": r.id,
            "caller_number": r.caller_number,
            "called_number": r.called_number,
            "call_datetime": str(r.call_datetime) if r.call_datetime else None,
            "duration_seconds": r.duration_seconds,
            "call_type": r.call_type,
            "charges": r.charges,
            "anomaly_score": r.anomaly_score,
            "anomaly_reasons": _json.loads(r.anomaly_reasons)
            if r.anomaly_reasons
            else [],
        }
        for r in records
    ]


def get_number_timeline(db: Session, phone_number: str) -> list[dict]:
    """Return every call to/from *phone_number* in chronological order."""
    records = (
        db.query(PhoneRecord)
        .filter(
            (PhoneRecord.caller_number == phone_number)
            | (PhoneRecord.called_number == phone_number)
        )
        .order_by(PhoneRecord.call_datetime.asc())
        .all()
    )

    import json as _json

    return [
        {
            "id": r.id,
            "caller_number": r.caller_number,
            "called_number": r.called_number,
            "call_datetime": str(r.call_datetime) if r.call_datetime else None,
            "call_datetime_raw": r.call_datetime_raw,
            "duration_seconds": r.duration_seconds,
            "duration_raw": r.duration_raw,
            "call_type": r.call_type,
            "charges": r.charges,
            "is_anomaly": r.is_anomaly,
            "anomaly_score": r.anomaly_score,
            "anomaly_reasons": _json.loads(r.anomaly_reasons)
            if r.anomaly_reasons
            else [],
            "subscriber_number": r.subscriber_number,
            "bill_number": r.bill_number,
            "bill_period_start": str(r.bill_period_start) if r.bill_period_start else None,
            "bill_period_end": str(r.bill_period_end) if r.bill_period_end else None,
        }
        for r in records
    ]


def get_new_contacts_by_month(db: Session) -> list[dict]:
    """For each month, identify numbers that appeared for the FIRST time.

    New contacts near key dates are forensically significant -- they may
    indicate new relationships, burner phones, or coordinated activity.
    """
    rows = (
        db.query(PhoneRecord)
        .filter(PhoneRecord.call_datetime.isnot(None))
        .order_by(PhoneRecord.call_datetime.asc())
        .all()
    )

    seen: set[str] = set()
    monthly_new: dict[str, list[str]] = defaultdict(list)

    for r in rows:
        contact = r.called_number or r.caller_number
        if not contact:
            continue
        if contact not in seen:
            seen.add(contact)
            month_key = r.call_datetime.strftime("%Y-%m")
            monthly_new[month_key].append(contact)

    return [
        {"month": month, "new_contacts": contacts, "count": len(contacts)}
        for month, contacts in sorted(monthly_new.items())
    ]


def get_call_pattern_changes(db: Session) -> list[dict]:
    """Flag months where the daily call rate deviates >50% from the overall average.

    Returns a list of months with their daily average, the overall daily
    average, the percentage deviation, and direction (increase/decrease).
    """
    rows = (
        db.query(PhoneRecord)
        .filter(PhoneRecord.call_datetime.isnot(None))
        .all()
    )

    if not rows:
        return []

    # Gather per-month stats
    months: dict[str, dict] = {}
    all_days: set = set()
    for r in rows:
        key = r.call_datetime.strftime("%Y-%m")
        if key not in months:
            months[key] = {"call_count": 0, "days": set()}
        months[key]["call_count"] += 1
        months[key]["days"].add(r.call_datetime.date())
        all_days.add(r.call_datetime.date())

    total_days = len(all_days) or 1
    overall_avg = len(rows) / total_days

    result = []
    for month_key in sorted(months):
        m = months[month_key]
        num_days = len(m["days"]) or 1
        daily_avg = m["call_count"] / num_days
        if overall_avg == 0:
            deviation_pct = 0.0
        else:
            deviation_pct = ((daily_avg - overall_avg) / overall_avg) * 100

        if abs(deviation_pct) > 50:
            result.append(
                {
                    "month": month_key,
                    "daily_avg": round(daily_avg, 1),
                    "overall_avg": round(overall_avg, 1),
                    "deviation_pct": round(deviation_pct, 1),
                    "direction": "increase" if deviation_pct > 0 else "decrease",
                }
            )

    return result
