"""compute() — the core of Phase 4 (spec §9.2).

Pure function: one student's resolved component scores + the pinned template
version + the scheme -> that student's ComputedResult. No I/O, no framework,
Decimal only. Runs inside a fixed-precision local context so a caller's global
decimal context can never change an output — the determinism guarantee
(spec §9.4: same inputs and versions -> byte-identical results).

Rounding happens ONCE, at the end (spec §9.2 step 5): contributions and the
renormalised sum stay at full precision; only the total is quantized. The
grade is looked up from the ROUNDED total — Chidi's 49.5 becomes 50 (grade C),
not 49.
"""

import decimal
from decimal import Decimal, localcontext
from typing import Sequence

from app.grading.engine.scheme import find_grade
from app.grading.engine.types import (
    FLAG_INCOMPLETE,
    FLAG_NO_SCOREABLE,
    FLAG_RENORMALISED,
    FLAG_UNGRADED,
    ROUNDING_MODES,
    BreakdownEntry,
    ComputedResult,
    EngineScheme,
    EngineTemplate,
    ScoreInput,
)

# Fixed working precision for the engine's arithmetic. Contributions like
# value/max_score can be non-terminating (e.g. 1/3); 50 digits is far beyond
# any school scale, and quantize at the end is what the report card shows.
ENGINE_PRECISION = 50

# Engine-level status resolution (spec §9.2 step 1): what a component with no
# score row at all resolves to.
STATUS_ENTERED = "entered"
STATUS_MISSING = "missing"

_ROUNDING = {name: getattr(decimal, name) for name in ROUNDING_MODES}


def compute(
    student_scores: Sequence[ScoreInput],
    template: EngineTemplate,
    scheme: EngineScheme,
) -> ComputedResult:
    """Compute one student's result (spec §9.2).

    `student_scores` is that student's resolved cells — one ScoreInput per
    component the caller consumed (the service synthesizes status='missing'
    for every roster student × template component, so "no score row" arrives
    as `missing`, never as an absent entry). All entries must belong to the
    same subject_enrolment_id.
    """
    if not student_scores:
        raise ValueError(
            "compute() received no score inputs; synthesize status='missing' "
            "rows for each template component instead"
        )
    seid = student_scores[0].subject_enrolment_id
    if any(s.subject_enrolment_id != seid for s in student_scores):
        raise ValueError("compute() got score inputs for more than one student")

    components = template.by_key()
    with localcontext() as ctx:
        ctx.prec = ENGINE_PRECISION

        # Step 1 — resolve each template component's status from the inputs.
        resolved: dict[str, ScoreInput] = {}
        for s in student_scores:
            if s.component_key not in components:
                continue  # not part of this template — cannot be consumed
            if s.component_key in resolved:
                raise ValueError(f"duplicate score input for component {s.component_key!r}")
            resolved[s.component_key] = s

        entries: list[BreakdownEntry] = []
        contributions: list[Decimal] = []
        included_weight = Decimal(0)
        excluded = False
        blocked = False
        flags: set[str] = set()

        for key in sorted(components):
            comp = components[key]
            cell = resolved.get(key)
            status = cell.status if cell is not None else STATUS_MISSING
            value = cell.value if cell is not None else None
            if status != STATUS_ENTERED:
                value = None

            if status == STATUS_MISSING:
                if scheme.missing_policy == "block":
                    # One unresolvable component blocks the whole student
                    # (spec §9.2: block = "cannot process"). Keep filling the
                    # breakdown for the error report, but there is no total.
                    blocked = True
                    entries.append(BreakdownEntry(key, status, value, None, False))
                    continue
                if scheme.missing_policy == "flag_incomplete":
                    flags.add(FLAG_INCOMPLETE)
                entries.append(BreakdownEntry(key, status, value, Decimal(0), False))
                contributions.append(Decimal(0))
                included_weight += comp.weight
            elif status == "absent":
                if scheme.absent_policy == "exclude_and_renormalise":
                    excluded = True
                    entries.append(BreakdownEntry(key, status, value, None, True))
                    continue
                entries.append(BreakdownEntry(key, status, value, Decimal(0), False))
                contributions.append(Decimal(0))
                included_weight += comp.weight
            elif status == "exempt":
                # exempt_policy is always exclude_and_renormalise (spec §9.2).
                excluded = True
                entries.append(BreakdownEntry(key, status, value, None, True))
                continue
            else:  # entered — the DB CHECK guarantees entered => value
                if value is None:
                    raise ValueError(f"entered score for {key!r} has no value")
                contribution = (value / comp.max_score) * comp.weight
                entries.append(BreakdownEntry(key, status, value, contribution, False))
                contributions.append(contribution)
                included_weight += comp.weight

        if blocked:
            return ComputedResult(
                subject_enrolment_id=seid,
                total=None,
                grade=None,
                breakdown=tuple(entries),
                flags=frozenset(flags | {FLAG_INCOMPLETE}),
            )
        if excluded:
            flags.add(FLAG_RENORMALISED)

        # Step 4 — total; renormalise when components were excluded.
        raw_total = sum(contributions, Decimal(0))
        if excluded:
            if included_weight == 0:
                # Everything excluded (e.g. exempt from every component):
                # renormalising would divide by zero — flag, no total.
                return ComputedResult(
                    subject_enrolment_id=seid,
                    total=None,
                    grade=None,
                    breakdown=tuple(entries),
                    flags=frozenset(flags | {FLAG_NO_SCOREABLE}),
                )
            raw_total = raw_total / included_weight * 100

        # Step 5 — round ONCE, at the end.
        quantum = Decimal(1).scaleb(-scheme.precision)
        total = raw_total.quantize(quantum, rounding=_ROUNDING[scheme.rounding_mode])

    # Step 6 — grade from the rounded total (validated boundaries => one hit).
    grade = find_grade(total, scheme.boundaries)
    extra = frozenset(flags | {FLAG_UNGRADED}) if grade is None else frozenset(flags)
    return ComputedResult(
        subject_enrolment_id=seid,
        total=total,
        grade=grade,
        breakdown=tuple(entries),
        flags=extra,
    )
