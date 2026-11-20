"""Property-based contract fuzzing (plan Phase 7): Schemathesis generates valid and
invalid requests for every operation in the live OpenAPI document and checks that the
API never answers 5xx, returns only documented status codes and content types, and
that every response body matches its schema.

Runs in-process against the ASGI app (SQLite, fixture index, an admin token), so it is
deterministic enough for CI. Long-running background jobs (index rebuild, evaluation
runs) are excluded here; tests/api covers them.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import pytest
import schemathesis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis.errors import Unsatisfiable
from schemathesis import GenerationMode, checks

from scripts.export_schemas import OPENAPI_PATH
from tests.support import AuthedClient

#: Examples per operation and mode. CI raises it via SCHEMATHESIS_MAX_EXAMPLES.
MAX_EXAMPLES = int(os.environ.get("SCHEMATHESIS_MAX_EXAMPLES", "20"))

# Checks that do not apply here (each would flag documented, intended behaviour):
# * positive_data_acceptance: some rules span fields and cannot be written in JSON Schema
#   (confidence weights sum to 1, a "correct" verdict needs chunk ids, a stats window of at
#   most 366 days), so a schema-valid body can still be a correct 422.
# * negative_data_rejection: FastAPI ignores unknown query parameters by design.
# Every other check runs, including not_a_server_error, status_code_conformance,
# content_type_conformance, response_schema_conformance and ignored_auth.
EXCLUDED_CHECKS = {
    GenerationMode.POSITIVE: [checks.positive_data_acceptance],
    GenerationMode.NEGATIVE: [checks.negative_data_rejection],
}

EXCLUDED = {
    ("POST", "/api/v1/admin/index/rebuild"),
    ("POST", "/api/v1/admin/eval-runs"),
}


@pytest.fixture
def fuzz_app(db_app_factory: Any, sqlite_database_url: str) -> Iterator[tuple[FastAPI, str]]:
    app: FastAPI = db_app_factory(
        sqlite_database_url, rate_limit_qa="1000000/minute", login_rate_limit="1000000/minute"
    )
    with TestClient(app) as client:
        token = AuthedClient.create(client).personas
        admin = next(p for r, p in token.items() if r.value == "admin")
        yield app, admin.token


def _operations() -> list[tuple[str, str]]:
    """Operations from the committed snapshot (collection time needs no running app;
    test_snapshots.py guarantees the snapshot matches the live document)."""
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    ops = [
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if (method.upper(), path) not in EXCLUDED
    ]
    return sorted(ops)


@pytest.mark.parametrize("mode", [GenerationMode.POSITIVE, GenerationMode.NEGATIVE], ids=str)
@pytest.mark.parametrize(("method", "path"), _operations(), ids=lambda v: str(v))
def test_api_conforms_to_its_contract(
    fuzz_app: tuple[FastAPI, str], method: str, path: str, mode: GenerationMode
) -> None:
    app, token = fuzz_app
    operation = schemathesis.openapi.from_asgi("/openapi.json", app)[path][method]
    headers = {"Authorization": f"Bearer {token}"}

    @given(case=operation.as_strategy(generation_mode=mode))
    @settings(
        max_examples=MAX_EXAMPLES,
        deadline=None,
        database=None,  # reproducible in CI; failures print the falsifying example
        suppress_health_check=list(HealthCheck),
    )
    def run(case: Any) -> None:
        case.call_and_validate(headers=headers, excluded_checks=EXCLUDED_CHECKS[mode])

    try:
        run()
    except Unsatisfiable:
        pytest.skip(f"no {mode.value} inputs exist for {method} {path}")
