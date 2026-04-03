"""spaCy-based named entity recognition pipeline.

Loads a spaCy model at module level and provides chunked extraction
of named entities from arbitrary-length text.
"""

import logging
import re
from typing import Any

import spacy
from spacy.language import Language

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from rubberduck.config import settings

logger = logging.getLogger(__name__)

# Maximum characters to process in a single spaCy call.
# spaCy's default max_length is 1_000_000 but processing very long texts
# in one pass can spike memory usage.
_CHUNK_SIZE = 100 * 1024  # 100 KB

# Map spaCy entity labels to Rubberduck entity types.
_LABEL_MAP: dict[str, str] = {
    "PERSON": "person",
    "ORG": "org",
    "GPE": "location",
    "LOC": "location",
    "FAC": "location",
    "NORP": "org",
    "PRODUCT": "device",
    "WORK_OF_ART": "other",
    "EVENT": "event",
    "DATE": "date",
    "TIME": "time",
    "MONEY": "money",
    "CARDINAL": "number",
    "ORDINAL": "number",
    "QUANTITY": "number",
    "PERCENT": "number",
    "LAW": "legal",
    "LANGUAGE": "other",
}

# ── Noise filtering ──────────────────────────────────────────
# Font names, CSS values, HTML artifacts commonly misclassified as PERSON/ORG
_BLOCKLIST: set[str] = {
    # Fonts (including common variations with quotes/suffixes)
    "arial", "helvetica", "calibri", "cambria", "verdana", "tahoma",
    "georgia", "garamond", "trebuchet", "palatino", "consolas", "courier",
    "times new roman", "times", "comic sans", "lucida", "segoe",
    "roboto", "open sans", "lato", "montserrat", "oswald", "raleway",
    "nunito", "ubuntu", "san francisco", "sf pro", "neue",
    "arial narrow", "arial black", "book antiqua", "century gothic",
    "franklin gothic", "lucida console", "lucida grande", "lucida sans",
    "ms sans serif", "ms serif", "palatino linotype", "segoe ui",
    "trebuchet ms", "sans-serif", "serif", "monospace",
    "helvetica neue", "blinkmacfont", "blinkmacfontsystem",
    "blinkmacfontsystemfont", "blinkmactypeface", "blinkmac",
    "system-ui", "apple color emoji", "segoe ui emoji", "noto color emoji",
    "segoe ui symbol", "droid sans", "fira sans", "source sans pro",
    "noto sans", "inter", "poppins", "barlow", "karla", "merriweather",
    "playfair display", "pt sans", "pt serif", "work sans",
    # CSS / HTML artifacts
    "none", "auto", "inherit", "initial", "unset", "normal", "bold",
    "italic", "underline", "solid", "hidden", "visible", "block",
    "inline", "flex", "grid", "absolute", "relative", "fixed",
    "transparent", "important", "border-box", "content-box",
    "div", "span", "table", "tbody", "thead", "img", "input", "button",
    "href", "src", "alt", "class", "style", "width", "height",
    "margin", "padding", "color", "background", "font-size", "font-family",
    "text-align", "line-height", "font-weight", "display", "position",
    "mso-style-type", "mso-style-name", "msonormal",
    "border-collapse", "cellspacing", "cellpadding", "colspan", "rowspan",
    "valign", "bgcolor", "nowrap", "email_table", "email_content",
    # Common false positives
    "http", "https", "www", "com", "org", "net", "gmail", "yahoo",
    "outlook", "null", "undefined", "true", "false", "n/a",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # Misc noise
    "subject", "date", "content-type", "mime-version", "unsubscribe",
    "view in browser", "click here", "read more", "learn more",
    "privacy policy", "terms of service",
}

# Patterns that indicate noise rather than real entities
_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^[\d\s.,;:!?@#$%^&*()\-+=\[\]{}<>/\\|]+$"),  # Purely punctuation/digits
    re.compile(r"^[\d.]+\s*(px|em|rem|pt|cm|mm|in|%)$", re.I),  # CSS units
    re.compile(r"^#[0-9a-fA-F]{3,8}$"),  # Hex colors
    re.compile(r"^[0-9a-fA-F]{6,}$"),  # Hex color codes without # (e.g. d3d9e4, 050C26)
    re.compile(r"^rgb\(", re.I),  # RGB values
    re.compile(r"^\d+(\.\d+)?$"),  # Bare numbers
    re.compile(r"^[A-Z]{1,2}$"),  # Single or double uppercase letters
    re.compile(r"^(mso|webkit|moz)-", re.I),  # Microsoft Office / browser prefixes
    re.compile(r"^\S+\.(woff2?|ttf|otf|eot|svg|png|jpg|gif|css|js)$", re.I),  # File refs
    re.compile(r"^[\w-]+:\s*[\w#-]+;?$"),  # CSS property: value patterns
    re.compile(r"<[^>]+>"),  # Contains HTML tags
    re.compile(r"^\d+px", re.I),  # Starts with pixel value (e.g. "14px;"></td)
    re.compile(r"^style=", re.I),  # Style attributes
    re.compile(r"^alt=$", re.I),  # Alt attribute remnants
    re.compile(r"^(font-|text-|border-|background-|margin-|padding-)", re.I),  # CSS properties
    re.compile(r"[\w-]+='[^']*'"),  # HTML attribute='value' patterns
    re.compile(r'[\w-]+="[^"]*"'),  # HTML attribute="value" patterns
    re.compile(r"^https?://", re.I),  # URLs (handled by regex extractor)
    re.compile(r"@[\w.-]+\.\w{2,}$"),  # Looks like email (handled by regex extractor)
]


