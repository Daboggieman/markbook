"""Phase 3 DB tests — the CHECK constraint and uniqueness (spec §6.4).

The zero-vs-missing invariant is a Phase 3 EXIT criterion: the DB CHECK —
not only the application validator — must block ('entered', NULL) and any
non-entered status carrying a value. A genuine zero (('entered', 0.00)) must
still go through. Runs on the testcontainer Postgres via the owner
connection, so RLS is not in play here (RLS tests live in tests/security/).

Raw SQL inserts, not the ORM: the point is what the DATABASE accepts, not
what the application sends.
"""

# ruff: noqa: S608  — fixed literal SQL against the testcontainer owner.

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.db


@pytest.fixture
async def maker(migrated_url: str):
    engine = create_async_engine(migrated_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def ids(maker: async_sessionmaker) -> dict[str, UUID]:
    """The full FK chain down to one subject enrolment, ready for scores:
    school → level/class/subject/class_subject → session/term → template/
    version (active) → assessment → student → enrolment → subject_enrolment."""
    school = uuid4()
    level, klass, subject = uuid4(), uuid4(), uuid4()
    class_subject, session_, term = uuid4(), uuid4(), uuid4()
    template, version, assessment = uuid4(), uuid4(), uuid4()
    student, enrolment, subject_enrolment = uuid4(), uuid4(), uuid4()
    async with maker() as s:
        for stmt, params in [
            ("INSERT INTO schools (id, name) VALUES (:id, 'Phase 3 DB')", {"id": school}),
            (
                "INSERT INTO educational_levels (id, school_id, name, ordinal) "
                "VALUES (:id, :s, 'JSS', 2)",
                {"id": level, "s": school},
            ),
            (
                "INSERT INTO classes (id, school_id, level_id, name, ordinal) "
                "VALUES (:id, :s, :l, 'JSS 1', 1)",
                {"id": klass, "s": school, "l": level},
            ),
            (
                "INSERT INTO subjects (id, school_id, name, code) "
                "VALUES (:id, :s, 'Mathematics', 'MTH')",
                {"id": subject, "s": school},
            ),
            (
                "INSERT INTO class_subjects (id, school_id, class_id, subject_id) "
                "VALUES (:id, :s, :c, :sub)",
                {"id": class_subject, "s": school, "c": klass, "sub": subject},
            ),
            (
                "INSERT INTO academic_sessions (id, school_id, name, is_current) "
                "VALUES (:id, :s, '2025/2026', true)",
                {"id": session_, "s": school},
            ),
            (
                "INSERT INTO terms (id, school_id, session_id, name, ordinal) "
                "VALUES (:id, :s, :a, 'First Term', 1)",
                {"id": term, "s": school, "a": session_},
            ),
            (
                "INSERT INTO assessment_templates (id, school_id, name) "
                "VALUES (:id, :s, 'Default template')",
                {"id": template, "s": school},
            ),
            (
                "INSERT INTO assessment_template_versions "
                "(id, school_id, template_id, version_no, status, definition) "
                "VALUES (:id, :s, :t, 1, 'active', :def)",
                {
                    "id": version,
                    "s": school,
                    "t": template,
                    "def": (
                        '{"components": [{"key": "CA1", "label": "First CA", '
                        '"max_score": "10.00", "weight": "10", "required": true}]}'
                    ),
                },
            ),
            (
                "INSERT INTO assessments (id, school_id, term_id, class_id, section_id, "
                "subject_id, template_version_id) "
                "VALUES (:id, :s, :t, :c, NULL, :sub, :v)",
                {
                    "id": assessment,
                    "s": school,
                    "t": term,
                    "c": klass,
                    "sub": subject,
                    "v": version,
                },
            ),
            (
                "INSERT INTO students (id, school_id, first_name, last_name, admission_no, "
                "status) VALUES (:id, :s, 'Adaeze', 'Okafor', 'ADM-0001', 'active')",
                {"id": student, "s": school},
            ),
            (
                "INSERT INTO enrolments (id, school_id, student_id, session_id, class_id, "
                "status) VALUES (:id, :s, :st, :a, :c, 'enrolled')",
                {"id": enrolment, "s": school, "st": student, "a": session_, "c": klass},
            ),
            (
                "INSERT INTO subject_enrolments (id, school_id, enrolment_id, class_subject_id) "
                "VALUES (:id, :s, :e, :cs)",
                {"id": subject_enrolment, "s": school, "e": enrolment, "cs": class_subject},
            ),
        ]:
            await s.execute(text(stmt), params)
        await s.commit()
    return {
        "school": school,
        "assessment": assessment,
        "subject_enrolment": subject_enrolment,
        "template": template,
        "term": term,
        "class": klass,
        "subject": subject,
    }


async def _insert_score(
    maker: async_sessionmaker,
    ids: dict[str, UUID],
    *,
    status: str,
    value: str | None,
) -> None:
    async with maker() as s:
        await s.execute(
            text(
                "INSERT INTO scores (id, school_id, assessment_id, subject_enrolment_id, "
                "component_key, status, value) "
                "VALUES (:id, :s, :a, :se, 'CA1', :status, :value)"
            ),
            {
                "id": uuid4(),
                "s": ids["school"],
                "a": ids["assessment"],
                "se": ids["subject_enrolment"],
                "status": status,
                "value": value,
            },
        )
        await s.commit()


class TestCheckConstraint:
    """The Phase 3 exit criterion, at the DB layer."""

    async def test_entered_without_value_blocked(self, maker, ids) -> None:
        with pytest.raises(IntegrityError, match="chk_scores_entered_value"):
            await _insert_score(maker, ids, status="entered", value=None)

    async def test_missing_with_value_blocked(self, maker, ids) -> None:
        with pytest.raises(IntegrityError, match="chk_scores_entered_value"):
            await _insert_score(maker, ids, status="missing", value="5.00")

    async def test_absent_with_value_blocked(self, maker, ids) -> None:
        with pytest.raises(IntegrityError, match="chk_scores_entered_value"):
            await _insert_score(maker, ids, status="absent", value="0.01")

    async def test_exempt_with_value_blocked(self, maker, ids) -> None:
        with pytest.raises(IntegrityError, match="chk_scores_entered_value"):
            await _insert_score(maker, ids, status="exempt", value="1.00")

    async def test_zero_is_a_real_score(self, maker, ids) -> None:
        """('entered', 0.00) must go THROUGH — zero is distinct from missing."""
        await _insert_score(maker, ids, status="entered", value="0.00")

    async def test_non_entered_null_passes(self, maker, ids) -> None:
        for status in ("absent", "exempt", "missing"):
            await _insert_score(maker, ids, status=status, value=None)


class TestUniqueness:
    async def test_score_cell_unique(self, maker, ids) -> None:
        await _insert_score(maker, ids, status="entered", value="7.00")
        with pytest.raises(IntegrityError):
            await _insert_score(maker, ids, status="entered", value="8.00")

    async def test_assessment_natural_key_nulls_not_distinct(self, maker, ids) -> None:
        """PG15+ `UNIQUE NULLS NOT DISTINCT`: two section-less assessments for
        the same (school, term, class, subject) collide even with NULL."""
        with pytest.raises(IntegrityError):
            async with maker() as s:
                await s.execute(
                    text(
                        "INSERT INTO assessments (id, school_id, term_id, class_id, "
                        "section_id, subject_id, template_version_id) "
                        "VALUES (:id, :s, :t, :c, NULL, :sub, :v)"
                    ),
                    {
                        "id": uuid4(),
                        "s": ids["school"],
                        "t": ids["term"],
                        "c": ids["class"],
                        "sub": ids["subject"],
                        "v": ids["version"],
                    },
                )
                await s.commit()

    async def test_assessment_different_sections_both_allowed(self, maker, ids) -> None:
        """NULL section vs an explicit section are distinct rows."""
        for section in (uuid4(), None):
            async with maker() as s:
                await s.execute(
                    text(
                        "INSERT INTO assessments (id, school_id, term_id, class_id, "
                        "section_id, subject_id, template_version_id) "
                        "VALUES (:id, :s, :t, :c, :sec, :sub, :v)"
                    ),
                    {
                        "id": uuid4(),
                        "s": ids["school"],
                        "t": ids["term"],
                        "c": ids["class"],
                        "sec": section,
                        "sub": ids["subject"],
                        "v": ids["version"],
                    },
                )
                await s.commit()

    async def test_template_version_no_unique(self, maker, ids) -> None:
        async with maker() as s:
            await s.execute(
                text(
                    "INSERT INTO assessment_template_versions "
                    "(id, school_id, template_id, version_no, status, definition) "
                    "VALUES (:id, :s, :t, 1, 'draft', :def)"
                ),
                {
                    "id": uuid4(),
                    "s": ids["school"],
                    "t": ids["template"],
                    "def": '{"components": []}',
                },
            )
            await s.commit()
        with pytest.raises(IntegrityError):
            async with maker() as s:
                await s.execute(
                    text(
                        "INSERT INTO assessment_template_versions "
                        "(id, school_id, template_id, version_no, status, definition) "
                        "VALUES (:id, :s, :t, 1, 'draft', :def)"
                    ),
                    {
                        "id": uuid4(),
                        "s": ids["school"],
                        "t": ids["template"],
                        "def": '{"components": []}',
                    },
                )
                await s.commit()
