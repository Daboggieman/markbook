"""Database session with tenant context (spec §5).

Every request-scoped session sets `SET LOCAL app.school_id` at transaction
start, derived from the authenticated user — never from client input. RLS
policies on every tenant table compare against that setting, so a query that
forgets its WHERE clause still cannot cross tenants.

The application DB role is not a superuser and does not bypass RLS.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.platform.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            echo=settings.db_echo,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def _quote_literal(value: str) -> str:
    """Quote a string as a SQL string literal, safely.

    school_id is always a UUID derived server-side, but we quote defensively
    rather than trusting any caller.
    """
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


async def set_tenant_context(session: AsyncSession, school_id: str) -> None:
    """Set the RLS tenant context for the current transaction.

    Must be called inside the transaction (before any query). `set_config`
    with `is_local = true` is transaction-scoped (the SET LOCAL equivalent):
    it disappears at commit/rollback, so a pooled connection never leaks a
    tenant setting. SET LOCAL itself cannot take bind parameters, which is
    why set_config is used instead.
    """
    await session.execute(
        text("SELECT set_config('app.school_id', :school_id, true)").bindparams(school_id=school_id)
    )


@asynccontextmanager
async def tenant_session(school_id: str) -> AsyncIterator[AsyncSession]:
    """Request/worker-scoped session with the tenant context applied.

    Usage: `async with tenant_session(school_id) as session: ...`
    """
    async with get_sessionmaker()() as session:
        async with session.begin():
            await set_tenant_context(session, school_id)
            yield session


async def get_db(school_id: str = "-") -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. In Phase 1 the auth dependency supplies school_id;
    until then it defaults to the placeholder and routes that need tenancy
    declare their own tenant_session usage."""
    async with get_sessionmaker()() as session:
        async with session.begin():
            if school_id != "-":
                await set_tenant_context(session, school_id)
            yield session


async def check_db_ready() -> dict[str, Any]:
    """Health helper: SELECT 1."""
    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT 1"))
        return {"database": "ok" if result.scalar() == 1 else "error"}
