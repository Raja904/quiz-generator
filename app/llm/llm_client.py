"""
app/llm/llm_client.py

Thin wrapper around LiteLLM that:
  - Reads the model name from settings.
  - Sends a chat completion request.
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

import litellm  # noqa: E402 — must be module-level for mock.patch to work

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

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
            # If the LLM returned a single question object instead of an array
            if "question" in parsed and "options" in parsed:
                return [parsed]
            
            # If it wrapped the array in a key like {"questions": [...]}
            for v in parsed.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    return v
                # If it's an empty list, we might just return it
                elif isinstance(v, list) and len(v) == 0:
                    return v
    except json.JSONDecodeError:
        pass

    # Fallback: find the first [...] block
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract a JSON array from LLM response:\n{text[:500]}")


def _setup_litellm_tracing():
    """Configure LiteLLM to use LangSmith for tracing if enabled."""
    import os
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        try:
            # LiteLLM's langsmith integration explicitly looks for LANGCHAIN_* env vars.
            # Map LANGSMITH_* to LANGCHAIN_* if needed.
            for suffix in ["API_KEY", "PROJECT", "ENDPOINT", "TRACING"]:
                smith_key = f"LANGSMITH_{suffix}"
                chain_key = f"LANGCHAIN_{suffix}"
                if smith_key in os.environ and chain_key not in os.environ:
                    os.environ[chain_key] = os.environ[smith_key]

            litellm.success_callback = ["langsmith"]
            litellm.failure_callback = ["langsmith"]
            logger.info("LangSmith tracing enabled natively for LiteLLM.")
        except Exception as e:
            logger.warning("Failed to enable LangSmith tracing: %s", e)

_setup_litellm_tracing()


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    chunk_index: int = 0,
    temperature: float = 0.4,
) -> LLMCallRecord:
    """
    Call the LLM and return a full :class:`LLMCallRecord` with parsed questions
    AND the raw prompt/response for audit logging.

    Args:
        system_prompt: System role message.
        user_prompt:   User role message containing the text chunk.
        model:         LiteLLM model string (e.g. ``mistral/mistral-small-latest``).
        chunk_index:   Source chunk index (for tracing/logging).
        temperature:   Sampling temperature.

    Returns:
        :class:`LLMCallRecord` — always returned even on failure
        (check ``record.success``).
    """
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

            completion_kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                temperature=temperature,
            )
            if _supports_json_mode(model):
                completion_kwargs["response_format"] = {"type": "json_object"}

            response = litellm.completion(**completion_kwargs)
            latency = time.perf_counter() - start

            raw_content: str = response.choices[0].message.content or ""
            tokens = getattr(response.usage, "total_tokens", 0) or 0

            record.raw_response = raw_content
            record.latency_seconds = latency
            record.tokens_used = tokens

            logger.info(
                "LLM call | chunk=%d model=%s attempt=%d latency=%.3fs tokens=%s",
                chunk_index,
                model,
                attempt,
                latency,
                tokens,
            )

            parsed = _extract_json_array(raw_content)
            record.parsed_questions = parsed
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
                "LLM call failed chunk=%d (attempt %d/%d): %s",
                chunk_index, attempt, MAX_RETRIES + 1, exc,
            )

    record.success = False
    record.error = str(last_error)
    return record


def _supports_json_mode(model: str) -> bool:
    """Return True if the model is known to support response_format=json_object."""
    json_mode_models = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
        "gpt-3.5-turbo", "gpt-4-1106-preview", "gpt-4-0125-preview",
    }
    model_name = model.split("/")[-1]
    return any(model_name.startswith(m) for m in json_mode_models)
