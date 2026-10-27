"""Alembic env.py — loaded by `alembic upgrade head` and `alembic revision`.

Sets up the async SQLAlchemy engine and runs migrations with the ops role,
not the app role.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path so `from app.platform.models import Base` works.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.platform.config import get_settings
from app.platform.models import Base

config = context.config

# Alembic IniConfig object; set database URL from our settings.
# The migration role (not the app role) is used here.
# An explicit URL (cfg.set_main_option from CLI/scripts/tests) wins; otherwise
# DATABASE_URL in the environment or .env file is used.
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection, just SQL output)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run async migrations with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (real DB connection)."""
    loop_kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        # psycopg async refuses ProactorEventLoop, the Windows default since
        # Python 3.8; pin the selector loop wherever this runs (host shell,
        # tests' worker threads).
        loop_kwargs["loop_factory"] = asyncio.SelectorEventLoop
    asyncio.run(run_async_migrations(), **loop_kwargs)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
