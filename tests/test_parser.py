"""
tests/test_parser.py

Tests for PDF text extraction.
Uses minimal, self-contained synthetic PDFs created in-memory with PyMuPDF.
"""

from __future__ import annotations

import pytest

from app.parsers.pdf_parser import PDFParseError, ParseResult, parse_pdf, parse_pdf_range


def _make_pdf(pages: list[str]) -> bytes:
    """Create an in-memory PDF with one page per string in *pages*."""
    import fitz
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_minimal_pdf(text: str = "Hello, this is a test PDF.") -> bytes:
    return _make_pdf([text])


# ── parse_pdf (full document) ─────────────────────────────────────────────────

class TestParsePdf:
    def test_returns_parse_result(self):
        result = parse_pdf(_make_minimal_pdf("The quick brown fox."), "test.pdf")
        assert isinstance(result, ParseResult)

    def test_extracts_text(self):
        result = parse_pdf(_make_minimal_pdf("Python is great."), "test.pdf")
        assert "Python" in result.text

    def test_page_count_single_page(self):
        result = parse_pdf(_make_minimal_pdf(), "test.pdf")
        assert result.page_count == 1
        assert result.total_pages == 1

    def test_page_count_multipage(self):
        result = parse_pdf(_make_pdf(["Page one", "Page two", "Page three"]), "test.pdf")
        assert result.page_count == 3
        assert result.total_pages == 3

    def test_total_pages_equals_page_count_for_full_parse(self):
        """When parsing the full doc, page_count and total_pages should match."""
        result = parse_pdf(_make_pdf(["A", "B", "C", "D"]), "test.pdf")
        assert result.page_count == result.total_pages == 4

    def test_parse_time_is_positive(self):
        result = parse_pdf(_make_minimal_pdf(), "test.pdf")
        assert result.parse_time_seconds >= 0.0

    def test_empty_bytes_raises(self):
        with pytest.raises(PDFParseError, match="empty"):
            parse_pdf(b"", "empty.pdf")

    def test_non_pdf_bytes_raises(self):
        with pytest.raises(PDFParseError):
            parse_pdf(b"This is not a PDF at all!", "fake.txt")

    def test_corrupted_pdf_raises(self):
        with pytest.raises(PDFParseError):
            parse_pdf(b"%PDF-1.4 corrupted garbage data @@@###!!!", "corrupted.pdf")


# ── parse_pdf_range ────────────────────────────────────────────────────────────

class TestParsePdfRange:
    def _make_5page_pdf(self) -> bytes:
        return _make_pdf([
            "Page 1: Introduction to machine learning.",
            "Page 2: Supervised learning algorithms.",
            "Page 3: Unsupervised learning and clustering.",
            "Page 4: Neural networks and deep learning.",
            "Page 5: Conclusion and future directions.",
        ])

    def test_full_range_same_as_parse_pdf(self):
        pdf_bytes = self._make_5page_pdf()
        full = parse_pdf(pdf_bytes, "test.pdf")
        ranged = parse_pdf_range(pdf_bytes, "test.pdf", start_page=1, end_page=5)
        assert full.page_count == ranged.page_count
        assert full.total_pages == ranged.total_pages

    def test_sub_range_page_count(self):
        pdf_bytes = self._make_5page_pdf()
        result = parse_pdf_range(pdf_bytes, "test.pdf", start_page=2, end_page=4)
        assert result.page_count == 3
        assert result.total_pages == 5

    def test_total_pages_always_full_document(self):
        """total_pages must reflect the whole PDF, not just the extracted range."""
        pdf_bytes = self._make_5page_pdf()
        result = parse_pdf_range(pdf_bytes, "test.pdf", start_page=3, end_page=3)
        assert result.page_count == 1
        assert result.total_pages == 5

    def test_none_end_page_defaults_to_last(self):
        pdf_bytes = self._make_5page_pdf()
        result = parse_pdf_range(pdf_bytes, "test.pdf", start_page=1, end_page=None)
        assert result.page_count == 5

    def test_extracts_only_selected_pages(self):
        pdf_bytes = self._make_5page_pdf()
        result = parse_pdf_range(pdf_bytes, "test.pdf", start_page=2, end_page=2)
        assert "Supervised" in result.text
        # Pages outside the range should not appear
        assert "Introduction" not in result.text
        assert "Conclusion" not in result.text

    def test_single_page_range(self):
        pdf_bytes = self._make_5page_pdf()
        result = parse_pdf_range(pdf_bytes, "test.pdf", start_page=4, end_page=4)
        assert result.page_count == 1
        assert "Neural" in result.text

    def test_start_out_of_range_raises(self):
        pdf_bytes = self._make_5page_pdf()
        with pytest.raises(PDFParseError, match="out of range"):
            parse_pdf_range(pdf_bytes, "test.pdf", start_page=10, end_page=10)

    def test_end_out_of_range_raises(self):
        pdf_bytes = self._make_5page_pdf()
        with pytest.raises(PDFParseError, match="out of range"):
            parse_pdf_range(pdf_bytes, "test.pdf", start_page=1, end_page=10)

    def test_empty_bytes_raises(self):
        with pytest.raises(PDFParseError, match="empty"):
            parse_pdf_range(b"", "empty.pdf")
