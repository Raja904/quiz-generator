"""
app/parsers/pdf_parser.py

PDF text extraction using PyMuPDF (primary).

Two public entry points:
  parse_pdf_range(file_bytes, filename, start_page, end_page)
      Extract text from a specific 1-indexed page range only.
      This is the primary function used by the quiz pipeline.

  parse_pdf(file_bytes, filename)
      Convenience wrapper: extracts the entire document.
      Used by POST /pdf-info and tests.

Handles corrupted files, empty documents, image-only PDFs, and out-of-range
page numbers gracefully with descriptive PDFParseError messages.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path  # noqa: F401  (kept for potential future use)

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    text: str                   # Joined text of extracted pages (raw, not cleaned)
    pages: list[str]            # Per-page text strings
    page_count: int             # Number of pages actually extracted (range size)
    total_pages: int            # Total pages in the full PDF document
    parse_time_seconds: float


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


# ── Primary entry point ────────────────────────────────────────────────────────

def parse_pdf_range(
    file_bytes: bytes,
    filename: str = "upload.pdf",
    start_page: int = 1,
    end_page: int | None = None,
) -> ParseResult:
    """
    Extract text from a specific page range of a PDF.

    Args:
        file_bytes: Raw bytes of the uploaded PDF.
        filename:   Original filename (used in error messages only).
        start_page: 1-indexed inclusive start page. Defaults to 1.
        end_page:   1-indexed inclusive end page.  ``None`` → last page.

    Returns:
        :class:`ParseResult` where:
          - ``page_count``  = number of pages in the requested range.
          - ``total_pages`` = total pages in the full document.

    Raises:
        PDFParseError: For invalid files, out-of-range pages, or no text found.
    """
    start = time.perf_counter()
    doc = _open_pdf(file_bytes, filename)

    try:
        total_pages: int = len(doc)

        # Resolve defaults
        effective_end: int = end_page if end_page is not None else total_pages

        # Basic range sanity (detailed validation happens in validators.py, but
        # guard against Python index errors here too)
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

        # Extract pages (fitz is 0-indexed)
        pages_text: list[str] = []
        for page_num in range(start_page - 1, effective_end):
            page = doc[page_num]
            text = page.get_text("text")  # type: ignore[attr-defined]
            if text.strip():
                pages_text.append(text)

    finally:
        doc.close()

    full_text = "\n\n".join(pages_text)

    if not full_text.strip():
        raise PDFParseError(
            f"No extractable text found in pages {start_page}–{effective_end} of "
            f"'{filename}'. The selected pages may contain only images or scanned "
            "content (OCR not yet supported)."
        )

    elapsed = time.perf_counter() - start
    page_count = effective_end - start_page + 1

    logger.info(
        "PDF parsed | file=%s pages=%d–%d (%d pages) total=%d parse_time=%.3fs",
        filename,
        start_page,
        effective_end,
        page_count,
        total_pages,
        elapsed,
    )

    return ParseResult(
        text=full_text,
        pages=pages_text,
        page_count=page_count,
        total_pages=total_pages,
        parse_time_seconds=elapsed,
    )


# ── Convenience wrapper ───────────────────────────────────────────────────────

def parse_pdf(file_bytes: bytes, filename: str = "upload.pdf") -> ParseResult:
    """
    Extract text from the **entire** PDF.

    Thin wrapper around :func:`parse_pdf_range` with the full page range.
    Used by ``POST /pdf-info`` and legacy callers.
    """
    return parse_pdf_range(file_bytes, filename, start_page=1, end_page=None)
