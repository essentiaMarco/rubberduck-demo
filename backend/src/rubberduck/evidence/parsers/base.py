"""Abstract base parser and shared data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RawEvent:
    """A timeline event derived from parsing. Minimal structure — timeline service normalizes."""

    timestamp_raw: str
    event_type: str  # communication, file_activity, login, location, legal, media
    event_subtype: str  # email_sent, page_view, gps_checkin, etc.
    summary: str
    actor: str | None = None
    target: str | None = None
    raw_data: dict | None = None
    confidence: float = 1.0


@dataclass
class ParseResult:
    """Output of a parser. Every parser must return this structure."""

    text_content: str  # Extracted full text
    metadata: dict = field(default_factory=dict)  # Format-specific metadata
    events: list[RawEvent] = field(default_factory=list)  # Derived timeline events
    entities_hint: list[str] = field(default_factory=list)  # Pre-identified entity strings
    pages: int = 0  # Page count for paginated documents
    language: str | None = None
    warnings: list[str] = field(default_factory=list)  # Non-fatal parse issues
    parser_name: str = ""


class BaseParser(ABC):
    """All format-specific parsers implement this interface."""

    @abstractmethod
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        """Parse a file and return structured content.

        Must not modify the original file.
        Must not load entire large files into memory.
        """
        ...

    @classmethod
    @abstractmethod
    def supported_mimetypes(cls) -> list[str]:
        """Return MIME types this parser handles."""
        ...

    @classmethod
    def parser_name(cls) -> str:
        return cls.__name__
