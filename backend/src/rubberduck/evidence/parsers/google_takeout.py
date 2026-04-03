"""Google Takeout parser — detects and routes Takeout directory structures."""

import json
import logging
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent

logger = logging.getLogger(__name__)


class GoogleTakeoutParser(BaseParser):
    """Detect and parse Google Takeout export structures.

    Takeout directories typically contain product-named subdirectories like:
    - Mail/ (MBOX files)
    - My Activity/ (HTML or JSON activity logs)
    - Location History/ (Records.json with GPS data)
    - YouTube and YouTube Music/ (watch/search history)
    - Chrome/ (browsing history, bookmarks)
    - Drive/ (files)
    - Google Photos/ (photos)
    - Contacts/ (vCards)
    - Calendar/ (ICS files)
    """

    @classmethod
    def detect_takeout(cls, directory: Path) -> bool:
        """Check if a directory looks like a Google Takeout export."""
        if not directory.is_dir():
            return False
        takeout_markers = [
            "Takeout", "Mail", "My Activity", "Location History",
            "YouTube and YouTube Music", "Google Photos", "Drive",
        ]
        children = {d.name for d in directory.iterdir()}
        return len(children & set(takeout_markers)) >= 2 or "Takeout" in str(directory)

    @classmethod
    def get_product_dirs(cls, takeout_root: Path) -> dict[str, Path]:
        """Map product names to their directories."""
        products = {}
        for child in takeout_root.iterdir():
            if child.is_dir():
                products[child.name] = child
        return products

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        """Parse individual Takeout files based on their location in the structure."""
        name = file_path.name.lower()
        parent_parts = [p.lower() for p in file_path.parts]

        # Route to specialized sub-parsers based on file location
        if "my activity" in parent_parts:
            return self._parse_activity(file_path)
        elif "location history" in parent_parts or name == "records.json":
            return self._parse_location_history(file_path)
        elif "youtube" in " ".join(parent_parts):
            return self._parse_youtube(file_path)
        elif "chrome" in parent_parts:
            return self._parse_chrome(file_path)
        else:
            # Fallback: treat as generic file
            return ParseResult(
                text_content="",
                metadata={"takeout_product": "unknown", "path": str(file_path)},
                warnings=["Unrecognized Takeout file location"],
                parser_name="GoogleTakeoutParser",
            )

    def _parse_activity(self, file_path: Path) -> ParseResult:
        """Parse My Activity HTML or JSON files."""
        events = []

        if file_path.suffix.lower() == ".json":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                text_parts = []
                if isinstance(data, list):
                    for item in data:
                        title = item.get("title", "")
                        time = item.get("time", "")
                        header = item.get("header", "")

                        text_parts.append(f"[{time}] {header}: {title}")

                        if time:
                            events.append(RawEvent(
                                timestamp_raw=time,
                                event_type="media" if "YouTube" in header else "digital_activity",
                                event_subtype="activity_entry",
                                summary=f"{header}: {title[:100]}",
                                raw_data=item,
                            ))

                return ParseResult(
                    text_content="\n".join(text_parts[:5000]),
                    metadata={"activity_count": len(data) if isinstance(data, list) else 1},
                    events=events,
                    parser_name="GoogleTakeoutParser.activity",
                )
            except json.JSONDecodeError as e:
                return ParseResult(
                    text_content="",
                    warnings=[f"Failed to parse activity JSON: {e}"],
                    parser_name="GoogleTakeoutParser.activity",
                )
        elif file_path.suffix.lower() in (".html", ".htm"):
            from bs4 import BeautifulSoup

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                soup = BeautifulSoup(f.read(), "lxml")

            text = soup.get_text(separator="\n", strip=True)
            # Google activity HTML uses specific class names
            activity_cells = soup.find_all(class_="content-cell")
            for cell in activity_cells[:1000]:
                cell_text = cell.get_text(strip=True)
                if cell_text:
                    events.append(RawEvent(
                        timestamp_raw="",
                        event_type="digital_activity",
                        event_subtype="activity_entry",
                        summary=cell_text[:200],
                    ))

            return ParseResult(
                text_content=text[:50000],
                metadata={"activity_entries_found": len(activity_cells)},
                events=events,
                parser_name="GoogleTakeoutParser.activity_html",
            )

        return ParseResult(text_content="", parser_name="GoogleTakeoutParser.activity")

    def _parse_location_history(self, file_path: Path) -> ParseResult:
        """Parse Location History Records.json using streaming."""
        events = []
        text_parts = []

        try:
            import ijson

            count = 0
            with open(file_path, "rb") as f:
                for record in ijson.items(f, "locations.item"):
                    lat = record.get("latitudeE7", 0) / 1e7
                    lon = record.get("longitudeE7", 0) / 1e7
                    timestamp = record.get("timestamp", record.get("timestampMs", ""))

                    text_parts.append(f"[{timestamp}] {lat:.6f}, {lon:.6f}")
                    events.append(RawEvent(
                        timestamp_raw=str(timestamp),
                        event_type="location",
                        event_subtype="gps_checkin",
                        summary=f"Location: {lat:.4f}, {lon:.4f}",
                        raw_data={"lat": lat, "lon": lon, "accuracy": record.get("accuracy")},
                    ))
                    count += 1

            return ParseResult(
                text_content="\n".join(text_parts[:5000]),
                metadata={"location_count": count},
                events=events,
                parser_name="GoogleTakeoutParser.location",
            )
        except Exception as e:
            return ParseResult(
                text_content="",
                warnings=[f"Location history parse failed: {e}"],
                parser_name="GoogleTakeoutParser.location",
            )

    def _parse_youtube(self, file_path: Path) -> ParseResult:
        """Parse YouTube watch/search history."""
        events = []

        if file_path.suffix.lower() == ".json":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                text_parts = []
                for item in (data if isinstance(data, list) else [data]):
                    title = item.get("title", "")
                    time = item.get("time", "")
                    url = item.get("titleUrl", "")

                    subtype = "video_watch"
                    if "search" in file_path.name.lower():
                        subtype = "search_query"

                    text_parts.append(f"[{time}] {title}")

                    if time:
                        events.append(RawEvent(
                            timestamp_raw=time,
                            event_type="media",
                            event_subtype=subtype,
                            summary=f"YouTube: {title[:100]}",
                            raw_data={"url": url, "title": title},
                        ))

                return ParseResult(
                    text_content="\n".join(text_parts),
                    metadata={"youtube_entry_count": len(data) if isinstance(data, list) else 1},
                    events=events,
                    parser_name="GoogleTakeoutParser.youtube",
                )
            except Exception as e:
                return ParseResult(
                    text_content="",
                    warnings=[f"YouTube parse failed: {e}"],
                    parser_name="GoogleTakeoutParser.youtube",
                )

        # HTML fallback
        if file_path.suffix.lower() in (".html", ".htm"):
            from bs4 import BeautifulSoup

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                soup = BeautifulSoup(f.read(), "lxml")

            text = soup.get_text(separator="\n", strip=True)
            return ParseResult(
                text_content=text[:50000],
                parser_name="GoogleTakeoutParser.youtube_html",
            )

        return ParseResult(text_content="", parser_name="GoogleTakeoutParser.youtube")

    def _parse_chrome(self, file_path: Path) -> ParseResult:
        """Parse Chrome browsing history JSON."""
        if file_path.suffix.lower() != ".json":
            return ParseResult(text_content="", parser_name="GoogleTakeoutParser.chrome")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            events = []
            text_parts = []

            items = data if isinstance(data, list) else data.get("Browser History", [])
            for item in items:
                title = item.get("title", "")
                url = item.get("url", "")
                time = item.get("time_usec", item.get("time", ""))

                text_parts.append(f"[{time}] {title}: {url}")
                if time:
                    events.append(RawEvent(
                        timestamp_raw=str(time),
                        event_type="digital_activity",
                        event_subtype="page_view",
                        summary=f"Visited: {title[:100]}",
                        raw_data={"url": url, "title": title},
                    ))

            return ParseResult(
                text_content="\n".join(text_parts[:5000]),
                metadata={"history_count": len(items)},
                events=events,
                parser_name="GoogleTakeoutParser.chrome",
            )
        except Exception as e:
            return ParseResult(
                text_content="",
                warnings=[f"Chrome history parse failed: {e}"],
                parser_name="GoogleTakeoutParser.chrome",
            )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        # This parser is invoked by directory detection, not MIME type matching
        return []
