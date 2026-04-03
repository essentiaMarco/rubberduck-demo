"""Jinja2 template rendering for legal documents.

Templates are loaded from the ``templates/legal/`` directory relative to the
project data root.  Every rendered document automatically receives a DRAFT
watermark header and footer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from rubberduck.config import settings
from rubberduck.legal.watermark import add_draft_watermark

# ── Template directory resolution ─────────────────────────

_TEMPLATE_DIR = Path(settings.data_dir) / "templates" / "legal"


def _get_env() -> Environment:
    """Build a Jinja2 environment from the legal templates directory.

    The environment supports template inheritance via ``{% extends %}``
    and auto-escapes HTML by default.
    """
    loader = FileSystemLoader(str(_TEMPLATE_DIR))
    return Environment(
        loader=loader,
        autoescape=select_autoescape(["html", "htm", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ── Public API ────────────────────────────────────────────


def render_template(template_name: str, parameters: dict[str, Any] | None = None) -> str:
    """Render a legal template and wrap it with the DRAFT watermark.

    Parameters
    ----------
    template_name:
        Filename of the template inside ``templates/legal/`` (e.g.
        ``"proposed_order.html"``).
    parameters:
        Key/value pairs passed into the template context.

    Returns
    -------
    str
        Rendered HTML/text with DRAFT header and footer.

    Raises
    ------
    jinja2.TemplateNotFound
        If *template_name* does not exist in the template directory.
    """
    env = _get_env()
    template = env.get_template(template_name)
    rendered = template.render(**(parameters or {}))
    return add_draft_watermark(rendered)


def list_templates() -> list[dict[str, str]]:
    """Return metadata for all available legal templates.

    Each entry contains ``name`` (filename) and ``path`` (absolute path).
    Only ``.html``, ``.htm``, ``.txt``, and ``.md`` files are included.
    """
    allowed_extensions = {".html", ".htm", ".txt", ".md"}
    templates: list[dict[str, str]] = []

    if not _TEMPLATE_DIR.exists():
        return templates

    for path in sorted(_TEMPLATE_DIR.rglob("*")):
        if path.is_file() and path.suffix.lower() in allowed_extensions:
            rel = path.relative_to(_TEMPLATE_DIR)
            templates.append({
                "name": str(rel),
                "path": str(path),
            })

    return templates
