"""M1 session analysis — 6 observation areas extracted via Claude API."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import anthropic

from rubberduck_analyzer.analyzers.transcript_analyzer import (
    Transcript,
    parse_transcript,
    transcript_to_text,
)
from rubberduck_analyzer.analyzers.claude_client import call_claude as _call_claude
from rubberduck_analyzer.context.use_case_registry import detect_use_cases


# ---------------------------------------------------------------------------
# Observation extraction prompts
# ---------------------------------------------------------------------------

_SYSTEM_PREFIX = (
    "You are an expert qualitative researcher analyzing a user testing interview "
    "for RubberDuck, an AI-powered code analysis tool that uses MCP integration. "
    "Extract structured observations from the transcript. Return ONLY valid JSON "
    "matching the requested schema. Verbatim quotes must be exact text from the "
    "transcript, not paraphrased."
)


def _extract_installation(client: anthropic.Anthropic, text: str) -> dict:
    """Extract installation/setup observations."""
    schema = """{
  "setup_method": "pre-call | on-call | failed",
  "setup_duration_minutes": <number or null>,
  "blockers": [{"description": "<string>", "category": "token_confusion | mcp_config | ide_specific | github_app | indexing | other"}],
  "facilitator_intervention_required": <boolean>,
  "verbatim_quotes": ["<exact quote from transcript>"]
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze the following interview transcript for INSTALLATION AND SETUP observations.\n\n"
        f"Look for: setup friction, where they got stuck, how long it took, token confusion "
        f"(API key vs MCP token), MCP configuration errors, IDE-specific issues, GitHub App "
        f"installation issues, repository indexing failures.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"If setup was not discussed or data is insufficient, set setup_method to 'pre-call' "
        f"and note the gap in a quote.\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _extract_prompting(client: anthropic.Anthropic, text: str) -> dict:
    """Extract prompting behavior observations."""
    schema = """{
  "prompt_independence": <1-5, where 1=needed full guidance and 5=wrote own prompts>,
  "prompt_style": "copied_from_website | natural_language | tool_specific | needed_help",
  "mentions_tool_names": <boolean — did they use call_chain, trace_variable, etc.>,
  "mcp_tool_usage": "used_correctly | ide_ignored_mcp | used_grep_instead | not_reached",
  "verbatim_quotes": ["<exact quote showing how they framed prompts>"]
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze the following interview transcript for PROMPTING BEHAVIOR observations.\n\n"
        f"Look for: did they write their own prompts or need guidance, did they use RubberDuck "
        f"tool names (call_chain, trace_variable, find_consumers, etc.) or plain English, "
        f"did the IDE actually call MCP tools or fall back to grep/cat.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _extract_output_review(client: anthropic.Anthropic, text: str) -> dict:
    """Extract output review behavior observations."""
    schema = """{
  "review_depth": <1-5, where 1=glanced and 5=verified line by line>,
  "verified_against_knowledge": <boolean — did they check output against what they know>,
  "identified_errors": ["<description of output errors they caught>"],
  "identified_correct": ["<description of output they confirmed as accurate>"],
  "skipped_sections": ["<what parts of output they ignored>"],
  "verbatim_quotes": ["<exact reactions to output>"]
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze the following interview transcript for OUTPUT REVIEW observations.\n\n"
        f"Look for: did they read output carefully, verify against what they know, skim or "
        f"ignore parts, catch errors, confirm accuracy.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _extract_llm_biases(client: anthropic.Anthropic, text: str) -> dict:
    """Extract LLM bias observations."""
    schema = """{
  "pre_existing_bias": "<text describing what they said about AI tools before using RubberDuck>",
  "bias_confirmed": <boolean — did their bias show up during use>,
  "bias_challenged": <boolean — did RubberDuck change their assumption>,
  "projected_limitations": ["<limitations they assumed from other tools>"],
  "verbatim_quotes": ["<statements showing bias or bias reversal>"]
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze the following interview transcript for LLM BIAS observations.\n\n"
        f"Look for: do they assume things are impossible, distrust output because 'AI hallucinates', "
        f"project limitations from other tools like Copilot/ChatGPT onto RubberDuck, or have "
        f"their assumptions challenged by the results.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _extract_trust(client: anthropic.Anthropic, text: str) -> dict:
    """Extract trust observations."""
    schema = """{
  "trust_score": <float or null — if explicitly stated like '8.5 out of 10'>,
  "trust_moments": [{"direction": "increased | decreased", "trigger": "<what caused the shift>"}],
  "would_use_again": <boolean or null>,
  "would_ship_based_on_output": <boolean or null>,
  "comparison_to_other_tools": "<how they compared trust vs Copilot, ChatGPT, etc.>",
  "verbatim_quotes": ["<trust-related statements>"]
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze the following interview transcript for TRUST observations.\n\n"
        f"Look for: how much they trust the output, what makes them believe or doubt results, "
        f"explicit trust ratings, whether they'd use the tool again, whether they'd ship code "
        f"based on its output.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _extract_product_feedback(client: anthropic.Anthropic, text: str) -> dict:
    """Extract product feedback observations."""
    schema = """{
  "feature_requests": [{"description": "<string>", "priority": "high | medium | low", "category": "<string>"}],
  "complaints": [{"description": "<string>", "severity": "blocker | major | minor"}],
  "comparisons_to_competitors": [{"competitor": "<name>", "feature": "<what they compared>", "verdict": "RD_better | competitor_better | tie"}],
  "verbatim_quotes": ["<feedback statements>"]
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze the following interview transcript for PRODUCT FEEDBACK observations.\n\n"
        f"Look for: feature requests, complaints, suggestions about the product, comparisons "
        f"to competitors (Copilot, CodeRabbit, Qodo, Cursor, Codex, etc.), what they wish "
        f"the tool could do.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


# ---------------------------------------------------------------------------
# Session-level scoring
# ---------------------------------------------------------------------------


def _extract_session_metadata(
    client: anthropic.Anthropic,
    text: str,
    transcript: Transcript,
) -> dict:
    """Extract tester and session metadata from the transcript."""
    schema = """{
  "tester_name": "<name or null>",
  "date": "<ISO date or null>",
  "ide": "Cursor | Codex | Claude Code | VS Code | unknown",
  "codebase": {
    "name": "<string or null>",
    "language": "<string, currently 'Python'>",
    "type": "production | personal | forked | toy",
    "domain": "<string — e.g., medical backend, ML training>",
    "industry": "<string or null — finance, automotive, software publishing, other>",
    "size": "small | medium | large | unknown",
    "has_tests": <boolean or null>,
    "has_recent_prs": <boolean or null>,
    "has_known_bugs": <boolean or null>
  },
  "total_duration_minutes": <number or null>,
  "debrief_completed": <boolean>,
  "handoff_delivered": <boolean>,
  "killer_question_asked": <boolean>,
  "killer_question_answer": "<string or null>"
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Extract session metadata from this interview transcript. Look for: tester name, "
        f"date, which IDE they used, their codebase details, session duration, whether a "
        f"debrief happened, whether M2 handoff was delivered, whether the facilitator asked "
        f"the 'killer question' (a decisive question about whether they'd use the tool).\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _extract_facilitator_compliance(client: anthropic.Anthropic, text: str) -> dict:
    """Check facilitator compliance with the interview guide."""
    schema = """{
  "followed_guide": <boolean>,
  "explained_tool_before_use": <boolean — violation if true>,
  "coached_prompts": <boolean — violation if true>,
  "completed_debrief": <boolean>,
  "delivered_handoff": <boolean>,
  "used_timer": <boolean or null>,
  "workflow_selection_appropriate": <boolean>
}"""
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Analyze this interview transcript for FACILITATOR COMPLIANCE with the interview guide.\n\n"
        f"The facilitator should NOT: explain the tool before the tester uses it, coach the "
        f"tester on what prompts to write, guide the tester too much. The facilitator SHOULD: "
        f"complete the debrief section, deliver the M2 handoff, let the tester explore independently.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


def _assess_m3_candidacy(
    client: anthropic.Anthropic,
    text: str,
    observations: dict,
) -> dict:
    """Assess whether this tester is a good M3 candidate."""
    schema = """{
  "rating": "yes | maybe | no",
  "reasons": ["<string>"],
  "codebase_complex_enough": <boolean>,
  "target_industry": <boolean>,
  "phase2_potential": <boolean>,
  "engagement_level": "high | medium | low"
}"""
    obs_summary = json.dumps(observations, indent=2, default=str)
    return _call_claude(
        client,
        _SYSTEM_PREFIX,
        f"Based on this interview transcript and the extracted observations, assess whether "
        f"this tester is a good candidate for Milestone 3 (a proof-of-value comparison).\n\n"
        f"Good M3 candidates have: complex production codebases, high engagement, work in "
        f"target industries (finance, automotive, software publishing), potential for Phase 2 "
        f"deep indexing and security audit.\n\n"
        f"Observations summary:\n{obs_summary}\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{text}",
    )


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------


def analyze_m1(
    transcript_path: str | Path,
    video_path: str | Path | None = None,
    output_path: str | Path | None = None,
    tester_name: str | None = None,
    facilitator_is_first: bool = True,
) -> dict:
    """Run the full M1 analysis pipeline on a transcript.

    Returns the complete session JSON and writes it to output_path if specified.
    """
    client = anthropic.Anthropic()

    # Step 1: Parse transcript
    print("Parsing transcript...", file=sys.stderr)
    transcript = parse_transcript(transcript_path, facilitator_is_first)
    text = transcript_to_text(transcript)

    # Step 2: Extract session metadata
    print("Extracting session metadata...", file=sys.stderr)
    metadata = _extract_session_metadata(client, text, transcript)
    if tester_name:
        metadata["tester_name"] = tester_name
    if transcript.tester_name and not tester_name:
        metadata["tester_name"] = transcript.tester_name

    # Step 3: Extract observations (6 areas)
    print("Extracting installation observations...", file=sys.stderr)
    installation = _extract_installation(client, text)

    print("Extracting prompting observations...", file=sys.stderr)
    prompting = _extract_prompting(client, text)

    print("Extracting output review observations...", file=sys.stderr)
    output_review = _extract_output_review(client, text)

    print("Extracting LLM bias observations...", file=sys.stderr)
    llm_biases = _extract_llm_biases(client, text)

    print("Extracting trust observations...", file=sys.stderr)
    trust = _extract_trust(client, text)

    print("Extracting product feedback...", file=sys.stderr)
    product_feedback = _extract_product_feedback(client, text)

    observations = {
        "installation": installation,
        "prompting": prompting,
        "output_review": output_review,
        "llm_biases": llm_biases,
        "trust": trust,
        "product_feedback": product_feedback,
    }

    # Validation rule 1: every area must be scored or marked insufficient
    for area_name, area_data in observations.items():
        if isinstance(area_data, dict) and area_data.get("error"):
            observations[area_name] = {
                "status": "insufficient_data",
                "reason": area_data["error"],
            }

    # Step 4: Detect use cases from transcript
    detected_ucs = detect_use_cases(text)

    # Step 5: Facilitator compliance
    print("Checking facilitator compliance...", file=sys.stderr)
    compliance = _extract_facilitator_compliance(client, text)

    # Step 6: M3 candidacy
    print("Assessing M3 candidacy...", file=sys.stderr)
    m3_candidacy = _assess_m3_candidacy(client, text, observations)

    # Step 7: Compute phase durations from timestamps
    phase_durations = _compute_phase_durations(transcript)

    # Assemble session JSON
    session = {
        "milestone": "M1",
        "tester": {
            "name": metadata.get("tester_name"),
            "date": metadata.get("date") or str(date.today()),
            "ide": metadata.get("ide", "unknown"),
            "codebase": metadata.get("codebase", {}),
        },
        "session": {
            "total_duration_minutes": metadata.get("total_duration_minutes"),
            "setup_duration_minutes": installation.get("setup_duration_minutes"),
            "exploration_duration_minutes": phase_durations.get("exploration"),
            "debrief_duration_minutes": phase_durations.get("debrief"),
            "workflows_attempted": detected_ucs[:5],  # top 5 detected
            "workflows_completed": detected_ucs[:3],  # conservative estimate
            "debrief_completed": metadata.get("debrief_completed", False),
            "handoff_delivered": metadata.get("handoff_delivered", False),
            "killer_question_asked": metadata.get("killer_question_asked", False),
            "killer_question_answer": metadata.get("killer_question_answer"),
        },
        "observations": observations,
        "m3_candidacy": m3_candidacy,
        "facilitator_compliance": compliance,
        "video_path": str(video_path) if video_path else None,
        "transcript_format": transcript.format_detected,
        "utterance_count": len(transcript.utterances),
    }

    # Write output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
        print(f"Session JSON written to {output_path}", file=sys.stderr)
    else:
        # Default output path
        name = (metadata.get("tester_name") or "unknown").replace(" ", "_").lower()
        dt = metadata.get("date") or str(date.today())
        default_path = Path("data/sessions") / f"{name}_{dt}.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
        print(f"Session JSON written to {default_path}", file=sys.stderr)

    return session


def _compute_phase_durations(transcript: Transcript) -> dict[str, float | None]:
    """Estimate phase durations from timestamped utterances."""
    if not transcript.utterances or transcript.utterances[0].timestamp is None:
        return {}

    phase_ranges: dict[str, tuple[float, float]] = {}
    for utt in transcript.utterances:
        if utt.phase and utt.timestamp is not None:
            if utt.phase not in phase_ranges:
                phase_ranges[utt.phase] = (utt.timestamp, utt.timestamp)
            else:
                start, _ = phase_ranges[utt.phase]
                phase_ranges[utt.phase] = (start, utt.timestamp)

    return {
        phase: round((end - start) / 60, 1)
        for phase, (start, end) in phase_ranges.items()
        if end > start
    }
