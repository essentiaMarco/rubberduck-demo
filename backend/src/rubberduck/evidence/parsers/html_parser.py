"""HTML parser using BeautifulSoup."""

import logging
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class HtmlParser(BaseParser):
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        from bs4 import BeautifulSoup

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        soup = BeautifulSoup(content, "lxml")

        # Remove script and style elements
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = soup.title.string if soup.title else None
        text = soup.get_text(separator="\n", strip=True)

        # Extract links
        links = []
        for a in soup.find_all("a", href=True):
            links.append({"text": a.get_text(strip=True), "href": a["href"]})

        # Extract meta tags
        meta = {}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property", "")
            content_val = tag.get("content", "")
            if name and content_val:
                meta[name] = content_val

        return ParseResult(
            text_content=text,
            metadata={
                "title": title,
                "link_count": len(links),
                "links": links[:100],
                "meta": meta,
            },
            parser_name="HtmlParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["text/html", "application/xhtml+xml"]
