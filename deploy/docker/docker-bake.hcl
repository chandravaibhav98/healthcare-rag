# Build all three images in one call (plan §4 Phase 10, ADR-0016).
#
#   docker buildx bake -f deploy/docker/docker-bake.hcl --load            # local
#   docker buildx bake -f deploy/docker/docker-bake.hcl --load api web    # a subset
#
# CI sets CACHE=gha (BuildKit layer cache in GitHub's Actions cache, one scope per image)
# and GIT_SHA/SOURCE_URL for the OCI labels. Paths are relative to the repository root,
# which is where bake must be run from. The tags match what scripts/docker-up.* and
# scripts/k8s-up.* expect, so either can reuse these images with --no-build.

variable "TAG" { default = "local" }
variable "CACHE" { default = "" }
variable "GIT_SHA" { default = "" }
variable "SOURCE_URL" { default = "" }

function "cache_from" {
  params = [scope]
  result = CACHE == "gha" ? ["type=gha,scope=${scope}"] : []
}

function "cache_to" {
  params = [scope]
  result = CACHE == "gha" ? ["type=gha,mode=max,scope=${scope}"] : []
}

group "default" {
  targets = ["api", "web", "index"]
}

target "_common" {
  context = "."
  labels = {
    # null drops the label when the variable is unset (local builds).
    "org.opencontainers.image.revision" = GIT_SHA != "" ? GIT_SHA : null
    "org.opencontainers.image.source"   = SOURCE_URL != "" ? SOURCE_URL : null
  }
}

target "api" {
  inherits   = ["_common"]
  dockerfile = "deploy/docker/api.Dockerfile"
  tags       = ["rag-api:${TAG}"]
  cache-from = cache_from("api")
  cache-to   = cache_to("api")
}

target "web" {
  inherits   = ["_common"]
  dockerfile = "deploy/docker/web.Dockerfile"
  tags       = ["rag-web:${TAG}"]
  cache-from = cache_from("web")
  cache-to   = cache_to("web")
}

# Tagged rag-index:build; scripts/ci/save-images.sh adds rag-index:<index_version>.
target "index" {
  inherits   = ["_common"]
  dockerfile = "deploy/docker/index.Dockerfile"
  tags       = ["rag-index:build"]
  cache-from = cache_from("index")
  cache-to   = cache_to("index")
}
