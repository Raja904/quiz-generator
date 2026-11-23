"""Tests for the Groq-backed LLM client."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.llm_client import acall_llm, call_llm


MODEL = "qwen/qwen3.8-27b"
RESPONSE_TEXT = json.dumps([{"question": "A question?", "options": ["A", "B", "C", "D"]}])


def _completion_response(content=RESPONSE_TEXT):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=42),
    )


def test_call_llm_uses_groq_and_parses_response():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _completion_response()

    with patch("app.llm.llm_client.Groq", return_value=mock_client) as groq:
        record = call_llm("system prompt", "user prompt", MODEL)

    assert record.success
    assert record.parsed_questions[0]["question"] == "A question?"
    assert record.tokens_used == 42
    groq.assert_called_once_with(timeout=30)
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == MODEL
    assert kwargs["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert kwargs["stream"] is False


@pytest.mark.asyncio
async def test_acall_llm_uses_async_groq_and_parses_response():
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.chat.completions.create = AsyncMock(return_value=_completion_response())

    with patch("app.llm.llm_client.AsyncGroq", return_value=mock_client) as groq:
        record = await acall_llm("system prompt", "user prompt", MODEL)

    assert record.success
    assert record.parsed_questions[0]["question"] == "A question?"
    groq.assert_called_once_with(timeout=30)
    mock_client.chat.completions.create.assert_awaited_once()
