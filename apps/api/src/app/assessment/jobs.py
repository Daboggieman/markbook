"""Bulk-import worker job (Phase 3 — spec §6.4, §12, ADR 003/D6).

Row-level partial success: valid rows are applied, invalid rows are reported
per CSV row number in the job result. The apply path is exactly the web
path's (`AssessmentService._apply_rows`) with source='import' — one code
path, two front doors, one ledger.

The jobs table carries no RLS (school_id is a data column there), so the job
row is loaded before the tenant context is set; everything downstream of it
runs with `app.school_id` set from the job row.

Failure settlement runs in its OWN transaction, deliberately: if the apply
step died on a database error the original transaction is aborted and cannot
record anything — marking the row failed from a fresh session is the only
way the job ever leaves `running`.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.access.service import Actor
from app.assessment.service import AssessmentService
from app.platform.db import get_sessionmaker, set_tenant_context
from app.platform.errors import ProblemError
from app.platform.logging import get_logger
from app.platform.models import Job

log = get_logger("import_scores")


async def import_scores(ctx: dict, *, job_id: str) -> None:
    """Arq job function (registered in apps/worker/worker.py).

    `ctx` is Arq's per-job context — unused; the durable state is the jobs
    row. A row found already `succeeded`/`failed` is a re-delivery after the
    settlement landed: skip. A row found `running` means a previous attempt
    died mid-transaction — its work rolled back, so re-run from scratch.
    """
    maker = get_sessionmaker()
    try:
        async with maker() as session:
            async with session.begin():
                job = await session.get(Job, UUID(job_id))
                if job is None:
                    log.error("import_job_missing", job_id=job_id)
                    return
                if job.status in ("succeeded", "failed"):
                    log.info("import_job_already_settled", job_id=job_id, status=job.status)
                    return
                if job.school_id is None:
                    raise ValueError("import job has no school_id — cannot run outside a tenant")
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
                result = await AssessmentService(session).apply_import(
                    school_id,
                    UUID(str(params["assessment_id"])),
                    str(params.get("csv") or ""),
                    actor,
                )
                job.status = "succeeded"
                job.result = result
                job.finished_at = datetime.now(UTC)
    except ProblemError as exc:
        log.warning("import_job_failed", job_id=job_id, code=exc.code, detail=exc.detail)
        await _settle_failed(maker, job_id, exc.detail)
    except Exception as exc:
        log.exception("import_job_crashed", job_id=job_id)
        await _settle_failed(maker, job_id, f"unexpected error: {exc}")


async def _settle_failed(maker, job_id: str, error: str) -> None:
    """Mark the job failed from a fresh transaction (see module docstring)."""
    async with maker() as session:
        async with session.begin():
            job = await session.get(Job, UUID(job_id))
            if job is None or job.status in ("succeeded", "failed"):
                return
            job.status = "failed"
            job.error = error[:2000]
            job.finished_at = datetime.now(UTC)
