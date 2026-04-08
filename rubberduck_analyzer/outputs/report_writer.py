"""Markdown report generation for engineering team."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from rubberduck_analyzer.synthesizer.evidence_tracker import evidence_coverage_report


def generate_report(
    sessions: list[dict],
    patterns: dict,
    action_items: list[dict],
    output_path: str | Path = "data/reports/engineering_report.md",
) -> Path:
    """Generate the engineering team Markdown report.

    Structured as:
    - Executive summary
    - Critical issues (blockers)
    - Usability issues (friction)
    - Feature gaps
    - Trust signals
    - Evidence inventory
    - Recommended next steps
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sections: list[str] = []

    # Header
    sections.append(f"# RubberDuck User Testing Report")
    sections.append(f"Generated: {date.today()}")
    sections.append(f"Sessions analyzed: {len(sessions)}")
    sections.append("")

    # Executive Summary
    sections.append("## Executive Summary")
    sections.append("")
    sections.append(_executive_summary(sessions, patterns))
    sections.append("")

    # Critical Issues
    sections.append("## Critical Issues (Blockers)")
    sections.append("")
    sections.append(_critical_issues(patterns, action_items))
    sections.append("")

    # Usability Issues
    sections.append("## Usability Issues (Friction)")
    sections.append("")
    sections.append(_usability_issues(patterns))
    sections.append("")

    # Feature Gaps
    sections.append("## Feature Gaps")
    sections.append("")
    sections.append(_feature_gaps(patterns))
    sections.append("")

    # Trust Signals
    sections.append("## Trust Signals")
    sections.append("")
    sections.append(_trust_signals(patterns))
    sections.append("")

    # Evidence Inventory
    sections.append("## Evidence Inventory")
    sections.append("")
    sections.append(evidence_coverage_report(sessions))
    sections.append("")

    # Recommended Next Steps
    sections.append("## Recommended Next Steps")
    sections.append("")
    sections.append(_next_steps(action_items))
    sections.append("")

    # Facilitator Compliance
    sections.append("## Facilitator Compliance")
    sections.append("")
    sections.append(_compliance_section(patterns))
    sections.append("")

    report = "\n".join(sections)
    output_path.write_text(report, encoding="utf-8")
    return output_path


def _executive_summary(sessions: list[dict], patterns: dict) -> str:
    """Generate 3-5 bullet executive summary."""
    inst = patterns.get("installation", {})
    trust = patterns.get("trust", {})
    feedback = patterns.get("feedback", {})

    bullets: list[str] = []

    # Installation rate
    issue_rate = inst.get("issue_rate", 0)
    if issue_rate > 0.5:
        bullets.append(f"- **Installation remains the #1 barrier**: {int(issue_rate * 100)}% of sessions had setup issues")

    # Trust
    avg_trust = trust.get("avg_trust_score")
    if avg_trust is not None:
        bullets.append(f"- Average trust score: **{avg_trust}/10** across {len(sessions)} sessions")

    # Top feedback
    top_requests = feedback.get("feature_requests_ranked", [])
    if top_requests:
        top = top_requests[0]
        bullets.append(f"- Most requested feature: **{top['description']}** ({top['frequency']} testers)")

    # MCP usage
    prompting = patterns.get("prompting", {})
    mcp_ignored = prompting.get("mcp_ignored_rate", 0)
    if mcp_ignored > 0.3:
        bullets.append(f"- MCP tools ignored by IDE in **{int(mcp_ignored * 100)}%** of sessions")

    # Compliance
    compliance = patterns.get("compliance", {})
    guide_rate = compliance.get("guide_followed_rate", 0)
    if guide_rate < 0.5:
        bullets.append(f"- Facilitator guide followed in only **{int(guide_rate * 100)}%** of sessions")

    if not bullets:
        bullets.append(f"- {len(sessions)} sessions analyzed — see details below")

    return "\n".join(bullets)


