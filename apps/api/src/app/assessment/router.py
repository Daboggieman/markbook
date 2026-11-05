"""Assessment router — templates, assessments, score entry (Phase 3).

HTTP layer only; logic in `assessment.service`. Every route declares `require`
or `require_with_scope` (route-coverage guard); tenant-data routes use
`get_actor_db` so the RLS context is set from the JWT.

Score-writing routes use `require_with_scope("scores.enter")` rather than
plain `require`: the service needs the caller's SCOPE to enforce the Phase 3
exit criterion — an `assigned`-scope teacher writing outside their assignments
is a 403 from the service's assignment check, not an all-or-nothing permission
gate.
"""
# ruff: noqa: B008  — Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.access.dependency import get_actor_db, require, require_with_scope
from app.access.service import Actor
from app.assessment import schemas
from app.assessment.service import AssessmentService

router = APIRouter(tags=["assessment"])


# ---- templates & versions ------------------------------------------------------


@router.get("/assessment-templates", response_model=list[schemas.AssessmentTemplateResponse])
async def list_templates(
    actor: Actor = Depends(require("assessments.view")),
    session=Depends(get_actor_db),
) -> list[schemas.AssessmentTemplateResponse]:
    service = AssessmentService(session)
    rows = await service.list_templates(actor.school_id)
    return [schemas.AssessmentTemplateResponse.model_validate(r) for r in rows]


@router.post("/assessment-templates", response_model=schemas.AssessmentTemplateResponse, status_code=201)
async def create_template(
    body: schemas.AssessmentTemplateCreate,
    actor: Actor = Depends(require("assessments.manage")),
    session=Depends(get_actor_db),
) -> schemas.AssessmentTemplateResponse:
    """Creates the template AND its first (draft) version (spec §6.4)."""
    service = AssessmentService(session)
    template, _version = await service.create_template(actor.school_id, body, actor)
    await session.commit()
    return schemas.AssessmentTemplateResponse.model_validate(template)


@router.get(
    "/assessment-templates/{template_id}/versions",
    response_model=list[schemas.TemplateVersionResponse],
)
async def list_template_versions(
    template_id: UUID,
    actor: Actor = Depends(require("assessments.view")),
    session=Depends(get_actor_db),
) -> list[schemas.TemplateVersionResponse]:
    service = AssessmentService(session)
    rows = await service.list_template_versions(actor.school_id, template_id)
    return [schemas.TemplateVersionResponse.model_validate(r) for r in rows]


@router.post(
    "/assessment-templates/{template_id}/versions",
    response_model=schemas.TemplateVersionResponse,
    status_code=201,
)
async def create_template_version(
    template_id: UUID,
    body: schemas.TemplateVersionCreate,
    actor: Actor = Depends(require("assessments.manage")),
    session=Depends(get_actor_db),
) -> schemas.TemplateVersionResponse:
    """Editing a template creates a NEW version; existing versions are
    immutable and existing assessments keep the version they were created
    with (spec §6.4 — Phase 3 exit criterion)."""
    service = AssessmentService(session)
    row = await service.create_template_version(actor.school_id, template_id, body)
    await session.commit()
    return schemas.TemplateVersionResponse.model_validate(row)


@router.post(
    "/template-versions/{version_id}/activate",
    response_model=schemas.TemplateVersionResponse,
)
async def activate_template_version(
    version_id: UUID,
    actor: Actor = Depends(require("assessments.manage")),
    session=Depends(get_actor_db),
) -> schemas.TemplateVersionResponse:
    """Draft → active; the previously active version of the same template is
    retired. Assessments pin the version they were created with, so retiring
    it changes nothing for them."""
    service = AssessmentService(session)
    row = await service.activate_template_version(actor.school_id, version_id)
    await session.commit()
    return schemas.TemplateVersionResponse.model_validate(row)


# ---- assessments -----------------------------------------------------------------


@router.post("/assessments", response_model=schemas.AssessmentResponse, status_code=201)
async def create_assessment(
    body: schemas.AssessmentCreate,
    actor: Actor = Depends(require("assessments.manage")),
    session=Depends(get_actor_db),
) -> schemas.AssessmentResponse:
    """One result set per (term, class, section, subject); the template
    version must be active."""
    service = AssessmentService(session)
    row = await service.create_assessment(actor.school_id, body)
    await session.commit()
    return schemas.AssessmentResponse.model_validate(row)


