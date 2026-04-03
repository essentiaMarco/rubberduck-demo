"""Extract individual EmailMessage records from parsed MBOX/EML files.

This module reads already-parsed email files and creates per-email database
records with spam classification, threading info, and communication metadata.
It runs as a post-processing step after the main parser pipeline.
"""

import email
import email.utils
import json
import logging
import mailbox
from datetime import datetime, timezone
from email.policy import default as default_policy
from pathlib import Path

from sqlalchemy.orm import Session

from rubberduck.db.models import EmailMessage, File
from rubberduck.evidence.spam_classifier import classify_email

logger = logging.getLogger(__name__)


def _parse_date(date_str: str) -> datetime | None:
    """Parse an RFC 2822 date string into a UTC datetime."""
    if not date_str:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _count_recipients(msg) -> int:
    """Count total recipients across To, Cc, Bcc."""
    count = 0
    for field in ["To", "Cc", "Bcc"]:
        val = str(msg.get(field, ""))
        if val:
            count += len(email.utils.getaddresses([val]))
    return max(count, 1)


def _extract_body_preview(msg, max_chars: int = 500) -> str:
    """Extract a text preview of the email body."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
            elif ct == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(
                            payload.decode("utf-8", errors="replace"), "lxml"
                        )
                        for tag in soup(["script", "style", "noscript"]):
                            tag.decompose()
                        body = soup.get_text(separator=" ", strip=True)
                    except Exception:
                        body = payload.decode("utf-8", errors="replace")[:max_chars]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            raw = payload.decode("utf-8", errors="replace")
            ct = msg.get_content_type()
            if ct == "text/html":
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw, "lxml")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    body = soup.get_text(separator=" ", strip=True)
                except Exception:
                    body = raw
            else:
                body = raw

    return body[:max_chars].strip()


def _get_body_length(msg) -> int:
    """Get approximate full body length in characters."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return len(payload)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return len(payload)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return len(payload)
    return 0


def _count_attachments(msg) -> tuple[bool, int]:
    """Return (has_attachments, attachment_count)."""
    count = 0
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_filename():
                count += 1
    return count > 0, count


def _get_headers_raw(msg) -> str:
    """Get raw header text for spam classification."""
    parts = []
    for key in msg.keys():
        parts.append(f"{key}: {msg[key]}")
    return "\n".join(parts)


def _detect_comm_type(msg) -> str:
    """Detect communication type from email content/headers.

    Checks for WhatsApp, SMS, call logs, etc. forwarded via email.
    """
    subject = str(msg.get("Subject", "")).lower()
    from_addr = str(msg.get("From", "")).lower()

    # WhatsApp chat exports (usually attached as .txt or forwarded)
    if "whatsapp" in subject or "whatsapp" in from_addr:
        return "whatsapp"

    # SMS/text message exports
    if any(kw in subject for kw in ["sms", "text message", "imessage"]):
        return "sms"

    # Call logs
    if any(kw in subject for kw in ["call log", "call history", "missed call", "voicemail"]):
        return "call"

    # Social media notifications
    if any(kw in from_addr for kw in ["facebook", "instagram", "twitter", "linkedin", "tiktok"]):
        return "social_media"

    # Calendar/meeting invites
    if any(kw in subject for kw in ["invitation:", "meeting:", "calendar"]):
        return "calendar"

    return "email"


