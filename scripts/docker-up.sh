#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# docker-up.sh: build the images and start the Compose stack. Parity: docker-up.ps1.
#
#   postgres → migrate → indexer → api → web (http://localhost:8080), then seed and
#   smoke-test through nginx. Secrets live in deploy/compose/.env (generated on first
#   run, git-ignored). Idempotent: re-running rebuilds changed layers and recreates
#   only what changed.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/docker-up.sh [--no-build] [--demo] [--observability] [--port N]
                            [--no-smoke] [--ci] [-h|--help]

  --no-build        Use the existing images (rag-api:local, rag-web:local, INDEX_IMAGE)
  --demo            Seed reviewer@/user@ accounts and a week of history. Runs the stack
                    with APP_ENV=staging (demo accounts are refused in production)
  --observability   Also start Prometheus (:9090) and Grafana (:3000)
  --port N          Publish the web app on 127.0.0.1:N (default 8080, saved in .env)
  --no-smoke        Skip the smoke test through nginx
  --ci              Plain output (no colours)

Passwords: deploy/compose/.env (SEED_ADMIN_PASSWORD for admin@example.org).
USAGE
}

BUILD=1; DEMO=0; OBS=0; PORT=""; SMOKE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) BUILD=0 ;;
    --demo) DEMO=1 ;;
    --observability) OBS=1 ;;
    --port) [[ $# -ge 2 ]] || die "--port needs a value"; PORT="$2"; shift ;;
    --no-smoke) SMOKE=0 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
[[ -z "$PORT" || "$PORT" =~ ^[0-9]+$ ]] || die "--port must be a number"

require_docker
log_step "Configuration"
ensure_compose_env
[[ -n "$PORT" ]] && env_set "$COMPOSE_ENV" WEB_PORT "$PORT"
((DEMO)) && env_set "$COMPOSE_ENV" APP_ENV staging
WEB_PORT="$(env_get "$COMPOSE_ENV" WEB_PORT)"; WEB_PORT="${WEB_PORT:-8080}"
log_info "deploy/compose/.env · web port $WEB_PORT · APP_ENV $(env_get "$COMPOSE_ENV" APP_ENV || true)"

if ((BUILD)); then
  build_images local
  env_set "$COMPOSE_ENV" INDEX_IMAGE "rag-index:$INDEX_VERSION"
  env_set "$COMPOSE_ENV" API_IMAGE rag-api:local
  env_set "$COMPOSE_ENV" WEB_IMAGE rag-web:local
fi

compose_cmd "$( ((OBS)) && echo --observability)"
log_step "Starting the stack"
run "${COMPOSE[@]}" up -d --wait --remove-orphans
log_ok "postgres, api and web are healthy; migrate and indexer finished"

log_step "Seeding accounts"
if ((DEMO)); then
  run "${COMPOSE[@]}" run --rm seed --demo
else
  run "${COMPOSE[@]}" run --rm seed
fi

if ((SMOKE)); then
  log_step "Smoke test through nginx"
  bash "$REPO_ROOT/scripts/smoke.sh" --base-url "http://127.0.0.1:$WEB_PORT"
fi

log_step "Ready"
log_info "Web app:  http://localhost:$WEB_PORT   (admin@example.org / SEED_ADMIN_PASSWORD in deploy/compose/.env)"
((OBS)) && log_info "Grafana:  http://localhost:3000   (admin / GRAFANA_ADMIN_PASSWORD)  ·  Prometheus: http://localhost:9090"
log_info "Logs: scripts/docker-logs.sh [service] · Stop: scripts/docker-down.sh"
