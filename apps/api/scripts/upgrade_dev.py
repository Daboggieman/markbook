"""Upgrade the dev database to head (runbook helper).

Usage (from apps/api): .venv/Scripts/python.exe scripts/upgrade_dev.py

Uses MARKBOOK_DATABASE_MIGRATION_URL (the markbook_ops role) from .env —
migrations never run as the app role (spec §5). env.py's explicit-URL rule
makes the set_main_option here authoritative.
"""

import os
from pathlib import Path

from alembic import command
from alembic import config as alembic_config


def _migration_url() -> str:
    url = os.environ.get("MARKBOOK_DATABASE_MIGRATION_URL")
    if url:
        return url
    env = Path(__file__).parents[1] / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.partition("=")[0].strip() == (
            "MARKBOOK_DATABASE_MIGRATION_URL"
        ):
            return line.partition("=")[2].strip()
    raise SystemExit("MARKBOOK_DATABASE_MIGRATION_URL not set and not found in .env")


def main() -> None:
    cfg = alembic_config.Config()
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _migration_url())
    command.upgrade(cfg, "head")
    print("upgraded to head")


if __name__ == "__main__":
    main()
