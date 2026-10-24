# Markbook — Coding Agent Rules

Source of record: spec §17 (Coding-Agent Instructions). These are the standing rules every
Markbook coding session works under. Read them before every session. Breakage is reported to
the user as a process deviation.

---

Give the following to any coding agent as **standing rules**.

1. **Work one phase at a time.** Begin with the phase verification step
   ([`06-roadmap.md`](06-roadmap.md)). Do not start a later phase until the current phase exit
   criteria pass.
2. **Never put business rules in clients.** Permissions, calculations, workflow transitions, and
   locking live only in the backend (D8).
3. **Every route must declare `require(...)` or `@public`.** The route-coverage test must stay
   green.
4. **Every tenant table needs `school_id`, a leading-`school_id` index, and an RLS policy.**
   Never read `school_id` from request input.
5. **Respect module boundaries.** Call other modules through their `service` interfaces only;
   keep import-linter passing.
6. **Use `Decimal` for scores and totals.** Never `float`.
7. **Never hard-delete academic data.** Archive.
8. **Never edit an applied migration.** Add a new one. Use expand-migrate-contract.
9. **Every state-changing action writes an audit event in the same transaction.**
10. **Write tests first for the engine, authorization, and workflow.** Add a test for every bug
    fix.
11. **Do not log secrets or personal data.**
12. **Do not add features outside the initial scope** (no fees, attendance, portals,
    multi-school UI) without an ADR.
13. **Record non-trivial decisions as ADRs** in `docs/adr/`.
14. **At the end of each phase,** report: deliverables done, tests added and passing, known
    gaps, and any deviations from this spec.

## Project workflow rules (not from the spec)

These come from the project owner, standing beside the spec rules above:

15. **Do not create or amend commits unless the user asks, and never push.** The user commits
    and pushes outside these sessions.
16. **One branch per phase.** Work happens on a branch named for the phase
    (e.g. `markbook_phase_0`), branched from `master` for Phase 0 and from the previous phase's
    branch after that. Never work directly on `master`.
