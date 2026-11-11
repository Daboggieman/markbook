"""Academic schemas — Pydantic request/response models (Phase 2)."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Label = Annotated[str, Field(min_length=1, max_length=100)]


# ---------------------------------------------------------------------------
# Academic sessions / terms
# ---------------------------------------------------------------------------


class AcademicSessionCreate(BaseModel):
    name: Annotated[str, Field(min_length=3, max_length=100)]  # e.g. "2025/2026"
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False


class AcademicSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    start_date: date | None
    end_date: date | None
    is_current: bool
    created_at: datetime
    updated_at: datetime
    version: int


class TermCreate(BaseModel):
    session_id: UUID
    name: Label
    ordinal: Annotated[int, Field(ge=1, le=10)]
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False


class TermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    session_id: UUID
    name: str
    ordinal: int
    start_date: date | None
    end_date: date | None
    is_current: bool
    created_at: datetime
    updated_at: datetime
    version: int


# ---------------------------------------------------------------------------
# Levels / classes / sections / subjects
# ---------------------------------------------------------------------------


class EducationalLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    ordinal: int
    created_at: datetime


class ClassCreate(BaseModel):
    level_id: UUID
    name: Label
    ordinal: int | None = None


class ClassResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    level_id: UUID
    name: str
    ordinal: int | None
    created_at: datetime


class SectionCreate(BaseModel):
    class_id: UUID
    name: Label


class SectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    class_id: UUID
    name: str
    created_at: datetime


class SubjectCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    code: Annotated[str, Field(min_length=1, max_length=20)] | None = None


class SubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    code: str | None
    created_at: datetime


class ClassSubjectCreate(BaseModel):
    class_id: UUID
    subject_id: UUID
    is_optional: bool = False


class ClassSubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    class_id: UUID
    subject_id: UUID
    is_optional: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Enrolments
# ---------------------------------------------------------------------------


class EnrolmentCreate(BaseModel):
    student_id: UUID
    session_id: UUID
    class_id: UUID
    section_id: UUID | None = None


class EnrolmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    student_id: UUID
    session_id: UUID
    class_id: UUID
    section_id: UUID | None
    status: str
    started_on: date | None
    ended_on: date | None
    created_at: datetime
    updated_at: datetime
    version: int


# ---------------------------------------------------------------------------
# Teacher assignments
# ---------------------------------------------------------------------------


class TeacherAssignmentCreate(BaseModel):
    teacher_user_id: UUID
    session_id: UUID
    class_id: UUID
    section_id: UUID | None = None
    subject_id: UUID | None = None
    role: Annotated[str, Field(pattern="^(subject|form)$")] = "subject"


class TeacherAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    teacher_user_id: UUID
    session_id: UUID
    class_id: UUID
    section_id: UUID | None
    subject_id: UUID | None
    role: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------


class PromotionDecision(BaseModel):
    student_id: UUID
    # promote: next class in the school's class sequence (override with to_class_id)
    # repeat: same class again; graduate: close out, no new enrolment
    decision: Annotated[str, Field(pattern="^(promote|repeat|graduate)$")]
    to_class_id: UUID | None = None
    to_section_id: UUID | None = None


class PromotionRunRequest(BaseModel):
    from_session_id: UUID
    to_session_id: UUID
    decisions: Annotated[list[PromotionDecision], Field(min_length=1, max_length=500)]


class PromotionRunOutcome(BaseModel):
    student_id: UUID
    decision: str
    from_enrolment_id: UUID | None  # None when the student had no live enrolment
    to_enrolment_id: UUID | None
    to_class_id: UUID | None
    note: str | None = None


class PromotionRunResponse(BaseModel):
    outcomes: list[PromotionRunOutcome]
