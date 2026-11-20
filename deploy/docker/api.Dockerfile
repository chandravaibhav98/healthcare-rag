# -----------------------------------------------------------------------------
# rag-api: the FastAPI service (plan §4 Phase 8, ADR-0014).
#
#   docker build -f deploy/docker/api.Dockerfile -t rag-api:local .
#
# The image carries code and dependencies only. The index is NOT baked in: Compose
# mounts it from the rag-index image's volume and Kubernetes copies it in with an
# init container (ADR-0008), so the app and the index roll out and back independently.
# The same image runs the migrations (`python scripts/db.py upgrade`) and the seed job.
# -----------------------------------------------------------------------------
ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9

FROM ${UV_IMAGE} AS uv

# --- build: resolve the locked runtime dependencies into /app/.venv ----------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
# Bytecode is compiled at build time (the runtime root filesystem is read-only); the
# image's own Python is used, never a downloaded one, so the interpreter is the one
# that runs the app.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# Dependencies first (cached until uv.lock changes); --frozen fails if the lock is stale.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# --- runtime ---------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
ARG APP_UID=10001
LABEL org.opencontainers.image.title="rag-api" \
      org.opencontainers.image.description="Healthcare Guidelines RAG Assistant API (synthetic corpus, not for clinical use)" \
      org.opencontainers.image.licenses="UNLICENSED"
RUN groupadd --system --gid ${APP_UID} app \
 && useradd --system --uid ${APP_UID} --gid app --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app
WORKDIR /app/backend
COPY --from=build /app/.venv /app/.venv
# Source tree layout is kept (app/core/config.py resolves REPO_ROOT as /app): the
# package is run from source, not installed, exactly as in development.
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
# Admin-triggered evaluations (POST /admin/eval-runs) need the harness and gold sets.
COPY backend/evaluation ./evaluation
RUN python3 -m compileall -q app evaluation migrations scripts
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    LOG_FORMAT=json \
    LOG_QUESTION_TEXT=false \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    INDEX_DIR=/var/lib/rag/index \
    INDEX_STORE_DIR=/var/lib/rag/indexes \
    CORPUS_DIR=/var/lib/rag/corpus \
    FORWARDED_ALLOW_IPS=127.0.0.1
USER ${APP_UID}:${APP_UID}
EXPOSE 8000
# No curl in the slim image; Python's stdlib does the probe. Kubernetes uses its own
# probes (deploy/k8s), this one serves Compose and `docker run`.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
# --proxy-headers: the client address for rate limiting and the audit log comes from
# X-Forwarded-For, trusted only from FORWARDED_ALLOW_IPS (set to the proxy's network
# by Compose/Kubernetes; the API is never exposed directly). Access logging is off:
# the app writes one structured JSON line per request (RequestContextMiddleware).
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--no-server-header", "--no-access-log", \
     "--timeout-graceful-shutdown", "20"]
