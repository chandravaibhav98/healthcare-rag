"""RBAC matrix (plan Phase 5 exit criterion): every admin route × every role.

The table is the policy. `test_matrix_covers_every_admin_route` fails when a route is
added without deciding who may call it, so the policy cannot silently drift.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import pytest

from app.api.routes.admin import PREFIX
from app.core.security import Role
from tests.support import AuthedClient

R, A = Role.REVIEWER, Role.ADMIN
MATRIX: Final[dict[tuple[str, str], Role]] = {
    ("GET", "/stats"): R,
    ("GET", "/queries"): R,
    ("GET", "/queries/{query_id}"): R,
    ("GET", "/reviews"): R,
    ("POST", "/reviews/{query_id}"): R,
    ("GET", "/reviews/export/gold.jsonl"): R,
    ("GET", "/eval-runs"): R,
    ("POST", "/eval-runs"): A,
    ("GET", "/eval-runs/{run_id}"): R,
    ("GET", "/index/versions"): R,
    ("POST", "/index/versions/{version}/activate"): A,
    ("GET", "/index/rebuild"): A,
    ("POST", "/index/rebuild"): A,
    ("GET", "/documents"): R,
    ("GET", "/config"): R,
    ("PUT", "/config"): A,
    ("GET", "/audit-log"): A,
}
PATH_VALUES: Final = {
    "{query_id}": str(uuid.uuid4()),
    "{run_id}": str(uuid.uuid4()),
    "{version}": "abcdef123456",  # pragma: allowlist secret (a fake index version)
}
CALLERS: Final[list[Role | None]] = [None, Role.USER, Role.REVIEWER, Role.ADMIN]


def _concrete(path: str) -> str:
    for placeholder, value in PATH_VALUES.items():
        path = path.replace(placeholder, value)
    return PREFIX + path


def _no_op_runner(*_: Any) -> dict[str, Any]:
    return {"scorecard": {}}


def test_matrix_covers_every_admin_route(lite_api: AuthedClient) -> None:
    documented = {
        (method.upper(), path.removeprefix(PREFIX))
        for path, item in lite_api.app.openapi()["paths"].items()
        if path.startswith(PREFIX)
        for method in item
    }
    assert documented == set(MATRIX), (
        f"missing from MATRIX: {sorted(documented - set(MATRIX))}; "
        f"stale in MATRIX: {sorted(set(MATRIX) - documented)}"
    )


@pytest.mark.parametrize("caller", CALLERS, ids=lambda c: c.value if c else "anonymous")
@pytest.mark.parametrize(("method", "path"), sorted(MATRIX), ids=lambda v: str(v))
def test_role_matrix(lite_api: AuthedClient, method: str, path: str, caller: Role | None) -> None:
    lite_api.app.state.eval_service._runner = _no_op_runner  # no real evaluation here
    required = MATRIX[(method, path)]
    resp = lite_api.client.request(method, _concrete(path), headers=lite_api.as_(caller), json={})
    if caller is None:
        assert resp.status_code == 401, resp.text
        assert resp.headers["www-authenticate"] == "Bearer"
    elif not caller.allows(required):
        assert resp.status_code == 403, resp.text
        assert resp.headers["content-type"] == "application/problem+json"
    else:
        assert resp.status_code not in (401, 403), resp.text
    lite_api.run(lite_api.app.state.eval_service.wait)
    lite_api.run(lite_api.app.state.index_service.wait_for_rebuild)
