"""Application factory.

Phase 0 wires only the contract (routes, schemas, problem+json). Phase 3 adds the
lifespan (index loading), middleware (request IDs, metrics) and health routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app import __version__
from app.api.errors import PROBLEM_JSON, register_exception_handlers
from app.api.routes.qa import router as qa_router
from app.api.schemas.qa import CONTRACT_VERSION

API_TITLE = "Healthcare Guidelines RAG Assistant"
API_DESCRIPTION = (
    "Citation-first, evidence-validated question answering over guideline documents.\n\n"
    "> ⚠️ All guideline content is **synthetic**. Not for clinical use."
)


def _build_openapi(app: FastAPI) -> dict[str, Any]:
    """OpenAPI with error responses declared as `application/problem+json`.

    FastAPI documents every response model under `application/json`. The real error
    media type is set here so the published contract matches the wire (ADR-0006).
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=API_TITLE,
        version=CONTRACT_VERSION,
        description=API_DESCRIPTION,
        routes=app.routes,
    )
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            for code, response in operation.get("responses", {}).items():
                content = response.get("content", {})
                if code[:1] in {"4", "5"} and "application/json" in content:
                    response["content"] = {PROBLEM_JSON: content["application/json"]}
    app.openapi_schema = schema
    return schema


def create_app() -> FastAPI:
    # `version` is the CONTRACT version, not the build version, so the committed
    # OpenAPI snapshot changes only when the contract does.
    app = FastAPI(title=API_TITLE, version=CONTRACT_VERSION, description=API_DESCRIPTION)
    app.state.build_version = __version__
    register_exception_handlers(app)
    app.include_router(qa_router)
    app.openapi = lambda: _build_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
