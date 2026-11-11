"""Academic service — structure, enrolment and promotion logic (Phase 2).

Promotion is the historical-context invariant made real (spec §6.3): each
decision runs in a savepoint, ends the from-session enrolment by stamping
status/ended_on, creates a NEW enrolment in the to-session, and links the two
in promotion_records. Nothing on the old enrolment changes except that stamp,
so results (Phase 4) that reference `enrolment_id` keep their context forever.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.academic import schemas
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
from app.academic.repository import AcademicRepository
from app.people.models import Student  # documented academic → people read edge
from app.people.service import PeopleService
from app.platform.errors import (
    CONFLICT,
    INVALID_STATE_TRANSITION,
    NOT_FOUND,
    ProblemError,
)


class AcademicService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = AcademicRepository(session)

    async def _one_or_404(self, model, *, school_id: UUID, id_: UUID, label: str):
        row = await self._s.scalar(
            select(model).where(model.school_id == school_id, model.id == id_)
        )
        if row is None:
            raise ProblemError(NOT_FOUND, f"{label} not found", status=404)
        return row

    # ---- sessions & terms ---------------------------------------------------

    async def create_session(
        self, school_id: UUID, data: schemas.AcademicSessionCreate
    ) -> AcademicSession:
        session_row = AcademicSession(
            school_id=school_id,
            name=data.name,
            start_date=data.start_date,
            end_date=data.end_date,
            is_current=data.is_current,
        )
        try:
            session_row = await self._repo.create_session(session_row)
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "A session with that name already exists") from exc
        if data.is_current:
            await self._repo.clear_current_session(school_id, session_row.id)
        return session_row

    async def list_sessions(self, school_id: UUID) -> list[AcademicSession]:
        return await self._repo.list_sessions(school_id)

    async def get_session(self, school_id: UUID, session_id: UUID) -> AcademicSession:
        return await self._one_or_404(
            AcademicSession, school_id=school_id, id_=session_id, label="Session"
        )

    async def create_term(self, school_id: UUID, data: schemas.TermCreate) -> Term:
        await self.get_session(school_id, data.session_id)
        term = Term(
            school_id=school_id,
            session_id=data.session_id,
            name=data.name,
            ordinal=data.ordinal,
            start_date=data.start_date,
            end_date=data.end_date,
            is_current=data.is_current,
        )
        try:
            return await self._repo.create_term(term)
        except IntegrityError as exc:
            raise ProblemError(
                CONFLICT, "A term with that name already exists in the session"
            ) from exc

    async def list_terms(self, school_id: UUID, session_id: UUID) -> list[Term]:
        return await self._repo.list_terms(school_id, session_id)

    # ---- levels / classes / sections / subjects --------------------------------

    async def list_levels(self, school_id: UUID) -> list[EducationalLevel]:
        return await self._repo.list_levels(school_id)

    async def create_class(self, school_id: UUID, data: schemas.ClassCreate) -> Class:
        await self._one_or_404(
            EducationalLevel, school_id=school_id, id_=data.level_id, label="Educational level"
        )
        klass = Class(
            school_id=school_id, level_id=data.level_id, name=data.name, ordinal=data.ordinal
        )
        try:
            return await self._repo.create_class(klass)
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "A class with that name already exists") from exc

    async def list_classes(self, school_id: UUID, level_id: UUID | None = None) -> list[Class]:
        return await self._repo.list_classes(school_id, level_id)

    async def get_class(self, school_id: UUID, class_id: UUID) -> Class:
        return await self._one_or_404(Class, school_id=school_id, id_=class_id, label="Class")

    async def create_section(self, school_id: UUID, data: schemas.SectionCreate) -> Section:
        await self.get_class(school_id, data.class_id)
        section = Section(school_id=school_id, class_id=data.class_id, name=data.name)
        try:
            return await self._repo.create_section(section)
        except IntegrityError as exc:
            raise ProblemError(
                CONFLICT, "A section with that name already exists in the class"
            ) from exc

    async def list_sections(self, school_id: UUID, class_id: UUID) -> list[Section]:
        return await self._repo.list_sections(school_id, class_id)

    async def create_subject(self, school_id: UUID, data: schemas.SubjectCreate) -> Subject:
        subject = Subject(school_id=school_id, name=data.name, code=data.code)
        try:
            return await self._repo.create_subject(subject)
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "A subject with that name or code already exists") from exc

    async def list_subjects(self, school_id: UUID) -> list[Subject]:
        return await self._repo.list_subjects(school_id)

    async def list_class_subjects(self, class_id: UUID) -> list[ClassSubject]:
        return await self._repo.list_class_subjects(class_id)

    async def create_class_subject(
        self, school_id: UUID, data: schemas.ClassSubjectCreate
    ) -> ClassSubject:
        await self.get_class(school_id, data.class_id)
        await self._one_or_404(Subject, school_id=school_id, id_=data.subject_id, label="Subject")
        class_subject = ClassSubject(
            school_id=school_id,
            class_id=data.class_id,
            subject_id=data.subject_id,
            is_optional=data.is_optional,
        )
        try:
            return await self._repo.create_class_subject(class_subject)
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "That subject is already offered by the class") from exc

    # ---- enrolments ---------------------------------------------------------------

    async def enrol_student(self, school_id: UUID, data: schemas.EnrolmentCreate) -> Enrolment:
        await self.get_session(school_id, data.session_id)
        await self.get_class(school_id, data.class_id)
        student = await self._s.scalar(
            select(Student).where(Student.school_id == school_id, Student.id == data.student_id)
        )
        if student is None:
            raise ProblemError(NOT_FOUND, "Student not found", status=404)
        if data.section_id is not None:
            section = await self._s.scalar(
                select(Section).where(
                    Section.school_id == school_id,
                    Section.id == data.section_id,
                    Section.class_id == data.class_id,
                )
            )
            if section is None:
                raise ProblemError(NOT_FOUND, "Section not found in that class", status=404)
        existing = await self._repo.get_live_enrolment(data.student_id, data.session_id)
        if existing is not None:
            raise ProblemError(CONFLICT, "Student already has a live enrolment in this session")
        try:
            return await self._create_enrolment_with_subjects(
                school_id,
                student_id=data.student_id,
                session_id=data.session_id,
                class_id=data.class_id,
                section_id=data.section_id,
            )
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "Enrolment references inconsistent records") from exc

    async def _create_enrolment_with_subjects(
        self,
        school_id: UUID,
        *,
        student_id: UUID,
        session_id: UUID,
        class_id: UUID,
        section_id: UUID | None,
    ) -> Enrolment:
        enrolment = Enrolment(
            school_id=school_id,
            student_id=student_id,
            session_id=session_id,
            class_id=class_id,
            section_id=section_id,
            status="enrolled",
            started_on=datetime.now(UTC).date(),
        )
        await self._repo.create_enrolment(enrolment)
        class_subjects = await self._repo.list_class_subjects(class_id)
        await self._repo.create_subject_enrolments(
            [
                SubjectEnrolment(
                    school_id=school_id,
                    enrolment_id=enrolment.id,
                    class_subject_id=cs.id,
                )
                for cs in class_subjects
            ]
        )
        return enrolment

    # ---- teacher assignments ---------------------------------------------------------

    async def create_teacher_assignment(
        self, school_id: UUID, data: schemas.TeacherAssignmentCreate
    ) -> TeacherAssignment:
        await self.get_session(school_id, data.session_id)
        await self.get_class(school_id, data.class_id)
        assignment = TeacherAssignment(
            school_id=school_id,
            teacher_user_id=data.teacher_user_id,
            session_id=data.session_id,
            class_id=data.class_id,
            section_id=data.section_id,
            subject_id=data.subject_id,
            role=data.role,
        )
        try:
            return await self._repo.create_teacher_assignment(assignment)
        except IntegrityError as exc:
            raise ProblemError(CONFLICT, "Assignment references a missing teacher user") from exc

    async def list_teacher_assignments(
        self, school_id: UUID, teacher_user_id: UUID, session_id: UUID
    ) -> list[TeacherAssignment]:
        return await self._repo.list_teacher_assignments(school_id, teacher_user_id, session_id)

    # ---- promotions ----------------------------------------------------------------------

    async def run_promotion(
        self, school_id: UUID, data: schemas.PromotionRunRequest, decided_by: UUID
    ) -> schemas.PromotionRunResponse:
        if data.from_session_id == data.to_session_id:
            raise ProblemError(INVALID_STATE_TRANSITION, "from and to sessions must differ")
        await self.get_session(school_id, data.from_session_id)
        await self.get_session(school_id, data.to_session_id)

        # Promotion order for auto-advance: level ordinal, then class ordinal.
        sequence = await self._repo.list_classes(school_id)
        position = {c.id: i for i, c in enumerate(sequence)}

        student_ids = [d.student_id for d in data.decisions]
        live = await self._repo.get_live_enrolments(student_ids, data.from_session_id)

        people = PeopleService(self._s)
        today = datetime.now(UTC).date()
        outcomes: list[schemas.PromotionRunOutcome] = []

        for decision in data.decisions:
            enrolment = live.get(decision.student_id)
            if enrolment is None:
                outcomes.append(
                    schemas.PromotionRunOutcome(
                        student_id=decision.student_id,
                        decision=decision.decision,
                        from_enrolment_id=None,
                        to_enrolment_id=None,
                        to_class_id=None,
                        note="no live enrolment in from-session; skipped",
                    )
                )
                continue
            # Capture the id before the savepoint: a rollback expires the
            # enrolment object, and async SQLAlchemy cannot lazily refresh it
            # in the except handlers below.
            enrolment_id = enrolment.id
            try:
                async with self._s.begin_nested():
                    outcome = await self._apply_decision(
                        school_id,
                        decision,
                        enrolment,
                        data.to_session_id,
                        sequence,
                        position,
                        today,
                        decided_by,
                        people,
                    )
                    outcomes.append(outcome)
            except ProblemError as exc:
                outcomes.append(
                    schemas.PromotionRunOutcome(
                        student_id=decision.student_id,
                        decision=decision.decision,
                        from_enrolment_id=enrolment_id,
                        to_enrolment_id=None,
                        to_class_id=None,
                        note=exc.detail,
                    )
                )
            except IntegrityError:
                outcomes.append(
                    schemas.PromotionRunOutcome(
                        student_id=decision.student_id,
                        decision=decision.decision,
                        from_enrolment_id=enrolment_id,
                        to_enrolment_id=None,
                        to_class_id=None,
                        note="already enrolled in the target session; skipped",
                    )
                )
        return schemas.PromotionRunResponse(outcomes=outcomes)

    async def _apply_decision(
        self,
        school_id: UUID,
        decision: schemas.PromotionDecision,
        enrolment: Enrolment,
        to_session_id: UUID,
        sequence: list[Class],
        position: dict[UUID, int],
        today,
        decided_by: UUID,
        people: PeopleService,
    ) -> schemas.PromotionRunOutcome:
        if decision.decision == "graduate":
            await self._repo.end_enrolment(enrolment, status="graduated", ended_on=today)
            await people.mark_graduated(school_id, decision.student_id)
            await self._repo.add_promotion_record(
                PromotionRecord(
                    school_id=school_id,
                    student_id=decision.student_id,
                    from_enrolment_id=enrolment.id,
                    to_enrolment_id=None,
                    decision="graduate",
                    decided_by=decided_by,
                )
            )
            return schemas.PromotionRunOutcome(
                student_id=decision.student_id,
                decision="graduate",
                from_enrolment_id=enrolment.id,
                to_enrolment_id=None,
                to_class_id=None,
            )

        if decision.decision == "repeat":
            to_class_id = decision.to_class_id or enrolment.class_id
            status = "repeated"
        else:  # promote
            if decision.to_class_id is not None:
                to_class_id = decision.to_class_id
            else:
                pos = position.get(enrolment.class_id)
                if pos is None or pos + 1 >= len(sequence):
                    raise ProblemError(
                        INVALID_STATE_TRANSITION,
                        "no class follows this one; use decision=graduate",
                    )
                to_class_id = sequence[pos + 1].id
            status = "promoted"

        new_enrolment = await self._create_enrolment_with_subjects(
            school_id,
            student_id=decision.student_id,
            session_id=to_session_id,
            class_id=to_class_id,
            section_id=decision.to_section_id,
        )
        await self._repo.end_enrolment(enrolment, status=status, ended_on=today)
        await self._repo.add_promotion_record(
            PromotionRecord(
                school_id=school_id,
                student_id=decision.student_id,
                from_enrolment_id=enrolment.id,
                to_enrolment_id=new_enrolment.id,
                decision=status,
                decided_by=decided_by,
            )
        )
        return schemas.PromotionRunOutcome(
            student_id=decision.student_id,
            decision=status,
            from_enrolment_id=enrolment.id,
            to_enrolment_id=new_enrolment.id,
            to_class_id=to_class_id,
        )
