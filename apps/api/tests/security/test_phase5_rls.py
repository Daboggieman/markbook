"""RLS isolation for the Phase 5 tenant tables (spec §6.5).

Same treatment as Phases 3–4: the three tables migration 0006 created —
workflow_definitions, approval_records, published_documents — checked
through the dedicated non-superuser app role, so the policies are
load-bearing rather than decorative.
"""

# ruff: noqa: S608  — table names come from the fixed _PHASE5_TABLES tuple.

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.platform.db import set_tenant_context

pytestmark = pytest.mark.rls

_PHASE5_TABLES = (
    "workflow_definitions",
    "approval_records",
    "published_documents",
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
        for table in _PHASE5_TABLES:
            await conn.execute(text(f"GRANT SELECT ON {table} TO markbook_app"))
    await engine.dispose()
    engine = create_async_engine(_app_role_url(migrated_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def _seed_workflow_chain(url: str, school_id, tag: str) -> None:
    """One definition + one approval record + one published document per
    school, via the superuser (bypasses RLS)."""
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        school = str(school_id)
        level, klass, subject = uuid4(), uuid4(), uuid4()
        class_subject, session_, term = uuid4(), uuid4(), uuid4()
        template, version, assessment = uuid4(), uuid4(), uuid4()
        student, enrolment, subject_enrolment = uuid4(), uuid4(), uuid4()
        user, definition, record, document = uuid4(), uuid4(), uuid4(), uuid4()
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
                "subject_id, template_version_id, workflow_state) "
                "VALUES (:id, :s, :t, :c, NULL, :sub, :v, 'published')",
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
                "INSERT INTO users (id, school_id, email, username, password_hash, "
                "is_super_admin, status, token_version, failed_login_count) "
                "VALUES (:id, :s, :email, :username, 'x', false, 'active', 1, 0)",
                {
                    "id": user,
                    "s": school,
                    "email": f"{user.hex[:8]}@p5rls.local",
                    "username": f"u{user.hex[:8]}",
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
                "INSERT INTO workflow_definitions (id, school_id, name, stages, created_by) "
                "VALUES (:id, :s, 'Def ' || :tag, '[{\"state\": \"submitted\"}]'::jsonb, :u)",
                {"id": definition, "s": school, "tag": tag, "u": user},
            ),
            (
                "INSERT INTO approval_records (id, school_id, assessment_id, from_state, "
                "to_state, actor_id, reason) "
                "VALUES (:id, :s, :a, 'locked', 'published', :u, NULL)",
                {"id": record, "s": school, "a": assessment, "u": user},
            ),
            (
                "INSERT INTO published_documents (id, school_id, assessment_id, enrolment_id, "
                "kind, doc_version, storage_key, checksum, published_by) "
                "VALUES (:id, :s, :a, :se, 'report_card', 1, 'schools/' || :s || '/x.pdf', "
                "'ab' || 'cd' || 'ef' || '00', :u)",
                {"id": document, "s": school, "a": assessment, "se": subject_enrolment, "u": user},
            ),
        ]:
            await conn.execute(text(stmt), params)
    await engine.dispose()


async def test_phase5_rls_blocks_cross_tenant_reads(
    two_schools, migrated_url, app_role_session_factory
) -> None:
    school_a, school_b = two_schools
    await _seed_workflow_chain(migrated_url, school_a, "P5-AAA")
    await _seed_workflow_chain(migrated_url, school_b, "P5-BBB")

    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_a))
            for table in _PHASE5_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert rows, f"{table}: seeded rows invisible to their own school"
                assert {r[0] for r in rows} <= {school_a}, f"{table} leaked school B"

    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_b))
            for table in _PHASE5_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert {r[0] for r in rows} <= {school_b}, f"{table} leaked school A"


async def test_phase5_rls_blocks_unset_context(migrated_url, app_role_session_factory) -> None:
    await _seed_workflow_chain(migrated_url, uuid4(), "P5-UAA")

    async with app_role_session_factory() as session:
        async with session.begin():
            for table in _PHASE5_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert rows == [], f"{table} visible with no tenant context set"
