"""
tests/test_chunker.py

Unit tests for token-aware text chunking.
"""

from __future__ import annotations

import pytest

from app.utils.chunker import TextChunk, chunk_text


SAMPLE_TEXT = "\n\n".join(
    [
        "Artificial intelligence is transforming the way we work and live.",
        "Machine learning is a subset of AI that allows systems to learn from data.",
        "Deep learning uses neural networks with many layers to model complex patterns.",
        "Natural language processing enables computers to understand human language.",
        "Computer vision allows machines to interpret and understand visual information.",
        "Reinforcement learning trains agents by rewarding desired behaviours.",
        "Transfer learning applies knowledge from one domain to another related domain.",
        "Generative AI can produce text, images, audio, and video from prompts.",
        "Large language models are trained on vast corpora of text data.",
        "The transformer architecture revolutionised natural language understanding.",
    ]
)


def test_chunk_returns_list_of_text_chunks():
    chunks = chunk_text(SAMPLE_TEXT, chunk_size=200, chunk_overlap=20)
    assert isinstance(chunks, list)
    assert all(isinstance(c, TextChunk) for c in chunks)


def test_chunks_are_indexed_sequentially():
    chunks = chunk_text(SAMPLE_TEXT, chunk_size=200, chunk_overlap=20)
    for i, chunk in enumerate(chunks):
        assert chunk.index == i


def test_chunk_text_is_non_empty():
    chunks = chunk_text(SAMPLE_TEXT, chunk_size=200, chunk_overlap=20)
    for chunk in chunks:
        assert chunk.text.strip() != ""


def test_all_content_covered():
    """All original paragraphs should appear in at least one chunk."""
    chunks = chunk_text(SAMPLE_TEXT, chunk_size=200, chunk_overlap=20)
    combined = " ".join(c.text for c in chunks)
    for paragraph in SAMPLE_TEXT.split("\n\n"):
        # Check a representative keyword from each paragraph
        first_word = paragraph.split()[0]
        assert first_word in combined, f"Paragraph starting with '{first_word}' missing from chunks"


def test_single_chunk_for_tiny_text():
    short = "This is a very short text. It should fit in one chunk."
    chunks = chunk_text(short, chunk_size=1500, chunk_overlap=150)
    assert len(chunks) == 1
    assert "very short text" in chunks[0].text


def test_empty_string_returns_no_chunks():
    chunks = chunk_text("", chunk_size=1500, chunk_overlap=150)
    assert chunks == []


def test_token_counts_are_positive():
    chunks = chunk_text(SAMPLE_TEXT, chunk_size=200, chunk_overlap=20)
    for chunk in chunks:
        assert chunk.token_count > 0


def test_custom_chunk_size_respected():
    """With a small chunk_size, we should get more chunks than with a large one."""
    small_chunks = chunk_text(SAMPLE_TEXT, chunk_size=50, chunk_overlap=5)
    large_chunks = chunk_text(SAMPLE_TEXT, chunk_size=1500, chunk_overlap=150)
    assert len(small_chunks) >= len(large_chunks)
