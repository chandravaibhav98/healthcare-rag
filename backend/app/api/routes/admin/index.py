"""Index versions (list, activate, dev-only rebuild) and the corpus inventory."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, status

from app.api.deps import (
    MAX_OFFSET,
    ActorDep,
    AdminDep,
    DbDep,
    RegistryDep,
    ReviewerDep,
    SessionDep,
    SettingsDep,
)
from app.api.routes.admin._common import PREFIX, responses, state
from app.api.schemas.admin import DocumentOut, IndexVersionOut, Page, RebuildStatus
from app.db.models import IndexVersion
from app.rag.pipeline import IndexIntegrityError
from app.services import admin_service
from app.services.index_service import (
    IndexService,
    IndexVersionUnavailableError,
    RebuildInProgressError,
    UnknownIndexVersionError,
)

router = APIRouter(prefix=PREFIX, tags=["admin"])
VersionPath = Annotated[str, Path(pattern=r"^[0-9a-f]{6,32}$")]


def version_out(row: IndexVersion) -> IndexVersionOut:
    out = IndexVersionOut.model_validate(row)
    out.corpus_hash = (row.manifest.get("corpus") or {}).get("hash")
    out.config_hash = row.manifest.get("config_hash")
    return out


def rebuild_status(service: IndexService, allowed: bool) -> RebuildStatus:
    s = service.rebuild_state
    return RebuildStatus(
        allowed=allowed,
        running=s.running,
        started_at=s.started_at,
        finished_at=s.finished_at,
        last_version=s.last_version,
        last_error=s.last_error,
    )


@router.get(
    "/index/versions",
    response_model=Page[IndexVersionOut],
    operation_id="admin_list_index_versions",
    summary="Known index versions (newest first) and which one is active",
    responses=responses(422),
)
async def list_versions(
    _: ReviewerDep,
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> Page[IndexVersionOut]:
    service: IndexService = state(request, "index_service")
    rows = sorted(
        await service.versions(session), key=lambda r: (r.created_at, r.version), reverse=True
    )
    return Page(
        items=[version_out(r) for r in rows[offset : offset + limit]],
        total=len(rows),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/index/versions/{version}/activate",
    response_model=IndexVersionOut,
    operation_id="admin_activate_index_version",
    summary="Verify, load and activate an index version (hot swap, audited)",
    responses=responses(404, 409, 422),
)
async def activate_version(
    _: AdminDep, request: Request, session: SessionDep, actor: ActorDep, version: VersionPath
) -> IndexVersionOut:
    service: IndexService = state(request, "index_service")
    try:
        row = await service.activate(session, version, actor)
    except UnknownIndexVersionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Index version not found.") from exc
    except IndexVersionUnavailableError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Index {version} is not available in this deployment: its files were replaced "
            "by a later rollout. Roll the deployment back to that index image instead.",
        ) from exc
    except (IndexIntegrityError, FileNotFoundError) as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Index {version} failed verification: {exc}"
        ) from exc
    request.app.state.metrics.set_index(version)
    return version_out(row)


@router.get(
    "/index/rebuild",
    response_model=RebuildStatus,
    operation_id="admin_rebuild_status",
    summary="State of the last dev-only index rebuild",
    responses=responses(),
)
async def get_rebuild(_: AdminDep, request: Request, settings: SettingsDep) -> RebuildStatus:
    return rebuild_status(state(request, "index_service"), settings.index_rebuild_allowed)


@router.post(
    "/index/rebuild",
    response_model=RebuildStatus,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="admin_rebuild_index",
    summary="Rebuild the index from the corpus (development only; asynchronous)",
    description="Builds into INDEX_STORE_DIR/<version>/ and registers the version; it does "
    "NOT activate it. Disabled in production, where CI builds index images (ADR-0008).",
    responses=responses(409),
)
async def rebuild(
    _: AdminDep, request: Request, db: DbDep, actor: ActorDep, settings: SettingsDep
) -> RebuildStatus:
    if not settings.index_rebuild_allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Index rebuilds are disabled in this environment; publish versions through CI.",
        )
    service: IndexService = state(request, "index_service")
    try:
        service.start_rebuild(db, actor)
    except RebuildInProgressError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "A rebuild is already running.") from exc
    return rebuild_status(service, True)


_DOC_SORTS = {"doc_id", "chunk_count", "effective_date", "source_org"}


@router.get(
    "/documents",
    response_model=Page[DocumentOut],
    operation_id="admin_list_documents",
    summary="Corpus inventory of the active index, with chunk counts",
    responses=responses(422),
)
async def list_documents(
    _: ReviewerDep,
    registry: RegistryDep,
    source_org: str | None = None,
    topic: str | None = None,
    status_: Annotated[Literal["current", "superseded"] | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=200, description="Text in the title.")] = None,
    sort: Literal["doc_id", "chunk_count", "effective_date", "source_org"] = "doc_id",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> Page[DocumentOut]:
    docs = admin_service.documents(registry.current().index)
    if source_org:
        docs = [d for d in docs if d.source_org.lower() == source_org.lower()]
    if topic:
        docs = [d for d in docs if topic in d.topics]
    if status_:
        docs = [d for d in docs if d.status == status_]
    if q:
        docs = [d for d in docs if q.lower() in d.title.lower()]
    docs.sort(key=lambda d: (getattr(d, sort), d.doc_id), reverse=order == "desc")
    return Page(
        items=[DocumentOut.model_validate(d) for d in docs[offset : offset + limit]],
        total=len(docs),
        limit=limit,
        offset=offset,
    )
