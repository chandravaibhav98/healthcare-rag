#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# docker-logs.sh: show the Compose stack's logs. Parity: docker-logs.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/docker-logs.sh [SERVICE...] [--follow] [--tail N] [-h|--help]

  SERVICE     postgres, migrate, indexer, api, web, prometheus, grafana (default: all)
  --follow    Keep streaming (Ctrl+C to stop)
  --tail N    Lines per service (default 200)
USAGE
}

ARGS=(--tail 200); SERVICES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow|-f) ARGS+=(--follow) ;;
    --tail) [[ $# -ge 2 ]] || die "--tail needs a value"; ARGS+=(--tail "$2"); shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) SERVICES+=("$1") ;;
  esac
  shift
done

require_docker
compose_placeholders
compose_cmd --observability
"${COMPOSE[@]}" logs "${ARGS[@]}" "${SERVICES[@]}"
