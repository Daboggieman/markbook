"""Markbook worker entrypoint (spec §12, decisions D4/D6).

Same codebase as the API, started with a different entrypoint. Jobs are
Redis-backed via Arq (default, ADR 003); job status is durably recorded in
the `jobs` table so it survives Redis loss.

Run locally:  python apps/worker/worker.py
Run in docker: compose service `worker`.
"""

from collections.abc import Callable
from typing import Any

from app.platform.config import get_settings
from app.platform.job_queue import redis_settings_from_url
from app.platform.logging import configure_logging, get_logger


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(level=get_settings().log_level, fmt=get_settings().log_format)
    log = get_logger("worker")
    log.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    log = get_logger("worker")
    log.info("worker_stopped")


# Job functions are registered here as they are added (Phase 2+).
# Each job is idempotent and re-runnable (spec §12).
from app.assessment.jobs import import_scores  # noqa: E402  — registered below

JOB_FUNCTIONS: list[Callable[..., Any]] = [
    import_scores,
]

# Periodic jobs are added when the first one ships (the nightly audit chain
# verifier, Phase 1).


class WorkerSettings:
    """Arq worker settings. Job functions registered here run on this process."""

    functions = JOB_FUNCTIONS
    on_startup = startup
    on_shutdown = shutdown
    redis_settings: Any = None  # populated from config at import time (below)
    max_jobs = 10
    job_timeout = 600  # seconds
    keep_result = 3600


WorkerSettings.redis_settings = redis_settings_from_url(get_settings().redis_url)


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
