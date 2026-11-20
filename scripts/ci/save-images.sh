#!/usr/bin/env bash
# save-images.sh OUT_DIR: save the images built by `docker buildx bake` (deploy/docker/
# docker-bake.hcl) so later jobs test, and the release publishes, these exact bits.
set -euo pipefail
OUT="${1:?usage: save-images.sh OUT_DIR}"
mkdir -p "$OUT"
v="$(docker run --rm --network none rag-index:build cat /index/manifest.json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["index_version"])')"
docker tag rag-index:build "rag-index:$v"
docker save rag-api:local rag-web:local rag-index:build "rag-index:$v" | gzip -1 >"$OUT/images.tar.gz"
echo "INDEX_VERSION=$v" >"$OUT/images.env"
docker image inspect rag-api:local rag-web:local rag-index:build \
  --format '{{index .RepoTags 0}} {{.Id}} {{.Size}}' >"$OUT/images.txt"
echo "index_version=$v" >>"${GITHUB_OUTPUT:-/dev/null}"
echo "saved $(du -h "$OUT/images.tar.gz" | cut -f1) to $OUT (index $v)"
