"""Login throttling — Redis-backed counters with exponential backoff (spec §7.1).

Counters live per (email, IP) and per IP. Each failure increments the counter;
a success resets both. The module reuses the platform Redis client from
idempotency so there is exactly one connection pool per process.
"""

from app.platform.config import get_settings
from app.platform.errors import RATE_LIMITED, ProblemError
from app.platform.idempotency import get_redis

_EMAIL_PREFIX = "throttle:login:email"
_IP_PREFIX = "throttle:login:ip"


def _email_key(email: str) -> str:
    return f"{_EMAIL_PREFIX}:{email.lower()}"


def _ip_key(ip: str) -> str:
    return f"{_IP_PREFIX}:{ip}"


async def check_login_throttle(*, email: str, ip: str | None) -> None:
    """Reject the attempt up front if either counter is at the limit."""
    settings = get_settings()
    redis = get_redis()
    window = settings.login_throttle_window_seconds

    failures = await redis.get(_email_key(email))
    if failures is not None and int(failures) >= settings.login_max_failures:
        raise ProblemError(
            RATE_LIMITED,
            "Too many failed login attempts; try again later",
            headers={"Retry-After": str(window)},
        )

    if ip:
        ip_failures = await redis.get(_ip_key(ip))
        ip_limit = settings.login_max_failures * 10  # IP-wide limit is looser
        if ip_failures is not None and int(ip_failures) >= ip_limit:
            raise ProblemError(
                RATE_LIMITED,
                "Too many failed logins from this address",
                headers={"Retry-After": str(window)},
            )


async def record_login_failure(*, email: str, ip: str | None) -> None:
    """Increment both counters with exponential-backoff windows."""
    settings = get_settings()
    redis = get_redis()

    failures = await redis.incr(_email_key(email))
    # Exponential backoff: window doubles with each failure past the limit.
    ttl = settings.login_throttle_window_seconds * (2 ** max(0, failures - settings.login_max_failures))
    if failures == 1:
        await redis.expire(_email_key(email), ttl)

    if ip:
        ip_failures = await redis.incr(_ip_key(ip))
        if ip_failures == 1:
            await redis.expire(_ip_key(ip), settings.login_throttle_window_seconds)


async def record_login_success(*, email: str, ip: str | None) -> None:
    """Reset both counters after a successful login."""
    redis = get_redis()
    await redis.delete(_email_key(email))
    if ip:
        await redis.delete(_ip_key(ip))
