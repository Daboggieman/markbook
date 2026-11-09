"""input_hash — the determinism fingerprint (spec §9.4).

Each processing run stores an `input_hash` of all scores consumed: the same
inputs must always produce the same hash and byte-identical results. The hash
is SHA-256 over a canonical serialization of the exact ScoreInput list the
engine consumes — one entry per roster student × template component (missing
components synthesized as status='missing' upstream), students sorted by id,
components sorted by key, values canonicalized to plain fixed-point strings so
Decimal('8.00') and Decimal('8') hash identically.
"""

import hashlib
import json
from decimal import Decimal
from typing import Sequence

from app.grading.engine.types import ScoreInput


def canonical_value(value: Decimal | None) -> str | None:
    """Fixed-point canonical form: '8.00' -> '8', '49.50' -> '49.5',
    '100.00' -> '100'. None for no value (statuses absent/exempt/missing)."""
    if value is None:
        return None
    if value == 0:
        return "0"  # collapse -0 and 0.00 into one form
    return format(value.normalize(), "f")


def input_hash(scores: Sequence[ScoreInput]) -> str:
    """SHA-256 over the canonical score set (spec §9.4).

    Pass the SAME list (post-synthesis, one entry per student × component)
    that was fed to compute() — the hash must cover everything consumed.
    """
    grouped: dict[str, list[tuple[str, str, str | None]]] = {}
    for s in scores:
        grouped.setdefault(s.subject_enrolment_id, []).append(
            (s.component_key, s.status, canonical_value(s.value))
        )
    payload: list[list[object]] = []
    for seid in sorted(grouped):
        cells = sorted(grouped[seid])
        payload.append([seid, [[k, st, v] for k, st, v in cells]])
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
