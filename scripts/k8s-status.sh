#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# k8s-status.sh: what is running, and does it answer. Parity: k8s-status.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/k8s-status.sh [--ci] [-h|--help]

Shows nodes, workloads, jobs, autoscaling, disruption budgets, network policies,
the Gateway and the served index_version (K8S_BASE_URL, default http://127.0.0.1:8088).
USAGE
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
BASE_URL="${K8S_BASE_URL:-http://127.0.0.1:8088}"
require_kubectl

log_step "Nodes ($K8S_CONTEXT)"
kube get nodes -o wide
log_step "Workloads in $K8S_NAMESPACE"
kube -n "$K8S_NAMESPACE" get deployments,statefulsets,pods,jobs -o wide
log_step "Autoscaling, disruption budgets, network policies"
kube -n "$K8S_NAMESPACE" get hpa,pdb,networkpolicies
log_step "Gateway"
kube -n "$K8S_NAMESPACE" get gateways,httproutes
log_step "Images"
kube -n "$K8S_NAMESPACE" get deployment api -o jsonpath='{range .spec.template.spec.initContainers[*]}{"  init "}{.name}{": "}{.image}{"\n"}{end}{range .spec.template.spec.containers[*]}{"  "}{.name}{": "}{.image}{"\n"}{end}'
kube -n "$K8S_NAMESPACE" get deployment web -o jsonpath='{range .spec.template.spec.containers[*]}{"  "}{.name}{": "}{.image}{"\n"}{end}'
log_step "Through the gateway ($BASE_URL)"
if body="$(curl -fsS --max-time 5 "$BASE_URL/readyz" 2>/dev/null)"; then
  log_ok "readyz: $body"
else
  log_warn "no answer on $BASE_URL (scripts/k8s-port-forward.sh is the fallback)"
fi
