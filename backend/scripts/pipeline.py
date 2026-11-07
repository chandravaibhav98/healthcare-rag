"""Index pipeline CLI, the spec's `scripts/pipeline.py` (plan §4 Phase 1).

    uv run python scripts/pipeline.py build   [--corpus DIR] [--out DIR]
    uv run python scripts/pipeline.py verify  [--index DIR] [--corpus DIR]
    uv run python scripts/pipeline.py inspect [--index DIR] [--doc ID | --chunk ID] [--stats] [--limit N]
    uv run python scripts/pipeline.py determinism [--corpus DIR] [--runs N] [--save-manifest FILE]
    uv run python scripts/pipeline.py ask "QUESTION" [--index DIR] [--top-k N] [--mode M] [--no-expansion]

Defaults come from Settings (CORPUS_DIR, INDEX_DIR, CHUNK_*, EMBEDDING_*).
Exit codes: 0 ok · 1 failure (invalid corpus, integrity or staleness problem).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from app.core.config import Settings
from app.domain.models import Chunk
from app.rag.ingestion.loader import CorpusError
from app.rag.pipeline import BuildConfig, IndexIntegrityError, build_index, load_index, verify_index
from app.rag.retrieval.hybrid import RetrievalMode
from app.rag.runtime import build_runtime


def _cmd_build(args: argparse.Namespace, settings: Settings) -> int:
    corpus = args.corpus or settings.corpus_dir
    out = args.out or settings.index_dir
    result = build_index(corpus, out, BuildConfig.from_settings(settings))
    m = result.manifest
    print(f"index_version  {m['index_version']}")
    print(f"documents      {m['counts']['documents']}")
    print(f"chunks         {m['counts']['chunks']}  ({m['counts']['tokens']} tokens)")
    print(f"corpus hash    {m['corpus']['hash'][:16]}…")
    print(f"written to     {out}")
    return 0


def _cmd_verify(args: argparse.Namespace, settings: Settings) -> int:
    index = args.index or settings.index_dir
    corpus = None if args.no_corpus else (args.corpus or settings.corpus_dir)
    problems = verify_index(index, corpus)
    for p in problems:
        print(f"FAIL  {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"OK    {index} matches its manifest" + ("" if corpus is None else " and the corpus"))
    return 0


def _pct(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _print_chunk(c: Chunk, full: bool) -> None:
    flag = " +overlap" if c.has_overlap else ""
    print(f"\n── {c.chunk_id}  [{c.token_count} tok{flag}]  {c.section}")
    body = c.text if full else (c.text[:280] + ("…" if len(c.text) > 280 else ""))
    print("   " + body.replace("\n", "\n   "))


def _cmd_inspect(args: argparse.Namespace, settings: Settings) -> int:
    idx = load_index(args.index or settings.index_dir)
    chunks = idx.chunks
    if args.chunk:
        match = [c for c in chunks if c.chunk_id == args.chunk]
        if not match:
            print(f"no chunk {args.chunk}", file=sys.stderr)
            return 1
        _print_chunk(match[0], full=True)
        return 0
    if args.doc:
        chunks = [c for c in chunks if c.doc_id == args.doc]
        if not chunks:
            print(f"no document {args.doc}", file=sys.stderr)
            return 1
        for c in chunks[: args.limit]:
            _print_chunk(c, full=True)
        return 0

    tokens = [c.token_count for c in chunks]
    per_doc = Counter(c.doc_id for c in chunks)
    cfg = idx.manifest["config"]["chunking"]
    print(
        f"index_version {idx.index_version}  ·  {len(per_doc)} documents  ·  {len(chunks)} chunks"
    )
    print(
        f"tokens/chunk  min {min(tokens)}  p10 {_pct(tokens, 0.1)}  median {int(statistics.median(tokens))}"
        f"  p90 {_pct(tokens, 0.9)}  max {max(tokens)}  (target {cfg['min_tokens']}–{cfg['max_tokens']})"
    )
    small = sum(t < cfg["min_tokens"] // 2 for t in tokens)
    large = sum(t > cfg["max_tokens"] for t in tokens)
    print(
        f"outliers      {small} below {cfg['min_tokens'] // 2} tokens · {large} above {cfg['max_tokens']}"
    )
    print(f"chunks/doc    min {min(per_doc.values())}  max {max(per_doc.values())}")
    print(
        "by org        "
        + "  ".join(f"{k} {v}" for k, v in sorted(Counter(c.source_org for c in chunks).items()))
    )
    if args.stats:
        return 0
    for c in chunks[: args.limit]:
        _print_chunk(c, full=False)
    return 0


def _cmd_determinism(args: argparse.Namespace, settings: Settings) -> int:
    """SC1: rebuild N times in separate processes, each with a different PYTHONHASHSEED."""
    corpus = (args.corpus or settings.corpus_dir).resolve()
    runs = max(2, args.runs)
    digests: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="hcrag-determinism-") as tmp:
        for run in range(runs):
            out = Path(tmp) / f"run-{run}"
            env = {**os.environ, "PYTHONHASHSEED": str(run * 7919 + 1), "PYTHONUTF8": "1"}
            proc = subprocess.run(  # noqa: S603  (fixed interpreter and script)
                [sys.executable, __file__, "build", "--corpus", str(corpus), "--out", str(out)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                print(proc.stderr, file=sys.stderr)
                return 1
            digests.append(
                {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
            )
        first_manifest = Path(tmp) / "run-0" / "manifest.json"
        version = json.loads(first_manifest.read_text(encoding="utf-8"))["index_version"]
        if args.save_manifest:
            args.save_manifest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(first_manifest, args.save_manifest)

    names = sorted(set().union(*digests))
    identical = True
    for name in names:
        values = {d.get(name, "<missing>") for d in digests}
        same = len(values) == 1
        identical &= same
        print(
            f"{'OK  ' if same else 'DIFF'}  {name:<16} {next(iter(values))[:16] if same else values}"
        )
    if identical:
        print(f"PASS  {runs} builds byte-identical · index_version {version}")
        return 0
    print(f"FAIL  builds differ across {runs} runs", file=sys.stderr)
    return 1


def _cmd_ask(args: argparse.Namespace, settings: Settings) -> int:
    """Phase 2 developer tool: retrieval + extractive answer (no validation until Phase 3)."""
    runtime = build_runtime(
        load_index(args.index or settings.index_dir),
        settings,
        mode=RetrievalMode(args.mode),
        expansion=False if args.no_expansion else None,
    )
    expanded = runtime.retriever.expand(args.question)
    hits = runtime.retriever.retrieve(args.question, args.top_k)
    print(f"index_version {runtime.index_version} · mode {args.mode} · top_k {args.top_k}")
    if expanded.added_terms:
        print(f"expanded with: {', '.join(expanded.added_terms)}")
    print("\nrank  score  dense sparse  chunk_id")
    for h in hits:
        d = h.dense_rank if h.dense_rank is not None else "-"
        s = h.sparse_rank if h.sparse_rank is not None else "-"
        print(f"{h.rank:>4}  {h.score:.3f}  {d!s:>5} {s!s:>6}  {h.chunk.chunk_id}")
    answer = runtime.generator.generate(args.question, hits)
    print("\nANSWER (unvalidated; validation arrives in Phase 3)")
    print("  " + (answer.text or "(no supporting sentence found)"))
    for c in answer.citations:
        ch = c.retrieved.chunk
        print(f"  [{c.citation_id}] {ch.source_org} · {ch.title} · {ch.section}  ({ch.chunk_id})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build the index from the corpus")
    b.add_argument("--corpus", type=Path)
    b.add_argument("--out", type=Path)

    v = sub.add_parser("verify", help="check artifact hashes and corpus freshness")
    v.add_argument("--index", type=Path)
    v.add_argument("--corpus", type=Path)
    v.add_argument("--no-corpus", action="store_true", help="skip the staleness check")

    i = sub.add_parser("inspect", help="summarise chunks or show a document/chunk")
    i.add_argument("--index", type=Path)
    group = i.add_mutually_exclusive_group()
    group.add_argument("--doc")
    group.add_argument("--chunk")
    i.add_argument("--stats", action="store_true", help="summary only")
    i.add_argument("--limit", type=int, default=10)

    d = sub.add_parser("determinism", help="rebuild N times with different hash seeds and compare")
    d.add_argument("--corpus", type=Path)
    d.add_argument("--runs", type=int, default=2)
    d.add_argument(
        "--save-manifest", type=Path, help="copy the manifest here (cross-OS comparison)"
    )

    a = sub.add_parser("ask", help="retrieve and extract an answer (developer tool)")
    a.add_argument("question")
    a.add_argument("--index", type=Path)
    a.add_argument("--top-k", type=int, default=5)
    a.add_argument("--mode", choices=[m.value for m in RetrievalMode], default="hybrid")
    a.add_argument("--no-expansion", action="store_true")

    args = parser.parse_args(argv)
    settings = Settings()
    handlers = {
        "build": _cmd_build,
        "verify": _cmd_verify,
        "inspect": _cmd_inspect,
        "determinism": _cmd_determinism,
        "ask": _cmd_ask,
    }
    try:
        return handlers[args.command](args, settings)
    except (CorpusError, IndexIntegrityError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
