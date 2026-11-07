"""`manifest.json`: the identity card of an index build (SC1).

It records *what* was indexed (normalised corpus hashes), *how* (every config value that
changes the output) and *with what* (library versions), plus the SHA-256 of every
artifact. It contains no timestamps, absolute paths or host names, so two builds of
the same inputs produce byte-identical manifests on any machine.

    index_version = sha256(corpus_hash + config_hash + environment)[:12]
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, Final

from app.domain.models import Chunk, Document

MANIFEST_SCHEMA: Final = 1
MANIFEST_NAME: Final = "manifest.json"


def dump_json(obj: Any) -> bytes:
    """Canonical JSON: sorted keys, 2-space indent, UTF-8, LF-terminated."""
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def environment() -> dict[str, str]:
    # Python *minor* only: patch releases do not change outputs, and pinning the patch
    # would make the manifest differ between two correctly configured machines.
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "numpy": pkg_version("numpy"),
        "faiss-cpu": pkg_version("faiss-cpu"),
        "snowballstemmer": pkg_version("snowballstemmer"),
    }


def corpus_section(docs: Sequence[Document]) -> dict[str, Any]:
    documents = [
        {
            "doc_id": d.doc_id,
            "path": d.path,
            "sha256": d.sha256,
            "source_org": d.meta.source_org.value,
            "status": d.meta.status.value,
            "version": d.meta.version,
            "effective_date": d.meta.effective_date.isoformat(),
        }
        for d in sorted(docs, key=lambda d: d.path)
    ]
    digest = sha256_bytes("".join(f"{d['path']}\t{d['sha256']}\n" for d in documents).encode())
    return {"hash": digest, "documents": documents}


def build_manifest(
    docs: Sequence[Document],
    chunks: Sequence[Chunk],
    config: Mapping[str, Any],
    artifacts: Mapping[str, bytes],
) -> dict[str, Any]:
    corpus = corpus_section(docs)
    config_hash = sha256_bytes(dump_json(dict(config)))
    env = environment()
    identity = corpus["hash"] + config_hash + dump_json(env).decode("utf-8")
    return {
        "schema_version": MANIFEST_SCHEMA,
        "index_version": sha256_bytes(identity.encode("utf-8"))[:12],
        "corpus": corpus,
        "config": dict(config),
        "config_hash": config_hash,
        "environment": env,
        "counts": {
            "documents": len(docs),
            "chunks": len(chunks),
            "tokens": sum(c.token_count for c in chunks),
        },
        "artifacts": {
            name: {"sha256": sha256_bytes(data), "bytes": len(data)}
            for name, data in sorted(artifacts.items())
        },
    }


def read_manifest(index_dir: Path) -> dict[str, Any]:
    path = index_dir / MANIFEST_NAME
    if not path.is_file():
        raise FileNotFoundError(f"no {MANIFEST_NAME} in {index_dir}; build the index first")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema {data.get('schema_version')}")
    return data


def verify_artifacts(index_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """Return human-readable integrity problems (empty list = intact)."""
    problems: list[str] = []
    for name, meta in manifest["artifacts"].items():
        path = index_dir / name
        if not path.is_file():
            problems.append(f"missing artifact {name}")
            continue
        actual = sha256_bytes(path.read_bytes())
        if actual != meta["sha256"]:
            problems.append(f"{name}: sha256 {actual[:12]}… != manifest {meta['sha256'][:12]}…")
    return problems
