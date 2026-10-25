"""Access module — SQLAlchemy models (Phase 1)."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.models import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("ix_roles_school_id", "school_id"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    school_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", lazy="noload", cascade="all, delete-orphan"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="role", lazy="noload", cascade="all, delete-orphan"
    )


class Permission(Base):
    """Global catalogue, seeded at migration time. Rows are never mutated."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission", lazy="noload"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        String(100), ForeignKey("permissions.code"), primary_key=True
    )
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, default="school")

    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")


class UserRole(Base):
    """Junction: user belongs to role."""

    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
