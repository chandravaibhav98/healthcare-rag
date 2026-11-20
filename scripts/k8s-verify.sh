#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# k8s-verify.sh: prove zero-downtime operations on the running cluster (plan §4 Phase 9).
# Parity: k8s-verify.ps1. Run after scripts/k8s-up.sh.
#
#   1. Rolling restart under load: k6 drives /qa while `kubectl rollout restart` replaces
#      every api and web pod. Gate: zero failed requests.
#   2. Index rollout and rollback under load: a second index (different chunking, so a
#      different index_version) is rolled out with `kubectl set image`, every API pod is
#      checked to serve it, then `kubectl rollout undo` restores the previous one.
#      Gate: zero failed requests, and the served index_version is right after each step.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/k8s-verify.sh [--vus N] [--duration D] [--skip-restart] [--skip-index]
                             [--ci] [-h|--help]

  --vus N          Virtual users during each check (default 20)
  --duration D     k6 duration per check, long enough to cover the rollout (default 90s)
  --skip-restart   Skip the rolling-restart check
  --skip-index     Skip the index rollout/rollback check
  --ci             Plain output (no colours)

Environment: K8S_CONTEXT, K8S_BASE_URL (default http://127.0.0.1:8088), K8S_IMAGE_LOADER.
USAGE
}

VUS=20; DURATION=90s; DO_RESTART=1; DO_INDEX=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vus) [[ $# -ge 2 ]] || die "--vus needs a value"; VUS="$2"; shift ;;
    --duration) [[ $# -ge 2 ]] || die "--duration needs a value"; DURATION="$2"; shift ;;
    --skip-restart) DO_RESTART=0 ;;
    --skip-index) DO_INDEX=0 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
BASE_URL="${K8S_BASE_URL:-http://127.0.0.1:8088}"
NS="$K8S_NAMESPACE"
require_kubectl
require_cmd curl "curl is needed for the checks."
PY="$(venv_python)"
mkdir -p "$REPO_ROOT/artifacts/k8s-verify"
wait_http "$BASE_URL/readyz" 30 || die "$BASE_URL does not answer; run scripts/k8s-up.sh first"

served_version() { curl -fsS --max-time 5 "$BASE_URL/readyz" | sed -n 's/.*"index_version":"\([0-9a-f]*\)".*/\1/p'; }

# expect_version <v>: 20 consecutive requests, spread over the replicas, must report <v>.
# Pods that are terminating may still finish requests on kept-alive connections for a few
# seconds after `rollout status` returns, so allow up to 60 s to converge.
expect_version() {
  local want="$1" got streak=0 deadline=$((SECONDS + 60))
  while ((streak < 20)); do
    got="$(served_version || true)"
    if [[ "$got" == "$want" ]]; then streak=$((streak + 1)); else streak=0; sleep 1; fi
    ((SECONDS < deadline)) || { log_error "still serving $got 60 s after the rollout, expected $want"; return 1; }
  done
  log_ok "20 consecutive requests served index $want"
}

LOAD_PID=""
start_load() { # start_load <name>
  LOAD_LOG="$REPO_ROOT/artifacts/k8s-verify/$1.log"
  bash "$REPO_ROOT/scripts/load-test.sh" --target "$BASE_URL" --vus "$VUS" --duration "$DURATION" \
    --p95 2000 --ci >"$LOAD_LOG" 2>&1 &
  LOAD_PID=$!
  sleep 8 # let k6 ramp up before disturbing the cluster
}

# finish_load <name>: wait for k6, then require zero failed requests and checks.
finish_load() {
  local rc=0
  wait "$LOAD_PID" || rc=$?
  LOAD_PID=""
  cp "$REPO_ROOT/artifacts/load/summary.json" "$REPO_ROOT/artifacts/k8s-verify/$1.summary.json"
  local verdict=0
  "$PY" - "$REPO_ROOT/artifacts/k8s-verify/$1.summary.json" "$1" <<'PY' || verdict=$?
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))["metrics"]
failed, total = m["http_req_failed"]["passes"], m["http_reqs"]["count"]
bad_checks = m["checks"]["fails"]
p95 = m["http_req_duration"].get("p(95)")
print(f"    {sys.argv[2]}: {total} requests, {failed} failed, {bad_checks} failed checks, p95 {p95:.0f} ms")
sys.exit(1 if failed or bad_checks or total == 0 else 0)
PY
  ((rc == 0 && verdict == 0)) || { log_error "$1: requests failed (log: artifacts/k8s-verify/$1.log)"; return 1; }
  log_ok "$1: zero failed requests"
}
# On any failure: stop k6, and if the candidate index was rolled out but not yet rolled
# back, roll it back so the cluster is left as it was found.
ROLLED_OUT=0
cleanup() {
  [[ -n "$LOAD_PID" ]] && kill "$LOAD_PID" 2>/dev/null
  if ((ROLLED_OUT)); then
    log_warn "restoring the previous index (kubectl rollout undo)"
    kube -n "$NS" rollout undo deployment/api >/dev/null 2>&1 || true
  fi
  return 0
}
trap cleanup EXIT

# --- 1. rolling restart -------------------------------------------------------------------
if ((DO_RESTART)); then
  log_step "Rolling restart of api and web under load ($VUS VUs)"
  start_load rolling-restart
  run kube -n "$NS" rollout restart deployment/api deployment/web
  run kube -n "$NS" rollout status deployment/api --timeout=300s
  run kube -n "$NS" rollout status deployment/web --timeout=300s
  finish_load rolling-restart
fi

# --- 2. index rollout and rollback --------------------------------------------------------
if ((DO_INDEX)); then
  require_docker
  log_step "Index rollout and rollback under load"
  CURRENT="$(served_version)"
  [[ -n "$CURRENT" ]] || die "could not read the served index_version"
  CURRENT_IMAGE="$(kube -n "$NS" get deployment api -o jsonpath='{.spec.template.spec.initContainers[?(@.name=="index")].image}')"
  log_info "serving $CURRENT ($CURRENT_IMAGE)"
  # A different chunking gives a different but equally valid index (index.Dockerfile).
  extra=(); [[ -n "${DOCKER_BUILD_ARGS:-}" ]] && read -r -a extra <<<"$DOCKER_BUILD_ARGS"
  run docker build "${extra[@]}" -q -f "$DOCKER_DIR/index.Dockerfile" \
    --build-arg CHUNK_MIN_TOKENS=100 --build-arg CHUNK_MAX_TOKENS=200 -t rag-index:candidate "$REPO_ROOT" >/dev/null
  CANDIDATE="$(image_index_version rag-index:candidate)"
  [[ -n "$CANDIDATE" && "$CANDIDATE" != "$CURRENT" ]] || die "the candidate index has no new index_version"
  run docker tag rag-index:candidate "rag-index:$CANDIDATE"
  load_images "rag-index:$CANDIDATE"

  start_load index-rollout
  ROLLED_OUT=1
  run kube -n "$NS" set image deployment/api "index=rag-index:$CANDIDATE"
  run kube -n "$NS" annotate deployment/api kubernetes.io/change-cause="index $CANDIDATE (k8s-verify)" --overwrite
  run kube -n "$NS" rollout status deployment/api --timeout=300s
  expect_version "$CANDIDATE"
  run kube -n "$NS" rollout undo deployment/api
  ROLLED_OUT=0
  run kube -n "$NS" rollout status deployment/api --timeout=300s
  expect_version "$CURRENT"
  finish_load index-rollout
  run kube -n "$NS" rollout history deployment/api
fi

log_step "All checks passed"
log_info "k6 summaries: artifacts/k8s-verify/"
