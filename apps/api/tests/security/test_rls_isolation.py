"""RLS isolation test — the Phase 0 exit criterion (spec §16).

With RLS enabled on `outbox_events`, a session whose tenant context is school A
must not see school B's rows — even for a query with no WHERE clause. This is
the database-level backstop behind the repository base class.

The test connects as a dedicated non-superuser role (`markbook_app`): the
postgres superuser bypasses RLS by definition, so testing isolation through
the superuser connection proves nothing. Creating the role here mirrors how
production grants work (spec §5: the app role is not a superuser and does not
bypass RLS).
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.platform.db import set_tenant_context

pytestmark = pytest.mark.rls


async def _create_app_role(url: str) -> None:
    """Create the application role (non-superuser — RLS applies to it)."""
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
        await conn.execute(text("GRANT SELECT, INSERT ON outbox_events TO markbook_app"))
        await conn.execute(text("GRANT SELECT ON schools TO markbook_app"))
    await engine.dispose()


def _app_role_url(url: str) -> str:
    """Swap the connection URL to the app role (no superuser)."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    netloc = f"markbook_app:markbook_app@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


async def _insert_outbox(url: str, school_id, topic: str) -> None:
    """Insert via the migration role (superuser — RLS not applied to it)."""
    from datetime import UTC, datetime

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO outbox_events (id, school_id, topic, payload, created_at) "
                "VALUES (:id, :school_id, :topic, CAST(:payload AS JSONB), :created_at)"
            ).bindparams(
                id=uuid4(),
                school_id=school_id,
                topic=topic,
                payload="{}",
                created_at=datetime.now(UTC),
            )
        )
    await engine.dispose()


@pytest.fixture
async def app_role_session_factory(migrated_url: str):
    """Session factory connecting AS the app role (non-superuser, RLS applies)."""
    await _create_app_role(migrated_url)
    engine = create_async_engine(_app_role_url(migrated_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


async def test_rls_blocks_cross_tenant_reads(
    two_schools, migrated_url, app_role_session_factory
) -> None:
    school_a, school_b = two_schools

    # One row per school, inserted by the migration role (superuser — bypasses RLS).
    await _insert_outbox(migrated_url, school_a, "results.published")
    await _insert_outbox(migrated_url, school_b, "score.changed")

    # The app role sees only its own school's rows — even with no WHERE clause.
    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_a))
            rows = (await session.execute(text("SELECT school_id FROM outbox_events"))).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == school_a

    async with app_role_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_b))
            rows = (await session.execute(text("SELECT school_id FROM outbox_events"))).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == school_b


async def test_rls_blocks_unset_context(migrated_url, app_role_session_factory) -> None:
    """No tenant context set → RLS denies every row, not all-but-one's."""
    async with app_role_session_factory() as session:
        async with session.begin():
            rows = (await session.execute(text("SELECT school_id FROM outbox_events"))).fetchall()
    assert rows == []
