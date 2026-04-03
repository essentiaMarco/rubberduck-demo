"""Google-specific supplemental order builder.

Generates narrow and broad draft orders for Google digital-asset
disclosure under RUFADAA (Cal. Prob. Code sections 870-884).

All output is marked DRAFT and must be reviewed by a qualified attorney
or the pro se petitioner before filing.
"""

from __future__ import annotations

from typing import Any

from rubberduck.legal.watermark import add_draft_watermark

# ── Google product category catalogue ─────────────────────

GOOGLE_PRODUCT_CATEGORIES: list[dict[str, str]] = [
    {
        "product": "Gmail",
        "category": "gmail",
        "description": "Email messages, drafts, labels, and attachments",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (content of electronic communications)",
        "data_location": "Provider records / Google Takeout",
    },
    {
        "product": "Contacts",
        "category": "contacts",
        "description": "Saved contacts, contact groups, and metadata",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (catalogue of communications)",
        "data_location": "Google Takeout",
    },
    {
        "product": "Drive",
        "category": "drive",
        "description": "Files, folders, sharing permissions, and revision history",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "Google Takeout",
    },
    {
        "product": "Photos",
        "category": "photos",
        "description": "Photos, videos, albums, and associated metadata (EXIF, timestamps)",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "Google Takeout",
    },
    {
        "product": "Calendar",
        "category": "calendar",
        "description": "Calendar events, invitations, RSVPs, and recurrences",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "Google Takeout",
    },
    {
        "product": "YouTube Watch History",
        "category": "youtube_watch",
        "description": "Videos viewed, watch timestamps, and duration",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (catalogue of communications); My Activity",
        "data_location": "My Activity / Google Takeout",
    },
    {
        "product": "YouTube Search History",
        "category": "youtube_search",
        "description": "Search queries entered on YouTube",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (catalogue of communications); My Activity",
        "data_location": "My Activity / Google Takeout",
    },
    {
        "product": "Google My Activity",
        "category": "my_activity",
        "description": "Aggregated activity log across all Google services",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "My Activity",
    },
    {
        "product": "Web & App Activity",
        "category": "web_app_activity",
        "description": "Search queries, visited URLs, and app interaction logs",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (catalogue of communications)",
        "data_location": "My Activity / Provider records",
    },
    {
        "product": "Maps Timeline",
        "category": "maps_timeline",
        "description": "Location history, place visits, and travel routes",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "My Activity / Google Takeout",
    },
    {
        "product": "Account Sign-in Metadata",
        "category": "sign_in_metadata",
        "description": "Login timestamps, IP addresses, device identifiers, and session data",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (catalogue of communications)",
        "data_location": "Provider records",
    },
    {
        "product": "Chrome Sync",
        "category": "chrome_sync",
        "description": "Bookmarks, browsing history, saved passwords, and autofill data",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "Google Takeout",
    },
    {
        "product": "Google Voice",
        "category": "google_voice",
        "description": "Call logs, voicemails, and text messages",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (content of electronic communications)",
        "data_location": "Provider records / Google Takeout",
    },
    {
        "product": "Android/Play Activity",
        "category": "android_play",
        "description": "App installs, usage statistics, and Play Store transactions",
        "legal_basis_notes": "Cal. Prob. Code \u00a7 873 (other digital assets)",
        "data_location": "My Activity / Google Takeout",
    },
]

_CATEGORY_LOOKUP: dict[str, dict[str, str]] = {
    c["category"]: c for c in GOOGLE_PRODUCT_CATEGORIES
}


# ── Draft section builders ────────────────────────────────


