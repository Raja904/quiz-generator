"""
app/utils/validators.py

Centralised business-rule validation for the quiz generation pipeline.

All functions raise ``ValueError`` (with a user-friendly message) on any
violation.  The route handler catches these and converts them to HTTP 422
responses with a structured ``detail`` payload.

Keeping validation here (rather than inline in routes or the service) makes
it reusable from CLI tools, tests, and future endpoints without duplication.
"""

from __future__ import annotations

# ── Constants ──────────────────────────────────────────────────────────────────

ALLOWED_QUESTION_COUNTS: list[int] = [10, 20, 30, 50, 75, 100, 150]
MAX_QUESTIONS_ABSOLUTE: int = 150          # hard ceiling regardless of pages
QUESTIONS_PER_PAGE_RATIO: float = 2.5     # max questions = selected_pages × ratio


# ── Page range ─────────────────────────────────────────────────────────────────

def validate_page_range(
    start_page: int,
    end_page: int,
    total_pages: int,
    max_pages: int = 100,
) -> None:
    """
    Validate that ``(start_page, end_page)`` is a legal page range.

    Args:
        start_page:  1-indexed inclusive start page (user-supplied).
        end_page:    1-indexed inclusive end page (user-supplied).
        total_pages: Total pages in the full document (from the parser).
        max_pages:   Maximum number of pages allowed per request.

    Raises:
        ValueError: with a human-readable description of the violation.
    """
    if start_page < 1:
        raise ValueError(
            f"start_page must be ≥ 1, got {start_page}."
        )
    if end_page > total_pages:
        raise ValueError(
            f"end_page ({end_page}) exceeds the document's total pages "
            f"({total_pages}). Please enter a value between 1 and {total_pages}."
        )
    if start_page > end_page:
        raise ValueError(
            f"start_page ({start_page}) must be ≤ end_page ({end_page})."
        )
    selected = end_page - start_page + 1
    if selected > max_pages:
        raise ValueError(
            f"Selected range is {selected} pages, but the maximum allowed per "
            f"request is {max_pages} pages. "
            f"Please narrow your selection (e.g. pages {start_page}–"
            f"{start_page + max_pages - 1})."
        )


# ── Question count ─────────────────────────────────────────────────────────────

def validate_question_count(
    total_questions: int,
    selected_pages: int,
    allowed_counts: list[int] | None = None,
) -> None:
    """
    Validate that *total_questions* is an allowed value and does not exceed
    the per-page capacity cap.

    Cap formula::

        max_questions = min(selected_pages × 2.5, 150)

    Args:
        total_questions: Number of questions the user requested.
        selected_pages:  Number of pages in the chosen range.
        allowed_counts:  Permitted question counts.  Defaults to
                         :data:`ALLOWED_QUESTION_COUNTS`.

    Raises:
        ValueError: with a human-readable description of the violation.
    """
    if total_questions < 1:
        raise ValueError(
            f"You requested {total_questions} questions, but you must request at least 1."
        )

    cap = min(int(selected_pages * QUESTIONS_PER_PAGE_RATIO), MAX_QUESTIONS_ABSOLUTE)
    if total_questions > cap:
        raise ValueError(
            f"You requested {total_questions} questions for {selected_pages} "
            f"page(s), but the maximum allowed is {cap} "
            f"(= min({selected_pages} pages × {QUESTIONS_PER_PAGE_RATIO}, "
            f"{MAX_QUESTIONS_ABSOLUTE})). "
            f"Please reduce the number of questions or expand the page range."
        )


# ── Convenience: compute max questions for a page count ───────────────────────

def max_questions_for_pages(
    page_count: int,
    allowed_counts: list[int] | None = None,
) -> int:
    """
    Return the highest *allowed* question count that does not exceed the
    per-page cap for *page_count* pages.

    Useful for the ``POST /pdf-info`` response so the frontend knows the
    ceiling before the user picks a range.

    Args:
        page_count:     Total pages being considered.
        allowed_counts: Permitted question counts.  Defaults to
                        :data:`ALLOWED_QUESTION_COUNTS`.

    Returns:
        The largest allowed count ≤ cap, or the smallest allowed count if
        the cap is below every option (very short document edge case).
    """
    cap = min(int(page_count * QUESTIONS_PER_PAGE_RATIO), MAX_QUESTIONS_ABSOLUTE)
    return max(1, cap)
