#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# image-size.sh IMAGE MAX_MB: fail when the image's layers add up to MAX_MB or more.
#
# Sums `docker history` layer sizes in bytes. That is the uncompressed image as it runs,
# and it is the same under the classic and the containerd image store. `docker image
# inspect .Size` is not: with containerd (Docker Desktop; default for new Docker Engine
# 29 installs) it also counts the compressed blobs, so the same image reads ~20 % larger
# (manual test F-18: 443 MB inspect vs ~358 MB of layers).
# -----------------------------------------------------------------------------
set -euo pipefail
image="${1:?usage: image-size.sh IMAGE MAX_MB}"
max_mb="${2:?usage: image-size.sh IMAGE MAX_MB}"
bytes=$(docker history --human=false --format '{{.Size}}' "$image" | awk '{s += $1} END {printf "%d", s}')
mb=$((bytes / 1024 / 1024))
echo "$image: ${mb} MB of layers (budget < ${max_mb} MB)"
test "$bytes" -lt $((max_mb * 1024 * 1024))