def _build_category_table(
    categories: list[dict[str, str]],
    accounts: list[str],
    date_range_start: str | None,
    date_range_end: str | None,
) -> str:
    """Generate a Markdown table of requested product categories."""
    date_range = _format_date_range(date_range_start, date_range_end)
    account_scope = ", ".join(accounts) if accounts else "All associated accounts"

    lines = [
        "| # | Product | Description | Date Range | Account Scope | Legal Basis | Necessity |",
        "|---|---------|-------------|------------|---------------|-------------|-----------|",
    ]
    for i, cat in enumerate(categories, 1):
        necessity = (
            f"Records are necessary to identify, catalogue, and preserve "
            f"digital assets of the decedent under RUFADAA."
        )
        lines.append(
            f"| {i} | {cat['product']} | {cat['description']} | "
            f"{date_range} | {account_scope} | "
            f"{cat.get('legal_basis_notes', 'Cal. Prob. Code \u00a7 873')} | "
            f"{necessity} |"
        )
    return "\n".join(lines)


def _format_date_range(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} through {end}"
    if start:
        return f"{start} through present"
    if end:
        return f"Account inception through {end}"
    return "Account inception through present"


def _build_statutory_basis_table() -> str:
    """Markdown table of relevant RUFADAA provisions."""
    lines = [
        "| Citation | Description | Applicability |",
        "|----------|-------------|---------------|",
        "| Cal. Prob. Code \u00a7 870 | Definitions | Key terms for fiduciary digital-asset access |",
        "| Cal. Prob. Code \u00a7 871 | Applicability | RUFADAA scope: fiduciaries, personal reps, agents |",
        "| Cal. Prob. Code \u00a7 873 | Disclosure to personal representative | Authorizes disclosure of catalogue and content |",
        "| Cal. Prob. Code \u00a7 874 | Disclosure to conservator | Applies when conservatorship is at issue |",
        "| Cal. Prob. Code \u00a7 880 | Court order for disclosure | Court may order custodian to disclose |",
        "| Cal. Prob. Code \u00a7 884 | Custodian compliance and immunity | Safe harbor for good-faith compliance |",
    ]
    return "\n".join(lines)


def _build_findings_table(accounts: list[str], date_range_start: str | None, date_range_end: str | None) -> str:
    """Generate the findings / factual basis section."""
    date_range = _format_date_range(date_range_start, date_range_end)
    lines = [
        "| Finding | Detail |",
        "|---------|--------|",
        f"| Account holder | Decedent maintained Google account(s): {', '.join(accounts) or 'TBD'} |",
        f"| Date range | {date_range} |",
        "| Fiduciary authority | Petitioner has been appointed or seeks appointment as personal representative |",
        "| RUFADAA authorization | Cal. Prob. Code \u00a7\u00a7 870\u2013884 authorize disclosure upon court order |",
        "| Necessity | Digital records are necessary for estate administration and asset identification |",
    ]
    return "\n".join(lines)


def _build_service_instructions() -> str:
    """Standard service instructions for Google."""
    return (
        "## Service Instructions\n\n"
        "1. Serve a certified copy of the signed order on Google LLC via its registered agent or "
        "through Google's Legal Investigations Support portal.\n"
        "2. Include: (a) certified copy of Letters Testamentary or Letters of Administration; "
        "(b) certified copy of the court order; (c) death certificate; "
        "(d) government-issued ID of the petitioner.\n"
        "3. Google's mailing address for legal process:\n"
        "   Google LLC, c/o Legal Investigations Support, 1600 Amphitheatre Parkway, "
        "Mountain View, CA 94043\n"
        "4. Electronic submission may also be available via "
        "https://support.google.com/legal/contact/lr_legalother\n"
    )


def _build_unresolved_issues(
    categories: list[dict[str, str]],
    accounts: list[str],
) -> list[str]:
    """Identify unresolved issues that require attorney review."""
    issues: list[str] = []
    if not accounts:
        issues.append("No Google account identifiers specified; petitioner must provide account email(s).")
    if len(accounts) > 1:
        issues.append(
            "Multiple accounts listed; confirm each account belonged to the decedent "
            "and is within the scope of fiduciary authority."
        )
    issues.append(
        "Verify that the petitioner's fiduciary authority (Letters Testamentary, "
        "Letters of Administration, or court appointment) is current and valid."
    )
    issues.append(
        "Confirm the date range is appropriate for the estate administration needs."
    )
    issues.append(
        "Review each requested category for necessity and proportionality; "
        "the court may narrow overly broad requests."
    )
    return issues


