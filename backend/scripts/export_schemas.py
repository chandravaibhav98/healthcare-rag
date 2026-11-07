"""Export the committed contract snapshots, or check that they are current.

    uv run python scripts/export_schemas.py           # (re)write snapshots
    uv run python scripts/export_schemas.py --check   # exit 1 if any snapshot is stale

Snapshots are committed so that (a) contract changes are visible in code review,
(b) the frontend client can be generated without a running server and (c) CI can
fail when the code and the published contract disagree.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.main import create_app
from evaluation.schemas import GoldItem

BACKEND_DIR = Path(__file__).resolve().parents[1]
OPENAPI_PATH = BACKEND_DIR / "openapi.json"
GOLD_SCHEMA_PATH = BACKEND_DIR / "evaluation" / "datasets" / "gold.schema.json"


def render_json(document: dict[str, Any]) -> str:
    """Stable, LF-terminated JSON. Key order is left to the generator, which is deterministic."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def render_openapi() -> str:
    return render_json(create_app().openapi())


def render_gold_schema() -> str:
    schema = GoldItem.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "gold.schema.json"
    return render_json(schema)


SNAPSHOTS: dict[Path, Callable[[], str]] = {
    OPENAPI_PATH: render_openapi,
    GOLD_SCHEMA_PATH: render_gold_schema,
}


def stale_snapshots() -> list[Path]:
    return [
        path
        for path, render in SNAPSHOTS.items()
        if not path.exists() or path.read_text(encoding="utf-8") != render()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="fail if any snapshot is stale")
    args = parser.parse_args(argv)

    if args.check:
        stale = stale_snapshots()
        for path in stale:
            print(f"STALE: {path.relative_to(BACKEND_DIR)}", file=sys.stderr)
        if stale:
            print("Run: uv run python scripts/export_schemas.py", file=sys.stderr)
            return 1
        print("Contract snapshots are up to date.")
        return 0

    for path, render in SNAPSHOTS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(), encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(BACKEND_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
