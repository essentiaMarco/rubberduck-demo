"""Transcript parser with auto format detection, noise normalization, and phase segmentation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Utterance:
    """Single speaker turn in a transcript."""

    speaker: str  # "facilitator" | "tester"
    timestamp: float | None
    text: str
    phase: str | None = None  # assigned during segmentation
    raw_speaker_name: str | None = None


@dataclass
class Transcript:
    """Parsed and normalized transcript."""

    utterances: list[Utterance] = field(default_factory=list)
    format_detected: str = "unknown"  # "labeled" | "timestamped"
    tester_name: str | None = None
    facilitator_name: str | None = None


# ---------------------------------------------------------------------------
# Noise normalization
# ---------------------------------------------------------------------------

def _codex_preserving_prefix(m: re.Match) -> str:
    """Replace 'codecs' while keeping the preceding preposition."""
    text = m.group(0)
    return text[: text.lower().rfind("codecs")] + "Codex"


NOISE_REPLACEMENTS: list[tuple[re.Pattern, str | callable]] = [
    (re.compile(r"\brobo\s*duck\b", re.IGNORECASE), "RubberDuck"),
    (re.compile(r"\brobot\s*duck\b", re.IGNORECASE), "RubberDuck"),
    (re.compile(r"\brubber\s*duck\b", re.IGNORECASE), "RubberDuck"),
    (re.compile(r"\bcloth\s+code\b", re.IGNORECASE), "Claude Code"),
    (re.compile(r"\bcloud\s+code\b", re.IGNORECASE), "Claude Code"),
    (re.compile(r"\bmtp\b", re.IGNORECASE), "MCP"),
    # "codecs" in tool context -> Codex (handled with surrounding-word heuristic)
    (re.compile(r"\bcodecs\b(?=\s+(?:web|desktop|app|ide|tool|editor))", re.IGNORECASE), "Codex"),
    (re.compile(r"(?:in|with|using|from|open)\s+\bcodecs\b", re.IGNORECASE), _codex_preserving_prefix),
]


def normalize_text(text: str) -> str:
    """Apply all noise normalizations to a text string."""
    for pattern, replacement in NOISE_REPLACEMENTS:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

_FORMAT_A_PATTERN = re.compile(r"^(Me|Them)\s*:", re.IGNORECASE)
_FORMAT_B_PATTERN = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+(.+?):\s*(.*)$")


def detect_format(lines: list[str]) -> str:
    """Detect transcript format by scanning initial non-empty lines."""
    a_count = 0
    b_count = 0
    checked = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _FORMAT_A_PATTERN.match(line):
            a_count += 1
        if _FORMAT_B_PATTERN.match(line):
            b_count += 1
        checked += 1
        if checked >= 10:
            break
    if b_count > a_count:
        return "timestamped"
    if a_count > 0:
        return "labeled"
    return "unknown"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_timestamp(ts_str: str) -> float:
    """Convert HH:MM:SS to seconds."""
    parts = ts_str.split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s


def _parse_labeled(lines: list[str]) -> list[Utterance]:
    """Parse Format A (Me/Them labeled) transcripts."""
    utterances: list[Utterance] = []
    current_speaker = None
    current_text_parts: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = _FORMAT_A_PATTERN.match(line)
        if match:
            # Flush previous utterance
            if current_speaker is not None and current_text_parts:
                utterances.append(Utterance(
                    speaker="facilitator" if current_speaker.lower() == "me" else "tester",
                    timestamp=None,
                    text=normalize_text(" ".join(current_text_parts)),
                    raw_speaker_name=current_speaker,
                ))
            current_speaker = match.group(1)
            rest = line[match.end():].strip()
            current_text_parts = [rest] if rest else []
        elif current_speaker is not None:
            current_text_parts.append(line)

    # Flush last utterance
    if current_speaker is not None and current_text_parts:
        utterances.append(Utterance(
            speaker="facilitator" if current_speaker.lower() == "me" else "tester",
            timestamp=None,
            text=normalize_text(" ".join(current_text_parts)),
            raw_speaker_name=current_speaker,
        ))
    return utterances


def _parse_timestamped(
    lines: list[str],
    facilitator_is_first: bool = True,
) -> tuple[list[Utterance], str | None, str | None]:
    """Parse Format B (timestamped) transcripts. Returns (utterances, facilitator_name, tester_name)."""
    utterances: list[Utterance] = []
    speaker_order: list[str] = []
    current_speaker_name: str | None = None
    current_timestamp: float | None = None
    current_text_parts: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = _FORMAT_B_PATTERN.match(line)
        if match:
            # Flush previous
            if current_speaker_name is not None and current_text_parts:
                role = _resolve_role(current_speaker_name, speaker_order, facilitator_is_first)
                utterances.append(Utterance(
                    speaker=role,
                    timestamp=current_timestamp,
                    text=normalize_text(" ".join(current_text_parts)),
                    raw_speaker_name=current_speaker_name,
                ))
            ts_str, speaker_name, text = match.group(1), match.group(2), match.group(3)
            current_timestamp = _parse_timestamp(ts_str)
            current_speaker_name = speaker_name.strip()
            if current_speaker_name not in speaker_order:
                speaker_order.append(current_speaker_name)
            current_text_parts = [text] if text else []
        elif current_speaker_name is not None:
            current_text_parts.append(line)

    # Flush last
    if current_speaker_name is not None and current_text_parts:
        role = _resolve_role(current_speaker_name, speaker_order, facilitator_is_first)
        utterances.append(Utterance(
            speaker=role,
            timestamp=current_timestamp,
            text=normalize_text(" ".join(current_text_parts)),
            raw_speaker_name=current_speaker_name,
        ))

    facilitator_name = speaker_order[0] if facilitator_is_first and speaker_order else None
    tester_name = speaker_order[1] if facilitator_is_first and len(speaker_order) > 1 else None
    if not facilitator_is_first:
        tester_name = speaker_order[0] if speaker_order else None
        facilitator_name = speaker_order[1] if len(speaker_order) > 1 else None

    return utterances, facilitator_name, tester_name


def _resolve_role(
    speaker_name: str,
    speaker_order: list[str],
    facilitator_is_first: bool,
) -> str:
    """Map a speaker name to facilitator/tester based on order of appearance."""
    if not speaker_order:
        return "facilitator" if facilitator_is_first else "tester"
    first = speaker_order[0]
    if facilitator_is_first:
        return "facilitator" if speaker_name == first else "tester"
    return "tester" if speaker_name == first else "facilitator"


# ---------------------------------------------------------------------------
# Phase segmentation
# ---------------------------------------------------------------------------

PHASE_KEYWORDS: dict[str, list[str]] = {
    "setup": [
        "install", "token", "mcp", "setup", "github app", "connect",
        "api key", "extension", "plugin", "configure", "configuration",
        "repository", "indexing", "indexed",
    ],
    "baseline": [
        "current workflow", "what tools", "how do you", "experience with",
        "background", "what kind of", "your codebase", "day to day",
        "normally use", "typically use", "code review process",
    ],
    "exploration": [
        "call_chain", "trace_variable", "find_consumers", "plan_change",
        "search_code", "symbols_overview", "security_audit", "shared_variables",
        "rubberduck", "let me try", "let's try", "can you show",
        "run that", "what does this", "interesting", "output",
    ],
    "debrief": [
        "first impression", "surprised", "confusing", "trust",
        "scale of 1", "rate", "overall", "what did you think",
        "biggest takeaway", "most useful", "least useful",
    ],
    "handoff": [
        "milestone 2", "next step", "screen record", "write 3-5 sentences",
        "on your own", "independent", "pick a workflow", "record yourself",
    ],
}


def _score_phase(text: str) -> dict[str, float]:
    """Score a text against each phase's keywords. Returns {phase: score}."""
    text_lower = text.lower()
    scores: dict[str, float] = {}
    for phase, keywords in PHASE_KEYWORDS.items():
        score = sum(1.0 for kw in keywords if kw in text_lower)
        scores[phase] = score
    return scores


