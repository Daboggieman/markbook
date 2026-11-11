"""FastAPI authorization dependencies (Phase 1).

`require(permission, resource_loader)` is mandatory on every route. A CI test
(route-coverage guard) fails if any route lacks `require` or an explicit
`@public` marker.

The actor is derived from the JWT only — school_id never comes from client
input (spec §5). `token_version` is checked through a short Redis cache
(30 s TTL) to avoid a DB hit on every request; a revocation bumps the cache
version so tokens expire within one TTL window.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.repository import AccessRepository
from app.access.service import (
    SENSITIVE_PERMISSIONS,
    Actor,
    ResourceRef,
    authorize,
    scope_filter,
)
from app.platform.db import get_sessionmaker, set_tenant_context
from app.platform.errors import PERMISSION_DENIED, ProblemError
from app.platform.logging import get_logger

log = get_logger("auth")

TOKEN_VERSION_CACHE_TTL = 30  # seconds (spec §7.1)
_PUBLIC_ATTR = "_markbook_public"


def public(func: Any) -> Any:
    """Mark a route as public so the route-coverage test skips it."""
    setattr(func, _PUBLIC_ATTR, True)
    return func


def decode_bearer(request: Request) -> dict[str, Any]:
    """Extract and decode the JWT from the Authorization header.

    Raises ProblemError(401) if absent or malformed.
    """
    from app.identity.tokens import decode_access_token

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise ProblemError(
            PERMISSION_DENIED,
            "Missing bearer token",
            status=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth.removeprefix("Bearer ").strip()
    try:
        return decode_access_token(token)
    except Exception as exc:
        raise ProblemError(
            PERMISSION_DENIED, "Invalid or expired access token", status=401
        ) from exc


async def get_cached_token_version(user_id: UUID) -> int | None:
    """Return the current token_version from Redis, or None if not cached.

    On cache miss, load from DB and populate the cache. Returns None if the
    user has never had a session (first login has version=1, which == default).
    """
    from app.platform.redis_cache import get_cached_token_version as _cached

    return await _cached(user_id)


async def _load_grants(session: Any, user_id: UUID) -> list[tuple[str, str]]:
    """Load effective permissions from the DB; no caching in Phase 1."""
    repo = AccessRepository(session)
    return await repo.effective_permissions(user_id)


def require(
    permission: str,
    resource_loader: Callable[..., Any] | None = None,
) -> Callable[[Request], Awaitable[Actor]]:
    """Route dependency: authenticate, then authorize `permission`.

    Usage::

        @router.get("/students")
        async def list_students(
            actor: Actor = Depends(require("students.view")),
            session: AsyncSession = Depends(get_db_session),
        ): ...

    With a resource::

        @router.patch("/students/{student_id}")
        async def edit_student(
            student_id: UUID,
            actor: Actor = Depends(
                require(
                    "students.edit",
                    lambda session, path_params: load_student(session, student_id),
                )
            ),
        ): ...

    `resource_loader(session, path_params)` is called only when the permission
    is `assigned` or `own`; it must return a `ResourceRef` or None.
    """

    async def dependency(request: Request) -> Actor:
        actor = await _authenticate(request)

        maker = get_sessionmaker()
        async with maker() as session:
            async with session.begin():
                await set_tenant_context(session, str(actor.school_id))
                grants = await _load_grants(session, actor.user_id)
                resource: ResourceRef | None = None
                if resource_loader is not None:
                    resource = resource_loader(session, request.path_params)

                try:
                    authorize(grants, permission, resource, actor=actor)
                except ProblemError:
                    if permission in SENSITIVE_PERMISSIONS:
                        log.warning(
                            "permission_denied",
                            permission=permission,
                            user_id=str(actor.user_id),
                            path=str(request.url.path),
                        )
                    raise

        return actor

    return dependency


async def _authenticate(request: Request) -> Actor:
    """Decode the bearer token and verify token_version against Redis."""
    claims = decode_bearer(request)
    version_now = await get_cached_token_version(UUID(claims["sub"]))
    if version_now is not None and int(claims["token_version"]) != version_now:
        raise ProblemError(
            PERMISSION_DENIED,
            "Token revoked; sign in again",
            status=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Actor(
        user_id=UUID(claims["sub"]),
        school_id=UUID(claims["school_id"]),
        token_version=int(claims["token_version"]),
        session_id=UUID(claims["session_id"]),
    )


def require_with_scope(
    permission: str,
) -> Callable[[Request], Awaitable[tuple[Actor, str]]]:
    """As require(), but returns `(actor, scope)` for list endpoints.

    Lists have no single resource to authorize against — the scoping IS the
    authorization (spec §7.2). The caller passes the returned scope to the
    service: 'school' lists everything, 'assigned' narrows to the actor's
    teacher assignments (Phase 2 resolver), 'own' the service's call.
    """

    async def dependency(request: Request) -> tuple[Actor, str]:
        actor = await _authenticate(request)
        maker = get_sessionmaker()
        async with maker() as session:
            async with session.begin():
                await set_tenant_context(session, str(actor.school_id))
                grants = await _load_grants(session, actor.user_id)
        scope = scope_filter(grants, permission)
        return actor, scope

    return dependency


async def get_actor_db(request: Request) -> AsyncIterator[AsyncSession]:
    """DB dependency with the tenant context derived from the bearer token.

    get_db leaves `app.school_id` unset, and RLS then hides every row from the
    non-superuser app role — any route reading tenant data must use this one.
    """
    claims = decode_bearer(request)
    school_id = str(UUID(claims["school_id"]))
    async with get_sessionmaker()() as session:
        async with session.begin():
            await set_tenant_context(session, school_id)
            yield session


def get_db_session(school_id: str = "-") -> Any:
    """Placeholder — replaced by platform.db.get_db in the real app factory.

    Phase 1 router wiring will use the real get_db.
    """
    from app.platform.db import get_db

    return Depends(get_db)
