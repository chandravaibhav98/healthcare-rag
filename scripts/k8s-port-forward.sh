#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# k8s-port-forward.sh: reach the app without the gateway's NodePort (e.g. a cluster
# other than the local kind one). Parity: k8s-port-forward.ps1. Ctrl+C stops it.
#
#   web (default): http://127.0.0.1:8089 → nginx (SPA + /api proxied to the API)
#   api          : http://127.0.0.1:8000 → the API directly (/docs, /metrics)
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/k8s-port-forward.sh [--service web|api] [--port N] [-h|--help]

  --service   web (default) or api
  --port N    Local port (default 8089 for web, 8000 for api)
USAGE
}

SERVICE=web; PORT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) [[ $# -ge 2 ]] || die "--service needs a value"; SERVICE="$2"; shift ;;
    --port) [[ $# -ge 2 ]] || die "--port needs a value"; PORT="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
case "$SERVICE" in
  web) TARGET=8080; PORT="${PORT:-8089}" ;;
  api) TARGET=8000; PORT="${PORT:-8000}" ;;
  *) die "--service must be web or api" ;;
esac
require_kubectl
log_step "Forwarding http://127.0.0.1:$PORT → service/$SERVICE:$TARGET (Ctrl+C to stop)"
# kubectl reconnects to a new pod only when restarted; loop so a rollout does not end it.
while true; do
  kube -n "$K8S_NAMESPACE" port-forward --address 127.0.0.1 "service/$SERVICE" "$PORT:$TARGET" || true
  log_warn "port-forward ended (pod replaced?); reconnecting in 2 s"
  sleep 2
done
