"""Access-package coverage completion.

The 90% gate (docs/build_docs/05-testing-strategy.md) covers `access` as well
as `grading` and `workflow`. Two Phase 1 surfaces were never exercised by any
later phase:

  - AccessRepository's role-management methods — no roles API exists yet;
    they are the storage seam a Phase 6 admin screen will sit on;
  - access/schemas.py — no router imports it yet.

This file drives both directly, plus the bearer-envelope 401 paths and the
expired-reauth window of access/dependency.py over real HTTP. The missing and
malformed-token 401s fire before any SQL (decode_bearer runs first inside
every auth dependency), so they need the app but not the testcontainer; the
expired-reauth probe needs a granted user because require() opens a DB
session before require_reauth gets its turn.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.params import Depends
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.access.dependency import get_db_session
from app.access.repository import AccessRepository
from app.access.schemas import (
    EffectivePermission,
    RoleCreate,
    RolePermissionAssign,
    RoleResponse,
    RoleUpdate,
    RoleWithPermissions,
    UserProfileResponse,
)
from app.identity.tokens import create_access_token

LOCK_URL = "/api/v1/assessments/{}/lock"  # any reauth-protected route works


@pytest.fixture
async def client(monkeypatch):
    """The real app; no DB rows seeded — the probed 401s fire before SQL."""
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestBearerEnvelope:
    async def test_missing_bearer_token(self, client: AsyncClient) -> None:
        r = await client.post(LOCK_URL.format(uuid4()), json={})
        assert r.status_code == 401, r.text
        assert "Missing bearer token" in r.json()["detail"]

    async def test_malformed_bearer_token(self, client: AsyncClient) -> None:
        r = await client.post(
            LOCK_URL.format(uuid4()), json={}, headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert r.status_code == 401, r.text
        assert "Invalid or expired" in r.json()["detail"]

    async def test_expired_reauth_window(self, migrated_url: str, monkeypatch) -> None:
        """A reauth token older than the window is refused like no reauth at all.

        Needs a real grant: on the lock route require('results.lock') resolves
        BEFORE require_reauth (signature order), so the token's user must hold
        the permission or the route 403s before the window is ever checked.
        And require() opens a DB session, hence the patched sessionmaker.
        """
        import time

        from app.platform import db as platform_db
        from app.platform.config import get_settings

        engine = create_async_engine(migrated_url)
        monkeypatch.setattr(
            platform_db, "_sessionmaker", async_sessionmaker(engine, expire_on_commit=False)
        )
        school, user, role = uuid4(), uuid4(), uuid4()
        async with engine.begin() as conn:
            for stmt, params in [
                (
                    "INSERT INTO schools (id, name) VALUES (:i, :n) ON CONFLICT (id) DO NOTHING",
                    {"i": school, "n": "ReauthGap"},
                ),
                (
                    "INSERT INTO users (id, school_id, email, username, password_hash, "
                    "is_super_admin, status, token_version, failed_login_count) "
                    "VALUES (:id, :s, :email, :u, :pw, false, 'active', 1, 0)",
                    {
                        "id": user,
                        "s": school,
                        "email": "locker@gap.local",
                        "u": "gap_locker",
                        "pw": "not-used",
                    },
                ),
                (
                    "INSERT INTO roles (id, school_id, name, is_super_admin) "
                    "VALUES (:i, :s, 'Locker', false)",
                    {"i": role, "s": school},
                ),
                (
                    "INSERT INTO role_permissions (role_id, permission_code, scope_type) "
                    "VALUES (:r, 'results.lock', 'school')",
                    {"r": role},
                ),
                (
                    "INSERT INTO user_roles (user_id, role_id, school_id, granted_by) "
                    "VALUES (:u, :r, :s, NULL)",
                    {"u": user, "r": role, "s": school},
                ),
            ]:
                await conn.execute(text(stmt), params)

        stale = int(time.time()) - (get_settings().reauth_window_seconds + 60)
        token, _ = create_access_token(
            user_id=user,
            school_id=school,
            token_version=1,
            session_id=uuid4(),
            reauth_at=stale,
        )
        from app.main import create_app

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                LOCK_URL.format(uuid4()), json={}, headers={"Authorization": f"Bearer {token}"}
            )
        await engine.dispose()
        assert r.status_code == 401, r.text
        assert "expired" in r.json()["detail"]


def test_get_db_session_placeholder_returns_a_dependency() -> None:
    dep = get_db_session()
    assert isinstance(dep, Depends)


# ---- repository: the role-management seam ----------------------------------------


@pytest.mark.db
class TestRepository:
    async def test_role_lifecycle_methods(self, migrated_url: str) -> None:
        engine = create_async_engine(migrated_url)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        school, user, user2 = uuid4(), uuid4(), uuid4()
        pw = "not-used-here"
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO schools (id, name) VALUES (:i, :n) ON CONFLICT (id) DO NOTHING"),
                {"i": school, "n": "AccessGap"},
            )
            for uid, uname in ((user, "gap_a"), (user2, "gap_b")):
                await conn.execute(
                    text(
                        "INSERT INTO users (id, school_id, email, username, password_hash, "
                        "is_super_admin, status, token_version, failed_login_count) "
                        "VALUES (:id, :s, :email, :u, :pw, false, 'active', 1, 0)"
                    ),
                    {"id": uid, "s": school, "email": f"{uname}@gap.local", "u": uname, "pw": pw},
                )

        async with maker() as s:
            repo = AccessRepository(s)
            role = await repo.create_role(
                school_id=school, name="Form Master", description="watches a form"
            )
            # insert path, then the update path on the same (role, code) pair
            await repo.assign_permission_to_role(role.id, "assessments.view", "school")
            await repo.assign_permission_to_role(role.id, "assessments.view", "assigned")
            await repo.assign_role_to_user(
                user_id=user, role_id=role.id, school_id=school, granted_by=None
            )

            assert ("assessments.view", "assigned") in await repo.effective_permissions(user)
            assert await repo.role_ids_for_user(user) == [role.id]
            got = await repo.role_by_id(role.id)
            assert got is not None and got.name == "Form Master"
            assert await repo.is_super_admin(user) is False
            # commit — the next block opens a FRESH session, and an uncommitted
            # flush rolls back on close, hiding block 1's rows from it
            await s.commit()

        async with maker() as s:
            repo = AccessRepository(s)
            sa_role = await repo.create_role(
                school_id=school, name="Super Admin", description=None, is_super_admin=True
            )
            await repo.assign_role_to_user(
                user_id=user2, role_id=sa_role.id, school_id=school, granted_by=None
            )
            assert await repo.is_super_admin(user2) is True

            roles = [r.name for r in await repo.roles_for_school(school)]
            assert roles == sorted(roles)  # order_by(Role.name)
            assert roles == ["Form Master", "Super Admin"]

        await engine.dispose()


# ---- schemas: validation contracts nobody imports yet ----------------------------


class TestSchemas:
    def test_role_create_rejects_short_name(self) -> None:
        with pytest.raises(ValidationError):
            RoleCreate(name="a")
        assert RoleCreate(name="ok").permission_ids == []

    def test_role_permission_assign_scope_pattern(self) -> None:
        assert RolePermissionAssign(permission_codes=["roles.manage"]).scope_type == "school"
        for scope in ("assigned", "own"):
            assert RolePermissionAssign(permission_codes=[], scope_type=scope).scope_type == scope
        with pytest.raises(ValidationError):
            RolePermissionAssign(permission_codes=["x"], scope_type="global")

    def test_role_response_round_trip(self) -> None:
        ns = SimpleNamespace(
            id=uuid4(),
            school_id=uuid4(),
            name="Admin",
            is_super_admin=False,
            description=None,
            created_at=datetime.now(UTC),
        )
        assert RoleResponse.model_validate(ns).name == "Admin"

    def test_user_profile_nests_permissions(self) -> None:
        ns = SimpleNamespace(
            user_id=uuid4(),
            school_id=uuid4(),
            email="t@x.local",
            username="t",
            is_super_admin=False,
        )
        profile = UserProfileResponse(
            **ns.__dict__,
            roles=[
                RoleWithPermissions(
                    **RoleResponse(
                        id=uuid4(),
                        school_id=ns.school_id,
                        name="Teacher",
                        is_super_admin=False,
                        description=None,
                        created_at=datetime.now(UTC),
                    ).model_dump(),
                    permissions=[EffectivePermission(code="scores.enter", scope_type="assigned")],
                )
            ],
            effective_permissions=[EffectivePermission(code="scores.enter", scope_type="own")],
        )
        assert profile.roles[0].permissions[0].code == "scores.enter"
        assert profile.effective_permissions[0].scope_type == "own"

    def test_role_update_partial(self) -> None:
        assert RoleUpdate().name is None
        with pytest.raises(ValidationError):
            RoleUpdate(name="x")
