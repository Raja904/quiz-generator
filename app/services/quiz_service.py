"""
app/services/quiz_service.py

Orchestrates the full PDF → Range Extract → Clean → Adaptive Chunk → LLM → Quiz pipeline.

Pipeline steps
--------------
1.  Parse page range   — extract only the user-selected pages (fitz, in-memory)
2.  Free PDF bytes     — del file_bytes immediately after parsing (try/finally)
3.  Validate range     — page range rules + question count cap (post-parse)
4.  Clean text         — normalise whitespace, ligatures, control chars
5.  Count tokens       — tiktoken estimate of total tokens in selected text
6.  Adaptive params    — derive chunk_size & overlap from token count + question count
7.  Chunk              — split cleaned text into overlapping token-aware chunks
8.  Distribute         — allocate per-chunk question counts that sum to total_questions
9.  Initial LLM pass   — call LLM per chunk, validate each response
10. Shortfall check    — identify chunks that underdelivered
11. Top-up pass        — re-call only the deficient chunks (max 2 rounds)
12. Final warning      — if still short after top-up, surface a warning in the response
13. Return QuizResponse

No data is written to disk.  The runs/ directory has been removed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
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
from app.utils.adaptive_chunker import (
    compute_chunk_params,
    count_tokens,
    distribute_questions,
)
from app.utils.chunker import TextChunk, chunk_text
from app.utils.chunk_filter import is_educational_chunk
from app.utils.text_cleaner import clean_text
from app.utils.deduplicator import deduplicate_questions
from app.utils.validators import validate_page_range, validate_question_count

logger = logging.getLogger(__name__)

_MAX_TOPUP_ROUNDS = 2  # maximum top-up passes over deficient chunks


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
    """Coerce a raw LLM dict into a QuizQuestion.  Returns None if invalid."""
    try:
        raw["source_chunk"] = chunk_index
        if "difficulty" in raw:
            raw["difficulty"] = str(raw["difficulty"]).lower()

        question = QuizQuestion(**raw)

        if question.correct_answer not in question.options:
            logger.warning(
                "chunk[%d]: correct_answer %r not in options %s — skipping.",
                chunk_index,
                question.correct_answer,
                question.options,
            )
            return None

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
    """
    Call the LLM for one chunk concurrently and return validated questions.

    The llm_client already retries on transient errors / JSON parse failures
    (MAX_RETRIES = 2 attempts before marking the call failed).
    """
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
    Make up to _MAX_TOPUP_ROUNDS passes over deficient chunks, asking each one
    for exactly the number of questions it still owes.

    Returns a flat list of additional validated questions.
    """
    extra: list[QuizQuestion] = []

    for round_num in range(1, _MAX_TOPUP_ROUNDS + 1):
        if remaining_deficit <= 0:
            break

        deficient = [r for r in results if r.deficit > 0]
        if not deficient:
            break

        logger.info(
            "Top-up round %d/%d | deficit=%d across %d chunk(s)",
            round_num,
            _MAX_TOPUP_ROUNDS,
            remaining_deficit,
            len(deficient),
        )

        # Build tasks to run concurrently in this round
        tasks = []
        task_res_map = []

        for res in deficient:
            if remaining_deficit <= 0:
                break
            need = min(res.deficit, remaining_deficit)
            tasks.append(_acall_chunk(
                chunk=res.chunk,
                num_questions=need,
                llm_model=llm_model,
                semaphore=semaphore,
                is_topup=True,
            ))
            task_res_map.append((res, need))
            remaining_deficit -= need

        # Wait for all top-up requests in this round
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

    Raises:
        PDFParseError:  For unreadable or image-only PDFs.
        ValueError:     For invalid page ranges or question counts (→ HTTP 422).
        RuntimeError:   For unexpected pipeline failures.
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
        del file_bytes  # release memory regardless of success or error

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

    # ── Step 3: Validate (post-parse, because we now know total_pages) ─────────
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

    # ── Step 4: Clean & Pre-filter Pages ───────────────────────────────────────
    # We clean and filter each page BEFORE combining them to prevent a dense page
    # from artificially saving a sparse Table of Contents page when chunked.
    educational_pages = []
    for page_text in parse_result.pages:
        cleaned_page = clean_text(page_text)
        if is_educational_chunk(cleaned_page):
            educational_pages.append(cleaned_page)
            
    if not educational_pages:
        raise RuntimeError("No educational content found after filtering pages (e.g. Table of Contents, Index).")
        
    cleaned = "\n\n".join(educational_pages)
    logger.info("Cleaned & Filtered | chars=%d  pages_retained=%d/%d", len(cleaned), len(educational_pages), len(parse_result.pages))

    # ── Step 5: Count tokens ───────────────────────────────────────────────────
    total_tokens = count_tokens(cleaned)
    logger.info("Token count | tokens=%d", total_tokens)

    # ── Step 6: Adaptive chunk parameters ─────────────────────────────────────
    chunk_size, chunk_overlap = compute_chunk_params(
        total_tokens=total_tokens,
        total_questions=total_questions,
        min_chunk_size=settings.min_chunk_size,
        max_chunk_size=settings.max_chunk_size,
        overlap_ratio=settings.chunk_overlap_ratio,
    )
    logger.info(
        "Adaptive params | chunk_size=%d  chunk_overlap=%d",
        chunk_size,
        chunk_overlap,
    )

    # ── Step 7: Chunk ──────────────────────────────────────────────────────────
    chunks: list[TextChunk] = chunk_text(
        cleaned, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    if not chunks:
        raise RuntimeError("No text chunks were produced. Cannot generate quiz.")

    logger.info("Chunked | num_chunks=%d", len(chunks))

    # ── Step 8: Distribute questions per chunk ─────────────────────────────────
    q_per_chunk: list[int] = distribute_questions(len(chunks), total_questions)
    logger.info("Question distribution: %s (sum=%d)", q_per_chunk, sum(q_per_chunk))

    # ── Step 9: Initial LLM pass (Concurrent) ──────────────────────────────────
    results: list[_ChunkResult] = []
    
    semaphore = asyncio.Semaphore(5)
    tasks = []
    
    for chunk, n_q in zip(chunks, q_per_chunk):
        logger.info(
            "LLM call setup | chunk[%d]  tokens=%d  questions_requested=%d",
            chunk.index,
            chunk.token_count,
            n_q,
        )
        tasks.append(_acall_chunk(chunk, num_questions=n_q, llm_model=llm_model, semaphore=semaphore))
        
    chunk_responses = await asyncio.gather(*tasks)
    
    for chunk, n_q, questions in zip(chunks, q_per_chunk, chunk_responses):
        results.append(_ChunkResult(chunk=chunk, assigned=n_q, questions=questions))

    all_questions: list[QuizQuestion] = [q for r in results for q in r.questions]
    
    # ── Step 9b: Deduplicate Questions ─────────────────────────────────────────
    all_questions = deduplicate_questions(all_questions)

    initial_generated = len(all_questions)
    initial_deficit = total_questions - initial_generated

    logger.info(
        "Initial pass complete | generated=%d/%d  deficit=%d",
        initial_generated,
        total_questions,
        initial_deficit,
    )

    # ── Steps 10 & 11: Shortfall detection + top-up ────────────────────────────
    warning: str | None = None

    if initial_deficit > 0:
        logger.info("Shortfall detected — starting top-up pass(es).")
        extra = await _atopup(results, llm_model=llm_model, semaphore=semaphore, remaining_deficit=initial_deficit)
        all_questions.extend(extra)
        
        # Deduplicate again after top-up just in case
        all_questions = deduplicate_questions(all_questions)

    final_generated = len(all_questions)
    final_deficit = total_questions - final_generated

    if final_generated == 0:
        raise RuntimeError(
            "Failed to generate any valid questions from the provided text. "
            "The AI model may have returned invalid responses, or the text might be too short."
        )

    if final_deficit > 0:
        warning = (
            f"Unable to generate {final_deficit} of the requested {total_questions} "
            f"question(s) after {_MAX_TOPUP_ROUNDS} top-up round(s). "
            f"Returning {final_generated} question(s)."
        )
        logger.warning(warning)

    # ── Step 13: Save to Database ──────────────────────────────────────────────
    quiz_repo = QuizRepository(db)
    db_metadata, db_quiz = await quiz_repo.save_quiz_results(
        user_id=user.id,
        filename=filename,
        total_pages=parse_result.total_pages,
        total_tokens=total_tokens,
        llm_model=llm_model,
        final_generated=final_generated,
        all_questions=all_questions,
    )

    # ── Step 14: Build and return response ─────────────────────────────────────
    total_time = time.perf_counter() - pipeline_start

    logger.info(
        "=== Pipeline DONE | questions=%d/%d  chunks=%d  time=%.3fs ===",
        final_generated,
        total_questions,
        len(chunks),
        total_time,
    )

    return QuizResponse(
        id=db_quiz.id,
        questions=all_questions,
        requested_questions=total_questions,
        generated_questions=final_generated,
        page_range=PageRangeInfo(
            start_page=start_page,
            end_page=effective_end,
            selected_pages=selected_pages,
            pdf_total_pages=parse_result.total_pages,
        ),
        chunking_stats=ChunkingStats(
            total_tokens_in_range=total_tokens,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            num_chunks=len(chunks),
        ),
        warning=warning,
    )
