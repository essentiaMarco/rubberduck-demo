"""PDF report generator using Jinja2 + WeasyPrint.

Renders investigation reports as HTML from templates, then converts to PDF.
Reports are stored in data/exports/reports/ for download.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader
from sqlalchemy import func
from sqlalchemy.orm import Session

from rubberduck.config import settings
from rubberduck.db.models import (
    Case,
    EmailMessage,
    Entity,
    EntityMention,
    EvidenceSource,
    File,
    FinancialTransaction,
    ForensicAlert,
    ForensicSecret,
    GeoLocation,
    Hypothesis,
    HypothesisFinding,
    PhoneRecord,
    Relationship,
)

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(settings.exports_dir) / "reports"


def _ensure_reports_dir():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ── HTML template ────────────────────────────────────────────

_BASE_CSS = """
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11pt; color: #1a1a1a; margin: 40px; }
h1 { font-size: 20pt; color: #1e293b; border-bottom: 2px solid #6366f1; padding-bottom: 8px; }
h2 { font-size: 14pt; color: #334155; margin-top: 24px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }
h3 { font-size: 12pt; color: #475569; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
th { background: #f1f5f9; color: #334155; font-weight: 600; text-align: left; padding: 6px 10px; border: 1px solid #e2e8f0; }
td { padding: 5px 10px; border: 1px solid #e2e8f0; vertical-align: top; }
tr:nth-child(even) { background: #f8fafc; }
.stat-box { display: inline-block; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 16px; margin: 4px; text-align: center; }
.stat-value { font-size: 18pt; font-weight: 700; color: #6366f1; }
.stat-label { font-size: 8pt; color: #64748b; text-transform: uppercase; }
.severity-critical { color: #dc2626; font-weight: 700; }
.severity-high { color: #ea580c; font-weight: 700; }
.severity-medium { color: #ca8a04; }
.anomaly-row { background: #fef3c7 !important; }
.header { text-align: center; margin-bottom: 24px; }
.header .subtitle { color: #64748b; font-size: 10pt; }
.footer { margin-top: 40px; border-top: 1px solid #e2e8f0; padding-top: 12px; font-size: 8pt; color: #94a3b8; text-align: center; }
.draft-watermark { color: #ef4444; font-size: 9pt; text-align: center; font-weight: 700; margin: 8px 0; }
@page { margin: 1.5cm; @bottom-center { content: "Gotham4Justice — Page " counter(page); font-size: 8pt; color: #94a3b8; } }
"""


def generate_investigation_summary(db: Session, case_id: str | None = None) -> Path:
    """Generate a full investigation summary report as PDF."""
    _ensure_reports_dir()

    # Gather data
    case = db.query(Case).get(case_id) if case_id else None
    total_files = db.query(File).count()
    total_size = db.query(func.sum(File.file_size_bytes)).scalar() or 0
    source_count = db.query(EvidenceSource).count()
    entity_count = db.query(Entity).count()
    relationship_count = db.query(Relationship).count()
    secret_count = db.query(ForensicSecret).count()
    alert_count = db.query(ForensicAlert).filter(ForensicAlert.dismissed == False).count()
    email_count = db.query(EmailMessage).count()
    phone_count = db.query(PhoneRecord).count()
    tx_count = db.query(FinancialTransaction).count()
    geo_count = db.query(GeoLocation).count()

    # Status breakdown
    status_counts = dict(
        db.query(File.parse_status, func.count()).group_by(File.parse_status).all()
    )

    # Top entities
    top_entities = (
        db.query(Entity.canonical_name, Entity.entity_type, func.count(EntityMention.id).label("mentions"))
        .join(EntityMention, Entity.id == EntityMention.entity_id)
        .group_by(Entity.id)
        .order_by(func.count(EntityMention.id).desc())
        .limit(20)
        .all()
    )

    # Critical secrets
    critical_secrets = (
        db.query(ForensicSecret)
        .filter(ForensicSecret.severity.in_(["critical", "high"]), ForensicSecret.dismissed == False)
        .order_by(ForensicSecret.severity.asc())
        .limit(20)
        .all()
    )

    # Active alerts
    active_alerts = (
        db.query(ForensicAlert)
        .filter(ForensicAlert.dismissed == False)
        .order_by(ForensicAlert.severity.asc(), ForensicAlert.created_at.desc())
        .limit(20)
        .all()
    )

    # Hypotheses
    hypotheses = db.query(Hypothesis).order_by(Hypothesis.updated_at.desc()).limit(10).all()

    now = datetime.now(timezone.utc)
    case_name = case.name if case else "All Cases"

    html = f"""<!DOCTYPE html><html><head><style>{_BASE_CSS}</style></head><body>
    <div class="header">
        <h1>Investigation Summary Report</h1>
        <div class="subtitle">{case_name} — Generated {now.strftime('%B %d, %Y at %H:%M UTC')}</div>
        <div class="draft-watermark">CONFIDENTIAL — LAW ENFORCEMENT SENSITIVE</div>
    </div>

    <h2>Evidence Overview</h2>
    <div>
        <div class="stat-box"><div class="stat-value">{total_files:,}</div><div class="stat-label">Total Files</div></div>
        <div class="stat-box"><div class="stat-value">{total_size / (1024**3):.1f} GB</div><div class="stat-label">Total Size</div></div>
        <div class="stat-box"><div class="stat-value">{source_count}</div><div class="stat-label">Sources</div></div>
        <div class="stat-box"><div class="stat-value">{entity_count:,}</div><div class="stat-label">Entities</div></div>
        <div class="stat-box"><div class="stat-value">{relationship_count:,}</div><div class="stat-label">Relationships</div></div>
    </div>
    <table>
        <tr><th>Parse Status</th><th>Count</th></tr>
        {"".join(f'<tr><td>{s}</td><td>{c}</td></tr>' for s, c in sorted(status_counts.items()))}
    </table>

    <h2>Communication Summary</h2>
    <div>
        <div class="stat-box"><div class="stat-value">{email_count:,}</div><div class="stat-label">Emails</div></div>
        <div class="stat-box"><div class="stat-value">{phone_count:,}</div><div class="stat-label">Phone Records</div></div>
        <div class="stat-box"><div class="stat-value">{tx_count:,}</div><div class="stat-label">Transactions</div></div>
        <div class="stat-box"><div class="stat-value">{geo_count}</div><div class="stat-label">GPS Points</div></div>
    </div>

    <h2>Top Entities (by mention count)</h2>
    <table>
        <tr><th>#</th><th>Name</th><th>Type</th><th>Mentions</th></tr>
        {"".join(f'<tr><td>{i+1}</td><td>{e.canonical_name}</td><td>{e.entity_type}</td><td>{e.mentions:,}</td></tr>' for i, e in enumerate(top_entities))}
    </table>

    <h2>Forensic Alerts ({alert_count} active)</h2>
    <table>
        <tr><th>Severity</th><th>Type</th><th>Title</th></tr>
        {"".join(f'<tr><td class="severity-{a.severity}">{a.severity.upper()}</td><td>{a.alert_type}</td><td>{a.title}</td></tr>' for a in active_alerts)}
    </table>

    <h2>Discovered Secrets ({secret_count} total)</h2>
    <table>
        <tr><th>Severity</th><th>Type</th><th>Masked Value</th></tr>
        {"".join(f'<tr><td class="severity-{s.severity}">{s.severity.upper()}</td><td>{s.secret_type}</td><td><code>{s.masked_value}</code></td></tr>' for s in critical_secrets)}
    </table>

    <h2>Hypotheses</h2>
    <table>
        <tr><th>Title</th><th>Status</th><th>Confidence</th></tr>
        {"".join(f'<tr><td>{h.title}</td><td>{h.status}</td><td>{h.confidence:.0%}</td></tr>' for h in hypotheses if h.confidence is not None)}
        {"".join(f'<tr><td>{h.title}</td><td>{h.status}</td><td>--</td></tr>' for h in hypotheses if h.confidence is None)}
    </table>

    <div class="footer">
        Generated by Gotham4Justice Digital Forensic Platform v0.1.0<br>
        This report is generated automatically and should be reviewed by a qualified investigator.
    </div>
    </body></html>"""

    filename = f"investigation_summary_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_path = REPORTS_DIR / filename

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(pdf_path))
        logger.info("Report generated: %s", pdf_path)
    except ImportError:
        # Fallback: save as HTML if WeasyPrint not available
        pdf_path = pdf_path.with_suffix(".html")
        pdf_path.write_text(html, encoding="utf-8")
        logger.warning("WeasyPrint not available — saved as HTML: %s", pdf_path)

    return pdf_path


def generate_secrets_report(db: Session) -> Path:
    """Generate a secrets/credentials report as PDF."""
    _ensure_reports_dir()

    secrets = (
        db.query(ForensicSecret)
        .filter(ForensicSecret.dismissed == False)
        .order_by(ForensicSecret.severity.asc(), ForensicSecret.created_at.desc())
        .all()
    )

    # Enrich with file names
    file_ids = {s.file_id for s in secrets}
    file_names = {}
    if file_ids:
        for f in db.query(File.id, File.file_name).filter(File.id.in_(file_ids)).all():
            file_names[f.id] = f.file_name

    now = datetime.now(timezone.utc)
    rows = ""
    for i, s in enumerate(secrets, 1):
        rows += f"""<tr class="{'anomaly-row' if s.severity == 'critical' else ''}">
            <td>{i}</td>
            <td class="severity-{s.severity}">{s.severity.upper()}</td>
            <td>{s.secret_type}</td>
            <td><code>{s.masked_value}</code></td>
            <td>{file_names.get(s.file_id, s.file_id[:8])}</td>
            <td>{s.detection_method}</td>
            <td>{s.confidence:.0%}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head><style>{_BASE_CSS}</style></head><body>
    <div class="header">
        <h1>Discovered Secrets & Credentials Report</h1>
        <div class="subtitle">Generated {now.strftime('%B %d, %Y at %H:%M UTC')}</div>
        <div class="draft-watermark">CONFIDENTIAL — LAW ENFORCEMENT SENSITIVE</div>
    </div>

    <h2>Summary</h2>
    <p>{len(secrets)} secrets discovered across evidence files.</p>

    <h2>Findings</h2>
    <table>
        <tr><th>#</th><th>Severity</th><th>Type</th><th>Masked Value</th><th>Source File</th><th>Method</th><th>Confidence</th></tr>
        {rows}
    </table>

    <div class="footer">
        Generated by Gotham4Justice Digital Forensic Platform v0.1.0<br>
        Values are masked for security. Full values available in the platform.
    </div>
    </body></html>"""

    filename = f"secrets_report_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_path = REPORTS_DIR / filename

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(pdf_path))
    except ImportError:
        pdf_path = pdf_path.with_suffix(".html")
        pdf_path.write_text(html, encoding="utf-8")

    return pdf_path


# Report type registry
REPORT_TYPES = {
    "investigation_summary": {
        "name": "Investigation Summary",
        "description": "Full case overview: evidence, entities, communications, secrets, hypotheses",
        "generator": generate_investigation_summary,
    },
    "secrets": {
        "name": "Secrets & Credentials",
        "description": "All discovered passwords, keys, tokens, and wallet addresses",
        "generator": generate_secrets_report,
    },
}
