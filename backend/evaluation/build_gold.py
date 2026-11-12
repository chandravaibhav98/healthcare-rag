"""Build the gold dev/test files from the two YAML authoring sources (ADR-0001, Phase 4).

    uv run python -m evaluation.build_gold            # write the JSONL files + manifest
    uv run python -m evaluation.build_gold --check    # exit 1 if they are stale

People edit only the YAML files; everything else is derived deterministically:

* `gold_source.yaml`      → `gold_dev.jsonl`  (ids q-0001…, development pool)
* `gold_test_source.yaml` → `gold_test.jsonl` (ids q-1001…, held-out test-v2)

Every chunk id must exist in the index, and the manifest pins the `index_version` the
labels were made against plus the SHA-256 of both sources (re-chunking means re-annotating).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Final

import yaml

from app.core.config import get_settings
from app.rag.index.manifest import read_manifest
from evaluation.schemas import GoldItem, QuestionKind, Split

DATASETS: Final = Path(__file__).resolve().parent / "datasets"
SOURCE: Final = DATASETS / "gold_source.yaml"
TEST_SOURCE: Final = DATASETS / "gold_test_source.yaml"
DEV_PATH: Final = DATASETS / "gold_dev.jsonl"
TEST_PATH: Final = DATASETS / "gold_test.jsonl"
MANIFEST_PATH: Final = DATASETS / "gold_manifest.json"
TEST_ID_OFFSET: Final = 1000


def _items_from_source(
    source: dict[str, list[dict[str, Any]]],
) -> list[tuple[dict[str, Any], bool]]:
    out: list[tuple[dict[str, Any], bool]] = []
    for topic, entries in source.items():
        for entry in entries:
            kind = QuestionKind(entry["kind"])
            answerable = kind is not QuestionKind.UNANSWERABLE
            g2 = list(entry.get("g2") or [])
            g1 = list(entry.get("g1") or [])
            overlap = set(g1) & set(g2)
            if overlap:
                raise ValueError(
                    f"{entry['q']!r}: chunk listed as both g1 and g2: {sorted(overlap)}"
                )
            item = {
                "question": entry["q"],
                "topic": topic,
                "kind": kind.value,
                "answerable": answerable,
                "relevant_chunk_ids": g2 + g1,
                "grades": {**dict.fromkeys(g2, 2), **dict.fromkeys(g1, 1)},
                "expected_keywords": list(entry.get("kw") or []),
            }
            out.append((item, bool(entry.get("seen", False))))
    return out


def build(index_dir: Path) -> tuple[list[GoldItem], dict[str, Any]]:
    manifest = read_manifest(index_dir)
    known = {c["chunk_id"] for c in _chunk_records(index_dir)}
    gold: list[GoldItem] = []
    for split, path, offset in ((Split.DEV, SOURCE, 0), (Split.TEST, TEST_SOURCE, TEST_ID_OFFSET)):
        raw = _items_from_source(yaml.safe_load(path.read_text(encoding="utf-8")))
        for n, (item, _) in enumerate(raw, start=1):
            missing = [c for c in item["relevant_chunk_ids"] if c not in known]
            if missing:
                raise ValueError(f"{item['question']!r}: chunk ids not in the index: {missing}")
            gold.append(
                GoldItem.model_validate({"id": f"q-{offset + n:04d}", "split": split.value, **item})
            )
    questions = [g.question for g in gold]
    dupes = [q for q, n in Counter(questions).items() if n > 1]
    if dupes:
        raise ValueError(f"duplicate questions across the gold files: {dupes}")
    meta = {
        "index_version": manifest["index_version"],
        "source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE, TEST_SOURCE)
        },
        "counts": _counts(gold),
    }
    return gold, meta


def _chunk_records(index_dir: Path) -> list[dict[str, Any]]:
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _counts(gold: list[GoldItem]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in Split:
        items = [g for g in gold if g.split is split]
        out[split.value] = {
            "total": len(items),
            "answerable": sum(g.answerable for g in items),
            "by_kind": dict(sorted(Counter(g.kind.value for g in items).items())),
        }
    return out


def render(gold: list[GoldItem], meta: dict[str, Any]) -> dict[Path, str]:
    def lines(split: Split) -> str:
        return "".join(
            json.dumps(g.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for g in gold
            if g.split is split
        )

    return {
        DEV_PATH: lines(Split.DEV),
        TEST_PATH: lines(Split.TEST),
        MANIFEST_PATH: json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the gold dev/test splits.")
    parser.add_argument("--index", type=Path, default=None, help="index dir (default INDEX_DIR)")
    parser.add_argument("--check", action="store_true", help="fail if the outputs are stale")
    args = parser.parse_args(argv)
    gold, meta = build(args.index or get_settings().index_dir)
    outputs = render(gold, meta)
    if args.check:
        stale = [
            p.name
            for p, text in outputs.items()
            if not p.exists() or p.read_text(encoding="utf-8") != text
        ]
        if stale:
            print(f"stale gold files {stale}: run `uv run python -m evaluation.build_gold`")
            return 1
        print("Gold splits are up to date.")
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(DATASETS.parents[1])}")
    print(json.dumps(meta["counts"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
