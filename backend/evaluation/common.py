"""Shared plumbing for the evaluation CLIs: loading gold splits, the index and runtimes,
run ids and report folders. Evaluation always runs in-process (no HTTP), through the
same `build_runtime` / `QAService` the API uses, so the numbers describe the product."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from app.core.config import Settings, get_settings
from app.rag.pipeline import LoadedIndex, load_index
from evaluation.build_gold import DEV_PATH, MANIFEST_PATH, TEST_PATH
from evaluation.schemas import GoldItem, Split, load_gold_jsonl

REPORTS_DIR: Final = Path(__file__).resolve().parent / "reports"


class GoldIndexMismatchError(RuntimeError):
    """The gold labels were made against a different index (ADR-0001 §6)."""


def load_split(split: Split | str) -> list[GoldItem]:
    split = Split(split)
    if split is Split.DEV:
        return load_gold_jsonl(DEV_PATH)
    if split is Split.TEST:
        return load_gold_jsonl(TEST_PATH)
    raise ValueError(split)


def check_index(index: LoadedIndex) -> str | None:
    """Fail fast if gold labels reference chunks the index lacks (ADR-0001 §6).

    Returns a warning when the index version differs from the labelled one but every
    labelled chunk id still exists (for example a manifest-only change)."""
    pinned = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["index_version"]
    known = {c.chunk_id for c in index.chunks}
    missing = sorted(
        {cid for split in Split for g in load_split(split) for cid in g.relevant_chunk_ids} - known
    )
    if missing:
        raise GoldIndexMismatchError(
            f"{len(missing)} labelled chunk ids are not in index {index.index_version} "
            f"(labels pinned to {pinned}); re-annotate: {missing[:5]}"
        )
    if index.index_version != pinned:
        return f"index {index.index_version} differs from labelled {pinned}; ids still match"
    return None


def load_checked_index(
    settings: Settings | None = None, index_dir: Path | None = None
) -> LoadedIndex:
    """Load the index and fail fast if the gold labels do not match it."""
    settings = settings or get_settings()
    index = load_index(index_dir or settings.index_dir)
    warning = check_index(index)
    if warning:
        print(f"warning: {warning}")
    return index


def new_run_dir(kind: str, split: Split | str, index_version: str, tag: str = "") -> Path:
    """`reports/<UTC stamp>-<kind>[-tag]-<split>-<index_version>[-n]/`, never overwritten."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = "-".join(p for p in (stamp, kind, tag, Split(split).value, index_version) if p)
    run_dir, n = REPORTS_DIR / name, 1
    while run_dir.exists():
        n += 1
        run_dir = REPORTS_DIR / f"{name}-{n}"
    run_dir.mkdir(parents=True)
    return run_dir


def git_revision() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
