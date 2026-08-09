"""
main.py

FastAPI application entry point.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db.database import engine
from app.db.models import Base

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    logger.info(
        "PDF-to-Quiz API started | version=%s  model=%s  "
        "chunk_size=%d tokens  overlap=%d  max_pages=%d",
        settings.app_version,
        settings.llm_model,
        settings.preferred_chunk_size,
        settings.chunk_overlap,
        settings.max_pages_per_request,
    )
    yield


# ── FastAPI application ───────────────────────────────────────────────────────
app = FastAPI(
    title="PDF-to-Quiz API",
    description=(
        "AI-powered backend that converts PDF documents into structured "
        "multiple-choice quizzes using an LLM.\n\n"
        "**Workflow:**\n"
        "1. `POST /pdf-info` — Upload your PDF to get page count and limits.\n"
        "2. `POST /generate-quiz` — Submit PDF with page range and question count.\n"
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — open for development; restrict to your frontend origin in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
# Mount at root as well to catch frontend requests missing the /api/v1 suffix
app.include_router(router)
