"""`POST /api/v1/escalations`: a user asks a reviewer to check an answer (Phase 6).

Abstentions already land in the review queue; this lets a user flag a *validated* answer
they doubt, or add context to an abstention. The answer is identified by the request ID
the user received. Anonymous users may escalate anonymous answers; an answer that
belongs to a signed-in user can only be escalated by that user (others get 404, so the
endpoint reveals nothing about other people's questions). Escalating twice is harmless.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import (
    ActorDep,
    OptionalUserDep,
    SessionDep,
    enforce_qa_rate_limit,
)
from app.api.errors import problem_responses
from app.api.schemas.escalation import EscalationRequest, EscalationResponse
from app.core.redaction import redact
from app.db.base import utcnow
from app.repositories import audit
from app.repositories import query_log as query_repo

router = APIRouter(tags=["qa"])


@router.post(
    "/api/v1/escalations",
    response_model=EscalationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="escalate_answer",
    summary="Ask for human review of an answer",
    responses=problem_responses(404, 422, 429, 503),
    dependencies=[Depends(enforce_qa_rate_limit)],
)
async def escalate(
    body: EscalationRequest,
    request: Request,
    session: SessionDep,
    user: OptionalUserDep,
    actor: ActorDep,
) -> EscalationResponse:
    # The query log is written off the request path; make sure this pod's rows are in.
    await request.app.state.query_log_writer.flush()
    row = await query_repo.get_by_request_id(session, body.request_id)
    if row is None or (row.user_id is not None and (user is None or user.id != row.user_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No answer with this request ID.")
    first = row.escalated_at is None
    if first:
        row.escalated_at = utcnow()
    if body.note:
        row.escalation_note = redact(body.note).text
    audit.record(
        session,
        actor,
        "query.escalated" if first else "query.escalation_updated",
        target_type="query",
        target_id=str(row.id),
        details={"status": row.status, "has_note": bool(body.note)},
    )
    await session.commit()
    assert row.escalated_at is not None  # noqa: S101  (set above)
    return EscalationResponse(request_id=body.request_id, escalated_at=row.escalated_at)
