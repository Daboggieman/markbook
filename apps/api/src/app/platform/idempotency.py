"""Idempotency helpers (spec §2.5, §8).

All POSTs that create or transition accept an Idempotency-Key. Keys are stored
in Redis for 24 h with the stored response, so a retry returns the original
response instead of re-applying. Sync operations additionally get a durable
record (sync_operations, Phase 7).
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request

from app.platform.config import get_settings
from app.platform.errors import VALIDATION_ERROR, ProblemError

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None


def require_idempotency_key(request: Request) -> str:
    """Extract and validate the Idempotency-Key header."""
    key = request.headers.get("Idempotency-Key")
    if not key:
        raise ProblemError(
            VALIDATION_ERROR,
            "Idempotency-Key header is required for this operation",
        )
    return key


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _redis_key(key: str) -> str:
    return f"idem:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _parse_stored(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def idempotent_response(
    key: str,
    payload: Any,
    handler: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
):
    """Run `handler` once per idempotency key; replays return the stored response.

    `handler` is an async callable taking no args, returning (status_code, body_dict).
    A reused key with a different body is rejected rather than silently replayed.
    """
    r = get_redis()
    settings = get_settings()
    redis_key = _redis_key(key)
    fingerprint = _fingerprint(payload)

    stored_raw = await r.get(_redis_key(key))
    if stored_raw is not None:
        stored = _parse_stored(stored_raw)
        if stored is not None:
            if stored.get("fingerprint") != fingerprint:
                raise ProblemError(
                    VALIDATION_ERROR,
                    "Idempotency-Key was already used with a different request body",
                    status=422,
                )
            return int(stored["status"]), stored["body"]

    status, body = await handler()
    await r.set(
        redis_key,
        json.dumps({"fingerprint": fingerprint, "status": status, "body": body}, default=str),
        ex=settings.idempotency_key_ttl_seconds,
    )
    return status, body
