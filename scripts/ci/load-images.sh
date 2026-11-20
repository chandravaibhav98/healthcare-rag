#!/usr/bin/env bash
# load-images.sh DIR: load the images saved by save-images.sh (rag-api:local,
# rag-web:local, rag-index:build and rag-index:<index_version>).
set -euo pipefail
DIR="${1:?usage: load-images.sh DIR}"
gunzip -c "$DIR/images.tar.gz" | docker load
cat "$DIR/images.env"
