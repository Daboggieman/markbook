"""Identity router â€” HTTP layer only (Phase 1).

Every route declares `require(...)` or `@public` (route-coverage guard).
Business logic lives in `identity.service`; this module never touches
repositories directly.
"""
# ruff: noqa: B008  â€” Depends(require(...)) in defaults is the FastAPI idiom.

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.access.dependency import get_actor_db, public, require
from app.access.service import Actor
from app.identity import schemas
from app.identity.service import IdentityService
from app.platform.db import tenant_session
from app.platform.errors import ProblemError

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@public
@router.post("/login", response_model=schemas.LoginResponse)
async def login(
    request: Request,
    body: schemas.LoginRequest,
) -> schemas.LoginResponse:
    """Password login. Throttled per (email, IP) and per IP (spec Â§7.1)."""
    ip = _client_ip(request)
    # Seed School is the single tenant at launch (spec Â§5).
    school_id = UUID("00000000-0000-7000-8000-000000000001")
    async with tenant_session(str(school_id)) as session:
        service = IdentityService(session)
        response, _session = await service.login(
            school_id=school_id,
            email=body.email,
            password=body.password,
            ip=ip,
            user_agent=request.headers.get("User-Agent"),
            device_label=body.device_label,
            device_platform=body.device_platform,
        )
        return response


@public
@router.post("/refresh", response_model=schemas.RefreshResponse)
async def refresh(body: schemas.RefreshRequest) -> schemas.RefreshResponse:
    """Rotate the refresh token; reuse revokes the whole session family."""
    from app.platform.db import get_sessionmaker

    maker = get_sessionmaker()
    async with maker() as session:
        service = IdentityService(session)
        response = await service.refresh(body.refresh_token, ip=None)
        await session.commit()
        return response


@router.post("/logout")
async def logout(
    actor: Actor = Depends(require("sessions.manage")),
    session=Depends(get_actor_db),
) -> dict[str, str]:
    """Revoke the current session (spec Â§7.1)."""
    from app.identity.repository import IdentityRepository

    repo = IdentityRepository(session)
    await repo.revoke_session(actor.session_id)
    return {"status": "logged_out"}


# ---------------------------------------------------------------------------
# MFA
# ---------------------------------------------------------------------------


@router.get("/users/me/mfa/setup", response_model=schemas.MfaSetupResponse)
async def mfa_setup(
    actor: Actor = Depends(require("users.edit")),
    session=Depends(get_actor_db),
) -> schemas.MfaSetupResponse:
    """Generate a new TOTP secret for the current user."""
    from app.identity.repository import IdentityRepository

    repo = IdentityRepository(session)
    user = await repo.get_user_by_id(actor.user_id)
    if user is None:
        raise ProblemError("NOT_FOUND", "User not found", status=404)
    service = IdentityService(session)
    return await service.setup_mfa(user)


@router.post("/users/me/mfa/verify")
async def mfa_verify(
    body: schemas.MfaVerifyRequest,
    actor: Actor = Depends(require("users.edit")),
    session=Depends(get_actor_db),
) -> dict[str, bool]:
    """Verify a TOTP code."""
    from app.identity.repository import IdentityRepository

    repo = IdentityRepository(session)
    user = await repo.get_user_by_id(actor.user_id)
    if user is None:
        raise ProblemError("NOT_FOUND", "User not found", status=404)
    service = IdentityService(session)
    ok = await service.verify_mfa(user, body.totp_code)
    return {"verified": ok}


# ---------------------------------------------------------------------------
# Users (admin)
# ---------------------------------------------------------------------------


@router.get(
    "/users",
    response_model=list[schemas.UserListItem],
    dependencies=[Depends(require("users.view"))],
)
async def list_users(
    actor: Actor = Depends(require("users.view")),
    session=Depends(get_actor_db),
) -> list[schemas.UserListItem]:
    """List users scoped to the actor's school (RLS enforced)."""
    from sqlalchemy import select

    from app.identity.models import User

    result = await session.execute(
        select(User).where(User.school_id == actor.school_id).order_by(User.email)
    )
    users = result.scalars().all()
    return [schemas.UserListItem.model_validate(u) for u in users]


@router.post(
    "/users",
    response_model=schemas.UserResponse,
    status_code=201,
    dependencies=[Depends(require("users.create"))],
)
async def create_user(
    body: schemas.UserCreate,
    actor: Actor = Depends(require("users.create")),
    session=Depends(get_actor_db),
) -> schemas.UserResponse:
    """Create a user. Cannot create a Super Admin without roles.manage."""
    service = IdentityService(session)
    user = await service.create_user(
        school_id=actor.school_id,
        email=body.email,
        username=body.username,
        password=body.password,
        is_super_admin=body.is_super_admin,
    )
    return schemas.UserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}",
    response_model=schemas.UserResponse,
    dependencies=[Depends(require("users.edit"))],
)
async def change_user_status(
    user_id: UUID,
    body: schemas.UserStatusUpdate,
    actor: Actor = Depends(require("users.edit")),
    session=Depends(get_actor_db),
) -> schemas.UserResponse:
    """Change a user's status (active/suspended/deactivated).

    Deactivating the last active Super Admin returns 409 (spec Â§7.1 D9).
    """
    service = IdentityService(session)
    user = await service.set_user_status(user_id=user_id, new_status=body.status)
    await session.commit()
    return schemas.UserResponse.model_validate(user)
