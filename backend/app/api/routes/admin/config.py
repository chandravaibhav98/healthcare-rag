"""Runtime tuning: threshold, retrieval floor and confidence weights (audited)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import ActorDep, AdminDep, ReviewerDep, SessionDep
from app.api.routes.admin._common import PREFIX, responses, state
from app.api.schemas.admin import ConfigOut, ConfigUpdate, ConfigValues
from app.rag.validation.confidence import ConfidenceWeights
from app.services.config_service import ConfigConflictError, ConfigService, ConfigView
from app.services.tuning import Tuning

router = APIRouter(prefix=PREFIX, tags=["admin"])


def config_out(view: ConfigView) -> ConfigOut:
    return ConfigOut(
        version=view.version,
        values=ConfigValues.model_validate(view.tuning.to_values()),
        updated_at=view.row.created_at if view.row else None,
        updated_by=view.row.created_by if view.row else None,
        comment=view.row.comment if view.row else None,
    )


@router.get(
    "/config",
    response_model=ConfigOut,
    operation_id="admin_get_config",
    summary="Current runtime tuning (version 0 = environment defaults)",
    responses=responses(),
)
async def get_config(_: ReviewerDep, request: Request, session: SessionDep) -> ConfigOut:
    service: ConfigService = state(request, "config_service")
    return config_out(await service.current(session))


@router.put(
    "/config",
    response_model=ConfigOut,
    operation_id="admin_update_config",
    summary="Change runtime tuning (audited; other pods follow within CONFIG_POLL_SECONDS)",
    responses=responses(409, 422),
)
async def put_config(
    _: AdminDep, request: Request, session: SessionDep, actor: ActorDep, body: ConfigUpdate
) -> ConfigOut:
    service: ConfigService = state(request, "config_service")
    v = body.values
    tuning = Tuning(
        threshold=v.threshold,
        retrieval_floor=v.retrieval_floor,
        weights=ConfidenceWeights(
            coverage=v.weights.coverage,
            query_support=v.weights.query_support,
            retrieval=v.weights.retrieval,
        ),
    )
    try:
        view = await service.update(
            session,
            expected_version=body.expected_version,
            tuning=tuning,
            comment=body.comment,
            actor=actor,
        )
    except ConfigConflictError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Configuration changed meanwhile (now version {exc.current_version}); reload "
            "and retry.",
        ) from exc
    return config_out(view)
