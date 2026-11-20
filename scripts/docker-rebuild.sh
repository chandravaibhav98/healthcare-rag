#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# docker-rebuild.sh: rebuild the images and recreate the containers that changed.
# Parity: docker-rebuild.ps1. Data volumes are kept.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/docker-rebuild.sh [--no-cache] [--observability] [--ci] [-h|--help]

  --no-cache        Rebuild every layer (e.g. to pick up base-image security fixes)
  --observability   Keep the observability profile running
  --ci              Plain output (no colours)
USAGE
}

BUILD_ARGS=(); OBS=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache) BUILD_ARGS=(--no-cache --pull) ;;
    --observability) OBS=1 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_docker
ensure_compose_env
build_images local "${BUILD_ARGS[@]}"
env_set "$COMPOSE_ENV" INDEX_IMAGE "rag-index:$INDEX_VERSION"
compose_cmd "$( ((OBS)) && echo --observability)"
log_step "Recreating changed containers"
run "${COMPOSE[@]}" up -d --wait --remove-orphans
log_ok "stack is healthy (index $INDEX_VERSION)"
