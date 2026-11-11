"""Arq job enqueue helper (ADR 003 — Redis-backed queue, durable jobs table).

The `jobs` row is the durable record (survives Redis loss); this helper is
the Redis trigger that makes a running worker pick the job up. Enqueue is
best-effort by design: if Redis is unreachable the row stays `queued`, the
caller still returns 202, and the backlog is visible in the jobs table
instead of lost. A queued job with a dead Redis is the documented degraded
mode — it is picked up on manual re-enqueue or worker restart recovery,
never silently dropped.
"""

from urllib.parse import urlparse
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings

from app.platform.config import get_settings
from app.platform.logging import get_logger

log = get_logger("jobs")


def redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


async def enqueue_job(job_id: UUID, function_name: str) -> bool:
    """Trigger an Arq job function by name with `job_id=str(...)` kwarg.

    The function name must match one registered in apps/worker/worker.py's
    JOB_FUNCTIONS (Arq dispatches by __name__). Returns False instead of
    raising when Redis is unreachable — the durable jobs row keeps the work.
    """
    settings = get_settings()
    try:
        pool = await create_pool(redis_settings_from_url(settings.redis_url))
    except Exception as exc:
        log.warning("job_enqueue_unreachable", job_id=str(job_id), error=str(exc))
        return False
    try:
        await pool.enqueue_job(function_name, job_id=str(job_id))
    except Exception as exc:
        log.warning("job_enqueue_failed", job_id=str(job_id), error=str(exc))
        return False
    finally:
        await pool.aclose()
    return True
