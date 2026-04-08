"""Cross-tester pattern detection and synthesis across sessions."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

from rubberduck_analyzer.outputs.excel_writer import generate_workbook
from rubberduck_analyzer.outputs.report_writer import generate_report


def _load_sessions(sessions_dir: str | Path) -> list[dict]:
    """Load all session JSONs from a directory."""
    sessions_dir = Path(sessions_dir)
    sessions: list[dict] = []
    for f in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
    return sessions


def _installation_patterns(sessions: list[dict]) -> dict:
    """Detect installation/setup patterns across sessions."""
    methods: list[str] = []
    durations: list[float] = []
    all_blockers: list[str] = []
    interventions = 0

    for s in sessions:
        inst = s.get("observations", {}).get("installation", {})
        if inst.get("setup_method"):
            methods.append(inst["setup_method"])
        if inst.get("setup_duration_minutes") is not None:
            durations.append(inst["setup_duration_minutes"])
        for blocker in inst.get("blockers", []):
            cat = blocker.get("category", blocker.get("description", "unknown"))
            all_blockers.append(cat)
        if inst.get("facilitator_intervention_required"):
            interventions += 1

    blocker_counts = Counter(all_blockers).most_common(10)

    return {
        "sessions_with_issues": sum(1 for m in methods if m != "pre-call"),
        "total_sessions": len(sessions),
        "issue_rate": round(sum(1 for m in methods if m != "pre-call") / max(len(sessions), 1), 2),
        "setup_methods": dict(Counter(methods)),
        "avg_setup_minutes": round(mean(durations), 1) if durations else None,
        "most_common_blockers": [{"blocker": b, "count": c} for b, c in blocker_counts],
        "facilitator_interventions": interventions,
    }


def _prompting_patterns(sessions: list[dict]) -> dict:
    """Detect prompting behavior patterns."""
    independence_scores: list[int] = []
    styles: list[str] = []
    mcp_usage: list[str] = []
    tool_name_mentions = 0

    for s in sessions:
        prompt = s.get("observations", {}).get("prompting", {})
        if prompt.get("prompt_independence") is not None:
            independence_scores.append(prompt["prompt_independence"])
        if prompt.get("prompt_style"):
            styles.append(prompt["prompt_style"])
        if prompt.get("mcp_tool_usage"):
            mcp_usage.append(prompt["mcp_tool_usage"])
        if prompt.get("mentions_tool_names"):
            tool_name_mentions += 1

    return {
        "avg_independence": round(mean(independence_scores), 1) if independence_scores else None,
        "prompt_styles": dict(Counter(styles)),
        "mcp_usage_breakdown": dict(Counter(mcp_usage)),
        "mcp_ignored_rate": round(
            sum(1 for u in mcp_usage if u == "ide_ignored_mcp") / max(len(mcp_usage), 1), 2
        ),
        "tool_name_mention_rate": round(tool_name_mentions / max(len(sessions), 1), 2),
    }


def _trust_patterns(sessions: list[dict]) -> dict:
    """Detect trust patterns."""
    scores: list[float] = []
    would_use_again = 0
    would_not = 0

    for s in sessions:
        trust = s.get("observations", {}).get("trust", {})
        if trust.get("trust_score") is not None:
            scores.append(trust["trust_score"])
        if trust.get("would_use_again") is True:
            would_use_again += 1
        elif trust.get("would_use_again") is False:
            would_not += 1

    return {
        "avg_trust_score": round(mean(scores), 1) if scores else None,
        "trust_scores": scores,
        "would_use_again": would_use_again,
        "would_not_use_again": would_not,
        "no_answer": len(sessions) - would_use_again - would_not,
    }


def _feedback_patterns(sessions: list[dict]) -> dict:
    """Aggregate and rank product feedback."""
    all_requests: list[dict] = []
    all_complaints: list[dict] = []
    all_comparisons: list[dict] = []

    for s in sessions:
        feedback = s.get("observations", {}).get("product_feedback", {})
        all_requests.extend(feedback.get("feature_requests", []))
        all_complaints.extend(feedback.get("complaints", []))
        all_comparisons.extend(feedback.get("comparisons_to_competitors", []))

    # Deduplicate by description similarity (simple exact match)
    request_counts = Counter(r.get("description", "") for r in all_requests)
    complaint_counts = Counter(c.get("description", "") for c in all_complaints)

    return {
        "feature_requests_ranked": [
            {"description": desc, "frequency": count}
            for desc, count in request_counts.most_common(20)
        ],
        "complaints_ranked": [
            {"description": desc, "frequency": count}
            for desc, count in complaint_counts.most_common(20)
        ],
        "competitor_comparisons": [
            {
                "competitor": c.get("competitor"),
                "feature": c.get("feature"),
                "verdict": c.get("verdict"),
            }
            for c in all_comparisons
        ],
        "total_feature_requests": len(all_requests),
        "total_complaints": len(all_complaints),
    }


def _codebase_patterns(sessions: list[dict]) -> dict:
    """Analyze codebase quality correlation with session quality."""
    types: list[str] = []
    industries: list[str] = []
    sizes: list[str] = []

    for s in sessions:
        cb = s.get("tester", {}).get("codebase", {})
        if cb.get("type"):
            types.append(cb["type"])
        if cb.get("industry"):
            industries.append(cb["industry"])
        if cb.get("size"):
            sizes.append(cb["size"])

    return {
        "codebase_types": dict(Counter(types)),
        "industries": dict(Counter(industries)),
        "sizes": dict(Counter(sizes)),
    }


def _compliance_patterns(sessions: list[dict]) -> dict:
    """Aggregate facilitator compliance."""
    followed = 0
    explained_before = 0
    coached = 0
    debrief_complete = 0
    handoff_complete = 0

    for s in sessions:
        comp = s.get("facilitator_compliance", {})
        if comp.get("followed_guide"):
            followed += 1
        if comp.get("explained_tool_before_use"):
            explained_before += 1
        if comp.get("coached_prompts"):
            coached += 1
        if comp.get("completed_debrief"):
            debrief_complete += 1
        if comp.get("delivered_handoff"):
            handoff_complete += 1

    n = max(len(sessions), 1)
    return {
        "guide_followed_rate": round(followed / n, 2),
        "explained_before_use_rate": round(explained_before / n, 2),
        "coached_prompts_rate": round(coached / n, 2),
        "debrief_completion_rate": round(debrief_complete / n, 2),
        "handoff_completion_rate": round(handoff_complete / n, 2),
        "most_common_violations": [
            v for v in [
                ("explained_tool_before_use", explained_before),
                ("coached_prompts", coached),
                ("incomplete_debrief", len(sessions) - debrief_complete),
                ("missing_handoff", len(sessions) - handoff_complete),
            ] if v[1] > 0
        ],
    }


def _generate_action_items(patterns: dict) -> list[dict]:
    """Generate prioritized action items from patterns."""
    items: list[dict] = []

    # Installation blockers
    inst = patterns.get("installation", {})
    for blocker in inst.get("most_common_blockers", [])[:5]:
        items.append({
            "priority": "high" if blocker["count"] >= 2 else "medium",
            "category": "installation",
            "description": f"Fix: {blocker['blocker']}",
            "source": "cross-tester pattern",
            "frequency": blocker["count"],
        })

    # Top feature requests
    feedback = patterns.get("feedback", {})
    for req in feedback.get("feature_requests_ranked", [])[:5]:
        items.append({
            "priority": "high" if req["frequency"] >= 2 else "medium",
            "category": "feature_request",
            "description": req["description"],
            "source": "user feedback",
            "frequency": req["frequency"],
        })

    # Top complaints
    for complaint in feedback.get("complaints_ranked", [])[:5]:
        items.append({
            "priority": "high" if complaint["frequency"] >= 2 else "medium",
            "category": "complaint",
            "description": complaint["description"],
            "source": "user feedback",
            "frequency": complaint["frequency"],
        })

    # Sort by priority then frequency
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (priority_order.get(x["priority"], 3), -x.get("frequency", 0)))

    return items


def synthesize_sessions(
    sessions_dir: str | Path,
    output_dir: str | Path | None = None,
) -> dict:
    """Run cross-tester synthesis on all session JSONs.

    Requires 3+ sessions for meaningful patterns.

    Returns synthesis result dict and generates Excel + Markdown reports.
    """
    sessions = _load_sessions(sessions_dir)

    if len(sessions) < 3:
        print(f"Warning: only {len(sessions)} sessions found. 3+ recommended for patterns.", file=sys.stderr)

    print(f"Synthesizing across {len(sessions)} sessions...", file=sys.stderr)

    # Detect patterns
    patterns = {
        "installation": _installation_patterns(sessions),
        "prompting": _prompting_patterns(sessions),
        "trust": _trust_patterns(sessions),
        "feedback": _feedback_patterns(sessions),
        "codebase": _codebase_patterns(sessions),
        "compliance": _compliance_patterns(sessions),
    }

    action_items = _generate_action_items(patterns)

    # Generate outputs
    out_dir = Path(output_dir) if output_dir else Path("data/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Excel workbook
    print("Generating Excel workbook...", file=sys.stderr)
    excel_path = generate_workbook(
        sessions=sessions,
        patterns=patterns,
        action_items=action_items,
        output_path=out_dir / "analysis.xlsx",
    )
    print(f"Excel report: {excel_path}", file=sys.stderr)

    # Markdown report
    print("Generating Markdown report...", file=sys.stderr)
    md_path = generate_report(
        sessions=sessions,
        patterns=patterns,
        action_items=action_items,
        output_path=out_dir / "engineering_report.md",
    )
    print(f"Markdown report: {md_path}", file=sys.stderr)

    # Save raw patterns JSON
    patterns_path = out_dir / "patterns.json"
    patterns_path.write_text(json.dumps(patterns, indent=2, default=str), encoding="utf-8")

    return {
        "session_count": len(sessions),
        "patterns": patterns,
        "action_items": action_items,
        "excel_path": str(excel_path),
        "markdown_path": str(md_path),
    }
