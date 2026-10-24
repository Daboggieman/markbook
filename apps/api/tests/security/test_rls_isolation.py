"""RLS isolation test — the Phase 0 exit criterion (spec §16).

With RLS enabled on `outbox_events`, a session whose tenant context is school A
must not see school B's rows — even for a query with no WHERE clause. This is
the database-level backstop behind the repository base class.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.platform.db import set_tenant_context

pytestmark = pytest.mark.rls


async def _insert_outbox(url: str, school_id, topic: str) -> None:
    """Insert via a connection with no tenant context (the migration role's view)."""
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


async def test_rls_blocks_cross_tenant_reads(two_schools, migrated_url) -> None:
    school_a, school_b = two_schools

    # One row per school, inserted by the migration role (RLS not applied —
    # it is a table owner / superuser, which is exactly why the app role is not).
    await _insert_outbox(migrated_url, school_a, "results.published")
    await _insert_outbox(migrated_url, school_b, "score.changed")

    # The app role sees only its own school's rows — even with no WHERE clause.
    maker = async_sessionmaker(create_async_engine(migrated_url), expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_a))
            rows = (await session.execute(text("SELECT school_id FROM outbox_events"))).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == school_a

    async with maker() as session:
        async with session.begin():
            await set_tenant_context(session, str(school_b))
            rows = (await session.execute(text("SELECT school_id FROM outbox_events"))).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == school_b


async def test_rls_blocks_unset_context(migrated_url) -> None:
    """No tenant context set → RLS denies every row, not all-but-one's."""
    maker = async_sessionmaker(create_async_engine(migrated_url), expire_on_commit=False)
    async with maker() as session:
        async with session.begin():
            rows = (await session.execute(text("SELECT school_id FROM outbox_events"))).fetchall()
    assert rows == []
