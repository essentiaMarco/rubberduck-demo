"""PDF parser using pdfplumber with Tesseract OCR fallback."""

import logging
from pathlib import Path

from rubberduck.evidence.parsers.base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """Parse PDF files. Falls back to OCR for scanned documents."""

    def parse(self, file_path: Path, **kwargs) -> ParseResult:
        import pdfplumber

        text_parts = []
        metadata = {}
        pages = 0
        warnings = []

        try:
            with pdfplumber.open(file_path) as pdf:
                metadata = {
                    "page_count": len(pdf.pages),
                    "metadata": pdf.metadata or {},
                }
                pages = len(pdf.pages)

                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        text_parts.append(page_text)
                    else:
                        # Try OCR fallback for this page
                        ocr_text = self._ocr_page(file_path, i)
                        if ocr_text:
                            text_parts.append(ocr_text)
                            warnings.append(f"Page {i + 1}: used OCR fallback")
                        else:
                            warnings.append(f"Page {i + 1}: no text extracted")

        except Exception as e:
            logger.error(f"Failed to parse PDF {file_path}: {e}")
            # Full OCR fallback
            ocr_text = self._ocr_full(file_path)
            if ocr_text:
                text_parts.append(ocr_text)
                warnings.append("Full document OCR fallback used")
            else:
                warnings.append(f"PDF parse failed: {e}")

        full_text = "\n\n".join(text_parts)

        # Extract potential entities from metadata
        entities_hint = []
        pdf_meta = metadata.get("metadata", {})
        if pdf_meta.get("Author"):
            entities_hint.append(pdf_meta["Author"])
        if pdf_meta.get("Creator"):
            entities_hint.append(pdf_meta["Creator"])

        return ParseResult(
            text_content=full_text,
            metadata=metadata,
            pages=pages,
            warnings=warnings,
            entities_hint=entities_hint,
            parser_name="PdfParser",
        )

    def _ocr_page(self, pdf_path: Path, page_num: int) -> str:
        """OCR a single PDF page using Tesseract."""
        try:
            from rubberduck.config import settings

            if not settings.ocr_enabled:
                return ""

            import pytesseract
            from pdf2image import convert_from_path

            images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1)
            if images:
                return pytesseract.image_to_string(images[0])
        except ImportError:
            logger.debug("pdf2image not available for OCR fallback")
        except Exception as e:
            logger.debug(f"OCR failed for page {page_num}: {e}")
        return ""

    def _ocr_full(self, pdf_path: Path) -> str:
        """OCR entire PDF as fallback."""
        try:
            from rubberduck.config import settings

            if not settings.ocr_enabled:
                return ""

            import pytesseract
            from pdf2image import convert_from_path

            images = convert_from_path(pdf_path)
            texts = [pytesseract.image_to_string(img) for img in images]
            return "\n\n".join(texts)
        except ImportError:
            return ""
        except Exception as e:
            logger.debug(f"Full OCR failed: {e}")
            return ""

    @classmethod
    def supported_mimetypes(cls) -> list[str]:
        return ["application/pdf"]
