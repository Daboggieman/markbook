# Testing notes — how to test Markbook and what the gates are

The testing strategy is in [`../build_docs/05-testing-strategy.md`](../build_docs/05-testing-strategy.md).
This file records how the test infrastructure is wired and what the golden examples prove.

## The golden examples

These are the first tests written, and they never change. They are the spec's worked example
from [`../build_docs/04-core-engine-specs.md`](../build_docs/04-core-engine-specs.md) §9.3,
turned into assertions.

| Student | CA1 | CA2 | Test | Exam | Expected total | Expected grade |
| --- | --- | --- | --- | --- | --- | --- |
| Ada | 8 | 7 | 15 | 48 | 78 | A |
| Bayo | 6 | 5 | 12 | 40 | 63 | B |
| Chidi | 5 | 4.5 | 9 | 31 | 50 (49.5 HALF_UP) | C |
| Dara | 9 | absent | 18 | 52 | 79 | A |
| Efe | 7 | 6 | exempt | 45 | 73 (renormalised) | A |

Plus boundary tests: 39 → F, 40 → E, 44 → E, 45 → D, 69 → B, 70 → A, 100 → A.
Plus policy combinations: absent `treat_zero` vs `exclude_and_renormalise`,
exempt, missing `block` / `treat_zero` / `flag_incomplete`.

These are in `apps/api/src/app/grading/engine/test_engine.py` (Phase 4).

## Testcontainers for DB tests

Repository and RLS tests run against a real Postgres via
[testcontainers-python](https://testcontainers.com/modules/postgresql/). A `conftest.py` fixture
spins up a container per test session, runs migrations, and tears it down. Do not mock the
database.

## Authorization matrix tests

A parametrised test iterates the permission/scope matrix. It is in `tests/security/` and
runs against a real DB (not mocked — RLS must be tested against Postgres, not a mock). The
matrix:

- Teacher A cannot read or write teacher B's class or subject.
- Teacher A cannot read or write their own class if their assignment does not cover that subject.
- Admin with `school` scope can read/write any record.
- Super Admin can do anything normal admins can, plus demote/manage Super Admin protections.

## Route-coverage guard

A CI test (Phase 1) iterates all FastAPI routes registered at startup, checks each has either
`require(...)` or `@public`, and fails if any route is uncovered. This is the enforcement
mechanism for rule 3 in
[`../build_docs/10-coding-agent-rules.md`](../build_docs/10-coding-agent-rules.md). It runs on
every push.

## Sync test scenarios

`tests/sync/` covers: duplicate op, retry-after-timeout, conflict, revoked device, revoked
permission, locked assessment, stale base version. Each is a `pytest` case that runs the full
server-side push handler against a test DB.

## CI test commands

```bash
# Fast
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy apps/api/src/app/grading apps/api/src/app/access  # strict on these

# Unit
.venv/bin/pytest apps/api/src/app/grading/engine/ -q

# Integration (requires testcontainers)
.venv/bin/pytest apps/api/tests/ -q --tb=short

# OpenAPI contract (Phase 1+)
.venv/bin/check-openapi-breakage  # fails CI on breaking change
```

## Coverage minimums

- `grading` engine: **90%**
- `access` service: **90%**
- `workflow` transitions: **90%**
