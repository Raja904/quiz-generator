"""
app/prompts/quiz_prompt.py

LLM prompt templates for quiz question generation.

Two modes:
  - Normal    : standard initial generation for a chunk.
  - Top-up    : supplementary pass on a chunk that underdelivered, asking the
                LLM to generate NEW questions not yet covered.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are an expert educational content creator specialising in generating \
high-quality multiple-choice quiz questions from academic and technical material.

Your output MUST be valid JSON — a JSON array of question objects.
Do NOT include any markdown fences, prose, or commentary outside the JSON array.\
""".strip()

_USER_PROMPT_TEMPLATE = """\
Generate exactly {num_questions} multiple-choice quiz questions based on the \
text excerpt below. Include a mix of:
  - Conceptual questions (testing understanding of key ideas)
  - Factual questions (testing recall of specific information)
  - Application-based questions (testing the ability to apply concepts)

For each question produce an object with these exact keys:
  "question"       – the question text (string)
  "options"        – a JSON array of exactly 4 distinct answer choices (strings)
  "correct_answer" – the correct choice, which MUST exactly match one element of "options"
  "explanation"    – a concise 1–3 sentence explanation of why the answer is correct
  "difficulty"     – one of: "easy", "medium", "hard"
  "source_chunk"   – the integer {chunk_index}

Return ONLY the JSON array. No extra text.

--- TEXT EXCERPT ---
{chunk_text}
--- END EXCERPT ---\
""".strip()

_TOPUP_SUFFIX = """

IMPORTANT — SUPPLEMENTARY GENERATION:
A previous pass on this same text excerpt already produced some questions.
You MUST generate {num_questions} ADDITIONAL questions that cover different
aspects, angles, or details from the text.  Do not repeat topics already
tested.  Focus on parts of the excerpt not yet examined."""


def build_user_prompt(
    chunk_text: str,
    chunk_index: int,
    num_questions: int,
    is_topup: bool = False,
) -> str:
    """
    Render the user-facing prompt for a single chunk.

    Args:
        chunk_text:    The text excerpt for this chunk.
        chunk_index:   Zero-based chunk index (embedded in each question).
        num_questions: Number of questions to request.
        is_topup:      When ``True``, appends a note asking the LLM to generate
                       NEW questions not covered by a prior call on this chunk.
    """
    base = _USER_PROMPT_TEMPLATE.format(
        num_questions=num_questions,
        chunk_index=chunk_index,
        chunk_text=chunk_text,
    )
    if is_topup:
        base += _TOPUP_SUFFIX.format(num_questions=num_questions)
    return base
