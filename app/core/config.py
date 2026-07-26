"""
app/core/config.py

Application configuration loaded from environment variables / .env file.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_model: str = "mistral/mistral-small-latest"

    # ── Adaptive chunking (derived per-request from total_tokens + total_questions)
    min_chunk_size: int = 300        # token floor for a single chunk
    max_chunk_size: int = 3000       # token ceiling for a single chunk
    chunk_overlap_ratio: float = 0.10  # fraction of chunk_size used as overlap

    # ── Database & Auth (Supabase) ────────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    database_url: str = ""

    # ── Quiz ──────────────────────────────────────────────────────────────────
    default_total_questions: int = 20
    allowed_question_counts: list[int] = [10, 20, 30, 50, 75, 100, 150]

    # ── Page range limits ─────────────────────────────────────────────────────
    max_pages_per_request: int = 100   # hard cap on selected page range size

    # ── App ───────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    app_version: str = "0.1.0"


# Singleton — import this throughout the app
settings = Settings()
