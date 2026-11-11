"""Workflow router — the seven transition routes (Phase 5).

HTTP layer only; the state machine lives in `workflow.service`. Permission
mapping (spec §10 table + §8):

  submit/start-review/return  scores.submit / scores.review (scoped — the
                              service re-checks `assigned` scope against
                              teacher assignments, like score entry)
  approve/lock/publish/correct  results.approve / results.lock /
                              results.publish / results.correct (school scope;
                              `require` denies an assigned-scope holder by
                              having no resource context)

Step-up gates (spec §7.1/§10): lock requires a `reauth_at` claim from
POST /auth/reauth within the last 5 minutes; publish additionally requires
that the re-auth verified a TOTP code (reauth_mfa claim — only set when the
account has MFA enrolled and verified, so the mandatory-MFA rule is enforced
without a second lookup).

Every transition inserts approval_record + audit event + outbox event in the
ONE transaction the route commits (spec §10).
"""

# ruff: noqa: B008  — Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.dependency import get_actor_db, require, require_reauth, require_with_scope
from app.access.service import Actor
from app.workflow import schemas
from app.workflow.service import WorkflowService

router = APIRouter(tags=["workflow"])


async def _transition(
    assessment_id: UUID,
    action: str,
    body: schemas.TransitionRequest,
    actor: Actor,
    session: AsyncSession,
    scope: str = "school",
) -> schemas.TransitionResponse:
    """Shared body of all seven routes: apply, commit, respond."""
    service = WorkflowService(session)
    record = await service.apply(
        actor.school_id, assessment_id, action, actor, reason=body.reason, scope=scope
    )
    await session.commit()
    return schemas.TransitionResponse(
        assessment_id=record.assessment_id,
        workflow_state=record.to_state,
        record_id=record.id,
        from_state=record.from_state,
        to_state=record.to_state,
        actor_id=record.actor_id,
        at=record.at,
    )


@router.post(
    "/assessments/{assessment_id}/submit",
    response_model=schemas.TransitionResponse,
)
async def submit(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    auth: tuple[Actor, str] = Depends(require_with_scope("scores.submit")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """DRAFT/RETURNED -> SUBMITTED. All required components must be resolved
    (no `missing` cells); a RETURNED resubmit starts a fresh review."""
    actor, scope = auth
    return await _transition(assessment_id, "submit", body, actor, session, scope)


@router.post(
    "/assessments/{assessment_id}/start-review",
    response_model=schemas.TransitionResponse,
)
async def start_review(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    auth: tuple[Actor, str] = Depends(require_with_scope("scores.review")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """SUBMITTED -> UNDER_REVIEW. The reviewer must not be the submitter."""
    actor, scope = auth
    return await _transition(assessment_id, "start-review", body, actor, session, scope)


@router.post(
    "/assessments/{assessment_id}/return",
    response_model=schemas.TransitionResponse,
)
async def return_for_editing(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    auth: tuple[Actor, str] = Depends(require_with_scope("scores.review")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """UNDER_REVIEW -> RETURNED (back to editing). A reason is required."""
    actor, scope = auth
    return await _transition(assessment_id, "return", body, actor, session, scope)


@router.post(
    "/assessments/{assessment_id}/approve",
    response_model=schemas.TransitionResponse,
)
async def approve(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    actor: Actor = Depends(require("results.approve")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """UNDER_REVIEW -> APPROVED. Requires a current successful processing
    run; separation of duties (submitter cannot approve) is on by default."""
    return await _transition(assessment_id, "approve", body, actor, session)


@router.post(
    "/assessments/{assessment_id}/lock",
    response_model=schemas.TransitionResponse,
)
async def lock(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    actor: Actor = Depends(require("results.lock")),
    reauth: Actor = Depends(require_reauth()),  # noqa: F841 — the gate IS the dependency
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """APPROVED -> LOCKED. Online only, with re-auth (spec §10)."""
    return await _transition(assessment_id, "lock", body, actor, session)


@router.post(
    "/assessments/{assessment_id}/publish",
    response_model=schemas.TransitionResponse,
)
async def publish(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    actor: Actor = Depends(require("results.publish")),
    reauth: Actor = Depends(require_reauth(require_mfa=True)),  # noqa: F841
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """LOCKED -> PUBLISHED. Online only, re-auth WITH MFA (spec §10).
    Enqueues the report-card generation job (ADR 005 — rendering is
    worker-only); the immutable published_documents rows appear when the
    job succeeds."""
    return await _transition(assessment_id, "publish", body, actor, session)


@router.post(
    "/assessments/{assessment_id}/correct",
    response_model=schemas.TransitionResponse,
)
async def correct(
    assessment_id: UUID,
    body: schemas.TransitionRequest,
    actor: Actor = Depends(require("results.correct")),
    session: AsyncSession = Depends(get_actor_db),
) -> schemas.TransitionResponse:
    """PUBLISHED -> PUBLISHED (v+1). A reason is required; the corrected
    documents become a NEW version superseding the old — never an overwrite
    (spec §10)."""
    return await _transition(assessment_id, "correct", body, actor, session)
