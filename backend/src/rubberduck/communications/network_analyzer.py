"""Communication network deep analysis — frequency matrix, burner detection, cross-platform correlation.

Analyzes communication patterns across email, phone, WhatsApp, and other channels
to surface investigatively critical insights: who talks to whom, new contacts around
key dates, potential burner phones, and cross-platform identity matches.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from rubberduck.db.models import EmailMessage, Entity, EntityMention, PhoneRecord

logger = logging.getLogger(__name__)


def get_frequency_matrix(db: Session) -> dict[str, Any]:
    """Build a contact frequency matrix across all communication channels.

    Returns {pairs: [{a, b, count, channels, total_duration}], top_contacts: [...]}
    """
    pairs: dict[tuple[str, str], dict] = defaultdict(lambda: {"count": 0, "channels": set(), "total_duration": 0})

    # Email pairs (from -> to)
    email_rows = (
        db.query(EmailMessage.email_from, EmailMessage.email_to)
        .filter(EmailMessage.email_from.isnot(None), EmailMessage.email_to.isnot(None))
        .filter(EmailMessage.is_spam == False)
        .all()
    )
    for row in email_rows:
        a = (row.email_from or "").strip().lower()
        b = (row.email_to or "").strip().lower().split(",")[0].strip()  # Take first recipient
        if a and b and a != b:
            key = tuple(sorted([a, b]))
            pairs[key]["count"] += 1
            pairs[key]["channels"].add("email")

    # Phone pairs (caller -> called)
    phone_rows = (
        db.query(PhoneRecord.caller_number, PhoneRecord.called_number, PhoneRecord.duration_seconds)
        .filter(PhoneRecord.caller_number.isnot(None), PhoneRecord.called_number.isnot(None))
        .all()
    )
    for row in phone_rows:
        a = row.caller_number
        b = row.called_number
        if a and b and a != b:
            key = tuple(sorted([a, b]))
            pairs[key]["count"] += 1
            pairs[key]["channels"].add("phone")
            pairs[key]["total_duration"] += row.duration_seconds or 0

    # Convert to sorted list
    result_pairs = []
    for (a, b), data in sorted(pairs.items(), key=lambda x: -x[1]["count"]):
        result_pairs.append({
            "contact_a": a,
            "contact_b": b,
            "count": data["count"],
            "channels": sorted(data["channels"]),
            "total_duration_seconds": data["total_duration"],
        })

    # Top contacts by total communication count
    contact_counts: dict[str, int] = defaultdict(int)
    for (a, b), data in pairs.items():
        contact_counts[a] += data["count"]
        contact_counts[b] += data["count"]

    top_contacts = [
        {"contact": c, "total_communications": n}
        for c, n in sorted(contact_counts.items(), key=lambda x: -x[1])[:50]
    ]

    return {
        "pairs": result_pairs[:500],
        "total_pairs": len(result_pairs),
        "top_contacts": top_contacts,
    }


def get_new_contacts(
    db: Session,
    around_date: str,
    window_days: int = 7,
) -> dict[str, Any]:
    """Find contacts whose first communication is within N days of a key date.

    This is forensically critical — new contacts appearing around dates of interest
    (will changes, account modifications, suspicious events) are high-value leads.
    """
    try:
        center = datetime.fromisoformat(around_date)
    except ValueError:
        return {"error": f"Invalid date format: {around_date}"}

    window_start = center - timedelta(days=window_days)
    window_end = center + timedelta(days=window_days)

    new_contacts: list[dict] = []

    # Phone: find numbers whose earliest record falls in the window
    phone_first = (
        db.query(
            PhoneRecord.called_number,
            func.min(PhoneRecord.call_datetime).label("first_seen"),
            func.count().label("total_calls"),
        )
        .filter(PhoneRecord.called_number.isnot(None))
        .group_by(PhoneRecord.called_number)
        .having(func.min(PhoneRecord.call_datetime).between(window_start, window_end))
        .all()
    )
    for row in phone_first:
        new_contacts.append({
            "contact": row.called_number,
            "channel": "phone",
            "first_seen": str(row.first_seen),
            "total_interactions": row.total_calls,
            "days_from_key_date": abs((row.first_seen - center).days) if row.first_seen else None,
        })

    # Email: find senders whose earliest non-spam email falls in the window
    email_first = (
        db.query(
            EmailMessage.email_from,
            func.min(EmailMessage.email_date).label("first_seen"),
            func.count().label("total_emails"),
        )
        .filter(EmailMessage.email_from.isnot(None), EmailMessage.is_spam == False)
        .group_by(EmailMessage.email_from)
        .having(func.min(EmailMessage.email_date).between(window_start, window_end))
        .all()
    )
    for row in email_first:
        new_contacts.append({
            "contact": row.email_from,
            "channel": "email",
            "first_seen": str(row.first_seen),
            "total_interactions": row.total_emails,
            "days_from_key_date": abs((row.first_seen - center).days) if row.first_seen else None,
        })

    new_contacts.sort(key=lambda x: abs(x.get("days_from_key_date") or 999))

    return {
        "key_date": around_date,
        "window_days": window_days,
        "window_start": str(window_start),
        "window_end": str(window_end),
        "new_contacts": new_contacts,
        "total": len(new_contacts),
    }


def detect_burner_phones(db: Session) -> dict[str, Any]:
    """Detect potential burner phones using heuristics.

    Flags numbers that:
    - Are active for less than 30 days total
    - Have fewer than 5 unique contacts
    - Show sudden appearance and disappearance
    """
    # Get per-number stats
    number_stats = (
        db.query(
            PhoneRecord.called_number.label("number"),
            func.count().label("total_calls"),
            func.min(PhoneRecord.call_datetime).label("first_seen"),
            func.max(PhoneRecord.call_datetime).label("last_seen"),
        )
        .filter(PhoneRecord.called_number.isnot(None))
        .group_by(PhoneRecord.called_number)
        .all()
    )

    burners: list[dict] = []
    for row in number_stats:
        if not row.first_seen or not row.last_seen:
            continue

        active_days = (row.last_seen - row.first_seen).days + 1

        # Count unique contacts for this number
        unique_contacts = (
            db.query(func.count(func.distinct(PhoneRecord.caller_number)))
            .filter(PhoneRecord.called_number == row.number)
            .scalar() or 0
        )

        reasons: list[str] = []
        score = 0.0

        if active_days <= 30:
            reasons.append(f"Active only {active_days} day(s)")
            score += 0.4
        if unique_contacts <= 3:
            reasons.append(f"Only {unique_contacts} unique contact(s)")
            score += 0.3
        if row.total_calls <= 10:
            reasons.append(f"Low activity: {row.total_calls} total calls")
            score += 0.2

        if score >= 0.5:
            burners.append({
                "number": row.number,
                "active_days": active_days,
                "unique_contacts": unique_contacts,
                "total_calls": row.total_calls,
                "first_seen": str(row.first_seen),
                "last_seen": str(row.last_seen),
                "burner_score": round(min(score, 1.0), 2),
                "reasons": reasons,
            })

    burners.sort(key=lambda x: -x["burner_score"])

    return {
        "potential_burners": burners,
        "total": len(burners),
    }


def get_comm_timeline(
    db: Session,
    contact_a: str,
    contact_b: str,
) -> dict[str, Any]:
    """Get all communications between two specific contacts, chronologically."""
    events: list[dict] = []

    # Phone calls between these contacts
    phone_calls = (
        db.query(PhoneRecord)
        .filter(
            or_(
                (PhoneRecord.caller_number == contact_a) & (PhoneRecord.called_number == contact_b),
                (PhoneRecord.caller_number == contact_b) & (PhoneRecord.called_number == contact_a),
            )
        )
        .order_by(PhoneRecord.call_datetime)
        .all()
    )
    for call in phone_calls:
        events.append({
            "timestamp": str(call.call_datetime) if call.call_datetime else None,
            "channel": "phone",
            "direction": "outgoing" if call.caller_number == contact_a else "incoming",
            "duration_seconds": call.duration_seconds,
            "call_type": call.call_type,
        })

    # Emails between these contacts
    emails = (
        db.query(EmailMessage)
        .filter(
            or_(
                (EmailMessage.email_from.ilike(f"%{contact_a}%")) & (EmailMessage.email_to.ilike(f"%{contact_b}%")),
                (EmailMessage.email_from.ilike(f"%{contact_b}%")) & (EmailMessage.email_to.ilike(f"%{contact_a}%")),
            ),
            EmailMessage.is_spam == False,
        )
        .order_by(EmailMessage.email_date)
        .all()
    )
    for em in emails:
        events.append({
            "timestamp": str(em.email_date) if em.email_date else None,
            "channel": "email",
            "direction": "outgoing" if contact_a.lower() in (em.email_from or "").lower() else "incoming",
            "subject": em.email_subject,
            "body_preview": (em.body_preview or "")[:200],
        })

    events.sort(key=lambda x: x.get("timestamp") or "")

    return {
        "contact_a": contact_a,
        "contact_b": contact_b,
        "events": events,
        "total": len(events),
    }
