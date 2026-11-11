"""People service — student and guardian business logic (Phase 2).

Duplicate detection: creation is blocked at a high similarity threshold
(POSSIBLE_DUPLICATE 409 with the candidates attached); `allow_duplicate`
bypasses it once the operator has eyeballed the candidates. The looser
0.6 threshold is what POST /students/check-duplicates reports.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.people import schemas
from app.people.models import Guardian, Student, StudentGuardian
from app.people.repository import PeopleRepository
from app.platform.errors import NOT_FOUND, POSSIBLE_DUPLICATE, VERSION_CONFLICT, ProblemError

CHECK_SIMILARITY = 0.6  # report threshold (check-duplicates endpoint)
BLOCK_SIMILARITY = 0.85  # creation block threshold


class PeopleService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = PeopleRepository(session)

    # ---- students ---------------------------------------------------------

    async def create_student(self, school_id: UUID, data: schemas.StudentCreate) -> Student:
        if not data.allow_duplicate:
            hits = await self._repo.find_duplicates(
                school_id,
                first_name=data.first_name,
                last_name=data.last_name,
                min_similarity=BLOCK_SIMILARITY,
            )
            if hits:
                candidates = [
                    schemas.DuplicateCandidate(
                        student_id=hit.id,
                        first_name=hit.first_name,
                        last_name=hit.last_name,
                        dob=hit.dob,
                        admission_no=hit.admission_no,
                        similarity=round(score, 3),
                    ).model_dump(mode="json")
                    for hit, score in hits
                ]
                raise ProblemError(
                    POSSIBLE_DUPLICATE,
                    "A very similar student already exists; re-send with "
                    "allow_duplicate=true if this is genuinely a new student",
                    extra={"candidates": candidates},
                )
        student = Student(
            school_id=school_id,
            first_name=data.first_name,
            middle_name=data.middle_name,
            last_name=data.last_name,
            dob=data.dob,
            sex=data.sex,
            admission_no=data.admission_no,
            system_id=data.system_id,
        )
        return await self._repo.create_student(student)

    async def get_student(self, school_id: UUID, student_id: UUID) -> Student:
        student = await self._repo.get_student(school_id, student_id)
        if student is None:
            raise ProblemError(NOT_FOUND, "Student not found", status=404)
        return student

    async def list_students(
        self,
        *,
        scope: str,
        school_id: UUID,
        teacher_user_id: UUID | None = None,
        session_id: UUID | None = None,
        class_id: UUID | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 50,
    ) -> list[Student]:
        """`scope` comes from access.scope_filter(grants, "students.view").

        - school → the whole school
        - assigned → only students in the teacher's own assignments
        - own → students have no created_by; treated as empty
        """
        if scope == "own":
            return []
        if scope == "assigned":
            return await self._repo.list_students(
                school_id=school_id,
                session_id=session_id,
                class_id=class_id,
                status=status,
                q=q,
                teacher_user_id=teacher_user_id,
                limit=limit,
            )
        return await self._repo.list_students(
            school_id=school_id,
            session_id=session_id,
            class_id=class_id,
            status=status,
            q=q,
            limit=limit,
        )

    async def update_student(
        self, school_id: UUID, student_id: UUID, data: schemas.StudentUpdate
    ) -> Student:
        student = await self.get_student(school_id, student_id)
        if student.version != data.version:
            raise ProblemError(
                VERSION_CONFLICT,
                "Student was modified by someone else; reload and retry",
            )
        for field in (
            "first_name",
            "middle_name",
            "last_name",
            "dob",
            "sex",
            "admission_no",
            "system_id",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(student, field, value)
        return await self._repo.update_student(student)

    async def archive_student(self, school_id: UUID, student_id: UUID, version: int) -> Student:
        """Archive, never delete (spec §6). Enrolments and any results
        attached to them are untouched — that is the history invariant."""
        student = await self.get_student(school_id, student_id)
        if student.version != version:
            raise ProblemError(
                VERSION_CONFLICT,
                "Student was modified by someone else; reload and retry",
            )
        return await self._repo.archive_student(student)

    async def check_duplicates(
        self, school_id: UUID, data: schemas.DuplicateCheckRequest
    ) -> schemas.DuplicateCheckResponse:
        hits = await self._repo.find_duplicates(
            school_id,
            first_name=data.first_name,
            last_name=data.last_name,
            exclude_student_id=data.exclude_student_id,
            min_similarity=CHECK_SIMILARITY,
        )
        return schemas.DuplicateCheckResponse(
            candidates=[
                schemas.DuplicateCandidate(
                    student_id=hit.id,
                    first_name=hit.first_name,
                    last_name=hit.last_name,
                    dob=hit.dob,
                    admission_no=hit.admission_no,
                    similarity=round(score, 3),
                )
                for hit, score in hits
            ]
        )

    # ---- guardians --------------------------------------------------------

    async def create_guardian(self, school_id: UUID, data: schemas.GuardianCreate) -> Guardian:
        guardian = Guardian(
            school_id=school_id,
            name=data.name,
            phone=data.phone,
            email=data.email,
            address=data.address,
        )
        return await self._repo.create_guardian(guardian)

    async def link_guardian(
        self, school_id: UUID, student_id: UUID, data: schemas.GuardianLinkRequest
    ) -> None:
        student = await self.get_student(school_id, student_id)
        guardian = await self._repo.get_guardian(school_id, data.guardian_id)
        if guardian is None:
            raise ProblemError(NOT_FOUND, "Guardian not found", status=404)
        await self._repo.link_student_guardian(
            StudentGuardian(
                student_id=student.id,
                guardian_id=guardian.id,
                school_id=school_id,
                relationship=data.relationship,
                is_primary=data.is_primary,
            )
        )

    async def mark_graduated(self, school_id: UUID, student_id: UUID) -> None:
        """Called by academic's promotion run (service→service, same session)."""
        student = await self.get_student(school_id, student_id)
        student.status = "graduated"
        await self._repo.update_student(student)

    async def list_guardians(self, student_id: UUID) -> list[Guardian]:
        return await self._repo.list_guardians_for_student(student_id)
