"""Audit log (admin only)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminDep, SessionDep, page_params
from app.api.routes.admin._common import PREFIX, responses, to_page
from app.api.schemas.admin import AuditOut, Page
from app.repositories import audit as audit_repo
from app.repositories.paging import PageRequest

router = APIRouter(prefix=PREFIX, tags=["admin"])
AuditPage = Annotated[PageRequest, Depends(page_params(audit_repo.SORTABLE, "created_at"))]


@router.get(
    "/audit-log",
    response_model=Page[AuditOut],
    operation_id="admin_list_audit_log",
    summary="Who changed what, when (filter by action prefix, actor, time)",
    responses=responses(422),
)
async def list_audit(
    _: AdminDep,
    session: SessionDep,
    page: AuditPage,
    action: Annotated[str | None, Query(max_length=64, description="Prefix, e.g. 'auth.'")] = None,
    actor_email: str | None = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> Page[AuditOut]:
    f = audit_repo.AuditFilter(action=action, actor_email=actor_email, since=since, until=until)
    return to_page(await audit_repo.page(session, f, page), AuditOut.model_validate)
