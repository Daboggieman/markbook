"""Workflow service — the assessment state machine (Phase 5, spec §10).

The transition table lives in code as data (`TRANSITIONS`); per-school
`workflow_definitions` add or skip OPTIONAL intermediate stages and attach
permissions to those optional stages only. The mandatory graph below — its
permissions, its reason requirements, its guards — is NOT configurable
(spec §10 implementation notes).

Every transition runs in ONE transaction (spec §10):

    row lock (SELECT FOR UPDATE) → state check → reason check → guards →
    state write → approval_records insert → audit_events insert →
    outbox_events insert

The caller's route holds the transaction boundary (`get_actor_db` + commit),
so a guard failure rolls the whole transition back — no partial state, no
record without audit, no audit without state.

Separation of duties: reviewer/approver must not be the submitter. The
reviewer rule (start-review) is hard table text; the approve rule is
"configurable, on by default" — configurable per school via
`schools.config.separation_of_duties` (absent = on).

Publication side effects are ASYNC and durable, never inline (ADR 005):
publish/correct insert a `documents.report_cards` jobs row + outbox events
in the same transaction; the worker renders PDFs and writes the immutable
published_documents rows (doc_version, supersedes_id).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.access.service import Actor
from app.assessment.models import Assessment
from app.audit.service import AuditService
from app.platform.errors import (
    INVALID_STATE_TRANSITION,
    NOT_FOUND,
    PERMISSION_DENIED,
    VALIDATION_ERROR,
    ProblemError,
)
from app.platform.models import Job
from app.platform.outbox import (
    TOPIC_ASSESSMENT_STATE_CHANGED,
    TOPIC_RESULTS_PUBLISHED,
    enqueue_outbox_event,
)
from app.workflow import schemas
from app.workflow.models import ApprovalRecord, WorkflowDefinition
from app.workflow.repository import WorkflowRepository


@dataclass(frozen=True)
class Transition:
    """One legal transition (spec §10 table, as data).

    `guards` name the engine methods that must pass before the state moves:
      - submit_resolved      — every required template component resolved for
                               every enrolled student (no `missing` cells).
                               Absent/exempt ARE resolutions; missing is not
                               — a school's scheme policies govern how
                               absent/exempt COMPUTE (Phase 4), never whether
                               an unentered cell may be submitted.
      - not_submitter        — reviewer must not be the submitter (hard rule).
      - separation_of_duties — submitter must not approve (configurable,
                               default on, per-school via schools.config).
      - results_current      — the latest processing run exists and succeeded
                               (approve gate: results are real and current).

    Re-auth (lock) and re-auth+MFA (publish) are ROUTE-level constraints
    (spec §7.1 step-up) — they gate who may call, not whether the state
    may move, so they live on the route, not here.
    """

    to_state: str
    permission: str
    reason_required: bool = False
    guards: tuple[str, ...] = ()
    document_job: bool = False  # publish/correct: enqueue documents.report_cards


# (from_state, action) → transition. The action IS the URL verb segment.
# RETURNED → SUBMITTED reuses "submit" (a resubmit is a fresh submission
# with a fresh review — the submitted approval_record the SoD guards read
# is the resubmission's own).
TRANSITIONS: dict[tuple[str, str], Transition] = {
    ("draft", "submit"): Transition("submitted", "scores.submit", guards=("submit_resolved",)),
    ("returned", "submit"): Transition("submitted", "scores.submit", guards=("submit_resolved",)),
    ("submitted", "start-review"): Transition(
        "under_review", "scores.review", guards=("not_submitter",)
    ),
    ("under_review", "return"): Transition("returned", "scores.review", reason_required=True),
    ("under_review", "approve"): Transition(
        "approved", "results.approve", guards=("results_current", "separation_of_duties")
    ),
    ("approved", "lock"): Transition("locked", "results.lock"),
    ("locked", "publish"): Transition("published", "results.publish", document_job=True),
    ("published", "correct"): Transition(
        "published", "results.correct", reason_required=True, document_job=True
    ),
}

DOCUMENT_JOB_TYPE = "documents.report_cards"

# Transition permissions that honour the `assigned` scope (spec §10 marks
# scores.submit "(scoped)"): a teacher with only the assigned scope may act
# only inside their assignments. results.* are registrar-level school-scope
# actions; require() itself denies an assigned-scope holder (no resource
# context), so the service sees only school-scope actors here.
SCOPED_TRANSITION_PERMISSIONS = frozenset({"scores.submit", "scores.review"})


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = WorkflowRepository(session)

    # ---- transition engine -------------------------------------------------------

    async def apply(
        self,
        school_id: UUID,
        assessment_id: UUID,
        action: str,
        actor: Actor,
        reason: str | None = None,
        scope: str = "school",
    ) -> ApprovalRecord:
        """The one transition path every action method goes through."""
        assessment = await self._repo.lock_assessment(school_id, assessment_id)
        if assessment is None:
            raise ProblemError(NOT_FOUND, "Assessment not found", status=404)

        from_state = assessment.workflow_state
        transition = TRANSITIONS.get((from_state, action))
        if transition is None:
            legal_from = sorted(s for (s, a) in TRANSITIONS if a == action)
            raise ProblemError(
                INVALID_STATE_TRANSITION,
                f"Cannot {action.replace('-', '_')} an assessment in state "
                f"'{from_state}' (legal from {legal_from})",
            )

        if transition.permission in SCOPED_TRANSITION_PERMISSIONS:
            from app.assessment.service import AssessmentService

            await AssessmentService(self._s).check_transition_scope(
                assessment, actor, scope, transition.permission
            )

        if transition.reason_required and not reason:
            raise ProblemError(
                VALIDATION_ERROR, f"A reason is required to {action.replace('-', ' ')}"
            )

        for guard in transition.guards:
            await getattr(self, f"_guard_{guard}")(school_id, assessment_id, actor)

        await self._repo.set_assessment_state(assessment, transition.to_state)
        record = await self._repo.add_approval_record(
            ApprovalRecord(
                school_id=school_id,
                assessment_id=assessment.id,
                from_state=from_state,
                to_state=transition.to_state,
                actor_id=actor.user_id,
                reason=reason,
            )
        )

        await AuditService(self._s, actor).write(
            f"workflow.{action.replace('-', '_')}",
            entity_type="assessment",
            entity_id=assessment.id,
            before={"workflow_state": from_state},
            after={"workflow_state": transition.to_state},
            reason=reason,
        )
        await enqueue_outbox_event(
            self._s,
            school_id=str(school_id),
            topic=TOPIC_ASSESSMENT_STATE_CHANGED,
            payload={
                "assessment_id": str(assessment.id),
                "from_state": from_state,
                "to_state": transition.to_state,
                "action": action,
                "actor_id": str(actor.user_id),
            },
        )
        if transition.document_job:
            await self._enqueue_document_job(school_id, assessment, actor, reason)
        return record

    async def _enqueue_document_job(
        self,
        school_id: UUID,
        assessment: "Assessment",
        actor: Actor,
        reason: str | None,
    ) -> None:
        """Durable document-generation job + results.published event, in the
        SAME transaction as the transition (spec §10). The worker renders and
        writes the published_documents rows — publish never blocks on
        WeasyPrint (ADR 005)."""
        assessment_id = assessment.id
        job = Job(
            school_id=school_id,
            type=DOCUMENT_JOB_TYPE,
            status="queued",
            params={
                "assessment_id": str(assessment_id),
                "correction": reason is not None,
                # The reason travels with the job: the worker stamps it on the
                # corrected published_documents row (spec §10 — the correction
                # is recorded on the document, not just the transition).
                "correction_reason": reason,
            },
            created_by=actor.user_id,
        )
        self._s.add(job)
        await self._s.flush()
        await enqueue_outbox_event(
            self._s,
            school_id=str(school_id),
            topic=TOPIC_RESULTS_PUBLISHED,
            payload={
                "assessment_id": str(assessment_id),
                "job_id": str(job.id),
                "correction": reason is not None,
            },
        )
        await AuditService(self._s, actor).write(
            "documents.generation_requested",
            entity_type="job",
            entity_id=job.id,
            after={"assessment_id": str(assessment_id), "type": DOCUMENT_JOB_TYPE},
            reason=reason,
        )

    # ---- guards ------------------------------------------------------------------

    async def _guard_submit_resolved(
        self, school_id: UUID, assessment_id: UUID, actor: Actor
    ) -> None:
        """Every REQUIRED template component resolved for every enrolled
        student (spec §10 submit constraint). Only `missing` blocks."""
        from app.assessment.service import AssessmentService

        sheet = await AssessmentService(self._s).get_sheet(school_id, assessment_id)
        required_keys = {c.key for c in sheet.components if c.required}
        unresolved: list[str] = []
        for row in sheet.rows:
            if any(
                key not in row.scores or row.scores[key].status == "missing"
                for key in required_keys
            ):
                unresolved.append(str(row.subject_enrolment_id))
        if unresolved:
            listing = ", ".join(sorted(unresolved)[:5])
            more = "" if len(unresolved) <= 5 else f" (+{len(unresolved) - 5} more)"
            raise ProblemError(
                VALIDATION_ERROR,
                f"Cannot submit: {len(unresolved)} student(s) have unresolved required "
                f"components: {listing}{more}",
                extra={"unresolved": sorted(unresolved)},
            )

    async def _guard_not_submitter(
        self, school_id: UUID, assessment_id: UUID, actor: Actor
    ) -> None:
        """Hard rule (spec §10): the reviewer is not the submitter."""
        submitter = await self._submitter(school_id, assessment_id)
        if submitter is not None and submitter == actor.user_id:
            raise ProblemError(
                PERMISSION_DENIED,
                "The submitter cannot start the review of their own submission",
                status=403,
            )

    async def _guard_separation_of_duties(
        self, school_id: UUID, assessment_id: UUID, actor: Actor
    ) -> None:
        """Configurable rule, ON by default (spec §10): the submitter cannot
        approve their own submission. Per-school opt-out in schools.config:
        {"separation_of_duties": false}."""
        config = await self._repo.school_config(school_id)
        if config.get("separation_of_duties", True) is False:
            return
        submitter = await self._submitter(school_id, assessment_id)
        if submitter is not None and submitter == actor.user_id:
            raise ProblemError(
                PERMISSION_DENIED,
                "Separation of duties: the submitter cannot approve their own submission",
                status=403,
            )

    async def _guard_results_current(
        self, school_id: UUID, assessment_id: UUID, actor: Actor
    ) -> None:
        """Approve gate (spec §10): a successful processing run exists and is
        current — the newest run of ANY status is a succeeded one. A newer
        failed/queued run means the results are stale and must be reprocessed
        (or the failed run resolved) before approval."""
        from app.grading.service import GradingService

        runs = await GradingService(self._s).list_runs(school_id, assessment_id)
        if not runs or runs[0].status != "succeeded":
            raise ProblemError(
                INVALID_STATE_TRANSITION,
                "Approve requires a current successful processing run for this assessment",
            )

    async def _submitter(self, school_id: UUID, assessment_id: UUID) -> UUID | None:
        record = await self._repo.latest_record_to_state(school_id, assessment_id, "submitted")
        return record.actor_id if record is not None else None

    # ---- workflow definitions (configurable optional stages) -----------------------

    async def save_definition(
        self, school_id: UUID, data: schemas.WorkflowDefinitionCreate, actor: Actor
    ) -> WorkflowDefinition:
        """Create or replace a named stage configuration (spec §10).

        Validation: every stage's state must be a legal workflow state.
        Stage permissions are NOT validated against the catalogue here —
        that needs access.repository (a forbidden edge); an unknown
        permission is simply never granted, so a typo'd stage permission
        fails closed at require() time, which is the safe direction.
        Optional stages only — the mandatory transition graph above is
        unaffected; a definition may reorder or skip optional intermediates,
        never weaken an invariant.
        """
        from app.assessment.models import WORKFLOW_STATES

        for stage in data.stages:
            if stage.state not in WORKFLOW_STATES:
                raise ProblemError(
                    VALIDATION_ERROR,
                    f"Unknown workflow state '{stage.state}' in stage definition",
                )
        existing = await self._repo.get_definition(school_id, data.name)
        definition = (
            existing
            if existing is not None
            else WorkflowDefinition(school_id=school_id, name=data.name, stages=[])
        )
        definition.stages = [s.model_dump() for s in data.stages]
        definition.created_by = actor.user_id
        if existing is None:
            await self._repo.create_definition(definition)
        else:
            await self._s.flush()
        await AuditService(self._s, actor).write(
            "workflow.definition_saved",
            entity_type="workflow_definition",
            entity_id=definition.id,
            after={"name": definition.name, "stages": definition.stages},
        )
        return definition

    # ---- action surface (module-reference interface) -------------------------------

    async def submit(
        self, school_id: UUID, assessment_id: UUID, actor: Actor, *, scope: str = "school"
    ) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "submit", actor, scope=scope)

    async def start_review(
        self, school_id: UUID, assessment_id: UUID, actor: Actor, *, scope: str = "school"
    ) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "start-review", actor, scope=scope)

    async def return_for_editing(
        self,
        school_id: UUID,
        assessment_id: UUID,
        reason: str,
        actor: Actor,
        *,
        scope: str = "school",
    ) -> ApprovalRecord:
        return await self.apply(
            school_id, assessment_id, "return", actor, reason=reason, scope=scope
        )

    async def approve(self, school_id: UUID, assessment_id: UUID, actor: Actor) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "approve", actor)

    async def lock(self, school_id: UUID, assessment_id: UUID, actor: Actor) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "lock", actor)

    async def publish(self, school_id: UUID, assessment_id: UUID, actor: Actor) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "publish", actor)

    async def correct(
        self, school_id: UUID, assessment_id: UUID, reason: str, actor: Actor
    ) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "correct", actor, reason=reason)
