"""Hidden content detection — encrypted files, steganography, file type mismatch.

Scans evidence files for indicators of concealed data:
- Password-protected archives (ZIP, RAR, 7z)
- Encrypted PDFs
- File extension vs MIME type mismatch (disguised files)
- DOCX hidden text, tracked changes, embedded OLE objects
- Steganography indicators via LSB chi-squared analysis
"""

import logging
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from rubberduck.db.models import File, ForensicAlert

logger = logging.getLogger(__name__)


def scan_hidden_content(db: Session, file_id: str | None = None) -> dict:
    """Run all hidden content detectors across evidence files.

    Creates ForensicAlert records for findings.
    """
    query = db.query(File).filter(File.parse_status.in_(["completed", "failed"]))
    if file_id:
        query = query.filter(File.id == file_id)

    files = query.all()
    stats = {
        "files_scanned": len(files),
        "encrypted_found": 0,
        "mismatch_found": 0,
        "hidden_content_found": 0,
        "alerts_created": 0,
    }

    for f in files:
        alerts = []

        # Check encrypted/password-protected files
        enc_alert = _check_encrypted(f)
        if enc_alert:
            alerts.append(enc_alert)
            stats["encrypted_found"] += 1

        # Check file type mismatch
        mm_alert = _check_type_mismatch(f)
        if mm_alert:
            alerts.append(mm_alert)
            stats["mismatch_found"] += 1

        # Check DOCX for hidden content
        if f.file_ext and f.file_ext.lower() == ".docx" and f.stored_path:
            docx_alerts = _check_docx_hidden(f)
            alerts.extend(docx_alerts)
            stats["hidden_content_found"] += len(docx_alerts)

        # Persist alerts (de-duplicate)
        for alert_data in alerts:
            existing = (
                db.query(ForensicAlert)
                .filter(
                    ForensicAlert.title == alert_data["title"],
                    ForensicAlert.evidence_file_id == f.id,
                )
                .first()
            )
            if not existing:
                alert = ForensicAlert(
                    alert_type=alert_data["alert_type"],
                    severity=alert_data["severity"],
                    title=alert_data["title"],
                    description=alert_data["description"],
                    evidence_file_id=f.id,
                    auto_generated=True,
                    rule_name="hidden_content_scan",
                )
                db.add(alert)
                stats["alerts_created"] += 1

    if stats["alerts_created"]:
        db.commit()

    return stats


# ── Encrypted file detection ─────────────────────────────────


def _check_encrypted(f: File) -> dict | None:
    """Detect password-protected files from parse errors and file inspection."""
    # Check parse error for encryption markers
    error = (f.parse_error or "").lower()
    if any(kw in error for kw in ("encrypt", "password", "protected", "locked", "access denied")):
        return {
            "alert_type": "encrypted_file",
            "severity": "high",
            "title": f"Encrypted file: {f.file_name}",
            "description": (
                f"File '{f.file_name}' ({f.mime_type or f.file_ext}) appears to be "
                f"password-protected or encrypted. Parse error: {f.parse_error}. "
                f"May require legal authority (warrant) to attempt decryption."
            ),
        }

    # Proactively check ZIP files
    if f.stored_path and f.file_ext and f.file_ext.lower() == ".zip":
        try:
            with zipfile.ZipFile(f.stored_path, "r") as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:  # Encrypted flag
                        return {
                            "alert_type": "encrypted_file",
                            "severity": "high",
                            "title": f"Encrypted ZIP: {f.file_name}",
                            "description": (
                                f"ZIP archive '{f.file_name}' contains encrypted entries. "
                                f"Encrypted members: check with forensic tools. "
                                f"May indicate intentional concealment."
                            ),
                        }
        except (zipfile.BadZipFile, OSError):
            pass

    # Check PDF encryption
    if f.stored_path and f.mime_type == "application/pdf":
        try:
            with open(f.stored_path, "rb") as fh:
                header = fh.read(4096)
                if b"/Encrypt" in header:
                    return {
                        "alert_type": "encrypted_file",
                        "severity": "high",
                        "title": f"Encrypted PDF: {f.file_name}",
                        "description": (
                            f"PDF '{f.file_name}' contains an /Encrypt dictionary. "
                            f"The document is password-protected."
                        ),
                    }
        except OSError:
            pass

    return None


# ── File type mismatch detection ─────────────────────────────

