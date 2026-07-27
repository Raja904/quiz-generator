"""
app/utils/adaptive_chunker.py

Utility functions for token counting.

NOTE: compute_chunk_params has been removed as part of the pipeline decoupling.
Chunking is now fixed (document-driven), not question-count-driven.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TIKTOKEN_ENCODING = "cl100k_base"


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
