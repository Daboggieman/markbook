"""Grading router â€” schemes, processing, results (Phase 4).

HTTP layer only; logic in `grading.service`. Every route declares `require`
(route-coverage guard); tenant-data routes use `get_actor_db` so the RLS
context is set from the JWT.

Permission mapping (the seeded catalogue has no dedicated scheme/results
read permission):
  - scheme read            â†’ assessments.view   (scheme config rides the
                                                  assessment-config surface)
  - scheme create/activate â†’ assessments.manage  (same lifecycle as templates)
  - processing             â†’ results.process     (spec's exact permission)
  - runs/results read      â†’ scores.view         (pre-publication results are
                                                  computed scores; a dedicated
                                                  results.view is a Phase 8
                                                  hardening candidate)
"""

# ruff: noqa: B008  â€” Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.dependency import get_actor_db, require
from app.access.service import Actor
from app.grading import schemas
from app.grading.service import GradingService

router = APIRouter(tags=["grading"])


# ---- grading schemes ---------------------------------------------------------


@router.post("/grading-schemes", response_model=schemas.SchemeResponse, status_code=201)
async def create_scheme(
    body: schemas.SchemeCreate,
    actor: Actor = Depends(require("assessments.manage")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.SchemeResponse:
    """Save a scheme definition: a new name starts at draft version 1, an
    existing name creates the NEXT version â€” editing never rewrites an
    existing version (spec Â§9.4)."""
    service = GradingService(session)
    row = await service.create_scheme(actor.school_id, body, actor)
    await session.commit()
    return schemas.SchemeResponse.model_validate(row)


@router.get("/grading-schemes", response_model=list[schemas.SchemeResponse])
async def list_schemes(
    actor: Actor = Depends(require("assessments.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> list[schemas.SchemeResponse]:
    service = GradingService(session)
    rows = await service.list_schemes(actor.school_id)
    return [schemas.SchemeResponse.model_validate(r) for r in rows]


@router.get("/grading-schemes/{scheme_id}", response_model=schemas.SchemeResponse)
async def get_scheme(
    scheme_id: UUID,
    actor: Actor = Depends(require("assessments.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.SchemeResponse:
    service = GradingService(session)
    row = await service.get_scheme(actor.school_id, scheme_id)
    return schemas.SchemeResponse.model_validate(row)


@router.post("/grading-schemes/{scheme_id}/activate", response_model=schemas.SchemeResponse)
async def activate_scheme(
    scheme_id: UUID,
    actor: Actor = Depends(require("assessments.manage")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.SchemeResponse:
    """Draft â†’ active; the previously active version of the same scheme name
    is retired. Processing cites an exact version, so retiring changes
    nothing already recorded."""
    service = GradingService(session)
    row = await service.activate_scheme(actor.school_id, scheme_id, actor)
    await session.commit()
    return schemas.SchemeResponse.model_validate(row)


# ---- processing ----------------------------------------------------------------


@router.post("/assessments/{assessment_id}/process", response_model=dict[str, str], status_code=202)
async def process_results(
    assessment_id: UUID,
    body: schemas.ProcessRequest,
    actor: Actor = Depends(require("results.process")),
    session: AsyncSession = Depends(get_actor_db),
) -> dict[str, str]:
    """Queue result processing (202 â€” async, spec Â§8). The body names the
    scheme VERSION to use; the template version is the one the assessment
    pins. Recalculation is explicit and creates a NEW run (spec Â§9.4); the
    job's progress is at GET /jobs/{job_id}."""
    service = GradingService(session)
    job, run = await service.enqueue_process(actor.school_id, assessment_id, body.scheme_id, actor)
    await session.commit()

    from app.platform.job_queue import enqueue_job

    await enqueue_job(job.id, "process_results")
    return {
        "job_id": str(job.id),
        "run_id": str(run.id),
        "status_url": f"/api/v1/jobs/{job.id}",
    }


@router.get(
    "/assessments/{assessment_id}/processing-runs",
    response_model=list[schemas.RunResponse],
)
async def list_processing_runs(
    assessment_id: UUID,
    actor: Actor = Depends(require("scores.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> list[schemas.RunResponse]:
    """Run history for the assessment, newest first; older runs are retained
    (spec Â§9.4)."""
    service = GradingService(session)
    rows = await service.list_runs(actor.school_id, assessment_id)
    return [schemas.RunResponse.model_validate(r) for r in rows]


@router.get("/assessments/{assessment_id}/results", response_model=schemas.ResultsResponse)
async def get_results(
    assessment_id: UUID,
    actor: Actor = Depends(require("scores.view")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.ResultsResponse:
    """The current results: the latest SUCCEEDED run and its rows in
    report-card order (position, then name)."""
    service = GradingService(session)
    run, rows = await service.get_results(actor.school_id, assessment_id)
    return schemas.ResultsResponse(
        run=schemas.RunResponse.model_validate(run),
        results=[
            schemas.ProcessedResultResponse(
                id=row.id,
                run_id=row.run_id,
                subject_enrolment_id=row.subject_enrolment_id,
                student_name=name,
                total=row.total,
                grade=row.grade,
                position=row.position,
                breakdown=row.breakdown,
                flags=row.flags,
            )
            for row, name in rows
        ],
    )
