"""Document-generation worker jobs (Phase 5 — ADR 005).

Same shape as process_results: the jobs row loads before the tenant context
is set; generation runs with `app.school_id` from the job row; failure
settlement runs in its OWN transaction. `storage` and `renderer` arrive as
module-level callables so tests can monkeypatch them without a container.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.access.service import Actor
from app.documents.render import html_to_pdf
from app.documents.service import DocumentService
from app.documents.storage import get_storage
from app.platform.db import get_sessionmaker, set_tenant_context
from app.platform.errors import ProblemError
from app.platform.logging import get_logger
from app.platform.models import Job

log = get_logger("documents")

# Test seams — monkeypatch these, not the service.
_renderer = html_to_pdf
_storage_factory = get_storage


async def report_cards(ctx: dict, *, job_id: str) -> None:
    """Arq job function (registered in apps/worker/worker.py)."""
    await _run_generation(job_id, "report_cards")


async def transcripts(ctx: dict, *, job_id: str) -> None:
    """Arq job function (registered in apps/worker/worker.py)."""
    await _run_generation(job_id, "transcripts")


async def _run_generation(job_id: str, kind: str) -> None:
    maker = get_sessionmaker()
    try:
        async with maker() as session:
            async with session.begin():
                job = await session.get(Job, UUID(job_id))
                if job is None:
                    log.error("documents_job_missing", job_id=job_id)
                    return
                if job.status in ("succeeded", "failed"):
                    log.info("documents_job_already_settled", job_id=job_id, status=job.status)
                    return
                if job.school_id is None:
                    raise ValueError("documents job has no school_id — cannot run outside a tenant")
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
                service = DocumentService(session)
                if kind == "report_cards":
                    result = await service.generate_report_cards(
                        school_id,
                        job,
                        actor,
                        storage=_storage_factory(),
                        renderer=_renderer,
                    )
                else:  # kind == "transcripts"
                    result = await service.generate_transcript(
                        school_id,
                        job,
                        actor,
                        storage=_storage_factory(),
                        renderer=_renderer,
                    )
                job.status = "succeeded"
                job.result = result
                job.finished_at = datetime.now(UTC)
    except ProblemError as exc:
        log.warning("documents_job_failed", job_id=job_id, code=exc.code, detail=exc.detail)
        await _settle_failed(maker, job_id, exc.detail)
    except Exception:
        log.exception("documents_job_crashed", job_id=job_id)
        await _settle_failed(maker, job_id, "unexpected error (see worker logs)")


async def _settle_failed(maker: async_sessionmaker[AsyncSession], job_id: str, error: str) -> None:
    """Mark the job failed from a fresh transaction (same rationale as
    grading.jobs._settle_failed — the aborted transaction rolled back)."""
    async with maker() as session:
        async with session.begin():
            job = await session.get(Job, UUID(job_id))
            if job is None or job.status in ("succeeded", "failed"):
                return
            job.status = "failed"
            job.error = error[:2000]
            job.finished_at = datetime.now(UTC)
