"""Audit hash-chain primitive tests (Phase 1 — spec §6.6).

Pure tests of canonical JSON stability and chain-link computation; the
write→verify round-trip against real Postgres lives in the DB tests
(tests/security/test_audit_chain_db.py).
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.audit.service import canonical_json, compute_chain_hash


def test_canonical_json_is_deterministic() -> None:
    a = canonical_json({"action": "login", "entity_type": "session"})
    b = canonical_json({"entity_type": "session", "action": "login"})
    assert a == b


def test_canonical_json_sorts_keys() -> None:
    data = json.loads(canonical_json({"b": 1, "a": 2}))
    assert list(data.keys()) == ["a", "b"]


def test_canonical_json_excludes_hash_fields() -> None:
    """hash/prev_hash are excluded so a stored hash can't feed its own computation."""
    with_hash = canonical_json({"action": "x", "hash": "aa", "prev_hash": "bb"})
    without = canonical_json({"action": "x"})
    assert with_hash == without


def test_canonical_json_serializes_domain_types() -> None:
    school = uuid4()
    at = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    event_id = uuid4()
    out = json.loads(canonical_json({"school_id": school, "at": at, "entity_id": event_id}))
    assert out["school_id"] == str(school)
    assert out["at"] == "2026-10-26T12:00:00Z"
    assert out["entity_id"] == str(event_id)


def test_first_link_is_sha256_of_payload() -> None:
    event = {"action": "login", "school_id": str(uuid4())}
    h = compute_chain_hash(None, event)
    assert h == hashlib.sha256(canonical_json(event)).digest()


def test_chained_link_includes_previous_hash() -> None:
    event1 = {"action": "a"}
    event2 = {"action": "b"}
    h1 = compute_chain_hash(None, event1)
    h2 = compute_chain_hash(h1, event2)
    expected = hashlib.sha256(h1 + canonical_json(event2)).digest()
    assert h2 == expected


def test_tampering_first_event_breaks_the_chain() -> None:
    """Recomputing link 2 from a tampered link 1 must not reproduce the stored hash."""
    e1 = {"action": "create", "entity_id": str(uuid4())}
    e2 = {"action": "update", "school_id": str(uuid4())}
    h1 = compute_chain_hash(None, e1)
    h2_stored = compute_chain_hash(h1, e2)

    # Attacker edits event 1's payload; the recomputed chain diverges.
    e1_forged = {**e1, "action": "tampered"}
    h1_forged = compute_chain_hash(None, e1_forged)
    assert compute_chain_hash(h1_forged, e2) != h2_stored
