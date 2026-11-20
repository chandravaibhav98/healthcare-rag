#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# smoke.sh: probe a running API (health, readiness, both /qa paths, schema, latency).
# Parity: smoke.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/smoke.sh [--base-url URL] [--bench N] [-h|--help]

  --base-url URL  API base URL (default: http://API_HOST:API_PORT from .env)
  --bench N       Send N extra /qa requests and check p95 <= 150 ms
USAGE
}

load_dotenv
BASE_URL="http://${API_HOST:-127.0.0.1}:${API_PORT:-8000}"; ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) [[ $# -ge 2 ]] || die "--base-url needs a value"; BASE_URL="$2"; shift ;;
    --bench) [[ $# -ge 2 ]] || die "--bench needs a value"; ARGS+=(--bench "$2"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."
log_step "Smoke test $BASE_URL"
run uv run --directory "$BACKEND_DIR" python scripts/smoke.py --base-url "$BASE_URL" "${ARGS[@]}"