def assign_phases(utterances: list[Utterance], window_size: int = 5) -> None:
    """Assign phase labels to utterances using a sliding-window keyword density approach.

    Phases are sequential: setup -> baseline -> exploration -> debrief -> handoff.
    Once a phase is assigned, we don't go backwards (monotonic progression).
    """
    if not utterances:
        return

    phase_order = ["setup", "baseline", "exploration", "debrief", "handoff"]
    current_phase_idx = 0

    for i, utt in enumerate(utterances):
        # Build window of surrounding utterances for context
        window_start = max(0, i - window_size // 2)
        window_end = min(len(utterances), i + window_size // 2 + 1)
        window_text = " ".join(u.text for u in utterances[window_start:window_end])

        scores = _score_phase(window_text)

        # Find the best-scoring phase at or after the current phase
        best_phase = phase_order[current_phase_idx]
        best_score = scores.get(best_phase, 0)
        for j in range(current_phase_idx, len(phase_order)):
            phase = phase_order[j]
            if scores.get(phase, 0) > best_score:
                best_phase = phase
                best_score = scores[phase]
                current_phase_idx = j

        utt.phase = best_phase


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_transcript(
    path: str | Path,
    facilitator_is_first: bool = True,
) -> Transcript:
    """Parse a transcript file, auto-detecting format and normalizing content."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()

    fmt = detect_format(lines)
    transcript = Transcript(format_detected=fmt)

    if fmt == "labeled":
        transcript.utterances = _parse_labeled(lines)
    elif fmt == "timestamped":
        utterances, fac_name, tester_name = _parse_timestamped(lines, facilitator_is_first)
        transcript.utterances = utterances
        transcript.facilitator_name = fac_name
        transcript.tester_name = tester_name
    else:
        # Fallback: treat every line as a tester utterance
        for line in lines:
            line = line.strip()
            if line:
                transcript.utterances.append(Utterance(
                    speaker="tester",
                    timestamp=None,
                    text=normalize_text(line),
                ))

    assign_phases(transcript.utterances)
    return transcript


def transcript_to_text(transcript: Transcript) -> str:
    """Convert a parsed transcript back to a single text block for Claude API prompts."""
    parts: list[str] = []
    for utt in transcript.utterances:
        label = "Facilitator" if utt.speaker == "facilitator" else "Tester"
        ts = f"[{utt.timestamp:.0f}s] " if utt.timestamp is not None else ""
        parts.append(f"{ts}{label}: {utt.text}")
    return "\n".join(parts)
