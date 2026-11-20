#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# scripts/lib/containers.sh: image and Compose helpers shared by docker-*.sh and
# k8s-*.sh (Phases 8-9). Source after common.sh. PowerShell parity: Containers.psm1.
# -----------------------------------------------------------------------------
# shellcheck disable=SC2034

if [[ -n "${_HCRAG_CONTAINERS_LOADED:-}" ]]; then return 0; fi
_HCRAG_CONTAINERS_LOADED=1

COMPOSE_DIR="$REPO_ROOT/deploy/compose"
COMPOSE_ENV="$COMPOSE_DIR/.env"
DOCKER_DIR="$REPO_ROOT/deploy/docker"
# Git Bash rewrites arguments that look like POSIX paths ("/index/manifest.json")
# into Windows paths; container paths must reach Docker unchanged.
export MSYS_NO_PATHCONV=1

require_docker() {
  require_cmd docker "Install Docker Desktop (Windows/macOS) or Docker Engine (Linux)."
  docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop / the docker service."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 ('docker compose') is required."
}

# compose_cmd [--observability]: the docker compose invocation for this repository.
compose_cmd() {
  COMPOSE=(docker compose --project-directory "$COMPOSE_DIR" -f "$COMPOSE_DIR/docker-compose.yml")
  if [[ "${1:-}" == "--observability" ]]; then
    COMPOSE+=(-f "$COMPOSE_DIR/docker-compose.observability.yml")
  fi
}

random_hex() { # random_hex <bytes>
  if command -v openssl >/dev/null 2>&1; then openssl rand -hex "$1"
  else od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'; fi
}

# ensure_compose_env: create deploy/compose/.env from .env.example on first use, with
# every `generate` value replaced by a fresh random secret. Never overwrites.
ensure_compose_env() {
  if [[ -f "$COMPOSE_ENV" ]]; then return 0; fi
  local line key
  : >"$COMPOSE_ENV.tmp"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([A-Z_]+)=generate$ ]]; then
      key="${BASH_REMATCH[1]}"
      printf '%s=%s\n' "$key" "$(random_hex 24)" >>"$COMPOSE_ENV.tmp"
    else
      printf '%s\n' "$line" >>"$COMPOSE_ENV.tmp"
    fi
  done <"$COMPOSE_DIR/.env.example"
  mv "$COMPOSE_ENV.tmp" "$COMPOSE_ENV"
  chmod 600 "$COMPOSE_ENV" 2>/dev/null || true
  log_ok "created deploy/compose/.env with generated secrets (git-ignored)"
  # A database volume from an earlier .env still has the OLD password: PostgreSQL only
  # applies POSTGRES_PASSWORD when it initialises an empty data directory.
  if docker volume inspect healthcare-rag_pgdata >/dev/null 2>&1; then
    die "a database volume from an earlier deploy/compose/.env exists and keeps its old password. Run scripts/docker-down.sh --volumes (deletes the data), then retry."
  fi
}

# compose_placeholders: lets `down`/`logs` run when .env is missing (Compose resolves
# every ${VAR:?} even for commands that do not start containers).
compose_placeholders() {
  if [[ ! -f "$COMPOSE_ENV" ]]; then
    export POSTGRES_PASSWORD=unused JWT_SECRET=unused GRAFANA_ADMIN_PASSWORD=unused
  fi
}

# env_get <file> <KEY> / env_set <file> <KEY> <value>
env_get() { sed -n "s/^$2=//p" "$1" | tail -1; }
env_set() {
  if grep -q "^$2=" "$1"; then
    sed -i.bak "s|^$2=.*|$2=$3|" "$1" && rm -f "$1.bak"
  else
    printf '%s=%s\n' "$2" "$3" >>"$1"
  fi
}

# image_index_version <image>: the index_version recorded in an index image.
image_index_version() {
  docker run --rm --network none "$1" cat /index/manifest.json \
    | sed -n 's/.*"index_version": *"\([0-9a-f]*\)".*/\1/p' | head -1
}

