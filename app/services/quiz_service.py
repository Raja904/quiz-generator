"""
app/services/quiz_service.py

Orchestrates the full PDF → Clean → Semantic Chunk → Filter → LLM → Validate →
Deduplicate → Trim → (Top-up if needed) → QuizResponse pipeline.

Pipeline steps
--------------
1.  Parse page range   — extract only the user-selected pages (fitz, in-memory)
2.  Free PDF bytes     — del file_bytes immediately after parsing (try/finally)
3.  Validate range     — page range rules + question count cap (post-parse)
4.  Clean & Filter     — normalise text, drop non-educational pages
5.  Count tokens       — tiktoken estimate of total tokens in selected text
6.  Fixed Chunking     — split on paragraph/sentence boundaries (fixed size, NOT question-count-driven)
7.  Filter Chunks      — drop non-educational chunks before any LLM call
8.  Compute QPQ        — questions_per_chunk = clamp(ceil(total_q / n_chunks), 2, 5)
9.  Initial LLM pass   — call LLM concurrently, ask each chunk for QPQ questions
10. Post-Validate      — validate, reject bad questions (missing fields, banned phrases, duplicate options)
11. Deduplicate        — remove duplicate questions
12. Trim               — slice exactly total_questions (over-generation trimmed here)
13. Top-up pass        — only if len(result) < total_questions after trim
14. Save & Return      — persist to DB, return QuizResponse

No data is written to disk.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from math import ceil
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import User
from app.repositories.quiz_repo import QuizRepository
from app.llm.llm_client import LLMCallRecord, acall_llm
from app.models.schemas import (
    ChunkingStats,
    DifficultyLevel,
    PageRangeInfo,
    QuizQuestion,
    QuizResponse,
)
from app.parsers.pdf_parser import ParseResult, PDFParseError, parse_pdf_range
from app.prompts.quiz_prompt import SYSTEM_PROMPT, build_user_prompt
from app.utils.adaptive_chunker import count_tokens
from app.utils.chunker import TextChunk, chunk_text
from app.utils.chunk_filter import is_educational_chunk
from app.utils.text_cleaner import clean_text
from app.utils.deduplicator import deduplicate_questions
from app.utils.validators import validate_page_range, validate_question_count

logger = logging.getLogger(__name__)

_MAX_TOPUP_ROUNDS = 2  # maximum top-up passes

# Phrases that should disqualify a question (document-referencing language)
_BANNED_PHRASES = [
    "according to the text",
    "according to the document",
    "according to the passage",
    "based on the pdf",
    "based on the text",
    "based on the document",
    "as mentioned above",
    "as stated in",
    "the text states",
    "the passage states",
]


# ── LangSmith tracing ─────────────────────────────────────────────────────────

def _traceable(func):
    """Wrap *func* with langsmith.traceable if tracing is enabled."""
    import os  # noqa: PLC0415
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        try:
            from langsmith import traceable  # noqa: PLC0415
            return traceable(name=func.__name__)(func)
        except ImportError:
            pass
    return func


# ── Question validation ────────────────────────────────────────────────────────

def _validate_question(raw: dict, chunk_index: int) -> QuizQuestion | None:
    """
    Coerce a raw LLM dict into a QuizQuestion with full post-validation.
    Returns None if the question fails any validation check.
    """
    try:
        raw["source_chunk"] = chunk_index
        if "difficulty" in raw:
            raw["difficulty"] = str(raw["difficulty"]).lower()

        question = QuizQuestion(**raw)

        # Check: question text is non-empty
        if not question.question or not question.question.strip():
            logger.warning("chunk[%d]: Empty question text — skipping.", chunk_index)
            return None

        # Check: explanation is non-empty
        if not question.explanation or not question.explanation.strip():
            logger.warning("chunk[%d]: Missing explanation — skipping.", chunk_index)
            return None

        # Check: exactly 4 options
        if len(question.options) != 4:
            logger.warning(
                "chunk[%d]: Expected 4 options, got %d — skipping.",
                chunk_index, len(question.options),
            )
            return None

        # Check: all 4 options are unique (case-insensitive)
        normalized_opts = [o.strip().lower() for o in question.options]
        if len(set(normalized_opts)) != 4:
            logger.warning(
                "chunk[%d]: Duplicate options detected — skipping.", chunk_index
            )
            return None

        # Check: correct_answer exists in options
        if question.correct_answer not in question.options:
            logger.warning(
                "chunk[%d]: correct_answer %r not in options %s — skipping.",
                chunk_index,
                question.correct_answer,
                question.options,
            )
            return None

        # Check: question does not contain banned document-referencing phrases
        q_lower = question.question.lower()
        for phrase in _BANNED_PHRASES:
            if phrase in q_lower:
                logger.warning(
                    "chunk[%d]: Banned phrase %r detected — skipping.", chunk_index, phrase
                )
                return None

        # Shuffle options so the correct answer isn't always at the same position
        random.shuffle(question.options)

        return question

    except Exception as exc:
        logger.warning(
            "chunk[%d]: Failed to parse question: %s | raw=%s",
            chunk_index,
            exc,
            raw,
        )
        return None


# ── Per-chunk LLM call ─────────────────────────────────────────────────────────

async def _acall_chunk(
    chunk: TextChunk,
    num_questions: int,
    llm_model: str,
    semaphore: asyncio.Semaphore,
    is_topup: bool = False,
) -> list[QuizQuestion]:
    """Call the LLM for one chunk concurrently and return validated questions."""
    user_prompt = build_user_prompt(
        chunk_text=chunk.text,
        chunk_index=chunk.index,
        num_questions=num_questions,
        is_topup=is_topup,
    )

    async with semaphore:
        record: LLMCallRecord = await acall_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=llm_model,
            chunk_index=chunk.index,
        )

    validated: list[QuizQuestion] = []
    if record.success:
        for raw in record.parsed_questions:
            if isinstance(raw, dict):
                q = _validate_question(raw, chunk.index)
                if q:
                    validated.append(q)

    logger.info(
        "chunk[%d] %s| valid=%d/%d  llm_tokens=%d  latency=%.3fs",
        chunk.index,
        "(topup) " if is_topup else "",
        len(validated),
        len(record.parsed_questions) if record.success else 0,
        record.tokens_used,
        record.latency_seconds,
    )
    return validated


# ── Shortfall top-up ──────────────────────────────────────────────────────────

@dataclass
class _ChunkResult:
    chunk: TextChunk
    assigned: int
    questions: list[QuizQuestion] = field(default_factory=list)

    @property
    def deficit(self) -> int:
        return max(0, self.assigned - len(self.questions))


async def _atopup(
    results: list[_ChunkResult],
    llm_model: str,
    semaphore: asyncio.Semaphore,
    remaining_deficit: int,
) -> list[QuizQuestion]:
    """
    Make up to _MAX_TOPUP_ROUNDS passes over chunks that produced good questions,
    asking each one for more to fill the remaining deficit.
    """
    extra: list[QuizQuestion] = []

    # Only top-up from chunks that already produced at least 1 valid question
    # (chunks that produced 0 are likely non-educational — skip them)
    productive_chunks = [r for r in results if len(r.questions) > 0]
    if not productive_chunks:
        # Fall back to all chunks if none were productive
        productive_chunks = results

    for round_num in range(1, _MAX_TOPUP_ROUNDS + 1):
        if remaining_deficit <= 0:
            break

        logger.info(
            "Top-up round %d/%d | deficit=%d across %d productive chunk(s)",
            round_num,
            _MAX_TOPUP_ROUNDS,
            remaining_deficit,
            len(productive_chunks),
        )

        tasks = []
        task_res_map = []

        for res in productive_chunks:
            if remaining_deficit <= 0:
                break
            need = min(settings.max_questions_per_chunk, remaining_deficit)
            tasks.append(_acall_chunk(
                chunk=res.chunk,
                num_questions=need,
                llm_model=llm_model,
                semaphore=semaphore,
                is_topup=True,
            ))
            task_res_map.append((res, need))
            remaining_deficit -= need

        round_results = await asyncio.gather(*tasks)

        for (res, _), new_questions in zip(task_res_map, round_results):
            res.questions.extend(new_questions)
            extra.extend(new_questions)

    return extra


# ── Main pipeline ─────────────────────────────────────────────────────────────

@_traceable
async def generate_quiz(
    file_bytes: bytes,
    filename: str,
    llm_model: str,
    total_questions: int,
    user: User,
    db: AsyncSession,
    start_page: int = 1,
    end_page: int | None = None,
) -> QuizResponse:
    """
    Run the full quiz generation pipeline.

    Args:
        file_bytes:       Raw bytes of the uploaded PDF.
        filename:         Original filename (for logging/metadata only).
        llm_model:        LiteLLM model string.
        total_questions:  Number of questions to generate.
        start_page:       1-indexed inclusive start page (default: 1).
        end_page:         1-indexed inclusive end page (default: last page).

    Returns:
        :class:`QuizResponse` with all validated questions and metadata.
    """
    pipeline_start = time.perf_counter()
    logger.info("=== Pipeline START | file=%s ===", filename)

    # ── Step 1 & 2: Parse selected pages, then immediately free raw bytes ──────
    parse_result: ParseResult
    try:
        parse_result = parse_pdf_range(
            file_bytes,
            filename,
            start_page=start_page,
            end_page=end_page,
        )
    finally:
        del file_bytes

    effective_end = end_page if end_page is not None else parse_result.total_pages
    selected_pages = effective_end - start_page + 1

    logger.info(
        "Parsed | pages=%d–%d (%d pages)  total_in_doc=%d  parse_time=%.3fs",
        start_page,
        effective_end,
        selected_pages,
        parse_result.total_pages,
        parse_result.parse_time_seconds,
    )

    # ── Step 3: Validate (post-parse) ─────────────────────────────────────────
    validate_page_range(
        start_page=start_page,
        end_page=effective_end,
        total_pages=parse_result.total_pages,
        max_pages=settings.max_pages_per_request,
    )
    validate_question_count(
        total_questions=total_questions,
        selected_pages=selected_pages,
        allowed_counts=settings.allowed_question_counts,
    )

    # ── Step 4: Clean & Filter Pages ──────────────────────────────────────────
    # Filter non-educational pages BEFORE chunking to keep chunks clean.
    educational_pages = []
    for page_text in parse_result.pages:
        cleaned_page = clean_text(page_text)
        if is_educational_chunk(cleaned_page):
            educational_pages.append(cleaned_page)

    if not educational_pages:
        raise RuntimeError(
            "No educational content found after filtering pages "
            "(e.g. Table of Contents, Index)."
        )

    cleaned = "\n\n".join(educational_pages)
    logger.info(
        "Cleaned & Filtered | chars=%d  pages_retained=%d/%d",
        len(cleaned), len(educational_pages), len(parse_result.pages)
    )

    # ── Step 5: Count tokens ───────────────────────────────────────────────────
    total_tokens = count_tokens(cleaned)
    logger.info("Token count | tokens=%d", total_tokens)

    # ── Step 6: Fixed Semantic Chunking ───────────────────────────────────────
    # Chunk size is DOCUMENT-DRIVEN, NOT question-count-driven.
    chunks: list[TextChunk] = chunk_text(
        cleaned,
        chunk_size=settings.preferred_chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        raise RuntimeError("No text chunks were produced. Cannot generate quiz.")

    logger.info(
        "Chunked | num_chunks=%d  chunk_size=%d  chunk_overlap=%d",
        len(chunks), settings.preferred_chunk_size, settings.chunk_overlap,
    )

    # ── Step 7: Filter non-educational chunks BEFORE LLM calls ───────────────
    valid_chunks = [c for c in chunks if is_educational_chunk(c.text)]
    skipped = len(chunks) - len(valid_chunks)
    if skipped:
        logger.info("Chunk filter | skipped=%d non-educational chunk(s)", skipped)

    if not valid_chunks:
        raise RuntimeError(
            "All chunks were filtered out as non-educational. "
            "Try selecting a different page range."
        )

    # ── Step 8: Compute questions per chunk ────────────────────────────────────
    # Over-generate intentionally: ask for enough per chunk so total > requested.
    # Then trim after deduplication.
    questions_per_chunk = ceil(total_questions / len(valid_chunks))
    questions_per_chunk = max(settings.min_questions_per_chunk,
                              min(questions_per_chunk, settings.max_questions_per_chunk))

    logger.info(
        "Generation plan | valid_chunks=%d  questions_per_chunk=%d  "
        "expected_generated≈%d  requested=%d",
        len(valid_chunks),
        questions_per_chunk,
        questions_per_chunk * len(valid_chunks),
        total_questions,
    )

    # ── Step 9: Initial LLM pass (Concurrent) ─────────────────────────────────
    semaphore = asyncio.Semaphore(3)  # max 3 concurrent LLM calls to avoid rate-limiting/freeze
    tasks = [
        _acall_chunk(
            chunk=chunk,
            num_questions=questions_per_chunk,
            llm_model=llm_model,
            semaphore=semaphore,
        )
        for chunk in valid_chunks
    ]

    chunk_responses = await asyncio.gather(*tasks)

    results: list[_ChunkResult] = []
    for chunk, questions in zip(valid_chunks, chunk_responses):
        results.append(_ChunkResult(
            chunk=chunk,
            assigned=questions_per_chunk,
            questions=questions,
        ))

    all_questions: list[QuizQuestion] = [q for r in results for q in r.questions]

    logger.info(
        "Initial pass complete | generated=%d  (requested=%d per run on %d chunks)",
        len(all_questions), questions_per_chunk, len(valid_chunks),
    )

    # ── Step 10 & 11: Deduplicate ──────────────────────────────────────────────
    all_questions = deduplicate_questions(all_questions)
    logger.info("After dedup | questions=%d", len(all_questions))

    # ── Step 12: Trim to exactly the requested count ───────────────────────────
    if len(all_questions) >= total_questions:
        final_questions = all_questions[:total_questions]
        logger.info(
            "Trimmed | generated=%d  returned=%d",
            len(all_questions), len(final_questions),
        )
        warning = None
    else:
        # ── Step 13: Top-up — only fired if we're still short after trim ──────
        deficit = total_questions - len(all_questions)
        logger.info(
            "Shortfall detected | have=%d  need=%d  starting top-up",
            len(all_questions), total_questions,
        )
        extra = await _atopup(
            results,
            llm_model=llm_model,
            semaphore=semaphore,
            remaining_deficit=deficit,
        )
        all_questions.extend(extra)
        all_questions = deduplicate_questions(all_questions)
        final_questions = all_questions[:total_questions]

        final_deficit = total_questions - len(final_questions)
        warning = None
        if final_deficit > 0:
            warning = (
                f"Unable to generate {final_deficit} of the requested {total_questions} "
                f"question(s) after {_MAX_TOPUP_ROUNDS} top-up round(s). "
                f"Returning {len(final_questions)} question(s)."
            )
            logger.warning(warning)

    if not final_questions:
        raise RuntimeError(
            "Failed to generate any valid questions from the provided text. "
            "The AI model may have returned invalid responses, or the text might be too short."
        )

    # ── Step 14: Save to Database ──────────────────────────────────────────────
    quiz_repo = QuizRepository(db)
    db_metadata, db_quiz = await quiz_repo.save_quiz_results(
        user_id=user.id,
        filename=filename,
        total_pages=parse_result.total_pages,
        total_tokens=total_tokens,
        llm_model=llm_model,
        requested_questions=total_questions,
        final_generated=len(final_questions),
        all_questions=final_questions,
    )

    # ── Step 15: Build and return response ─────────────────────────────────────
    total_time = time.perf_counter() - pipeline_start

    logger.info(
        "=== Pipeline DONE | questions=%d/%d  chunks=%d  time=%.3fs ===",
        len(final_questions),
        total_questions,
        len(valid_chunks),
        total_time,
    )

    return QuizResponse(
        id=db_quiz.id,
        questions=final_questions,
        requested_questions=total_questions,
        generated_questions=len(final_questions),
        page_range=PageRangeInfo(
            start_page=start_page,
            end_page=effective_end,
            selected_pages=selected_pages,
            pdf_total_pages=parse_result.total_pages,
        ),
        chunking_stats=ChunkingStats(
            total_tokens_in_range=total_tokens,
            chunk_size=settings.preferred_chunk_size,
            chunk_overlap=settings.chunk_overlap,
            num_chunks=len(valid_chunks),
        ),
        warning=warning,
    )
