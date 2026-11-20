"""`/qa` routes: thin HTTP adapters over `QAService` (plan §2.2, ADR-0006).

The pipeline is CPU-bound (FAISS, BM25, sentence scoring), so it runs in the threadpool
and never blocks the event loop.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    OPTIONAL_AUTH,
    OptionalUserDep,
    QAServiceDep,
    RequestIdDep,
    SettingsDep,
    enforce_qa_rate_limit,
)
from app.api.errors import problem_responses
from app.api.schemas.qa import QARequest, QAResponse

router = APIRouter(tags=["qa"])

_DESCRIPTION = (
    "Answer a question strictly from the indexed guidelines. Every answer is scored "
    "for evidential support; weakly supported answers are withheld with "
    "`status: needs_review` and the best candidate sources (ADR-0007). "
    "**Synthetic corpus — not for clinical use.**"
)


async def answer_question(
    body: QARequest,
    service: QAServiceDep,
    request_id: RequestIdDep,
    user: OptionalUserDep,
    settings: SettingsDep,
) -> QAResponse:
    # Anonymous access is a deployment choice (ADR-0008): on for the demo, off in prod.
    if user is None and not settings.allow_anonymous_qa:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = str(user.id) if user else None
    return await run_in_threadpool(service.answer, body, request_id, user_id)


_RESPONSES = problem_responses(401, 422, 429, 500, 503)
_DEPS = [Depends(enforce_qa_rate_limit)]

router.add_api_route(
    "/api/v1/qa",
    answer_question,
    methods=["POST"],
    response_model=QAResponse,
    operation_id="answer_question",
    summary="Answer a question with validated citations",
    description=_DESCRIPTION,
    responses=_RESPONSES,
    dependencies=_DEPS,
    openapi_extra=OPTIONAL_AUTH,
)
# Spec alias (brief D1). Same handler, so behaviour cannot diverge (ADR-0006).
router.add_api_route(
    "/qa",
    answer_question,
    methods=["POST"],
    response_model=QAResponse,
    operation_id="answer_question_alias",
    summary="Alias of POST /api/v1/qa (path required by the project brief)",
    description=_DESCRIPTION,
    responses=_RESPONSES,
    dependencies=_DEPS,
    openapi_extra=OPTIONAL_AUTH,
)
