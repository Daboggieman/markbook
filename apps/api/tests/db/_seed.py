"""Seeding helpers for the Phase 2 DB tests (tests/db/).

ORM inserts on the testcontainer connection — that connection is the table
owner/superuser, so RLS is not in play here (RLS tests live in
tests/security/). Objects are returned with attributes intact because the
session factory uses expire_on_commit=False (tests/conftest.py).
"""

from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.academic.models import (
    AcademicSession,
    Class,
    ClassSubject,
    EducationalLevel,
    Enrolment,
    Subject,
    SubjectEnrolment,
)
from app.people.models import Student
from app.platform.models import School


async def seed_school(maker: async_sessionmaker, school_id: UUID | None = None) -> UUID:
    school_id = school_id or uuid4()
    async with maker() as s:
        s.add(School(id=school_id, name=f"Seed {school_id.hex[:8]}"))
        await s.commit()
    return school_id


async def seed_structure(maker: async_sessionmaker, school_id: UUID) -> dict[str, UUID]:
    """Two sessions (2025/2026 current, 2026/2027 next), a JSS level with
    JSS 1 and JSS 2, Mathematics offered by both classes."""
    async with maker() as s:
        level = EducationalLevel(school_id=school_id, name="JSS", ordinal=2)
        s.add(level)
        await s.flush()
        jss1 = Class(school_id=school_id, level_id=level.id, name="JSS 1", ordinal=1)
        jss2 = Class(school_id=school_id, level_id=level.id, name="JSS 2", ordinal=2)
        s.add_all([jss1, jss2])
        await s.flush()
        maths = Subject(school_id=school_id, name="Mathematics", code="MTH")
        s.add(maths)
        await s.flush()
        s.add_all(
            [
                ClassSubject(school_id=school_id, class_id=jss1.id, subject_id=maths.id),
                ClassSubject(school_id=school_id, class_id=jss2.id, subject_id=maths.id),
            ]
        )
        from_session = AcademicSession(school_id=school_id, name="2025/2026", is_current=True)
        to_session = AcademicSession(school_id=school_id, name="2026/2027")
        s.add_all([from_session, to_session])
        await s.commit()
        return {
            "level_id": level.id,
            "jss1_id": jss1.id,
            "jss2_id": jss2.id,
            "subject_id": maths.id,
            "from_session_id": from_session.id,
            "to_session_id": to_session.id,
        }


async def seed_student(
    maker: async_sessionmaker,
    school_id: UUID,
    first_name: str = "Adaeze",
    last_name: str = "Okafor",
) -> Student:
    async with maker() as s:
        student = Student(
            school_id=school_id,
            first_name=first_name,
            last_name=last_name,
            admission_no=f"ADM-{uuid4().hex[:8]}",
        )
        s.add(student)
        await s.commit()
        return student


async def seed_enrolment(
    maker: async_sessionmaker,
    school_id: UUID,
    student_id: UUID,
    session_id: UUID,
    class_id: UUID,
) -> Enrolment:
    """Live enrolment plus one subject_enrolment per class subject."""
    async with maker() as s:
        enrolment = Enrolment(
            school_id=school_id,
            student_id=student_id,
            session_id=session_id,
            class_id=class_id,
            status="enrolled",
        )
        s.add(enrolment)
        await s.flush()
        class_subjects = (
            await s.execute(select(ClassSubject).where(ClassSubject.class_id == class_id))
        ).scalars().all()
        for cs in class_subjects:
            s.add(
                SubjectEnrolment(
                    school_id=school_id,
                    enrolment_id=enrolment.id,
                    class_subject_id=cs.id,
                )
            )
        await s.commit()
        return enrolment


async def seed_teacher_user(
    maker: async_sessionmaker, school_id: UUID, user_id: UUID | None = None
) -> UUID:
    user_id = user_id or uuid4()
    async with maker() as s:
        await s.execute(
            text(
                "INSERT INTO users (id, school_id, email, username, password_hash, "
                "is_super_admin, status, token_version, failed_login_count) "
                "VALUES (:id, :school, :email, :username, 'x', false, 'active', 1, 0)"
            ),
            {
                "id": str(user_id),
                "school": str(school_id),
                "email": f"{user_id.hex[:8]}@teacher.local",
                "username": f"t{user_id.hex[:8]}",
            },
        )
        await s.commit()
    return user_id
