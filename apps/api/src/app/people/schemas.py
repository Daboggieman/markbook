"""People schemas — Pydantic request/response models (Phase 2)."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


class StudentCreate(BaseModel):
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    middle_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    dob: date | None = None
    sex: Annotated[str, Field(pattern="^(m|f|M|F)$")] | None = None
    admission_no: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    system_id: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    guardian_ids: list[UUID] = []
    allow_duplicate: bool = False


class StudentUpdate(BaseModel):
    first_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    middle_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    dob: date | None = None
    sex: Annotated[str, Field(pattern="^(m|f|M|F)$")] | None = None
    admission_no: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    system_id: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    version: int  # optimistic concurrency (02-api-conventions.md)


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    system_id: str | None
    admission_no: str | None
    first_name: str
    middle_name: str | None
    last_name: str
    dob: date | None
    sex: str | None
    status: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class DuplicateCandidate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    first_name: str
    last_name: str
    dob: date | None
    admission_no: str | None
    similarity: float


class DuplicateCheckRequest(BaseModel):
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    exclude_student_id: UUID | None = None


class DuplicateCheckResponse(BaseModel):
    candidates: list[DuplicateCandidate]


# ---------------------------------------------------------------------------
# Guardians
# ---------------------------------------------------------------------------


class GuardianCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    phone: Annotated[str, Field(min_length=5, max_length=30)] | None = None
    email: Annotated[str, Field(max_length=255)] | None = None
    address: Annotated[str, Field(max_length=500)] | None = None


class GuardianResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    phone: str | None
    email: str | None
    address: str | None
    created_at: datetime
    updated_at: datetime
    version: int


class GuardianLinkRequest(BaseModel):
    guardian_id: UUID
    relationship: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    is_primary: bool = False
