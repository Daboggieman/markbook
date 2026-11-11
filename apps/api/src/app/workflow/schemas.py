"""Workflow schemas — Pydantic request/response models (Phase 5).

Transition requests carry only `reason`; the state graph itself is code
(spec §10). Stage definitions validate shape here, but the authority on
what states/permissions are legal is the workflow service — pydantic
carries shape, the service validates semantics.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StageDef(BaseModel):
    """One configurable stage of a school's workflow: the target state and
    the permission required to reach it. Mandatory invariants are NOT
    configurable — they live in the transition engine."""

    state: Annotated[str, Field(min_length=1, max_length=50)]
    requires: Annotated[str, Field(min_length=1, max_length=100)]


class WorkflowDefinitionCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    stages: Annotated[list[StageDef], Field(min_length=1)]


class WorkflowDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    stages: list[dict[str, str]]
    created_at: datetime


class TransitionRequest(BaseModel):
    """Body for submit/start-review/return/approve/lock/publish/correct.

    `reason` is REQUIRED for return and correct (spec §10) — enforced by the
    service so the rule sits beside the transition table, not in two places.
    """

    reason: Annotated[str | None, Field(max_length=2000)] = None

    @model_validator(mode="after")
    def _strip_reason(self) -> "TransitionRequest":
        if self.reason is not None:
            self.reason = self.reason.strip()
            if self.reason == "":
                self.reason = None
        return self


class TransitionResponse(BaseModel):
    """The assessment's new state plus the approval record written."""

    model_config = ConfigDict(from_attributes=True)

    assessment_id: UUID
    workflow_state: str
    record_id: UUID
    from_state: str
    to_state: str
    actor_id: UUID | None
    at: datetime
