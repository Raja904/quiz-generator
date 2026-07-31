# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder
# Install all Python dependencies in an isolated venv.
# Only the venv (not build tools) is carried into the runtime image.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# gcc + libpq-dev are needed to compile asyncpg and other C-extension deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv: fast, reliable Python package installer
RUN pip install --no-cache-dir uv

# ── Dependency installation (layer-cached) ────────────────────────────────
# Copy ONLY the files hatchling needs to resolve & install dependencies.
# This layer is re-used on every rebuild where these files haven't changed.
COPY pyproject.toml README.md ./

# Hatchling (build backend) discovers packages listed under
# [tool.hatch.build.targets.wheel] → packages = ["app"].
# We create a minimal stub so it can build a wheel without the full source.
# The real source is copied into the runtime image later.
RUN mkdir -p app && touch app/__init__.py

# Non-editable install (.) — resolves all deps from pyproject.toml + installs
# gunicorn (process manager not declared in pyproject.toml — added here).
# We do NOT use -e (editable) because:
#   • editable installs write a .pth pointing to /build, which won't exist in runtime
#   • the full source isn't present here anyway (only the stub above)
RUN uv venv /app/.venv && \
    uv pip install --no-cache --python /app/.venv/bin/python \
        "gunicorn>=22.0" \
        .


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime
# Minimal image — only the venv + application source, zero build tools.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    WORKERS=2 \
    TIMEOUT=120

# libpq5 is the runtime dependency required by asyncpg (PostgreSQL driver)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the fully-resolved virtualenv from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy only the files the running application actually needs
COPY main.py .
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# ── Non-root user (security best practice) ────────────────────────────────
RUN groupadd --gid 1001 appgroup && \
    useradd  --uid 1001 --gid appgroup --shell /bin/sh --no-create-home appuser && \
    chown -R appuser:appgroup /app

USER appuser

# Azure App Service routes traffic to this port (configured via WEBSITES_PORT)
EXPOSE 8000

# ── Health check ──────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/v1/health')" || exit 1

# ── Production start command ──────────────────────────────────────────────
# Gunicorn manages Uvicorn ASGI workers.
# $WORKERS / $PORT / $TIMEOUT are overridable via Azure App Service → Configuration.
CMD gunicorn main:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers ${WORKERS} \
        --bind 0.0.0.0:${PORT} \
        --timeout ${TIMEOUT} \
        --access-logfile - \
        --error-logfile - \
        --log-level info
