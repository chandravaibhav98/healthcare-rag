"""`/qa` routes. In Phase 0 they are contract-only stubs that return 501.

The routes exist now so that the OpenAPI snapshot, the generated frontend client
and the contract tests can all be built against the real v1 shape before the
pipeline exists. Phase 3 replaces the handler body with a call to `QAService`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.errors import problem_responses
from app.api.schemas.qa import QARequest, QAResponse

router = APIRouter(tags=["qa"])

_DESCRIPTION = (
    "Answer a question strictly from the indexed guidelines. Every answer is scored "
    "for evidential support; weakly supported answers are withheld with "
    "`status: needs_review` (ADR-0007). **Synthetic corpus — not for clinical use.**"
)


async def answer_question(body: QARequest) -> QAResponse:
    """Phase 0 stub: validates the request against contract v1, then reports 501."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="The QA pipeline is implemented in Phase 3; this route currently serves the v1 contract only.",
    )


_RESPONSES = problem_responses(422, 501)

router.add_api_route(
    "/api/v1/qa",
    answer_question,
    methods=["POST"],
    response_model=QAResponse,
    operation_id="answer_question",
    summary="Answer a question with validated citations",
    description=_DESCRIPTION,
    responses=_RESPONSES,
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
)
