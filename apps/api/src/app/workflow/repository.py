"""Workflow repository — SQL for definitions, approval records (Phase 5).

Every query carries an explicit school_id predicate; RLS is the second layer
(02-api-conventions). The assessment row lock lives here too — the transition
engine's `SELECT ... FOR UPDATE` (spec §10) — importing the assessment MODEL
directly (models-only edge, the Phase 2 precedent).

PublishedDocument rows are written by the documents worker, so their queries
live in the documents module, not here.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import Assessment
from app.workflow.models import ApprovalRecord, WorkflowDefinition


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- assessment row lock -------------------------------------------------

    async def lock_assessment(
        self, school_id: uuid.UUID, assessment_id: uuid.UUID
    ) -> Assessment | None:
        """SELECT ... FOR UPDATE — the transition engine's serialization point.

        Concurrent transitions on one assessment queue here; the second one
        sees the first's new state and takes the 409, instead of both
        validating against the stale state and double-transitioning.
        """
        result = await self._s.execute(
            select(Assessment)
            .where(Assessment.school_id == school_id, Assessment.id == assessment_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def set_assessment_state(self, assessment: Assessment, state: str) -> None:
        assessment.workflow_state = state
        assessment.updated_at = datetime.now(UTC)
        await self._s.flush()

    # ---- approval records ----------------------------------------------------

    async def add_approval_record(self, record: ApprovalRecord) -> ApprovalRecord:
        self._s.add(record)
        await self._s.flush()
        return record

    async def latest_record_to_state(
        self, school_id: uuid.UUID, assessment_id: uuid.UUID, to_state: str
    ) -> ApprovalRecord | None:
        """The most recent transition INTO `to_state` — how the engine knows
        who submitted (separation of duties) without adding columns."""
        result = await self._s.execute(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.school_id == school_id,
                ApprovalRecord.assessment_id == assessment_id,
                ApprovalRecord.to_state == to_state,
            )
            .order_by(ApprovalRecord.at.desc(), ApprovalRecord.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_records(
        self, school_id: uuid.UUID, assessment_id: uuid.UUID
    ) -> list[ApprovalRecord]:
        """Full transition history for the assessment, newest first."""
        result = await self._s.execute(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.school_id == school_id,
                ApprovalRecord.assessment_id == assessment_id,
            )
            .order_by(ApprovalRecord.at.desc(), ApprovalRecord.id.desc())
        )
        return list(result.scalars().all())

    # ---- workflow definitions --------------------------------------------------

    async def get_definition(self, school_id: uuid.UUID, name: str) -> WorkflowDefinition | None:
        result = await self._s.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.school_id == school_id,
                WorkflowDefinition.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_definitions(self, school_id: uuid.UUID) -> list[WorkflowDefinition]:
        result = await self._s.execute(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.school_id == school_id)
            .order_by(WorkflowDefinition.name)
        )
        return list(result.scalars().all())

    async def create_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self._s.add(definition)
        await self._s.flush()
        return definition

    # ---- school config (separation of duties toggle) ---------------------------

    async def school_config(self, school_id: uuid.UUID) -> dict:
        """The school row's `config` JSONB (schools are platform-owned; models
        import is the legal edge). Separation of duties is configurable per
        school here, ON when the key is absent (spec §10)."""
        from app.platform.models import School

        result = await self._s.execute(select(School.config).where(School.id == school_id))
        config = result.scalar_one_or_none()
        return config or {}
