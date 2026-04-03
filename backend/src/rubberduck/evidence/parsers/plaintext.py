"""Parsers for plain text, CSV, JSON, and XML files."""

import csv
import io
import json
import logging
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class PlainTextParser(BaseParser):
    """Parse plain text files with encoding detection."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        import chardet

        raw = file_path.read_bytes()
        detected = chardet.detect(raw[:10000])
        encoding = detected.get("encoding", "utf-8") or "utf-8"

        try:
            text = raw.decode(encoding, errors="replace")
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")

        return ParseResult(
            text_content=text,
            metadata={"encoding": encoding, "confidence": detected.get("confidence", 0)},
            parser_name="PlainTextParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["text/plain"]


class CsvParser(BaseParser):
    """Parse CSV/TSV files. Produces structured text representation."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        import chardet

        raw = file_path.read_bytes()
        detected = chardet.detect(raw[:10000])
        encoding = detected.get("encoding", "utf-8") or "utf-8"
        text = raw.decode(encoding, errors="replace")

        # Detect delimiter
        try:
            dialect = csv.Sniffer().sniff(text[:4096])
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = "," if file_path.suffix.lower() == ".csv" else "\t"

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)

        headers = rows[0] if rows else []
        row_count = len(rows) - 1 if rows else 0

        # Build readable text representation
        text_parts = [f"Headers: {', '.join(headers)}", f"Rows: {row_count}", ""]
        for i, row in enumerate(rows[:200]):  # Cap at 200 rows for text
            text_parts.append(" | ".join(row))
        if row_count > 200:
            text_parts.append(f"... ({row_count - 200} more rows)")

        return ParseResult(
            text_content="\n".join(text_parts),
            metadata={
                "headers": headers,
                "row_count": row_count,
                "delimiter": delimiter,
                "encoding": encoding,
            },
            parser_name="CsvParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["text/csv", "text/tab-separated-values"]


class JsonParser(BaseParser):
    """Parse JSON files. Handles large files with streaming."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        file_size = file_path.stat().st_size

        if file_size > 10 * 1024 * 1024:  # > 10MB: stream
            return self._parse_streaming(file_path)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)

        if isinstance(data, list):
            text = json.dumps(data[:100], indent=2, default=str)
            metadata = {"type": "array", "length": len(data)}
            if len(data) > 100:
                text += f"\n... ({len(data) - 100} more items)"
        elif isinstance(data, dict):
            text = json.dumps(data, indent=2, default=str)[:50000]
            metadata = {"type": "object", "keys": list(data.keys())[:50]}
        else:
            text = str(data)
            metadata = {"type": type(data).__name__}

        return ParseResult(
            text_content=text,
            metadata=metadata,
            parser_name="JsonParser",
        )

    def _parse_streaming(self, file_path: Path) -> ParseResult:
        """Stream large JSON files using ijson."""
        try:
            import ijson

            text_parts = []
            count = 0
            with open(file_path, "rb") as f:
                for item in ijson.items(f, "item"):
                    text_parts.append(json.dumps(item, default=str))
                    count += 1
                    if count >= 100:
                        break

            return ParseResult(
                text_content="\n".join(text_parts),
                metadata={"type": "streamed_array", "sample_count": count},
                warnings=["Large file: only first 100 items extracted"],
                parser_name="JsonParser",
            )
        except Exception as e:
            return ParseResult(
                text_content="",
                warnings=[f"Streaming JSON parse failed: {e}"],
                parser_name="JsonParser",
            )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["application/json"]


class XmlParser(BaseParser):
    """Parse XML files using streaming iterparse."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        from lxml import etree

        text_parts = []
        element_count = 0
        root_tag = None

        try:
            for event, elem in etree.iterparse(file_path, events=("end",)):
                if root_tag is None:
                    root_tag = elem.tag
                if elem.text and elem.text.strip():
                    text_parts.append(elem.text.strip())
                element_count += 1
                elem.clear()  # Free memory

                if len(text_parts) > 5000:
                    break
        except etree.XMLSyntaxError as e:
            return ParseResult(
                text_content="",
                warnings=[f"XML parse error: {e}"],
                parser_name="XmlParser",
            )

        return ParseResult(
            text_content="\n".join(text_parts),
            metadata={"root_tag": root_tag, "element_count": element_count},
            parser_name="XmlParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["application/xml", "text/xml"]
