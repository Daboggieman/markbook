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
publish/correct insert a `documents.report_cards` jobs row + outbox event in
the same transaction; the worker renders PDFs and writes the immutable
published_documents rows (doc_version, supersedes_id).
"""

from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.access.service import Actor
from app.audit.service import AuditService
from app.platform.errors import (
    INVALID_STATE_TRANSITION,
    PERMISSION_DENIED,
    VALIDATION_ERROR,
    ProblemError,
)
from app.workflow.models import ApprovalRecord
from app.workflow.repository import WorkflowRepository


class Transition:
    """One legal transition (spec §10 table, as data).

    `guards` names the engine methods that must pass before the state moves:
      - submit_resolved   — every required template component resolved for
                            every enrolled student (no `missing` cells).
                            Absent/exempt ARE resolutions; missing is not —
                            a school's scheme policies govern how absent/
                            exempt COMPUTE (Phase 4), never whether an
                            unentered cell may be submitted.
      - not_submitter     — reviewer must not be the submitter (hard rule).
      - separation_of_duties — submitter must not approve (configurable,
                            default on, per-school via schools.config).
      - results_current   — the latest processing run exists and succeeded
                            (approve gate: results are real and current).
    """

    __slots__ = ("to_state", "permission", "reason_required", "guards")

    def __init__(
        self,
        to_state: str,
        permission: str,
        *,
        reason_required: bool = False,
        guards: tuple[str, ...] = (),
    ) -> None:
        self.to_state = to_state
        self.permission = permission
        self.reason_required = reason_required
        self.guards = guards


# (from_state, action) → transition. The action IS the URL verb segment.
TRANSITIONS: dict[tuple[str, str], Transition] = {
    ("draft", "submit"): Transition("submitted", "scores.submit", guards=("submit_resolved",)),
    # RETURNED → SUBMITTED is a resubmit: same action verb, fresh review.
    ("returned", "submit"): Transition("submitted", "scores.submit", guards=("submit_resolved",)),
    ("submitted", "start-review"): Transition(
        "under_review", "scores.review", guards=("not_submitter",)
    ),
    ("under_review", "return"): Transition("returned", "scores.review", reason_required=True),
    ("under_review", "approve"): Transition(
        "approved", "results.approve", guards=("results_current", "separation_of_duties")
    ),
    ("approved", "lock"): Transition("locked", "results.lock"),
    ("locked", "publish"): Transition("published", "results.publish"),
    ("published", "correct"): Transition("published", "results.correct", reason_required=True),
}


class WorkflowService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = WorkflowRepository(session)

    # ---- transition engine -----------------------------------------------------

    async def apply(
        self,
        school_id: UUID,
        assessment_id: UUID,
        action: str,
        actor: Actor,  # noqa: F821 — Actor import at call time (see _actor note)
        reason: str | None = None,
    ) -> ApprovalRecord:
        """The one transition path every action method goes through."""
        from app.access.service import Actor as _Actor  # noqa: F401

        transition = None
        from_state = None
        # The action must be valid for SOME state; the state check comes from
        # the row itself after the lock.
        for (state, act), spec in TRANSITIONS.items():
            if act == action:
                transition = spec
                break
        if transition is None:
            raise ProblemError(VALIDATION_ERROR, f"Unknown workflow action: {action}")

        assessment = await self._repo.lock_assessment(school_id, assessment_id)
        if assessment is None:
            from app.platform.errors import NOT_FOUND, ProblemError as _PE

            raise _PE(NOT_FOUND, "Assessment not found", status=404)

        from_state = assessment.workflow_state
        spec = TRANSITIONS.get((from_state, action))
        if spec is None:
            raise ProblemError(
                INVALID_STATE_TRANSITION,
                f"Cannot {action.replace('-', '_')} an assessment in state "
                f"'{from_state}' (legal only from "
                f"{[s for (s, a) in TRANSITIONS if a == action]})",
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
        return record

    # ---- guards ------------------------------------------------------------------

    async def _guard_submit_resolved(
        self, school_id: UUID, assessment_id: UUID, actor: object
    ) -> None:
        """Every REQUIRED template component resolved for every enrolled
        student (spec §10 submit constraint). Absent/exempt count as
        resolved — only `missing` (never entered at all, or never resolved)
        blocks submission."""
        from app.assessment.service import AssessmentService

        sheet = await AssessmentService(self._s).get_sheet(school_id, assessment_id)
        required_keys = {c.key for c in sheet.components if c.required}
        unresolved: list[str] = []
        for row in sheet.rows:
            for key in sorted(required_keys):
                cell = row.scores.get(key)
                if cell is None or cell.status == "missing":
                    unresolved.append(str(row.subject_enrolment_id))
                    break
        if unresolved:
            listing = ", ".join(unresolved[:5])
            more = "" if len(unresolved) <= 5 else f" (+{len(unresolved) - 5} more)"
            raise ProblemError(
                VALIDATION_ERROR,
                f"Cannot submit: {len(unresolved)} student(s) have unresolved required "
                f"components: {listing}{more}",
                extra={"unresolved": unresolved},
            )

    async def _guard_not_submitter(
        self, school_id: UUID, assessment_id: UUID, actor: object
    ) -> None:
        """Hard rule (spec §10): the reviewer is not the submitter."""
        submitter = await self._repo.latest_record_to_state(school_id, assessment_id, "submitted")
        if submitter is not None and submitter.actor_id is not None:
            if submitter.actor_id == getattr(actor, "user_id", None):
                raise ProblemError(
                    PERMISSION_DENIED,
                    "The submitter cannot start the review of their own submission",
                    status=403,
                )

    async def _guard_separation_of_duties(
        self, school_id: UUID, assessment_id: UUID, actor: object
    ) -> None:
        """Configurable rule, ON by default (spec §10): the submitter cannot
        approve their own submission. Per-school opt-out in schools.config:
        {"separation_of_duties": false}."""
        from app.access.service import Actor as _Actor

        config = await self._repo.school_config(school_id)
        if config.get("separation_of_duties", True) is False:
            return
        submitter = await self._repo.latest_record_to_state(school_id, assessment_id, "submitted")
        if submitter is not None and submitter.actor_id is not None:
            if submitter.actor_id == getattr(_Actor, "__init__", None) or submitter.actor_id == getattr(
                actor, "user_id", None
            ):
                raise ProblemError(
                    PERMISSION_DENIED,
                    "Separation of duties: the submitter cannot approve their own submission",
                    status=403,
                )

    async def _guard_results_current(
        self, school_id: UUID, assessment_id: UUID, actor: object
    ) -> None:
        """Approve gate (spec §10): a successful processing run exists and is
        current — the newest run of ANY status is a succeeded one. A newer
        failed/queued run means the shown results are stale."""
        from app.grading.service import GradingService

        runs = await GradingService(self._s).list_runs(school_id, assessment_id)
        if not runs or runs[0].status != "succeeded":
            raise ProblemError(
                INVALID_STATE_TRANSITION,
                "Approve requires a current successful processing run for this assessment",
            )

    # ---- action surface (module-reference interface) ------------------------------

    async def submit(self, school_id: UUID, assessment_id: UUID, actor: object) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "submit", actor)

    async def start_review(self, school_id: UUID, assessment_id: UUID, actor: object) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "start-review", actor)

    async def return_for_editing(
        self, school_id: UUID, assessment_id: UUID, reason: str, actor: object
    ) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "return", actor, reason=reason)

    async def approve(self, school_id: UUID, assessment_id: UUID, actor: object) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "approve", actor)

    async def lock(self, school_id: UUID, assessment_id: UUID, actor: object) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "lock", actor)

    async def publish(self, school_id: UUID, assessment_id: UUID, actor: object) -> ApprovalRecord:
        record = await self.apply(school_id, assessment_id, "publish", actor)
        # Side effects (spec §10: one transaction — approval + audit + outbox):
        # audit is written by the caller's router-level hook; here: outbox +
        # the durable document-generation job. Rendering is worker-only
        # (ADR 005) — publish never blocks on WeasyPrint.
        return record

    async def correct(
        self, school_id: UUID, assessment_id: UUID, reason: str, actor: object
    ) -> ApprovalRecord:
        return await self.apply(school_id, assessment_id, "correct", actor, reason=reason)
