"""spaCy-based named entity recognition pipeline.

Loads a spaCy model at module level and provides chunked extraction
of named entities from arbitrary-length text.
"""

import logging
from typing import Any

import spacy
from spacy.language import Language

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
