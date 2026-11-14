"""An evaluation run started from the admin API computes exactly what the CLI gate does
(same code path, `evaluate_split`), on the real corpus and the committed baseline."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.admin import PREFIX
from evaluation.run import BASELINE_PATH
from tests.support import AuthedClient


def test_api_eval_run_matches_the_baseline(
    db_app_factory: Callable[..., FastAPI], sqlite_database_url: str, corpus_index_dir: Path
) -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    app = db_app_factory(sqlite_database_url, index_dir=corpus_index_dir)
    with TestClient(app) as client:
        api = AuthedClient.create(client)
        run = api.post(f"{PREFIX}/eval-runs").json()
        api.run(app.state.eval_service.wait)
        done = api.get(f"{PREFIX}/eval-runs/{run['id']}").json()
    assert done["status"] == "succeeded", done["error"]
    assert done["index_version"] == baseline["index_version"]
    for metric in ("p@5", "pass_rate", "false_validation_rate", "mrr"):
        assert done["scorecard"][metric] == pytest.approx(baseline[metric], abs=1e-4), metric
    assert done["summary"]["split"] == "dev"
    low = done["summary"]["low_confidence"]
    assert low, "the analyst list is part of every API run"
    assert {"id", "why", "confidence", "question"} <= set(low[0])
