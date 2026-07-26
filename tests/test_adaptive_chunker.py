"""
tests/test_adaptive_chunker.py

Unit tests for app.utils.adaptive_chunker.
All tests are pure (no I/O, no network).
"""

from __future__ import annotations

import pytest

from app.utils.adaptive_chunker import compute_chunk_params, distribute_questions


# ── compute_chunk_params ──────────────────────────────────────────────────────

class TestComputeChunkParams:
    def test_typical_medium_document(self):
        """~10 k tokens, 20 questions → tokens_per_q = 500 → within bounds."""
        size, overlap = compute_chunk_params(
            total_tokens=10_000,
            total_questions=20,
            min_chunk_size=300,
            max_chunk_size=3000,
            overlap_ratio=0.10,
        )
        assert size == 500
        assert overlap == 50  # 10% of 500

    def test_short_document_floored_at_min(self):
        """Very few tokens → chunk_size should be clamped to min_chunk_size."""
        size, overlap = compute_chunk_params(
            total_tokens=100,
            total_questions=50,
            min_chunk_size=300,
            max_chunk_size=3000,
        )
        assert size == 300
        assert overlap >= 50

    def test_long_document_capped_at_max(self):
        """Massive document, few questions → chunk_size should be clamped to max."""
        size, overlap = compute_chunk_params(
            total_tokens=500_000,
            total_questions=10,
            min_chunk_size=300,
            max_chunk_size=3000,
        )
        assert size == 3000
        assert overlap == 300  # 10% of 3000

    def test_zero_tokens_uses_min(self):
        """Edge case: empty document text → fall back to min_chunk_size."""
        size, overlap = compute_chunk_params(
            total_tokens=0,
            total_questions=10,
            min_chunk_size=300,
            max_chunk_size=3000,
        )
        assert size == 300

    def test_invalid_total_questions_raises(self):
        with pytest.raises(ValueError, match="total_questions must be > 0"):
            compute_chunk_params(total_tokens=5000, total_questions=0)

    def test_overlap_floor_of_50(self):
        """Even if 10% of chunk_size < 50, overlap should be at least 50."""
        size, overlap = compute_chunk_params(
            total_tokens=3_000,
            total_questions=10,  # tokens_per_q = 300 → exactly min
            min_chunk_size=300,
            max_chunk_size=3000,
            overlap_ratio=0.10,
        )
        # 10% of 300 = 30, floored to 50
        assert overlap == 50

    def test_custom_bounds(self):
        """Custom min/max should be respected."""
        size, overlap = compute_chunk_params(
            total_tokens=2_000,
            total_questions=4,   # tokens_per_q = 500
            min_chunk_size=100,
            max_chunk_size=400,
        )
        assert size == 400  # capped at max

    def test_exact_boundary(self):
        """tokens_per_q exactly equals max_chunk_size → use max."""
        size, overlap = compute_chunk_params(
            total_tokens=30_000,
            total_questions=10,   # tokens_per_q = 3000 = max
            min_chunk_size=300,
            max_chunk_size=3000,
        )
        assert size == 3000


# ── distribute_questions ──────────────────────────────────────────────────────

class TestDistributeQuestions:
    def test_even_distribution(self):
        dist = distribute_questions(num_chunks=6, total_questions=30)
        assert dist == [5, 5, 5, 5, 5, 5]
        assert sum(dist) == 30

    def test_remainder_spread_to_first_chunks(self):
        dist = distribute_questions(num_chunks=4, total_questions=30)
        # 30 // 4 = 7, remainder = 2 → first 2 chunks get 8
        assert dist == [8, 8, 7, 7]
        assert sum(dist) == 30

    def test_single_chunk(self):
        dist = distribute_questions(num_chunks=1, total_questions=20)
        assert dist == [20]

    def test_more_chunks_than_questions(self):
        """Each chunk gets at most 1 question; excess chunks get 0."""
        dist = distribute_questions(num_chunks=10, total_questions=3)
        assert dist == [1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        assert sum(dist) == 3

    def test_sum_always_equals_total(self):
        """Property: sum(distribute_questions(n, q)) == q for all valid inputs."""
        for n in range(1, 20):
            for q in [10, 20, 30, 50, 75, 100, 150]:
                dist = distribute_questions(num_chunks=n, total_questions=q)
                assert sum(dist) == q, f"Failed for n={n}, q={q}"
                assert len(dist) == n

    def test_zero_chunks_returns_empty(self):
        assert distribute_questions(num_chunks=0, total_questions=30) == []

    def test_zero_questions(self):
        dist = distribute_questions(num_chunks=5, total_questions=0)
        assert dist == [0, 0, 0, 0, 0]
        assert sum(dist) == 0

    def test_seven_chunks_thirty_questions(self):
        # 30 // 7 = 4, remainder = 2 → first 2 chunks get 5
        dist = distribute_questions(num_chunks=7, total_questions=30)
        assert dist[:2] == [5, 5]
        assert dist[2:] == [4, 4, 4, 4, 4]
        assert sum(dist) == 30
