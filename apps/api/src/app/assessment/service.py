"""Assessment service — templates, assessments, score entry (Phase 3).

Template versions are immutable once active (spec §6.4): editing a template
creates a NEW version and existing assessments keep pointing at the version
they were created with. The zero-vs-missing invariant is enforced by the DB
CHECK behind this service; `validation.validate_score_row` is the application
mirror that gives callers a clean 422 instead of a raw IntegrityError.

Every score write appends to `score_changes` (append-only ledger, spec §6.4)
in the same transaction, and emits `score.changed` on the transactional
outbox. Optimistic concurrency is per cell: each row carries the `base_version`
of the score it overwrites; a stale base raises VERSION_CONFLICT, so two
teachers editing different cells of one sheet never conflict.

Failure semantics differ by front door, on purpose:
  - Web batch (`batch_upsert_scores`): all-or-nothing — one bad row rejects
    the whole request, reporting every bad cell at once (the sheet is one
    transaction; the client redraws with all problems visible).
  - Import (`apply_import`, run by the worker job): row-level partial
    success — valid rows are applied, invalid rows are reported per row
    number in the job result.
Both share `_apply_rows`; only what the caller does with the row errors
differs.
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic.models import Class, Subject, Term, TeacherAssignment
from app.access.service import Actor
from app.assessment import schemas
from app.assessment.models import (
    EDITABLE_STATES,
    Assessment,
    AssessmentTemplate,
    AssessmentTemplateVersion,
    Score,
    ScoreChange,
)
from app.assessment.repository import AssessmentRepository
from app.assessment.validation import validate_score_row
from app.platform.errors import (
    CONFLICT,
    INVALID_STATE_TRANSITION,
    NOT_FOUND,
    PERMISSION_DENIED,
    VALIDATION_ERROR,
    VERSION_CONFLICT,
    ProblemError,
)
from app.platform.models import Job
from app.platform.outbox import TOPIC_SCORE_CHANGED, enqueue_outbox_event

CSV_REQUIRED_COLUMNS = ("subject_enrolment_id", "component_key", "status")


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = AssessmentRepository(session)

    async def _one_or_404(self, model, *, school_id: UUID, id_: UUID, label: str):
        row = await self._s.scalar(
            select(model).where(model.school_id == school_id, model.id == id_)
        )
        if row is None:
            raise ProblemError(NOT_FOUND, f"{label} not found", status=404)
        return row

    # ---- templates & versions -----------------------------------------------

    async def create_template(
        self, school_id: UUID, data: schemas.AssessmentTemplateCreate, actor: Actor
    ) -> tuple[AssessmentTemplate, AssessmentTemplateVersion]:
        """Create the template and its first (draft) version in one transaction."""
        template = AssessmentTemplate(
            school_id=school_id, name=data.name, created_by=actor.user_id
        )
        try:
            template = await self._repo.create_template(template)
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "A template with that name already exists") from exc
        version = await self._repo.create_version(
            AssessmentTemplateVersion(
                school_id=school_id,
                template_id=template.id,
                version_no=1,
                status="draft",
                definition=data.definition.model_dump(mode="json"),
                created_by=actor.user_id,
            )
        )
        return template, version

    async def list_templates(self, school_id: UUID) -> list[AssessmentTemplate]:
        return await self._repo.list_templates(school_id)

    async def get_template(self, school_id: UUID, template_id: UUID) -> AssessmentTemplate:
        return await self._one_or_404(
            AssessmentTemplate, school_id=school_id, id_=template_id, label="Template"
        )

    async def list_template_versions(
        self, school_id: UUID, template_id: UUID
    ) -> list[AssessmentTemplateVersion]:
        await self.get_template(school_id, template_id)
        return await self._repo.list_versions(school_id, template_id)

    async def create_template_version(
        self, school_id: UUID, template_id: UUID, data: schemas.TemplateVersionCreate
    ) -> AssessmentTemplateVersion:
        """Editing a template creates a NEW version (spec §6.4) — existing
        versions are never rewritten, and existing assessments keep the
        version they were created with."""
        template = await self.get_template(school_id, template_id)
        existing = await self._repo.list_versions(school_id, template_id)
        version_no = (existing[-1].version_no if existing else 0) + 1
        template.version += 1
        try:
            return await self._repo.create_version(
                AssessmentTemplateVersion(
                    school_id=school_id,
                    template_id=template_id,
                    version_no=version_no,
                    status="draft",
                    definition=data.definition.model_dump(mode="json"),
                )
            )
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "A version with that number already exists") from exc

    async def activate_template_version(
        self, school_id: UUID, version_id: UUID
    ) -> AssessmentTemplateVersion:
        """Draft → active. The previously active version of the same template
        is retired — assessments pin the version they were created with, so
        retiring it changes nothing for them (spec §6.4)."""
        version = await self._repo.get_version(school_id, version_id)
        if version is None:
            raise ProblemError(NOT_FOUND, "Template version not found", status=404)
        if version.status == "retired":
            raise ProblemError(
                INVALID_STATE_TRANSITION, "A retired template version cannot be reactivated"
            )
        if version.status == "active":
            return version
        current = await self._repo.get_active_version(school_id, version.template_id)
        if current is not None:
            await self._repo.set_version_status(current, "retired")
        await self._repo.set_version_status(version, "active")
        return version

    # ---- assessments -----------------------------------------------------------

    async def create_assessment(
        self, school_id: UUID, data: schemas.AssessmentCreate
    ) -> Assessment:
        """One result set per (term, class, section, subject). The template
        version must be active — a draft has never been approved for use, a
        retired one is closed."""
        await self._one_or_404(Term, school_id=school_id, id_=data.term_id, label="Term")
        await self._one_or_404(Class, school_id=school_id, id_=data.class_id, label="Class")
        await self._one_or_404(Subject, school_id=school_id, id_=data.subject_id, label="Subject")
        version = await self._repo.get_version(school_id, data.template_version_id)
        if version is None:
            raise ProblemError(NOT_FOUND, "Template version not found", status=404)
        if version.status != "active":
            raise ProblemError(VALIDATION_ERROR, "Template version is not active")
        existing = await self._repo.get_assessment_by_natural_key(
            school_id,
            term_id=data.term_id,
            class_id=data.class_id,
            subject_id=data.subject_id,
            section_id=data.section_id,
        )
        if existing is not None:
            raise ProblemError(
                CONFLICT,
                "An assessment already exists for that term, class, section and subject",
            )
        try:
            return await self._repo.create_assessment(
                Assessment(
                    school_id=school_id,
                    term_id=data.term_id,
                    class_id=data.class_id,
                    section_id=data.section_id,
                    subject_id=data.subject_id,
                    template_version_id=data.template_version_id,
                    workflow_state="draft",
                )
            )
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "Assessment references inconsistent records") from exc

    async def get_assessment(self, school_id: UUID, assessment_id: UUID) -> Assessment:
        return await self._one_or_404(
            Assessment, school_id=school_id, id_=assessment_id, label="Assessment"
        )

    async def list_assessments(
        self,
        school_id: UUID,
        *,
        scope: str,
        actor: Actor,
        term_id: UUID | None = None,
        class_id: UUID | None = None,
        subject_id: UUID | None = None,
    ) -> list[Assessment]:
        """`school` scope lists everything; `assigned` narrows to the actor's
        teacher assignments (spec §7.2); `own` makes no sense for assessments
        and is denied."""
        if scope == "assigned":
            return await self._repo.list_assessments(
                school_id,
                term_id=term_id,
                class_id=class_id,
                subject_id=subject_id,
                teacher_user_id=actor.user_id,
            )
        if scope != "school":
            raise ProblemError(PERMISSION_DENIED, "assessments.view requires school or assigned")
        return await self._repo.list_assessments(
            school_id, term_id=term_id, class_id=class_id, subject_id=subject_id
        )

    # ---- score sheet -----------------------------------------------------------

    async def get_sheet(self, school_id: UUID, assessment_id: UUID) -> schemas.ScoreSheetResponse:
        """The roster (academic's subject enrolments for this term/class/
        section/subject) merged with whatever scores exist."""
        assessment = await self.get_assessment(school_id, assessment_id)
        term = await self._one_or_404(
            Term, school_id=school_id, id_=assessment.term_id, label="Term"
        )
        version = await self._repo.get_version(school_id, assessment.template_version_id)
        if version is None:
            raise ProblemError(NOT_FOUND, "Template version not found", status=404)
        definition = schemas.TemplateDefinition.model_validate(version.definition)

        roster = await self._repo.list_sheet_rows(
            school_id,
            session_id=term.session_id,
            class_id=assessment.class_id,
            section_id=assessment.section_id,
            subject_id=assessment.subject_id,
        )
        existing = {
            (score.subject_enrolment_id, score.component_key): score
            for score in await self._repo.list_scores(school_id, assessment.id)
        }
        rows = [
            schemas.SheetRow(
                subject_enrolment_id=se_id,
                student_id=student_id,
                student_name=f"{first} {last}",
                admission_no=admission_no,
                scores={
                    key: schemas.ScoreCell.model_validate(score)
                    for key, score in (
                        (ck, existing[(se_id, ck)])
                        for ck in definition.component_keys()
                        if (se_id, ck) in existing
                    )
                },
            )
            for se_id, student_id, first, last, admission_no in roster
        ]
        return schemas.ScoreSheetResponse(
            assessment_id=assessment.id,
            workflow_state=assessment.workflow_state,
            components=definition.components,
            rows=rows,
        )

    # ---- score entry -----------------------------------------------------------

    async def _check_enter_scope(self, assessment: Assessment, actor: Actor, scope: str) -> None:
        """The Phase 3 exit criterion: a teacher with only the `assigned`
        scope may not write a score outside their assignments. `school` scope
        (admin) passes; `own` is meaningless for scores and denied."""
        if scope == "school":
            return
        if scope != "assigned":
            raise ProblemError(
                PERMISSION_DENIED, "scores.enter requires school or assigned scope"
            )

        term = await self._one_or_404(
            Term, school_id=assessment.school_id, id_=assessment.term_id, label="Term"
        )
        assignment = await self._s.scalar(
            select(TeacherAssignment.id).where(
                TeacherAssignment.school_id == assessment.school_id,
                TeacherAssignment.teacher_user_id == actor.user_id,
                TeacherAssignment.session_id == term.session_id,
                TeacherAssignment.class_id == assessment.class_id,
                (
                    TeacherAssignment.section_id.is_(None)
                    | (TeacherAssignment.section_id == assessment.section_id)
                ),
                (
                    TeacherAssignment.subject_id.is_(None)
                    | (TeacherAssignment.subject_id == assessment.subject_id)
                ),
            )
        )
        if assignment is None:
            raise ProblemError(
                PERMISSION_DENIED,
                "You are not assigned to this class/subject for the assessment's session",
                status=403,
            )

    async def _editable_assessment(self, school_id: UUID, assessment_id: UUID) -> Assessment:
        assessment = await self.get_assessment(school_id, assessment_id)
        if assessment.workflow_state not in EDITABLE_STATES:
            raise ProblemError(
                INVALID_STATE_TRANSITION,
                f"Assessment is {assessment.workflow_state}; scores are editable only "
                f"in {' and '.join(EDITABLE_STATES)}",
            )
        return assessment

    async def batch_upsert_scores(
        self,
        school_id: UUID,
        assessment_id: UUID,
        rows: list[schemas.ScoreRowInput],
        actor: Actor,
        *,
        scope: str = "school",
        source: str = "web",
        reason: str | None = None,
    ) -> list[Score]:
        """Batch upsert (spec §6.4). All-or-nothing: every row is validated,
        and one bad row rejects the whole batch — with ALL bad cells reported
        (extra.errors), so the client redraws the sheet with every problem
        visible. The import path is the one with row-level partial success."""
        assessment = await self._editable_assessment(school_id, assessment_id)
        await self._check_enter_scope(assessment, actor, scope)
        applied, row_errors = await self._apply_rows(
            school_id,
            assessment,
            list(enumerate(rows, start=1)),
            actor=actor,
            source=source,
            reason=reason,
        )
        if row_errors:
            # A version conflict is a concurrency failure (409), not a
            # validation failure (422): a batch whose errors are all
            # base_version problems answers 409; anything else answers 422
            # with every bad cell reported either way.
            if all(e.get("code") == VERSION_CONFLICT for e in row_errors):
                code = VERSION_CONFLICT
            else:
                code = VALIDATION_ERROR
            raise ProblemError(code, row_errors[0]["detail"], extra={"errors": row_errors})
        return applied

    async def apply_import(
        self, school_id: UUID, assessment_id: UUID, csv_text: str, actor: Actor
    ) -> dict:
        """Bulk import: row-level partial success (spec §16 Phase 3). Valid
        rows are applied (source='import'); invalid rows are reported per CSV
        row number in the returned result. A CSV whose header lacks the
        required columns, or a non-editable assessment, fails the whole job."""
        assessment = await self._editable_assessment(school_id, assessment_id)
        numbered_rows, row_errors = _parse_score_csv(csv_text)
        applied, apply_errors = await self._apply_rows(
            school_id,
            assessment,
            numbered_rows,
            actor=actor,
            source="import",
            reason="bulk import",
        )
        return {
            "applied": len(applied),
            "submitted": len(numbered_rows) + len(row_errors),
            "errors": row_errors + apply_errors,
        }

    async def _apply_rows(
        self,
        school_id: UUID,
        assessment: Assessment,
        numbered_rows: list[tuple[int, schemas.ScoreRowInput]],
        *,
        actor: Actor,
        source: str,
        reason: str | None,
    ) -> tuple[list[Score], list[dict]]:
        """Shared apply path for the web batch and the import job: validates
        against the pinned template version and the sheet roster, enforces
        per-cell optimistic concurrency, writes ledger + outbox per change.

        `numbered_rows` pairs each row with its caller-facing label (the web
        path numbers list positions; the import numbers CSV data rows) so the
        row_errors report points at the right line either way.

        Returns (applied scores, row errors). Rows that fail validation or
        conflict are skipped with an error entry — never applied half-way;
        the caller decides whether errors mean "reject everything" (web) or
        "report and continue" (import). Conflict entries carry
        `"code": VERSION_CONFLICT` so the web path can answer 409 when
        staleness, not validation, is the only problem.
        """
        version = await self._repo.get_version(school_id, assessment.template_version_id)
        if version is None:
            raise ProblemError(NOT_FOUND, "Template version not found", status=404)
        definition = schemas.TemplateDefinition.model_validate(version.definition)
        components = {c.key: c for c in definition.components}

        term = await self._one_or_404(
            Term, school_id=school_id, id_=assessment.term_id, label="Term"
        )
        roster_ids = {
            se_id
            for se_id, _sid, _f, _l, _a in await self._repo.list_sheet_rows(
                school_id,
                session_id=term.session_id,
                class_id=assessment.class_id,
                section_id=assessment.section_id,
                subject_id=assessment.subject_id,
            )
        }

        row_errors: list[dict] = []
        valid: list[tuple[int, schemas.ScoreRowInput]] = []
        seen: set[tuple[UUID, str]] = set()
        for row_no, row in numbered_rows:
            detail = self._row_problem(row, components, roster_ids, seen)
            if detail is None:
                seen.add((row.subject_enrolment_id, row.component_key))
                valid.append((row_no, row))
            else:
                row_errors.append({"row": row_no, "detail": detail})

        applied: list[Score] = []
        for row_no, row in valid:
            existing = await self._repo.get_score_for_cell(
                school_id,
                assessment_id=assessment.id,
                subject_enrolment_id=row.subject_enrolment_id,
                component_key=row.component_key,
            )
            if existing is None:
                if row.base_version is not None:
                    row_errors.append(
                        {
                            "row": row_no,
                            "code": VERSION_CONFLICT,
                            "detail": "Row carries a base_version but no score exists yet",
                        }
                    )
                    continue
                score = Score(
                    school_id=school_id,
                    assessment_id=assessment.id,
                    subject_enrolment_id=row.subject_enrolment_id,
                    component_key=row.component_key,
                    status=row.status,
                    value=row.value,
                    entered_by=actor.user_id if row.status == "entered" else None,
                    entered_at=datetime.now(UTC) if row.status == "entered" else None,
                    updated_by=actor.user_id,
                    version=1,
                )
                try:
                    score = await self._repo.add_score(score)
                except IntegrityError as exc:
                    raise ProblemError(
                        CONFLICT, "Score references inconsistent records"
                    ) from exc
                await self._record_change(
                    school_id,
                    score,
                    old_status=None,
                    old_value=None,
                    new_status=score.status,
                    new_value=score.value,
                    actor=actor,
                    source=source,
                    reason=reason,
                )
                applied.append(score)
            else:
                if row.base_version is None:
                    row_errors.append(
                        {
                            "row": row_no,
                            "code": VERSION_CONFLICT,
                            "detail": (
                                "Score already exists; send its current version as "
                                "base_version to overwrite"
                            ),
                        }
                    )
                    continue
                if row.base_version != existing.version:
                    row_errors.append(
                        {
                            "row": row_no,
                            "code": VERSION_CONFLICT,
                            "detail": (
                                f"Version conflict: base_version {row.base_version}, "
                                f"current {existing.version}"
                            ),
                        }
                    )
                    continue
                if existing.status == row.status and existing.value == row.value:
                    applied.append(existing)  # no-op write: no bump, no ledger row
                    continue
                old_status, old_value = existing.status, existing.value
                existing.status = row.status
                existing.value = row.value
                if row.status == "entered" and old_status != "entered":
                    existing.entered_by = actor.user_id
                    existing.entered_at = datetime.now(UTC)
                existing.updated_by = actor.user_id
                existing.version += 1
                await self._s.flush()
                await self._record_change(
                    school_id,
                    existing,
                    old_status=old_status,
                    old_value=old_value,
                    new_status=existing.status,
                    new_value=existing.value,
                    actor=actor,
                    source=source,
                    reason=reason,
                )
                applied.append(existing)
        return applied, row_errors

    def _row_problem(
        self,
        row: schemas.ScoreRowInput,
        components: dict[str, schemas.ComponentDef],
        roster_ids: set[UUID],
        seen: set[tuple[UUID, str]],
    ) -> str | None:
        """Per-row validation; None when the row may proceed."""
        cell = (row.subject_enrolment_id, row.component_key)
        if cell in seen:
            return (
                f"Duplicate rows for enrolment {row.subject_enrolment_id}, "
                f"component {row.component_key}"
            )
        if row.component_key not in components:
            return (
                f"Unknown component {row.component_key!r} — template defines "
                f"{sorted(components)}"
            )
        if row.subject_enrolment_id not in roster_ids:
            return (
                f"Enrolment {row.subject_enrolment_id} is not on this assessment's "
                "sheet (not enrolled in this subject)"
            )
        try:
            validate_score_row(row, components[row.component_key])
        except ProblemError as exc:
            return exc.detail
        return None

    async def _record_change(
        self,
        school_id: UUID,
        score: Score,
        *,
        old_status: str | None,
        old_value,
        new_status: str | None,
        new_value,
        actor: Actor,
        source: str,
        reason: str | None,
    ) -> None:
        """Append the ledger row and the outbox event in the caller's
        transaction (spec §6.4 — score_changes is append-only, no UPDATE)."""
        await self._repo.add_score_change(
            ScoreChange(
                school_id=school_id,
                score_id=score.id,
                old_status=old_status,
                old_value=old_value,
                new_status=new_status,
                new_value=new_value,
                reason=reason,
                changed_by=actor.user_id,
                source=source,
            )
        )
        await enqueue_outbox_event(
            self._s,
            school_id=str(school_id),
            topic=TOPIC_SCORE_CHANGED,
            payload={
                "score_id": str(score.id),
                "assessment_id": str(score.assessment_id),
                "subject_enrolment_id": str(score.subject_enrolment_id),
                "component_key": score.component_key,
                "old_status": old_status,
                "old_value": str(old_value) if old_value is not None else None,
                "new_status": new_status,
                "new_value": str(new_value) if new_value is not None else None,
                "version": score.version,
                "source": source,
            },
        )

    async def get_score_history(self, school_id: UUID, score_id: UUID) -> list[ScoreChange]:
        score = await self._repo.get_score(school_id, score_id)
        if score is None:
            raise ProblemError(NOT_FOUND, "Score not found", status=404)
        return await self._repo.list_score_changes(school_id, score_id)

    # ---- bulk import -------------------------------------------------------------

    async def get_job(self, school_id: UUID, job_id: UUID) -> Job:
        """The jobs table has no RLS (school_id is a data column there), so
        the school predicate here is the caller-facing tenancy check."""
        job = await self._s.get(Job, job_id)
        if job is None or (job.school_id is not None and job.school_id != school_id):
            raise ProblemError(NOT_FOUND, "Job not found", status=404)
        return job

    async def enqueue_import(
        self,
        school_id: UUID,
        assessment_id: UUID,
        csv_text: str,
        actor: Actor,
        *,
        scope: str = "school",
    ) -> Job:
        """Record the import job durably (survives Redis loss — ADR 003) and
        return it. Authorization is checked here, at enqueue time, so an
        out-of-scope import is rejected with a 403 now rather than as a
        failed job later; the job itself re-validates the assessment state
        when it runs."""
        assessment = await self.get_assessment(school_id, assessment_id)
        await self._check_enter_scope(assessment, actor, scope)
        job = Job(
            school_id=school_id,
            type="import_scores",
            status="queued",
            params={"assessment_id": str(assessment_id), "csv": csv_text},
            created_by=actor.user_id,
        )
        self._s.add(job)
        await self._s.flush()
        return job


def _parse_score_csv(csv_text: str) -> tuple[list[tuple[int, schemas.ScoreRowInput]], list[dict]]:
    """CSV → (data-row-numbered rows, parse errors). Row numbers are 1-based
    DATA row numbers (the header is not numbered) — the same numbering the
    error report uses downstream. Parse failures never abort the file."""
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = set(reader.fieldnames or ())
    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise ProblemError(
            VALIDATION_ERROR,
            f"CSV header must include {sorted(CSV_REQUIRED_COLUMNS)}; missing {missing}",
        )
    rows: list[tuple[int, schemas.ScoreRowInput]] = []
    errors: list[dict] = []
    for i, raw in enumerate(reader, start=1):
        try:
            se_id = UUID((raw.get("subject_enrolment_id") or "").strip())
            key = (raw.get("component_key") or "").strip()
            status = (raw.get("status") or "").strip()
            raw_value = (raw.get("value") or "").strip()
            if not key or not status:
                raise ValueError("component_key and status are required")
            value = Decimal(raw_value) if raw_value else None
            base_version_raw = (raw.get("base_version") or "").strip()
            base_version = int(base_version_raw) if base_version_raw else None
            rows.append(
                (
                    i,
                    schemas.ScoreRowInput(
                        subject_enrolment_id=se_id,
                        component_key=key,
                        status=status,  # type: ignore[arg-type]
                        value=value,
                        base_version=base_version,
                    ),
                )
            )
        except (ValueError, InvalidOperation) as exc:
            errors.append({"row": i, "detail": f"unparseable row: {exc}"})
    return rows, errors
