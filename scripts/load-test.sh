#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# load-test.sh: k6 load test of POST /qa (e2e/load/qa.js). Parity: load-test.ps1.
#
# Gate (plan §4 Phase 7): 50 virtual users for 5 minutes, p95 < 300 ms, 0 % 5xx.
# k6 exits non-zero when a threshold fails, and so does this script.
#
# Target: without --target a disposable, seeded API is started on --port with
# load-friendly rate limits (backend/scripts/e2e_server.py, data in artifacts/load)
# and stopped afterwards. With --target the given stack is used as is; its
# RATE_LIMIT_QA must allow the load or most requests will be 429s.
#
# Runner: a local `k6` if installed, otherwise the grafana/k6 Docker image.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/load-test.sh [--vus N] [--duration D] [--target URL] [--port P]
                            [--p95 MS] [--ci] [-h|--help]

  --vus N        Virtual users (default 50)
  --duration D   k6 duration, e.g. 30s, 5m (default 5m)
  --target URL   Use a running API instead of starting a disposable one
  --port P       Port of the disposable API (default 8200)
  --p95 MS       p95 latency threshold in ms (default 300)
  --ci           Plain output (no colours)

Examples:
  scripts/load-test.sh                          # full gate: 50 VUs x 5 min
  scripts/load-test.sh --vus 10 --duration 30s  # quick smoke
  scripts/load-test.sh --target http://localhost:8000
USAGE
}

VUS=50; DURATION=5m; TARGET=""; PORT=8200; P95=300
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vus) [[ $# -ge 2 ]] || die "--vus needs a value"; VUS="$2"; shift ;;
    --duration) [[ $# -ge 2 ]] || die "--duration needs a value"; DURATION="$2"; shift ;;
    --target) [[ $# -ge 2 ]] || die "--target needs a value"; TARGET="${2%/}"; shift ;;
    --port) [[ $# -ge 2 ]] || die "--port needs a value"; PORT="$2"; shift ;;
    --p95) [[ $# -ge 2 ]] || die "--p95 needs a value"; P95="$2"; shift ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
[[ "$VUS" =~ ^[0-9]+$ ]] || die "--vus must be a whole number"
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port must be a whole number"
[[ "$P95" =~ ^[0-9]+$ ]] || die "--p95 must be a whole number of milliseconds"

# --- runner -------------------------------------------------------------------
SCRIPT_REL="e2e/load/qa.js"
if command -v k6 >/dev/null 2>&1; then
  RUNNER=local
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  RUNNER=docker
else
  die "k6 not found and Docker is not running. Install k6 (https://grafana.com/docs/k6/latest/set-up/install-k6/; winget install k6 / brew install k6) or start Docker."
fi

# --- target -------------------------------------------------------------------
SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    log_info "stopping the disposable API (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ -z "$TARGET" ]]; then
  require_cmd curl "curl is needed to wait for the API."
  # Docker Desktop reaches the host through host.docker.internal, which needs the API on
  # all interfaces; elsewhere it stays on loopback.
  HOST=127.0.0.1
  [[ "$RUNNER" == docker && "$(uname -s)" != Linux ]] && HOST=0.0.0.0
  TARGET="http://127.0.0.1:$PORT"
  log_step "Starting a disposable API on $TARGET"
  mkdir -p "$REPO_ROOT/artifacts"
  # The venv's Python is exec'd directly (not through `uv run`) so $! is the server
  # itself and the cleanup trap stops it on Windows too, where killing uv would orphan it.
  PY="$BACKEND_DIR/.venv/bin/python"
  [[ -x "$PY" ]] || PY="$BACKEND_DIR/.venv/Scripts/python.exe"
  [[ -x "$PY" ]] || die "backend/.venv is missing: run scripts/setup.sh first."
  (cd "$BACKEND_DIR" && exec "$PY" scripts/e2e_server.py \
    --host "$HOST" --port "$PORT" --data-dir artifacts/load) \
    >"$REPO_ROOT/artifacts/load-server.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do
    if curl -fsS "$TARGET/readyz" >/dev/null 2>&1; then break; fi
    kill -0 "$SERVER_PID" 2>/dev/null || die "the API exited; see artifacts/load-server.log"
    sleep 1
  done
  curl -fsS "$TARGET/readyz" >/dev/null 2>&1 || die "the API did not become ready; see artifacts/load-server.log"
  log_ok "ready (log: artifacts/load-server.log)"
fi

# --- run ----------------------------------------------------------------------
mkdir -p "$REPO_ROOT/artifacts/load"
log_step "k6: $VUS VUs for $DURATION against $TARGET ($RUNNER), gate p95 < ${P95} ms, 0 % 5xx"
K6_ENV=(-e "VUS=$VUS" -e "DURATION=$DURATION" -e "P95_MS=$P95")
if [[ "$RUNNER" == local ]]; then
  (cd "$REPO_ROOT" && k6 run "${K6_ENV[@]}" -e "BASE_URL=$TARGET" \
    --summary-export artifacts/load/summary.json "$SCRIPT_REL")
else
  DOCKER_NET=(--network host); DOCKER_TARGET="$TARGET"
  if [[ "$(uname -s)" != Linux ]]; then
    DOCKER_NET=(--add-host host.docker.internal:host-gateway)
    DOCKER_TARGET="$(printf '%s' "$TARGET" | sed -E 's#//(127\.0\.0\.1|localhost)#//host.docker.internal#')"
  fi
  # MSYS_NO_PATHCONV stops Git Bash rewriting the container paths.
  MSYS_NO_PATHCONV=1 docker run --rm -i "${DOCKER_NET[@]}" \
    -v "$REPO_ROOT:/repo" -w /repo "${K6_IMAGE:-grafana/k6:latest}" run "${K6_ENV[@]}" \
    -e "BASE_URL=$DOCKER_TARGET" --summary-export artifacts/load/summary.json "$SCRIPT_REL"
fi
log_ok "load test passed; summary: artifacts/load/summary.json"
