"""Academic repository — structure, enrolment and promotion queries (Phase 2).

Primitives only; the promotion transaction is composed in
`academic.service.run_promotion`. Every query carries an explicit school_id
predicate; RLS is the second layer. Enrolment history is append-only here:
ending an enrolment stamps `status`/`ended_on`, nothing is updated away, so
results (Phase 4) that reference `enrolment_id` keep their context
(spec §6.3 historical-context invariant).
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic.models import (
    AcademicSession,
    Class,
    ClassSubject,
    EducationalLevel,
    Enrolment,
    PromotionRecord,
    Section,
    Subject,
    SubjectEnrolment,
    TeacherAssignment,
    Term,
)


class AcademicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- sessions & terms ---------------------------------------------------

    async def create_session(self, session_row: AcademicSession) -> AcademicSession:
        self._s.add(session_row)
        await self._s.flush()
        return session_row

    async def get_session(self, school_id: UUID, session_id: UUID) -> AcademicSession | None:
        result = await self._s.execute(
            select(AcademicSession).where(
                AcademicSession.school_id == school_id, AcademicSession.id == session_id
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(self, school_id: UUID) -> list[AcademicSession]:
        result = await self._s.execute(
            select(AcademicSession)
            .where(AcademicSession.school_id == school_id)
            .order_by(AcademicSession.name.desc())
        )
        return list(result.scalars().all())

    async def get_current_session(self, school_id: UUID) -> AcademicSession | None:
        result = await self._s.execute(
            select(AcademicSession).where(
                AcademicSession.school_id == school_id, AcademicSession.is_current.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def clear_current_session(self, school_id: UUID, keep_id: UUID) -> None:
        """`is_current` is single-valued per school: unset the others first."""
        rows = await self.list_sessions(school_id)
        for row in rows:
            if row.id != keep_id and row.is_current:
                row.is_current = False
        await self._s.flush()

    async def create_term(self, term: Term) -> Term:
        self._s.add(term)
        await self._s.flush()
        return term

    async def list_terms(self, school_id: UUID, session_id: UUID) -> list[Term]:
        result = await self._s.execute(
            select(Term)
            .where(Term.school_id == school_id, Term.session_id == session_id)
            .order_by(Term.ordinal)
        )
        return list(result.scalars().all())

    # ---- levels / classes / sections -----------------------------------------

    async def create_level(self, level: EducationalLevel) -> EducationalLevel:
        self._s.add(level)
        await self._s.flush()
        return level

    async def list_levels(self, school_id: UUID) -> list[EducationalLevel]:
        result = await self._s.execute(
            select(EducationalLevel)
            .where(EducationalLevel.school_id == school_id)
            .order_by(EducationalLevel.ordinal)
        )
        return list(result.scalars().all())

    async def create_class(self, klass: Class) -> Class:
        self._s.add(klass)
        await self._s.flush()
        return klass

    async def get_class(self, school_id: UUID, class_id: UUID) -> Class | None:
        result = await self._s.execute(
            select(Class).where(Class.school_id == school_id, Class.id == class_id)
        )
        return result.scalar_one_or_none()

    async def list_classes(self, school_id: UUID, level_id: UUID | None = None) -> list[Class]:
        """Promotion order: level ordinal, then class ordinal (Nursery → SS 3)."""
        stmt = (
            select(Class)
            .join(EducationalLevel, EducationalLevel.id == Class.level_id)
            .where(Class.school_id == school_id)
            .order_by(EducationalLevel.ordinal, Class.ordinal, Class.name)
        )
        if level_id is not None:
            stmt = stmt.where(Class.level_id == level_id)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def create_section(self, section: Section) -> Section:
        self._s.add(section)
        await self._s.flush()
        return section

    async def list_sections(self, school_id: UUID, class_id: UUID) -> list[Section]:
        result = await self._s.execute(
            select(Section)
            .where(Section.school_id == school_id, Section.class_id == class_id)
            .order_by(Section.name)
        )
        return list(result.scalars().all())

    # ---- subjects / class_subjects --------------------------------------------

    async def create_subject(self, subject: Subject) -> Subject:
        self._s.add(subject)
        await self._s.flush()
        return subject

    async def list_subjects(self, school_id: UUID) -> list[Subject]:
        result = await self._s.execute(
            select(Subject).where(Subject.school_id == school_id).order_by(Subject.name)
        )
        return list(result.scalars().all())

    async def create_class_subject(self, class_subject: ClassSubject) -> ClassSubject:
        self._s.add(class_subject)
        await self._s.flush()
        return class_subject

    async def list_class_subjects(self, class_id: UUID) -> list[ClassSubject]:
        result = await self._s.execute(
            select(ClassSubject).where(ClassSubject.class_id == class_id)
        )
        return list(result.scalars().all())

    # ---- enrolments -------------------------------------------------------------

    async def create_enrolment(self, enrolment: Enrolment) -> Enrolment:
        self._s.add(enrolment)
        await self._s.flush()
        return enrolment

    async def get_enrolment(self, school_id: UUID, enrolment_id: UUID) -> Enrolment | None:
        result = await self._s.execute(
            select(Enrolment).where(Enrolment.school_id == school_id, Enrolment.id == enrolment_id)
        )
        return result.scalar_one_or_none()

    async def get_live_enrolment(self, student_id: UUID, session_id: UUID) -> Enrolment | None:
        """The one status='enrolled' row for (student, session), if any."""
        result = await self._s.execute(
            select(Enrolment).where(
                Enrolment.student_id == student_id,
                Enrolment.session_id == session_id,
                Enrolment.status == "enrolled",
            )
        )
        return result.scalar_one_or_none()

    async def get_live_enrolments(
        self, student_ids: list[UUID], session_id: UUID
    ) -> dict[UUID, Enrolment]:
        """Batch form of get_live_enrolment: student_id → enrolment."""
        if not student_ids:
            return {}
        result = await self._s.execute(
            select(Enrolment).where(
                Enrolment.student_id.in_(student_ids),
                Enrolment.session_id == session_id,
                Enrolment.status == "enrolled",
            )
        )
        return {e.student_id: e for e in result.scalars().all()}

    async def end_enrolment(self, enrolment: Enrolment, *, status: str, ended_on: date) -> None:
        """Close out an enrolment in place. The row, its subject_enrolments and
        any results attached to it are never modified beyond this stamp."""
        enrolment.status = status
        enrolment.ended_on = ended_on
        await self._s.flush()

    async def create_subject_enrolments(self, rows: list[SubjectEnrolment]) -> None:
        self._s.add_all(rows)
        await self._s.flush()

    # ---- teacher assignments ------------------------------------------------------

    async def create_teacher_assignment(self, assignment: TeacherAssignment) -> TeacherAssignment:
        self._s.add(assignment)
        await self._s.flush()
        return assignment

    async def list_teacher_assignments(
        self, school_id: UUID, teacher_user_id: UUID, session_id: UUID
    ) -> list[TeacherAssignment]:
        result = await self._s.execute(
            select(TeacherAssignment).where(
                TeacherAssignment.school_id == school_id,
                TeacherAssignment.teacher_user_id == teacher_user_id,
                TeacherAssignment.session_id == session_id,
            )
        )
        return list(result.scalars().all())

    # ---- promotions -----------------------------------------------------------------

    async def add_promotion_record(self, record: PromotionRecord) -> PromotionRecord:
        self._s.add(record)
        await self._s.flush()
        return record
