"""RLS isolation for the Phase 2 tenant tables (spec §6).

The Phase 0 test proves the mechanism on `outbox_events`; this extends it to
the people/academic tables the Phase 2 migration created — students,
enrolments, subject_enrolments, teacher_assignments — through the dedicated
non-superuser app role, so the policies are load-bearing, not decorative.
"""
# ruff: noqa: S608  — table names come from the fixed _PHASE2_TABLES tuple.

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.platform.db import set_tenant_context

pytestmark = pytest.mark.rls

_PHASE2_TABLES = (
    "students",
    "guardians",
    "student_guardians",
    "academic_sessions",
    "terms",
    "educational_levels",
    "classes",
    "sections",
    "subjects",
    "class_subjects",
    "enrolments",
    "subject_enrolments",
    "teacher_assignments",
    "promotion_records",
)

# Tables the seed below actually populates — these must return rows.
_SEEDED_TABLES = ("educational_levels", "classes", "academic_sessions", "students", "enrolments")


async def _create_app_role(url: str) -> None:
    engine = create_async_engine(url)
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
        for table in _PHASE2_TABLES:
            await conn.execute(text(f"GRANT SELECT ON {table} TO markbook_app"))
    await engine.dispose()


def _app_role_url(url: str) -> str:
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    netloc = f"markbook_app:markbook_app@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


async def _insert_student_and_enrolment(url: str, school_id, tag: str) -> None:
    """Seed via the superuser connection (bypasses RLS by definition)."""
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        session_id = uuid4()
        class_id = uuid4()
        level_id = uuid4()
        student_id = uuid4()
        enrolment_id = uuid4()
        now = datetime.now(UTC)
        await conn.execute(
            text(
                "INSERT INTO educational_levels (id, school_id, name, ordinal) "
                "VALUES (:l, :s, 'JSS', 2)"
            ).bindparams(l=level_id, s=school_id)
        )
        await conn.execute(
            text(
                "INSERT INTO classes (id, school_id, level_id, name, ordinal) "
                "VALUES (:c, :s, :l, 'JSS 1', 1)"
            ).bindparams(c=class_id, s=school_id, l=level_id)
        )
        await conn.execute(
            text(
                "INSERT INTO academic_sessions (id, school_id, name, is_current, "
                "created_at, updated_at, version) "
                "VALUES (:a, :s, '2025/2026 ' || :tag, true, :now, :now, 1)"
            ).bindparams(a=session_id, s=school_id, tag=tag, now=now)
        )
        await conn.execute(
            text(
                "INSERT INTO students (id, school_id, first_name, last_name, status, "
                "created_at, updated_at, version) "
                "VALUES (:st, :s, 'Ada', :tag, 'active', :now, :now, 1)"
            ).bindparams(st=student_id, s=school_id, tag=tag, now=now)
        )
        await conn.execute(
            text(
                "INSERT INTO enrolments (id, school_id, student_id, session_id, class_id, "
                "status, created_at, updated_at, version) "
                "VALUES (:e, :s, :st, :a, :c, 'enrolled', :now, :now, 1)"
            ).bindparams(
                e=enrolment_id, s=school_id, st=student_id, a=session_id, c=class_id, now=now
            )
        )
    await engine.dispose()


@pytest.fixture
async def app_role_session_factory(migrated_url: str):
    await _create_app_role(migrated_url)
    engine = create_async_engine(_app_role_url(migrated_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def test_phase2_rls_blocks_cross_tenant_reads(
    two_schools, migrated_url, app_role_session_factory
) -> None:
    school_a, school_b = two_schools
    await _insert_student_and_enrolment(migrated_url, school_a, "AAA")
    await _insert_student_and_enrolment(migrated_url, school_b, "BBB")

    # School A's context: only A's rows are visible, on every tenant table.
    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_a))
            for table in _PHASE2_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert {r[0] for r in rows} <= {school_a}, f"{table} leaked school B"
            for table in _SEEDED_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert rows, f"{table}: seeded rows invisible to their own school"

    # School B's context: the mirror image.
    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_b))
            for table in _PHASE2_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert {r[0] for r in rows} <= {school_b}, f"{table} leaked school A"


async def test_phase2_rls_blocks_unset_context(migrated_url, app_role_session_factory) -> None:
    # A fresh school, so the fixed-UUID two_schools fixture isn't needed here.
    await _insert_student_and_enrolment(migrated_url, uuid4(), "UAA")

    async with app_role_session_factory() as session:
        async with session.begin():
            for table in _PHASE2_TABLES:
                rows = (await session.execute(text(f"SELECT school_id FROM {table}"))).fetchall()
                assert rows == [], f"{table} visible with no tenant context set"
