"""Image parser: EXIF extraction + optional OCR."""

import logging
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult, RawEvent

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img = Image.open(file_path)
        exif_data = {}
        gps_data = {}
        events = []
        entities_hint = []
        text_content = ""

        # Extract EXIF
        raw_exif = img._getexif()
        if raw_exif:
            for tag_id, value in raw_exif.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                if tag_name == "GPSInfo":
                    for gps_tag_id, gps_value in value.items():
                        gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                        gps_data[gps_tag_name] = str(gps_value)
                else:
                    try:
                        exif_data[tag_name] = str(value)
                    except Exception:
                        pass

        metadata = {
            "format": img.format,
            "size": img.size,
            "mode": img.mode,
            "exif": exif_data,
            "gps": gps_data,
        }

        # Create GPS event if available
        if gps_data:
            lat = _convert_gps(gps_data.get("GPSLatitude"), gps_data.get("GPSLatitudeRef"))
            lon = _convert_gps(gps_data.get("GPSLongitude"), gps_data.get("GPSLongitudeRef"))
            if lat and lon:
                timestamp = exif_data.get("DateTimeOriginal", exif_data.get("DateTime", ""))
                events.append(RawEvent(
                    timestamp_raw=timestamp,
                    event_type="location",
                    event_subtype="photo_gps",
                    summary=f"Photo taken at {lat:.6f}, {lon:.6f}",
                    raw_data={"lat": lat, "lon": lon, "file": file_path.name},
                ))

        # Timestamp event
        date_taken = exif_data.get("DateTimeOriginal") or exif_data.get("DateTime")
        if date_taken:
            events.append(RawEvent(
                timestamp_raw=date_taken,
                event_type="file_activity",
                event_subtype="photo_taken",
                summary=f"Photo: {file_path.name}",
                raw_data={"camera": exif_data.get("Model"), "software": exif_data.get("Software")},
            ))

        if exif_data.get("Model"):
            entities_hint.append(exif_data["Model"])

        # OCR if enabled and image is likely text-bearing
        try:
            from rubberduck.config import settings

            if settings.ocr_enabled:
                import pytesseract
                ocr_text = pytesseract.image_to_string(img)
                if ocr_text.strip():
                    text_content = ocr_text
        except Exception as e:
            logger.debug(f"OCR skipped for {file_path}: {e}")

        img.close()

        return ParseResult(
            text_content=text_content,
            metadata=metadata,
            events=events,
            entities_hint=entities_hint,
            parser_name="ImageParser",
        )

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return [
            "image/jpeg", "image/png", "image/gif", "image/tiff",
            "image/bmp", "image/webp",
        ]


def _convert_gps(value_str: str | None, ref: str | None) -> float | None:
    """Convert EXIF GPS tuple string to decimal degrees."""
    if not value_str:
        return None
    try:
        # EXIF GPS values come as tuples of rationals
        # After str() they look like "(47, 36, 24.123)"
        cleaned = value_str.strip("()").replace(" ", "")
        parts = [float(x) for x in cleaned.split(",")]
        if len(parts) == 3:
            deg = parts[0] + parts[1] / 60 + parts[2] / 3600
            if ref in ("S", "W"):
                deg = -deg
            return deg
    except (ValueError, IndexError):
        pass
    return None
