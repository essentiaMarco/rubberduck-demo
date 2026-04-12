"""Format-specific parsers. Each parser implements BaseParser."""

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent
from rubberduck.evidence.parsers.pdf import PdfParser
from rubberduck.evidence.parsers.docx import DocxParser
from rubberduck.evidence.parsers.plaintext import PlainTextParser, CsvParser, JsonParser, XmlParser
from rubberduck.evidence.parsers.html_parser import HtmlParser
from rubberduck.evidence.parsers.email_parser import EmailParser, MboxParser
from rubberduck.evidence.parsers.image import ImageParser
from rubberduck.evidence.parsers.google_takeout import GoogleTakeoutParser
from rubberduck.evidence.parsers.whatsapp_parser import WhatsAppParser
from rubberduck.evidence.parsers.browser_db import BrowserDbParser

# Parser registry: MIME type -> parser class
PARSER_REGISTRY: dict[str, type[BaseParser]] = {}


def _register_all():
    """Build the MIME type -> parser mapping."""
    parser_classes = [
        PlainTextParser, CsvParser, JsonParser, XmlParser,
        PdfParser, DocxParser, HtmlParser,
        EmailParser, MboxParser,
        ImageParser,
    ]
    for cls in parser_classes:
        for mime in cls.supported_mimetypes():
            PARSER_REGISTRY[mime] = cls


_register_all()


def get_parser_for_mime(mime_type: str) -> type[BaseParser] | None:
    """Look up a parser by MIME type."""
    return PARSER_REGISTRY.get(mime_type)


def get_parser_for_ext(ext: str) -> type[BaseParser] | None:
    """Fallback: look up parser by file extension."""
    EXT_MAP = {
        ".txt": PlainTextParser, ".log": PlainTextParser, ".md": PlainTextParser,
        ".csv": CsvParser, ".tsv": CsvParser,
        ".json": JsonParser, ".jsonl": JsonParser,
        ".xml": XmlParser,
        ".pdf": PdfParser,
        ".docx": DocxParser,
        ".html": HtmlParser, ".htm": HtmlParser,
        ".eml": EmailParser,
        ".mbox": MboxParser,
        ".jpg": ImageParser, ".jpeg": ImageParser, ".png": ImageParser,
        ".gif": ImageParser, ".tiff": ImageParser, ".bmp": ImageParser,
        ".webp": ImageParser, ".heic": ImageParser,
        # Browser databases
        ".sqlite": BrowserDbParser, ".db": BrowserDbParser, ".sqlite3": BrowserDbParser,
        ".sqlitedb": BrowserDbParser,
    }
    # Check if .txt file is actually a WhatsApp export
    if ext.lower() == ".txt":
        # This is handled at a higher level with WhatsAppParser.detect_whatsapp()
        pass
    return EXT_MAP.get(ext.lower())


__all__ = [
    "BaseParser", "ParseResult", "RawEvent",
    "PARSER_REGISTRY", "get_parser_for_mime", "get_parser_for_ext",
]
