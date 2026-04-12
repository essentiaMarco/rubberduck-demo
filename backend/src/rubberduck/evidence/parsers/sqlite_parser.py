"""Generic SQLite database parser for forensic evidence.

Handles arbitrary SQLite databases by enumerating tables and extracting
content. Detects known database types (iOS SMS, Contacts, Notes, etc.)
and delegates to specialized extractors.
"""

import json
import logging
import sqlite3
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent

logger = logging.getLogger(__name__)

# Known database signatures: table names -> description
_KNOWN_DB_TYPES: dict[frozenset[str], tuple[str, str]] = {
    frozenset({"message", "handle", "chat"}): ("ios_sms", "iOS Messages (SMS/iMessage)"),
    frozenset({"abperson", "abmultivalue"}): ("ios_contacts", "iOS Contacts (AddressBook)"),
    frozenset({"zicnotedata", "ziccloudsyncingobject"}): ("ios_notes", "iOS Notes"),
    frozenset({"calendaritem", "calendar"}): ("ios_calendar", "iOS Calendar"),
    frozenset({"call_history", "calls"}): ("call_log", "Call Log Database"),
    frozenset({"sms", "threads", "canonical_addresses"}): ("android_sms", "Android SMS/MMS"),
    frozenset({"contacts", "raw_contacts", "data"}): ("android_contacts", "Android Contacts"),
}


def _detect_db_type(tables: set[str]) -> tuple[str, str] | None:
    """Detect known database type by table names."""
    tables_lower = {t.lower() for t in tables}
    for sig, info in _KNOWN_DB_TYPES.items():
        if sig.issubset(tables_lower):
            return info
    return None


