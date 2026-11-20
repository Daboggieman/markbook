"""The roles platform endpoints (Phase 6).

Phase 1/2 built the storage seam and the schemas; the router exposing them is
new. These tests drive the five routes over real HTTP against the throwaway
Postgres: the happy-path lifecycle (catalogue → create role → attach grants →
grant to user → effective_permissions flow through → revoke) plus the gate
matrix (401 without a token, 403 without the permission, 422 unknown codes,
403 super-admin escalation).
"""

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.tokens import create_access_token

USER_SQL = (
    "INSERT INTO users (id, school_id, email, username, password_hash, "
    "is_super_admin, status, token_version, failed_login_count) "
    "VALUES (:id, :s, :email, :u, :pw, :sa, 'active', 1, 0)"
)
ROLE_SQL = (
    "INSERT INTO roles (id, school_id, name, is_super_admin) "
    "VALUES (:i, :s, :n, :sa)"
)
GRANT_SQL = (
    "INSERT INTO role_permissions (role_id, permission_code, scope_type) "
    "VALUES (:r, :p, :sc)"
)
USER_ROLE_SQL = (
    "INSERT INTO user_roles (user_id, role_id, school_id, granted_by) "
    "VALUES (:u, :r, :s, NULL)"
)


async def _seed(url: str, stmts: list[tuple[str, dict]]) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        for stmt, params in stmts:
            await conn.execute(text(stmt), params)
    await engine.dispose()


def _authed_app(monkeypatch, url: str):
    from app.main import create_app
    from app.platform import db as platform_db

    engine = create_async_engine(url)
    monkeypatch.setattr(platform_db, "_sessionmaker", async_sessionmaker(engine, expire_on_commit=False))
    app = create_app()
    return app, engine


@pytest.mark.db
class TestRolesLifecycle:
    async def test_full_lifecycle(self, migrated_url: str, monkeypatch) -> None:
        """Catalogue → create role → attach grants → grant to a second user →
        the grants show up in that user's effective_permissions → revoke."""
        app, engine = _authed_app(monkeypatch, migrated_url)
        school, admin, user2, role = uuid4(), uuid4(), uuid4(), uuid4()
        await _seed(
            migrated_url,
            [
                ("INSERT INTO schools (id, name) VALUES (:i, :n) ON CONFLICT (id) DO NOTHING",
                 {"i": school, "n": "RolesApi"}),
                (USER_SQL, {"id": admin, "s": school, "email": "admin@roles.local",
                            "u": "roles_admin", "pw": "x", "sa": False}),
                (USER_SQL, {"id": user2, "s": school, "email": "u2@roles.local",
                            "u": "roles_u2", "pw": "x", "sa": False}),
                (ROLE_SQL, {"i": role, "s": school, "n": "Clerk", "sa": False}),
                (GRANT_SQL, {"r": role, "p": "roles.view", "sc": "school"}),
                (GRANT_SQL, {"r": role, "p": "roles.manage", "sc": "school"}),
                (GRANT_SQL, {"r": role, "p": "permissions.view", "sc": "school"}),
                (GRANT_SQL, {"r": role, "p": "users.edit", "sc": "school"}),
                (USER_ROLE_SQL, {"u": admin, "r": role, "s": school}),
            ],
        )
        token, _ = create_access_token(
            user_id=admin, school_id=school, token_version=1, session_id=uuid4()
        )
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # catalogue
            r = await c.get("/api/v1/permissions", headers=headers)
            assert r.status_code == 200, r.text
            assert "roles.manage" in [p["code"] for p in r.json()]

            # create with initial grants
            r = await c.post(
                "/api/v1/roles",
                headers=headers,
                json={"name": "Form Master", "description": "watches a form",
                      "permission_ids": [["students.view", "school"]]},
            )
            assert r.status_code == 201, r.text
            form_master = r.json()
            assert [p["code"] for p in form_master["permissions"]] == ["students.view"]

            # list includes it
            r = await c.get("/api/v1/roles", headers=headers)
            assert r.status_code == 200, r.text
            assert any(g["name"] == "Form Master" for g in r.json())

            # attach (code re-uses the upsert path, re-scoping students.view)
            r = await c.post(
                f"/api/v1/roles/{form_master['id']}/permissions",
                headers=headers,
                json={"permission_codes": ["students.view"], "scope_type": "assigned"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["permissions"] == [
                {"code": "students.view", "scope_type": "assigned"}
            ]

            # grant the role to user2 — their /me now carries the permission
            r = await c.post(
                f"/api/v1/users/{user2}/roles", headers=headers, json={"role_id": form_master["id"]}
            )
            assert r.status_code == 200, r.text
            token2, _ = create_access_token(
                user_id=user2, school_id=school, token_version=1, session_id=uuid4()
            )
            r = await c.get(
                "/api/v1/auth/users/me", headers={"Authorization": f"Bearer {token2}"}
            )
            assert r.status_code == 200, r.text
            assert ("students.view", "assigned") in [
                (p["code"], p["scope_type"]) for p in r.json()["effective_permissions"]
            ]

            # revoke — the permission is gone again
            r = await c.delete(
                f"/api/v1/users/{user2}/roles/{form_master['id']}", headers=headers
            )
            assert r.status_code == 200, r.text
            assert r.json()["removed"] is True
            r = await c.get(
                "/api/v1/auth/users/me", headers={"Authorization": f"Bearer {token2}"}
            )
            assert r.json()["effective_permissions"] == []

            # validation: unknown permission code → 422, not an FK 500
            r = await c.post(
                "/api/v1/roles", headers=headers,
                json={"name": "Broken", "permission_ids": [["not_a_code", "school"]]},
            )
            assert r.status_code == 422, r.text

        await engine.dispose()

    async def test_gates(self, migrated_url: str, monkeypatch) -> None:
        """401 without a token; 403 without the permission; granting a
        super-admin role needs roles.manage beyond users.edit."""
        app, engine = _authed_app(monkeypatch, migrated_url)
        school, user, sa_role = uuid4(), uuid4(), uuid4()
        await _seed(
            migrated_url,
            [
                ("INSERT INTO schools (id, name) VALUES (:i, :n) ON CONFLICT (id) DO NOTHING",
                 {"i": school, "n": "RolesGate"}),
                (USER_SQL, {"id": user, "s": school, "email": "g@roles.local",
                            "u": "g_user", "pw": "x", "sa": False}),
                (ROLE_SQL, {"i": sa_role, "s": school, "n": "Big Admin", "sa": True}),
            ],
        )
        await _seed(
            migrated_url,
            [
                (ROLE_SQL, {"i": edit_role, "s": school, "n": "Editor", "sa": False}),
                (GRANT_SQL, {"r": edit_role, "p": "users.edit", "sc": "school"}),
                (USER_ROLE_SQL, {"u": user, "r": edit_role, "s": school}),
            ],
        )
        token, _ = create_access_token(
            user_id=user, school_id=school, token_version=1, session_id=uuid4()
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/roles")
            assert r.status_code == 401, r.text

            r = await c.get("/api/v1/roles", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 403, r.text

            # users.edit alone must NOT be able to grant a super-admin role
            r = await c.post(
                f"/api/v1/users/{user}/roles",
                headers={"Authorization": f"Bearer {token}"},
                json={"role_id": str(sa_role)},
            )
            assert r.status_code == 403, r.text
        await engine.dispose()
