"""
app/llm/llm_client.py

Thin wrapper around the Groq SDK that:
  - Sends chat completion requests to the configured model.
  - Parses the JSON response, stripping markdown code fences if present.
  - Retries up to MAX_RETRIES times on transient errors.
  - Measures and logs LLM latency.
  - Traces calls to LangSmith when LANGSMITH_TRACING=true.
  - Returns both the parsed questions AND the full raw response for audit logging.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from groq import AsyncGroq, Groq

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
REQUEST_TIMEOUT_SECONDS = 30
MAX_COMPLETION_TOKENS = 2048
TOP_P = 0.95
REASONING_EFFORT = "default"

# Regex to strip ```json ... ``` or ``` ... ``` wrappers
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass
class LLMCallRecord:
    """Full audit record for one LLM call (one chunk)."""
    chunk_index: int
    system_prompt: str
    user_prompt: str
    model: str
    raw_response: str = ""
    parsed_questions: list[dict[str, Any]] = field(default_factory=list)
    latency_seconds: float = 0.0
    tokens_used: int = 0
    success: bool = False
    error: str = ""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_json_array(text: str) -> list:
    """
    Attempt to extract a JSON array from *text*.

    Tries:
    1. Direct parse after stripping code fences.
    2. Regex search for the first [...] block in the text.
    """
    cleaned = _strip_code_fences(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            if "question" in parsed and "options" in parsed:
                return [parsed]
            for value in parsed.values():
                if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                    return value
    except json.JSONDecodeError:
        pass

    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract a JSON array from LLM response:\n{text[:500]}")


def _completion_kwargs(model: str, messages: list[dict[str, str]], temperature: float) -> dict[str, Any]:
    """Build common Groq chat completion arguments."""
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "top_p": TOP_P,
        "reasoning_effort": REASONING_EFFORT,
        "stream": False,
    }


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    chunk_index: int = 0,
    temperature: float = 0.4,
) -> LLMCallRecord:
    """Call Groq synchronously and return parsed questions plus audit details."""
    record = LLMCallRecord(
        chunk_index=chunk_index,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            start = time.perf_counter()
            response = Groq(timeout=REQUEST_TIMEOUT_SECONDS).chat.completions.create(
                **_completion_kwargs(model, messages, temperature)
            )
            latency = time.perf_counter() - start

            raw_content = response.choices[0].message.content or ""
            tokens = getattr(response.usage, "total_tokens", 0) or 0
            record.raw_response = raw_content
            record.latency_seconds = latency
            record.tokens_used = tokens

            logger.info(
                "Groq call | chunk=%d model=%s attempt=%d latency=%.3fs tokens=%s",
                chunk_index, model, attempt, latency, tokens,
            )

            record.parsed_questions = _extract_json_array(raw_content)
            record.success = True
            return record
        except ValueError as exc:
            last_error = exc
            record.error = str(exc)
            logger.warning(
                "JSON parse failed chunk=%d (attempt %d/%d): %s",
                chunk_index, attempt, MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            record.error = str(exc)
            logger.warning(
                "Groq call failed chunk=%d (attempt %d/%d): %s",
                chunk_index, attempt, MAX_RETRIES + 1, exc,
            )

    record.success = False
    record.error = str(last_error)
    return record


async def acall_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    chunk_index: int = 0,
    temperature: float = 0.4,
) -> LLMCallRecord:
    """Call Groq asynchronously and return parsed questions plus audit details."""
    record = LLMCallRecord(
        chunk_index=chunk_index,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            start = time.perf_counter()
            async with AsyncGroq(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.chat.completions.create(
                    **_completion_kwargs(model, messages, temperature)
                )
            latency = time.perf_counter() - start

            raw_content = response.choices[0].message.content or ""
            tokens = getattr(response.usage, "total_tokens", 0) or 0
            record.raw_response = raw_content
            record.latency_seconds = latency
            record.tokens_used = tokens

            logger.info(
                "Groq call (async) | chunk=%d model=%s attempt=%d latency=%.3fs tokens=%s",
                chunk_index, model, attempt, latency, tokens,
            )

            record.parsed_questions = _extract_json_array(raw_content)
            record.success = True
            return record
        except ValueError as exc:
            last_error = exc
            record.error = str(exc)
            logger.warning(
                "JSON parse failed chunk=%d (attempt %d/%d): %s",
                chunk_index, attempt, MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            record.error = str(exc)
            logger.warning(
                "Groq call failed chunk=%d (attempt %d/%d): %s",
                chunk_index, attempt, MAX_RETRIES + 1, exc,
            )

    record.success = False
    record.error = str(last_error)
    return record
