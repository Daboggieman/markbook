"""Super Admin protection trigger tests (Phase 1 exit criterion, spec §7.1 D9).

The DB trigger `protect_super_admin` is the backstop: no application bug may
allow deleting, deactivating or demoting a school's last active Super Admin.
Runs against real Postgres via testcontainers (`db` marker — CI's DB step).

Triggers fire regardless of the connecting role, so the throwaway container's
superuser connection exercises them fully.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.db


@pytest.fixture
async def school_id(migrated_url: str) -> str:
    """A fresh school per test so trigger counts are isolated between tests."""
    school_id = uuid4()
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO schools (id, name) VALUES (:id, :name)"),
            {"id": school_id, "name": "Trigger Test School"},
        )
    await engine.dispose()
    return str(school_id)


async def _insert_user(
    migrated_url: str, school_id: str, *, is_super_admin: bool, status: str = "active"
) -> str:
    user_id = str(uuid4())
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, school_id, email, username, password_hash, "
                "is_super_admin, status) VALUES (:id, :school, :email, :username, 'x', :sa, :st)"
            ),
            {
                "id": user_id,
                "school": school_id,
                "email": f"{user_id[:8]}@test.local",
                "username": f"u{user_id[:8]}",
                "sa": is_super_admin,
                "st": status,
            },
        )
    await engine.dispose()
    return user_id


async def _exec(migrated_url: str, sql: str, user_id: str) -> None:
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        # Bind as UUID, not str — psycopg renders str as VARCHAR and uuid = varchar has no operator.
        await conn.execute(text(sql).bindparams(id=UUID(user_id)))
    await engine.dispose()


async def test_delete_last_active_super_admin_blocked(migrated_url: str, school_id: str) -> None:
    user = await _insert_user(migrated_url, school_id=school_id, is_super_admin=True)
    with pytest.raises(SQLAlchemyError, match="last active Super Admin"):
        await _exec(migrated_url, "DELETE FROM users WHERE id = :id", user)


async def test_deactivate_last_active_super_admin_blocked(
    migrated_url: str, school_id: str
) -> None:
    user = await _insert_user(migrated_url, school_id, is_super_admin=True)
    with pytest.raises(SQLAlchemyError, match="deactivate the last active Super Admin"):
        await _exec(migrated_url, "UPDATE users SET status = 'suspended' WHERE id = :id", user)


async def test_delete_allowed_when_second_active_super_admin_exists(
    migrated_url: str, school_id: str
) -> None:
    first = await _insert_user(migrated_url, school_id, is_super_admin=True)
    await _insert_user(migrated_url, school_id, is_super_admin=True)
    await _exec(migrated_url, "DELETE FROM users WHERE id = :id", first)  # no raise


async def test_deactivate_allowed_when_another_active_super_admin_remains(
    migrated_url: str, school_id: str
) -> None:
    await _insert_user(migrated_url, school_id, is_super_admin=True)  # stays active
    other = await _insert_user(migrated_url, school_id, is_super_admin=True)
    await _exec(migrated_url, "UPDATE users SET status = 'suspended' WHERE id = :id", other)


async def test_delete_non_super_admin_never_blocked(migrated_url: str, school_id: str) -> None:
    user = await _insert_user(migrated_url, school_id, is_super_admin=False)
    await _exec(migrated_url, "DELETE FROM users WHERE id = :id", user)  # no raise
