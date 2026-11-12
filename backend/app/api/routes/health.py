"""Kubernetes-style probes and build information.

* `/healthz`: liveness. The process is up. It never checks dependencies, so a slow
  database cannot make the orchestrator restart healthy pods.
* `/readyz`: readiness. Ready only when a verified index is loaded (and, when DATABASE_URL is
  set, the database answers). Returns 503 when not ready so load balancers drain the pod.
* `/version`: build, contract and index versions, used by the UI footer and smoke tests.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app import __version__
from app.api.deps import RegistryDep
from app.api.schemas.health import CheckState, Liveness, Readiness, VersionInfo
from app.api.schemas.qa import CONTRACT_VERSION
from app.rag.analysis import ANALYSIS_VERSION

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=Liveness, operation_id="liveness", summary="Liveness probe")
async def healthz() -> Liveness:
    return Liveness()


@router.get(
    "/readyz",
    response_model=Readiness,
    operation_id="readiness",
    summary="Readiness probe",
    responses={503: {"model": Readiness, "description": "Not ready"}},
)
async def readyz(request: Request, response: Response, registry: RegistryDep) -> Readiness:
    db = request.app.state.db
    database: CheckState = "not_configured" if db is None else ("ok" if await db.ping() else "fail")
    checks: dict[str, CheckState] = {
        "index": "ok" if registry.is_loaded else "fail",
        # Optional (stateless mode); when configured it must answer, or the pod is drained.
        "database": database,
    }
    ready = all(state != "fail" for state in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    version = registry.current().index_version if registry.is_loaded else None
    return Readiness(status="ready" if ready else "not_ready", checks=checks, index_version=version)


@router.get("/version", response_model=VersionInfo, operation_id="version", summary="Build info")
async def version(registry: RegistryDep) -> VersionInfo:
    return VersionInfo(
        build_version=__version__,
        contract_version=CONTRACT_VERSION,
        index_version=registry.current().index_version if registry.is_loaded else None,
        analysis_version=ANALYSIS_VERSION,
    )
