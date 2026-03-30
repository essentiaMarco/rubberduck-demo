"""Email parsers: EML (single message) and MBOX (mailbox)."""

import email
import email.utils
import logging
import mailbox
from email.policy import default as default_policy
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent

logger = logging.getLogger(__name__)


class EmailParser(BaseParser):
    """Parse a single EML file."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        with open(file_path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=default_policy)

        return _parse_message(msg)

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["message/rfc822"]


class MboxParser(BaseParser):
    """Parse MBOX mailbox files. Iterates one message at a time (constant memory)."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        mbox = mailbox.mbox(file_path)
        all_text_parts = []
        all_events = []
        all_entities = []
        message_count = 0

        try:
            for msg in mbox:
                result = _parse_message(msg)
                all_text_parts.append(result.text_content)
                all_events.extend(result.events)
                all_entities.extend(result.entities_hint)
                message_count += 1
        finally:
            mbox.close()

        return ParseResult(
            text_content="\n\n---\n\n".join(all_text_parts),
            metadata={"message_count": message_count},
            events=all_events,
            entities_hint=list(set(all_entities)),
            parser_name="MboxParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["application/mbox"]


def _parse_message(msg) -> ParseResult:
    """Parse a single email message into a ParseResult."""
    headers = {
        "from": str(msg.get("From", "")),
        "to": str(msg.get("To", "")),
        "cc": str(msg.get("Cc", "")),
        "bcc": str(msg.get("Bcc", "")),
        "subject": str(msg.get("Subject", "")),
        "date": str(msg.get("Date", "")),
        "message_id": str(msg.get("Message-ID", "")),
        "in_reply_to": str(msg.get("In-Reply-To", "")),
    }

    # Extract body
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "lxml")
                    body = soup.get_text(separator="\n", strip=True)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")

    # Build text representation
    text = f"From: {headers['from']}\nTo: {headers['to']}\n"
    if headers["cc"]:
        text += f"Cc: {headers['cc']}\n"
    text += f"Subject: {headers['subject']}\nDate: {headers['date']}\n\n{body}"

    # Attachment info
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            filename = part.get_filename()
            if filename:
                attachments.append({
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "size": len(part.get_payload(decode=True) or b""),
                })

    # Create timeline event
    events = []
    if headers["date"]:
        events.append(RawEvent(
            timestamp_raw=headers["date"],
            event_type="communication",
            event_subtype="email_sent",
            summary=f"Email: {headers['subject'][:100]}",
            actor=headers["from"],
            target=headers["to"],
            raw_data={"subject": headers["subject"], "has_attachments": len(attachments) > 0},
        ))

    # Entity hints
    entities_hint = []
    for field_name in ["from", "to", "cc", "bcc"]:
        val = headers[field_name]
        if val:
            # Parse email addresses
            for name, addr in email.utils.getaddresses([val]):
                if name:
                    entities_hint.append(name)
                if addr:
                    entities_hint.append(addr)

    return ParseResult(
        text_content=text,
        metadata={**headers, "attachment_count": len(attachments), "attachments": attachments},
        events=events,
        entities_hint=entities_hint,
        parser_name="EmailParser",
    )
