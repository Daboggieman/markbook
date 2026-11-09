"""RLS isolation for the Phase 4 tenant tables (spec §6.5).

Same treatment as Phase 3: the three tables migration 0005 created —
grading_schemes, result_processing_runs, processed_results — checked through
the dedicated non-superuser app role, so the policies are load-bearing.
"""

# ruff: noqa: S608  — table names come from the fixed _PHASE4_TABLES tuple.

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.platform.db import set_tenant_context

pytestmark = pytest.mark.rls

_PHASE4_TABLES = (
    "grading_schemes",
    "result_processing_runs",
    "processed_results",
)


def _app_role_url(url: str) -> str:
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    netloc = f"markbook_app:markbook_app@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


@pytest.fixture
async def app_role_session_factory(migrated_url: str):
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'markbook_app') THEN "
                "CREATE ROLE markbook_app LOGIN PASSWORD 'markbook_app'; "
                "END IF; END $$;"
            )
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA public TO markbook_app"))
        await conn.execute(text("GRANT SELECT ON schools TO markbook_app"))
        for table in _PHASE4_TABLES:
            await conn.execute(text(f"GRANT SELECT ON {table} TO markbook_app"))
    await engine.dispose()
    engine = create_async_engine(_app_role_url(migrated_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed_grading_chain(url: str, school_id, tag: str) -> None:
    """One scheme + run + result per school, via the superuser (bypasses RLS)."""
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        school = str(school_id)
        level, klass, subject = uuid4(), uuid4(), uuid4()
        class_subject, session_, term = uuid4(), uuid4(), uuid4()
        template, version, assessment = uuid4(), uuid4(), uuid4()
        student, enrolment, subject_enrolment = uuid4(), uuid4(), uuid4()
        scheme, run, result = uuid4(), uuid4(), uuid4()
        for stmt, params in [
            (
                "INSERT INTO schools (id, name) VALUES (:s, :tag) ON CONFLICT (id) DO NOTHING",
                {"s": school, "tag": tag},
            ),
            (
                "INSERT INTO educational_levels (id, school_id, name, ordinal) "
                "VALUES (:id, :s, 'JSS ' || :tag, 2)",
                {"id": level, "s": school, "tag": tag},
            ),
            (
                "INSERT INTO classes (id, school_id, level_id, name, ordinal) "
                "VALUES (:id, :s, :l, 'JSS 1 ' || :tag, 1)",
                {"id": klass, "s": school, "l": level, "tag": tag},
            ),
            (
                "INSERT INTO subjects (id, school_id, name) VALUES (:id, :s, 'Maths ' || :tag)",
                {"id": subject, "s": school, "tag": tag},
            ),
            (
                "INSERT INTO class_subjects (id, school_id, class_id, subject_id) "
                "VALUES (:id, :s, :c, :sub)",
                {"id": class_subject, "s": school, "c": klass, "sub": subject},
            ),
            (
                "INSERT INTO academic_sessions (id, school_id, name, is_current) "
                "VALUES (:id, :s, '2025/2026 ' || :tag, true)",
                {"id": session_, "s": school, "tag": tag},
            ),
            (
                "INSERT INTO terms (id, school_id, session_id, name, ordinal) "
                "VALUES (:id, :s, :a, 'First Term', 1)",
                {"id": term, "s": school, "a": session_},
            ),
            (
                "INSERT INTO assessment_templates (id, school_id, name) "
                "VALUES (:id, :s, 'Template ' || :tag)",
                {"id": template, "s": school, "tag": tag},
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
                "status) VALUES (:id, :s, 'Ada', :ln, 'ADM-' || :adm, 'active')",
                {"id": student, "s": school, "ln": tag, "adm": tag},
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
                "definition) VALUES (:id, :s, 'WAEC ' || :tag, 1, 'active', :def)",
                {
                    "id": scheme,
                    "s": school,
                    "tag": tag,
                    "def": (
                        '{"rounding_mode": "ROUND_HALF_UP", "precision": 0, '
                        '"missing_policy": "flag_incomplete", "absent_policy": "treat_zero", '
                        '"exempt_policy": "exclude_and_renormalise", '
                        '"boundaries": [{"grade": "A", "min": 0, "max": 100}], '
                        '"tie_policy": "dense"}'
                    ),
                },
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
                "VALUES (:id, :s, :r, :se, 78.00, 'A', 1, '[]'::jsonb, '[]'::jsonb)",
                {"id": result, "s": school, "r": run, "se": subject_enrolment},
            ),
        ]:
            await conn.execute(text(stmt), params)
    await engine.dispose()


async def test_phase4_rls_blocks_cross_tenant_reads(
    two_schools, migrated_url, app_role_session_factory
) -> None:
    school_a, school_b = two_schools
    # Scheme names are UNIQUE per (school, name, version_no) — the tag keeps the
    # two schools' seeds distinguishable anyway.
    await _seed_grading_chain(migrated_url, school_a, "P4-AAA")
    await _seed_grading_chain(migrated_url, school_b, "P4-BBB")

    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_a))
            for table in _PHASE4_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert rows, f"{table}: seeded rows invisible to their own school"
                assert {r[0] for r in rows} <= {school_a}, f"{table} leaked school B"

    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_b))
            for table in _PHASE4_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert {r[0] for r in rows} <= {school_b}, f"{table} leaked school A"


async def test_phase4_rls_blocks_unset_context(migrated_url, app_role_session_factory) -> None:
    await _seed_grading_chain(migrated_url, uuid4(), "P4-UAA")

    async with app_role_session_factory() as session:
        async with session.begin():
            for table in _PHASE4_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert rows == [], f"{table} visible with no tenant context set"
