"""Metadata extraction from filenames and transcript content."""

from __future__ import annotations

import re
from pathlib import Path

from rubberduck_analyzer.analyzers.transcript_analyzer import (
    detect_format,
    parse_transcript,
)
from rubberduck_analyzer.analyzers.video_analyzer import get_video_duration

# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

# Pattern: "260406 - Tester 1 - Interview - Abrham Wendmeneh (Upwork)_Transcript.txt"
_FILENAME_PATTERNS = [
    # YYMMDD - Tester N - Type - Name (Source)_suffix
    re.compile(
        r"(\d{6})\s*-\s*Tester\s*\d+\s*-\s*(\w+)\s*-\s*(.+?)(?:\s*\(.*?\))?\s*[_.]",
        re.IGNORECASE,
    ),
    # Name_Transcript.txt or Name_Interview.txt
    re.compile(r"^(.+?)(?:_Transcript|_Interview|_Written|_Comparison|_Proposal)", re.IGNORECASE),
]

_DATE_PATTERN = re.compile(r"(\d{2})(\d{2})(\d{2})")


def _parse_date_from_code(code: str) -> str | None:
    """Convert YYMMDD to ISO date."""
    m = _DATE_PATTERN.match(code)
    if m:
        yy, mm, dd = m.groups()
        return f"20{yy}-{mm}-{dd}"
    return None


def extract_from_filename(filename: str) -> dict:
    """Extract metadata from a filename.

    Returns dict with any of: tester_name, date, milestone_type, source_platform.
    """
    meta: dict = {"original_filename": filename}

    # Try structured pattern first
    m = _FILENAME_PATTERNS[0].search(filename)
    if m:
        date_code, session_type, name = m.group(1), m.group(2), m.group(3)
        meta["date"] = _parse_date_from_code(date_code)
        meta["tester_name"] = name.strip()
        session_lower = session_type.lower()
        if "interview" in session_lower:
            meta["milestone_type"] = "M1"
        elif "independent" in session_lower or "m2" in session_lower:
            meta["milestone_type"] = "M2"
        elif "comparison" in session_lower or "m3" in session_lower:
            meta["milestone_type"] = "M3"

    # Detect source platform
    if "(upwork)" in filename.lower():
        meta["source_platform"] = "Upwork"
    elif "(fiverr)" in filename.lower():
        meta["source_platform"] = "Fiverr"

    # Detect file type from suffix
    fname_lower = filename.lower()
    if "transcript" in fname_lower:
        meta["file_type"] = "transcript"
    elif "written" in fname_lower:
        meta["file_type"] = "written_deliverable"
    elif "comparison" in fname_lower:
        meta["file_type"] = "comparison"
    elif "proposal" in fname_lower:
        meta["file_type"] = "proposal"
    elif any(fname_lower.endswith(ext) for ext in (".webm", ".mp4", ".mov", ".mkv")):
        meta["file_type"] = "video"

    # Fallback name extraction from simpler pattern
    if "tester_name" not in meta:
        m2 = _FILENAME_PATTERNS[1].search(filename)
        if m2:
            raw = m2.group(1).strip()
            # Clean up: replace underscores/hyphens, skip if it's just a date code
            cleaned = raw.replace("_", " ").replace("-", " ").strip()
            if cleaned and not cleaned.isdigit() and len(cleaned) > 2:
                meta["tester_name"] = cleaned

    return meta


# ---------------------------------------------------------------------------
# Transcript content analysis (quick, no Claude API)
# ---------------------------------------------------------------------------


def extract_from_transcript(path: str | Path) -> dict:
    """Quick metadata extraction from transcript content — no API calls.

    Returns dict with: format, utterance_count, tester_name, facilitator_name,
    estimated_duration_minutes, phases_detected, word_count, first_utterance_preview.
    """
    path = Path(path)
    if not path.is_file():
        return {"error": f"File not found: {path}"}

    transcript = parse_transcript(path)
    meta: dict = {
        "format": transcript.format_detected,
        "utterance_count": len(transcript.utterances),
        "tester_name": transcript.tester_name,
        "facilitator_name": transcript.facilitator_name,
    }

    # Word count
    total_words = sum(len(u.text.split()) for u in transcript.utterances)
    meta["word_count"] = total_words

    # Estimated duration from timestamps or word count
    if transcript.utterances and transcript.utterances[-1].timestamp is not None:
        last_ts = transcript.utterances[-1].timestamp
        first_ts = transcript.utterances[0].timestamp or 0
        meta["estimated_duration_minutes"] = round((last_ts - first_ts) / 60, 1)
    else:
        # ~150 words per minute for conversation
        meta["estimated_duration_minutes"] = round(total_words / 150, 1)

    # Phases detected
    phases = set()
    for u in transcript.utterances:
        if u.phase:
            phases.add(u.phase)
    meta["phases_detected"] = sorted(phases)

    # Speaker turns
    tester_turns = sum(1 for u in transcript.utterances if u.speaker == "tester")
    facilitator_turns = sum(1 for u in transcript.utterances if u.speaker == "facilitator")
    meta["tester_turns"] = tester_turns
    meta["facilitator_turns"] = facilitator_turns

    # First tester utterance preview
    for u in transcript.utterances:
        if u.speaker == "tester" and len(u.text) > 10:
            meta["first_tester_utterance"] = u.text[:120] + ("..." if len(u.text) > 120 else "")
            break

    return meta


def extract_from_video(path: str | Path) -> dict:
    """Quick metadata from video file — just duration."""
    path = Path(path)
    if not path.is_file():
        return {}
    duration = get_video_duration(path)
    return {
        "video_duration_seconds": duration,
        "video_duration_minutes": round(duration / 60, 1) if duration else None,
        "video_size_mb": round(path.stat().st_size / (1024 * 1024), 1),
    }


# ---------------------------------------------------------------------------
# Combined enrichment
# ---------------------------------------------------------------------------


def enrich_upload(
    transcript_path: str | Path | None = None,
    video_path: str | Path | None = None,
    written_path: str | Path | None = None,
    transcript_filename: str | None = None,
    video_filename: str | None = None,
) -> dict:
    """Combine all metadata sources into a single enriched dict."""
    meta: dict = {}

    # Filename-based extraction
    if transcript_filename:
        meta.update(extract_from_filename(transcript_filename))
    if video_filename:
        vid_meta = extract_from_filename(video_filename)
        # Don't overwrite transcript-derived name with video filename
        for k, v in vid_meta.items():
            if k not in meta or meta[k] is None:
                meta[k] = v

    # Content-based extraction (transcript)
    if transcript_path:
        transcript_meta = extract_from_transcript(transcript_path)
        meta["transcript"] = transcript_meta
        # Prefer transcript-detected name over filename-derived
        if transcript_meta.get("tester_name") and not meta.get("tester_name"):
            meta["tester_name"] = transcript_meta["tester_name"]

    # Video metadata
    if video_path:
        meta["video"] = extract_from_video(video_path)

    # Written deliverable word count
    if written_path:
        text = Path(written_path).read_text(encoding="utf-8")
        meta["written"] = {
            "word_count": len(text.split()),
            "char_count": len(text),
            "sentence_count": len(re.split(r'[.!?]+', text.strip())),
        }

    return meta
