"""Grading repository — schemes, processing runs, processed results (Phase 4).

Primitives only; transactions are composed in `grading.service`. Every query
carries an explicit school_id predicate; RLS on each table is the second
layer behind it (docs/handover_docs/02-api-conventions.md).

Read edges (models only, never another module's repository — the Phase 2
precedent):
  - `list_results` joins app.academic.models (SubjectEnrolment, Enrolment)
    and app.people.models.Student for the names the results table shows.
The scores/roster consumption set is NOT re-queried here:
`grading.service` calls `AssessmentService.get_sheet`, the same roster+cells
path the score sheet uses (a service-interface edge, like academic.service →
people.service) — one definition of "what is on the sheet", two consumers.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic.models import Enrolment, SubjectEnrolment
from app.grading.models import GradingScheme, ProcessedResult, ResultProcessingRun
from app.people.models import Student


class GradingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- schemes ---------------------------------------------------------------

    async def create_scheme(self, scheme: GradingScheme) -> GradingScheme:
        """Flush may raise IntegrityError on the (school, name, version_no)
        UNIQUE — the service maps it to CONFLICT."""
        self._s.add(scheme)
        await self._s.flush()
        return scheme

    async def get_scheme(self, school_id: UUID, scheme_id: UUID) -> GradingScheme | None:
        result = await self._s.execute(
            select(GradingScheme).where(
                GradingScheme.school_id == school_id, GradingScheme.id == scheme_id
            )
        )
        return result.scalar_one_or_none()

    async def list_schemes(
        self, school_id: UUID, *, name: str | None = None
    ) -> list[GradingScheme]:
        stmt = select(GradingScheme).where(GradingScheme.school_id == school_id)
        if name is not None:
            stmt = stmt.where(GradingScheme.name == name)
        result = await self._s.execute(stmt.order_by(GradingScheme.name, GradingScheme.version_no))
        return list(result.scalars().all())

    async def get_active_scheme(self, school_id: UUID, name: str) -> GradingScheme | None:
        result = await self._s.execute(
            select(GradingScheme).where(
                GradingScheme.school_id == school_id,
                GradingScheme.name == name,
                GradingScheme.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def set_scheme_status(self, scheme: GradingScheme, status: str) -> None:
        scheme.status = status
        await self._s.flush()

    # ---- runs --------------------------------------------------------------------

    async def create_run(self, run: ResultProcessingRun) -> ResultProcessingRun:
        self._s.add(run)
        await self._s.flush()
        return run

    async def get_run(self, school_id: UUID, run_id: UUID) -> ResultProcessingRun | None:
        result = await self._s.execute(
            select(ResultProcessingRun).where(
                ResultProcessingRun.school_id == school_id, ResultProcessingRun.id == run_id
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(self, school_id: UUID, assessment_id: UUID) -> list[ResultProcessingRun]:
        """Run history for an assessment, newest first (spec §9.4)."""
        result = await self._s.execute(
            select(ResultProcessingRun)
            .where(
                ResultProcessingRun.school_id == school_id,
                ResultProcessingRun.assessment_id == assessment_id,
            )
            .order_by(ResultProcessingRun.created_at.desc(), ResultProcessingRun.id)
        )
        return list(result.scalars().all())

    async def latest_succeeded_run(
        self, school_id: UUID, assessment_id: UUID
    ) -> ResultProcessingRun | None:
        """The 'current' run: the newest succeeded one (spec §9.4). Older runs
        are retained; failed ones never become current."""
        result = await self._s.execute(
            select(ResultProcessingRun)
            .where(
                ResultProcessingRun.school_id == school_id,
                ResultProcessingRun.assessment_id == assessment_id,
                ResultProcessingRun.status == "succeeded",
            )
            .order_by(ResultProcessingRun.created_at.desc(), ResultProcessingRun.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ---- processed results ---------------------------------------------------------

    async def add_processed_result(self, row: ProcessedResult) -> ProcessedResult:
        self._s.add(row)
        await self._s.flush()
        return row

    async def list_results(
        self, school_id: UUID, run_id: UUID
    ) -> list[tuple[ProcessedResult, str]]:
        """One run's results with student names, position-ordered (NULLs last,
        then name) — the report-card order. Read edge: academic.models
        (SubjectEnrolment, Enrolment) + people.models.Student — models only,
        never another module's repository."""
        result = await self._s.execute(
            select(ProcessedResult, Student)
            .join(
                SubjectEnrolment,
                SubjectEnrolment.id == ProcessedResult.subject_enrolment_id,
            )
            .join(Enrolment, Enrolment.id == SubjectEnrolment.enrolment_id)
            .join(Student, Student.id == Enrolment.student_id)
            .where(ProcessedResult.school_id == school_id, ProcessedResult.run_id == run_id)
            .order_by(
                ProcessedResult.position.asc().nulls_last(),
                Student.last_name,
                Student.first_name,
                Student.id,
            )
        )
        return [(row, f"{student.first_name} {student.last_name}") for row, student in result.all()]
