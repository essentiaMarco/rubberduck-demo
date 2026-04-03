"""Evidence gap analysis for digital-estate cases.

Compares existing legal documents / provider responses against the full
catalogue of known provider product categories and reports which
categories are covered, which are missing, and what the petitioner
should consider requesting next.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from rubberduck.db.models import LegalDocument

# ── Provider product catalogues ───────────────────────────
# Each entry: (product name, category slug, human description)

GOOGLE_PRODUCTS: list[dict[str, str]] = [
    {"product": "Gmail", "category": "gmail", "description": "Email messages, drafts, and attachments"},
    {"product": "Contacts", "category": "contacts", "description": "Saved contacts and contact metadata"},
    {"product": "Drive", "category": "drive", "description": "Files, folders, and sharing metadata in Google Drive"},
    {"product": "Photos", "category": "photos", "description": "Photos, videos, and album metadata in Google Photos"},
    {"product": "Calendar", "category": "calendar", "description": "Calendar events, invitations, and RSVPs"},
    {"product": "YouTube Watch History", "category": "youtube_watch", "description": "Videos watched and watch timestamps"},
    {"product": "YouTube Search History", "category": "youtube_search", "description": "Search queries within YouTube"},
    {"product": "Google My Activity", "category": "my_activity", "description": "Aggregated activity across Google services"},
    {"product": "Web & App Activity", "category": "web_app_activity", "description": "Search queries, visited URLs, and app interactions"},
    {"product": "Maps Timeline", "category": "maps_timeline", "description": "Location history and place visits from Google Maps"},
    {"product": "Account Sign-in Metadata", "category": "sign_in_metadata", "description": "Login timestamps, IP addresses, and device info"},
    {"product": "Chrome Sync", "category": "chrome_sync", "description": "Bookmarks, browsing history, and saved passwords synced via Chrome"},
    {"product": "Google Voice", "category": "google_voice", "description": "Call logs, voicemails, and text messages"},
    {"product": "Android/Play Activity", "category": "android_play", "description": "App installs, usage, and Play Store transactions"},
]

APPLE_PRODUCTS: list[dict[str, str]] = [
    {"product": "iCloud Mail", "category": "icloud_mail", "description": "Email messages and attachments in iCloud Mail"},
    {"product": "Photos", "category": "icloud_photos", "description": "Photos and videos stored in iCloud Photos"},
    {"product": "Drive", "category": "icloud_drive", "description": "Files and folders in iCloud Drive"},
    {"product": "Contacts", "category": "icloud_contacts", "description": "Contacts synced via iCloud"},
    {"product": "Calendar", "category": "icloud_calendar", "description": "Calendar events synced via iCloud"},
    {"product": "Notes", "category": "icloud_notes", "description": "Notes stored in iCloud"},
    {"product": "Messages", "category": "icloud_messages", "description": "iMessage and SMS messages stored in iCloud"},
    {"product": "Health", "category": "icloud_health", "description": "Health and fitness data synced via iCloud"},
    {"product": "Find My", "category": "find_my", "description": "Device and people location data from Find My"},
    {"product": "Safari History", "category": "safari_history", "description": "Browsing history synced via iCloud"},
]

MICROSOFT_PRODUCTS: list[dict[str, str]] = [
    {"product": "Outlook", "category": "outlook", "description": "Email, calendar, and contacts in Outlook/Exchange"},
    {"product": "OneDrive", "category": "onedrive", "description": "Files and folders in OneDrive"},
    {"product": "Skype", "category": "skype", "description": "Chat messages, call logs, and shared files in Skype"},
    {"product": "Teams", "category": "teams", "description": "Chat messages, meetings, and shared files in Teams"},
    {"product": "Edge History", "category": "edge_history", "description": "Browsing history synced via Microsoft Edge"},
    {"product": "Microsoft 365 Activity", "category": "m365_activity", "description": "Document edits, sharing, and collaboration activity"},
]

_ALL_PRODUCTS: dict[str, list[dict[str, str]]] = {
    "google": GOOGLE_PRODUCTS,
    "apple": APPLE_PRODUCTS,
    "microsoft": MICROSOFT_PRODUCTS,
}


# ── Gap analysis logic ────────────────────────────────────


def analyze_gaps(db: Session, case_id: str) -> dict[str, Any]:
    """Compare existing legal documents against the full product catalogue.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    case_id:
        Primary key of the case to analyze.

    Returns
    -------
    dict
        Keys: case_id, covered_categories, missing_categories,
        recommendations, statutory_basis, unresolved_issues.
    """
    # Fetch all legal documents for this case
    docs: list[LegalDocument] = (
        db.query(LegalDocument)
        .filter(LegalDocument.case_id == case_id)
        .all()
    )

    # Build a set of (provider, category) tuples that are already covered
    covered_keys: set[tuple[str, str]] = set()
    for doc in docs:
        provider = (doc.provider or "").lower()
        if not provider:
            continue

        # Try to extract covered categories from document parameters
        params: dict[str, Any] = {}
        if doc.parameters:
            try:
                params = json.loads(doc.parameters) if isinstance(doc.parameters, str) else doc.parameters
            except (json.JSONDecodeError, TypeError):
                pass

        categories_in_doc: list[str] = params.get("categories", [])
        if categories_in_doc:
            for cat in categories_in_doc:
                covered_keys.add((provider, cat))
        else:
            # If no explicit categories, mark the provider as partially covered
            # based on the doc_type presence alone
            if provider in _ALL_PRODUCTS:
                for p in _ALL_PRODUCTS[provider]:
                    # Mark as covered only if the document title or type hints at it
                    if p["category"].lower() in (doc.title or "").lower():
                        covered_keys.add((provider, p["category"]))

    # Build covered / missing lists
    covered_categories: list[dict[str, Any]] = []
    missing_categories: list[dict[str, Any]] = []

    for provider, products in _ALL_PRODUCTS.items():
        for prod in products:
            entry = {
                "provider": provider,
                "category": prod["category"],
                "product": prod["product"],
                "description": prod["description"],
                "status": "covered" if (provider, prod["category"]) in covered_keys else "missing",
            }

            # Find the covering document if any
            if (provider, prod["category"]) in covered_keys:
                covering_doc = next(
                    (
                        d
                        for d in docs
                        if (d.provider or "").lower() == provider
                    ),
                    None,
                )
                if covering_doc:
                    entry["existing_order"] = covering_doc.title
                covered_categories.append(entry)
            else:
                missing_categories.append(entry)

    # Generate recommendations
    recommendations: list[str] = []
    missing_by_provider: dict[str, int] = {}
    for m in missing_categories:
        prov = m["provider"]
        missing_by_provider[prov] = missing_by_provider.get(prov, 0) + 1

    for prov, count in sorted(missing_by_provider.items(), key=lambda x: -x[1]):
        recommendations.append(
            f"Consider requesting {count} additional {prov.title()} "
            f"product categor{'y' if count == 1 else 'ies'} via supplemental order."
        )

    if not docs:
        recommendations.insert(
            0,
            "No legal documents found for this case. Begin by drafting an "
            "initial proposed order under RUFADAA (Cal. Prob. Code "
            "\u00a7\u00a7 870\u2013884).",
        )

    # Standard statutory basis entries
    statutory_basis = [
        {
            "citation": "Cal. Prob. Code \u00a7 870",
            "summary": "Definitions for RUFADAA",
            "applicability": "Establishes key terms for fiduciary access to digital assets",
        },
        {
            "citation": "Cal. Prob. Code \u00a7 871",
            "summary": "Applicability of RUFADAA",
            "applicability": "Applies to fiduciaries, personal representatives, and agents",
        },
        {
            "citation": "Cal. Prob. Code \u00a7 873",
            "summary": "Disclosure of digital assets to personal representative",
            "applicability": "Authorizes disclosure of catalogue and content of electronic communications",
        },
        {
            "citation": "Cal. Prob. Code \u00a7 884",
            "summary": "Compliance and immunity for custodians",
            "applicability": "Provides safe harbor for custodians who comply in good faith",
        },
    ]

    unresolved_issues: list[str] = []
    if missing_categories:
        unresolved_issues.append(
            f"{len(missing_categories)} product categor{'y remains' if len(missing_categories) == 1 else 'ies remain'} "
            f"without legal coverage."
        )

    return {
        "case_id": case_id,
        "covered_categories": covered_categories,
        "missing_categories": missing_categories,
        "recommendations": recommendations,
        "statutory_basis": statutory_basis,
        "unresolved_issues": unresolved_issues,
    }
