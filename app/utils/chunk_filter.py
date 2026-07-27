"""
app/utils/chunk_filter.py

Heuristic-based filter to determine if a chunk of text contains meaningful content
worth sending to the LLM. Applied at TWO stages:
  1. Page-level (before chunking): drops entire pages.
  2. Chunk-level (after chunking): drops individual chunks.

Discards: Table of Contents, Index, References, Bibliography, Copyright,
          Cover pages, Glossary, Acknowledgements, and repetitive header-only chunks.
"""

from __future__ import annotations

import re

# Common headers for non-content sections
_SKIP_HEADERS = {
    "table of contents",
    "contents",
    "preface",
    "acknowledgements",
    "acknowledgment",
    "index",
    "references",
    "bibliography",
    "glossary",
    "copyright",
    "cover",
    "about the author",
    "about the authors",
}

# Phrases that indicate meta-document content (should not generate questions)
_SKIP_PHRASES = {
    "all rights reserved",
    "printed in",
    "published by",
    "isbn",
    "library of congress",
    "typeset by",
    "first published",
}


def _normalize(text: str) -> str:
    """Remove extra spaces between single characters (e.g. 'C O N T E N T S' → 'CONTENTS')."""
    # Collapse spaced-out single characters: "C O N T E N T S" → "CONTENTS"
    collapsed = re.sub(r"(?<!\w)(\w) (?=\w |\w$)", r"\1", text)
    return collapsed.strip().lower()


def is_educational_chunk(text: str) -> bool:
    """
    Determine if a text block (page or chunk) contains meaningful testable content.

    Returns False if:
    1. Empty or fewer than 20 words.
    2. First 5 non-empty lines match known skip headers (including spaced-letter variants).
    3. More than 60% of lines are very short (≤ 3 words) — catches TOC/Index patterns.
    4. Contains known meta-document phrases (copyright, ISBN, etc.).

    Args:
        text: The text to evaluate.

    Returns:
        True if the chunk should be sent to the LLM, False otherwise.
    """
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    # Heuristic 1: Check first 5 lines against skip headers
    # Handles both normal ("CONTENTS") and spaced-letter ("C O N T E N T S") variants
    for line in lines[:5]:
        line_lower = line.lower()
        normalized = _normalize(line)
        # Strip leading digits/bullets then check
        clean_line = re.sub(r"^[\d\.\s\-\|]+", "", line_lower).strip()
        clean_normalized = re.sub(r"^[\d\.\s\-\|]+", "", normalized).strip()
        if (
            line_lower in _SKIP_HEADERS
            or clean_line in _SKIP_HEADERS
            or normalized in _SKIP_HEADERS
            or clean_normalized in _SKIP_HEADERS
        ):
            return False

    # Heuristic 2: Word count floor
    words = text.split()
    total_words = len(words)
    if total_words < 20:
        return False

    # Heuristic 3: Meta-document phrase detection
    text_lower = text.lower()
    for phrase in _SKIP_PHRASES:
        if phrase in text_lower:
            return False

    # Heuristic 4: Line density — if >60% of lines have ≤3 words, it's likely a TOC/Index
    short_lines = sum(1 for line in lines if len(line.split()) <= 3)
    if len(lines) > 5 and (short_lines / len(lines)) > 0.60:
        return False

    return True