@router.get("/assessments", response_model=list[schemas.AssessmentResponse])
async def list_assessments(
    auth: tuple[Actor, str] = Depends(require_with_scope("assessments.view")),
    session=Depends(get_actor_db),
    term_id: UUID | None = Query(default=None),
    class_id: UUID | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
) -> list[schemas.AssessmentResponse]:
    """Scope-filtered (spec §7.2): 'assigned' callers see only assessments
    covered by their teacher assignments."""
    actor, scope = auth
    service = AssessmentService(session)
    rows = await service.list_assessments(
        actor.school_id,
        scope=scope,
        actor=actor,
        term_id=term_id,
        class_id=class_id,
        subject_id=subject_id,
    )
    return [schemas.AssessmentResponse.model_validate(r) for r in rows]


@router.get("/assessments/{assessment_id}/sheet", response_model=schemas.ScoreSheetResponse)
async def get_score_sheet(
    assessment_id: UUID,
    actor: Actor = Depends(require("assessments.view")),
    session=Depends(get_actor_db),
) -> schemas.ScoreSheetResponse:
    """The score sheet: roster (subject enrolments for the assessment's
    term/class/section/subject) merged with any entered scores."""
    service = AssessmentService(session)
    return await service.get_sheet(actor.school_id, assessment_id)


# ---- scores ------------------------------------------------------------------------


@router.put("/assessments/{assessment_id}/scores", response_model=list[schemas.ScoreResponse])
async def batch_upsert_scores(
    assessment_id: UUID,
    body: schemas.BatchScoreUpsert,
    auth: tuple[Actor, str] = Depends(require_with_scope("scores.enter")),
    session=Depends(get_actor_db),
) -> list[schemas.ScoreResponse]:
    """Batch upsert (spec §6.4). All-or-nothing: one bad row rejects the
    batch with every bad cell reported. Rows overwrite existing cells only
    with the row's current `base_version` — a stale one is 409
    VERSION_CONFLICT. The scores.edit permission (edit-after-submit gating)
    is enforced from Phase 5; in draft/returned, entry and edit are the same
    upsert action."""
    actor, scope = auth
    service = AssessmentService(session)
    rows = await service.batch_upsert_scores(
        actor.school_id, assessment_id, body.rows, actor, scope=scope
    )
    await session.commit()
    return [schemas.ScoreResponse.model_validate(r) for r in rows]


@router.post(
    "/assessments/{assessment_id}/scores/import",
    response_model=dict[str, str],
    status_code=202,
)
async def import_scores(
    assessment_id: UUID,
    body: schemas.ImportScoresRequest,
    auth: tuple[Actor, str] = Depends(require_with_scope("scores.enter")),
    session=Depends(get_actor_db),
) -> dict[str, str]:
    """Queue a bulk import (202 — long operation, spec §8). The job applies
    valid rows and reports invalid ones per row number at GET /jobs/{job_id}.
    The Arq trigger is best-effort after the durable jobs row commits."""
    actor, scope = auth
    service = AssessmentService(session)
    job = await service.enqueue_import(actor.school_id, assessment_id, body.csv, actor, scope=scope)
    await session.commit()

    from app.platform.job_queue import enqueue_job

    await enqueue_job(job.id, "import_scores")
    return {"job_id": str(job.id), "status_url": f"/api/v1/jobs/{job.id}"}


@router.get("/scores/{score_id}/history", response_model=list[schemas.ScoreChangeResponse])
async def get_score_history(
    score_id: UUID,
    actor: Actor = Depends(require("scores.view")),
    session=Depends(get_actor_db),
) -> list[schemas.ScoreChangeResponse]:
    """The append-only edit ledger for one score, oldest first (spec §6.4)."""
    service = AssessmentService(session)
    changes = await service.get_score_history(actor.school_id, score_id)
    return [schemas.ScoreChangeResponse.model_validate(c) for c in changes]


# ---- job status ----------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=schemas.JobResponse)
async def get_job(
    job_id: UUID,
    actor: Actor = Depends(require("assessments.view")),
    session=Depends(get_actor_db),
) -> schemas.JobResponse:
    """Job status/result. Assessment is the only job producer in Phase 3, so
    this route lives here; it moves to a shared home when a second producer
    appears."""
    service = AssessmentService(session)
    job = await service.get_job(actor.school_id, job_id)
    return schemas.JobResponse.model_validate(job)
