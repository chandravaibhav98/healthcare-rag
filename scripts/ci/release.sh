#!/usr/bin/env bash
# release.sh TAG: cut a release from images main CI already tested and published
# (release.yml, `release`). Nothing is rebuilt: the tag's commit must have passed CI on
# main, which published <image>:sha-<commit>; those manifests get the release tag.
#
#   REGISTRY  e.g. ghcr.io/<owner> (lower case)   required
#   OUT       output directory (default artifacts/release)
#   WAIT_MINUTES  how long to wait for main CI to publish sha-<commit> (default 0). A tag
#             pushed together with its commit races that run; release.yml waits 60.
#
# Writes to OUT: healthcare-rag-TAG.yaml (prod overlay, images pinned by digest),
# release-manifest.json, sbom-<image>.spdx.json, notes.md.
set -euo pipefail
export SYFT_CHECK_FOR_APP_UPDATE=false
TAG="${1:?usage: release.sh vX.Y.Z}"
: "${REGISTRY:?}"
OUT="${OUT:-artifacts/release}"
ROOT="$(git rev-parse --show-toplevel)"
SHA="$(git rev-list -n 1 "$TAG")"
mkdir -p "$OUT/kustomize"

digest_of() {
  docker buildx imagetools inspect "$1" --format '{{json .Manifest}}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])'
}

declare -A DIGEST
for name in rag-api rag-web rag-index; do
  src="$REGISTRY/$name:sha-$SHA"
  deadline=$(( $(date +%s) + ${WAIT_MINUTES:-0} * 60 ))
  until docker buildx imagetools inspect "$src" >/dev/null 2>&1; do
    if (( $(date +%s) >= deadline )); then
      echo "error: $src does not exist. $TAG ($SHA) must be a commit that passed CI on main." >&2
      exit 1
    fi
    echo "waiting for main CI to publish $src ..."; sleep 30
  done
  docker buildx imagetools create --tag "$REGISTRY/$name:$TAG" "$src"
  DIGEST[$name]="$(digest_of "$REGISTRY/$name:$TAG")"
  [[ "${DIGEST[$name]}" == "$(digest_of "$src")" ]] || { echo "error: digest changed while tagging $name" >&2; exit 1; }
  syft -q "registry:$REGISTRY/$name@${DIGEST[$name]}" -o "spdx-json=$OUT/sbom-$name.spdx.json"
  echo "$name:$TAG = ${DIGEST[$name]}"
done
# The index version is whatever the published index image says it is (no rebuild, no guess).
docker pull --quiet "$REGISTRY/rag-index@${DIGEST[rag-index]}" >/dev/null
INDEX_VERSION="$(docker run --rm --network none "$REGISTRY/rag-index@${DIGEST[rag-index]}" cat /index/manifest.json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["index_version"])')"

# The prod overlay with every image pinned by digest: what the platform applies.
REL="$(realpath --relative-to="$OUT/kustomize" "$ROOT/deploy/k8s/overlays/prod")"
cat >"$OUT/kustomize/kustomization.yaml" <<YAML
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [$REL]
# The prod overlay names its images ghcr.io/OWNER/<image>:CHANGE-ME; replace them whole.
images:
  - { name: ghcr.io/OWNER/rag-api, newName: $REGISTRY/rag-api, digest: ${DIGEST[rag-api]} }
  - { name: ghcr.io/OWNER/rag-web, newName: $REGISTRY/rag-web, digest: ${DIGEST[rag-web]} }
  - { name: ghcr.io/OWNER/rag-index, newName: $REGISTRY/rag-index, digest: ${DIGEST[rag-index]} }
YAML
kubectl kustomize "$OUT/kustomize" >"$OUT/healthcare-rag-$TAG.yaml"
grep -Eq "CHANGE-ME|OWNER/" "$OUT/healthcare-rag-$TAG.yaml" && { echo "error: an image tag placeholder survived rendering" >&2; exit 1; }

python3 - "$OUT/release-manifest.json" <<PY
import json, sys
json.dump({"tag": "$TAG", "commit": "$SHA", "index_version": "$INDEX_VERSION",
           "images": {n: {"repository": "$REGISTRY/" + n, "digest": d} for n, d in
                      [("rag-api", "${DIGEST[rag-api]}"), ("rag-web", "${DIGEST[rag-web]}"),
                       ("rag-index", "${DIGEST[rag-index]}")]}},
          open(sys.argv[1], "w"), indent=2)
PY

BASELINE="$(git -C "$ROOT" show "$SHA:backend/evaluation/baseline.json")"
cat >"$OUT/notes.md" <<MD
## Healthcare Guidelines RAG Assistant $TAG

Synthetic corpus, **not for clinical use**. Commit \`$SHA\`, index \`$INDEX_VERSION\`.
Every image below passed the full CI pipeline on \`main\` for this commit and was promoted
without a rebuild.

| Image | Digest |
| --- | --- |
| \`$REGISTRY/rag-api:$TAG\` | \`${DIGEST[rag-api]}\` |
| \`$REGISTRY/rag-web:$TAG\` | \`${DIGEST[rag-web]}\` |
| \`$REGISTRY/rag-index:$TAG\` | \`${DIGEST[rag-index]}\` |

**Deploy:** \`kubectl apply -f healthcare-rag-$TAG.yaml\` (the prod overlay, images pinned
by digest; set the host name and secret store first, see \`deploy/README.md\`).
**SBOMs:** \`sbom-<image>.spdx.json\` (SPDX, Syft).

<details><summary>Evaluation baseline at this commit (dev pool)</summary>

\`\`\`json
$BASELINE
\`\`\`
</details>
MD
echo "release $TAG ready in $OUT"