def _strip_html(text: str) -> str:
    """Strip any residual HTML from text as defense-in-depth.

    Some email parsers may pass through raw HTML (especially single-part
    HTML emails).  Running NER on HTML produces thousands of false positives
    from CSS class names, font-family values, and style attributes.
    """
    # Quick check: if text doesn't look like HTML, skip the expensive parse
    if "<" not in text or ">" not in text:
        return text

    # Only strip if there's a meaningful amount of HTML-like content
    tag_count = text.count("<")
    if tag_count < 5:
        return text

    if _HAS_BS4:
        soup = BeautifulSoup(text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    else:
        # Fallback: crude tag removal
        return re.sub(r"<[^>]+>", " ", text)


def _is_noise(surface: str) -> bool:
    """Return True if the surface form is likely noise, not a real entity."""
    lower = surface.lower().strip()

    # Strip trailing/leading quotes and punctuation that leak from HTML
    lower = lower.strip("'\"`,;:.")

    # Blocklist check
    if lower in _BLOCKLIST:
        return True

    # Pattern-based rejection
    for pattern in _NOISE_PATTERNS:
        if pattern.search(surface):
            return True

    # All-caps short strings that look like acronyms/codes (< 3 chars handled by length check)
    # Strings with too many special characters relative to letters
    letters = sum(1 for c in surface if c.isalpha())
    if letters == 0:
        return True
    if letters < len(surface) * 0.3:
        return True

    return False


# Lazy-loaded model instance
_nlp: Language | None = None


def _get_model() -> Language:
    """Return the shared spaCy model, loading it on first call."""
    global _nlp
    if _nlp is None:
        model_name = settings.spacy_model
        logger.info("Loading spaCy model: %s", model_name)
        try:
            _nlp = spacy.load(model_name)
        except OSError:
            logger.warning(
                "spaCy model '%s' not found; falling back to blank 'en' pipeline",
                model_name,
            )
            _nlp = spacy.blank("en")
    return _nlp


def unload_model() -> None:
    """Unload the spaCy model to free memory.

    The model will be re-loaded lazily on the next call to ``_get_model()``.
    """
    global _nlp
    if _nlp is not None:
        logger.info("Unloading spaCy model to free memory")
        _nlp = None


def reload_model() -> None:
    """Force-unload and then eagerly reload the spaCy model.

    Useful to reclaim memory held by internal caches (vocab, string store)
    that accumulate over many documents.
    """
    unload_model()
    _get_model()


def extract_entities(text: str, file_id: str | None = None) -> list[dict[str, Any]]:
    """Extract named entities from *text* using spaCy NER.

    For texts larger than 100 KB the input is processed in overlapping
    chunks to keep memory bounded.  Offsets are adjusted so they refer to
    the original string.

    Returns a list of dicts, each containing:
        text          - the surface form
        entity_type   - mapped Rubberduck type (person, org, location, ...)
        char_offset   - character offset in the original text
        confidence    - extraction confidence (spaCy does not emit scores,
                        so we default to 0.85 for all NER hits)
        extractor     - always ``"spacy_ner"``
        file_id       - passed through for downstream convenience
    """
    nlp = _get_model()
    if not text or not text.strip():
        return []

    # Defense-in-depth: strip any residual HTML that may have leaked
    # through the parser pipeline (e.g. single-part HTML emails).
    text = _strip_html(text)
    if not text.strip():
        return []

    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()  # (text, type, offset) dedup

    chunks = _make_chunks(text)

    for chunk_start, chunk_text in chunks:
        try:
            doc = nlp(chunk_text)
        except Exception as exc:
            logger.warning("spaCy processing failed at offset %d: %s", chunk_start, exc)
            continue

        for ent in doc.ents:
            mapped_type = _LABEL_MAP.get(ent.label_)
            if mapped_type is None:
                continue

            # Skip very short or very long surface forms (likely noise)
            surface = ent.text.strip()
            if len(surface) < 2 or len(surface) > 200:
                continue

            # Filter out font names, CSS values, HTML artifacts, etc.
            if _is_noise(surface):
                continue

            absolute_offset = chunk_start + ent.start_char
            dedup_key = (surface, mapped_type, absolute_offset)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            entities.append(
                {
                    "text": surface,
                    "entity_type": mapped_type,
                    "char_offset": absolute_offset,
                    "confidence": 0.85,
                    "extractor": "spacy_ner",
                    "file_id": file_id,
                }
            )

    return entities


def _make_chunks(text: str) -> list[tuple[int, str]]:
    """Split text into (offset, chunk) pairs for processing.

    Chunks overlap by 500 characters so entities spanning a boundary
    are captured in at least one chunk.
    """
    if len(text) <= _CHUNK_SIZE:
        return [(0, text)]

    overlap = 500
    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append((start, text[start:end]))
        start = end - overlap
    return chunks
