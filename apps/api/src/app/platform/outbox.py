"""Transactional outbox (spec §12, decision D5).

Domain events are inserted into `outbox_events` in the same transaction as
the state change that produced them — the guarantee a broker would otherwise
give us, without the broker. A worker dispatcher polls with
FOR UPDATE SKIP LOCKED, delivers to in-process handlers, marks dispatched.
The dispatcher is the seam where a broker plugs in later.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

# Topics at launch (spec §12). Do not invent topics ad hoc; add here.
TOPIC_ASSESSMENT_STATE_CHANGED = "assessment.state_changed"
TOPIC_RESULTS_PUBLISHED = "results.published"
TOPIC_SCORE_CHANGED = "score.changed"


async def enqueue_outbox_event(
    session: Any,  # AsyncSession; loosely typed so tests can pass a wrapper
    *,
    school_id: str,
    topic: str,
    payload: dict[str, Any],
) -> None:
    """Insert an outbox event in the caller's transaction.

    The caller must be inside the same transaction as the state change — that
    is the whole point of the transactional outbox.
    """
    await session.execute(
        text(
            """
            INSERT INTO outbox_events (id, school_id, topic, payload, created_at)
            VALUES (:id, :school_id, :topic, CAST(:payload AS JSONB), :created_at)
            """
        ).bindparams(
            id=uuid.uuid4(),
            school_id=uuid.UUID(school_id),
            topic=topic,
            payload=json.dumps(payload, default=str),
            created_at=datetime.now(UTC),
        )
    )
