"""Assessment schemas — Pydantic request/response models (Phase 3).

Scores are `Decimal` end to end (rule 6 — never float): the column is
NUMERIC(6,2), the engine uses Decimal, and these schemas parse JSON numbers
into Decimal so no float ever touches a score.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ScoreStatus = Literal["entered", "absent", "exempt", "missing"]
TemplateVersionStatus = Literal["draft", "active", "retired"]

# ---------------------------------------------------------------------------
# Templates and versions
# ---------------------------------------------------------------------------


class ComponentDef(BaseModel):
    """One score component inside a template version definition (spec §6.4)."""

    key: Annotated[str, Field(min_length=1, max_length=100)]
    label: Annotated[str, Field(min_length=1, max_length=100)]
    max_score: Annotated[Decimal, Field(gt=0)]
    weight: Annotated[Decimal, Field(gt=0)]
    required: bool = True


class TemplateDefinition(BaseModel):
    components: Annotated[list[ComponentDef], Field(min_length=1)]

    def component_keys(self) -> list[str]:
        return [c.key for c in self.components]


class AssessmentTemplateCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    definition: TemplateDefinition


class TemplateVersionCreate(BaseModel):
    definition: TemplateDefinition


class TemplateVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    version_no: int
    status: TemplateVersionStatus
    definition: dict[str, Any]
    created_at: datetime


class AssessmentTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    version: int


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------


class AssessmentCreate(BaseModel):
    term_id: UUID
    class_id: UUID
    section_id: UUID | None = None
    subject_id: UUID
    template_version_id: UUID


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    term_id: UUID
    class_id: UUID
    section_id: UUID | None
    subject_id: UUID
    template_version_id: UUID
    workflow_state: str
    version: int


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------


class ScoreRowInput(BaseModel):
    """One cell of a batch upsert. `base_version` carries the caller's last
    seen row version; None means "no row yet" (first entry)."""

    subject_enrolment_id: UUID
    component_key: Annotated[str, Field(min_length=1, max_length=100)]
    status: ScoreStatus
    value: Decimal | None = None
    base_version: int | None = None


class BatchScoreUpsert(BaseModel):
    rows: Annotated[list[ScoreRowInput], Field(min_length=1)]


class ScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    subject_enrolment_id: UUID
    component_key: str
    status: ScoreStatus
    value: Decimal | None
    version: int


class ScoreChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    score_id: UUID
    old_status: ScoreStatus | None
    old_value: Decimal | None
    new_status: ScoreStatus | None
    new_value: Decimal | None
    reason: str | None
    changed_at: datetime
    source: str


# ---------------------------------------------------------------------------
# Score sheet & bulk import
# ---------------------------------------------------------------------------


class ScoreCell(BaseModel):
    """One entered cell on the sheet (from the scores table)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ScoreStatus
    value: Decimal | None
    version: int


class SheetRow(BaseModel):
    """One student on the score sheet: roster identity plus any scores."""

    subject_enrolment_id: UUID
    student_id: UUID
    student_name: str
    admission_no: str
    scores: dict[str, ScoreCell] = {}


class ScoreSheetResponse(BaseModel):
    assessment_id: UUID
    workflow_state: str
    components: list[ComponentDef]
    rows: list[SheetRow]


class ImportScoresRequest(BaseModel):
    """CSV text: header `subject_enrolment_id,component_key,status,value`
    (value only on entered rows). The worker validates row by row."""

    csv: Annotated[str, Field(min_length=1)]


class JobResponse(BaseModel):
    """Job status. In Phase 3 assessment is the only job producer, so the
    route lives on this module's router; it moves to a shared home when a
    second producer appears (jobs belong to no module — platform table)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
