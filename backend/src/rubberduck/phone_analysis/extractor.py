"""Extract PhoneRecord rows from parsed Vodafone bill PDFs.

Reads CDR data produced by the bill parser and creates per-call database
records with anomaly scoring.  Runs as a post-processing step after PDF
ingestion, mirroring the email_extractor workflow.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from rubberduck.db.models import PhoneRecord
from rubberduck.phone_analysis.parser import parse_vodafone_bill

logger = logging.getLogger(__name__)


# ── Anomaly detection ────────────────────────────────────────


def _night_owl_score(dt: datetime | None) -> tuple[float, str | None]:
    """Score calls between 11 PM and 6 AM.  Worst at 2-4 AM."""
    if dt is None:
        return 0.0, None
    hour = dt.hour
    if hour >= 23 or hour < 6:
        if 2 <= hour <= 4:
            score = 0.5
        elif hour >= 23 or hour <= 1:
            score = 0.3
        else:
            score = 0.4
        return score, f"night_owl: call at {dt.strftime('%H:%M')}"
    return 0.0, None


def _long_call_score(duration_seconds: int) -> tuple[float, str | None]:
    """Flag calls longer than 30 minutes."""
    if duration_seconds > 1800:
        mins = duration_seconds // 60
        return 0.2, f"long_call: {mins} minutes"
    return 0.0, None


def _isd_call_score(call_type: str | None) -> tuple[float, str | None]:
    """Flag international (ISD) calls."""
    if call_type and "isd" in call_type.lower():
        return 0.15, "isd_call: international call"
    return 0.0, None


def _rapid_redial_score(
    record: dict, all_records: list[dict]
) -> tuple[float, str | None]:
    """Flag numbers called 3+ times within 10-minute windows.

    Checks the called_number of *record* against every other record's
    called_number.  If 3 or more calls to the same number fall within
    10 minutes of each other, the record is flagged.
    """
    target = record.get("called_number")
    rec_dt = record.get("call_datetime")
    if not target or not rec_dt:
        return 0.0, None

    window = timedelta(minutes=10)
    nearby = 0
    for other in all_records:
        if other.get("called_number") != target:
            continue
        other_dt = other.get("call_datetime")
        if other_dt is None:
            continue
        if abs((rec_dt - other_dt).total_seconds()) <= window.total_seconds():
            nearby += 1

    if nearby >= 3:
        return 0.3, f"rapid_redial: {target} called {nearby} times within 10 min"
    return 0.0, None


def _run_anomaly_detection(
    record: dict, all_records: list[dict]
) -> tuple[bool, float, list[str]]:
    """Apply all anomaly rules to a single record dict.

    Returns (is_anomaly, total_score, list_of_reason_strings).
    """
    reasons: list[str] = []
    total = 0.0

    for scorer in [
        lambda: _night_owl_score(record.get("call_datetime")),
        lambda: _long_call_score(record.get("duration_seconds", 0)),
        lambda: _isd_call_score(record.get("call_type")),
        lambda: _rapid_redial_score(record, all_records),
    ]:
        score, reason = scorer()
        if score > 0:
            total += score
            reasons.append(reason)

    total = min(total, 1.0)
    return total > 0, round(total, 3), reasons


# ── Single-file extraction ───────────────────────────────────


def extract_from_pdf(
    db: Session,
    pdf_path: str | Path,
    *,
    reprocess: bool = False,
    file_id: str | None = None,
) -> dict:
    """Parse one Vodafone bill PDF and persist PhoneRecord rows.

    Args:
        db: SQLAlchemy session.
        pdf_path: Path to the PDF on disk.
        reprocess: If True, delete existing records for this file and re-import.
        file_id: Optional File.id to link records back to the evidence file.

    Returns:
        Summary dict with counts and metadata.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"error": f"PDF not found: {pdf_path}"}

    # Clear old records when reprocessing
    if reprocess and file_id:
        db.query(PhoneRecord).filter(PhoneRecord.file_id == file_id).delete()
        db.flush()

    # Skip if already processed
    if file_id and not reprocess:
        existing = (
            db.query(PhoneRecord)
            .filter(PhoneRecord.file_id == file_id)
            .count()
        )
        if existing > 0:
            return {"skipped": True, "already_processed": existing}

    parsed = parse_vodafone_bill(pdf_path)
    raw_records = parsed.get("records", [])
    metadata = parsed.get("metadata", {})

    stats = {
        "file": pdf_path.name,
        "total_records": 0,
        "anomalies": 0,
        "bill_number": metadata.get("bill_number"),
        "subscriber": metadata.get("vodafone_number"),
        "period_start": str(metadata.get("period_start")) if metadata.get("period_start") else None,
        "period_end": str(metadata.get("period_end")) if metadata.get("period_end") else None,
        "warnings": parsed.get("warnings", []),
    }

    for idx, rec in enumerate(raw_records):
        is_anomaly, score, reasons = _run_anomaly_detection(rec, raw_records)

        phone_record = PhoneRecord(
            file_id=file_id,
            record_index=idx,
            subscriber_number=rec.get("subscriber_number"),
            subscriber_name=rec.get("subscriber_name"),
            caller_number=rec.get("caller_number"),
            called_number=rec.get("called_number"),
            call_datetime=rec.get("call_datetime"),
            call_datetime_raw=rec.get("call_datetime_raw"),
            duration_seconds=rec.get("duration_seconds", 0),
            duration_raw=rec.get("duration_raw"),
            charges=rec.get("charges", 0.0),
            call_type=rec.get("call_type"),
            bill_period_start=rec.get("bill_period_start"),
            bill_period_end=rec.get("bill_period_end"),
            bill_number=rec.get("bill_number"),
            bill_plan=rec.get("bill_plan"),
            is_anomaly=is_anomaly,
            anomaly_score=score,
            anomaly_reasons=json.dumps(reasons),
        )
        db.add(phone_record)

        stats["total_records"] += 1
        if is_anomaly:
            stats["anomalies"] += 1

        # Batch flush every 100 rows
        if (idx + 1) % 100 == 0:
            db.flush()

    db.flush()
    return stats


# ── Bulk extraction ──────────────────────────────────────────


def extract_all_phone_bills(
    db: Session,
    folder_path: str | Path,
    *,
    reprocess: bool = False,
) -> dict:
    """Batch-process every PDF in *folder_path*.

    Args:
        db: SQLAlchemy session.
        folder_path: Directory containing Vodafone bill PDFs.
        reprocess: Re-extract even if records already exist.

    Returns:
        Aggregated summary with per-file results.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        return {"error": f"Folder not found: {folder_path}"}

    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        pdf_files = sorted(folder.glob("*.PDF"))

    totals = {
        "files_processed": 0,
        "files_skipped": 0,
        "total_records": 0,
        "total_anomalies": 0,
        "errors": 0,
        "per_file": [],
    }

    for pdf in pdf_files:
        try:
            result = extract_from_pdf(db, pdf, reprocess=reprocess)
            if result.get("skipped"):
                totals["files_skipped"] += 1
            elif result.get("error"):
                totals["errors"] += 1
            else:
                totals["files_processed"] += 1
                totals["total_records"] += result.get("total_records", 0)
                totals["total_anomalies"] += result.get("anomalies", 0)
            totals["per_file"].append(result)
        except Exception as e:
            logger.warning("Failed to process %s: %s", pdf.name, e)
            totals["errors"] += 1
            totals["per_file"].append({"file": pdf.name, "error": str(e)})

    db.commit()
    return totals
