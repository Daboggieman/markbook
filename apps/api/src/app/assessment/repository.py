"""Assessment repository — templates, assessments, scores, ledger (Phase 3).

Primitives only; transactions are composed in `assessment.service`. Every
query carries an explicit school_id predicate; RLS on each table is the
second layer behind it (docs/handover_docs/02-api-conventions.md).

Academic/people read edges: `list_sheet_rows` joins Enrolment/ClassSubject
(app.academic.models) and Student (app.people.models) to build the score-sheet
roster. Models only, never another module's repository — the same precedent
people.repository set with its academic read edge in Phase 2. The sheet must
show names, and academic owns enrolments, so the join lives here rather than
duplicating a roster service method.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic.models import ClassSubject, Enrolment, SubjectEnrolment
from app.assessment.models import (
    Assessment,
    AssessmentTemplate,
    AssessmentTemplateVersion,
    Score,
    ScoreChange,
)
from app.people.models import Student


class AssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- templates & versions ------------------------------------------------

    async def create_template(self, template: AssessmentTemplate) -> AssessmentTemplate:
        self._s.add(template)
        await self._s.flush()
        return template

    async def get_template(self, school_id: UUID, template_id: UUID) -> AssessmentTemplate | None:
        result = await self._s.execute(
            select(AssessmentTemplate).where(
                AssessmentTemplate.school_id == school_id,
                AssessmentTemplate.id == template_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_templates(self, school_id: UUID) -> list[AssessmentTemplate]:
        result = await self._s.execute(
            select(AssessmentTemplate)
            .where(AssessmentTemplate.school_id == school_id)
            .order_by(AssessmentTemplate.name)
        )
        return list(result.scalars().all())

    async def create_version(
        self, version: AssessmentTemplateVersion
    ) -> AssessmentTemplateVersion:
        """Flush may raise IntegrityError on the (school, template, version_no)
        UNIQUE — the service maps it to CONFLICT."""
        self._s.add(version)
        await self._s.flush()
        return version

    async def get_version(
        self, school_id: UUID, version_id: UUID
    ) -> AssessmentTemplateVersion | None:
        result = await self._s.execute(
            select(AssessmentTemplateVersion).where(
                AssessmentTemplateVersion.school_id == school_id,
                AssessmentTemplateVersion.id == version_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_versions(
        self, school_id: UUID, template_id: UUID
    ) -> list[AssessmentTemplateVersion]:
        result = await self._s.execute(
            select(AssessmentTemplateVersion)
            .where(
                AssessmentTemplateVersion.school_id == school_id,
                AssessmentTemplateVersion.template_id == template_id,
            )
            .order_by(AssessmentTemplateVersion.version_no)
        )
        return list(result.scalars().all())

    async def get_active_version(
        self, school_id: UUID, template_id: UUID
    ) -> AssessmentTemplateVersion | None:
        result = await self._s.execute(
            select(AssessmentTemplateVersion).where(
                AssessmentTemplateVersion.school_id == school_id,
                AssessmentTemplateVersion.template_id == template_id,
                AssessmentTemplateVersion.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def set_version_status(
        self, version: AssessmentTemplateVersion, status: str
    ) -> None:
        version.status = status
        await self._s.flush()

    # ---- assessments -----------------------------------------------------------

    async def create_assessment(self, assessment: Assessment) -> Assessment:
        """Flush may raise IntegrityError on the natural-key UNIQUE
        (school, term, class, subject, section) — the service maps it."""
        self._s.add(assessment)
        await self._s.flush()
        return assessment

    async def get_assessment(self, school_id: UUID, assessment_id: UUID) -> Assessment | None:
        result = await self._s.execute(
            select(Assessment).where(
                Assessment.school_id == school_id, Assessment.id == assessment_id
            )
        )
        return result.scalar_one_or_none()

    async def get_assessment_by_natural_key(
        self,
        school_id: UUID,
        *,
        term_id: UUID,
        class_id: UUID,
        subject_id: UUID,
        section_id: UUID | None,
    ) -> Assessment | None:
        stmt = select(Assessment).where(
            Assessment.school_id == school_id,
            Assessment.term_id == term_id,
            Assessment.class_id == class_id,
            Assessment.subject_id == subject_id,
        )
        if section_id is None:
            stmt = stmt.where(Assessment.section_id.is_(None))
        else:
            stmt = stmt.where(Assessment.section_id == section_id)
        result = await self._s.execute(stmt)
        return result.scalar_one_or_none()

    async def list_assessments(
        self,
        school_id: UUID,
        *,
        term_id: UUID | None = None,
        class_id: UUID | None = None,
        subject_id: UUID | None = None,
        teacher_user_id: UUID | None = None,
    ) -> list[Assessment]:
        """Assessments for the school, newest first.

        `teacher_user_id` narrows to the `assigned` scope (spec §7.2): the
        assessment's (term→session, class, section, subject) must be covered by
        one of the teacher's assignments — a NULL assignment section/subject
        means "any section/subject", mirroring people.repository's filter.
        """
        from app.academic.models import Term, TeacherAssignment

        stmt = select(Assessment).where(Assessment.school_id == school_id)
        if term_id is not None:
            stmt = stmt.where(Assessment.term_id == term_id)
        if class_id is not None:
            stmt = stmt.where(Assessment.class_id == class_id)
        if subject_id is not None:
            stmt = stmt.where(Assessment.subject_id == subject_id)
        if teacher_user_id is not None:
            stmt = stmt.where(
                select(TeacherAssignment.id)
                .join(Term, Term.id == Assessment.term_id)
                .where(
                    TeacherAssignment.teacher_user_id == teacher_user_id,
                    TeacherAssignment.session_id == Term.session_id,
                    TeacherAssignment.school_id == school_id,
                    TeacherAssignment.class_id == Assessment.class_id,
                    TeacherAssignment.section_id.is_(None)
                    | (TeacherAssignment.section_id == Assessment.section_id),
                    TeacherAssignment.subject_id.is_(None)
                    | (TeacherAssignment.subject_id == Assessment.subject_id),
                )
                .exists()
            )
        stmt = stmt.order_by(Assessment.created_at.desc(), Assessment.id)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    # ---- scores & ledger ---------------------------------------------------------

    async def get_score(
        self, school_id: UUID, score_id: UUID
    ) -> Score | None:
        result = await self._s.execute(
            select(Score).where(Score.school_id == school_id, Score.id == score_id)
        )
        return result.scalar_one_or_none()

    async def get_score_for_cell(
        self, school_id: UUID, *, assessment_id: UUID, subject_enrolment_id: UUID, component_key: str
    ) -> Score | None:
        result = await self._s.execute(
            select(Score).where(
                Score.school_id == school_id,
                Score.assessment_id == assessment_id,
                Score.subject_enrolment_id == subject_enrolment_id,
                Score.component_key == component_key,
            )
        )
        return result.scalar_one_or_none()

    async def list_scores(self, school_id: UUID, assessment_id: UUID) -> list[Score]:
        result = await self._s.execute(
            select(Score)
            .where(Score.school_id == school_id, Score.assessment_id == assessment_id)
            .order_by(Score.subject_enrolment_id, Score.component_key)
        )
        return list(result.scalars().all())

    async def add_score(self, score: Score) -> Score:
        self._s.add(score)
        await self._s.flush()
        return score

    async def add_score_change(self, change: ScoreChange) -> ScoreChange:
        self._s.add(change)
        await self._s.flush()
        return change

    async def list_score_changes(self, school_id: UUID, score_id: UUID) -> list[ScoreChange]:
        result = await self._s.execute(
            select(ScoreChange)
            .where(ScoreChange.school_id == school_id, ScoreChange.score_id == score_id)
            .order_by(ScoreChange.changed_at, ScoreChange.id)
        )
        return list(result.scalars().all())

    # ---- score-sheet roster (academic/people read edge) ----------------------------

    async def list_sheet_rows(
        self,
        school_id: UUID,
        *,
        session_id: UUID,
        class_id: UUID,
        section_id: UUID | None,
        subject_id: UUID,
    ) -> list[tuple[UUID, UUID, str, str, str]]:
        """The roster the score sheet is drawn from: one row per live
        subject enrolment, (subject_enrolment_id, student_id, first_name,
        last_name, admission_no), name-ordered.

        An assessment without a section covers every live enrolment in the
        class; a sectioned one covers only that section's enrolments.
        """
        stmt = (
            select(
                SubjectEnrolment.id,
                Enrolment.student_id,
                Student.first_name,
                Student.last_name,
                Student.admission_no,
            )
            .join(Enrolment, Enrolment.id == SubjectEnrolment.enrolment_id)
            .join(ClassSubject, ClassSubject.id == SubjectEnrolment.class_subject_id)
            .join(Student, Student.id == Enrolment.student_id)
            .where(
                SubjectEnrolment.school_id == school_id,
                Enrolment.session_id == session_id,
                Enrolment.class_id == class_id,
                Enrolment.status == "enrolled",
                ClassSubject.class_id == class_id,
                ClassSubject.subject_id == subject_id,
            )
            .order_by(Student.last_name, Student.first_name, Student.id)
        )
        if section_id is not None:
            stmt = stmt.where(Enrolment.section_id == section_id)
        result = await self._s.execute(stmt)
        return [(row[0], row[1], row[2], row[3], row[4]) for row in result.all()]
