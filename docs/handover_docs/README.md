# Markbook — Handover

The running handover for the Markbook build sessions. These documents are the record of what
the app *is* and *why*, distinct from [`../build_docs/`](../build_docs/) which holds what the
app is *meant* to be.

**Read [`01-current-state.md`](01-current-state.md) first.** It is the only document here
that dates quickly. Everything else is reference and stays true until the thing it describes
changes.

Last updated: **2026-10-24** — initial setup.

## The resume point

**It lives in [`01-current-state.md`](01-current-state.md), and only there.** Do not restate
it elsewhere — multiple copies diverge, and a stale copy is worse than no copy.

## Standing constraints

- **Do not create or amend commits unless the user asks, and never push.** That includes not
  staging, not tidying this index, and not committing "while you're in there". The user commits
  and pushes outside these sessions.
- **One branch per phase.** Each phase's work happens on its own branch, named for the phase
  (e.g. `markbook_phase_0`), branched from `master` for Phase 0 and from the previous phase's
  branch after that. Record the working branch in [`01-current-state.md`](01-current-state.md)
  when a phase starts; never work directly on `master`.
- **Physical device runs and production deployments remain the user's to run.** Report
  readiness; do not claim a gate passed without their evidence. Automated checks
  (`pytest -q`, `ruff`, `mypy`, `alembic upgrade head`, `npx tsc --noEmit`) are ours to run.
- **The spec is the source of truth.** If a claim in these docs disagrees with
  [`../Markbook_Build_Specification .md`](../Markbook_Build_Specification%20.md), the spec wins
  and this file should be corrected.
- **Work one phase at a time.** Never start a phase before the previous phase's exit criteria
  pass — confirmed by running the verification step, not by assuming.
- **Zero is distinct from missing.** This is a database invariant, not a preference.
  `score.status='entered'` with value `0.00` is a real zero; `missing` has NULL.

## The documents

| File | What it holds | Read it when |
|---|---|---|
| [`01-current-state.md`](01-current-state.md) | Phase board, what is verified and when, open items | Always, first |
| [`02-api-conventions.md`](02-api-conventions.md) | Per-module conventions, the router/service/repository chain, and the departure record | Before adding a route |
| [`03-data-model-notes.md`](03-data-model-notes.md) | Decisions embedded in the schema, the duplicate-detection flow, the historical-context invariant | Changing the schema |
| [`04-module-reference.md`](04-module-reference.md) | Module surface: public interfaces of each service, cross-module calls | Changing a module's logic |
| [`05-architecture-decisions.md`](05-architecture-decisions.md) | Key decisions and why they were made | Questioning a dependency or an approach |
| [`06-testing-notes.md`](06-testing-notes.md) | Test infrastructure decisions, the golden examples, the route-coverage guard | Writing tests or extending CI |
| [`07-security-notes.md`](07-security-notes.md) | Security implementation details, the audit chain, Super Admin protections, MFA enforcement | Implementing auth or audit |
| [`08-repo-structure-and-hygiene.md`](08-repo-structure-and-hygiene.md) | Repo hygiene, environment variables, import-linter, the ADR process | Before git housekeeping |
| [`09-phase-acceptance.md`](09-phase-acceptance.md) | Phase-by-phase sign-off record | Closing a phase |

## Keeping it usable

- **Put new material in the document that owns the subject**, not at the top of `01`. `01` is a
  status board; if it grows past a screenful it is holding something that belongs elsewhere.
- **Date every claim** that could go stale, and say whether a number was *measured* or is
  *expected*. A count written without running becomes a stale claim.
- **When a decision is reversed, say so where the old one was written.** Several notes here
  exist only to stop a fixed thing being "fixed" again.
- **One fact, one home.** A status claim repeated in a second file is a claim that will
  disagree with itself. Link to the owner instead of restating it.
- **Write claims in the past tense about what happened, not the future tense about what will.**
