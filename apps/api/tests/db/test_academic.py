"""Phase 2 academic tests â€” promotion invariant, enrolment rules.

The promotion test is the historical-context exit criterion (spec Â§6.3):
the old enrolment keeps its row, its stamp and its subject_enrolments; the
new enrolment is a separate row in the new session.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.db import _seed

from app.academic.models import Enrolment, PromotionRecord, SubjectEnrolment
from app.academic.schemas import (
    EnrolmentCreate,
    PromotionDecision,
    PromotionRunRequest,
)
from app.academic.service import AcademicService
from app.people.models import Student
from app.platform.errors import CONFLICT, ProblemError

pytestmark = pytest.mark.db


@pytest.fixture
async def maker(migrated_url: str):
    engine = create_async_engine(migrated_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _enrolled_student(maker: async_sessionmaker) -> tuple[UUID, dict, Student]:
    """One school, structure, student, live JSS 1 enrolment with subject rows,
    plus a real user id for decided_by (promotion_records FK)."""
    school = await _seed.seed_school(maker)
    ids = await _seed.seed_structure(maker, school)
    student = await _seed.seed_student(maker, school)
    await _seed.seed_enrolment(maker, school, student.id, ids["from_session_id"], ids["jss1_id"])
    decider = await _seed.seed_teacher_user(maker, school)
    return school, ids, student, decider


def _run_request(ids: dict, *decisions: PromotionDecision) -> PromotionRunRequest:
    return PromotionRunRequest(
        from_session_id=ids["from_session_id"],
        to_session_id=ids["to_session_id"],
        decisions=list(decisions),
    )


async def test_promotion_keeps_old_results_context(maker: async_sessionmaker) -> None:
    """Old enrolment: stamped 'promoted', subject_enrolments intact. New
    enrolment: separate row in the to-session with fresh subject rows."""
    school, ids, student, decider = await _enrolled_student(maker)

    async with maker() as session:
        svc = AcademicService(session)
        result = await svc.run_promotion(
            school,
            _run_request(ids, PromotionDecision(student_id=student.id, decision="promote")),
            decided_by=decider,
        )
        await session.commit()

    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.decision == "promoted"
    assert outcome.note is None
    assert outcome.to_enrolment_id is not None
    assert outcome.to_class_id == ids["jss2_id"], "auto-advance follows the class sequence"

    async with maker() as s:
        old = (
            await s.execute(select(Enrolment).where(Enrolment.id == outcome.from_enrolment_id))
        ).scalar_one()
        assert old.status == "promoted"
        assert old.ended_on is not None
        old_subjects = (
            (
                await s.execute(
                    select(SubjectEnrolment).where(SubjectEnrolment.enrolment_id == old.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(old_subjects) == 1, "old subject enrolments are never touched"

        new = (
            await s.execute(select(Enrolment).where(Enrolment.id == outcome.to_enrolment_id))
        ).scalar_one()
        assert new.session_id == ids["to_session_id"]
        assert new.class_id == ids["jss2_id"]
        assert new.status == "enrolled"
        new_subjects = (
            (
                await s.execute(
                    select(SubjectEnrolment).where(SubjectEnrolment.enrolment_id == new.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(new_subjects) == 1, "fresh subject enrolments from the new class"

        records = (
            (
                await s.execute(
                    select(PromotionRecord).where(PromotionRecord.student_id == student.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(records) == 1
        assert records[0].from_enrolment_id == old.id
        assert records[0].to_enrolment_id == new.id


async def test_repeat_keeps_same_class(maker: async_sessionmaker) -> None:
    school, ids, student, decider = await _enrolled_student(maker)
    async with maker() as session:
        svc = AcademicService(session)
        result = await svc.run_promotion(
            school,
            _run_request(ids, PromotionDecision(student_id=student.id, decision="repeat")),
            decided_by=decider,
        )
        await session.commit()
    outcome = result.outcomes[0]
    assert outcome.decision == "repeated"
    assert outcome.to_class_id == ids["jss1_id"], "repeat stays in the same class"

    async with maker() as s:
        new = (
            await s.execute(select(Enrolment).where(Enrolment.id == outcome.to_enrolment_id))
        ).scalar_one()
        assert new.class_id == ids["jss1_id"]


async def test_graduate_closes_out_without_new_enrolment(
    maker: async_sessionmaker,
) -> None:
    school, ids, student, decider = await _enrolled_student(maker)
    async with maker() as session:
        svc = AcademicService(session)
        result = await svc.run_promotion(
            school,
            _run_request(ids, PromotionDecision(student_id=student.id, decision="graduate")),
            decided_by=decider,
        )
        await session.commit()
    outcome = result.outcomes[0]
    assert outcome.decision == "graduate"
    assert outcome.to_enrolment_id is None

    async with maker() as s:
        old = (
            await s.execute(select(Enrolment).where(Enrolment.id == outcome.from_enrolment_id))
        ).scalar_one()
        assert old.status == "graduated"
        live = (
            (
                await s.execute(
                    select(Enrolment).where(
                        Enrolment.student_id == student.id,
                        Enrolment.session_id == ids["to_session_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
        assert live == [], "graduate creates no new enrolment"
        row = (await s.execute(select(Student).where(Student.id == student.id))).scalar_one()
        assert row.status == "graduated"


async def test_promote_from_last_class_notes_no_successor(
    maker: async_sessionmaker,
) -> None:
    """Auto-advance from the final class in the sequence cannot promote; the
    outcome carries the note and the old enrolment stays live."""
    school, ids, student, decider = await _enrolled_student(maker)
    # Move the student to JSS 2 â€” the last class in the seeded sequence.
    async with maker() as s:
        enrol = (
            await s.execute(select(Enrolment).where(Enrolment.student_id == student.id))
        ).scalar_one()
        enrol.class_id = ids["jss2_id"]
        await s.commit()

    async with maker() as session:
        svc = AcademicService(session)
        result = await svc.run_promotion(
            school,
            _run_request(ids, PromotionDecision(student_id=student.id, decision="promote")),
            decided_by=decider,
        )
        await session.commit()
    outcome = result.outcomes[0]
    assert outcome.note is not None and "graduate" in outcome.note
    async with maker() as s:
        enrol = (
            await s.execute(select(Enrolment).where(Enrolment.student_id == student.id))
        ).scalar_one()
        assert enrol.status == "enrolled", "failed decision leaves the enrolment live"


async def test_skip_when_no_live_enrolment(maker: async_sessionmaker) -> None:
    school, ids, _student, _decider = await _enrolled_student(maker)
    stranger = await _seed.seed_student(maker, school, first_name="Ngozi", last_name="Eze")
    async with maker() as session:
        svc = AcademicService(session)
        result = await svc.run_promotion(
            school,
            _run_request(ids, PromotionDecision(student_id=stranger.id, decision="promote")),
            decided_by=decider,
        )
        await session.commit()
    assert result.outcomes[0].from_enrolment_id is None
    assert "no live enrolment" in (result.outcomes[0].note or "")


async def test_second_live_enrolment_conflicts(maker: async_sessionmaker) -> None:
    """ux_enrolments_student_session: one live enrolment per student per
    session (spec Â§6.3)."""
    school, ids, student, decider = await _enrolled_student(maker)
    async with maker() as session:
        svc = AcademicService(session)
        with pytest.raises(ProblemError) as exc_info:
            await svc.enrol_student(
                school,
                EnrolmentCreate(
                    student_id=student.id,
                    session_id=ids["from_session_id"],
                    class_id=ids["jss2_id"],
                ),
            )
        assert exc_info.value.code == CONFLICT


async def test_enrol_creates_subject_enrolments(maker: async_sessionmaker) -> None:
    school, ids, _student, _decider = await _enrolled_student(maker)
    newbie = await _seed.seed_student(maker, school, first_name="Obi", last_name="Nwachukwu")
    async with maker() as session:
        svc = AcademicService(session)
        enrolment = await svc.enrol_student(
            school,
            EnrolmentCreate(
                student_id=newbie.id,
                session_id=ids["from_session_id"],
                class_id=ids["jss1_id"],
            ),
        )
        await session.commit()
        subject_rows = (
            (
                await session.execute(
                    select(SubjectEnrolment).where(SubjectEnrolment.enrolment_id == enrolment.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(subject_rows) == 1
