# Repo structure and hygiene

The monorepo layout is in [`../build_docs/07-repo-structure.md`](../build_docs/07-repo-structure.md).
This file records hygiene rules — what is tracked, what is never committed, how ADRs are
numbered.

## The ADR process

- ADRs live in `docs/adr/`, numbered `NNN-slug.md` starting at `001`.
- Phase 0 delivers ADRs 001–005 (the D1–D10 decisions that need one: monolith vs services, the
  outbox, the job queue library, PDF generation, the sync protocol).
- ADRs are immutable once accepted. To reverse one, write a new ADR that supersedes it, and
  update the old one's status to `superseded by NNN`.
- Rule 13 in [`../build_docs/10-coding-agent-rules.md`](../build_docs/10-coding-agent-rules.md):
  record non-trivial decisions as ADRs. Rule 12: features outside initial scope require an ADR.

### ADR template

```markdown
# ADR NNN: <title>

Status: proposed | accepted | superseded by ADR NNN
Date: YYYY-MM-DD

## Context
What forces are in play.

## Decision
What was decided.

## Consequences
What this makes easy, what it makes hard, what it rules out.
```

## Environment variables

Secrets come from the environment, never the repo. The `.env.example` file lists every variable
the app reads, with placeholder values. `.env` is gitignored. No exceptions, including for
local development.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection string (app role, non-superuser) |
| `DATABASE_MIGRATION_URL` | Migration/ops role — separate from the app role |
| `REDIS_URL` | Redis connection |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Object storage |
| `JWT_SECRET` | Access-token signing key |
| `ARGON2ID_PARAMS` | Tuned hashing parameters |
| `SCHOOL_ID` | The one school's UUID, for local dev seeding |

## Import-linter

The module dependency rule is enforced by import-linter in CI. The contract file lives at
`apps/api/contracts.ini` (Phase 0). A CI red on a boundary violation is a stop, not a warning —
fix the boundary, do not weaken the contract.

## Git hygiene

- Do not commit generated files: `packages/api-client/` is generated but **is** committed, so
  that a stale client is visible in review rather than silently regenerated at build time.
- Do not commit `.env`, `*.sqlite`, `dist/`, `node_modules/`, `.venv/`.
- **One branch per phase.** The working branch is named for the phase
  (e.g. `markbook_phase_0`), branched from `master` for Phase 0 and from the previous phase's
  branch after that. Record it in [`01-current-state.md`](01-current-state.md) when a phase
  starts. Never work directly on `master`. The user commits and pushes outside these sessions.

## Clean-DB migration check

Phase exit criteria include `alembic upgrade head` on a clean DB. This is not a formality —
it catches migrations that depend on state left behind by a previous migration's data. Run it
against an empty database, not the dev database.
