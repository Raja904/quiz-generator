"""
app/parsers/pdf_parser.py

PDF text extraction using PyMuPDF (primary) with per-page OCR fallback.

Two public entry points:
  parse_pdf_range(file_bytes, filename, start_page, end_page)
      Extract text from a specific 1-indexed page range only.
      This is the primary function used by the quiz pipeline.

  parse_pdf(file_bytes, filename)
      Convenience wrapper: extracts the entire document.
      Used by POST /pdf-info and tests.

Per-page OCR fallback:
  - Primary: page.get_text() via PyMuPDF.
  - If a page yields fewer than OCR_THRESHOLD characters of non-whitespace
    text, the page is rendered to a PNG image and passed to the configured
    OCR engine (default: EasyOCREngine).
  - OCR happens ONLY for pages that need it.
  - The result is merged seamlessly — downstream chunking and quiz
    generation see a single text blob with no structural difference.
  - The number of pages requiring OCR is logged.

API contracts are unchanged. PDFParseError is raised only when BOTH
native extraction and OCR fail to yield any text from the range.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path  # noqa: F401  (kept for potential future use)

logger = logging.getLogger(__name__)

# ── Tuneable constants ────────────────────────────────────────────────────────

# A page with fewer than this many non-whitespace characters is considered
# "image-only" and will be routed through OCR.
OCR_THRESHOLD: int = 30

# DPI used when rendering a page to an image for OCR.
# 150 is a good balance between accuracy and speed for typical lecture slides.
OCR_DPI: int = 150


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    text: str                   # Joined text of extracted pages (raw, not cleaned)
    pages: list[str]            # Per-page text strings
    page_count: int             # Number of pages actually extracted (range size)
    total_pages: int            # Total pages in the full PDF document
    parse_time_seconds: float
    ocr_page_count: int = 0     # How many pages needed OCR (0 if none)


class PDFParseError(Exception):
    """Raised when the PDF cannot be opened, is empty, or yields no text."""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _open_pdf(file_bytes: bytes, filename: str):
    """Open *file_bytes* as a fitz document; raise PDFParseError on failure."""
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError as exc:
        raise PDFParseError(
            "PyMuPDF is not installed. Run: pip install pymupdf"
        ) from exc

    if not file_bytes:
        raise PDFParseError(f"Uploaded file '{filename}' is empty.")

    if file_bytes[:4] != b"%PDF":
        raise PDFParseError(
            f"'{filename}' does not appear to be a valid PDF (bad magic bytes)."
        )

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:  # fitz.FileDataError is a subclass of Exception
        raise PDFParseError(f"Corrupted or unreadable PDF '{filename}': {exc}") from exc

    if len(doc) == 0:
        doc.close()
        raise PDFParseError(f"PDF '{filename}' contains no pages.")

    return doc


def _needs_ocr(raw_text: str) -> bool:
    """Return True if *raw_text* is too sparse to be useful without OCR."""
    return len(raw_text.replace(" ", "").replace("\n", "")) < OCR_THRESHOLD


def _ocr_page(page, filename: str, page_num_1indexed: int, ocr_engine) -> str:
    """
    Render *page* to a PNG image and run OCR on it.

    Args:
        page:             A fitz.Page object.
        filename:         Original filename (for log messages only).
        page_num_1indexed: 1-based page number (for log messages only).
        ocr_engine:       An instance of OCREngine. If None, returns empty string.

    Returns:
        OCR-extracted text, or empty string if OCR is unavailable or fails.
    """
    if ocr_engine is None:
        return ""

    try:
        import fitz  # noqa: PLC0415
        # Render page to PNG at the configured DPI
        mat = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        image_bytes: bytes = pix.tobytes("png")
        pix = None  # release memory

        ocr_text = ocr_engine.run(image_bytes)
        logger.debug(
            "OCR complete | file=%s page=%d chars=%d",
            filename,
            page_num_1indexed,
            len(ocr_text),
        )
        return ocr_text

    except Exception as exc:
        logger.warning(
            "OCR failed for page %d of '%s': %s",
            page_num_1indexed,
            filename,
            exc,
        )
        return ""


def _build_ocr_engine():
    """
    Build the default OCR engine (EasyOCR).

    Returns None if EasyOCR is not installed, so callers can degrade
    gracefully rather than crashing at import time.
    """
    try:
        from app.parsers.ocr_engine import EasyOCREngine  # noqa: PLC0415
        return EasyOCREngine(languages=["en"], gpu=False)
    except Exception as exc:
        logger.warning(
            "OCR engine could not be initialised (%s). "
            "Scanned pages will be skipped instead of OCR'd.",
            exc,
        )
        return None


# ── Primary entry point ────────────────────────────────────────────────────────

def parse_pdf_range(
    file_bytes: bytes,
    filename: str = "upload.pdf",
    start_page: int = 1,
    end_page: int | None = None,
) -> ParseResult:
    """
    Extract text from a specific page range of a PDF.

    For each page:
      1. Try PyMuPDF's page.get_text() (fast, native).
      2. If the result has fewer than OCR_THRESHOLD non-whitespace characters,
         render the page to an image and run EasyOCR on it.

    OCR is only run on pages that need it. All other aspects of the API
    contract remain identical to the original implementation.

    Args:
        file_bytes: Raw bytes of the uploaded PDF.
        filename:   Original filename (used in error messages only).
        start_page: 1-indexed inclusive start page. Defaults to 1.
        end_page:   1-indexed inclusive end page. ``None`` → last page.

    Returns:
        :class:`ParseResult` where:
          - ``page_count``     = number of pages in the requested range.
          - ``total_pages``    = total pages in the full document.
          - ``ocr_page_count`` = how many pages required OCR fallback.

    Raises:
        PDFParseError: For invalid files, out-of-range pages, or no text found
                       even after OCR.
    """
    start = time.perf_counter()
    doc = _open_pdf(file_bytes, filename)

    # Lazily build OCR engine; None if EasyOCR not installed.
    ocr_engine = _build_ocr_engine()

    try:
        total_pages: int = len(doc)

        # Resolve defaults
        effective_end: int = end_page if end_page is not None else total_pages

        # Basic range sanity
        if start_page < 1 or start_page > total_pages:
            raise PDFParseError(
                f"start_page ({start_page}) is out of range "
                f"for a {total_pages}-page document."
            )
        if effective_end < start_page or effective_end > total_pages:
            raise PDFParseError(
                f"end_page ({effective_end}) is out of range "
                f"for a {total_pages}-page document."
            )

        # ── Per-page extraction with OCR fallback ─────────────────────────────
        pages_text: list[str] = []
        ocr_page_count: int = 0

        for page_num in range(start_page - 1, effective_end):
            page = doc[page_num]
            raw_text: str = page.get_text("text")  # type: ignore[attr-defined]

            if _needs_ocr(raw_text):
                # Page is image-only or nearly blank — try OCR
                page_num_1indexed = page_num + 1
                logger.debug(
                    "Sparse text on page %d of '%s' (chars=%d) — attempting OCR.",
                    page_num_1indexed,
                    filename,
                    len(raw_text.strip()),
                )
                ocr_text = _ocr_page(page, filename, page_num_1indexed, ocr_engine)
                if ocr_text.strip():
                    pages_text.append(ocr_text)
                    ocr_page_count += 1
                # If OCR also returns nothing, we simply skip this page
                # (same behaviour as the original parser for blank pages)
            else:
                if raw_text.strip():
                    pages_text.append(raw_text)

    finally:
        doc.close()

    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        raise PDFParseError(
            f"No extractable text found in pages {start_page}–{effective_end} of "
            f"'{filename}'. The selected pages appear to contain only images or "
            "scanned content that could not be recognised."
        )

    elapsed = time.perf_counter() - start
    page_count = effective_end - start_page + 1

    logger.info(
        "PDF parsed | file=%s pages=%d–%d (%d pages) "
        "ocr_pages=%d total=%d parse_time=%.3fs",
        filename,
        start_page,
        effective_end,
        page_count,
        ocr_page_count,
        total_pages,
        elapsed,
    )

    return ParseResult(
        text=full_text,
        pages=pages_text,
        page_count=page_count,
        total_pages=total_pages,
        parse_time_seconds=elapsed,
        ocr_page_count=ocr_page_count,
    )


# ── Convenience wrapper ───────────────────────────────────────────────────────

def parse_pdf(file_bytes: bytes, filename: str = "upload.pdf") -> ParseResult:
    """
    Extract text from the **entire** PDF.

    Thin wrapper around :func:`parse_pdf_range` with the full page range.
    Used by ``POST /pdf-info`` and legacy callers.
    """
    return parse_pdf_range(file_bytes, filename, start_page=1, end_page=None)
