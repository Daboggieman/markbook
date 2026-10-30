"""Phase 2 people tests — archive invariant, duplicate detection, scoped lists.

Runs against real Postgres via testcontainers (`db` marker); the connection
is the table owner/superuser, so RLS is not exercised here (tests/security/).
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.academic.models import Enrolment, Section, SubjectEnrolment, TeacherAssignment
from app.people.schemas import DuplicateCheckRequest, StudentCreate
from app.people.service import PeopleService
from app.platform.errors import POSSIBLE_DUPLICATE, ProblemError
from tests.db import _seed

pytestmark = pytest.mark.db


@pytest.fixture
async def maker(migrated_url: str):
    engine = create_async_engine(migrated_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_archive_preserves_history(maker: async_sessionmaker) -> None:
    """Archiving stamps the student; enrolments and subject_enrolments are
    untouched (spec §6 — the history invariant)."""
    school = await _seed.seed_school(maker)
    ids = await _seed.seed_structure(maker, school)
    student = await _seed.seed_student(maker, school)
    enrolment = await _seed.seed_enrolment(
        maker, school, student.id, ids["from_session_id"], ids["jss1_id"]
    )

    async with maker() as session:
        svc = PeopleService(session)
        archived = await svc.archive_student(school, student.id, version=1)
        await session.commit()

    assert archived.status == "archived"
    assert archived.archived_at is not None

    async with maker() as s:
        enrol = (
            await s.execute(select(Enrolment).where(Enrolment.id == enrolment.id))
        ).scalar_one()
        assert enrol.status == "enrolled", "archive must not touch enrolments"
        assert enrol.class_id == ids["jss1_id"]
        subject_rows = (
            await s.execute(
                select(SubjectEnrolment).where(SubjectEnrolment.enrolment_id == enrolment.id)
            )
        ).scalars().all()
        assert len(subject_rows) == 1, "subject enrolments survive the archive"


async def test_create_blocks_near_duplicate(maker: async_sessionmaker) -> None:
    school = await _seed.seed_school(maker)
    async with maker() as session:
        svc = PeopleService(session)
        await svc.create_student(
            school,
            _create_request(first_name="Chiamaka", last_name="Okonkwo"),
        )
        await session.commit()

    async with maker() as session:
        svc = PeopleService(session)
        with pytest.raises(ProblemError) as exc_info:
            await svc.create_student(
                school, _create_request(first_name="Chiamaka", last_name="Okonkwo")
            )
        assert exc_info.value.code == POSSIBLE_DUPLICATE
        assert exc_info.value.extra["candidates"], "candidates must accompany the 409"


async def test_create_allows_identical_with_force(maker: async_sessionmaker) -> None:
    school = await _seed.seed_school(maker)
    async with maker() as session:
        svc = PeopleService(session)
        await svc.create_student(
            school, _create_request(first_name="Chiamaka", last_name="Okonkwo")
        )
        second = await svc.create_student(
            school,
            _create_request(first_name="Chiamaka", last_name="Okonkwo", allow_duplicate=True),
        )
        await session.commit()
    assert second.id is not None


async def test_check_duplicates_reports_similar_names(maker: async_sessionmaker) -> None:
    school = await _seed.seed_school(maker)
    async with maker() as session:
        svc = PeopleService(session)
        await svc.create_student(
            school, _create_request(first_name="Adaeze", last_name="Okafor")
        )
        await session.commit()

    async with maker() as session:
        svc = PeopleService(session)
        report = await svc.check_duplicates(
            school,
            _dup_request(first_name="Adaeze", last_name="Okafra"),  # typo'd query
        )
        assert len(report.candidates) == 1
        assert report.candidates[0].similarity > 0.6


async def test_scoped_list_respects_teacher_assignments(
    maker: async_sessionmaker,
) -> None:
    """The assigned scope (spec §7.2): a teacher only sees students in the
    classes they are assigned to; school scope sees everything."""
    school = await _seed.seed_school(maker)
    ids = await _seed.seed_structure(maker, school)
    teacher = await _seed.seed_teacher_user(maker, school)
    s1 = await _seed.seed_student(maker, school, first_name="Ada", last_name="Bello")
    s2 = await _seed.seed_student(maker, school, first_name="Emeka", last_name="Bello")
    outsider = await _seed.seed_student(maker, school, first_name="Zuri", last_name="Abbas")
    for sid in (s1.id, s2.id):
        await _seed.seed_enrolment(maker, school, sid, ids["from_session_id"], ids["jss1_id"])
    await _seed.seed_enrolment(
        maker, school, outsider.id, ids["from_session_id"], ids["jss2_id"]
    )

    async with maker() as session:
        session.add(
            TeacherAssignment(
                school_id=school,
                teacher_user_id=teacher,
                session_id=ids["from_session_id"],
                class_id=ids["jss1_id"],
                role="form",
            )
        )
        await session.commit()

    async with maker() as session:
        svc = PeopleService(session)
        assigned = await svc.list_students(
            scope="assigned",
            school_id=school,
            teacher_user_id=teacher,
            session_id=ids["from_session_id"],
        )
        assert {s.id for s in assigned} == {s1.id, s2.id}, "only the assigned class"

        everyone = await svc.list_students(
            scope="school",
            school_id=school,
            session_id=ids["from_session_id"],
        )
        assert {s.id for s in everyone} == {s1.id, s2.id, outsider.id}

        own_scope = await svc.list_students(
            scope="own", school_id=school, teacher_user_id=teacher
        )
        assert own_scope == []


async def test_assignment_section_narrowing(maker: async_sessionmaker) -> None:
    """A NULL section on the assignment covers the whole class; a set section
    covers only that section."""
    school = await _seed.seed_school(maker)
    ids = await _seed.seed_structure(maker, school)
    teacher = await _seed.seed_teacher_user(maker, school)
    s1 = await _seed.seed_student(maker, school, first_name="Ada", last_name="Bello")
    s2 = await _seed.seed_student(maker, school, first_name="Emeka", last_name="Bello")
    await _seed.seed_enrolment(maker, school, s1.id, ids["from_session_id"], ids["jss1_id"])
    await _seed.seed_enrolment(maker, school, s2.id, ids["from_session_id"], ids["jss1_id"])

    async with maker() as session:
        section_a = Section(school_id=school, class_id=ids["jss1_id"], name="A")
        session.add(section_a)
        await session.flush()
        # s1 in section A, s2 sectionless
        enrol_s1 = (
            await session.execute(
                select(Enrolment).where(
                    Enrolment.student_id == s1.id,
                    Enrolment.session_id == ids["from_session_id"],
                )
            )
        ).scalar_one()
        enrol_s1.section_id = section_a.id
        session.add(
            TeacherAssignment(
                school_id=school,
                teacher_user_id=teacher,
                session_id=ids["from_session_id"],
                class_id=ids["jss1_id"],
                section_id=section_a.id,
                role="form",
            )
        )
        await session.commit()

    async with maker() as session:
        svc = PeopleService(session)
        assigned = await svc.list_students(
            scope="assigned",
            school_id=school,
            teacher_user_id=teacher,
            session_id=ids["from_session_id"],
        )
        assert {s.id for s in assigned} == {s1.id}


def _create_request(
    first_name: str, last_name: str, allow_duplicate: bool = False
) -> StudentCreate:
    return StudentCreate(
        first_name=first_name,
        last_name=last_name,
        allow_duplicate=allow_duplicate,
    )


def _dup_request(first_name: str, last_name: str) -> DuplicateCheckRequest:
    return DuplicateCheckRequest(first_name=first_name, last_name=last_name)
