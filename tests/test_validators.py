"""
tests/test_validators.py

Unit tests for app.utils.validators.
All tests are pure (no I/O, no network).
"""

from __future__ import annotations

import pytest

from app.utils.validators import (
    ALLOWED_QUESTION_COUNTS,
    max_questions_for_pages,
    validate_page_range,
    validate_question_count,
)


# ── validate_page_range ────────────────────────────────────────────────────────

class TestValidatePageRange:
    def test_valid_full_document(self):
        """Selecting the whole document should pass."""
        validate_page_range(start_page=1, end_page=65, total_pages=65)

    def test_valid_sub_range(self):
        """A valid sub-range should pass without error."""
        validate_page_range(start_page=10, end_page=30, total_pages=65)

    def test_single_page(self):
        validate_page_range(start_page=5, end_page=5, total_pages=65)

    def test_start_page_zero_raises(self):
        with pytest.raises(ValueError, match="start_page must be ≥ 1"):
            validate_page_range(start_page=0, end_page=10, total_pages=65)

    def test_start_page_negative_raises(self):
        with pytest.raises(ValueError, match="start_page must be ≥ 1"):
            validate_page_range(start_page=-5, end_page=10, total_pages=65)

    def test_end_page_exceeds_total_raises(self):
        with pytest.raises(ValueError, match="end_page.*exceeds the document"):
            validate_page_range(start_page=1, end_page=70, total_pages=65)

    def test_start_after_end_raises(self):
        with pytest.raises(ValueError, match="start_page.*must be ≤ end_page"):
            validate_page_range(start_page=30, end_page=20, total_pages=65)

    def test_exceeds_max_pages_raises(self):
        with pytest.raises(ValueError, match="maximum allowed per request"):
            validate_page_range(
                start_page=1, end_page=101, total_pages=200, max_pages=100
            )

    def test_exactly_max_pages_passes(self):
        """Selecting exactly max_pages should be valid."""
        validate_page_range(
            start_page=1, end_page=100, total_pages=200, max_pages=100
        )

    def test_error_message_includes_limit(self):
        """Error message should mention the configured max."""
        with pytest.raises(ValueError, match="50 pages"):
            validate_page_range(
                start_page=1, end_page=60, total_pages=200, max_pages=50
            )


# ── validate_question_count ────────────────────────────────────────────────────

class TestValidateQuestionCount:
    def test_valid_count_within_cap(self):
        """30 questions for 20 pages (cap=50) should pass."""
        validate_question_count(total_questions=30, selected_pages=20)

    def test_every_allowed_count_with_enough_pages(self):
        """All allowed counts should pass when pages are sufficient."""
        for count in ALLOWED_QUESTION_COUNTS:
            # Need at least ceil(count / 2.5) pages
            min_pages = int(count / 2.5) + 1
            validate_question_count(total_questions=count, selected_pages=min_pages)

    def test_not_in_allowed_list_raises(self):
        with pytest.raises(ValueError, match="not an allowed question count"):
            validate_question_count(total_questions=25, selected_pages=20)

    def test_exceeds_per_page_cap_raises(self):
        """10 pages → cap = 25.  Requesting 30 should fail."""
        with pytest.raises(ValueError, match="maximum allowed is 25"):
            validate_question_count(total_questions=30, selected_pages=10)

    def test_cap_capped_at_150(self):
        """Even with 200 pages, cap is 150 (hard ceiling)."""
        # 200 pages × 2.5 = 500, but capped at 150
        validate_question_count(total_questions=150, selected_pages=200)

    def test_exactly_at_cap_passes(self):
        """Requesting exactly the cap should pass."""
        # 20 pages × 2.5 = 50 → 50 is in allowed list
        validate_question_count(total_questions=50, selected_pages=20)

    def test_error_message_includes_cap_formula(self):
        """Error message should explain the cap formula."""
        with pytest.raises(ValueError, match="2.5"):
            validate_question_count(total_questions=100, selected_pages=10)

    def test_custom_allowed_counts(self):
        with pytest.raises(ValueError, match="not an allowed question count"):
            validate_question_count(
                total_questions=20,
                selected_pages=100,
                allowed_counts=[10, 50, 100],
            )


# ── max_questions_for_pages ────────────────────────────────────────────────────

class TestMaxQuestionsForPages:
    def test_10_pages(self):
        # cap = min(10 * 2.5, 150) = 25 → largest allowed ≤ 25 = 20
        assert max_questions_for_pages(10) == 20

    def test_20_pages(self):
        # cap = 50 → largest allowed ≤ 50 = 50
        assert max_questions_for_pages(20) == 50

    def test_40_pages(self):
        # cap = 100 → largest allowed ≤ 100 = 100
        assert max_questions_for_pages(40) == 100

    def test_60_pages(self):
        # cap = 150 → largest allowed ≤ 150 = 150
        assert max_questions_for_pages(60) == 150

    def test_100_pages(self):
        # cap = 150 (hard cap) → 150
        assert max_questions_for_pages(100) == 150

    def test_3_pages_very_short(self):
        # cap = 7.5 → int = 7 → largest allowed ≤ 7 = 10? No, 10 > 7 → falls back to min
        # cap = min(3 * 2.5, 150) = 7 → no allowed count ≤ 7 → returns min(allowed) = 10
        result = max_questions_for_pages(3)
        assert result == 10  # falls back to the smallest allowed count

    def test_custom_allowed_counts(self):
        result = max_questions_for_pages(20, allowed_counts=[5, 15, 25, 50])
        # cap = 50 → largest ≤ 50 = 50
        assert result == 50
