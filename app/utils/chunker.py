"""
app/utils/chunker.py

Token-aware text chunking using tiktoken.
  - Respects paragraph boundaries (splits on double newlines first).
  - Supports configurable chunk size and overlap.
  - Returns chunks with their estimated token counts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Encoding used for token counting. cl100k_base is compatible with GPT-3.5/4
# and gives reasonable estimates for other models too.
_TIKTOKEN_ENCODING = "cl100k_base"


@dataclass
class TextChunk:
    index: int
    text: str
    token_count: int


def _get_encoder():
    """Lazily load tiktoken encoder (avoids import cost at module load)."""
    try:
        import tiktoken
        return tiktoken.get_encoding(_TIKTOKEN_ENCODING)
    except ImportError as exc:
        raise RuntimeError(
            "tiktoken is not installed. Run: uv pip install tiktoken"
        ) from exc


def _count_tokens(text: str, encoder) -> int:
    return len(encoder.encode(text))


def chunk_text(
    text: str,
    chunk_size: int = 1500,
    chunk_overlap: int = 150,
) -> list[TextChunk]:
    """
    Split *text* into token-aware overlapping chunks.

    Strategy:
    1. Split on paragraph boundaries (``\\n\\n``).
    2. Group paragraphs into chunks up to *chunk_size* tokens.
    3. When a chunk is full, carry the last *chunk_overlap* tokens forward
       into the next chunk (implemented by keeping a trailing overlap buffer).
    4. If a single paragraph exceeds *chunk_size*, split it on sentence
       boundaries as a fallback, then on whitespace if still too large.

    Args:
        text:          Clean text to chunk.
        chunk_size:    Target maximum tokens per chunk.
        chunk_overlap: Number of overlap tokens between adjacent chunks.

    Returns:
        Ordered list of :class:`TextChunk` objects.
    """
    encoder = _get_encoder()

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        return []

    # --- Flatten oversized paragraphs into sentence-level pieces ---
    flat_pieces: list[str] = []
    for para in paragraphs:
        if _count_tokens(para, encoder) <= chunk_size:
            flat_pieces.append(para)
        else:
            # Try sentence-level splitting
            import re
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current: list[str] = []
            current_tokens = 0
            for sentence in sentences:
                st = _count_tokens(sentence, encoder)
                if current_tokens + st > chunk_size and current:
                    flat_pieces.append(" ".join(current))
                    current = []
                    current_tokens = 0
                if st > chunk_size:
                    # Last resort: split on whitespace
                    words = sentence.split()
                    buf: list[str] = []
                    buf_tokens = 0
                    for word in words:
                        wt = _count_tokens(word, encoder)
                        if buf_tokens + wt > chunk_size and buf:
                            flat_pieces.append(" ".join(buf))
                            buf = []
                            buf_tokens = 0
                        buf.append(word)
                        buf_tokens += wt
                    if buf:
                        flat_pieces.append(" ".join(buf))
                else:
                    current.append(sentence)
                    current_tokens += st
            if current:
                flat_pieces.append(" ".join(current))

    # --- Greedy packing with overlap ---
    chunks: list[TextChunk] = []
    buffer: list[str] = []
    buffer_tokens = 0

    def _flush(buf: list[str], buf_tok: int) -> tuple[list[str], int]:
        """Save current buffer as a chunk; return overlap carry-over."""
        chunk_text_str = "\n\n".join(buf)
        chunks.append(
            TextChunk(
                index=len(chunks),
                text=chunk_text_str,
                token_count=buf_tok,
            )
        )
        # Build overlap: take pieces from the end until we reach chunk_overlap tokens
        overlap_buf: list[str] = []
        overlap_tokens = 0
        for piece in reversed(buf):
            pt = _count_tokens(piece, encoder)
            if overlap_tokens + pt > chunk_overlap:
                break
            overlap_buf.insert(0, piece)
            overlap_tokens += pt
        return overlap_buf, overlap_tokens

    for piece in flat_pieces:
        pt = _count_tokens(piece, encoder)
        if buffer_tokens + pt > chunk_size and buffer:
            buffer, buffer_tokens = _flush(buffer, buffer_tokens)
        buffer.append(piece)
        buffer_tokens += pt

    if buffer:
        _flush(buffer, buffer_tokens)

    logger.info(
        "Chunking complete | total_chunks=%d avg_tokens=%.0f",
        len(chunks),
        sum(c.token_count for c in chunks) / max(len(chunks), 1),
    )
    for c in chunks:
        logger.debug("  chunk[%d] tokens=%d", c.index, c.token_count)

    return chunks
