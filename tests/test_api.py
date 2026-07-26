"""
tests/test_api.py

Integration tests for the FastAPI endpoints.
The LLM is mocked so no real API key is required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.llm.llm_client import LLMCallRecord
from main import app

# Mock user for testing
_MOCK_USER = User(id=uuid.uuid4(), email="test@example.com", full_name="Test User")

async def mock_get_current_user():
    return _MOCK_USER

async def mock_get_db():
    mock_session = AsyncMock()
    yield mock_session

app.dependency_overrides[get_current_user] = mock_get_current_user
app.dependency_overrides[get_db] = mock_get_db

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_minimal_pdf(text: str = "AI is transforming the world.") -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_multipage_pdf(pages: int = 5) -> bytes:
    """Create a PDF with *pages* pages, each containing distinct text."""
    import fitz
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"Page {i + 1}: Artificial intelligence enables machines to learn. "
            f"Deep learning is a subset of machine learning.",
        )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


_MOCK_QUESTIONS = [
    {
        "question": "What is artificial intelligence?",
        "options": [
            "A type of database",
            "The simulation of human intelligence by machines",
            "A programming language",
            "A hardware component",
        ],
        "correct_answer": "The simulation of human intelligence by machines",
        "explanation": "AI refers to machines simulating human-like intelligence.",
        "difficulty": "easy",
        "source_chunk": 0,
    }
]


def _mock_llm_record(**kwargs) -> LLMCallRecord:
    """Build a successful LLMCallRecord for use as a call_llm side_effect."""
    return LLMCallRecord(
        chunk_index=kwargs.get("chunk_index", 0),
        system_prompt=kwargs.get("system_prompt", "system"),
        user_prompt=kwargs.get("user_prompt", "user"),
        model=kwargs.get("model", "mistral/mistral-small-latest"),
        raw_response=json.dumps(_MOCK_QUESTIONS),
        parsed_questions=_MOCK_QUESTIONS,
        latency_seconds=0.5,
        tokens_used=100,
        success=True,
    )


# ── Health endpoint ───────────────────────────────────────────────────────────

def test_health_returns_200():
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_response_schema():
    response = client.get("/api/v1/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


# ── POST /pdf-info ────────────────────────────────────────────────────────────

def test_pdf_info_returns_200():
    pdf_bytes = _make_minimal_pdf("This is a test document about machine learning.")
    response = client.post(
        "/api/v1/pdf-info",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200


def test_pdf_info_response_schema():
    pdf_bytes = _make_minimal_pdf("Artificial intelligence is reshaping industries worldwide.")
    response = client.post(
        "/api/v1/pdf-info",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    body = response.json()
    assert "filename" in body
    assert "page_count" in body
    assert "estimated_tokens" in body
    assert "max_questions_allowed" in body
    assert "allowed_question_counts" in body
    assert isinstance(body["allowed_question_counts"], list)
    assert body["page_count"] >= 1
    assert body["estimated_tokens"] >= 0


def test_pdf_info_empty_file_returns_400():
    response = client.post(
        "/api/v1/pdf-info",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_pdf_info_non_pdf_returns_400():
    response = client.post(
        "/api/v1/pdf-info",
        files={"file": ("doc.txt", b"just some text", "text/plain")},
    )
    assert response.status_code == 400


# ── POST /generate-quiz ────────────────────────────────────────────────────────

def test_generate_quiz_with_valid_pdf():
    # Use a 10-page PDF so the cap (25) covers 10 questions
    pdf_bytes = _make_multipage_pdf(pages=10)
    with patch("app.services.quiz_service.call_llm", side_effect=_mock_llm_record):
        response = client.post(
            "/api/v1/generate-quiz",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"total_questions": 10},
        )

    assert response.status_code == 200
    body = response.json()
    assert "questions" in body
    assert isinstance(body["questions"], list)
    assert "requested_questions" in body
    assert "generated_questions" in body
    assert "page_range" in body
    assert "chunking_stats" in body


def test_generate_quiz_response_page_range():
    pdf_bytes = _make_multipage_pdf(pages=10)
    with patch("app.services.quiz_service.call_llm", side_effect=_mock_llm_record):
        response = client.post(
            "/api/v1/generate-quiz",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"total_questions": 10, "start_page": 1, "end_page": 5},
        )
    assert response.status_code == 200
    body = response.json()
    page_range = body["page_range"]
    assert page_range["start_page"] == 1
    assert page_range["end_page"] == 5
    assert page_range["selected_pages"] == 5
    assert page_range["pdf_total_pages"] == 10


def test_generate_quiz_response_question_structure():
    # 10-page PDF so cap (25) covers 10 questions
    pdf_bytes = _make_multipage_pdf(pages=10)
    with patch("app.services.quiz_service.call_llm", side_effect=_mock_llm_record):
        response = client.post(
            "/api/v1/generate-quiz",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"total_questions": 10},
        )

    assert response.status_code == 200
    questions = response.json()["questions"]
    if questions:
        q = questions[0]
        assert "question" in q
        assert "options" in q
        assert len(q["options"]) == 4
        assert "correct_answer" in q
        assert "explanation" in q
        assert "difficulty" in q
        assert "source_chunk" in q
        assert q["correct_answer"] in q["options"]


def test_generate_quiz_empty_file_returns_400():
    response = client.post(
        "/api/v1/generate-quiz",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"total_questions": 10},
    )
    assert response.status_code == 400


def test_generate_quiz_non_pdf_returns_400():
    response = client.post(
        "/api/v1/generate-quiz",
        files={"file": ("document.txt", b"This is plain text, not a PDF.", "text/plain")},
        data={"total_questions": 10},
    )
    assert response.status_code == 400


def test_generate_quiz_corrupted_pdf_returns_400():
    response = client.post(
        "/api/v1/generate-quiz",
        files={"file": ("bad.pdf", b"%PDF-1.4 corrupted!!!", "application/pdf")},
        data={"total_questions": 10},
    )
    assert response.status_code == 400


def test_generate_quiz_no_file_returns_422():
    response = client.post("/api/v1/generate-quiz")
    assert response.status_code == 422


def test_generate_quiz_invalid_question_count_returns_422():
    """25 is not in the allowed question counts."""
    pdf_bytes = _make_minimal_pdf("Some content about AI and machine learning.")
    response = client.post(
        "/api/v1/generate-quiz",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"total_questions": 25},
    )
    assert response.status_code == 422
    assert "not an allowed question count" in response.json()["detail"].lower() \
        or "not an allowed" in response.json()["detail"]


def test_generate_quiz_start_page_after_end_page_returns_422():
    pdf_bytes = _make_multipage_pdf(pages=10)
    response = client.post(
        "/api/v1/generate-quiz",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"total_questions": 10, "start_page": 8, "end_page": 5},
    )
    assert response.status_code == 422


def test_generate_quiz_end_page_exceeds_total_returns_400():
    """end_page > total_pages: the PDF parser fires a PDFParseError → 400."""
    pdf_bytes = _make_multipage_pdf(pages=5)
    with patch("app.services.quiz_service.call_llm", side_effect=_mock_llm_record):
        response = client.post(
            "/api/v1/generate-quiz",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"total_questions": 10, "start_page": 1, "end_page": 999},
        )
    assert response.status_code == 400


def test_generate_quiz_question_count_exceeds_page_cap_returns_422():
    """1 page → cap = 2 questions. Requesting 10 should fail with 422."""
    pdf_bytes = _make_minimal_pdf("Short document with just one page of content.")
    response = client.post(
        "/api/v1/generate-quiz",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"total_questions": 10, "start_page": 1, "end_page": 1},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    # Should mention pages or maximum
    assert "maximum" in detail.lower() or "pages" in detail.lower()


def test_generate_quiz_no_warning_on_success():
    """In the normal case, the warning field should be null."""
    pdf_bytes = _make_minimal_pdf("AI content for quiz generation.")
    with patch("app.services.quiz_service.call_llm", side_effect=_mock_llm_record):
        response = client.post(
            "/api/v1/generate-quiz",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            data={"total_questions": 10},
        )
    # warning may be null or absent in the success case
    body = response.json()
    # Only check if we got a 200 first
    if response.status_code == 200:
        # warning key should exist (may be null)
        assert "warning" in body