def _critical_issues(patterns: dict, action_items: list[dict]) -> str:
    """List critical blockers."""
    blockers = [a for a in action_items if a.get("priority") == "high"]
    if not blockers:
        return "No critical blockers identified."

    lines: list[str] = []
    for item in blockers[:10]:
        lines.append(f"- **{item['description']}** (reported {item.get('frequency', '?')}x, source: {item.get('source', 'unknown')})")
    return "\n".join(lines)


def _usability_issues(patterns: dict) -> str:
    """Describe friction points."""
    lines: list[str] = []

    inst = patterns.get("installation", {})
    blockers = inst.get("most_common_blockers", [])
    if blockers:
        lines.append("### Setup Friction")
        for b in blockers[:5]:
            lines.append(f"- {b['blocker']}: {b['count']} occurrences")

    avg_setup = inst.get("avg_setup_minutes")
    if avg_setup:
        lines.append(f"\nAverage setup time: **{avg_setup} minutes**")

    prompting = patterns.get("prompting", {})
    avg_ind = prompting.get("avg_independence")
    if avg_ind:
        lines.append(f"\n### Prompting")
        lines.append(f"Average prompt independence: **{avg_ind}/5**")

    styles = prompting.get("prompt_styles", {})
    if styles:
        lines.append("Prompt styles observed:")
        for style, count in styles.items():
            lines.append(f"  - {style}: {count}")

    return "\n".join(lines) if lines else "No significant usability issues identified."


def _feature_gaps(patterns: dict) -> str:
    """List feature requests and competitor gaps."""
    feedback = patterns.get("feedback", {})
    lines: list[str] = []

    requests = feedback.get("feature_requests_ranked", [])
    if requests:
        lines.append("### Feature Requests (by frequency)")
        for r in requests[:10]:
            lines.append(f"- {r['description']} ({r['frequency']}x)")

    comparisons = feedback.get("competitor_comparisons", [])
    competitor_better = [c for c in comparisons if c.get("verdict") == "competitor_better"]
    if competitor_better:
        lines.append("\n### Competitor Advantages Cited")
        for c in competitor_better:
            lines.append(f"- **{c.get('competitor')}**: {c.get('feature')}")

    return "\n".join(lines) if lines else "No feature gaps identified."


def _trust_signals(patterns: dict) -> str:
    """Describe trust patterns."""
    trust = patterns.get("trust", {})
    lines: list[str] = []

    avg = trust.get("avg_trust_score")
    if avg:
        lines.append(f"Average trust score: **{avg}/10**")

    use_again = trust.get("would_use_again", 0)
    would_not = trust.get("would_not_use_again", 0)
    no_answer = trust.get("no_answer", 0)
    lines.append(f"Would use again: {use_again} yes, {would_not} no, {no_answer} no answer")

    scores = trust.get("trust_scores", [])
    if scores:
        lines.append(f"Trust score range: {min(scores)} to {max(scores)}")

    return "\n".join(lines) if lines else "Insufficient trust data."


def _next_steps(action_items: list[dict]) -> str:
    """Prioritized recommendations."""
    if not action_items:
        return "No action items generated. More sessions needed."

    lines: list[str] = []
    for i, item in enumerate(action_items[:15], 1):
        priority_marker = {"high": "P0", "medium": "P1", "low": "P2"}.get(item["priority"], "P?")
        lines.append(f"{i}. **[{priority_marker}]** {item['description']} ({item['category']})")

    return "\n".join(lines)


def _compliance_section(patterns: dict) -> str:
    """Facilitator compliance summary."""
    comp = patterns.get("compliance", {})
    lines: list[str] = []

    lines.append(f"Guide followed: **{int(comp.get('guide_followed_rate', 0) * 100)}%**")
    lines.append(f"Debrief completed: **{int(comp.get('debrief_completion_rate', 0) * 100)}%**")
    lines.append(f"Handoff delivered: **{int(comp.get('handoff_completion_rate', 0) * 100)}%**")

    violations = comp.get("most_common_violations", [])
    if violations:
        lines.append("\nMost common violations:")
        for v_name, v_count in violations:
            lines.append(f"  - {v_name}: {v_count} sessions")

    return "\n".join(lines)
