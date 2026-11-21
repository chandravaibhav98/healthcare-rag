"""A disposable, seeded API for the Playwright suite (plan Phase 7).

    uv run python scripts/e2e_server.py --port 8100 [--data-dir artifacts/e2e] [--candidate-index]

Every start wipes its data directory (default `artifacts/e2e/`), migrates a fresh SQLite database, seeds the admin,
reviewer and user accounts plus a week of demo history (scripts/seed.py --demo), and
serves the API with generous rate limits. Playwright starts it through `webServer`
(e2e/playwright.config.ts) and scripts/load-test.* starts it (with its own data
directory) when no target is given; it is never used outside tests.

`--candidate-index` (the Phase 11 demo, E2E_CANDIDATE_INDEX=1) also builds a second index
with larger chunks (100-200 tokens, like scripts/k8s-verify's candidate) into the index
store, so the dashboard has a version to activate and roll back.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Final

E2E_PASSWORD: Final = "e2e-password-123"  # noqa: S105  (throwaway test accounts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Disposable data directory, wiped on start (default: artifacts/e2e).",
    )
    parser.add_argument(
        "--candidate-index",
        action="store_true",
        help="Also build a second index version (larger chunks) into the index store.",
    )
    args = parser.parse_args(argv)

    from app.core.config import REPO_ROOT

    data = args.data_dir or REPO_ROOT / "artifacts" / "e2e"
    if not data.is_absolute():
        data = REPO_ROOT / data
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    db_url = f"sqlite+aiosqlite:///{(data / 'app.db').as_posix()}"
    index_dir = Path(os.environ.get("INDEX_DIR") or REPO_ROOT / "artifacts" / "index")
    if not index_dir.is_absolute():
        index_dir = REPO_ROOT / index_dir
    if not (index_dir / "manifest.json").is_file():
        from app.rag.pipeline import build_index

        index_dir = data / "index"
        print(f"e2e: building the index into {index_dir}")
        build_index(REPO_ROOT / "corpus", index_dir)

    if args.candidate_index:
        _build_candidate(data / "indexes")

    os.environ.update(
        APP_ENV="development",
        DATABASE_URL=db_url,
        INDEX_DIR=str(index_dir),
        INDEX_STORE_DIR=str(data / "indexes"),
        ALLOW_INDEX_REBUILD="false",
        SEED_ADMIN_EMAIL="admin@example.org",
        SEED_ADMIN_PASSWORD=E2E_PASSWORD,
        RATE_LIMIT_QA="100000/minute",
        LOGIN_RATE_LIMIT="100000/minute",
        LOG_LEVEL="WARNING",
        LOG_FORMAT="console",
        ALLOW_ANONYMOUS_QA="true",
    )
    from app.core.config import get_settings
    from app.db.migrations import upgrade

    get_settings.cache_clear()
    upgrade(db_url)

    from scripts import seed

    seed.main(["--demo"])

    import uvicorn

    print(f"e2e: API ready on http://{args.host}:{args.port}")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        access_log=False,  # one line per request drowns the load test and E2E output
    )
    return 0


def _build_candidate(store: Path) -> None:
    """A second, equally valid index (another chunking) for the activate/rollback demo."""
    from app.core.config import REPO_ROOT
    from app.rag.ingestion.chunker import ChunkingConfig
    from app.rag.pipeline import BuildConfig, build_index

    tmp = store / ".candidate"
    result = build_index(
        REPO_ROOT / "corpus",
        tmp,
        BuildConfig(chunking=ChunkingConfig(min_tokens=100, max_tokens=200)),
    )
    version = str(result.manifest["index_version"])
    tmp.rename(store / version)
    print(f"e2e: candidate index {version} in {store}")


if __name__ == "__main__":
    sys.exit(main())
