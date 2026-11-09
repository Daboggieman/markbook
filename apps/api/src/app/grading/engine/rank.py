"""rank() — dense or competition ranking over computed results (spec §9.2 step 7).

Blocked / no-scoreable results (total None) are not rankable and are skipped —
the service stores them without a position. Ties share a position; the
underlying sort is total DESC then subject_enrolment_id ASC so the output order
is fully deterministic even between tied students.
"""

from collections.abc import Sequence
from decimal import Decimal, localcontext

from app.grading.engine.compute import ENGINE_PRECISION
from app.grading.engine.types import ComputedResult, EngineScheme, RankedResult


def rank(results: Sequence[ComputedResult], scheme: EngineScheme) -> list[RankedResult]:
    """Rank rankable results (dense or competition per `tie_policy`)."""
    with localcontext() as ctx:
        ctx.prec = ENGINE_PRECISION
        # (result, narrowed total) pairs — None totals are not rankable.
        pairs: list[tuple[ComputedResult, Decimal]] = []
        for r in results:
            if r.total is not None:
                pairs.append((r, r.total))
        # Total DESC, then id ASC — deterministic even between ties.
        pairs.sort(key=lambda pair: (-pair[1], pair[0].subject_enrolment_id))

        out: list[RankedResult] = []
        if scheme.tie_policy == "competition":
            # Position = 1 + number of strictly better totals: 1, 1, 3, 4.
            better = 0
            prev_total: Decimal | None = None
            for i, (r, total) in enumerate(pairs):
                if prev_total is None or total != prev_total:
                    better = i
                    prev_total = total
                out.append(_with_position(r, better + 1))
        else:  # dense — position = index of the distinct total: 1, 1, 2, 3.
            position = 0
            prev_total: Decimal | None = None
            for r, total in pairs:
                if prev_total is None or total != prev_total:
                    position += 1
                    prev_total = total
                out.append(_with_position(r, position))
        return out


def _with_position(r: ComputedResult, position: int) -> RankedResult:
    if r.total is None:  # unreachable — rank() only passes narrowed pairs
        raise ValueError("cannot rank a result with no total")
    return RankedResult(
        subject_enrolment_id=r.subject_enrolment_id,
        total=r.total,
        grade=r.grade,
        position=position,
        breakdown=r.breakdown,
        flags=r.flags,
    )
