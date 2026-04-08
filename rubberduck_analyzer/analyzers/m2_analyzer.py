"""M2 independent-use deliverable analysis."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import anthropic

from rubberduck_analyzer.analyzers.transcript_analyzer import normalize_text
from rubberduck_analyzer.analyzers.video_analyzer import analyze_video, video_analysis_to_dict
from rubberduck_analyzer.context.use_case_registry import detect_use_cases

MODEL = "claude-sonnet-4-6"


def _call_claude(client: anthropic.Anthropic, system: str, user: str) -> dict:
    """Send a structured extraction prompt to Claude and parse the JSON response."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    return json.loads(text.strip())


_SYSTEM = (
    "You are an expert qualitative researcher analyzing deliverables from a user "
    "testing program for RubberDuck, an AI-powered code analysis tool. Extract "
    "structured observations from the provided text. Return ONLY valid JSON."
)


def _analyze_written_deliverable(client: anthropic.Anthropic, written_text: str) -> dict:
    """Analyze the 3-5 sentence written deliverable from M2."""
    schema = """{
  "use_case_chosen": "<UC-XX or 'unmapped_use_case'>",
  "use_case_description": "<what they did>",
  "used_different_codebase": <boolean or null>,
  "positive_feedback": ["<what worked>"],
  "negative_feedback": ["<what didn't work>"],
  "would_use_again": <boolean or null>,
  "new_use_case_discovered": <boolean>,
  "independence_level": <1-5, where 1=struggled alone and 5=fully independent>,
  "writing_quality": <1-5, where 1=vague/unclear and 5=articulate/detailed>,
  "m3_recommendation": "yes | maybe | no",
  "m3_task_suggestions": ["<suggested hard tasks based on what they described>"],
  "verbatim_quotes": ["<key phrases from the written deliverable>"]
}"""
    return _call_claude(
        client,
        _SYSTEM,
        f"Analyze this written deliverable from an M2 independent-use session. The tester "
        f"was asked to pick a workflow and use RubberDuck on their own, then write 3-5 sentences.\n\n"
        f"Map their activity to one of these use cases:\n"
        f"UC-01: Understand Code, UC-02: Security Audit, UC-03: Bug Localization,\n"
        f"UC-04: Code Review, UC-05: Change Impact, UC-06: Plan Features,\n"
        f"UC-07: Generate Code, UC-08: Check Logic, UC-09: Compare Versions,\n"
        f"UC-10: Quick Check\n\n"
        f"Assess their writing quality (1-5) and whether they're a good M3 candidate.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"WRITTEN DELIVERABLE:\n{written_text}",
    )


def analyze_m2(
    video_path: str | Path | None = None,
    written_path: str | Path | None = None,
    transcript_path: str | Path | None = None,
    output_path: str | Path | None = None,
    tester_name: str | None = None,
) -> dict:
    """Run the full M2 analysis pipeline.

    Returns the M2 analysis JSON and writes it to output_path if specified.
    """
    client = anthropic.Anthropic()

    # Parse written deliverable
    if written_path is None:
        raise ValueError("written_path is required for M2 analysis")

    print("Analyzing written deliverable...", file=sys.stderr)
    written_text = normalize_text(Path(written_path).read_text(encoding="utf-8"))
    written_analysis = _analyze_written_deliverable(client, written_text)

    # Optional: parse transcript
    transcript_analysis = None
    if transcript_path:
        from rubberduck_analyzer.analyzers.transcript_analyzer import (
            parse_transcript,
            transcript_to_text,
        )
        print("Parsing M2 transcript...", file=sys.stderr)
        transcript = parse_transcript(transcript_path)
        transcript_text = transcript_to_text(transcript)
        transcript_analysis = {
            "utterance_count": len(transcript.utterances),
            "format_detected": transcript.format_detected,
        }

    # Optional: video analysis
    video_data = None
    if video_path:
        print("Analyzing M2 video...", file=sys.stderr)
        va = analyze_video(video_path)
        video_data = video_analysis_to_dict(va)

    # Detect use cases from written text
    detected_ucs = detect_use_cases(written_text)

    # Assemble result
    result = {
        "milestone": "M2",
        "tester_name": tester_name,
        "date": str(date.today()),
        "use_case_chosen": written_analysis.get("use_case_chosen", "unknown"),
        "new_use_case_discovered": written_analysis.get("new_use_case_discovered", False),
        "independence_level": written_analysis.get("independence_level"),
        "writing_quality": written_analysis.get("writing_quality"),
        "m3_recommendation": written_analysis.get("m3_recommendation", "maybe"),
        "m3_task_suggestions": written_analysis.get("m3_task_suggestions", []),
        "written_analysis": written_analysis,
        "video_analysis": video_data,
        "transcript_analysis": transcript_analysis,
        "detected_use_cases": detected_ucs,
    }

    # Write output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"M2 analysis written to {output_path}", file=sys.stderr)
    else:
        name = (tester_name or "unknown").replace(" ", "_").lower()
        default_path = Path("data/sessions") / f"{name}_m2_{date.today()}.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"M2 analysis written to {default_path}", file=sys.stderr)

    return result
