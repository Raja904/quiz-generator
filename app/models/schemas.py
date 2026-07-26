"""
app/models/schemas.py

Pydantic models for request/response validation.

Design note: QuizOptions is kept as a separate model (not inlined into the
route signature) so that additional options — difficulty_mix, question_types,
language, Bloom's taxonomy level — can be added later without changing the
API contract.  All new fields will be optional with sensible defaults.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class DifficultyLevel(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


# ── Question ──────────────────────────────────────────────────────────────────

class QuizQuestion(BaseModel):
    """A single multiple-choice question with metadata."""
    model_config = ConfigDict(from_attributes=True)

    question: str = Field(..., description="The question text.")
    options: Annotated[
        list[str],
        Field(min_length=4, max_length=4, description="Exactly four answer options."),
    ]
    correct_answer: str = Field(
        ..., description="The correct option (must match one of the options exactly)."
    )
    explanation: str = Field(..., description="Brief explanation of the correct answer.")
    difficulty: DifficultyLevel = Field(..., description="Difficulty level of the question.")
    source_chunk: int = Field(..., description="Zero-based index of the source text chunk.")


# ── Quiz sub-response models ───────────────────────────────────────────────────

class PageRangeInfo(BaseModel):
    """The page range that was actually processed."""
    start_page: int
    end_page: int
    selected_pages: int
    pdf_total_pages: int


class ChunkingStats(BaseModel):
    """Adaptive chunking parameters computed for this specific request."""
    total_tokens_in_range: int
    chunk_size: int
    chunk_overlap: int
    num_chunks: int


# ── Top-level responses ────────────────────────────────────────────────────────

class QuizResponse(BaseModel):
    """Top-level response returned by POST /generate-quiz."""

    id: UUID = Field(
        ..., description="The unique ID of the generated quiz in the database."
    )
    questions: list[QuizQuestion]
    requested_questions: int = Field(
        ..., description="Number of questions the user asked for."
    )
    generated_questions: int = Field(
        ..., description="Number of questions actually returned."
    )
    page_range: PageRangeInfo
    chunking_stats: ChunkingStats
    warning: str | None = Field(
        default=None,
        description=(
            "Set when generated_questions < requested_questions after all retries. "
            "Null in the normal case."
        ),
    )


class PDFInfoResponse(BaseModel):
    """
    Response returned by POST /pdf-info.

    Lets the frontend display total pages, estimate processing load, and
    compute which question-count options are valid for the selected range
    before the user submits the full generate-quiz request.
    """
    filename: str
    page_count: int
    estimated_tokens: int
    max_questions_allowed: int = Field(
        ...,
        description=(
            "Largest allowed question count given the full document "
            "(= min(page_count × 2.5, 150))."
        ),
    )
    allowed_question_counts: list[int] = Field(
        ...,
        description="The complete set of accepted question-count values.",
    )


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str
    version: str


# ── DB Fetch Responses ────────────────────────────────────────────────────────

class QuizListItem(BaseModel):
    """A summary of a quiz for listing past generations."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    total_questions: int
    created_at: datetime
    llm_model: str


class QuizzesResponse(BaseModel):
    """Response for GET /quizzes."""
    quizzes: list[QuizListItem]


class QuizDetailResponse(BaseModel):
    """Response for GET /quizzes/{quiz_id}."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    total_questions: int
    created_at: datetime
    llm_model: str
    questions: list[QuizQuestion]

# ── User model (minimal — only identity fields) ────────────────────────────────

class User(BaseModel):
    """
    Minimal user record.

    Only the fields needed to uniquely identify a user and associate quizzes
    with their account.  No profile picture, phone number, or address.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    created_at: datetime
    last_login: datetime | None = None
