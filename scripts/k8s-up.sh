#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# k8s-up.sh: the full stack on a local kind cluster (plan §4 Phase 9). Parity: k8s-up.ps1.
#
#   1. kind cluster (1 control plane + 2 workers, deploy/k8s/kind/cluster.yaml)
#   2. platform: Envoy Gateway (Gateway API) and metrics-server (for the HPA)
#   3. images: build, tag by content, load into the nodes
#   4. secrets: overlays/local/secrets.env, generated once (git-ignored)
#   5. apply overlays/local, then wait: postgres → db-migrate → api, web → db-seed
#   6. smoke test through the gateway: http://localhost:8088
#
# Idempotent: re-running rebuilds and rolls only what changed. Scripted checks of
# rolling updates and index rollback: scripts/k8s-verify.sh.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/containers.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/k8s-up.sh [--overlay local|prod] [--recreate] [--no-build]
                         [--existing-cluster] [--no-smoke] [--ci] [-h|--help]

  --overlay local     kind cluster + Envoy Gateway + in-cluster PostgreSQL (default)
  --overlay prod      Render deploy/k8s/overlays/prod to artifacts/k8s-prod.yaml only;
                      production is applied by the release pipeline (Phase 10)
  --recreate          Delete and recreate the kind cluster first
  --no-build          Use the existing local images
  --existing-cluster  Use the current K8S_CONTEXT as is: no kind, no platform install
                      (the Gateway API implementation must already be there)
  --no-smoke          Skip the smoke test through the gateway
  --ci                Plain output (no colours)

Environment: K8S_CONTEXT (default kind-healthcare-rag), K8S_BASE_URL (default
http://127.0.0.1:8088), K8S_IMAGE_LOADER (non-kind clusters), DOCKER_BUILD_ARGS.
USAGE
}

OVERLAY=local; RECREATE=0; BUILD=1; EXISTING=0; SMOKE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --overlay) [[ $# -ge 2 ]] || die "--overlay needs a value"; OVERLAY="$2"; shift ;;
    --recreate) RECREATE=1 ;;
    --no-build) BUILD=0 ;;
    --existing-cluster) EXISTING=1 ;;
    --no-smoke) SMOKE=0 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
BASE_URL="${K8S_BASE_URL:-http://127.0.0.1:8088}"
OVERLAY_DIR="${K8S_OVERLAY_DIR:-$K8S_DIR/overlays/local}"

if [[ "$OVERLAY" == prod ]]; then
  require_cmd kubectl "Install kubectl: https://kubernetes.io/docs/tasks/tools/"
  mkdir -p "$REPO_ROOT/artifacts"
  run kubectl kustomize "$K8S_DIR/overlays/prod" -o "$REPO_ROOT/artifacts/k8s-prod.yaml"
  log_ok "rendered artifacts/k8s-prod.yaml"
  log_info "Production is applied by the release pipeline (plan Phase 10), not from a laptop."
  exit 0
fi
[[ "$OVERLAY" == local ]] || die "--overlay must be local or prod"

require_docker
require_cmd kubectl "Install kubectl: https://kubernetes.io/docs/tasks/tools/"
require_cmd curl "curl is needed for the readiness checks."

# --- 1. cluster -------------------------------------------------------------------------
if ((EXISTING)); then
  log_step "Cluster: existing context $K8S_CONTEXT"
  require_kubectl
else
  require_cmd kind "Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
  [[ "$K8S_CONTEXT" == "kind-$KIND_CLUSTER" ]] || die "with kind, K8S_CONTEXT must be kind-$KIND_CLUSTER (or use --existing-cluster)"
  log_step "Cluster: kind '$KIND_CLUSTER'"
  if ((RECREATE)) && kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
    run kind delete cluster --name "$KIND_CLUSTER"
  fi
  if kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
    log_ok "cluster exists"
  else
    run kind create cluster --config "$K8S_DIR/kind/cluster.yaml" --wait 180s
  fi

  # --- 2. platform ------------------------------------------------------------------------
  log_step "Platform: Envoy Gateway $ENVOY_GATEWAY_VERSION, metrics-server $METRICS_SERVER_VERSION"
  if ! kube -n envoy-gateway-system get deployment envoy-gateway >/dev/null 2>&1; then
    run kube apply --server-side --force-conflicts \
      -f "https://github.com/envoyproxy/gateway/releases/download/$ENVOY_GATEWAY_VERSION/install.yaml"
  fi
  run kube -n envoy-gateway-system wait deployment/envoy-gateway --for=condition=Available --timeout=300s
  # The gateway's data plane runs here; the app's NetworkPolicies admit this namespace.
  run kube label namespace envoy-gateway-system healthcare-rag/gateway=true --overwrite
  if ! kube -n kube-system get deployment metrics-server >/dev/null 2>&1; then
    run kube apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/$METRICS_SERVER_VERSION/components.yaml"
    # kind's kubelets use self-signed serving certificates.
    run kube -n kube-system patch deployment metrics-server --type=json \
      -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
  fi
  log_ok "platform ready"
