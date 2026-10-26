"""Token helpers — pure JWT and refresh-token primitives (Phase 1).

Lives apart from the DB-backed identity service so other modules can decode
access tokens without dragging identity's repository into their import graph
(the import-linter no-cross-repository contract is chain-sensitive). This
module imports platform only.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import jwt

from app.platform.config import get_settings


def create_access_token(
    *,
    user_id: uuid.UUID,
    school_id: uuid.UUID,
    token_version: int,
    session_id: uuid.UUID,
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


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()
