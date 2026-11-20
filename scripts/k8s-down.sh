#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# k8s-down.sh: remove the local Kubernetes deployment. Parity: k8s-down.ps1.
# Default: delete the whole kind cluster. --namespace-only keeps the cluster and its
# platform (Envoy Gateway, metrics-server) and removes only the app and its data.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/k8s-down.sh [--namespace-only] [--ci] [-h|--help]

  --namespace-only   Delete only the healthcare-rag namespace (faster re-deploys)
  --ci               Plain output (no colours)
USAGE
}

NS_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace-only) NS_ONLY=1 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if ((NS_ONLY)); then
  require_kubectl
  log_step "Deleting namespace $K8S_NAMESPACE (database included)"
  run kube delete namespace "$K8S_NAMESPACE" --ignore-not-found --wait=true --timeout=180s
  log_ok "namespace removed; cluster kept"
  exit 0
fi

[[ "$K8S_CONTEXT" == "kind-$KIND_CLUSTER" ]] || die "refusing to delete a cluster that is not the local kind cluster ($K8S_CONTEXT); use --namespace-only"
require_cmd kind "Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
log_step "Deleting kind cluster '$KIND_CLUSTER'"
if kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
  run kind delete cluster --name "$KIND_CLUSTER"
  log_ok "cluster deleted"
else
  log_info "no such cluster: nothing to do"
fi
