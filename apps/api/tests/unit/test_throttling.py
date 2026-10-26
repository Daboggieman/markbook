"""Login throttling tests (Phase 1 — spec §7.1).

Redis-backed counters with exponential backoff. The real Redis is swapped for
an in-memory fake; the contract under test is the counter logic, not Redis.
"""

import pytest

from app.platform import throttling
from app.platform.errors import RATE_LIMITED, ProblemError


class FakeRedis:
    """Minimal async stand-in for the redis client surface throttling uses."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def incr(self, key: str) -> int:
        value = int(self.data.get(key, "0")) + 1
        self.data[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.data.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(throttling, "get_redis", lambda: fake)
    return fake


async def test_check_passes_with_no_failures(fake_redis: FakeRedis) -> None:
    await throttling.check_login_throttle(email="a@x.co", ip="1.2.3.4")


async def test_check_raises_at_email_limit(fake_redis) -> None:
    settings = throttling.get_settings()
    for _ in range(settings.login_max_failures):
        await throttling.record_login_failure(email="a@x.co", ip=None)
    with pytest.raises(ProblemError) as exc_info:
        await throttling.check_login_throttle(email="a@x.co", ip="1.2.3.4")
    assert exc_info.value.code == RATE_LIMITED
    assert exc_info.value.status == 429


async def test_record_failure_increments_email_and_ip_counters(fake_redis) -> None:
    await throttling.record_login_failure(email="a@x.co", ip="1.2.3.4")
    assert fake_redis.data[throttling._email_key("a@x.co")] == "1"
    assert fake_redis.data[throttling._ip_key("1.2.3.4")] == "1"


async def test_record_login_success_resets_counters(fake_redis) -> None:
    await throttling.record_login_failure(email="a@x.co", ip="1.2.3.4")
    await throttling.record_login_success(email="a@x.co", ip="1.2.3.4")
    assert fake_redis.data.get(throttling._email_key("a@x.co")) is None
    assert fake_redis.data.get(throttling._ip_key("1.2.3.4")) is None


async def test_check_passes_when_ip_absent(fake_redis) -> None:
    """No IP → only the email counter is consulted; no crash on None."""
    await throttling.check_login_throttle(email="a@x.co", ip=None)
