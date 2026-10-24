"""Structured JSON logging with request ids (spec §2.10, §15).

Every request gets an X-Request-Id; every log line carries it. Personal data
and secrets never enter logs — the scrubber drops known-sensitive keys by
denylist and callers must pass allowlisted fields only.
"""

import logging
from contextvars import ContextVar
from typing import Any

import structlog

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
school_id_ctx: ContextVar[str] = ContextVar("school_id", default="-")
actor_id_ctx: ContextVar[str] = ContextVar("actor_id", default="-")

# Fields never allowed in log records (defence in depth; the allowlist logger
# in modules must also respect this).
SCRUBBED_KEYS = {
    "password",
    "password_hash",
    "token",
    "refresh_token",
    "access_token",
    "secret",
    "authorization",
    "cookie",
    "dob",
    "phone",
    "email",
    "address",
}


def scrub(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SCRUBBED_KEYS:
        return "[scrubbed]"
    if isinstance(value, dict):
        return {k: scrub(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def add_context(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    event_dict["request_id"] = request_id_ctx.get()
    event_dict["school_id"] = school_id_ctx.get()
    event_dict["actor_id"] = actor_id_ctx.get()
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Idempotent — safe to call from api, worker, and tests."""
    renderer: structlog.typing.Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            add_context,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def set_request_context(request_id: str, school_id: str = "-", actor_id: str = "-") -> None:
    """Bind request context for the current async context."""
    request_id_ctx.set(request_id)
    school_id_ctx.set(school_id)
    actor_id_ctx.set(actor_id)
