"""M3 evidence classification and aggregation across testers."""

from __future__ import annotations

import json
from pathlib import Path

PROOF_TO_SHIP_METRICS = ["HCR", "RCCR", "RPP", "BRP", "BRR", "MSPR", "RDSR"]


def aggregate_evidence(sessions: list[dict]) -> dict:
    """Aggregate M3 evidence across all sessions.

    Returns a summary of evidence coverage, quality, and gaps.
    """
    m3_sessions = [s for s in sessions if s.get("milestone") == "M3"]

    if not m3_sessions:
        return {
            "total_m3_sessions": 0,
            "evidence_types": {},
            "metric_coverage": {m: 0 for m in PROOF_TO_SHIP_METRICS},
            "avg_quality": None,
            "gaps": PROOF_TO_SHIP_METRICS[:],
            "marketing_ready": [],
            "investor_ready": [],
        }

    # Count evidence types
    evidence_types: dict[str, int] = {}
    qualities: list[int] = []
    metric_coverage: dict[str, int] = {m: 0 for m in PROOF_TO_SHIP_METRICS}
    marketing_ready: list[str] = []
    investor_ready: list[str] = []
    advantages_demonstrated: list[dict] = []

    for s in m3_sessions:
        ev = s.get("evidence", {})
        etype = ev.get("evidence_type", "unknown")
        evidence_types[etype] = evidence_types.get(etype, 0) + 1

        quality = ev.get("evidence_quality")
        if quality is not None:
            qualities.append(quality)

        for metric in ev.get("metrics_touched", []):
            if metric in metric_coverage:
                metric_coverage[metric] += 1

        tester = s.get("tester_name", "unknown")
        if ev.get("usable_for_marketing"):
            marketing_ready.append(tester)
        if ev.get("usable_for_investor_deck"):
            investor_ready.append(tester)

        if ev.get("rubberduck_advantage_demonstrated"):
            advantages_demonstrated.append({
                "tester": tester,
                "findings_surfaced": ev.get("specific_findings_rubberduck_surfaced", []),
                "normal_tools_missed": ev.get("specific_findings_normal_tools_missed", []),
            })

    # Identify metric gaps
    gaps = [m for m, count in metric_coverage.items() if count == 0]

    return {
        "total_m3_sessions": len(m3_sessions),
        "evidence_types": evidence_types,
        "metric_coverage": metric_coverage,
        "avg_quality": round(sum(qualities) / len(qualities), 1) if qualities else None,
        "gaps": gaps,
        "marketing_ready": marketing_ready,
        "investor_ready": investor_ready,
        "advantages_demonstrated": advantages_demonstrated,
    }


def evidence_coverage_report(sessions: list[dict]) -> str:
    """Generate a text summary of evidence coverage for the engineering report."""
    summary = aggregate_evidence(sessions)

    lines = [
        f"**M3 Evidence: {summary['total_m3_sessions']} sessions**",
        "",
    ]

    if summary["total_m3_sessions"] == 0:
        lines.append("No M3 proof-of-value comparisons completed yet.")
        return "\n".join(lines)

    # Evidence types
    lines.append("Evidence types collected:")
    for etype, count in summary["evidence_types"].items():
        lines.append(f"  - {etype}: {count}")

    # Quality
    if summary["avg_quality"]:
        lines.append(f"\nAverage evidence quality: {summary['avg_quality']}/5")

    # Metric coverage
    lines.append("\nProof-to-ship metric coverage:")
    for metric, count in summary["metric_coverage"].items():
        status = "covered" if count > 0 else "GAP"
        lines.append(f"  - {metric}: {count} sessions ({status})")

    # Gaps
    if summary["gaps"]:
        lines.append(f"\nMetric gaps (no evidence): {', '.join(summary['gaps'])}")

    # Marketing/investor readiness
    if summary["marketing_ready"]:
        lines.append(f"\nMarketing-ready evidence from: {', '.join(summary['marketing_ready'])}")
    if summary["investor_ready"]:
        lines.append(f"Investor-ready evidence from: {', '.join(summary['investor_ready'])}")

    return "\n".join(lines)
