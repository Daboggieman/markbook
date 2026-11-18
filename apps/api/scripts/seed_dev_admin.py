"""Create the first dev Super Admin (runbook helper).

Usage (from apps/api):
    .venv/Scripts/python.exe scripts/seed_dev_admin.py [email] [password]

Defaults: admin@seed.school / Dev-Admin-2026
Uses the app role (MARKBOOK_DATABASE_URL) with tenant context set — the same
write path the API itself uses — and attaches the seeded Super Admin role
(migration 0002 grants it every permission at school scope; authorize() has no
super-admin bypass, so the junction row is what actually empowers the user).
Idempotent: exits 0 if the email already exists.
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from sqlalchemy import text  # noqa: E402

from app.identity.repository import IdentityRepository  # noqa: E402
from app.identity.service import IdentityService  # noqa: E402
from app.platform.db import (  # noqa: E402
    get_engine,
    get_sessionmaker,
    set_tenant_context,
)

SCHOOL_ID = "00000000-0000-7000-8000-000000000001"  # 'Seed School' from 0001
SUPER_ADMIN_ROLE_ID = "00000000-0000-7000-8000-000000000001"  # from 0002


async def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else "admin@seed.school"
    password = sys.argv[2] if len(sys.argv) > 2 else "Dev-Admin-2026"

    engine = get_engine()
    maker = get_sessionmaker()
    async with maker() as session:
        await set_tenant_context(session, SCHOOL_ID)
        service = IdentityService(session)
        repo = IdentityRepository(session)

        existing = await repo.get_user_by_email(uuid.UUID(SCHOOL_ID), email)
        if existing is not None:
            print(f"user {email} already exists — nothing to do")
            await engine.dispose()
            return 0

        user = await service.create_user(
            school_id=uuid.UUID(SCHOOL_ID),
            email=email,
            username=email.split("@")[0],
            password=password,
            is_super_admin=True,
        )
        # authorize() reads grants from user_roles only — attach the role.
        await session.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"
                " ON CONFLICT DO NOTHING"
            ),
            {"u": str(user.id), "r": SUPER_ADMIN_ROLE_ID},
        )
        await session.commit()
        print(f"created super admin {email} (user_id={user.id})")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