# build_images <tag> [extra docker build args...]: build rag-api:<tag>, rag-web:<tag>
# and the index image, tagged rag-index:<index_version>. Sets INDEX_VERSION.
# DOCKER_BUILD_ARGS (env, optional): extra `docker build` flags for every image, e.g.
# "--network host" or "--build-arg HTTPS_PROXY=..." behind a corporate proxy.
build_images() {
  local tag="$1"; shift
  local extra=()
  [[ -n "${DOCKER_BUILD_ARGS:-}" ]] && read -r -a extra <<<"$DOCKER_BUILD_ARGS"
  set -- "${extra[@]}" "$@"
  log_step "Building images (tag $tag)"
  run docker build "$@" -f "$DOCKER_DIR/index.Dockerfile" -t rag-index:build "$REPO_ROOT"
  INDEX_VERSION="$(image_index_version rag-index:build)"
  [[ -n "$INDEX_VERSION" ]] || die "could not read index_version from rag-index:build"
  run docker tag rag-index:build "rag-index:$INDEX_VERSION"
  run docker build "$@" -f "$DOCKER_DIR/api.Dockerfile" -t "rag-api:$tag" "$REPO_ROOT"
  run docker build "$@" -f "$DOCKER_DIR/web.Dockerfile" -t "rag-web:$tag" "$REPO_ROOT"
  log_ok "rag-api:$tag  rag-web:$tag  rag-index:$INDEX_VERSION"
}

# --- Kubernetes (Phase 9) ---------------------------------------------------------------
KIND_CLUSTER="healthcare-rag"
K8S_CONTEXT="${K8S_CONTEXT:-kind-$KIND_CLUSTER}"
K8S_NAMESPACE="healthcare-rag"
K8S_DIR="$REPO_ROOT/deploy/k8s"
# Pinned platform components installed into the local kind cluster.
ENVOY_GATEWAY_VERSION="v1.10.0"
METRICS_SERVER_VERSION="v0.9.1"

kube() { kubectl --context "$K8S_CONTEXT" "$@"; }

require_kubectl() {
  require_cmd kubectl "Install kubectl: https://kubernetes.io/docs/tasks/tools/"
  kube version --request-timeout=10s >/dev/null 2>&1 \
    || die "kubectl cannot reach context '$K8S_CONTEXT'. Run scripts/k8s-up.sh first (or set K8S_CONTEXT)."
}

# content_tag <image>: a 12-hex tag derived from the image ID, so a rebuilt image gets a
# new tag (and pods roll) while an unchanged one keeps its tag (and nothing restarts).
content_tag() { docker image inspect --format '{{.Id}}' "$1" | sed 's/^sha256://' | cut -c1-12; }

# load_images <image...>: make local images available to the cluster.
#   kind-* context  → `kind load docker-image` (falls back to `ctr import` per node)
#   K8S_IMAGE_LOADER → `docker save <image> | $K8S_IMAGE_LOADER` (e.g. k3s, minikube)
#   otherwise       → assume the cluster pulls from a registry (images must be pushed)
load_images() {
  local img node loader=()
  if [[ "$K8S_CONTEXT" == kind-* ]]; then
    local cluster="${K8S_CONTEXT#kind-}"
    for img in "$@"; do
      if ! run kind load docker-image --name "$cluster" "$img"; then
        # Docker's containerd image store can export images kind load rejects; import
        # straight into each node's containerd instead.
        log_warn "kind load failed for $img; importing with ctr on each node"
        for node in $(kind get nodes --name "$cluster"); do
          docker save "$img" | docker exec -i "$node" ctr -n k8s.io images import --all-platforms - >/dev/null \
            || die "could not load $img into $node"
        done
      fi
    done
  elif [[ -n "${K8S_IMAGE_LOADER:-}" ]]; then
    read -r -a loader <<<"$K8S_IMAGE_LOADER"
    for img in "$@"; do
      log_info "docker save $img | $K8S_IMAGE_LOADER"
      docker save "$img" | "${loader[@]}" >/dev/null || die "could not load $img"
    done
  else
    log_warn "context $K8S_CONTEXT is not kind and K8S_IMAGE_LOADER is unset: the cluster must pull $*"
  fi
}

# wait_http <url> <seconds>: poll until the URL answers 2xx.
wait_http() {
  local url="$1" deadline=$((SECONDS + $2))
  until curl -fsS -o /dev/null --max-time 3 "$url" 2>/dev/null; do
    ((SECONDS < deadline)) || return 1
    sleep 2
  done
}

# venv_python: the backend virtualenv's interpreter (Linux/macOS or Windows layout).
venv_python() {
  local py="$BACKEND_DIR/.venv/bin/python"
  [[ -x "$py" ]] || py="$BACKEND_DIR/.venv/Scripts/python.exe"
  [[ -x "$py" ]] || die "backend/.venv is missing: run scripts/setup.sh first."
  printf '%s' "$py"
}
