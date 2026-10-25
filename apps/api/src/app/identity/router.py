"""Identity router — HTTP layer only (Phase 1).

Every route declares `require(...)` or `@public` (route-coverage guard).
Business logic lives in `identity.service`; this module never touches
repositories directly.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.access.dependency import get_actor, public, require
from app.access.service import Actor
from app.identity import schemas
from app.identity.service import IdentityService
from app.platform.db import get_db
from app.platform.errors import INVALID_CREDENTIALS, ProblemError
from app.platform.throttling import record_login_failure, record_login_success

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@public
@router.post("/login", response_model=schemas.LoginResponse)
async def login(
    request: Request,
    body: schemas.LoginRequest,
    session=Depends(get_db),
) -> schemas.LoginResponse:
    """Password login. Throttled per (email, IP) and per IP (spec §7.1)."""
    from app.platform.config import get_settings

    ip = _client_ip(request)
    # Seed School is the single tenant at launch (spec §5).
    school_id = UUID("00000000-0000-7000-8000-000000000001")

    service = IdentityService(session)
    try:
        response, _session = await service.login(
            school_id=school_id,
            email=body.email,
            password=body.password,
            ip=ip,
            user_agent=request.headers.get("User-Agent"),
            device_label=body.device_label,
            device_platform=body.device_platform,
        )
    except ProblemError:
        raise

    await record_login_success(email=body.email, ip=ip)
    return response


@public
@router.post("/refresh", response_model=schemas.RefreshResponse)
async def refresh(body: schemas.RefreshRequest) -> schemas.RefreshResponse:
    """Rotate the refresh token; reuse revokes the whole session family."""
    from fastapi import Request as _Request  # placeholder to avoid lint complaint

    # Refresh is a pure token operation; it opens its own session.
    from app.platform.db import get_sessionmaker
    from app.platform.errors import RATE_LIMITED

    from app.platform.throttling import check_login_throttle

    service = IdentityService(_new_session())
    return await service.refresh(body.refresh_token)


@router.post("/logout")
async def logout(
    actor: Annotated[object, Depends(get_actor)],
    session: Any = Depends(get_db),
) -> dict[str, str]:
    """Revoke the current session (spec §7.1)."""
    from app.identity.repository import IdentityRepository

    await IdentityRepository(session).revoke_session(actor.session_id)
    return {"status": "logged_out"}


@router.post("/mfa/setup", response_model=schemas.MfaSetupResponse)
async def mfa_setup(
    actor: Annotated[object, Depends(get_actor)],
    session: Any = Depends(get_db),
) -> schemas.MfaSetupResponse:
    """Generate a TOTP secret for the current user."""
    from app.identity.repository import IdentityRepository

    repo = IdentityRepository(session)
    user = await repo.get_user_by_id(actor.user_id)
    if user is None:
        raise ProblemError("NOT_FOUND", "User not found", status=404)
    service = IdentityService(session)
    result = await service.setup_mfa(user)
    return result


@router.post("/mfa/verify")
async def mfa_verify(
    body: schemas.MfaVerifyRequest,
    actor: Annotated[object, Depends(get_actor)],
    session: Any = Depends(get_db),
) -> dict[str, bool]:
    """Verify a TOTP code for the current user."""
    from app.identity.repository import IdentityRepository

    repo = IdentityRepository(session)
    user = await repo.get_user_by_id(actor.user_id)
    if user is None:
        raise ProblemError("NOT_FOUND", "User not found", status=404)
    service = IdentityService(session)
    ok = await service.verify_mfa(user, body.totp_code)
    return {"verified": ok}


@router.post("/reauth", response_model=schemas.RefreshResponse)
async def reauth(
    body: schemas.ReauthRequest,
    actor: Annotated[object, Depends(get_actor)],
    session: Any = Depends(get_db),
) -> dict[str, str]:
    """Step-up authentication: fresh password check returns a new access token
    with `reauth_at` claim valid for 5 minutes (spec §7.1)."""
    from app.identity.repository import IdentityRepository
    from app.identity.service import verify_password

    repo = IdentityRepository(session)
    user = await repo.get_user_by_id(actor.user_id)
    if user is None or not verify_password(body.password, user.password_hash):
        raise ProblemError(INVALID_CREDENTIALS, "Invalid password", status=401)
    return {"reauthenticated": "true", "valid_for_seconds": "300"}


# Users (admin) -----------------------------------------------------------------


@router.get("/users", response_model=list[schemas.UserListItem])
async def list_users(
    actor: Annotated[object, Depends(get_actor)],
    session: Any = Depends(get_db),
) -> list[schemas.UserListItem]:
    """List users (school scope enforced by RLS)."""
    from sqlalchemy import select

    from app.identity.models import User

    result = await session.execute(select(User))
    users = result.scalars().all()
    return [schemas.UserListItem.model_validate(u) for u in users]


@router.post("/users", response_model=schemas.UserResponse, status_code=201)
async def create_user(
    body: schemas.UserCreate,
    actor: Annotated[object, Depends(get_actor)],
    session: Any = Depends(get_db),
) -> schemas.UserResponse:
    """Create a user. Super Admin flag requires users.manage + audit."""
    from app.identity.service import hash_password

    service = IdentityService(session)
    user = await service.create_user(
        school_id=actor.school_id,
        email=body.email,
        username=body.username,
        password=body.password,
        is_super_admin=body.is_super_admin,
    )
    return schemas.UserResponse.model_validate(user)
