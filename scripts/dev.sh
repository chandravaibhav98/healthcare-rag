#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# dev.sh: run the API (uvicorn --reload) and the web app (Vite) together.
# Ctrl+C stops both. Parity: dev.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/dev.sh [--api-only | --web-only] [-h|--help]

  --api-only   Run only the FastAPI service (http://API_HOST:API_PORT)
  --web-only   Run only the Vite dev server (http://localhost:5173)
USAGE
}

API=1; WEB=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-only) WEB=0 ;;
    --web-only) API=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
((API || WEB)) || die "--api-only and --web-only are mutually exclusive"
load_dotenv
INDEX="${INDEX_DIR:-artifacts/index}"; [[ "$INDEX" = /* ]] || INDEX="$REPO_ROOT/$INDEX"

PIDS=()
cleanup() { for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if ((API)); then
  require_cmd uv "Run scripts/setup.sh first."
  [[ -f "$INDEX/manifest.json" ]] || die "No index at $INDEX. Run scripts/build-index.sh first."
  if [[ -n "${DATABASE_URL:-}" ]]; then
    # Local convenience only: deployments run scripts/db-migrate.* as a separate step.
    log_step "Migrate the database (DATABASE_URL is set)"
    run uv run --directory "$BACKEND_DIR" python scripts/db.py upgrade
  fi
  log_step "API on http://${API_HOST:-127.0.0.1}:${API_PORT:-8000} (docs at /docs)"
  run uv run --directory "$BACKEND_DIR" uvicorn --factory app.main:create_app --reload \
    --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}" &
  PIDS+=($!)
fi
if ((WEB)); then
  require_cmd npm "Install Node (see scripts/preflight.sh)."
  log_step "Web on http://localhost:5173"
  run npm --prefix "$REPO_ROOT/frontend" run dev &
  PIDS+=($!)
fi
wait -n
