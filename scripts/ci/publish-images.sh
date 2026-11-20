#!/usr/bin/env bash
# publish-images.sh: push the CI-tested images to the registry (release.yml, `publish`).
#
#   REGISTRY      e.g. ghcr.io/<owner> (lower case)          required
#   GIT_SHA       the commit the images were built from      required
#   INDEX_VERSION from images.env                             required
#   EXTRA_TAG     a moving tag, e.g. "main"                   optional
#   SIGN          "true": Cosign-sign each digest and attach its SBOM as an attestation
#                 (keyless via GitHub OIDC, or COSIGN_KEY for a key pair)
#   COSIGN_ARGS   extra flags for cosign sign/attest, e.g. "--tlog-upload=false
#                 --use-signing-config=false" for an offline test registry
#   OUT           output directory (default artifacts/release)
#
# Tags: rag-api / rag-web → sha-<sha> [+ EXTRA_TAG]; rag-index → <index_version>, sha-<sha>.
# Writes OUT/release-manifest.json (refs + digests) and OUT/sbom-<image>.spdx.json.
set -euo pipefail
export SYFT_CHECK_FOR_APP_UPDATE=false
: "${REGISTRY:?}" "${GIT_SHA:?}" "${INDEX_VERSION:?}"
OUT="${OUT:-artifacts/release}"
SIGN="${SIGN:-false}"
mkdir -p "$OUT"

digest_of() { # digest_of <ref>: the registry digest of a pushed tag
  docker buildx imagetools inspect "$1" --format '{{json .Manifest}}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])'
}

declare -A SOURCE=([rag-api]=rag-api:local [rag-web]=rag-web:local [rag-index]=rag-index:build)
declare -A DIGEST
for name in rag-api rag-web rag-index; do
  repo="$REGISTRY/$name"
  if [[ "$name" == rag-index ]]; then tags=("$INDEX_VERSION" "sha-$GIT_SHA")
  else tags=("sha-$GIT_SHA"); [[ -n "${EXTRA_TAG:-}" ]] && tags+=("$EXTRA_TAG"); fi
  for t in "${tags[@]}"; do
    docker tag "${SOURCE[$name]}" "$repo:$t"
    docker push --quiet "$repo:$t"
  done
  DIGEST[$name]="$(digest_of "$repo:${tags[0]}")"
  echo "pushed $repo:{$(IFS=,; echo "${tags[*]}")} @ ${DIGEST[$name]}"
  syft -q "docker:${SOURCE[$name]}" -o "spdx-json=$OUT/sbom-$name.spdx.json"
  if [[ "$SIGN" == true ]]; then
    key=(); [[ -n "${COSIGN_KEY:-}" ]] && key=(--key "$COSIGN_KEY")
    read -r -a extra <<<"${COSIGN_ARGS:-}"
    key+=("${extra[@]}")
    cosign sign --yes "${key[@]}" "$repo@${DIGEST[$name]}"
    cosign attest --yes "${key[@]}" --type spdxjson --predicate "$OUT/sbom-$name.spdx.json" "$repo@${DIGEST[$name]}"
  fi
done

python3 - "$OUT/release-manifest.json" <<PY
import json, sys
json.dump({
    "commit": "$GIT_SHA",
    "index_version": "$INDEX_VERSION",
    "signed": "$SIGN" == "true",
    "images": {
        "rag-api":   {"repository": "$REGISTRY/rag-api",   "digest": "${DIGEST[rag-api]}"},
        "rag-web":   {"repository": "$REGISTRY/rag-web",   "digest": "${DIGEST[rag-web]}"},
        "rag-index": {"repository": "$REGISTRY/rag-index", "digest": "${DIGEST[rag-index]}"},
    },
}, open(sys.argv[1], "w"), indent=2)
PY
echo "wrote $OUT/release-manifest.json"
