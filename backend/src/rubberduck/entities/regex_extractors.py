"""Regex-based entity extractors for structured data types.

Extracts emails, phone numbers, IP addresses, and URLs from free text.
All extractors return dicts in the same format as the spaCy NER pipeline
so they can be merged seamlessly downstream.
"""

import re
from typing import Any


_MAX_CHUNK = 500_000  # Max chars per regex chunk to bound backtracking
_CHUNK_OVERLAP = 200  # Overlap to catch matches spanning chunk boundaries


def _safe_finditer(pattern: re.Pattern, text: str):
    """Run regex finditer in bounded chunks to defend against ReDoS on large inputs."""
    if len(text) <= _MAX_CHUNK:
        yield from pattern.finditer(text)
        return
    seen_offsets: set[int] = set()
    for start in range(0, len(text), _MAX_CHUNK - _CHUNK_OVERLAP):
        chunk = text[start : start + _MAX_CHUNK]
        for m in pattern.finditer(chunk):
            absolute_offset = start + m.start()
            if absolute_offset not in seen_offsets:
                seen_offsets.add(absolute_offset)
                yield m

# ── Email (simplified RFC 5322) ───────────────────────────────

_EMAIL_RE = re.compile(
    r"""
    (?<![.\w@-])                           # no preceding word/dot/@ chars
    [a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+     # local part
    @                                       # at sign
    [a-zA-Z0-9]                            # domain start
    (?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?    # domain body
    (?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*  # subdomains
    \.[a-zA-Z]{2,}                         # TLD
    """,
    re.VERBOSE,
)


def extract_emails(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Extract email addresses from *text*."""
    results: list[dict[str, Any]] = []
    for m in _safe_finditer(_EMAIL_RE, text):
        results.append(
            {
                "text": m.group(),
                "entity_type": "email",
                "char_offset": m.start(),
                "confidence": 0.95,
                "extractor": "regex_email",
                "file_id": file_id,
            }
        )
    return results


# ── US Phone Numbers ──────────────────────────────────────────

_PHONE_RE = re.compile(
    r"""
    (?<!\d)                           # no leading digit
    (?:
        \+?1[\s.-]?                   # optional country code
    )?
    (?:
        \(?[2-9]\d{2}\)?              # area code with optional parens
        [\s.\-/]*                     # separator
        [2-9]\d{2}                    # exchange
        [\s.\-/]*                     # separator
        \d{4}                         # subscriber
    )
    (?!\d)                            # no trailing digit
    """,
    re.VERBOSE,
)


def extract_phones(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Extract US-format phone numbers from *text*."""
    results: list[dict[str, Any]] = []
    for m in _safe_finditer(_PHONE_RE, text):
        raw = m.group().strip()
        # Quick sanity: must contain at least 10 digits
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10 or len(digits) > 11:
            continue
        results.append(
            {
                "text": raw,
                "entity_type": "phone",
                "char_offset": m.start(),
                "confidence": 0.90,
                "extractor": "regex_phone",
                "file_id": file_id,
            }
        )
    return results


# ── IP Addresses ──────────────────────────────────────────────

_IPV4_RE = re.compile(
    r"""
    (?<!\d)                                  # no leading digit
    (?:25[0-5]|2[0-4]\d|[01]?\d\d?)         # octet 1
    \.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)       # octet 2
    \.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)       # octet 3
    \.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)       # octet 4
    (?!\d)                                   # no trailing digit
    """,
    re.VERBOSE,
)

# Simplified IPv6: matches full and compressed forms
_IPV6_RE = re.compile(
    r"""
    (?<![:\w])                               # no preceding colon or word
    (?:
        (?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}               # full
        | (?:[0-9a-fA-F]{1,4}:){1,7}:                           # trailing ::
        | (?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}          # :: in middle
        | (?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}
        | (?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}
        | (?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}
        | (?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}
        | [0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}
        | ::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}         # :: prefix
        | ::                                                      # all zeros
    )
    (?![:\w])                                # no trailing colon or word
    """,
    re.VERBOSE,
)


def extract_ips(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Extract IPv4 and IPv6 addresses from *text*."""
    results: list[dict[str, Any]] = []

    for m in _safe_finditer(_IPV4_RE, text):
        results.append(
            {
                "text": m.group(),
                "entity_type": "ip",
                "char_offset": m.start(),
                "confidence": 0.95,
                "extractor": "regex_ip",
                "file_id": file_id,
            }
        )

    for m in _safe_finditer(_IPV6_RE, text):
        addr = m.group()
        # Skip if it looks like it was already captured as part of a URL
        if len(addr) < 3:
            continue
        results.append(
            {
                "text": addr,
                "entity_type": "ip",
                "char_offset": m.start(),
                "confidence": 0.90,
                "extractor": "regex_ip",
                "file_id": file_id,
            }
        )

    return results


# ── URLs ──────────────────────────────────────────────────────

_URL_RE = re.compile(
    r"""
    https?://                                           # scheme
    (?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*  # subdomains
    [a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?     # domain
    \.[a-zA-Z]{2,}                                      # TLD
    (?::\d{1,5})?                                       # optional port
    (?:/[^\s<>"')\]]*)?                                  # optional path
    """,
    re.VERBOSE,
)


def extract_urls(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Extract HTTP/HTTPS URLs from *text*."""
    results: list[dict[str, Any]] = []
    for m in _safe_finditer(_URL_RE, text):
        url = m.group().rstrip(".,;:!?")  # strip trailing punctuation
        results.append(
            {
                "text": url,
                "entity_type": "url",
                "char_offset": m.start(),
                "confidence": 0.95,
                "extractor": "regex_url",
                "file_id": file_id,
            }
        )
    return results


# ── Aggregate extractor ──────────────────────────────────────

def extract_all(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Run all regex extractors and return a combined list of mentions."""
    results: list[dict[str, Any]] = []
    results.extend(extract_emails(text, file_id))
    results.extend(extract_phones(text, file_id))
    results.extend(extract_ips(text, file_id))
    results.extend(extract_urls(text, file_id))
    return results
