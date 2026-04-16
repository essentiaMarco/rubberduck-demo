"""Forensic alert rule engine and watchlist matcher.

Generates ForensicAlert records when evidence matches investigative rules
or user-defined watchlist terms. Alerts are the primary mechanism for
surfacing clues to investigators automatically.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from rubberduck.db.models import (
    File,
    ForensicAlert,
    ForensicSecret,
    WatchlistEntry,
)

logger = logging.getLogger(__name__)


# ── Alert rule definitions ───────────────────────────────────


@dataclass
class AlertRule:
    """A single automated alert rule."""

    name: str
    description: str
    alert_type: str
    severity: str
    check_fn: Callable[[Session, str | None], list[dict[str, Any]]]


def _check_critical_secrets(db: Session, file_id: str | None = None) -> list[dict]:
    """Flag critical-severity secrets (private keys, DB creds, cloud keys)."""
    query = db.query(ForensicSecret).filter(
        ForensicSecret.severity == "critical",
        ForensicSecret.dismissed == False,
    )
    if file_id:
        query = query.filter(ForensicSecret.file_id == file_id)

    results = []
    for secret in query.all():
        results.append({
            "title": f"Critical secret found: {secret.secret_type}",
            "description": (
                f"{secret.secret_type} discovered in evidence file. "
                f"Masked value: {secret.masked_value}. "
                f"Detection: {secret.detection_method} (confidence {secret.confidence:.0%})."
            ),
            "evidence_file_id": secret.file_id,
            "related_ids": json.dumps([secret.id]),
        })
    return results


def _check_high_severity_secrets(db: Session, file_id: str | None = None) -> list[dict]:
    """Flag high-severity secrets (passwords, tokens, crypto wallets)."""
    query = db.query(ForensicSecret).filter(
        ForensicSecret.severity == "high",
        ForensicSecret.dismissed == False,
    )
    if file_id:
        query = query.filter(ForensicSecret.file_id == file_id)

    results = []
    for secret in query.all():
        results.append({
            "title": f"Secret detected: {secret.secret_type}",
            "description": (
                f"{secret.secret_type} found. Masked: {secret.masked_value}. "
                f"Category: {secret.secret_category}."
            ),
            "evidence_file_id": secret.file_id,
            "related_ids": json.dumps([secret.id]),
        })
    return results


def _check_crypto_wallets(db: Session, file_id: str | None = None) -> list[dict]:
    """Flag cryptocurrency wallet addresses — potential hidden assets."""
    query = db.query(ForensicSecret).filter(
        ForensicSecret.secret_category == "crypto_wallet",
        ForensicSecret.dismissed == False,
    )
    if file_id:
        query = query.filter(ForensicSecret.file_id == file_id)

    results = []
    for secret in query.all():
        results.append({
            "title": f"Cryptocurrency wallet: {secret.secret_type}",
            "description": (
                f"Crypto wallet address found: {secret.masked_value}. "
                f"This may indicate hidden digital assets requiring investigation. "
                f"Consider querying the blockchain for transaction history."
            ),
            "evidence_file_id": secret.file_id,
            "related_ids": json.dumps([secret.id]),
        })
    return results


def _check_encrypted_files(db: Session, file_id: str | None = None) -> list[dict]:
    """Flag files that failed parsing due to encryption/password protection."""
    query = db.query(File).filter(
        File.parse_status == "failed",
    )
    if file_id:
        query = query.filter(File.id == file_id)

    results = []
    for f in query.all():
        error = (f.parse_error or "").lower()
        if any(kw in error for kw in ("encrypt", "password", "protected", "locked")):
            results.append({
                "title": f"Encrypted/protected file: {f.file_name}",
                "description": (
                    f"File '{f.file_name}' ({f.mime_type}) could not be parsed — "
                    f"appears to be password-protected or encrypted. "
                    f"Error: {f.parse_error}. May require warrant for decryption."
                ),
                "evidence_file_id": f.id,
            })
    return results


def _check_file_type_mismatch(db: Session, file_id: str | None = None) -> list[dict]:
    """Flag files where extension doesn't match detected MIME type."""
    query = db.query(File).filter(
        File.mime_type.isnot(None),
        File.file_ext.isnot(None),
    )
    if file_id:
        query = query.filter(File.id == file_id)

    # Known safe mismatches to ignore
    safe_pairs = {
        (".json", "text/plain"), (".csv", "text/plain"),
        (".txt", "text/html"), (".log", "text/plain"),
        (".md", "text/plain"), (".mbox", "text/plain"),
        (".eml", "text/plain"), (".xml", "text/html"),
    }

    results = []
    mime_ext_map = {
        "image/jpeg": {".jpg", ".jpeg"},
        "image/png": {".png"},
        "image/gif": {".gif"},
        "application/pdf": {".pdf"},
        "application/zip": {".zip"},
        "application/x-tar": {".tar"},
        "application/gzip": {".gz", ".tgz"},
        "application/x-rar-compressed": {".rar"},
        "application/x-7z-compressed": {".7z"},
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    }

    for f in query.all():
        ext = f.file_ext.lower()
        mime = f.mime_type.lower()

        if (ext, mime) in safe_pairs:
            continue

        expected_exts = mime_ext_map.get(mime)
        if expected_exts and ext not in expected_exts:
            results.append({
                "title": f"File type mismatch: {f.file_name}",
                "description": (
                    f"File '{f.file_name}' has extension '{ext}' but MIME type "
                    f"is '{mime}'. Expected extensions: {expected_exts}. "
                    f"This could indicate a deliberately disguised file."
                ),
                "evidence_file_id": f.id,
            })
    return results