fi

# --- 3. images --------------------------------------------------------------------------
if ((BUILD)); then
  build_images local
else
  INDEX_VERSION="$(image_index_version rag-index:build)"
  [[ -n "$INDEX_VERSION" ]] || die "no rag-index:build image; run without --no-build"
fi
API_TAG="$(content_tag rag-api:local)"; WEB_TAG="$(content_tag rag-web:local)"
run docker tag rag-api:local "rag-api:$API_TAG"
run docker tag rag-web:local "rag-web:$WEB_TAG"
log_step "Loading images into the cluster"
load_images "rag-api:$API_TAG" "rag-web:$WEB_TAG" "rag-index:$INDEX_VERSION" postgres:18-alpine

# --- 4. secrets -------------------------------------------------------------------------
SECRETS="$K8S_DIR/overlays/local/secrets.env"
if [[ ! -f "$SECRETS" ]]; then
  pg="$(random_hex 24)"
  {
    echo "POSTGRES_PASSWORD=$pg"
    echo "JWT_SECRET=$(random_hex 32)"
    echo "SEED_ADMIN_PASSWORD=$(random_hex 12)"
    echo "DATABASE_URL=postgresql+asyncpg://rag:$pg@postgres:5432/rag"
  } >"$SECRETS"
  chmod 600 "$SECRETS" 2>/dev/null || true
  log_ok "created deploy/k8s/overlays/local/secrets.env (git-ignored)"
fi

# --- 5. apply ---------------------------------------------------------------------------
GEN="$REPO_ROOT/artifacts/k8s-local"
mkdir -p "$GEN"
REL="$(realpath --relative-to="$GEN" "$OVERLAY_DIR" 2>/dev/null || python3 -c 'import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))' "$OVERLAY_DIR" "$GEN")"
cat >"$GEN/kustomization.yaml" <<YAML
# Generated by scripts/k8s-up.sh: the local overlay with this build's image tags.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [$REL]
images:
  - { name: rag-api, newTag: "$API_TAG" }
  - { name: rag-web, newTag: "$WEB_TAG" }
  - { name: rag-index, newTag: "$INDEX_VERSION" }
YAML
log_step "Applying the local overlay (index $INDEX_VERSION)"
# Jobs are immutable: remove the previous runs so this build's migration and seed run.
run kube -n "$K8S_NAMESPACE" delete job db-migrate db-seed --ignore-not-found
run kube apply -k "$GEN"

log_step "Waiting for the rollout"
run kube -n "$K8S_NAMESPACE" rollout status statefulset/postgres --timeout=300s
run kube -n "$K8S_NAMESPACE" wait job/db-migrate --for=condition=Complete --timeout=600s
run kube -n "$K8S_NAMESPACE" rollout status deployment/api --timeout=300s
run kube -n "$K8S_NAMESPACE" rollout status deployment/web --timeout=300s
run kube -n "$K8S_NAMESPACE" wait job/db-seed --for=condition=Complete --timeout=600s
run kube -n "$K8S_NAMESPACE" wait gateway/hcrag --for=condition=Programmed --timeout=300s
log_ok "api, web and postgres ready; migrations and seed done"

# --- 6. smoke ---------------------------------------------------------------------------
if ((SMOKE)); then
  log_step "Smoke test through the gateway ($BASE_URL)"
  wait_http "$BASE_URL/readyz" 120 || die "the gateway does not answer on $BASE_URL (try scripts/k8s-port-forward.sh)"
  bash "$REPO_ROOT/scripts/smoke.sh" --base-url "$BASE_URL"
fi

log_step "Ready"
log_info "Web app: $BASE_URL   (admin@example.org / SEED_ADMIN_PASSWORD in deploy/k8s/overlays/local/secrets.env)"
log_info "Status: scripts/k8s-status.sh · Checks: scripts/k8s-verify.sh · Remove: scripts/k8s-down.sh"
