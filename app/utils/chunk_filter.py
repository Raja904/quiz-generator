"""
app/utils/chunk_filter.py

Heuristic-based filter to determine if a chunk of text contains educational prose
worth sending to the LLM. Discards Table of Contents, References, Index, and
sparse text chunks.
"""

from __future__ import annotations

import re

# Common headers for non-educational sections
_SKIP_HEADERS = {
    "table of contents",
    "contents",
    "preface",
    "acknowledgements",
    "index",
    "references",
    "bibliography",
    "glossary",
}

def is_educational_chunk(text: str) -> bool:
    """
    Determine if a chunk of text contains meaningful educational prose.
    
    Returns False if:
    1. The chunk has < 20 words.
    2. The first non-empty line exactly matches a known skip-header.
    3. The chunk is too sparse (average words per line < 5), typical of TOCs or Indexes.
    
    Args:
        text: The chunk text.
        
    Returns:
        True if the chunk should be sent to the LLM, False otherwise.
    """
    if not text:
        return False
        
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    # Heuristic 1: Check first line against skip headers
    first_line_lower = lines[0].lower()
    
    # Strip common numbering/punctuation (e.g. "1. Table of Contents" -> "table of contents")
    clean_first_line = re.sub(r"^[\d\.\s\-]+", "", first_line_lower).strip()
    
    if clean_first_line in _SKIP_HEADERS or first_line_lower in _SKIP_HEADERS:
        return False

    # Calculate word statistics
    words = text.split()
    total_words = len(words)
    
    # Heuristic 2: Length
    if total_words < 20:
        return False
        
    # Heuristic 3: Prose Density (Average words per line)
    # A normal paragraph has 10+ words per line.
    # TOCs and Indexes usually have very short lines with page numbers.
    avg_words_per_line = total_words / len(lines)
    if avg_words_per_line < 5:
        return False

    return True