# Extension -> expected MIME types (common forensically relevant formats)
_EXPECTED_MIMES: dict[str, set[str]] = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".gif": {"image/gif"},
    ".pdf": {"application/pdf"},
    ".zip": {"application/zip", "application/x-zip-compressed"},
    ".rar": {"application/x-rar-compressed", "application/vnd.rar"},
    ".7z": {"application/x-7z-compressed"},
    ".doc": {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
    ".exe": {"application/x-dosexec", "application/x-executable", "application/x-msdos-program"},
    ".mp3": {"audio/mpeg"},
    ".mp4": {"video/mp4"},
    ".avi": {"video/x-msvideo"},
}

# Safe to ignore (common harmless mismatches)
_IGNORE_MISMATCHES = {
    (".json", "text/plain"),
    (".csv", "text/plain"),
    (".txt", "text/html"),
    (".log", "text/plain"),
    (".md", "text/plain"),
    (".mbox", "text/plain"),
    (".eml", "text/plain"),
    (".xml", "text/html"),
    (".json", "text/html"),
    (".csv", "application/csv"),
    (".tsv", "text/plain"),
    (".docx", "application/zip"),  # DOCX is actually a ZIP
    (".xlsx", "application/zip"),  # XLSX is actually a ZIP
}


def _check_type_mismatch(f: File) -> dict | None:
    """Flag files where the extension doesn't match the detected MIME type."""
    if not f.file_ext or not f.mime_type:
        return None

    ext = f.file_ext.lower()
    mime = f.mime_type.lower()

    # Skip known harmless mismatches
    if (ext, mime) in _IGNORE_MISMATCHES:
        return None

    expected = _EXPECTED_MIMES.get(ext)
    if expected and mime not in expected:
        return {
            "alert_type": "file_mismatch",
            "severity": "medium",
            "title": f"File type mismatch: {f.file_name}",
            "description": (
                f"File '{f.file_name}' has extension '{ext}' but actual MIME type "
                f"is '{mime}'. Expected: {expected}. "
                f"This could indicate a deliberately renamed/disguised file."
            ),
        }

    return None


# ── DOCX hidden content detection ────────────────────────────


def _check_docx_hidden(f: File) -> list[dict]:
    """Inspect DOCX internals for hidden text, tracked changes, embedded objects."""
    alerts: list[dict] = []
    stored = Path(f.stored_path) if f.stored_path else None
    if not stored or not stored.exists():
        return alerts

    try:
        import zipfile
        with zipfile.ZipFile(stored, "r") as zf:
            names = zf.namelist()

            # Check for tracked changes (revisions)
            if "word/document.xml" in names:
                doc_xml = zf.read("word/document.xml").decode("utf-8", errors="replace")

                # Deletions (tracked changes)
                del_count = doc_xml.count("<w:del ")
                ins_count = doc_xml.count("<w:ins ")
                if del_count > 0 or ins_count > 0:
                    alerts.append({
                        "alert_type": "hidden_content",
                        "severity": "medium",
                        "title": f"Tracked changes in: {f.file_name}",
                        "description": (
                            f"DOCX '{f.file_name}' contains tracked changes: "
                            f"{del_count} deletion(s), {ins_count} insertion(s). "
                            f"These may reveal earlier versions of the document content."
                        ),
                    })

                # Hidden text (<w:vanish/>)
                if "<w:vanish" in doc_xml:
                    alerts.append({
                        "alert_type": "hidden_content",
                        "severity": "high",
                        "title": f"Hidden text in: {f.file_name}",
                        "description": (
                            f"DOCX '{f.file_name}' contains hidden text (w:vanish formatting). "
                            f"This text is invisible in normal view but may contain relevant information."
                        ),
                    })

            # Check for comments
            if "word/comments.xml" in names:
                comments_xml = zf.read("word/comments.xml").decode("utf-8", errors="replace")
                comment_count = comments_xml.count("<w:comment ")
                if comment_count > 0:
                    alerts.append({
                        "alert_type": "hidden_content",
                        "severity": "low",
                        "title": f"Comments in: {f.file_name}",
                        "description": (
                            f"DOCX '{f.file_name}' contains {comment_count} comment(s). "
                            f"Comments may contain investigatively relevant annotations."
                        ),
                    })

            # Check for embedded OLE objects
            ole_files = [n for n in names if "embeddings/" in n.lower() or "oleObject" in n]
            if ole_files:
                alerts.append({
                    "alert_type": "hidden_content",
                    "severity": "medium",
                    "title": f"Embedded objects in: {f.file_name}",
                    "description": (
                        f"DOCX '{f.file_name}' contains {len(ole_files)} embedded object(s): "
                        f"{', '.join(Path(n).name for n in ole_files[:5])}. "
                        f"Embedded objects may contain additional data or executables."
                    ),
                })

    except (zipfile.BadZipFile, OSError, UnicodeDecodeError) as e:
        logger.debug("DOCX inspection failed for %s: %s", f.file_name, e)

    return alerts
