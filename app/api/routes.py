"""
app/api/routes.py

FastAPI route definitions:
  POST /pdf-info       — Upload PDF, get page count + token estimate (no LLM call)
  POST /generate-quiz  — Upload PDF with options → quiz JSON
  GET  /health         — Liveness check
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.deps import DbSession, get_current_user
from app.core.config import settings
from app.db.models import User
from app.repositories.quiz_repo import QuizRepository
from app.models.schemas import HealthResponse, PDFInfoResponse, QuizResponse, QuizzesResponse, QuizDetailResponse, QuizListItem
from app.parsers.pdf_parser import PDFParseError, parse_pdf
from app.services.quiz_service import generate_quiz
from uuid import UUID
from app.utils.adaptive_chunker import count_tokens
from app.utils.text_cleaner import clean_text
from app.utils.validators import (
    ALLOWED_QUESTION_COUNTS,
    max_questions_for_pages,
    validate_question_count,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "binary/octet-stream",  # some clients send this for PDFs
}


def _assert_pdf(file: UploadFile) -> None:
    """Raise HTTP 400 if the uploaded file does not look like a PDF."""
    if file.content_type and file.content_type not in _SUPPORTED_CONTENT_TYPES:
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported file type '{file.content_type}'. "
                    "Only PDF files are accepted."
                ),
            )


# ── GET /health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check(db: DbSession = None) -> HealthResponse:
    """Returns the API health status and checks DB connection."""
    db_status = "ok"
    try:
        if db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    if db_status == "error":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )

    return HealthResponse(
        status="ok",
        version=settings.app_version,
    )


# ── POST /pdf-info ────────────────────────────────────────────────────────────

@router.post(
    "/pdf-info",
    response_model=PDFInfoResponse,
    summary="Inspect a PDF without generating a quiz",
    tags=["PDF"],
    responses={
        400: {"description": "Invalid or unreadable PDF"},
    },
)
async def pdf_info(
    file: UploadFile = File(..., description="PDF file to inspect"),
    user: User = Depends(get_current_user),
) -> PDFInfoResponse:
    """
    Upload a PDF and receive its basic metadata:
    - Total page count.
    - Estimated token count (for the full document).
    - Maximum questions allowed (based on full page count).
    - The list of valid question-count options.

    **No LLM call is made.**  This endpoint is intended to power the frontend
    page-range / question-count selection UI before the user submits a quiz
    generation request.
    """
    _assert_pdf(file)

    logger.info(
        "pdf-info | filename=%s content_type=%s", file.filename, file.content_type
    )

    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # ── Fast metadata extraction (no full text parse) ─────────────────────────
    # We only need page count + a rough token estimate.
    # Sampling up to 5 pages is sufficient for estimation and is nearly instant.
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages: int = len(doc)

        if total_pages == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF contains no pages.",
            )

        # Sample up to 5 evenly-spaced pages to estimate token density
        sample_indices = list(
            dict.fromkeys(
                int(i * (total_pages - 1) / max(min(5, total_pages) - 1, 1))
                for i in range(min(5, total_pages))
            )
        )
        sample_text = "\n".join(
            doc[i].get_text("text") for i in sample_indices if i < total_pages
        )
        doc.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read PDF: {exc}",
        ) from exc
    finally:
        del file_bytes

    # Extrapolate full-document token estimate from sampled pages
    sampled_pages = len(sample_indices)
    sample_tokens = count_tokens(clean_text(sample_text))
    estimated_tokens = int(sample_tokens / max(sampled_pages, 1) * total_pages)

    max_q = max_questions_for_pages(
        total_pages,
        allowed_counts=settings.allowed_question_counts,
    )

    logger.info(
        "pdf-info complete | pages=%d  tokens≈%d  max_questions=%d",
        total_pages,
        estimated_tokens,
        max_q,
    )

    return PDFInfoResponse(
        filename=file.filename or "upload.pdf",
        page_count=total_pages,
        estimated_tokens=estimated_tokens,
        max_questions_allowed=max_q,
        allowed_question_counts=settings.allowed_question_counts,
    )


# ── POST /generate-quiz ───────────────────────────────────────────────────────

@router.post(
    "/generate-quiz",
    response_model=QuizResponse,
    summary="Generate a quiz from an uploaded PDF",
    tags=["Quiz"],
    responses={
        400: {"description": "Invalid or unreadable PDF"},
        422: {"description": "Validation error (page range or question count)"},
        500: {"description": "Internal pipeline error"},
    },
)
async def generate_quiz_endpoint(
    file: UploadFile = File(..., description="PDF file to generate quiz from"),
    total_questions: int = Form(
        default=20,
        description=(
            "Total number of questions to generate. "
            f"Allowed values: {ALLOWED_QUESTION_COUNTS}."
        ),
    ),
    start_page: int = Form(
        default=1,
        ge=1,
        description="First page to process (1-indexed, inclusive).",
    ),
    end_page: int | None = Form(
        default=None,
        ge=1,
        description=(
            "Last page to process (1-indexed, inclusive). "
            "Omit to process until the last page of the PDF."
        ),
    ),
    user: User = Depends(get_current_user),
    db: DbSession = None,
) -> QuizResponse:
    """
    Upload a PDF and receive a structured list of multiple-choice questions.

    **Processing flow:**
    1. Extract text only from the selected page range.
    2. Derive chunk size adaptively from token count and requested question count.
    3. Distribute questions evenly across chunks.
    4. Call the LLM per chunk; retry deficient chunks if the total falls short.
    5. Return all validated questions with processing metadata.

    **Validation rules:**
    - `1 ≤ start_page ≤ end_page ≤ total_pages`
    - `end_page − start_page + 1 ≤ 100` (configurable via `MAX_PAGES_PER_REQUEST`)
    - `total_questions` must be one of the allowed values.
    - `total_questions ≤ min(selected_pages × 2.5, 150)`
    """
    _assert_pdf(file)

    # ── Pre-parse validation (fast, no I/O) ───────────────────────────────────
    if total_questions < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="total_questions must be ≥ 1.",
        )
    if start_page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_page must be ≥ 1.",
        )
    if end_page is not None and end_page < start_page:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"end_page ({end_page}) must be ≥ start_page ({start_page}).",
        )

    logger.info(
        "generate-quiz | filename=%s  total_questions=%d  pages=%s–%s",
        file.filename,
        total_questions,
        start_page,
        end_page or "last",
    )

    # ── Read file ─────────────────────────────────────────────────────────────
    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # ── Run pipeline ──────────────────────────────────────────────────────────
    try:
        result = await generate_quiz(
            file_bytes=file_bytes,
            filename=file.filename or "upload.pdf",
            llm_model=settings.llm_model,
            total_questions=total_questions,
            user=user,
            db=db,
            start_page=start_page,
            end_page=end_page,
        )
    except PDFParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        # Validation errors from validators.py (page range, question cap)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.error("Pipeline error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quiz generation failed: {exc}",
        ) from exc

    return result


# ── GET /quizzes ───────────────────────────────────────────────────────────────

@router.get(
    "/quizzes",
    response_model=QuizzesResponse,
    summary="List past quizzes",
    tags=["Quiz"],
)
async def list_quizzes(
    user: User = Depends(get_current_user),
    db: DbSession = None,
) -> QuizzesResponse:
    """Returns a list of all quizzes generated by the authenticated user."""
    quiz_repo = QuizRepository(db)
    rows = await quiz_repo.get_user_quizzes(user.id)

    quizzes = []
    for quiz, filename in rows:
        quizzes.append(
            QuizListItem(
                id=quiz.id,
                filename=filename,
                total_questions=quiz.total_questions,
                created_at=quiz.created_at,
                llm_model=quiz.llm_model,
            )
        )

    return QuizzesResponse(quizzes=quizzes)


# ── GET /quizzes/{quiz_id} ─────────────────────────────────────────────────────

@router.get(
    "/quizzes/{quiz_id}",
    response_model=QuizDetailResponse,
    summary="Get details of a specific quiz",
    tags=["Quiz"],
)
async def get_quiz(
    quiz_id: UUID,
    user: User = Depends(get_current_user),
    db: DbSession = None,
) -> QuizDetailResponse:
    """Returns the full questions and metadata for a specific quiz."""
    quiz_repo = QuizRepository(db)
    quiz = await quiz_repo.get_quiz_with_details(quiz_id, user.id)

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found.",
        )

    return QuizDetailResponse(
        id=quiz.id,
        filename=quiz.pdf_metadata.filename,
        total_questions=quiz.total_questions,
        created_at=quiz.created_at,
        llm_model=quiz.llm_model,
        questions=quiz.questions,  # The SQLAlchemy models map directly to the Pydantic schema here
    )

