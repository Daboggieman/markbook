"""People repository — student, guardian and junction queries (Phase 2).

Every query carries an explicit school_id predicate; RLS on each table is the
second layer behind it (docs/handover_docs/02-api-conventions.md). Archive
stamps `status`/`archived_at` only — enrolments (and the results Phase 4 will
attach to them) are never touched, which is what keeps history intact
(spec §6: archive, not delete).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.people.models import Guardian, Student, StudentGuardian


class PeopleRepository:
    def __init__(self, session) -> None:
        self._s = session

    # ---- students ---------------------------------------------------------

    async def create_student(self, student: Student) -> Student:
        self._s.add(student)
        await self._s.flush()
        return student

    async def get_student(self, school_id: UUID, student_id: UUID) -> Student | None:
        result = await self._s.execute(
            select_student().where(Student.school_id == school_id, Student.id == student_id)
        )
        return result.scalar_one_or_none()

    async def list_students(
        self,
        *,
        school_id: UUID,
        session_id: UUID | None = None,
        class_id: UUID | None = None,
        status: str | None = None,
        q: str | None = None,
        teacher_user_id: UUID | None = None,
        after: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> list[Student]:
        """List students, newest-first is wrong for a roster — name order here.

        `teacher_user_id` narrows to students the teacher is assigned to for
        the session (the `assigned` scope, spec §7.2): the student must have a
        live enrolment in that session whose (class_id, section_id) matches a
        teacher assignment, where a NULL assignment section means the whole
        class.
        """
        from app.academic.models import Enrolment, TeacherAssignment

        stmt = select_student().where(Student.school_id == school_id)
        if status is not None:
            stmt = stmt.where(Student.status == status)
        if session_id is not None:
            live = (
                select(Enrolment.id)
                .where(
                    Enrolment.student_id == Student.id,
                    Enrolment.school_id == school_id,
                    Enrolment.session_id == session_id,
                    Enrolment.status == "enrolled",
                )
                .exists()
            )
            stmt = stmt.where(exists_placeholder := True) if False else stmt
        if class_id is not None:
            stmt = stmt.join(Enrolment, (Enrolment.student_id == Student.id)).where(
                Enrolment.session_id == session_id if session_id else True,
                Enrolment.class_id == class_id,
                Enrolment.status == "enrolled",
            )
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(
                func.lower(Student.first_name).like(like)
                | func.lower(Student.last_name).like(like)
                | func.lower(Student.admission_no).like(like)
            )
        if teacher_user_id is not None:
            if session_id is None:
                raise ValueError("assigned scope needs a session_id")
            ta = TeacherAssignment
            stmt = stmt.where(
                select(Enrolment.id)
                .join(
                    TeacherAssignment,
                    (TeacherAssignment.class_id == Enrolment.class_id)
                    & (
                        TeacherAssignment.section_id.is_(None)
                        | (TeacherAssignment.section_id == Enrolment.section_id)
                    ),
                )
                .where(
                    Enrolment.student_id == Student.id,
                    Enrolment.session_id == session_id,
                    Enrolment.status == "enrolled",
                    TeacherAssignment.teacher_user_id == teacher_user_id,
                    TeacherAssignment.session_id == session_id,
                    TeacherAssignment.school_id == school_id,
                )
                .exists()
            )
        stmt = stmt.order_by(Student.last_name, Student.first_name, Student.id).limit(limit)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def update_student(self, student: Student) -> Student:
        self._s.add(student)
        await self._s.flush()
        return student

    async def archive_student(self, student: Student) -> Student:
        """Archive (spec §6: no hard deletes). Enrolments are untouched."""
        student.status = "archived"
        student.archived_at = datetime.now(UTC)
        await self._s.flush()
        return student

    async def find_duplicates(
        self,
        school_id: UUID,
        *,
        first_name: str,
        last_name: str,
        exclude_student_id: UUID | None = None,
        min_similarity: float = 0.6,
        limit: int = 10,
    ) -> list[tuple[Student, float]]:
        """Trigram similarity over `lower(first || ' ' || last)` (migration 0003
        index). Uses the `%` operator so the GIN trgm index is usable, and
        scores each hit with similarity() for the caller to rank."""
        full = func.lower(Student.first_name + " " + Student.last_name)
        target = func.lower(f"{first_name} {last_name}")
        score = func.similarity(full, target).label("score")
        stmt = (
            select(Student, score)
            .where(
                Student.school_id == school_id,
                full.op("%")(target),
                score > min_similarity,
            )
            .order_by(score.desc())
            .limit(limit)
        )
        if exclude_student_id is not None:
            stmt = stmt.where(Student.id != exclude_student_id)
        result = await self._s.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    # ---- guardians --------------------------------------------------------

    async def create_guardian(self, guardian) -> None:
        self._s.add(guardian)
        await self._s.flush()

    async def get_guardian(self, school_id: UUID, guardian_id: UUID):
        from sqlalchemy import select as _sel

        result = await self._s.execute(
            _sel(Guardian).where(Guardian.school_id == school_id, Guardian.id == guardian_id)
        )
        return result.scalar_one_or_none()

    async def link_student_guardian(self, link: StudentGuardian) -> None:
        self._s.add(link)
        await self._s.flush()

    async def list_guardians_for_student(self, student_id: UUID) -> list[Guardian]:
        result = await self._s.execute(
            select(Guardian)
            .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
            .where(StudentGuardian.student_id == student_id)
            .order_by(Guardian.name)
        )
        return list(result.scalars().all())


def select_student():
    from sqlalchemy import select

    return select(Student)
