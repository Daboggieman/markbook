"""Identity schemas — Pydantic request/response models (Phase 1)."""
# ruff: noqa: S105  # "bearer"/"basic" token_type literals are not secrets.

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: Annotated[str, Field(min_length=1, max_length=254)]
    password: Annotated[str, Field(min_length=1)]
    device_label: str | None = None
    device_platform: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_id: UUID
    school_id: UUID
    requires_mfa: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int
    token_type: str = "bearer"


class MfaVerifyRequest(BaseModel):
    totp_code: Annotated[str, Field(pattern=r"^\d{6}$")]


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class ReauthRequest(BaseModel):
    password: Annotated[str, Field(min_length=1)]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    email: EmailStr
    username: Annotated[str, Field(min_length=2, max_length=50)]
    password: Annotated[str, Field(min_length=8, max_length=128)]  # hashed; never plaintext in resp
    role_ids: list[UUID] = []
    is_super_admin: bool = False


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: Annotated[str, Field(min_length=2, max_length=50)] | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended|deactivated)$")
    mfa_enabled: bool | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    email: str
    username: str
    is_super_admin: bool
    status: str
    mfa_enabled: bool
    failed_login_count: int
    locked_until: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    is_super_admin: bool
    status: str
    mfa_enabled: bool
    created_at: datetime


class UserPasswordChange(BaseModel):
    current_password: Annotated[str, Field(min_length=1)]
    new_password: Annotated[str, Field(min_length=8, max_length=128)]


# ---------------------------------------------------------------------------
# Sessions / Devices
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID | None
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    ip: str | None
    user_agent: str | None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str | None
    platform: str | None
    registered_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
