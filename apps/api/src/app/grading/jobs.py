"""Result-processing worker job (Phase 4 — spec §9, §12).

Same shape as assessment's import_scores: the jobs table carries no RLS, so
the job row is loaded before the tenant context is set; everything downstream
runs with `app.school_id` from the job row. Failure settlement runs in its
OWN transaction — and settles the RUN row too, not just the job row: the run
was marked `running` inside the aborted transaction, so without this it would
stay `running` forever after any failure (the run history is the
per-assessment record of record).

A run found already `succeeded`/`failed` is a re-delivery after settlement
landed: `apply_run` reports it without recomputing (determinism means a
recompute would be identical anyway — but the skip is cheaper and honest).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.access.service import Actor
from app.grading.models import ResultProcessingRun
from app.grading.service import GradingService
from app.platform.db import get_sessionmaker, set_tenant_context
from app.platform.errors import ProblemError
from app.platform.logging import get_logger
from app.platform.models import Job

log = get_logger("process_results")


async def process_results(ctx: dict, *, job_id: str) -> None:
    """Arq job function (registered in apps/worker/worker.py)."""
    maker = get_sessionmaker()
    try:
        async with maker() as session:
            async with session.begin():
                job = await session.get(Job, UUID(job_id))
                if job is None:
                    log.error("process_job_missing", job_id=job_id)
                    return
                if job.status in ("succeeded", "failed"):
                    log.info("process_job_already_settled", job_id=job_id, status=job.status)
                    return
                if job.school_id is None:
                    raise ValueError("process job has no school_id — cannot run outside a tenant")
                school_id = job.school_id
                await set_tenant_context(session, str(school_id))
                job.status = "running"
                await session.flush()

                actor = Actor(
                    user_id=job.created_by or uuid4(),
                    school_id=school_id,
                    token_version=0,
                    session_id=uuid4(),
                )
                params = job.params or {}
                result = await GradingService(session).apply_run(
                    school_id,
                    UUID(str(params["run_id"])),
                    actor,
                )
                job.status = "succeeded"
                job.result = result
                job.finished_at = datetime.now(UTC)
    except ProblemError as exc:
        log.warning("process_job_failed", job_id=job_id, code=exc.code, detail=exc.detail)
        await _settle_failed(maker, job_id, exc.detail)
    except Exception:
        log.exception("process_job_crashed", job_id=job_id)
        await _settle_failed(maker, job_id, "unexpected error (see worker logs)")


async def _settle_failed(maker: async_sessionmaker[AsyncSession], job_id: str, error: str) -> None:
    """Mark job AND run failed from a fresh transaction (see module docstring).

    The run UPDATE needs the tenant context — result_processing_runs has RLS
    and this fresh transaction would otherwise match zero rows, silently."""
    async with maker() as session:
        async with session.begin():
            job = await session.get(Job, UUID(job_id))
            if job is None or job.status in ("succeeded", "failed"):
                return
            job.status = "failed"
            job.error = error[:2000]
            job.finished_at = datetime.now(UTC)
            params = job.params or {}
            run_id = params.get("run_id")
            if run_id is None or job.school_id is None:
                return
            await set_tenant_context(session, str(job.school_id))
            await session.execute(
                update(ResultProcessingRun)
                .where(
                    ResultProcessingRun.id == UUID(str(run_id)),
                    ResultProcessingRun.school_id == job.school_id,
                )
                .values(status="failed", error=error[:2000], finished_at=datetime.now(UTC))
            )
