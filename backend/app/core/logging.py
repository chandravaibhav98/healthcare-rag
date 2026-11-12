"""Structured logging (structlog). JSON in production, readable console output in dev.

Every event carries the `request_id` bound by `RequestContextMiddleware`, so all log
lines of one request can be correlated. Request bodies are never logged automatically:
the question text appears only in the opt-in query log (ADR-0009).
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s", force=True)
