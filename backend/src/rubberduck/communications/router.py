"""API routes for communications — browse, filter, and analyze email messages."""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case as sql_case
from sqlalchemy.orm import Session

from rubberduck.db.models import EmailMessage, File
from rubberduck.db.sqlite import get_db

router = APIRouter(prefix="/api/communications", tags=["communications"])


@router.get("/messages")
def list_messages(
    classification: str | None = Query(None, description="Filter: personal, newsletter, notification, spam"),
    is_spam: bool | None = Query(None, description="Filter spam messages"),
    comm_type: str | None = Query(None, description="Filter: email, whatsapp, sms, call, social_media"),
    sender: str | None = Query(None, description="Filter by sender (partial match)"),
    search: str | None = Query(None, description="Search subject and body preview"),
    date_start: str | None = Query(None),
    date_end: str | None = Query(None),
    sort_by: str | None = Query("date", description="Sort: date, spam_score, sender"),
    sort_dir: str | None = Query("desc", description="Sort direction: asc, desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List email messages with filtering and spam detection."""
    q = db.query(EmailMessage)

    if classification:
        q = q.filter(EmailMessage.classification == classification)
    if is_spam is not None:
        q = q.filter(EmailMessage.is_spam == is_spam)
    if comm_type:
        q = q.filter(EmailMessage.comm_type == comm_type)
    if sender:
        q = q.filter(EmailMessage.email_from.ilike(f"%{sender}%"))
    if search:
        q = q.filter(
            (EmailMessage.email_subject.ilike(f"%{search}%"))
            | (EmailMessage.body_preview.ilike(f"%{search}%"))
        )
    if date_start:
        q = q.filter(EmailMessage.email_date >= date_start)
    if date_end:
        q = q.filter(EmailMessage.email_date <= date_end)

    total = q.count()

    # Sorting
    if sort_by == "spam_score":
        order_col = EmailMessage.spam_score
    elif sort_by == "sender":
        order_col = EmailMessage.email_from
    else:
        order_col = EmailMessage.email_date

    # Exclude records with no email metadata (binary files misidentified as .eml)
    q = q.filter(
        (EmailMessage.email_from.isnot(None)) | (EmailMessage.email_subject.isnot(None))
    )

    if sort_dir == "asc":
        q = q.order_by(order_col.asc().nullslast())
    else:
        q = q.order_by(order_col.desc().nullslast())

    messages = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_msg_dict(m) for m in messages],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/messages/{message_id}")
def get_message(message_id: str, db: Session = Depends(get_db)):
    """Get a single email message with full details."""
    msg = db.query(EmailMessage).get(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return _msg_dict(msg, full=True)


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get communication statistics — message counts by classification, sender, etc."""
    total = db.query(EmailMessage).count()
    if total == 0:
        return {
            "total_messages": 0,
            "by_classification": {},
            "by_comm_type": {},
            "spam_count": 0,
            "non_spam_count": 0,
            "top_senders": [],
            "date_range": None,
        }

    by_classification = dict(
        db.query(EmailMessage.classification, func.count())
        .group_by(EmailMessage.classification)
        .all()
    )

    by_comm_type = dict(
        db.query(EmailMessage.comm_type, func.count())
        .group_by(EmailMessage.comm_type)
        .all()
    )

    spam_count = db.query(EmailMessage).filter(EmailMessage.is_spam == True).count()

    # Top senders (non-spam)
    top_senders = (
        db.query(EmailMessage.email_from, func.count().label("cnt"))
        .filter(EmailMessage.is_spam == False)
        .filter(EmailMessage.email_from.isnot(None))
        .group_by(EmailMessage.email_from)
        .order_by(func.count().desc())
        .limit(20)
        .all()
    )

    # Date range
    date_min = db.query(func.min(EmailMessage.email_date)).scalar()
    date_max = db.query(func.max(EmailMessage.email_date)).scalar()

    return {
        "total_messages": total,
        "by_classification": by_classification,
        "by_comm_type": by_comm_type,
        "spam_count": spam_count,
        "non_spam_count": total - spam_count,
        "top_senders": [
            {"sender": s, "count": c} for s, c in top_senders
        ],
        "date_range": {
            "start": str(date_min) if date_min else None,
            "end": str(date_max) if date_max else None,
        },
    }


@router.get("/threads")
def get_threads(
    is_spam: bool | None = Query(False),
    sender: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Group messages by subject thread (Re: stripping)."""
    from sqlalchemy import func as fn

    q = db.query(
        func.replace(
            func.replace(
                func.replace(EmailMessage.email_subject, "Re: ", ""),
                "RE: ", "",
            ),
            "Fwd: ", "",
        ).label("thread_subject"),
        fn.count().label("message_count"),
        fn.min(EmailMessage.email_date).label("first_date"),
        fn.max(EmailMessage.email_date).label("last_date"),
        fn.group_concat(EmailMessage.email_from.distinct()).label("participants"),
    )

    if is_spam is not None:
        q = q.filter(EmailMessage.is_spam == is_spam)
    if sender:
        q = q.filter(EmailMessage.email_from.ilike(f"%{sender}%"))
    if date_start:
        q = q.filter(EmailMessage.email_date >= date_start)
    if date_end:
        q = q.filter(EmailMessage.email_date <= date_end)

    q = q.group_by("thread_subject").order_by(fn.max(EmailMessage.email_date).desc())

    total = q.count()
    threads = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [
            {
                "subject": t.thread_subject,
                "message_count": t.message_count,
                "first_date": str(t.first_date) if t.first_date else None,
                "last_date": str(t.last_date) if t.last_date else None,
                "participants": t.participants.split(",") if t.participants else [],
            }
            for t in threads
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/extract")
def extract_emails(
    reprocess: bool = Query(False, description="Re-extract all emails (clears existing)"),
    db: Session = Depends(get_db),
):
    """Extract individual EmailMessage records from all email files.

    This runs the spam classifier and creates per-email database records.
    """
    from rubberduck.evidence.email_extractor import extract_all_emails
    result = extract_all_emails(db, reprocess=reprocess)
    return result


@router.post("/extract/{file_id}")
def extract_emails_from_single_file(
    file_id: str,
    reprocess: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Extract EmailMessage records from a specific file."""
    from rubberduck.evidence.email_extractor import extract_emails_from_file

    file_record = db.query(File).get(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    result = extract_emails_from_file(db, file_record, reprocess=reprocess)
    db.commit()
    return result


def _msg_dict(msg: EmailMessage, full: bool = False) -> dict:
    """Convert EmailMessage to API dict."""
    d = {
        "id": msg.id,
        "file_id": msg.file_id,
        "message_index": msg.message_index,
        "email_from": msg.email_from,
        "email_to": msg.email_to,
        "email_subject": msg.email_subject,
        "email_date": str(msg.email_date) if msg.email_date else None,
        "is_spam": msg.is_spam,
        "spam_score": msg.spam_score,
        "classification": msg.classification,
        "comm_type": msg.comm_type,
        "has_attachments": msg.has_attachments,
        "attachment_count": msg.attachment_count,
        "body_length": msg.body_length,
    }
    if full:
        d["email_cc"] = msg.email_cc
        d["message_id"] = msg.message_id
        d["in_reply_to"] = msg.in_reply_to
        d["email_date_raw"] = msg.email_date_raw
        d["body_preview"] = msg.body_preview
        d["spam_reasons"] = json.loads(msg.spam_reasons) if msg.spam_reasons else []
        d["created_at"] = str(msg.created_at) if msg.created_at else None
    else:
        # Include a short body preview in list view too
        d["body_preview"] = (msg.body_preview or "")[:200]
    return d
