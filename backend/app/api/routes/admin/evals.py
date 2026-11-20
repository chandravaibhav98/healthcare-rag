"""Evaluation runs on the dev pool, against the active index and live tuning."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import ActorDep, AdminDep, DbDep, ReviewerDep, SessionDep, page_params
from app.api.routes.admin._common import PREFIX, responses, state, to_page
from app.api.schemas.admin import EvalRunDetail, EvalRunOut, EvalStatus, Page
from app.repositories import eval_runs as run_repo
from app.repositories.paging import PageRequest
from app.services.eval_service import EvalAlreadyRunningError, EvalService

router = APIRouter(prefix=PREFIX, tags=["admin"])
RunPage = Annotated[
    PageRequest, Depends(page_params(run_repo.SORTABLE, "created_at", name="EvalRunSort"))
]


@router.get(
    "/eval-runs",
    response_model=Page[EvalRunOut],
    operation_id="admin_list_eval_runs",
    summary="Evaluation run history",
    responses=responses(422),
)
async def list_runs(
    _: ReviewerDep,
    session: SessionDep,
    page: RunPage,
    status_: Annotated[EvalStatus | None, Query(alias="status")] = None,
) -> Page[EvalRunOut]:
    return to_page(await run_repo.page(session, status_, page), EvalRunOut.model_validate)


@router.post(
    "/eval-runs",
    response_model=EvalRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="admin_start_eval_run",
    summary="Start an evaluation of the dev pool (asynchronous)",
    description="Poll `GET /eval-runs/{id}` for the result. One run at a time (409). The "
    "held-out test split is never evaluated from the API (ADR-0001).",
    responses=responses(409),
)
async def start_run(_: AdminDep, request: Request, db: DbDep, actor: ActorDep) -> EvalRunOut:
    service: EvalService = state(request, "eval_service")
    try:
        run = await service.start(db, actor)
    except EvalAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return EvalRunOut.model_validate(run)


@router.get(
    "/eval-runs/{run_id}",
    response_model=EvalRunDetail,
    operation_id="admin_get_eval_run",
    summary="One evaluation run with its full summary",
    responses=responses(404, 422),
)
async def get_run(_: ReviewerDep, session: SessionDep, run_id: uuid.UUID) -> EvalRunDetail:
    run = await run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluation run not found.")
    return EvalRunDetail.model_validate(run)