# ── Main builder ──────────────────────────────────────────


def build_google_order(
    case_id: str,
    accounts: list[str],
    categories: list[dict[str, Any]],
    date_range_start: str | None = None,
    date_range_end: str | None = None,
) -> dict[str, Any]:
    """Build narrow and broad draft supplemental orders for Google.

    Parameters
    ----------
    case_id:
        Case identifier for reference.
    accounts:
        List of Google account email addresses.
    categories:
        List of category dicts from the request. Each should have at
        least a ``category`` key matching a slug in
        :data:`GOOGLE_PRODUCT_CATEGORIES`. Categories with
        ``selected=True`` go into the narrow draft; all categories go
        into the broad draft.
    date_range_start, date_range_end:
        ISO date strings bounding the request period.

    Returns
    -------
    dict
        Keys: narrow_draft, broad_draft, necessity_memo,
        attachment_checklist, evidentiary_gaps, assumptions.
    """
    # Resolve selected vs all categories
    selected_cats: list[dict[str, str]] = []
    all_cats: list[dict[str, str]] = []

    for cat_input in categories:
        slug = cat_input.get("category", "")
        cat_meta = _CATEGORY_LOOKUP.get(slug)
        if cat_meta is None:
            continue
        all_cats.append(cat_meta)
        if cat_input.get("selected", False):
            selected_cats.append(cat_meta)

    # If nothing explicitly selected, use all as narrow too
    if not selected_cats:
        selected_cats = list(all_cats)

    # If no categories provided at all, use the full catalogue
    if not all_cats:
        all_cats = list(GOOGLE_PRODUCT_CATEGORIES)
        selected_cats = list(all_cats)

    date_range = _format_date_range(date_range_start, date_range_end)
    account_str = ", ".join(accounts) if accounts else "[ACCOUNT EMAIL(S) TO BE SPECIFIED]"

    # ── Narrow draft ──────────────────────────────────────
    narrow_sections = [
        f"# PROPOSED SUPPLEMENTAL ORDER RE: DISCLOSURE OF GOOGLE DIGITAL ASSETS",
        f"## Case Reference: {case_id}",
        "",
        f"**Account(s):** {account_str}",
        f"**Date Range:** {date_range}",
        "",
        "## Statutory Basis",
        "",
        _build_statutory_basis_table(),
        "",
        "## Findings",
        "",
        _build_findings_table(accounts, date_range_start, date_range_end),
        "",
        "## Requested Categories (Narrow Scope)",
        "",
        _build_category_table(selected_cats, accounts, date_range_start, date_range_end),
        "",
        "## Necessity and Proportionality",
        "",
        "The requested categories are narrowly tailored to the categories of digital assets "
        "reasonably believed to be held by Google LLC on behalf of the decedent. Disclosure "
        "is necessary for the personal representative to fulfil fiduciary duties under "
        "Cal. Prob. Code \u00a7\u00a7 870\u2013884 (RUFADAA), including identification, preservation, "
        "and distribution of the decedent's digital estate.",
        "",
        _build_service_instructions(),
        "",
        "## Unresolved Issues",
        "",
    ]
    for issue in _build_unresolved_issues(selected_cats, accounts):
        narrow_sections.append(f"- {issue}")

    narrow_draft = add_draft_watermark("\n".join(narrow_sections))

    # ── Broad draft ───────────────────────────────────────
    broad_sections = [
        f"# PROPOSED SUPPLEMENTAL ORDER RE: DISCLOSURE OF GOOGLE DIGITAL ASSETS (BROAD)",
        f"## Case Reference: {case_id}",
        "",
        f"**Account(s):** {account_str}",
        f"**Date Range:** {date_range}",
        "",
        "## Statutory Basis",
        "",
        _build_statutory_basis_table(),
        "",
        "## Findings",
        "",
        _build_findings_table(accounts, date_range_start, date_range_end),
        "",
        "## Requested Categories (Broad Scope \u2014 All Potentially Relevant)",
        "",
        _build_category_table(all_cats, accounts, date_range_start, date_range_end),
        "",
        "## Necessity and Proportionality",
        "",
        "The broad scope is requested to ensure comprehensive identification of all "
        "digital assets held by Google LLC on behalf of the decedent. The personal "
        "representative requires access to the complete catalogue to discharge fiduciary "
        "duties. The court may narrow the scope of disclosure as appropriate.",
        "",
        _build_service_instructions(),
        "",
        "## Unresolved Issues",
        "",
    ]
    for issue in _build_unresolved_issues(all_cats, accounts):
        broad_sections.append(f"- {issue}")

    broad_draft = add_draft_watermark("\n".join(broad_sections))

    # ── Necessity memo ────────────────────────────────────
    memo_lines = [
        "# MEMORANDUM OF NECESSITY",
        f"## Case Reference: {case_id}",
        "",
        "This memorandum supports the accompanying Proposed Supplemental Order "
        "requesting disclosure of digital assets from Google LLC.",
        "",
        "### Legal Framework",
        "",
        "The Revised Uniform Fiduciary Access to Digital Assets Act (RUFADAA), "
        "codified at Cal. Prob. Code \u00a7\u00a7 870\u2013884, authorizes a court to order "
        "a custodian of digital assets to disclose information to a personal "
        "representative when disclosure is reasonably necessary for estate administration.",
        "",
        "### Factual Basis",
        "",
        f"The decedent maintained Google account(s) ({account_str}) containing "
        "digital assets that may include financial records, communications, "
        "personal documents, and other items relevant to the administration of the estate.",
        "",
        "### Necessity",
        "",
        "Access to the requested categories is necessary to:",
        "1. Identify and catalogue the decedent's digital assets",
        "2. Preserve assets at risk of deletion or expiration",
        "3. Locate financial accounts, insurance policies, and other entitlements",
        "4. Identify potential claims or liabilities of the estate",
        "5. Fulfil notice obligations to creditors and beneficiaries",
        "",
        "### Proportionality",
        "",
        "The request is proportional to the estate's needs. Categories not relevant "
        "to estate administration have been excluded from the narrow variant. The "
        "broad variant is provided as an alternative should the court find that a "
        "wider scope is appropriate given the circumstances.",
    ]
    necessity_memo = add_draft_watermark("\n".join(memo_lines))

    # ── Attachment checklist ──────────────────────────────
    attachment_checklist = [
        "Certified copy of Letters Testamentary or Letters of Administration",
        "Certified copy of the signed court order",
        "Certified copy of the death certificate",
        "Government-issued photo ID of the petitioner / personal representative",
        "Cover letter identifying the account(s) and referencing the court order",
        "Proposed Supplemental Order (narrow or broad variant)",
        "Memorandum of Necessity (if required by the court)",
    ]

    # ── Evidentiary gaps ──────────────────────────────────
    evidentiary_gaps: list[str] = []
    if not accounts:
        evidentiary_gaps.append("Google account email address(es) not yet identified")
    if not date_range_start:
        evidentiary_gaps.append("Start date for requested records not specified")
    if not date_range_end:
        evidentiary_gaps.append("End date for requested records not specified (defaulting to present)")
    evidentiary_gaps.append(
        "Fiduciary appointment documentation should be verified as current"
    )

    # ── Assumptions ───────────────────────────────────────
    assumptions = [
        "The petitioner has been or will be appointed as the personal representative of the estate.",
        "The identified Google account(s) belonged to the decedent.",
        "The case is proceeding in California under RUFADAA (Cal. Prob. Code \u00a7\u00a7 870\u2013884).",
        "Google LLC is the custodian of the digital assets at issue.",
        "The court has jurisdiction to issue orders directed to Google LLC.",
        "All statutory prerequisites for a disclosure order have been or will be satisfied.",
    ]

    return {
        "narrow_draft": narrow_draft,
        "broad_draft": broad_draft,
        "necessity_memo": necessity_memo,
        "attachment_checklist": attachment_checklist,
        "evidentiary_gaps": evidentiary_gaps,
        "assumptions": assumptions,
    }