def extract_emails_from_file(
    db: Session,
    file_record: File,
    *,
    reprocess: bool = False,
) -> dict:
    """Extract individual EmailMessage records from an EML or MBOX file.

    Args:
        db: Database session
        file_record: The File record to process
        reprocess: If True, delete existing EmailMessage records and re-extract

    Returns:
        Summary dict with counts
    """
    if file_record.file_ext not in (".eml", ".mbox"):
        return {"skipped": True, "reason": "not an email file"}

    # Find the original file path
    stored_path = Path(file_record.stored_path) if file_record.stored_path else None
    if not stored_path or not stored_path.exists():
        return {"error": "original file not found on disk"}

    # Clear existing records if reprocessing
    if reprocess:
        db.query(EmailMessage).filter(EmailMessage.file_id == file_record.id).delete()
        db.flush()

    # Check if already processed
    existing_count = (
        db.query(EmailMessage).filter(EmailMessage.file_id == file_record.id).count()
    )
    if existing_count > 0 and not reprocess:
        return {"skipped": True, "already_processed": existing_count}

    stats = {
        "total": 0,
        "spam": 0,
        "newsletter": 0,
        "notification": 0,
        "personal": 0,
        "errors": 0,
    }

    if file_record.file_ext == ".mbox":
        mbox = mailbox.mbox(str(stored_path))
        try:
            for idx, msg in enumerate(mbox):
                try:
                    _create_email_record(db, file_record.id, msg, idx, stats)
                except Exception as e:
                    logger.warning("Failed to extract email %d from %s: %s", idx, file_record.file_name, e)
                    stats["errors"] += 1

                # Commit in batches of 100
                if (idx + 1) % 100 == 0:
                    db.flush()
        finally:
            mbox.close()
    else:
        # Single .eml file
        with open(stored_path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=default_policy)
        try:
            _create_email_record(db, file_record.id, msg, 0, stats)
        except Exception as e:
            logger.warning("Failed to extract email from %s: %s", file_record.file_name, e)
            stats["errors"] += 1

    db.flush()
    return stats


def _create_email_record(
    db: Session,
    file_id: str,
    msg,
    index: int,
    stats: dict,
) -> EmailMessage:
    """Create a single EmailMessage record from an email.message.Message."""
    email_from = str(msg.get("From", ""))
    email_to = str(msg.get("To", ""))
    email_cc = str(msg.get("Cc", ""))
    subject = str(msg.get("Subject", ""))
    date_raw = str(msg.get("Date", ""))
    message_id = str(msg.get("Message-ID", ""))
    in_reply_to = str(msg.get("In-Reply-To", ""))

    email_date = _parse_date(date_raw)
    has_attach, attach_count = _count_attachments(msg)
    body_preview = _extract_body_preview(msg)
    body_length = _get_body_length(msg)
    headers_raw = _get_headers_raw(msg)
    recipient_count = _count_recipients(msg)
    comm_type = _detect_comm_type(msg)

    # Run spam classification
    spam_result = classify_email(
        email_from=email_from,
        email_to=email_to,
        subject=subject,
        body=body_preview,
        headers_raw=headers_raw,
        has_attachments=has_attach,
        recipient_count=recipient_count,
    )

    record = EmailMessage(
        file_id=file_id,
        message_index=index,
        message_id=message_id or None,
        in_reply_to=in_reply_to or None,
        email_from=email_from or None,
        email_to=email_to or None,
        email_cc=email_cc or None,
        email_subject=subject or None,
        email_date=email_date,
        email_date_raw=date_raw or None,
        body_preview=body_preview or None,
        body_length=body_length,
        has_attachments=has_attach,
        attachment_count=attach_count,
        is_spam=spam_result["is_spam"],
        spam_score=spam_result["spam_score"],
        spam_reasons=json.dumps(spam_result["spam_reasons"]),
        classification=spam_result["classification"],
        comm_type=comm_type,
    )
    db.add(record)

    stats["total"] += 1
    classification = spam_result["classification"]
    if classification in stats:
        stats[classification] += 1

    return record


def extract_all_emails(db: Session, *, reprocess: bool = False) -> dict:
    """Extract EmailMessage records from ALL email files in the database.

    This is the bulk operation for initial processing or re-processing.
    """
    email_files = (
        db.query(File)
        .filter(
            File.parse_status == "completed",
            File.file_ext.in_([".eml", ".mbox"]),
            File.stored_path.isnot(None),
        )
        .all()
    )

    totals = {
        "files_processed": 0,
        "files_skipped": 0,
        "total_emails": 0,
        "total_spam": 0,
        "total_personal": 0,
        "errors": 0,
    }

    for f in email_files:
        result = extract_emails_from_file(db, f, reprocess=reprocess)
        if result.get("skipped"):
            totals["files_skipped"] += 1
        elif result.get("error"):
            totals["errors"] += 1
        else:
            totals["files_processed"] += 1
            totals["total_emails"] += result.get("total", 0)
            totals["total_spam"] += result.get("spam", 0) + result.get("newsletter", 0) + result.get("notification", 0)
            totals["total_personal"] += result.get("personal", 0)

    db.commit()
    return totals
