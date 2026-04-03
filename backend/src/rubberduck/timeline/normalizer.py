"""Timestamp normalizer — converts heterogeneous timestamp formats to UTC."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from dateutil import parser as dateutil_parser
from dateutil.tz import gettz, tzutc

from rubberduck.config import settings

logger = logging.getLogger(__name__)

# Threshold to distinguish Unix seconds from milliseconds.
# Timestamps above 1e12 are treated as milliseconds (year ~2001 in ms).
_MS_THRESHOLD = 1e12


def normalize(raw_timestamp: str | int | float) -> dict:
    """Normalize a raw timestamp to a canonical dict.

    Returns
    -------
    dict with keys:
        utc       – ISO 8601 string in UTC (always present on success)
        original  – the original value as a string
        timezone  – IANA timezone string or ``None``
        assumed   – ``True`` if the timezone was assumed from settings
        error     – error message if parsing failed (utc will be ``None``)
    """
    original = str(raw_timestamp)
    result = {
        "utc": None,
        "original": original,
        "timezone": None,
        "assumed": False,
        "error": None,
    }

    try:
        dt = _parse(raw_timestamp)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Unparseable timestamp: {exc}"
        logger.warning("Could not parse timestamp %r: %s", raw_timestamp, exc)
        return result

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        # Naive datetime — assume the configured default timezone
        default_tz = gettz(settings.default_timezone)
        dt = dt.replace(tzinfo=default_tz)
        result["timezone"] = settings.default_timezone
        result["assumed"] = True
    else:
        # Timezone-aware — preserve the original zone name
        result["timezone"] = _tz_name(dt)
        result["assumed"] = False

    # Convert to UTC
    dt_utc = dt.astimezone(timezone.utc)
    result["utc"] = dt_utc.isoformat()
    return result


# ── Internal parse chain ──────────────────────────────────────


def _parse(raw: str | int | float) -> datetime:
    """Try multiple strategies in order until one succeeds."""
    # Numeric input — Unix epoch
    if isinstance(raw, (int, float)):
        return _from_epoch(raw)

    text = str(raw).strip()

    # Numeric string — Unix epoch
    if re.match(r"^-?\d+(\.\d+)?$", text):
        return _from_epoch(float(text))

    # ISO 8601 (handles most well-formed timestamps)
    try:
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        pass

    # RFC 2822 (email Date headers)
    try:
        return parsedate_to_datetime(text)
    except (ValueError, TypeError, IndexError):
        pass

    # Fallback: dateutil parser — handles US formats, natural language dates, etc.
    return dateutil_parser.parse(text)


def _from_epoch(value: float) -> datetime:
    """Convert a Unix epoch (seconds or milliseconds) to a UTC datetime."""
    if abs(value) > _MS_THRESHOLD:
        value = value / 1000.0
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _tz_name(dt: datetime) -> str | None:
    """Best-effort extraction of a timezone name from a datetime."""
    tz = dt.tzinfo
    if tz is None:
        return None
    if isinstance(tz, tzutc):
        return "UTC"
    name = getattr(tz, "zone", None) or getattr(tz, "_name", None)
    if name:
        return str(name)
    # Fall back to the UTC offset representation
    offset = tz.utcoffset(dt)
    if offset is not None:
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        hours, remainder = divmod(abs(total_seconds), 3600)
        minutes = remainder // 60
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    return None