# ── Rule registry ────────────────────────────────────────────

ALERT_RULES: list[AlertRule] = [
    AlertRule(
        name="critical_secrets",
        description="Private keys, cloud credentials, database connection strings",
        alert_type="secret_found",
        severity="critical",
        check_fn=_check_critical_secrets,
    ),
    AlertRule(
        name="high_secrets",
        description="Passwords, tokens, and auth credentials",
        alert_type="secret_found",
        severity="high",
        check_fn=_check_high_severity_secrets,
    ),
    AlertRule(
        name="crypto_wallets",
        description="Cryptocurrency wallet addresses — potential hidden assets",
        alert_type="secret_found",
        severity="high",
        check_fn=_check_crypto_wallets,
    ),
    AlertRule(
        name="encrypted_files",
        description="Password-protected or encrypted files",
        alert_type="encrypted_file",
        severity="high",
        check_fn=_check_encrypted_files,
    ),
    AlertRule(
        name="file_type_mismatch",
        description="Files whose extension doesn't match actual content type",
        alert_type="file_mismatch",
        severity="medium",
        check_fn=_check_file_type_mismatch,
    ),
]


# ── Rule engine ──────────────────────────────────────────────


def run_alert_rules(
    db: Session,
    file_id: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate all alert rules and create ForensicAlert records.

    De-duplicates against existing alerts to avoid spamming.
    """
    created = 0
    skipped = 0
    errors = 0

    for rule in ALERT_RULES:
        try:
            findings = rule.check_fn(db, file_id)
            for finding in findings:
                # De-duplicate: skip if same title + file already exists
                existing = (
                    db.query(ForensicAlert)
                    .filter(
                        ForensicAlert.title == finding["title"],
                        ForensicAlert.evidence_file_id == finding.get("evidence_file_id"),
                    )
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                alert = ForensicAlert(
                    case_id=case_id,
                    alert_type=rule.alert_type,
                    severity=rule.severity,
                    title=finding["title"],
                    description=finding.get("description"),
                    evidence_file_id=finding.get("evidence_file_id"),
                    entity_id=finding.get("entity_id"),
                    related_ids=finding.get("related_ids"),
                    auto_generated=True,
                    rule_name=rule.name,
                )
                db.add(alert)
                created += 1

        except Exception as exc:
            logger.error("Alert rule '%s' failed: %s", rule.name, exc)
            errors += 1

    if created:
        db.commit()

    return {
        "rules_evaluated": len(ALERT_RULES),
        "alerts_created": created,
        "duplicates_skipped": skipped,
        "errors": errors,
    }


# ── Watchlist matching ───────────────────────────────────────


def check_watchlist(
    db: Session,
    text: str,
    file_id: str,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Check text against all active watchlist entries.

    Creates ForensicAlert records for any matches found.
    """
    entries = db.query(WatchlistEntry).filter(WatchlistEntry.active == True).all()
    if not entries:
        return {"entries_checked": 0, "matches": 0}

    matches = 0
    for entry in entries:
        try:
            if entry.is_regex:
                pattern = re.compile(entry.term, re.IGNORECASE)
                found = bool(pattern.search(text))
            else:
                found = entry.term.lower() in text.lower()
        except re.error:
            logger.warning("Invalid watchlist regex: %s", entry.term)
            continue

        if found:
            # De-duplicate
            existing = (
                db.query(ForensicAlert)
                .filter(
                    ForensicAlert.alert_type == "watchlist_hit",
                    ForensicAlert.rule_name == f"watchlist:{entry.id}",
                    ForensicAlert.evidence_file_id == file_id,
                )
                .first()
            )
            if existing:
                continue

            alert = ForensicAlert(
                case_id=case_id or entry.case_id,
                alert_type="watchlist_hit",
                severity=entry.severity or "high",
                title=f"Watchlist match: '{entry.term}'",
                description=(
                    f"Watchlist term '{entry.term}' "
                    f"({'regex' if entry.is_regex else 'keyword'}) "
                    f"matched in evidence file. Category: {entry.category or 'general'}."
                ),
                evidence_file_id=file_id,
                auto_generated=True,
                rule_name=f"watchlist:{entry.id}",
            )
            db.add(alert)
            matches += 1

    if matches:
        db.commit()

    return {"entries_checked": len(entries), "matches": matches}
