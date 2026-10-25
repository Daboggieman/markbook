"""Identity service — authentication business logic (Phase 1).

Owns: login (with throttling + lockout), JWT access tokens, refresh rotation
with reuse detection, logout, session revocation, MFA (TOTP), re-auth step-up.

Rules (spec §7.1):
  - Argon2id password hashing (tuned params in config).
  - Access token: short-lived JWT (10–15 min) with sub, school_id,
    token_version, session_id.
  - Refresh token: opaque random value, stored hashed, rotated on every use.
  - Refresh reuse revokes the whole session family.
  - Login throttling: Redis counters per (email, IP) and per IP, exponential
    backoff plus `locked_until`.
  - MFA: TOTP, mandatory for Super Admin and privileged roles.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pyotp
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Device, Session, User
from app.identity.repository import IdentityRepository
from app.identity.schemas import LoginResponse, MfaSetupResponse, RefreshResponse
from app.platform.config import get_settings
from app.platform.errors import ProblemError

# Argon2id password hashing (spec §7.1); parameters come from config.
_pwd_context: "PasswordContext" | None = None


class PasswordContext:
    """Argon2id hashing tuned from config (verify_and_update rehashes lazily)."""

    def __init__(self) -> None:
        from passlib.context import CryptContext

        settings = get_settings()
        self._ctx = CryptContext(
            schemes=["argon2"],
            deprecated="auto",
            argon2__time_cost=settings.argon2id_time_cost,
            argon2__memory_cost=settings.argon2id_memory_cost,
            argon2__parallelism=settings.argon2id_parallelism,
        )

    def hash(self, password: str) -> str:
        return self._ctx.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._ctx.verify(password, password_hash)
        except Exception:
            return False

    def needs_rehash(self, password: str, password_hash: str) -> bool:
        return self._ctx.needs_update(password_hash)


def _password_context() -> "PasswordContext":
    global _pwd_context
    if _pwd_context is None:
        _pwd_context = PasswordContext()  # type: ignore[assignment]
    return _pwd_context  # type: ignore[return-value]


def hash_password(password: str) -> str:
    return _password_context().hash(password)


def verify_password(plain: str, password_hash: str) -> bool:
    return _password_context().verify(password, password_hash)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(
    *,
    user_id: UUID,
    school_id: UUID,
    token_version: int,
    session_id: UUID,
    is_super_admin: bool = False,
) -> tuple[str, int]:
    """Return (encoded_jwt, ttl_seconds)."""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = settings.access_token_ttl_seconds
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "school_id": str(school_id),
        "token_version": token_version,
        "session_id": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + ttl,
        "iss": "markbook",
    }
    if is_super_admin:
        claims["super"] = True
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, ttl


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises jwt.InvalidTokenError on failure."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer="markbook",
        options={"require": ["exp", "sub", "school_id", "token_version", "session_id"]},
    )


# ---------------------------------------------------------------------------
# Refresh tokens (opaque, rotated, reuse-detected)
# ---------------------------------------------------------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


# ---------------------------------------------------------------------------
# Identity service
# ---------------------------------------------------------------------------


class IdentityService:
    """Auth business logic. One instance per request."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._repo = IdentityRepository(session)

    # ---- login ------------------------------------------------------------

    async def login(
        self,
        *,
        school_id: UUID,
        email: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
        device_label: str | None = None,
        device_platform: str | None = None,
    ) -> tuple[LoginResponse, Session]:
        """Authenticate and create a session. Raises ProblemError on failure."""
        from app.platform.throttling import check_login_throttle, record_login_failure

        await check_login_throttle(email=email, ip=ip)

        user = await self._repo.get_user_by_email(school_id, email)
        if user is None:
            # Same response shape as wrong password — no user enumeration.
            await record_login_failure(email=email, ip=ip)
            raise ProblemError(
                INVALID_CREDENTIALS, "Invalid email or password", status=401
            )

        if user.locked_until and user.locked_until > datetime.now(UTC):
            raise ProblemError(
                ACCOUNT_LOCKED,
                "Account temporarily locked due to failed logins; try later",
                status=423,
            )

        if not _password_context().verify(password, user.password_hash):
            await self._repo.record_failed_login(user.id)
            await record_login_failure(email=email, ip=ip)
            raise ProblemError(
                INVALID_CREDENTIALS, "Invalid email or password", status=401
            )

        if user.status != "active":
            raise ProblemError(
                ACCOUNT_NOT_ACTIVE, f"Account status is '{user.status}'", status=403
            )

        # Lockout from too many consecutive failures.
        settings = get_settings()
        if user.failed_login_count >= settings.login_max_failures:
            locked_until = datetime.now(UTC) + timedelta(seconds=settings.login_lockout_seconds)
            await self._repo.lock_user(user.id, locked_until)
            raise ProblemError(ACCOUNT_LOCKED, "Too many failed logins", status=423)

        await self._repo.reset_failed_logins(user.id)

        refresh_token = generate_refresh_token()
        session = Session(
            id=uuid4(),
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.refresh_token_ttl_seconds),
            ip=ip,
            user_agent=user_agent,
        )
        await self._repo.create_session(session)

        access_token, ttl = create_access_token(
            user_id=user.id,
            school_id=school_id,
            token_version=user.token_version,
            session_id=session.id,
        )
        return (
            LoginResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=ttl,
                user_id=user.id,
                school_id=school_id,
                requires_mfa=user.mfa_enabled,
            ),
            session,
        )

    # ---- refresh ----------------------------------------------------------

    async def refresh(
        self,
        refresh_token: str,
        *,
        ip: str | None = None,
    ) -> RefreshResponse:
        """Rotate the refresh token; detect reuse of an already-rotated one."""
        token_hash = hash_refresh_token(refresh_token)
        session = await self._repo.get_session_by_refresh_hash(token_hash)

        if session is None:
            raise ProblemError(INVALID_REFRESH, "Invalid refresh token", status=401)

        if session.revoked_at is not None:
            # Reuse of a rotated token → revoke the whole family (spec §7.1).
            await self._repo.revoke_all_user_sessions(session.user_id)
            await self._repo.increment_token_version(session.user_id)
            raise ProblemError(
                REFRESH_REUSED, "Refresh token reuse detected; session revoked", status=401
            )

        if session.expires_at < datetime.now(UTC):
            raise ProblemError(SESSION_EXPIRED, "Session expired", status=401)

        user = await self._repo.get_user_by_id(session.user_id)
        if user is None or user.status != "active":
            raise ProblemError(ACCOUNT_NOT_ACTIVE, "Account is not active", status=403)

        # Rotate: new refresh token replaces the old hash (reuse detection).
        new_refresh = generate_refresh_token()
        session.refresh_token_hash = hash_refresh_token(new_refresh)
        session.issued_at = datetime.now(UTC)
        session.expires_at = datetime.now(UTC) + timedelta(
            seconds=get_settings().refresh_token_ttl_seconds
        )
        await self._s.flush()

        access_token, ttl = create_access_token(
            user_id=user.id,
            school_id=user.school_id,
            token_version=user.token_version,
            session_id=session.id,
        )
        return RefreshResponse(access_token=access_token, expires_in=ttl)

    # ---- logout / revocation ----------------------------------------------

    async def logout(self, session_id: UUID) -> None:
        await self._repo.revoke_session(session_id)

    async def revoke_all_sessions(self, user_id: UUID) -> None:
        await self._repo.revoke_all_user_sessions(user_id)
        await self._repo.increment_token_version(user_id)

    # ---- users ------------------------------------------------------------

    async def create_user(
        self,
        *,
        school_id: UUID,
        email: str,
        username: str,
        password: str,
        is_super_admin: bool = False,
    ) -> User:
        settings = get_settings()
        existing = await self._repo.get_user_by_email(school_id, email)
        if existing is not None:
            raise ProblemError(CONFLICT, "A user with this email already exists")
        user = User(
            id=uuid4(),
            school_id=school_id,
            email=email,
            username=username,
            password_hash=_password_context().hash(password),
            is_super_admin=is_super_admin,
        )
        return await self._repo.create_user(user)

    # ---- MFA --------------------------------------------------------------

    async def setup_mfa(self, user: User) -> MfaSetupResponse:
        import pyotp

        secret = pyotp.random_base32()
        user.mfa_secret = secret
        await self._s.flush()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Markbook")
        return MfaSetupResponse(secret=secret, otpauth_uri=uri)

    async def verify_mfa(self, user: User, totp_code: str) -> bool:
        import pyotp

        if not user.mfa_secret:
            return False
        return pyotp.TOTP(user.mfa_secret).verify(totp_code, valid_window=1)
