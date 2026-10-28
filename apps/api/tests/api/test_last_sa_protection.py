"""Last active Super Admin cannot be deactivated (spec §7.1 D9).

Service-level complement to the DB trigger test in tests/security/: the
service guard returns a clean 409 so callers never hit the raw trigger
exception, while the trigger remains the hard backstop. Runs against real
Postgres via testcontainers (`db` marker). RLS does not apply — the
testcontainer connection is the table owner/superuser.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.service import IdentityService
from app.platform.errors import CONFLICT, ProblemError

pytestmark = pytest.mark.db


@pytest.fixture
async def maker(migrated_url: str):
    engine = create_async_engine(migrated_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_school(maker: async_sessionmaker, school_id: UUID) -> None:
    async with maker() as s:
        await s.execute(
            text("INSERT INTO schools (id, name) VALUES (:id, :name)"),
            {"id": str(school_id), "name": f"SA Guard {school_id.hex[:8]}"},
        )
        await s.commit()


async def _seed_super_admin(
    maker: async_sessionmaker, school_id: UUID, sa_id: UUID, *, is_super_admin: bool = True
) -> None:
    async with maker() as s:
        await s.execute(
            text(
                "INSERT INTO users (id, school_id, email, username, password_hash, "
                "is_super_admin, status, token_version, failed_login_count) "
                "VALUES (:id, :school, :email, :username, 'x', :sa, 'active', 1, 0)"
            ),
            {
                "id": str(sa_id),
                "school": str(school_id),
                "email": f"{sa_id.hex[:8]}@sa.local",
                "username": f"sa{sa_id.hex[:8]}",
                "sa": is_super_admin,
            },
        )
        await s.commit()


async def test_deactivate_only_sa_returns_409(maker: async_sessionmaker) -> None:
    """Deactivating the sole active Super Admin raises ProblemError 409."""
    school_id, sa_id = uuid4(), uuid4()
    await _seed_school(maker, school_id)
    await _seed_super_admin(maker, school_id, sa_id)

    async with maker() as session:
        svc = IdentityService(session)
        with pytest.raises(ProblemError) as exc_info:
            await svc.set_user_status(user_id=sa_id, new_status="suspended")
        assert exc_info.value.code == CONFLICT
        assert exc_info.value.status == 409


async def test_suspend_allowed_when_other_sa_exists(maker: async_sessionmaker) -> None:
    """Suspending one of two Super Admins succeeds."""
    school_id, sa1, sa2 = uuid4(), uuid4(), uuid4()
    await _seed_school(maker, school_id)
    await _seed_super_admin(maker, school_id, sa1)
    await _seed_super_admin(maker, school_id, sa2)

    async with maker() as session:
        svc = IdentityService(session)
        user = await svc.set_user_status(user_id=sa1, new_status="suspended")
        assert user.status == "suspended"


async def test_deactivate_revokes_sessions_and_bumps_token_version(
    maker: async_sessionmaker,
) -> None:
    """Moving a user out of active kills their sessions and outstanding tokens."""
    from datetime import UTC, datetime, timedelta

    from app.identity.models import Session

    school_id, user_id = uuid4(), uuid4()
    await _seed_school(maker, school_id)
    # A plain user: a lone Super Admin would hit the 409 guard before the
    # revocation path this test exercises.
    await _seed_super_admin(maker, school_id, user_id, is_super_admin=False)

    async with maker() as session:
        session.add(
            Session(
                id=uuid4(),
                school_id=school_id,
                user_id=user_id,
                refresh_token_hash=b"\x01" * 32,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.commit()

    async with maker() as session:
        svc = IdentityService(session)
        user = await svc.set_user_status(user_id=user_id, new_status="suspended")
        assert user.status == "suspended"
        # The router commits after the service call; mirror that contract here.
        await session.commit()

    async with maker() as s:
        revoked = (
            await s.execute(
                text("SELECT revoked_at FROM sessions WHERE user_id = :u"), {"u": str(user_id)}
            )
        ).scalar()
        version = (
            await s.execute(
                text("SELECT token_version FROM users WHERE id = :u"), {"u": str(user_id)}
            )
        ).scalar()
        assert revoked is not None, "live sessions must be revoked on deactivation"
        assert version == 2, "token_version must bump so cached JWTs die"
