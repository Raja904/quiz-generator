# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder
# Install dependencies in an isolated environment to keep the runtime image small.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Prevents Python from writing .pyc files and enables unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build tools (needed for some packages with C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable dependency resolution
RUN pip install --no-cache-dir uv

# Copy only the dependency manifest first for maximum layer caching.
# If pyproject.toml hasn't changed, this layer is reused on rebuild.
COPY pyproject.toml .

# Install production dependencies only (no [dev] extras) into a venv
RUN uv venv /app/.venv && \
    uv pip install --no-cache --python /app/.venv/bin/python \
        "gunicorn>=22.0" \
        -e .


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime
# Minimal image — only runtime artefacts, no build tools or caches.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Make the venv the active Python environment
    PATH="/app/.venv/bin:$PATH" \
    # Gunicorn / Uvicorn defaults (overridable via Azure App Service config)
    PORT=8000 \
    WORKERS=2 \
    TIMEOUT=120

# Minimal runtime system library (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the fully installed virtualenv from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source — everything the app needs at runtime
COPY main.py .
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# ── Non-root user for security ─────────────────────────────────────────────
# Azure App Service runs containers as root by default but best practice
# is to drop privileges. The PORT binding is ≥1024, so no CAP_NET_BIND needed.
RUN groupadd --gid 1001 appgroup && \
    useradd  --uid 1001 --gid appgroup --shell /bin/sh --no-create-home appuser && \
    chown -R appuser:appgroup /app

USER appuser

# Azure App Service reads WEBSITES_PORT (or PORT) to route traffic.
EXPOSE 8000

# ── Health check ───────────────────────────────────────────────────────────
# Checks the /api/v1/health endpoint every 30 s.
# Gives the container 60 s to start before the first check.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/v1/health')" || exit 1

# ── Start command ──────────────────────────────────────────────────────────
# Gunicorn as the process manager, Uvicorn as the ASGI worker class.
# $WORKERS defaults to 2; override via Azure App Service → Configuration →
# Application Settings with key WORKERS.
CMD gunicorn main:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers ${WORKERS} \
        --bind 0.0.0.0:${PORT} \
        --timeout ${TIMEOUT} \
        --access-logfile - \
        --error-logfile - \
        --log-level info
