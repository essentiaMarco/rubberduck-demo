"""M3 proof-of-value comparison analysis with evidence classification."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import anthropic

from rubberduck_analyzer.analyzers.claude_client import call_claude as _call_claude
from rubberduck_analyzer.analyzers.transcript_analyzer import normalize_text
from rubberduck_analyzer.analyzers.video_analyzer import analyze_video, video_analysis_to_dict
from rubberduck_analyzer.context.use_case_registry import detect_use_cases, USE_CASES


_SYSTEM = (
    "You are an expert qualitative researcher analyzing a proof-of-value comparison "
    "for RubberDuck, an AI-powered code analysis tool. The tester performed the same "
    "hard task twice: once with normal tools, once with RubberDuck. Extract structured "
    "evidence from the provided materials. Return ONLY valid JSON."
)

HARD_TASK_CATEGORIES = [
    "security_audit",
    "industry_problem",
    "risky_pr",
    "multi_cause_bug",
    "blast_radius",
]

PREFERRED_CATEGORIES = ["security_audit", "industry_problem"]

PROOF_TO_SHIP_METRICS = ["HCR", "RCCR", "RPP", "BRP", "BRR", "MSPR", "RDSR"]


def _analyze_proposal(client: anthropic.Anthropic, proposal_text: str) -> dict:
    """Analyze the task proposal."""
    schema = """{
  "task_description": "<what they proposed to do>",
  "task_category": "<security_audit | industry_problem | risky_pr | multi_cause_bug | blast_radius | other>",
  "is_preferred_category": <boolean — true if security_audit or industry_problem>,
  "mapped_use_case": "<UC-XX or null>",
  "complexity_assessment": "<high | medium | low>",
  "suitable_for_comparison": <boolean>
}"""
    return _call_claude(
        client,
        _SYSTEM,
        f"Analyze this M3 task proposal. The tester was asked to propose a hard task for "
        f"proof-of-value comparison. Preferred categories are security audit (Phase 2 deep "
        f"indexing) and industry-specific problems. Fallback categories are risky PR review, "
        f"multi-cause bug, and blast radius analysis.\n\n"
        f"Map to use cases: UC-01 through UC-10 if applicable.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"TASK PROPOSAL:\n{proposal_text}",
    )


def _analyze_comparison(client: anthropic.Anthropic, comparison_text: str, proposal: dict) -> dict:
    """Analyze the written comparison between with/without RubberDuck."""
    schema = """{
  "task_performed_matches_proposal": <boolean>,
  "what_normal_tools_found": ["<findings without RubberDuck>"],
  "what_rubberduck_found": ["<findings with RubberDuck>"],
  "what_normal_tools_missed": ["<gaps in normal-tools approach>"],
  "what_rubberduck_missed": ["<gaps in RubberDuck approach>"],
  "time_without_minutes": <number or null>,
  "time_with_minutes": <number or null>,
  "which_they_trust_to_ship": "normal_tools | rubberduck | both | neither",
  "rubberduck_advantage_demonstrated": <boolean>,
  "verbatim_quotes": ["<key comparison statements>"]
}"""
    proposal_summary = json.dumps(proposal, indent=2, default=str)
    return _call_claude(
        client,
        _SYSTEM,
        f"Analyze this written comparison from an M3 proof-of-value session.\n\n"
        f"The approved task proposal was:\n{proposal_summary}\n\n"
        f"Check if the completed task matches the proposal. Extract what each approach "
        f"found and missed, time comparison, and which result they'd trust.\n\n"
        f"Return JSON matching this schema:\n{schema}\n\n"
        f"WRITTEN COMPARISON:\n{comparison_text}",
    )


def _classify_evidence(
    client: anthropic.Anthropic,
    proposal: dict,
    comparison: dict,
    video_without: dict | None,
    video_with: dict | None,
) -> dict:
    """Classify the evidence quality and type."""
    schema = """{
  "evidence_type": "paired-ablation | security-proof | industry-story | new-use-case",
  "evidence_quality": <1-5>,
  "comparison_clear": <boolean>,
  "rubberduck_advantage_demonstrated": <boolean>,
  "specific_findings_rubberduck_surfaced": ["<string>"],
  "specific_findings_normal_tools_missed": ["<string>"],
  "new_use_case_identified": "<string or null>",
  "metrics_touched": ["<HCR | RCCR | RPP | BRP | BRR | MSPR | RDSR>"],
  "proposal_match": <boolean>,
  "usable_for_marketing": <boolean>,
  "usable_for_investor_deck": <boolean>
}"""
    context = {
        "proposal": proposal,
        "comparison": comparison,
        "video_without_summary": {
            "duration_minutes": video_without.get("duration_minutes") if video_without else None,
            "tools_observed": video_without.get("tools_observed") if video_without else None,
        },
        "video_with_summary": {
            "duration_minutes": video_with.get("duration_minutes") if video_with else None,
            "tools_observed": video_with.get("tools_observed") if video_with else None,
            "mcp_tools_used": video_with.get("mcp_tools_used") if video_with else None,
        },
    }
    return _call_claude(
        client,
        _SYSTEM,
        f"Classify the evidence from this M3 proof-of-value comparison.\n\n"
        f"Evidence types:\n"
        f"- paired-ablation: valid side-by-side comparison of same task\n"
        f"- security-proof: demonstrates RubberDuck security audit capabilities\n"
        f"- industry-story: demonstrates value in a target industry context\n"
        f"- new-use-case: discovered a use case beyond UC-01 through UC-10\n\n"
        f"Metrics: HCR (Hidden Consumer Recall), RCCR (Root-Cause Completeness Rate), "
        f"RPP (Reachability Proof Precision), BRP/BRR (Blast Radius Precision/Recall), "
        f"MSPR (Minimal Safe Patch Rate), RDSR (Repair Dossier Sufficiency Rate)\n\n"
        f"Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"Return JSON matching this schema:\n{schema}",
    )


def analyze_m3(
    video_without_path: str | Path,
    video_with_path: str | Path,
    comparison_path: str | Path,
    proposal_path: str | Path,
    output_path: str | Path | None = None,
    tester_name: str | None = None,
) -> dict:
    """Run the full M3 analysis pipeline.

    Returns the M3 analysis JSON and writes it to output_path if specified.
    """
    client = anthropic.Anthropic()

    # Step 1: Parse proposal
    print("Analyzing task proposal...", file=sys.stderr)
    proposal_text = normalize_text(Path(proposal_path).read_text(encoding="utf-8"))
    proposal = _analyze_proposal(client, proposal_text)

    # Step 2: Parse written comparison
    print("Analyzing written comparison...", file=sys.stderr)
    comparison_text = normalize_text(Path(comparison_path).read_text(encoding="utf-8"))
    comparison = _analyze_comparison(client, comparison_text, proposal)

    # Step 3: Video analysis (both recordings)
    print("Analyzing video WITHOUT RubberDuck...", file=sys.stderr)
    va_without = analyze_video(video_without_path)
    video_without_data = video_analysis_to_dict(va_without)

    print("Analyzing video WITH RubberDuck...", file=sys.stderr)
    va_with = analyze_video(video_with_path)
    video_with_data = video_analysis_to_dict(va_with)

    # Step 4: Evidence classification
    print("Classifying evidence...", file=sys.stderr)
    evidence = _classify_evidence(
        client, proposal, comparison, video_without_data, video_with_data,
    )

    # Assemble result
    result = {
        "milestone": "M3",
        "tester_name": tester_name,
        "date": str(date.today()),
        "proposal": proposal,
        "comparison": comparison,
        "evidence": evidence,
        "evidence_type": evidence.get("evidence_type", "unknown"),
        "evidence_quality": evidence.get("evidence_quality"),
        "video_without": video_without_data,
        "video_with": video_with_data,
        "time_comparison": {
            "without_minutes": comparison.get("time_without_minutes"),
            "with_minutes": comparison.get("time_with_minutes"),
            "video_without_minutes": video_without_data.get("duration_minutes"),
            "video_with_minutes": video_with_data.get("duration_minutes"),
        },
    }

    # Write output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"M3 analysis written to {output_path}", file=sys.stderr)
    else:
        name = (tester_name or "unknown").replace(" ", "_").lower()
        default_path = Path("data/sessions") / f"{name}_m3_{date.today()}.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"M3 analysis written to {default_path}", file=sys.stderr)

    return result
