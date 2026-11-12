"""Admin API (plan Phase 5). Reviewers read; admins also change things.

RBAC is declared on each route with `ReviewerDep` / `AdminDep`, and
`tests/api/test_rbac_matrix.py` asserts every route under /api/v1/admin against an
explicit role table, so a new route without a matrix entry fails CI.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.admin import audit, config, evals, index, queries, stats
from app.api.routes.admin._common import PREFIX

__all__ = ["PREFIX", "router"]

router = APIRouter()
for module in (stats, queries, evals, index, config, audit):
    router.include_router(module.router)
