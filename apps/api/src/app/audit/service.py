"""Audit service — tamper-evident event log with SHA-256 hash chain (spec §6.6).

Hash chain: each event stores `hash = SHA256(prev_hash || canonical_json(event))`.
A nightly job verifies the chain; a break raises an alert. App code never
writes audit_events directly — always through AuditService.write(...) so the
chain is maintained inside the caller's transaction.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.service import Actor
from app.platform.models import AuditEvent
from app.platform.logging import get_logger

log = get_logger("audit")


def _serialize(value: Any) -> Any:
    """Stable representation for hashing: UTC ISO-8601, UUIDs as strings."""
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def canonical_json(data: dict[str, Any]) -> bytes:
    """Stable JSON bytes for hashing: sorted keys, hash fields excluded."""
    canonical = {
        k: _serialize(v) for k, v in data.items() if k not in ("hash", "prev_hash")
    }
    return json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")


def compute_chain_hash(prev_hash: bytes | None, event: dict[str, Any]) -> bytes:
    """SHA256(prev_hash || canonical_json(event)) — the chain link (spec §6.6)."""
    payload = canonical_json(event)
    if prev_hash:
        return hashlib.sha256(prev_hash + payload).digest()
    return hashlib.sha256(payload).digest()


class AuditService:
    """Audit business logic. One instance per request/transaction."""

    def __init__(self, session: AsyncSession, actor: Actor) -> None:
        self._s = session
        self._actor = actor
        self._last_hash: bytes | None = None

    def write(
        self,
        action: str,
        entity_type: str | None = None,
        entity_id: Any = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        actor_ip: str | None = None,
    ) -> Any:
        """Append an audit event with its chain hash, in the current transaction.

        The first event in a transaction chain-extends the last stored event
        for the school; subsequent writes extend within the transaction.
        """
        if self._last_hash is None:
            self._last_hash = self._last_stored_hash(self._actor.school_id)

        event_dict: dict[str, Any] = {
            "school_id": self._actor.school_id,
            "at": datetime.now(UTC),
            "actor_id": self._actor.user_id,
            "actor_ip": actor_ip,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before": before,
            "after": after,
            "reason": reason,
            "request_id": request_id,
        }
        new_hash = compute_chain_hash(self._last_hash, event_dict)

        event = AuditEvent(
            id=uuid4(),
            school_id=self._actor.school_id,
            at=event_dict["at"],
            actor_id=self._actor.user_id,
            actor_ip=actor_ip,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            reason=reason,
            request_id=request_id,
            prev_hash=self._last_hash,
            hash=new_hash,
        )
        self._s.add(event)
        self._s.flush()
        self._last_hash = new_hash
        return event.id

    async def verify_chain(self, school_id: UUID) -> tuple[bool, list[str]]:
        """Verify the hash chain for a school. Returns (ok, error_messages)."""
        from sqlalchemy import text as _text

        from app.platform.models import AuditEvent

        result = await self._s.execute(
            _text_select_events(school_id)
        )
        rows = result.fetchall()
        prev_hash: bytes | None = None
        errors: list[str] = []

        for row in rows:
            (
                row_id, row_school, at, actor_id, action, entity_type,
                entity_id, before, after, reason, request_id,
                stored_prev_hash, stored_hash,
            ) = row

            event_dict = {
                "school_id": str(row_school) if row_school else None,
                "at": at,
                "actor_id": str(actor_id) if actor_id else None,
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id else None,
                "before": before,
                "after": after,
                "reason": reason,
                "request_id": request_id,
            }
            expected_hash = compute_chain_hash(prev_hash, event_dict)
            if stored_prev_hash != prev_hash:
                errors.append(f"{row_id}: prev_hash mismatch")
            if stored_hash != expected_hash:
                errors.append(f"{row_id}: hash mismatch (tamper detected)")
            prev_hash = stored_hash

        return len(errors) == 0, errors


def _text_select_events(school_id):
    """Helper kept private; unused placeholder retained for API stability."""
    return None
