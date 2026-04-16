"""Browser database forensic parser — Chrome, Firefox, Safari SQLite databases.

Extracts browsing history, saved credentials, bookmarks, downloads,
autofill data, and cookies from browser profile databases.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent

logger = logging.getLogger(__name__)

# Chrome epoch: Jan 1, 1601 (microseconds)
_CHROME_EPOCH_OFFSET = 11644473600 * 1_000_000
# Firefox epoch: same as Unix but in microseconds
_FIREFOX_EPOCH_US = True


def _chrome_ts_to_datetime(chrome_ts: int) -> datetime | None:
    """Convert Chrome/Chromium timestamp (microseconds since 1601-01-01) to datetime."""
    if not chrome_ts or chrome_ts <= 0:
        return None
    try:
        unix_us = chrome_ts - _CHROME_EPOCH_OFFSET
        return datetime.fromtimestamp(unix_us / 1_000_000, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _firefox_ts_to_datetime(firefox_ts: int) -> datetime | None:
    """Convert Firefox timestamp (microseconds since Unix epoch) to datetime."""
    if not firefox_ts or firefox_ts <= 0:
        return None
    try:
        return datetime.fromtimestamp(firefox_ts / 1_000_000, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _safari_ts_to_datetime(safari_ts: float) -> datetime | None:
    """Convert Safari/CoreData timestamp (seconds since 2001-01-01) to datetime."""
    if not safari_ts:
        return None
    try:
        # CoreData epoch = 2001-01-01 00:00:00 UTC
        unix_ts = safari_ts + 978307200
        return datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _detect_browser(cursor: sqlite3.Cursor) -> str | None:
    """Detect which browser owns this SQLite database by table names."""
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0].lower() for row in cursor.fetchall()}
    except sqlite3.Error:
        return None

    # Chrome/Chromium: "urls", "visits", "keyword_search_terms"
    if "urls" in tables and ("visits" in tables or "keyword_search_terms" in tables):
        return "chrome_history"
    # Chrome Login Data: "logins"
    if "logins" in tables and "stats" in tables:
        return "chrome_logins"
    # Chrome Cookies
    if "cookies" in tables and "meta" in tables:
        return "chrome_cookies"
    # Chrome Web Data (autofill)
    if "autofill" in tables:
        return "chrome_autofill"
    # Firefox places.sqlite
    if "moz_places" in tables and "moz_historyvisits" in tables:
        return "firefox_places"
    # Firefox cookies
    if "moz_cookies" in tables:
        return "firefox_cookies"
    # Safari History.db
    if "history_items" in tables and "history_visits" in tables:
        return "safari_history"

    return None


class BrowserDbParser(BaseParser):
    """Parse browser SQLite databases for forensic evidence.

    Detects Chrome, Firefox, and Safari databases by table structure.
    Extracts history, saved credentials, bookmarks, cookies, autofill.
    """

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        text_parts: list[str] = []
        events: list[RawEvent] = []
        entities_hint: list[str] = []
        metadata: dict = {"browser": "unknown", "db_type": "unknown"}
        warnings: list[str] = []

        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
        except sqlite3.Error as e:
            return ParseResult(
                text_content="",
                warnings=[f"Cannot open SQLite database: {e}"],
                parser_name="BrowserDbParser",
            )

        try:
            db_type = _detect_browser(cursor)
            if not db_type:
                conn.close()
                # Fall through to GenericSqliteParser for non-browser SQLite files
                from rubberduck.evidence.parsers.sqlite_parser import GenericSqliteParser
                return GenericSqliteParser().parse(file_path, **kwargs)

            metadata["db_type"] = db_type

            if db_type == "chrome_history":
                metadata["browser"] = "chrome"
                self._parse_chrome_history(cursor, text_parts, events, entities_hint, warnings)
            elif db_type == "chrome_logins":
                metadata["browser"] = "chrome"
                self._parse_chrome_logins(cursor, text_parts, events, entities_hint, warnings)
            elif db_type == "chrome_cookies":
                metadata["browser"] = "chrome"
                self._parse_chrome_cookies(cursor, text_parts, events, entities_hint, warnings)
            elif db_type == "chrome_autofill":
                metadata["browser"] = "chrome"
                self._parse_chrome_autofill(cursor, text_parts, events, entities_hint, warnings)
            elif db_type == "firefox_places":
                metadata["browser"] = "firefox"
                self._parse_firefox_places(cursor, text_parts, events, entities_hint, warnings)
            elif db_type == "firefox_cookies":
                metadata["browser"] = "firefox"
                self._parse_firefox_cookies(cursor, text_parts, events, entities_hint, warnings)
            elif db_type == "safari_history":
                metadata["browser"] = "safari"
                self._parse_safari_history(cursor, text_parts, events, entities_hint, warnings)

        except sqlite3.Error as e:
            warnings.append(f"Database parse error: {e}")
        finally:
            conn.close()

        metadata["event_count"] = len(events)
        metadata["entity_hints"] = len(entities_hint)

        return ParseResult(
            text_content="\n".join(text_parts),
            metadata=metadata,
            events=events,
            entities_hint=entities_hint,
            warnings=warnings,
            parser_name="BrowserDbParser",
        )

    # ── Chrome History ───────────────────────────────────────

    def _parse_chrome_history(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract browsing history from Chrome History database."""
        try:
            cursor.execute("""
                SELECT u.url, u.title, v.visit_time, v.transition
                FROM visits v JOIN urls u ON v.url = u.id
                ORDER BY v.visit_time DESC
                LIMIT 50000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Chrome Browsing History ({len(rows)} visits) ===\n")

            for row in rows:
                url = row["url"] or ""
                title = row["title"] or ""
                dt = _chrome_ts_to_datetime(row["visit_time"])
                ts_str = dt.isoformat() if dt else ""

                text_parts.append(f"[{ts_str}] {title}\n  {url}")
                entities_hint.append(url)

                if dt:
                    events.append(RawEvent(
                        timestamp_raw=ts_str,
                        event_type="digital_activity",
                        event_subtype="page_visit",
                        summary=f"Visited: {title[:100]}" if title else f"Visited: {url[:100]}",
                        raw_data={"url": url, "title": title},
                    ))

            # Also extract search terms
            try:
                cursor.execute("""
                    SELECT term, url_id FROM keyword_search_terms
                    ORDER BY url_id DESC LIMIT 10000
                """)
                search_rows = cursor.fetchall()
                if search_rows:
                    text_parts.append(f"\n=== Chrome Search Terms ({len(search_rows)}) ===\n")
                    for sr in search_rows:
                        text_parts.append(f"Search: {sr['term']}")
            except sqlite3.Error:
                pass  # keyword_search_terms may not exist

            # Downloads
            try:
                cursor.execute("""
                    SELECT target_path, tab_url, start_time, total_bytes, mime_type
                    FROM downloads
                    ORDER BY start_time DESC LIMIT 5000
                """)
                dl_rows = cursor.fetchall()
                if dl_rows:
                    text_parts.append(f"\n=== Chrome Downloads ({len(dl_rows)}) ===\n")
                    for dl in dl_rows:
                        dt = _chrome_ts_to_datetime(dl["start_time"])
                        ts_str = dt.isoformat() if dt else ""
                        text_parts.append(
                            f"[{ts_str}] {dl['target_path']}\n"
                            f"  From: {dl['tab_url']}\n"
                            f"  Size: {dl['total_bytes']} bytes, Type: {dl['mime_type']}"
                        )
                        if dt:
                            events.append(RawEvent(
                                timestamp_raw=ts_str,
                                event_type="file_activity",
                                event_subtype="download",
                                summary=f"Downloaded: {Path(dl['target_path'] or '').name}",
                                raw_data={"url": dl["tab_url"], "path": dl["target_path"],
                                          "size": dl["total_bytes"], "mime": dl["mime_type"]},
                            ))
            except sqlite3.Error:
                pass  # downloads table may not exist

        except sqlite3.Error as e:
            warnings.append(f"Chrome history parse error: {e}")

    # ── Chrome Saved Logins ──────────────────────────────────

    def _parse_chrome_logins(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract saved credentials from Chrome Login Data database."""
        try:
            cursor.execute("""
                SELECT origin_url, username_value, date_created, date_last_used,
                       times_used, password_value
                FROM logins
                ORDER BY date_last_used DESC
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Chrome Saved Credentials ({len(rows)}) ===\n")
            text_parts.append("NOTE: Passwords are encrypted with OS keychain. "
                              "Decryption requires access to the original machine.\n")

            for row in rows:
                url = row["origin_url"] or ""
                username = row["username_value"] or ""
                dt_created = _chrome_ts_to_datetime(row["date_created"])
                dt_used = _chrome_ts_to_datetime(row["date_last_used"])
                times_used = row["times_used"] or 0

                # Check if password blob is present (even if encrypted)
                has_password = bool(row["password_value"])

                text_parts.append(
                    f"URL: {url}\n"
                    f"  Username: {username}\n"
                    f"  Created: {dt_created.isoformat() if dt_created else 'unknown'}\n"
                    f"  Last used: {dt_used.isoformat() if dt_used else 'unknown'}\n"
                    f"  Times used: {times_used}\n"
                    f"  Password stored: {'YES (encrypted)' if has_password else 'NO'}"
                )

                entities_hint.append(url)
                if username:
                    entities_hint.append(username)

                ts = (dt_used or dt_created)
                if ts:
                    events.append(RawEvent(
                        timestamp_raw=ts.isoformat(),
                        event_type="digital_activity",
                        event_subtype="saved_credential",
                        summary=f"Saved login: {username}@{url[:60]}",
                        actor=username or None,
                        raw_data={"url": url, "username": username,
                                  "times_used": times_used, "has_password": has_password},
                    ))

        except sqlite3.Error as e:
            warnings.append(f"Chrome logins parse error: {e}")

    # ── Chrome Cookies ───────────────────────────────────────

    def _parse_chrome_cookies(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract cookies — focus on session/auth cookies for account mapping."""
        try:
            cursor.execute("""
                SELECT host_key, name, value, creation_utc, last_access_utc, is_persistent
                FROM cookies
                ORDER BY last_access_utc DESC
                LIMIT 10000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Chrome Cookies ({len(rows)}) ===\n")

            # Group by domain for readability
            domains: dict[str, list] = {}
            for row in rows:
                host = row["host_key"] or ""
                domains.setdefault(host, []).append(row)
                entities_hint.append(host)

            for domain, cookies in sorted(domains.items(), key=lambda x: -len(x[1]))[:100]:
                text_parts.append(f"\n{domain} ({len(cookies)} cookies)")
                for c in cookies[:10]:
                    name = c["name"]
                    # Flag session/auth cookies
                    is_auth = any(kw in name.lower() for kw in
                                  ("session", "token", "auth", "sid", "jwt", "csrf",
                                   "login", "user", "account"))
                    marker = " [AUTH]" if is_auth else ""
                    text_parts.append(f"  {name}{marker}")

        except sqlite3.Error as e:
            warnings.append(f"Chrome cookies parse error: {e}")

    # ── Chrome Autofill ──────────────────────────────────────

    def _parse_chrome_autofill(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract autofill data — may contain names, addresses, phone numbers."""
        try:
            cursor.execute("""
                SELECT name, value, count, date_created, date_last_used
                FROM autofill
                ORDER BY count DESC
                LIMIT 5000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Chrome Autofill ({len(rows)} entries) ===\n")

            for row in rows:
                field_name = row["name"] or ""
                value = row["value"] or ""
                count = row["count"] or 0
                dt_last = _chrome_ts_to_datetime(row["date_last_used"])

                text_parts.append(f"  {field_name}: {value} (used {count}x)")
                entities_hint.append(value)

                # Flag potentially sensitive fields
                sensitive_fields = {"name", "email", "phone", "address", "city",
                                    "state", "zip", "card", "ccnumber", "ssn"}
                if any(kw in field_name.lower() for kw in sensitive_fields):
                    if dt_last:
                        events.append(RawEvent(
                            timestamp_raw=dt_last.isoformat(),
                            event_type="digital_activity",
                            event_subtype="autofill_entry",
                            summary=f"Autofill: {field_name}={value[:50]}",
                            raw_data={"field": field_name, "value": value, "count": count},
                        ))

        except sqlite3.Error as e:
            warnings.append(f"Chrome autofill parse error: {e}")

    # ── Firefox History ──────────────────────────────────────

    def _parse_firefox_places(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract Firefox browsing history and bookmarks from places.sqlite."""
        try:
            # History visits
            cursor.execute("""
                SELECT p.url, p.title, v.visit_date, v.visit_type
                FROM moz_historyvisits v
                JOIN moz_places p ON v.place_id = p.id
                ORDER BY v.visit_date DESC
                LIMIT 50000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Firefox Browsing History ({len(rows)} visits) ===\n")

            for row in rows:
                url = row["url"] or ""
                title = row["title"] or ""
                dt = _firefox_ts_to_datetime(row["visit_date"])
                ts_str = dt.isoformat() if dt else ""

                text_parts.append(f"[{ts_str}] {title}\n  {url}")
                entities_hint.append(url)

                if dt:
                    events.append(RawEvent(
                        timestamp_raw=ts_str,
                        event_type="digital_activity",
                        event_subtype="page_visit",
                        summary=f"Visited: {title[:100]}" if title else f"Visited: {url[:100]}",
                        raw_data={"url": url, "title": title, "browser": "firefox"},
                    ))

            # Bookmarks
            try:
                cursor.execute("""
                    SELECT b.title, p.url, b.dateAdded
                    FROM moz_bookmarks b
                    JOIN moz_places p ON b.fk = p.id
                    WHERE b.type = 1
                    ORDER BY b.dateAdded DESC
                    LIMIT 10000
                """)
                bm_rows = cursor.fetchall()
                if bm_rows:
                    text_parts.append(f"\n=== Firefox Bookmarks ({len(bm_rows)}) ===\n")
                    for bm in bm_rows:
                        title = bm["title"] or ""
                        url = bm["url"] or ""
                        dt = _firefox_ts_to_datetime(bm["dateAdded"])
                        text_parts.append(f"[{dt.isoformat() if dt else ''}] {title}: {url}")
                        entities_hint.append(url)

                        if dt:
                            events.append(RawEvent(
                                timestamp_raw=dt.isoformat(),
                                event_type="digital_activity",
                                event_subtype="bookmark_created",
                                summary=f"Bookmarked: {title[:80]}",
                                raw_data={"url": url, "title": title},
                            ))
            except sqlite3.Error:
                pass

        except sqlite3.Error as e:
            warnings.append(f"Firefox places parse error: {e}")

    # ── Firefox Cookies ──────────────────────────────────────

    def _parse_firefox_cookies(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract Firefox cookies from cookies.sqlite."""
        try:
            cursor.execute("""
                SELECT host, name, value, creationTime, lastAccessed, isSecure
                FROM moz_cookies
                ORDER BY lastAccessed DESC
                LIMIT 10000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Firefox Cookies ({len(rows)}) ===\n")

            domains: dict[str, int] = {}
            for row in rows:
                host = row["host"] or ""
                domains[host] = domains.get(host, 0) + 1
                entities_hint.append(host)

            for domain, count in sorted(domains.items(), key=lambda x: -x[1])[:100]:
                text_parts.append(f"  {domain}: {count} cookies")

        except sqlite3.Error as e:
            warnings.append(f"Firefox cookies parse error: {e}")

    # ── Safari History ───────────────────────────────────────

    def _parse_safari_history(self, cursor, text_parts, events, entities_hint, warnings):
        """Extract Safari browsing history from History.db."""
        try:
            cursor.execute("""
                SELECT hi.url, hv.title, hv.visit_time
                FROM history_visits hv
                JOIN history_items hi ON hv.history_item = hi.id
                ORDER BY hv.visit_time DESC
                LIMIT 50000
            """)
            rows = cursor.fetchall()
            text_parts.append(f"=== Safari Browsing History ({len(rows)} visits) ===\n")

            for row in rows:
                url = row["url"] or ""
                title = row["title"] or ""
                dt = _safari_ts_to_datetime(row["visit_time"])
                ts_str = dt.isoformat() if dt else ""

                text_parts.append(f"[{ts_str}] {title}\n  {url}")
                entities_hint.append(url)

                if dt:
                    events.append(RawEvent(
                        timestamp_raw=ts_str,
                        event_type="digital_activity",
                        event_subtype="page_visit",
                        summary=f"Visited: {title[:100]}" if title else f"Visited: {url[:100]}",
                        raw_data={"url": url, "title": title, "browser": "safari"},
                    ))

        except sqlite3.Error as e:
            warnings.append(f"Safari history parse error: {e}")

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["application/x-sqlite3", "application/vnd.sqlite3"]
