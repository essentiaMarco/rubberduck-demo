"""Evidence ingestion orchestrator — the central pipeline."""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import magic
from sqlalchemy.orm import Session

from rubberduck.config import settings
from rubberduck.db.models import EvidenceSource, File
from rubberduck.evidence.archive import extract_archive, is_archive
from rubberduck.evidence.hasher import hash_file
from rubberduck.evidence.manifest import ManifestWriter
from rubberduck.evidence.parsers import get_parser_for_ext, get_parser_for_mime
from rubberduck.evidence.parsers.google_takeout import GoogleTakeoutParser
from rubberduck.evidence.store import ensure_parsed_dir, store_original
from rubberduck.jobs.manager import job_manager

logger = logging.getLogger(__name__)


class IngestService:
    """Orchestrates evidence ingestion: hash → store → extract → parse → index."""

    @staticmethod
    def ingest_directory(db: Session, job_id: str, source_id: str, dir_path: str) -> dict:
        """Ingest all files from a local directory."""
        directory = Path(dir_path)
        if not directory.is_dir():
            raise ValueError(f"Not a directory: {dir_path}")

        # Detect Google Takeout
        is_takeout = GoogleTakeoutParser.detect_takeout(directory)
        if is_takeout:
            logger.info(f"Detected Google Takeout structure at {directory}")

        # Collect all files
        all_files = []
        for root, dirs, files in os.walk(directory):
            for fname in files:
                fpath = Path(root) / fname
                if fpath.is_file() and not fname.startswith("."):
                    all_files.append(fpath)

        total = len(all_files)
        processed = 0
        results = {"total_files": total, "ingested": 0, "duplicates": 0, "errors": 0}

        for fpath in all_files:
            try:
                relative_path = str(fpath.relative_to(directory))
                IngestService._ingest_single_file(db, source_id, fpath, relative_path, is_takeout)
                results["ingested"] += 1
            except Exception as e:
                logger.error(f"Failed to ingest {fpath}: {e}")
                results["errors"] += 1

            processed += 1
            if processed % 10 == 0:
                job_manager.update_progress(db, job_id, processed / total, processed, total)

        job_manager.update_progress(db, job_id, 1.0, total, total)
        return results

    @staticmethod
    def ingest_upload(db: Session, job_id: str, source_id: str, file_path: Path, original_name: str) -> dict:
        """Ingest a single uploaded file."""
        results = {"ingested": 0, "errors": 0}
        try:
            IngestService._ingest_single_file(db, source_id, file_path, original_name)
            results["ingested"] = 1
        except Exception as e:
            logger.error(f"Failed to ingest upload {original_name}: {e}")
            results["errors"] = 1
        return results

    @staticmethod
    def _ingest_single_file(
        db: Session,
        source_id: str,
        file_path: Path,
        original_path: str,
        is_takeout: bool = False,
    ) -> File:
        """Ingest one file: hash, store, detect format, and enqueue parsing."""
        # Step 1: Hash
        hash_result = hash_file(file_path)

        # Step 2: Check for duplicates
        existing = db.query(File).filter(File.sha256 == hash_result.sha256).first()
        if existing:
            # Record as duplicate but still track it
            file_record = File(
                source_id=source_id,
                original_path=original_path,
                file_name=file_path.name,
                file_ext=file_path.suffix,
                file_size_bytes=hash_result.size_bytes,
                sha256=hash_result.sha256,
                md5=hash_result.md5,
                is_duplicate=True,
                duplicate_of_id=existing.id,
                stored_path=existing.stored_path,
                parse_status="completed",
            )
            db.add(file_record)
            db.commit()
            ManifestWriter.record(db, file_record.id, "received", {"original_path": original_path})
            ManifestWriter.record(db, file_record.id, "hashed", {"sha256": hash_result.sha256, "md5": hash_result.md5})
            ManifestWriter.record(db, file_record.id, "duplicate_detected", {"duplicate_of": existing.id})
            return file_record

        # Step 3: Detect MIME type
        try:
            mime_type = magic.from_file(str(file_path), mime=True)
        except Exception:
            mime_type = "application/octet-stream"

        # Step 4: Store original
        stored_path = store_original(file_path, source_id, hash_result.sha256, file_path.suffix)

        is_arch = is_archive(file_path)

        file_record = File(
            source_id=source_id,
            original_path=original_path,
            stored_path=str(stored_path),
            file_name=file_path.name,
            file_ext=file_path.suffix,
            mime_type=mime_type,
            file_size_bytes=hash_result.size_bytes,
            sha256=hash_result.sha256,
            md5=hash_result.md5,
            is_archive=is_arch,
            parse_status="pending",
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)

        # Custody chain
        ManifestWriter.record(db, file_record.id, "received", {"original_path": original_path})
        ManifestWriter.record(db, file_record.id, "hashed", {"sha256": hash_result.sha256, "md5": hash_result.md5})
        ManifestWriter.record(db, file_record.id, "stored", {"stored_path": str(stored_path)})

        # Step 5: Handle archives
        if is_arch:
            try:
                with tempfile.TemporaryDirectory(prefix="rd_extract_") as tmp_dir:
                    extracted = extract_archive(file_path, Path(tmp_dir))
                    for extracted_path in extracted:
                        child_relative = f"{original_path}/{extracted_path.relative_to(tmp_dir)}"
                        child = IngestService._ingest_single_file(
                            db, source_id, extracted_path, child_relative, is_takeout
                        )
                        child.parent_file_id = file_record.id
                        db.commit()
            except Exception as e:
                logger.error(f"Archive extraction failed for {file_path}: {e}")
                file_record.parse_status = "failed"
                file_record.parse_error = f"{type(e).__name__}: archive extraction failed"
                db.commit()
            return file_record

        # Step 6: Parse the file
        IngestService._parse_file(db, file_record, file_path, is_takeout)
        return file_record

    @staticmethod
    def _parse_file(db: Session, file_record: File, file_path: Path, is_takeout: bool = False):
        """Run format-specific parser on a file."""
        file_record.parse_status = "processing"
        db.commit()

        # Select parser
        parser_cls = get_parser_for_mime(file_record.mime_type or "")
        if not parser_cls:
            parser_cls = get_parser_for_ext(file_record.file_ext or "")

        # Special case: Google Takeout files
        if is_takeout and not parser_cls:
            parser_cls = GoogleTakeoutParser

        if not parser_cls:
            file_record.parse_status = "unsupported"
            file_record.parse_error = f"No parser for MIME={file_record.mime_type}, ext={file_record.file_ext}"
            db.commit()
            ManifestWriter.record(db, file_record.id, "parse_skipped", {"reason": "unsupported_format"})
            return

        try:
            parser = parser_cls()
            result = parser.parse(file_path)

            # Save parsed content
            parsed_dir = ensure_parsed_dir(file_record.id)
            if result.text_content:
                (parsed_dir / "content.txt").write_text(result.text_content, encoding="utf-8")
            if result.metadata:
                (parsed_dir / "metadata.json").write_text(json.dumps(result.metadata, default=str))
            if result.events:
                events_data = [
                    {
                        "timestamp_raw": e.timestamp_raw,
                        "event_type": e.event_type,
                        "event_subtype": e.event_subtype,
                        "summary": e.summary,
                        "actor": e.actor,
                        "target": e.target,
                        "raw_data": e.raw_data,
                        "confidence": e.confidence,
                    }
                    for e in result.events
                ]
                (parsed_dir / "events.json").write_text(json.dumps(events_data, default=str))

            file_record.parse_status = "completed"
            file_record.parsed_path = str(parsed_dir)
            file_record.parsed_at = datetime.now(timezone.utc)
            file_record.parser_used = result.parser_name
            db.commit()

            ManifestWriter.record(
                db,
                file_record.id,
                "parsed",
                {
                    "parser": result.parser_name,
                    "text_length": len(result.text_content),
                    "event_count": len(result.events),
                    "entity_hints": len(result.entities_hint),
                    "warnings": result.warnings,
                },
            )

            # Auto-index for full-text search
            try:
                from rubberduck.search.indexer import index_file
                if result.text_content.strip():
                    index_file(db, file_record.id, result.text_content)
            except Exception as idx_err:
                logger.warning("FTS5 indexing failed for %s: %s", file_record.id, idx_err)

            # Auto-extract individual email records from EML/MBOX files
            if file_record.file_ext in (".eml", ".mbox"):
                try:
                    from rubberduck.evidence.email_extractor import extract_emails_from_file
                    email_stats = extract_emails_from_file(db, file_record)
                    logger.info(
                        "Extracted %d emails from %s (spam: %d, personal: %d)",
                        email_stats.get("total", 0),
                        file_record.file_name,
                        email_stats.get("spam", 0) + email_stats.get("newsletter", 0),
                        email_stats.get("personal", 0),
                    )
                except Exception as email_err:
                    logger.warning("Email extraction failed for %s: %s", file_record.id, email_err)

        except Exception as e:
            file_record.parse_status = "failed"
            file_record.parse_error = f"{type(e).__name__}: parse failed"
            db.commit()
            ManifestWriter.record(db, file_record.id, "parse_failed", {"error": type(e).__name__})
            logger.error(f"Parse failed for {file_record.file_name}: {e}")
