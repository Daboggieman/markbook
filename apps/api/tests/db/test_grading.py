"""Phase 4 DB tests — grading tables' constraints (spec §6.5).

The DB-layer invariants the service relies on: scheme version uniqueness,
processed-result uniqueness per (run, enrolment), the run→results CASCADE,
and the nullable-total shape for excluded-everything students. Runs on the
testcontainer owner connection, so RLS is not in play here (tests/security/).

Raw SQL inserts, not the ORM: the point is what the DATABASE accepts.
"""

# ruff: noqa: S608  — fixed literal SQL against the testcontainer owner.

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.db


@pytest.fixture
async def maker(migrated_url: str):
    engine = create_async_engine(migrated_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def ids(maker: async_sessionmaker) -> dict[str, UUID]:
    """The full FK chain plus one scheme, run, and processed result."""
    school = uuid4()
    level, klass, subject = uuid4(), uuid4(), uuid4()
    class_subject, session_, term = uuid4(), uuid4(), uuid4()
    template, version, assessment = uuid4(), uuid4(), uuid4()
    student, enrolment, subject_enrolment = uuid4(), uuid4(), uuid4()
    scheme, run, result = uuid4(), uuid4(), uuid4()
    definition = (
        '{"rounding_mode": "ROUND_HALF_UP", "precision": 0, '
        '"missing_policy": "flag_incomplete", "absent_policy": "treat_zero", '
        '"exempt_policy": "exclude_and_renormalise", '
        '"boundaries": [{"grade": "A", "min": 0, "max": 100}], "tie_policy": "dense"}'
    )
    async with maker() as s:
        for stmt, params in [
            ("INSERT INTO schools (id, name) VALUES (:id, 'Phase 4 DB')", {"id": school}),
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
                "INSERT INTO subjects (id, school_id, name) VALUES (:id, :s, 'Mathematics')",
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
            (
                "INSERT INTO grading_schemes (id, school_id, name, version_no, status, "
                "definition) VALUES (:id, :s, 'WAEC standard', 1, 'active', :def)",
                {"id": scheme, "s": school, "def": definition},
            ),
            (
                "INSERT INTO result_processing_runs (id, school_id, assessment_id, scheme_id, "
                "scheme_version, template_version_id, status) "
                "VALUES (:id, :s, :a, :sch, 1, :v, 'succeeded')",
                {"id": run, "s": school, "a": assessment, "sch": scheme, "v": version},
            ),
            (
                "INSERT INTO processed_results (id, school_id, run_id, subject_enrolment_id, "
                "total, grade, position, breakdown, flags) "
                "VALUES (:id, :s, :r, :se, 78.00, 'A', 1, CAST(:bd AS jsonb), CAST(:fl AS jsonb))",
                {
                    "id": result,
                    "s": school,
                    "r": run,
                    "se": subject_enrolment,
                    "bd": json.dumps(
                        [
                            {
                                "component_key": "CA1",
                                "status": "entered",
                                "value": "8",
                                "contribution": "8",
                                "excluded": False,
                            }
                        ]
                    ),
                    "fl": "[]",
                },
            ),
        ]:
            await s.execute(text(stmt), params)
        await s.commit()
    return {
        "school": school,
        "assessment": assessment,
        "subject_enrolment": subject_enrolment,
        "template": template,
        "version": version,
        "scheme": scheme,
        "run": run,
        "result": result,
    }


class TestSchemeConstraints:
    async def test_scheme_version_unique(self, maker, ids) -> None:
        """(school, name, version_no) is UNIQUE — v1 exists; a second v1 collides."""
        with pytest.raises(IntegrityError):
            async with maker() as s:
                await s.execute(
                    text(
                        "INSERT INTO grading_schemes (id, school_id, name, version_no, "
                        "status, definition) VALUES (:id, :s, 'WAEC standard', 1, 'draft', :def)"
                    ),
                    {"id": uuid4(), "s": ids["school"], "def": "{}"},
                )
                await s.commit()

    async def test_same_version_no_under_other_name_allowed(self, maker, ids) -> None:
        async with maker() as s:
            await s.execute(
                text(
                    "INSERT INTO grading_schemes (id, school_id, name, version_no, "
                    "status, definition) VALUES (:id, :s, 'Other scheme', 1, 'draft', :def)"
                ),
                {"id": uuid4(), "s": ids["school"], "def": "{}"},
            )
            await s.commit()

    async def test_run_status_enum_blocks_junk(self, maker, ids) -> None:
        """'cancelled' is not a runstatus label — a native-enum violation is a
        DataError (SQLSTATE 22P02), not an integrity violation."""
        with pytest.raises(DataError):
            async with maker() as s:
                await s.execute(
                    text(
                        "INSERT INTO result_processing_runs (id, school_id, assessment_id, "
                        "scheme_id, scheme_version, template_version_id, status) "
                        "VALUES (:id, :s, :a, :sch, 1, :v, 'cancelled')"
                    ),
                    {
                        "id": uuid4(),
                        "s": ids["school"],
                        "a": ids["assessment"],
                        "sch": ids["scheme"],
                        "v": ids["version"],
                    },
                )
                await s.commit()


class TestRunAndResults:
    async def test_result_unique_per_run_and_enrolment(self, maker, ids) -> None:
        with pytest.raises(IntegrityError):
            async with maker() as s:
                await s.execute(
                    text(
                        "INSERT INTO processed_results (id, school_id, run_id, "
                        "subject_enrolment_id, total, grade, position, breakdown, flags) "
                        "VALUES (:id, :s, :r, :se, 70.00, 'A', 2, '[]'::jsonb, '[]'::jsonb)"
                    ),
                    {
                        "id": uuid4(),
                        "s": ids["school"],
                        "r": ids["run"],
                        "se": ids["subject_enrolment"],
                    },
                )
                await s.commit()

    async def test_deleting_run_cascades_results(self, maker, ids) -> None:
        async with maker() as s:
            await s.execute(
                text("DELETE FROM result_processing_runs WHERE id = :r"), {"r": ids["run"]}
            )
            await s.commit()
            count = (
                await s.execute(
                    text("SELECT count(*) FROM processed_results WHERE run_id = :r"),
                    {"r": ids["run"]},
                )
            ).scalar_one()
        assert count == 0

    async def test_null_total_row_is_storable(self, maker, ids) -> None:
        """A no-scoreable-components student stores NULL total/grade/position
        (the run still reports them — spec §9.2 step 8's flags carry the why)."""
        async with maker() as s:
            # The fixture's own result occupies (run, subject_enrolment); this
            # row models a DIFFERENT student's outcome in the same run.
            await s.execute(
                text("DELETE FROM processed_results WHERE run_id = :r"), {"r": ids["run"]}
            )
            await s.execute(
                text(
                    "INSERT INTO processed_results (id, school_id, run_id, "
                    "subject_enrolment_id, total, grade, position, breakdown, flags) "
                    "VALUES (:id, :s, :r, :se, NULL, NULL, NULL, '[]'::jsonb, "
                    "'[\"no_scoreable_components\"]'::jsonb)"
                ),
                {
                    "id": uuid4(),
                    "s": ids["school"],
                    "r": ids["run"],
                    "se": ids["subject_enrolment"],
                },
            )
            await s.commit()

    async def test_run_error_column_round_trips(self, maker, ids) -> None:
        """The documented deviation: a failed run records WHY in `error`."""
        async with maker() as s:
            await s.execute(
                text(
                    "UPDATE result_processing_runs SET status = 'failed', "
                    "error = 'missing_policy=block: 2 student(s)' WHERE id = :r"
                ),
                {"r": ids["run"]},
            )
            await s.commit()
            row = (
                await s.execute(
                    text("SELECT status, error FROM result_processing_runs WHERE id = :r"),
                    {"r": ids["run"]},
                )
            ).one()
        assert row.status == "failed"
        assert "block" in row.error
