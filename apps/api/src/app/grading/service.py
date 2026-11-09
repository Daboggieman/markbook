"""Grading service — schemes, processing runs, processed results (Phase 4).

The calculation itself lives in the pure engine (`app.grading.engine`); this
service is the seam between the database and the engine:

  - `create_scheme` / `activate_scheme` — scheme versioning (spec §9.4):
    saving a definition under an existing name creates the NEXT version;
    activation retires the previous active of the same name. The engine's
    `validate_scheme` is the single authority on what a valid scheme is.
  - `enqueue_process` — durable jobs row + a `queued` run capturing the exact
    inputs (scheme version row + scheme_version + the assessment's pinned
    template version). Recalculation is explicit and audited (spec §9.4).
  - `apply_run` — the worker-side deterministic core. It consumes the SAME
    sheet path the score sheet uses (`AssessmentService.get_sheet` — one
    definition of "what is on the sheet"), synthesizes one engine ScoreInput
    per roster student × template component (absent rows resolve to
    `missing`, spec §9.2 step 1), computes, ranks, and writes
    `processed_results` immutably.
  - Failure semantics: `missing_policy=block` fails the WHOLE run with the
    blocked students listed — a report card set must not silently drop a
    student. A student with every component excluded (no renormalisable
    weight) is stored with NULL total/grade/position and the
    `no_scoreable_components` flag. Failed runs settle from a fresh
    transaction in `grading.jobs` (the run row rolls back with the aborted
    job transaction, so it would otherwise stay `queued` forever).

The run records `input_hash` over exactly the ScoreInput list consumed —
same inputs + same versions reproduce byte-identical results (spec §9.4).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.service import Actor
from app.assessment.service import AssessmentService
from app.audit.service import AuditService
from app.grading import schemas
from app.grading.engine import (
    STATUS_MISSING,
    EngineComponent,
    EngineScheme,
    EngineTemplate,
    SchemeValidationError,
    ScoreInput,
    build_scheme,
    compute,
    input_hash,
    rank,
)
from app.grading.engine.types import ComputedResult
from app.grading.models import GradingScheme, ProcessedResult, ResultProcessingRun
from app.grading.repository import GradingRepository
from app.platform.errors import (
    CONFLICT,
    INVALID_STATE_TRANSITION,
    NOT_FOUND,
    VALIDATION_ERROR,
    ProblemError,
)
from app.platform.models import Job
from app.platform.outbox import TOPIC_RESULTS_PROCESSED, enqueue_outbox_event


class GradingService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = GradingRepository(session)
        self._assessments = AssessmentService(session)

    # ---- schemes ---------------------------------------------------------------

    async def create_scheme(
        self, school_id: UUID, data: schemas.SchemeCreate, actor: Actor
    ) -> GradingScheme:
        """Save a scheme definition. A new name starts at version 1 (draft);
        an existing name creates the next version — editing never rewrites
        (spec §9.4)."""
        try:
            build_scheme(**data.definition.engine_kwargs())
        except SchemeValidationError as exc:
            raise ProblemError(VALIDATION_ERROR, str(exc)) from exc
        existing = await self._repo.list_schemes(school_id, name=data.name)
        version_no = (existing[-1].version_no if existing else 0) + 1
        try:
            scheme = await self._repo.create_scheme(
                GradingScheme(
                    school_id=school_id,
                    name=data.name,
                    version_no=version_no,
                    status="draft",
                    definition=data.definition.model_dump(mode="json"),
                    created_by=actor.user_id,
                )
            )
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "A scheme with that name/version already exists") from exc
        await AuditService(self._s, actor).write(
            "grading.scheme.created",
            entity_type="grading_scheme",
            entity_id=scheme.id,
            after={"name": scheme.name, "version_no": version_no},
        )
        return scheme

    async def list_schemes(self, school_id: UUID) -> list[GradingScheme]:
        return await self._repo.list_schemes(school_id)

    async def get_scheme(self, school_id: UUID, scheme_id: UUID) -> GradingScheme:
        scheme = await self._repo.get_scheme(school_id, scheme_id)
        if scheme is None:
            raise ProblemError(NOT_FOUND, "Grading scheme not found", status=404)
        return scheme

    async def activate_scheme(
        self, school_id: UUID, scheme_id: UUID, actor: Actor
    ) -> GradingScheme:
        """Draft → active; the previously active version of the same scheme
        name is retired. Retired versions cannot be reactivated — processing
        always cites an exact version, so retirement changes nothing already
        recorded."""
        scheme = await self.get_scheme(school_id, scheme_id)
        if scheme.status == "retired":
            raise ProblemError(
                INVALID_STATE_TRANSITION, "A retired scheme version cannot be reactivated"
            )
        if scheme.status == "active":
            return scheme
        current = await self._repo.get_active_scheme(school_id, scheme.name)
        if current is not None:
            await self._repo.set_scheme_status(current, "retired")
        await self._repo.set_scheme_status(scheme, "active")
        await AuditService(self._s, actor).write(
            "grading.scheme.activated",
            entity_type="grading_scheme",
            entity_id=scheme.id,
            after={"name": scheme.name, "version_no": scheme.version_no},
        )
        return scheme

    # ---- processing -----------------------------------------------------------

    async def enqueue_process(
        self, school_id: UUID, assessment_id: UUID, scheme_id: UUID, actor: Actor
    ) -> tuple[Job, ResultProcessingRun]:
        """Record the durable job + queued run and return them. The run pins
        the exact inputs at request time: the chosen scheme version and the
        template version the assessment already pins. The scheme version must
        be active — a draft was never approved for use (mirrors assessment
        creation's active-template rule)."""
        assessment = await self._assessments.get_assessment(school_id, assessment_id)
        scheme = await self.get_scheme(school_id, scheme_id)
        if scheme.status != "active":
            raise ProblemError(VALIDATION_ERROR, "Grading scheme version is not active")
        run = await self._repo.create_run(
            ResultProcessingRun(
                school_id=school_id,
                assessment_id=assessment.id,
                scheme_id=scheme.id,
                scheme_version=scheme.version_no,
                template_version_id=assessment.template_version_id,
                status="queued",
                requested_by=actor.user_id,
            )
        )
        job = Job(
            school_id=school_id,
            type="process_results",
            status="queued",
            params={
                "assessment_id": str(assessment.id),
                "scheme_id": str(scheme.id),
                "run_id": str(run.id),
            },
            created_by=actor.user_id,
        )
        self._s.add(job)
        await self._s.flush()
        await AuditService(self._s, actor).write(
            "results.process_requested",
            entity_type="result_processing_run",
            entity_id=run.id,
            after={
                "assessment_id": str(assessment.id),
                "scheme_id": str(scheme.id),
                "scheme_version": scheme.version_no,
            },
        )
        return job, run

    async def apply_run(self, school_id: UUID, run_id: UUID, actor: Actor) -> dict:
        """The deterministic core, run by the worker job (never HTTP). Idempotent
        on re-delivery: a run already settled is reported, not recomputed."""
        run = await self._repo.get_run(school_id, run_id)
        if run is None:
            raise ProblemError(NOT_FOUND, "Processing run not found", status=404)
        if run.status in ("succeeded", "failed"):
            return {"run_id": str(run.id), "status": run.status, "already_settled": True}

        # The consumption set: the same sheet the score sheet shows.
        sheet = await self._assessments.get_sheet(school_id, run.assessment_id)
        scheme_row = await self.get_scheme(school_id, run.scheme_id)
        try:
            scheme_def = schemas.SchemeDefinition.model_validate(scheme_row.definition)
            scheme: EngineScheme = build_scheme(**scheme_def.engine_kwargs())
        except SchemeValidationError as exc:
            # A stored definition can no longer be parsed — treat as a data
            # integrity fault, not a caller validation error.
            raise ProblemError(VALIDATION_ERROR, f"Stored scheme is invalid: {exc}") from exc
        template = EngineTemplate(
            components=tuple(
                EngineComponent(
                    key=c.key, max_score=c.max_score, weight=c.weight, required=c.required
                )
                for c in sorted(sheet.components, key=lambda c: c.key)
            )
        )

        # One ScoreInput per roster student × template component (spec §9.2
        # step 1): a cell with no score row resolves to `missing`.
        inputs_by_student: dict[str, list[ScoreInput]] = {}
        for row in sheet.rows:
            seid = str(row.subject_enrolment_id)
            inputs_by_student[seid] = [
                ScoreInput(
                    seid,
                    comp.key,
                    row.scores[comp.key].status if comp.key in row.scores else STATUS_MISSING,
                    row.scores[comp.key].value if comp.key in row.scores else None,
                )
                for comp in sorted(sheet.components, key=lambda c: c.key)
            ]

        ordered_ids = sorted(inputs_by_student)
        all_inputs = [inp for seid in ordered_ids for inp in inputs_by_student[seid]]
        digest = input_hash(all_inputs)

        run.status = "running"
        run.started_at = datetime.now(UTC)
        await self._s.flush()

        computed = [compute(inputs_by_student[seid], template, scheme) for seid in ordered_ids]
        blocked = [r for r in computed if r.blocked]
        if blocked:
            listing = ", ".join(r.subject_enrolment_id for r in blocked[:5])
            more = "" if len(blocked) <= 5 else f" (+{len(blocked) - 5} more)"
            raise ProblemError(
                VALIDATION_ERROR,
                f"missing_policy=block: {len(blocked)} student(s) have unresolvable "
                f"components and cannot be processed: {listing}{more}",
                extra={"blocked": [r.subject_enrolment_id for r in blocked]},
            )
        ranked = rank(computed, scheme)
        positions = {r.subject_enrolment_id: r.position for r in ranked}

        for r in computed:
            await self._repo.add_processed_result(
                ProcessedResult(
                    school_id=school_id,
                    run_id=run.id,
                    subject_enrolment_id=UUID(r.subject_enrolment_id),
                    total=r.total,
                    grade=r.grade,
                    position=positions.get(r.subject_enrolment_id),
                    breakdown=_breakdown_json(r),
                    flags=sorted(r.flags),
                )
            )
        run.status = "succeeded"
        run.input_hash = digest
        run.finished_at = datetime.now(UTC)
        await self._s.flush()

        await enqueue_outbox_event(
            self._s,
            school_id=str(school_id),
            topic=TOPIC_RESULTS_PROCESSED,
            payload={
                "run_id": str(run.id),
                "assessment_id": str(run.assessment_id),
                "processed": len(computed),
                "input_hash": digest,
            },
        )
        await AuditService(self._s, actor).write(
            "results.processed",
            entity_type="result_processing_run",
            entity_id=run.id,
            after={
                "assessment_id": str(run.assessment_id),
                "processed": len(computed),
                "input_hash": digest,
            },
        )
        return {
            "run_id": str(run.id),
            "status": "succeeded",
            "processed": len(computed),
            "input_hash": digest,
        }

    # ---- history & current results ------------------------------------------------

    async def list_runs(self, school_id: UUID, assessment_id: UUID) -> list[ResultProcessingRun]:
        """Run history, newest first. Older runs are retained (spec §9.4)."""
        await self._assessments.get_assessment(school_id, assessment_id)
        return await self._repo.list_runs(school_id, assessment_id)

    async def get_results(
        self, school_id: UUID, assessment_id: UUID
    ) -> tuple[ResultProcessingRun, list[tuple[ProcessedResult, str]]]:
        """The current results: the latest SUCCEEDED run and its rows in
        report-card order. 404 when no run has ever succeeded."""
        await self._assessments.get_assessment(school_id, assessment_id)
        run = await self._repo.latest_succeeded_run(school_id, assessment_id)
        if run is None:
            raise ProblemError(
                NOT_FOUND, "No successful processing run for this assessment", status=404
            )
        return run, await self._repo.list_results(school_id, run.id)


def _breakdown_json(result: ComputedResult) -> list[dict[str, Any]]:
    """ComputedResult.breakdown → JSONB-ready dicts (Decimals as strings)."""
    return [
        {
            "component_key": e.component_key,
            "status": e.status,
            "value": str(e.value) if e.value is not None else None,
            "contribution": str(e.contribution) if e.contribution is not None else None,
            "excluded": e.excluded,
        }
        for e in result.breakdown
    ]
