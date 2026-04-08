"""M1 session analysis — evidence-anchored observations via Claude API."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import anthropic

from rubberduck_analyzer.analyzers.transcript_analyzer import (
    Transcript,
    parse_transcript,
    transcript_to_indexed_text,
    transcript_to_text,
)
from rubberduck_analyzer.analyzers.claude_client import call_claude as _call_claude
from rubberduck_analyzer.context.use_case_registry import detect_use_cases


# ---------------------------------------------------------------------------
# System prompt — shared across all extraction calls
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a senior UX researcher analyzing a user testing interview for RubberDuck, "
    "an AI-powered code analysis tool using MCP integration with IDEs.\n\n"
    "EVIDENCE FORMAT — for every observation, provide an 'evidence' array:\n"
    "Each evidence item MUST have:\n"
    "- 'insight': your analytical finding paraphrased in your own words (NOT a raw quote)\n"
    "- 'supporting_quote': the exact words from the transcript that support this insight\n"
    "- 'utterance_index': the [N] number from the transcript line\n"
    "- 'speaker': 'facilitator' or 'tester'\n"
    "- 'phase': the phase tag from the transcript line (setup/baseline/exploration/debrief/handoff)\n\n"
    "ANALYSIS DEPTH — for every observation area:\n"
    "- Explain the ROOT CAUSE (WHY something happened, not just WHAT)\n"
    "- Assess SEVERITY (how much this affects the product's success)\n"
    "- Note CROSS-CONNECTIONS to other observation areas when relevant\n\n"
    "Return ONLY valid JSON matching the requested schema."
)


# ---------------------------------------------------------------------------
# Evidence schema fragment (reused in all prompts)
# ---------------------------------------------------------------------------

_EVIDENCE_SCHEMA = """
"evidence": [{
  "insight": "<your analytical finding in your own words — NOT a raw quote>",
  "supporting_quote": "<exact words from the transcript>",
  "utterance_index": <the [N] number from the transcript>,
  "speaker": "facilitator | tester",
  "phase": "setup | baseline | exploration | debrief | handoff"
}]
"""


# ---------------------------------------------------------------------------
# Batched observation extraction (2 calls for 6 areas)
# ---------------------------------------------------------------------------


def _extract_observations_batch_1(client: anthropic.Anthropic, indexed_text: str) -> dict:
    """Extract installation, prompting, and output review with evidence chains."""
    schema = """{
  "installation": {
    "setup_method": "pre-call | on-call | failed",
    "setup_duration_minutes": <number or null>,
    "blockers": [{"description": "<string>", "category": "token_confusion | mcp_config | ide_specific | github_app | indexing | other", "root_cause": "<WHY this blocker occurred>", "severity": "blocker | major | minor"}],
    "facilitator_intervention_required": <boolean>,
    "summary": "<2-3 sentence analytical summary of setup experience>",
    """ + _EVIDENCE_SCHEMA + """
  },
  "prompting": {
    "prompt_independence": <1-5, where 1=needed full guidance and 5=wrote own prompts>,
    "prompt_style": "copied_from_website | natural_language | tool_specific | needed_help",
    "mentions_tool_names": <boolean>,
    "mcp_tool_usage": "used_correctly | ide_ignored_mcp | used_grep_instead | not_reached",
    "prompt_evolution": "<did their prompting improve over the session? describe the arc>",
    "summary": "<2-3 sentence analytical summary>",
    """ + _EVIDENCE_SCHEMA + """
  },
  "output_review": {
    "review_depth": <1-5, where 1=glanced and 5=verified line by line>,
    "verified_against_knowledge": <boolean>,
    "identified_errors": ["<description>"],
    "identified_correct": ["<description>"],
    "skipped_sections": ["<what they ignored and why>"],
    "comprehension_level": "<did they understand what the output meant? high/medium/low>",
    "summary": "<2-3 sentence analytical summary>",
    """ + _EVIDENCE_SCHEMA + """
  }
}"""
    return _call_claude(
        client,
        _SYSTEM,
        f"Analyze this interview transcript and extract THREE observation areas.\n\n"
        f"For each area, provide root-cause analysis (WHY, not just WHAT) and cite evidence "
        f"using the utterance [N] indices from the transcript.\n\n"
        f"1. INSTALLATION: setup friction, blockers with root causes, MCP config issues\n"
        f"2. PROMPTING: independence level, style evolution over session, MCP tool usage\n"
        f"3. OUTPUT REVIEW: depth of review, what they verified vs skipped, comprehension\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"INDEXED TRANSCRIPT:\n{indexed_text}",
    )


def _extract_observations_batch_2(client: anthropic.Anthropic, indexed_text: str) -> dict:
    """Extract LLM biases, trust, and product feedback with evidence chains."""
    schema = """{
  "llm_biases": {
    "pre_existing_bias": "<analytical description of their AI tool assumptions>",
    "bias_confirmed": <boolean>,
    "bias_challenged": <boolean>,
    "projected_limitations": ["<limitation assumed from other tools>"],
    "bias_trajectory": "<how did their bias change over the session?>",
    "summary": "<2-3 sentence analytical summary>",
    """ + _EVIDENCE_SCHEMA + """
  },
  "trust": {
    "trust_score": <float 0-10 scale. MUST be 0-10. Convert percentages: 82%=8.2. If they say 'I trust it' without a number, estimate with reasoning>,
    "trust_score_reasoning": "<how you determined the score — direct quote or inference>",
    "trust_trajectory": [{"moment": "<what happened>", "direction": "increased | decreased", "utterance_index": <N>}],
    "would_use_again": <boolean or null>,
    "would_ship_based_on_output": <boolean or null>,
    "comparison_to_other_tools": "<analytical comparison, not just a quote>",
    "trust_drivers": "<what specifically builds trust in this tool for this tester>",
    "trust_barriers": "<what specifically undermines trust>",
    "summary": "<2-3 sentence analytical summary>",
    """ + _EVIDENCE_SCHEMA + """
  },
  "product_feedback": {
    "feature_requests": [{"description": "<string>", "priority": "high | medium | low", "category": "<string>", "reasoning": "<why they want this>"}],
    "complaints": [{"description": "<string>", "severity": "blocker | major | minor", "root_cause": "<underlying problem>"}],
    "comparisons_to_competitors": [{"competitor": "<name>", "feature": "<what they compared>", "verdict": "RD_better | competitor_better | tie", "reasoning": "<why>"}],
    "positive_signals": ["<things that worked well or impressed them>"],
    "summary": "<2-3 sentence analytical summary>",
    """ + _EVIDENCE_SCHEMA + """
  }
}"""
    return _call_claude(
        client,
        _SYSTEM,
        f"Analyze this interview transcript and extract THREE observation areas.\n\n"
        f"For each area, provide root-cause analysis and cite evidence using utterance [N] indices.\n\n"
        f"1. LLM BIASES: pre-existing AI assumptions, how bias evolved over session\n"
        f"2. TRUST: score on 0-10 scale (MUST normalize — convert percentages, estimate if implicit), "
        f"trust trajectory with turning points, what drives and undermines trust\n"
        f"3. PRODUCT FEEDBACK: feature requests with reasoning, complaints with root causes, "
        f"competitor comparisons with analysis, positive signals\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"INDEXED TRANSCRIPT:\n{indexed_text}",
    )


# ---------------------------------------------------------------------------
# Session metadata + compliance + M3 candidacy
# ---------------------------------------------------------------------------


def _extract_session_metadata(
    client: anthropic.Anthropic,
    indexed_text: str,
    transcript: Transcript,
) -> dict:
    """Extract tester and session metadata."""
    schema = """{
  "tester_name": "<name or null>",
  "date": "<ISO date or null>",
  "ide": "Cursor | Codex | Claude Code | VS Code | unknown",
  "codebase": {
    "name": "<string or null>",
    "language": "<string>",
    "type": "production | personal | forked | toy",
    "domain": "<string — e.g., medical backend, ML training>",
    "industry": "<string or null — finance, automotive, software publishing, other>",
    "size": "small (<5k LOC) | medium (5k-50k LOC) | large (50k+ LOC) | unknown",
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
        _SYSTEM,
        f"Extract session metadata from this transcript. Look for: tester name, date, IDE, "
        f"codebase details, duration, whether debrief happened, whether M2 handoff was delivered.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{indexed_text}",
    )


def _extract_facilitator_compliance(
    client: anthropic.Anthropic,
    indexed_text: str,
) -> dict:
    """Check facilitator compliance with evidence."""
    schema = """{
  "followed_guide": <boolean>,
  "explained_tool_before_use": <boolean — VIOLATION if true>,
  "coached_prompts": <boolean — VIOLATION if true>,
  "guided_too_much": <boolean — VIOLATION if true>,
  "completed_debrief": <boolean>,
  "delivered_handoff": <boolean>,
  "used_timer": <boolean or null>,
  "workflow_selection_appropriate": <boolean>,
  "violations": [{
    "type": "explained_tool_before_use | coached_prompts | guided_too_much",
    "description": "<what happened>",
    "impact": "<how this affected the session quality>",
    "utterance_index": <N>
  }],
  "summary": "<2-3 sentence assessment of facilitator performance>"
}"""
    return _call_claude(
        client,
        _SYSTEM,
        f"Analyze facilitator compliance. The facilitator should NOT: explain the tool before "
        f"the tester uses it, coach prompts, or guide too much. They SHOULD: complete debrief, "
        f"deliver M2 handoff, let tester explore independently.\n\n"
        f"For each violation, cite the utterance index and assess impact on session quality.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{indexed_text}",
    )


def _assess_m3_candidacy(
    client: anthropic.Anthropic,
    indexed_text: str,
    observations: dict,
) -> dict:
    """Assess M3 candidacy with calibrated reasoning."""
    schema = """{
  "rating": "yes | maybe | no",
  "confidence": "high | medium | low",
  "reasons": ["<specific, evidence-backed reason>"],
  "concerns": ["<specific risk if proceeding to M3>"],
  "codebase_complex_enough": <boolean>,
  "target_industry": <boolean>,
  "phase2_potential": <boolean>,
  "engagement_level": "high | medium | low",
  "recommended_m3_task": "<if yes/maybe, what specific hard task would suit their codebase>",
  "summary": "<2-3 sentence recommendation with clear logic>"
}"""
    obs_summary = json.dumps(observations, indent=2, default=str)[:3000]
    return _call_claude(
        client,
        _SYSTEM,
        f"Assess M3 candidacy. Calibration guidelines:\n"
        f"- 'yes': production codebase + high engagement + target industry + clear POV task\n"
        f"- 'maybe': mixed signals (good codebase but low engagement, or high engagement but toy codebase)\n"
        f"- 'no': tool didn't work, tester disengaged, or codebase unsuitable\n\n"
        f"Be specific — cite what in their session supports each reason.\n\n"
        f"Observations:\n{obs_summary}\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TRANSCRIPT:\n{indexed_text}",
    )


# ---------------------------------------------------------------------------
# Video integration
# ---------------------------------------------------------------------------


def _integrate_video_analysis(session: dict, video_analysis: dict) -> None:
    """Enrich session data with video analysis findings."""
    if not video_analysis:
        return

    session["video_analysis"] = {
        "duration_minutes": video_analysis.get("duration_minutes"),
        "frame_count": video_analysis.get("frame_count"),
        "screen_share_detected": video_analysis.get("screen_share_detected"),
        "tools_observed": video_analysis.get("tools_observed", []),
        "mcp_tools_used": video_analysis.get("mcp_tools_used", False),
        "grep_cat_observed": video_analysis.get("grep_cat_observed", False),
    }

    # Cross-reference: if video shows grep/cat but prompting says MCP used, flag conflict
    prompting = session.get("observations", {}).get("prompting", {})
    if video_analysis.get("grep_cat_observed") and prompting.get("mcp_tool_usage") == "used_correctly":
        if "video_conflicts" not in session:
            session["video_conflicts"] = []
        session["video_conflicts"].append({
            "area": "prompting",
            "conflict": "Video shows grep/cat commands but transcript analysis marked MCP as 'used_correctly'",
            "recommendation": "Review video frames — IDE may have fallen back to grep despite MCP being available",
        })

    # Use video duration as ground truth if transcript estimate differs significantly
    vid_dur = video_analysis.get("duration_minutes")
    sess_dur = session.get("session", {}).get("total_duration_minutes")
    if vid_dur and sess_dur and abs(vid_dur - sess_dur) > 10:
        session.setdefault("video_conflicts", []).append({
            "area": "duration",
            "conflict": f"Video duration ({vid_dur:.0f}m) differs from transcript estimate ({sess_dur:.0f}m) by {abs(vid_dur - sess_dur):.0f}m",
            "recommendation": "Use video duration as ground truth",
        })
        session["session"]["total_duration_minutes"] = vid_dur


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
    """Run the full M1 analysis pipeline.

    Produces evidence-anchored observations with transcript location references.
    """
    client = anthropic.Anthropic()

    # Step 1: Parse transcript
    print("Parsing transcript...", file=sys.stderr)
    transcript = parse_transcript(transcript_path, facilitator_is_first)
    indexed_text = transcript_to_indexed_text(transcript)

    # Step 2: Extract session metadata
    print("Extracting session metadata...", file=sys.stderr)
    metadata = _extract_session_metadata(client, indexed_text, transcript)
    if tester_name:
        metadata["tester_name"] = tester_name
    elif transcript.tester_name:
        metadata["tester_name"] = transcript.tester_name

    # Step 3: Extract observations (6 areas in 2 batched calls)
    print("Extracting observations batch 1 (installation, prompting, output review)...", file=sys.stderr)
    batch_1 = _extract_observations_batch_1(client, indexed_text)

    print("Extracting observations batch 2 (LLM biases, trust, product feedback)...", file=sys.stderr)
    batch_2 = _extract_observations_batch_2(client, indexed_text)

    observations = {
        "installation": batch_1.get("installation", {}),
        "prompting": batch_1.get("prompting", {}),
        "output_review": batch_1.get("output_review", {}),
        "llm_biases": batch_2.get("llm_biases", {}),
        "trust": batch_2.get("trust", {}),
        "product_feedback": batch_2.get("product_feedback", {}),
    }

    # Validation: mark areas with errors as insufficient
    for area_name, area_data in observations.items():
        if isinstance(area_data, dict) and area_data.get("error"):
            observations[area_name] = {
                "status": "insufficient_data",
                "reason": area_data["error"],
            }

    # Step 4: Detect use cases
    detected_ucs = detect_use_cases(transcript_to_text(transcript))

    # Step 5: Facilitator compliance
    print("Checking facilitator compliance...", file=sys.stderr)
    compliance = _extract_facilitator_compliance(client, indexed_text)

    # Step 6: M3 candidacy
    print("Assessing M3 candidacy...", file=sys.stderr)
    m3_candidacy = _assess_m3_candidacy(client, indexed_text, observations)

    # Step 7: Phase durations
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
            "setup_duration_minutes": observations.get("installation", {}).get("setup_duration_minutes"),
            "exploration_duration_minutes": phase_durations.get("exploration"),
            "debrief_duration_minutes": phase_durations.get("debrief"),
            "workflows_attempted": detected_ucs[:5],
            "workflows_completed": detected_ucs[:3],
            "debrief_completed": metadata.get("debrief_completed", False),
            "handoff_delivered": metadata.get("handoff_delivered", False),
            "killer_question_asked": metadata.get("killer_question_asked", False),
            "killer_question_answer": metadata.get("killer_question_answer"),
        },
        "observations": observations,
        "m3_candidacy": m3_candidacy,
        "facilitator_compliance": compliance,
        "transcript_format": transcript.format_detected,
        "utterance_count": len(transcript.utterances),
    }

    # Step 8: Video integration (if provided)
    if video_path and Path(video_path).is_file():
        print("Analyzing video...", file=sys.stderr)
        from rubberduck_analyzer.analyzers.video_analyzer import (
            analyze_video,
            video_analysis_to_dict,
        )
        va = analyze_video(video_path)
        _integrate_video_analysis(session, video_analysis_to_dict(va))

    # Write output
    if output_path:
        output_path = Path(output_path)
    else:
        name = (metadata.get("tester_name") or "unknown").replace(" ", "_").lower()
        dt = metadata.get("date") or str(date.today())
        output_path = Path("data/sessions") / f"{name}_{dt}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
    print(f"Session JSON written to {output_path}", file=sys.stderr)

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
