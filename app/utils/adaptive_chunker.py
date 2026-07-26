"""
app/utils/adaptive_chunker.py

Token-driven adaptive chunking utilities.

Instead of the user choosing chunk_size / questions_per_chunk manually,
we derive both from two first-class inputs:
  - total_tokens   : actual token count of the selected PDF text
  - total_questions: the number of questions the user wants

All functions here are pure (no I/O, no side-effects) and fully unit-testable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Encoding used for token counting.  cl100k_base is compatible with GPT-3.5/4
# and gives reasonable estimates for other models too.
_TIKTOKEN_ENCODING = "cl100k_base"


# ── Token counting ─────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """
    Count tokens in *text* using tiktoken (cl100k_base encoding).

    Falls back to a character-based estimate (~4 chars per token) when
    tiktoken is not installed, so the function never raises ImportError.
    """
    try:
        import tiktoken  # noqa: PLC0415
        enc = tiktoken.get_encoding(_TIKTOKEN_ENCODING)
        return len(enc.encode(text))
    except ImportError:
        logger.warning(
            "tiktoken not installed — using character-based token estimate. "
            "Run: pip install tiktoken"
        )
        return max(1, len(text) // 4)


# ── Adaptive chunk parameter computation ──────────────────────────────────────

def compute_chunk_params(
    total_tokens: int,
    total_questions: int,
    min_chunk_size: int = 300,
    max_chunk_size: int = 3000,
    overlap_ratio: float = 0.10,
) -> tuple[int, int]:
    """
    Derive ``(chunk_size, chunk_overlap)`` from the document token count and
    the desired number of questions.

    The core idea: give each question roughly equal "coverage" of the text.

    .. code-block:: text

        tokens_per_question = total_tokens / total_questions
        chunk_size          = clamp(tokens_per_question, min, max)
        chunk_overlap       = max(50, chunk_size × overlap_ratio)

    Args:
        total_tokens:    Token count of the text that will be chunked.
        total_questions: Number of quiz questions the user requested.
        min_chunk_size:  Lower bound for chunk_size (tokens).
        max_chunk_size:  Upper bound for chunk_size (tokens).
        overlap_ratio:   Fraction of chunk_size to use as overlap.

    Returns:
        ``(chunk_size, chunk_overlap)`` as a tuple of ints.

    Raises:
        ValueError: If *total_questions* ≤ 0.
    """
    if total_questions <= 0:
        raise ValueError(f"total_questions must be > 0, got {total_questions}.")

    if total_tokens <= 0:
        chunk_size = min_chunk_size
    else:
        tokens_per_question = total_tokens / total_questions
        chunk_size = int(max(min_chunk_size, min(tokens_per_question, max_chunk_size)))

    chunk_overlap = max(50, int(chunk_size * overlap_ratio))

    logger.debug(
        "Adaptive params | total_tokens=%d total_questions=%d "
        "→ chunk_size=%d chunk_overlap=%d",
        total_tokens,
        total_questions,
        chunk_size,
        chunk_overlap,
    )
    return chunk_size, chunk_overlap


# ── Question distribution ──────────────────────────────────────────────────────

def distribute_questions(num_chunks: int, total_questions: int) -> list[int]:
    """
    Distribute *total_questions* across *num_chunks* as evenly as possible,
    guaranteeing the list always sums to exactly *total_questions*.

    The integer remainder is spread one-at-a-time across the *first* N chunks,
    so no chunk ever gets more than one extra question.

    Examples::

        distribute_questions(6, 30) → [5, 5, 5, 5, 5, 5]   # exact
        distribute_questions(4, 30) → [8, 8, 7, 7]          # remainder=2
        distribute_questions(7, 30) → [5, 5, 5, 5, 4, 4, 4] # remainder=2 → first 2 get +1... wait
        # 30 // 7 = 4, remainder = 2 → first 2 chunks get 5, rest get 4
        # → [5, 5, 4, 4, 4, 4, 4]  ✓  sum = 5+5+4*5 = 30

    Args:
        num_chunks:      Number of chunks (must be > 0).
        total_questions: Total number of questions to distribute.

    Returns:
        List of ints, one per chunk, summing to *total_questions*.
        Returns an empty list when *num_chunks* ≤ 0.
    """
    if num_chunks <= 0:
        return []
    if total_questions <= 0:
        return [0] * num_chunks

    base = total_questions // num_chunks
    remainder = total_questions % num_chunks
    distribution = [base + (1 if i < remainder else 0) for i in range(num_chunks)]

    logger.debug(
        "Question distribution | total=%d chunks=%d → %s",
        total_questions,
        num_chunks,
        distribution,
    )
    return distribution
