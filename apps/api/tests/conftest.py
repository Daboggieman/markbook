"""Shared test fixtures.

DB-backed tests (RLS, repository) need real Postgres — testcontainers starts a
throwaway instance per session (docs/handover_docs/06-testing-notes.md).
Migrations run against a clean database, so `alembic upgrade head` is proven
with every DB test run.
"""

import sys
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

SEED_SCHOOL_A = UUID("00000000-0000-7000-8000-00000000000a")
SEED_SCHOOL_B = UUID("00000000-0000-7000-8000-00000000000b")

if sys.platform == "win32":
    # psycopg async refuses ProactorEventLoop (the Python ≥3.8 Windows default).
    # The pytest_asyncio_loop_factories hook is pytest-asyncio's supported way to
    # control loop creation; on non-Windows platforms no hook is registered and
    # default loop creation is untouched.
    import asyncio

    def pytest_asyncio_loop_factories(
        config: pytest.Config, item: pytest.Item
    ) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
        return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """A real Postgres for the session (docker required)."""
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
    with PostgresContainer("postgres:17-alpine", username="test", password="test") as pg:
        from urllib.parse import urlparse, urlunparse

        raw = pg.get_connection_url().replace("psycopg2", "psycopg")
        # testcontainers omits the password when user == password; restore it.
        parsed = urlparse(raw)
        netloc = f"test:test@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        url = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
        yield url


@pytest.fixture(scope="session")
def migrated_url(pg_url: str) -> str:
    """Run alembic migrations against the throwaway Postgres; yield the URL."""
    import concurrent.futures

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", pg_url)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        pool.submit(command.upgrade, cfg, "head").result()
    return pg_url


@pytest.fixture
async def two_schools(migrated_url: str) -> AsyncIterator[tuple[UUID, UUID]]:
    """Two schools in the migrated baseline DB, for RLS isolation tests."""
    engine = create_async_engine(migrated_url)
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO schools (id, name) VALUES (:id, :name), (:id2, :name2)").bindparams(
                id=SEED_SCHOOL_A,
                name="School A",
                id2=SEED_SCHOOL_B,
                name2="School B",
            )
        )
    await engine.dispose()
    yield SEED_SCHOOL_A, SEED_SCHOOL_B


@pytest.fixture
async def session_factory(pg_url: str) -> AsyncIterator[async_sessionmaker]:
    """A session factory against the raw (unmigrated) throwaway Postgres."""
    engine = create_async_engine(pg_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()
