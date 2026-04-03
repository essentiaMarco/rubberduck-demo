"""WhatsApp chat export parser.

Handles WhatsApp's standard text export format:
    [DD/MM/YYYY, HH:MM:SS] Sender: Message text
    or
    DD/MM/YYYY, HH:MM - Sender: Message text

Also handles the format without brackets and various date separators.
"""

import re
import logging
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent

logger = logging.getLogger(__name__)

# WhatsApp message patterns (multiple format variants)
_PATTERNS = [
    # [DD/MM/YYYY, HH:MM:SS] Sender: Message
    re.compile(
        r"\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\]\s+(.*?):\s+(.*)",
    ),
    # DD/MM/YYYY, HH:MM - Sender: Message
    re.compile(
        r"(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\s*[-–]\s+(.*?):\s+(.*)",
    ),
    # MM/DD/YY, HH:MM AM/PM - Sender: Message (US format)
    re.compile(
        r"(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm])\s*[-–]\s+(.*?):\s+(.*)",
    ),
]

# System message patterns (not real messages from people)
_SYSTEM_PATTERNS = [
    re.compile(r"(messages and calls are end-to-end encrypted)", re.I),
    re.compile(r"(created group|changed the subject|added|removed|left)", re.I),
    re.compile(r"(message was deleted|this message was deleted)", re.I),
    re.compile(r"(missed voice call|missed video call)", re.I),
    re.compile(r"(your security code .* changed)", re.I),
]


def _is_system_message(text: str) -> bool:
    """Check if a message is a WhatsApp system message."""
    for pattern in _SYSTEM_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _parse_whatsapp_date(date_str: str, time_str: str) -> str:
    """Normalize WhatsApp date/time to an ISO-ish string for timeline parsing."""
    # Clean up
    date_str = date_str.strip()
    time_str = time_str.strip()
    return f"{date_str} {time_str}"


class WhatsAppParser(BaseParser):
    """Parse WhatsApp chat export text files."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")

        messages = []
        events = []
        entities_hint = set()
        current_msg = None

        for line in text.split("\n"):
            matched = False
            for pattern in _PATTERNS:
                m = pattern.match(line)
                if m:
                    # Save previous multi-line message
                    if current_msg:
                        messages.append(current_msg)

                    date_str, time_str, sender, message = m.groups()
                    sender = sender.strip()
                    message = message.strip()

                    timestamp_raw = _parse_whatsapp_date(date_str, time_str)
                    is_system = _is_system_message(message)

                    current_msg = {
                        "timestamp": timestamp_raw,
                        "sender": sender,
                        "message": message,
                        "is_system": is_system,
                    }

                    if not is_system:
                        entities_hint.add(sender)
                        events.append(RawEvent(
                            timestamp_raw=timestamp_raw,
                            event_type="communication",
                            event_subtype="whatsapp_message",
                            summary=f"WhatsApp: {sender}: {message[:100]}",
                            actor=sender,
                            raw_data={
                                "sender": sender,
                                "message": message[:500],
                                "comm_type": "whatsapp",
                            },
                            confidence=0.95,
                        ))

                    matched = True
                    break

            if not matched and current_msg:
                # Continuation line of previous message
                current_msg["message"] += "\n" + line

        # Don't forget the last message
        if current_msg:
            messages.append(current_msg)

        # Build text content with clear formatting
        text_parts = []
        for msg in messages:
            prefix = "[SYSTEM] " if msg["is_system"] else ""
            text_parts.append(
                f"[{msg['timestamp']}] {prefix}{msg['sender']}: {msg['message']}"
            )

        non_system = [m for m in messages if not m.get("is_system")]
        system_count = len(messages) - len(non_system)

        # Count unique senders
        senders = set(m["sender"] for m in non_system)

        return ParseResult(
            text_content="\n".join(text_parts),
            metadata={
                "message_count": len(messages),
                "non_system_messages": len(non_system),
                "system_messages": system_count,
                "participants": sorted(senders),
                "participant_count": len(senders),
                "comm_type": "whatsapp",
            },
            events=events,
            entities_hint=list(entities_hint),
            parser_name="WhatsAppParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        # WhatsApp exports are plain text, so we use extension-based detection
        return []

    @classmethod
    def detect_whatsapp(cls, file_path: Path) -> bool:
        """Heuristic to detect if a text file is a WhatsApp export."""
        try:
            # Read first few KB
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(4096)

            # Count pattern matches in the first few lines
            matches = 0
            for line in head.split("\n")[:20]:
                for pattern in _PATTERNS:
                    if pattern.match(line):
                        matches += 1
                        break

            # If >50% of first 20 lines match, it's likely a WhatsApp export
            return matches >= 3
        except Exception:
            return False
