"""Identity repository — SQL queries (Phase 1)."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import Device, Session, User


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- users ------------------------------------------------------------

    async def get_user_by_email(self, school_id: UUID, email: str) -> User | None:
        result = await self._s.execute(
            select(User).where(User.school_id == school_id, User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self._s.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        self._s.add(user)
        await self._s.flush()
        return user

    async def update_user(self, user: User) -> User:
        self._s.add(user)
        await self._s.flush()
        return user

    async def count_active_super_admins(self, school_id: UUID, exclude_user_id: UUID) -> int:
        """Active super admins in the school other than `exclude_user_id`."""
        result = await self._s.execute(
            select(User).where(
                User.school_id == school_id,
                User.is_super_admin.is_(True),
                User.status == "active",
                User.id != exclude_user_id,
            )
        )
        return len(result.scalars().all())

    async def increment_token_version(self, user_id: UUID) -> None:
        await self._s.execute(
            update(User).where(User.id == user_id).values(token_version=User.token_version + 1)
        )

    async def record_failed_login(self, user_id: UUID) -> None:
        await self._s.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_login_count=User.failed_login_count + 1)
        )

    async def reset_failed_logins(self, user_id: UUID) -> None:
        await self._s.execute(
            update(User).where(User.id == user_id).values(failed_login_count=0, locked_until=None)
        )

    async def lock_user(self, user_id: UUID, locked_until) -> None:
        await self._s.execute(
            update(User).where(User.id == user_id).values(locked_until=locked_until)
        )

    # ---- sessions ---------------------------------------------------------

    async def create_session(self, session: Session) -> Session:
        self._s.add(session)
        await self._s.flush()
        return session

    async def get_session_by_refresh_hash(self, refresh_token_hash: bytes) -> Session | None:
        result = await self._s.execute(
            select(Session).where(Session.refresh_token_hash == refresh_token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, session_id: UUID) -> None:
        from datetime import UTC, datetime

        await self._s.execute(
            update(Session).where(Session.id == session_id).values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all_user_sessions(self, user_id: UUID) -> None:
        from datetime import UTC, datetime

        await self._s.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    # ---- devices ----------------------------------------------------------

    async def create_device(self, device: Device) -> Device:
        self._s.add(device)
        await self._s.flush()
        return device

    async def get_device_by_id(self, device_id: UUID) -> Device | None:
        result = await self._s.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def update_device_last_seen(self, device_id: UUID) -> None:
        from datetime import UTC, datetime

        await self._s.execute(
            update(Device).where(Device.id == device_id).values(last_seen_at=datetime.now(UTC))
        )

    async def revoke_device(self, device_id: UUID) -> None:
        from datetime import UTC, datetime

        await self._s.execute(
            update(Device).where(Device.id == device_id).values(revoked_at=datetime.now(UTC))
        )
