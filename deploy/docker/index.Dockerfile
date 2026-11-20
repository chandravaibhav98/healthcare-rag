# -----------------------------------------------------------------------------
# rag-index: the versioned index artifact as an OCI image (ADR-0008, plan Phase 8).
#
#   docker build -f deploy/docker/index.Dockerfile -t rag-index:build .
#   docker run --rm rag-index:build cat /index/manifest.json   # → index_version
#
# The build stage runs the same deterministic pipeline as CI (SC1), so the image's
# index_version equals the one `scripts/verify-determinism.*` reports for this commit.
# The final stage is tiny: the index files plus `cp`, because its only job is to be
# copied into the API's index volume (Compose `indexer` service, Kubernetes init
# container). Tag it rag-index:<index_version>; scripts/docker-up.* and k8s-up.* do.
#
# Build args (chunking only; the embedding settings must match the API's):
#   CHUNK_MIN_TOKENS, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_RATIO
# A different chunking gives a different, equally valid index_version, which is how
# scripts/k8s-verify.* produces a second index to test rollout and rollback.
# -----------------------------------------------------------------------------
ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9
ARG RUNTIME_IMAGE=busybox:1.37

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONHASHSEED=random \
    PYTHONPATH=/app/backend
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY corpus /app/corpus
ARG CHUNK_MIN_TOKENS=80
ARG CHUNK_MAX_TOKENS=160
ARG CHUNK_OVERLAP_RATIO=0.15
# PYTHONHASHSEED=random above: the build must not depend on Python's hash salt (SC1).
RUN CHUNK_MIN_TOKENS=${CHUNK_MIN_TOKENS} CHUNK_MAX_TOKENS=${CHUNK_MAX_TOKENS} \
    CHUNK_OVERLAP_RATIO=${CHUNK_OVERLAP_RATIO} \
    /app/.venv/bin/python scripts/pipeline.py build --corpus /app/corpus --out /index \
 && /app/.venv/bin/python scripts/pipeline.py verify --index /index --corpus /app/corpus \
 && /app/.venv/bin/python -c "import json; m = json.load(open('/index/manifest.json')); print('index_version', m['index_version'])"

FROM ${RUNTIME_IMAGE} AS runtime
LABEL org.opencontainers.image.title="rag-index" \
      org.opencontainers.image.description="Versioned RAG index built from the synthetic corpus; see /index/manifest.json"
COPY --from=build --chown=65534:65534 /index /index
# /target exists and is owned by the copying user, so a new Docker named volume mounted
# there inherits that owner (Kubernetes uses an emptyDir with fsGroup instead).
RUN mkdir -p /target && chown 65534:65534 /target
USER 65534:65534
# Copies the index into the volume mounted at /target (Compose indexer, k8s init
# container). `cp -R` then a manifest check: a partial copy must not look complete.
CMD ["sh", "-c", "cp -R /index/. /target/ && test -s /target/manifest.json && echo \"index copied: $(grep -m1 '\"index_version\"' /target/manifest.json)\""]
