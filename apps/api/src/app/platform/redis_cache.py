"""Redis cache for token_version — short-TTL revocation check (spec §7.1).

A revocation bumps `users.token_version`; outstanding JWTs carry the old
version and are rejected within the cache TTL (30 s). On a cache miss the DB
is read and the cache populated. Redis outages fail open (None) so the JWT's
own claims remain the source of truth until the DB check runs.
"""

from uuid import UUID

from app.platform.idempotency import get_redis
from app.platform.logging import get_logger

log = get_logger("auth-cache")

_TOKEN_VERSION_CACHE_TTL = 30  # seconds


def _token_version_key(user_id: UUID) -> str:
    return f"auth:token_version:{user_id}"


async def get_cached_token_version(user_id: UUID) -> int | None:
    """Current token_version for the user, cached ~30 s (spec §7.1).

    Returns None when the user is unknown or Redis is unavailable — callers
    then fall back to trusting the JWT's embedded version.
    """
    from app.platform.db import get_sessionmaker

    redis = get_redis()
    key = _token_version_key(user_id)

    try:
        cached = await redis.get(key)
        if cached is not None:
            return int(cached)
    except Exception as exc:  # Redis down → degrade gracefully
        log.warning("token_version_cache_error", error=str(exc))
        return None

    # Cache miss: load from DB and populate.
    from sqlalchemy import text

    maker = get_sessionmaker()
    async with maker() as session:
        result = await session.execute(
            text("SELECT token_version FROM users WHERE id = :uid").bindparams(uid=user_id)
        )
        row = result.first()
    if row is None:
        return None
    version = int(row[0])
    try:
        await redis.set(_token_version_key(user_id), version, ex=_TOKEN_VERSION_CACHE_TTL)
    except Exception as exc:
        log.warning("token_version_cache_write_error", error=str(exc))
    return version


async def bump_token_version_cache(user_id: UUID, version: int) -> None:
    """Update the cached version immediately after a revocation bump."""
    try:
        redis = get_redis()
        await redis.set(_token_version_key(user_id), version, ex=_TOKEN_VERSION_CACHE_TTL)
    except Exception as exc:
        log.warning("token_version_cache_bump_error", error=str(exc))
