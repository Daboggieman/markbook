"""Access repository — SQL queries (Phase 1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.models import Role, RolePermission, UserRole


class AccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- effective permissions -------------------------------------------

    async def effective_permissions(
        self, user_id: UUID
    ) -> list[tuple[str, str]]:
        """All (permission_code, scope_type) pairs granted via the user's roles.

        The broadest scope wins at the engine level; here we return every grant.
        """
        result = await self._s.execute(
            select(RolePermission.permission_code, RolePermission.scope_type)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        return [(row[0], row[1]) for row in result]

    async def role_ids_for_user(self, user_id: UUID) -> list[UUID]:
        result = await self._s.execute(
            select(UserRole.role_id).where(UserRole.user_id == user_id)
        )
        return [row[0] for row in result]

    async def role_by_id(self, role_id: UUID) -> Role | None:
        result = await self._s.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def roles_for_school(self, school_id: UUID) -> list[Role]:
        result = await self._s.execute(
            select(Role).where(Role.school_id == school_id).order_by(Role.name)
        )
        return list(result.scalars().all())

    async def create_role(
        self,
        *,
        school_id: UUID,
        name: str,
        description: str | None,
        is_super_admin: bool = False,
    ) -> Role:
        role = Role(
            school_id=school_id,
            name=name,
            description=description,
            is_super_admin=is_super_admin,
        )
        self._s.add(role)
        await self._s.flush()
        return role

    async def assign_permission_to_role(
        self, role_id: UUID, permission_code: str, scope_type: str
    ) -> None:
        result = await self._s.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_code == permission_code,
            )
        )
        if existing := result.scalar_one_or_none():
            existing.scope_type = scope_type
        else:
            self._s.add(
                RolePermission(
                    role_id=role_id,
                    permission_code=permission_code,
                    scope_type=scope_type,
                )
            )
        await self._s.flush()

    async def assign_role_to_user(
        self, *, user_id: UUID, role_id: UUID, granted_by: UUID | None
    ) -> None:
        self._s.add(UserRole(user_id=user_id, role_id=role_id, granted_by=granted_by))
        await self._s.flush()

    async def is_super_admin(self, user_id: UUID) -> bool:
        result = await self._s.execute(
            select(Role.is_super_admin)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .limit(1)
        )
        return bool(result.scalar_one_or_none())