class GenericSqliteParser(BaseParser):
    """Parse any SQLite database for forensic evidence.

    Enumerates all tables, detects known types, and extracts content
    as searchable text with structured events where possible.
    """

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        text_parts: list[str] = []
        events: list[RawEvent] = []
        entities_hint: list[str] = []
        metadata: dict = {"db_type": "generic"}
        warnings: list[str] = []

        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        except sqlite3.Error as e:
            return ParseResult(
                text_content="", warnings=[f"Cannot open SQLite database: {e}"],
                parser_name="GenericSqliteParser",
            )

        try:
            # Enumerate tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row["name"] for row in cursor.fetchall()}
            metadata["tables"] = sorted(tables)
            metadata["table_count"] = len(tables)

            text_parts.append(f"=== SQLite Database: {file_path.name} ===")
            text_parts.append(f"Tables: {', '.join(sorted(tables))}\n")

            # Detect known type
            db_info = _detect_db_type(tables)
            if db_info:
                metadata["db_type"] = db_info[0]
                metadata["db_description"] = db_info[1]
                text_parts.append(f"Detected type: {db_info[1]}\n")

                # Specialized extraction
                if db_info[0] == "ios_sms":
                    self._extract_ios_sms(cursor, text_parts, events, entities_hint, warnings)
                elif db_info[0] == "android_sms":
                    self._extract_android_sms(cursor, text_parts, events, entities_hint, warnings)
                elif db_info[0] == "ios_contacts":
                    self._extract_ios_contacts(cursor, text_parts, entities_hint, warnings)
            else:
                # Generic: dump each table's content as text
                for table in sorted(tables):
                    if table.startswith("sqlite_"):
                        continue
                    self._dump_table(cursor, table, text_parts, warnings)

        except sqlite3.Error as e:
            warnings.append(f"Database parse error: {e}")
        finally:
            conn.close()

        return ParseResult(
            text_content="\n".join(text_parts),
            metadata=metadata,
            events=events,
            entities_hint=entities_hint,
            warnings=warnings,
            parser_name="GenericSqliteParser",
        )

    def _dump_table(self, cursor, table: str, text_parts: list[str], warnings: list[str]):
        """Dump table content as text (up to 1000 rows)."""
        try:
            cursor.execute(f'SELECT * FROM "{table}" LIMIT 1000')
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            text_parts.append(f"\n--- {table} ({len(rows)} rows) ---")
            text_parts.append(" | ".join(columns))

            for row in rows:
                values = []
                for val in row:
                    if val is None:
                        values.append("")
                    elif isinstance(val, bytes):
                        values.append(f"[{len(val)} bytes]")
                    else:
                        values.append(str(val)[:200])
                text_parts.append(" | ".join(values))

        except sqlite3.Error as e:
            warnings.append(f"Failed to read table {table}: {e}")

    def _extract_ios_sms(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract iOS Messages (SMS/iMessage) from sms.db."""
        try:
            cursor.execute("""
                SELECT m.ROWID, m.text, m.date, m.is_from_me, m.service,
                       h.id as handle_id
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                ORDER BY m.date DESC
                LIMIT 50000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"\n=== iOS Messages ({len(rows)} messages) ===\n")

            for row in rows:
                text = row["text"] or ""
                handle = row["handle_id"] or ""
                is_from_me = row["is_from_me"]
                service = row["service"] or "SMS"

                # iOS timestamps are seconds since 2001-01-01
                ts = None
                if row["date"]:
                    try:
                        from datetime import datetime, timezone
                        # Nanoseconds since 2001-01-01 for newer iOS
                        epoch_val = row["date"]
                        if epoch_val > 1e18:  # nanoseconds
                            epoch_val = epoch_val / 1e9
                        unix_ts = epoch_val + 978307200  # 2001-01-01 offset
                        ts = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
                    except (ValueError, OSError, OverflowError):
                        pass

                direction = "sent" if is_from_me else "received"
                ts_str = ts.isoformat() if ts else ""

                text_parts.append(f"[{ts_str}] {direction} ({service}) {handle}: {text[:500]}")

                if handle:
                    entities_hint.append(handle)

                if ts:
                    events.append(RawEvent(
                        timestamp_raw=ts_str,
                        event_type="communication",
                        event_subtype=f"sms_{direction}",
                        summary=f"{service} {direction}: {text[:100]}" if text else f"{service} {direction} to/from {handle}",
                        actor=handle if not is_from_me else None,
                        target=handle if is_from_me else None,
                        raw_data={"handle": handle, "service": service, "is_from_me": is_from_me},
                    ))

        except sqlite3.Error as e:
            warnings.append(f"iOS SMS extraction error: {e}")

    def _extract_android_sms(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract Android SMS from mmssms.db."""
        try:
            cursor.execute("""
                SELECT address, date, body, type, read
                FROM sms
                ORDER BY date DESC
                LIMIT 50000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"\n=== Android SMS ({len(rows)} messages) ===\n")

            for row in rows:
                address = row["address"] or ""
                body = row["body"] or ""
                # Android timestamps are Unix milliseconds
                ts = None
                if row["date"]:
                    try:
                        from datetime import datetime, timezone
                        ts = datetime.fromtimestamp(row["date"] / 1000, tz=timezone.utc)
                    except (ValueError, OSError):
                        pass

                msg_type = "received" if row["type"] == 1 else "sent"
                ts_str = ts.isoformat() if ts else ""

                text_parts.append(f"[{ts_str}] {msg_type} {address}: {body[:500]}")

                if address:
                    entities_hint.append(address)

                if ts:
                    events.append(RawEvent(
                        timestamp_raw=ts_str,
                        event_type="communication",
                        event_subtype=f"sms_{msg_type}",
                        summary=f"SMS {msg_type}: {body[:100]}" if body else f"SMS {msg_type} {address}",
                        actor=address if msg_type == "received" else None,
                        target=address if msg_type == "sent" else None,
                    ))

        except sqlite3.Error as e:
            warnings.append(f"Android SMS extraction error: {e}")

    def _extract_ios_contacts(self, cursor, text_parts, entities_hint, warnings):
        """Extract iOS contacts from AddressBook.sqlitedb."""
        try:
            cursor.execute("""
                SELECT p.ROWID, p.First, p.Last, p.Organization,
                       mv.value, mv.label
                FROM ABPerson p
                LEFT JOIN ABMultiValue mv ON p.ROWID = mv.record_id
                ORDER BY p.Last, p.First
            """)
            rows = cursor.fetchall()
            text_parts.append(f"\n=== iOS Contacts ({len(rows)} entries) ===\n")

            current_person = None
            for row in rows:
                name = f"{row['First'] or ''} {row['Last'] or ''}".strip()
                org = row["Organization"] or ""
                value = row["value"] or ""
                label = row["label"] or ""

                if name != current_person:
                    current_person = name
                    text_parts.append(f"\n{name}" + (f" ({org})" if org else ""))
                    if name:
                        entities_hint.append(name)
                    if org:
                        entities_hint.append(org)

                if value:
                    text_parts.append(f"  {label}: {value}")
                    entities_hint.append(value)

        except sqlite3.Error as e:
            warnings.append(f"iOS contacts extraction error: {e}")

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["application/x-sqlite3", "application/vnd.sqlite3"]
