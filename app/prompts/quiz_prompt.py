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
You are an expert assessment generator.

Generate accurate multiple-choice questions strictly from the supplied text.

Always return valid JSON.
Never use outside knowledge.
Never mention the document.
Each question must have exactly one correct answer.\
""".strip()

_USER_PROMPT_TEMPLATE = """\
Generate at most {num_questions} high-quality MCQs. Only generate fewer if the chunk genuinely lacks sufficient testable facts or concepts.

Requirements:
- Standalone questions (no phrases like "According to the text").
- Exactly one objectively correct answer.
- Ensure every incorrect option is unambiguously incorrect.
- Never generate options where multiple answers could reasonably be considered correct.
- Four options.
- Plausible distractors that belong to the same category as the correct answer and are realistic enough to test understanding.
- Every question must be answerable solely from the provided text.
- Do not use outside knowledge or infer information not explicitly supported by the text.
- Do not ask about chapter numbers, page numbers, figure numbers, table numbers, or section titles.
- Do NOT ask meta-questions about the document itself (e.g., "What is the primary focus of this document?", "What is in the contents section?").
- If the provided chunk genuinely contains no testable facts or concepts, return an empty JSON array []. Do not create filler questions.

Output JSON with:
  "question"       – the question text (string)
  "options"        – a JSON array of exactly 4 distinct answer choices (strings)
  "correct_answer" – the correct choice, which MUST exactly match one element of "options"
  "explanation"    – a concise 1-2 sentence explanation
  "difficulty"     – one of: "easy", "medium", "hard"

Return ONLY a valid JSON array.
Do not return markdown, code fences, or any additional text.

TEXT:
{chunk_text}\
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
        chunk_text=chunk_text,
    )
    if is_topup:
        base += _TOPUP_SUFFIX.format(num_questions=num_questions)
    return base
