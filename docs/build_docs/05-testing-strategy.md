# Markbook — Testing Strategy

Source of record: spec §14 (Testing Strategy). Phase exit criteria in
[`06-roadmap.md`](06-roadmap.md) point at this doc; the verification template lives there.

## What each layer must cover

| Layer | Tooling | Must cover |
| --- | --- | --- |
| Engine unit tests | pytest, hypothesis | Golden examples from §9.3; every boundary value; rounding modes; missing, absent, exempt policies; ties; property test that grade is always found and total stays within 0 to 100 |
| Repository/DB tests | pytest + real Postgres (testcontainers) | Constraints (zero vs missing CHECK, uniqueness), RLS isolation between two test schools, audit append-only grants |
| API tests | pytest + httpx | Every route: unauthenticated, wrong permission, wrong scope, valid; validation errors; pagination; idempotency |
| Authorization matrix | parametrised | Teacher A cannot read or write teacher B's class or subject; scoped list filtering |
| Workflow tests | pytest | Every legal transition; every illegal transition; separation of duties; edit blocked after submit; correction versioning |
| Sync tests | pytest | Duplicate op, retry after timeout, conflict, revoked device, revoked permission, locked assessment, stale base version |
| Route-coverage guard | CI test | Fails if any route lacks `require(...)` or `@public` |
| Frontend | Vitest + Testing Library | Score sheet validation UX, conflict dialog |
| E2E | Playwright | Teacher enters and submits; reviewer returns; admin approves, locks, publishes; correction after publish |
| Load | k6 | 500 concurrent teachers entering scores; result processing for a 1,500-student term |
| Operational | scripted | Backup restore into a clean environment and verification query suite |

## CI gates

- Lint: ruff, mypy strict on `grading` and `access`.
- Import-linter (module dependency rule).
- Tests with coverage minimum: **90% on `grading`, `access`, `workflow`**.
- OpenAPI breaking-change check.
- Dependency and container scanning.

## Standing test rules

- Write tests **first** for the engine, authorization, and workflow (rule 10,
  [`10-coding-agent-rules.md`](10-coding-agent-rules.md)).
- Add a test for every bug fix.
- Never weaken a test to obtain a passing result. Never claim a test passed without running it.
- Load targets (Phase 8): 500 concurrent teachers entering scores; result processing for a
  1,500-student term.
