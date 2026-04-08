"""Static registry of RubberDuck use cases UC-01 through UC-10."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UseCase:
    """A RubberDuck use case definition."""

    id: str
    name: str
    description: str
    keywords: list[str]
    tools: list[str]


USE_CASES: dict[str, UseCase] = {
    "UC-01": UseCase(
        id="UC-01",
        name="Understand Code",
        description="Map structure, entry points, data flow",
        keywords=[
            "understand", "structure", "entry point", "data flow",
            "how does this work", "what does this do", "overview",
            "architecture", "codebase", "navigate", "explore",
        ],
        tools=["symbols_overview", "call_chain", "trace_variable"],
    ),
    "UC-02": UseCase(
        id="UC-02",
        name="Security Audit",
        description="Entry-to-sink security paths (Phase 2 required)",
        keywords=[
            "security", "vulnerability", "audit", "injection",
            "sql injection", "xss", "csrf", "authentication",
            "authorization", "exploit", "attack", "penetration",
        ],
        tools=["security_audit"],
    ),
    "UC-03": UseCase(
        id="UC-03",
        name="Bug Localization",
        description="Root cause via variable tracing and control flow",
        keywords=[
            "bug", "error", "crash", "root cause", "debug",
            "why is this", "broken", "failing", "exception",
            "traceback", "stack trace", "unexpected",
        ],
        tools=["trace_variable", "call_chain"],
    ),
    "UC-04": UseCase(
        id="UC-04",
        name="Code Review",
        description="Review diffs for downstream-propagating bugs",
        keywords=[
            "code review", "review", "pull request", "pr",
            "diff", "change", "merge", "downstream", "propagat",
        ],
        tools=["find_consumers", "call_chain", "plan_change"],
    ),
    "UC-05": UseCase(
        id="UC-05",
        name="Change Impact",
        description="Blast radius before modifying a function",
        keywords=[
            "impact", "blast radius", "what will break", "affected",
            "downstream", "ripple", "dependency", "consumers",
            "if i change", "what happens if",
        ],
        tools=["plan_change", "find_consumers"],
    ),
    "UC-06": UseCase(
        id="UC-06",
        name="Plan Features",
        description="Plan a new feature tests-first using existing patterns",
        keywords=[
            "plan", "feature", "implement", "new function",
            "add", "create", "build", "tests first", "tdd",
            "existing pattern", "similar to",
        ],
        tools=["symbols_overview", "search_code", "call_chain"],
    ),
    "UC-07": UseCase(
        id="UC-07",
        name="Generate Code",
        description="Generate code matching existing style",
        keywords=[
            "generate", "write code", "create function",
            "boilerplate", "scaffold", "template", "matching style",
        ],
        tools=["search_code", "symbols_overview"],
    ),
    "UC-08": UseCase(
        id="UC-08",
        name="Check Logic",
        description="Verify correctness of complex logic, find branch gaps",
        keywords=[
            "logic", "correct", "verify", "branch", "edge case",
            "condition", "if else", "switch", "validation",
            "boundary", "corner case",
        ],
        tools=["trace_variable", "call_chain"],
    ),
    "UC-09": UseCase(
        id="UC-09",
        name="Compare Versions",
        description="Compare implementations across classes/versions",
        keywords=[
            "compare", "version", "difference", "migration",
            "old vs new", "before after", "refactor", "legacy",
        ],
        tools=["search_code", "call_chain"],
    ),
    "UC-10": UseCase(
        id="UC-10",
        name="Quick Check",
        description="30-second assessment of a method",
        keywords=[
            "quick check", "quick look", "glance", "brief",
            "what does this method", "summarize", "tldr",
        ],
        tools=["call_chain", "symbols_overview"],
    ),
}


def detect_use_cases(text: str) -> list[str]:
    """Detect which use cases are referenced in a text block.

    Returns a list of UC IDs sorted by match strength (most keywords matched first).
    """
    text_lower = text.lower()
    scores: list[tuple[str, int]] = []
    for uc_id, uc in USE_CASES.items():
        score = sum(1 for kw in uc.keywords if kw in text_lower)
        if score > 0:
            scores.append((uc_id, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [uc_id for uc_id, _ in scores]


def get_use_case(uc_id: str) -> UseCase | None:
    """Look up a use case by ID."""
    return USE_CASES.get(uc_id)
