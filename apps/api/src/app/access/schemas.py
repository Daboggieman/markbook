"""Access schemas — Pydantic request/response models (Phase 1)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=100)]
    description: str | None = None
    permission_ids: list[tuple[str, str]] = []  # (permission_code, scope_type)


class RoleUpdate(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    description: str | None = None


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    is_super_admin: bool
    description: str | None
    created_at: datetime


class RolePermissionAssign(BaseModel):
    permission_codes: list[str]
    scope_type: Annotated[
        str, Field(pattern="^(school|assigned|own)$", default="school")
    ]


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str | None


# ---------------------------------------------------------------------------
# Effective permissions (returned with user profile)
# ---------------------------------------------------------------------------


class EffectivePermission(BaseModel):
    code: str
    scope_type: str  # school | assigned | own


class RoleWithPermissions(RoleResponse):
    permissions: list[EffectivePermission] = []


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    school_id: UUID
    email: str
    username: str
    is_super_admin: bool
    roles: list[RoleWithPermissions] = []
    effective_permissions: list[EffectivePermission] = []
