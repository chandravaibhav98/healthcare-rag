#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# docker-down.sh: stop the Compose stack (observability profile included).
# Parity: docker-down.ps1. Data volumes are kept unless --volumes is given.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/docker-down.sh [--volumes] [--ci] [-h|--help]

  --volumes   Also delete the volumes: database, index, Prometheus and Grafana data
  --ci        Plain output (no colours)
USAGE
}

VOLUMES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes) VOLUMES=(--volumes) ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_docker
compose_placeholders
compose_cmd --observability
log_step "Stopping the stack"
run "${COMPOSE[@]}" --profile tools down --remove-orphans "${VOLUMES[@]}"
if ((${#VOLUMES[@]})); then log_ok "stopped; volumes deleted"; else log_ok "stopped; volumes kept (--volumes deletes them)"; fi
