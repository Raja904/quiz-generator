"""
app/utils/text_cleaner.py

Cleans raw extracted PDF text:
  - Collapses excessive blank lines
  - Normalises whitespace within lines
  - Removes null bytes and control characters
  - Fixes common ligature/encoding artifacts
"""

from __future__ import annotations

import re
import unicodedata


# Ligature / encoding artifact replacements common in PDFs
_LIGATURE_MAP: dict[str, str] = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb06": "st",
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u00ad": "",   # soft hyphen
}

_LIGATURE_RE = re.compile("|".join(re.escape(k) for k in _LIGATURE_MAP))


def _replace_ligatures(text: str) -> str:
    return _LIGATURE_RE.sub(lambda m: _LIGATURE_MAP[m.group()], text)


def clean_text(text: str) -> str:
    """
    Clean raw PDF-extracted text for downstream chunking and LLM processing.

    Steps applied (in order):
    1. Replace ligatures and typographic characters.
    2. Normalise Unicode to NFC.
    3. Strip null bytes and non-printable control characters (except \\n, \\t).
    4. Normalise internal whitespace within each line.
    5. Collapse runs of 3+ blank lines down to 2 blank lines.
    6. Strip leading/trailing whitespace from the whole document.

    Args:
        text: Raw text from the PDF parser.

    Returns:
        Cleaned text string.
    """
    if not text:
        return text

    # 1. Ligature / encoding fixes
    text = _replace_ligatures(text)

    # 2. Unicode normalisation
    text = unicodedata.normalize("NFC", text)

    # 3. Remove null bytes and control chars (keep \n, \r, \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # 4. Normalise internal whitespace within lines (collapse multiple spaces/tabs)
    lines = text.splitlines()
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in lines]
    text = "\n".join(lines)

    # 5. Collapse 3+ consecutive blank lines → 2 blank lines (preserve paragraph breaks)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 6. Strip overall
    return text.strip()
