# Markbook — Repository Structure

Source of record: spec §4 (Repository Layout).

## The monorepo

```
markbook/
  apps/
    api/
      src/app/
        main.py                 # app factory, middleware, routers
        platform/               # config, db, redis, jobs, outbox, logging, errors, pagination, idempotency
        identity/               # router.py, service.py, repository.py, models.py, schemas.py
        access/
        people/
        academic/
        assessment/
        grading/
          engine/               # PURE calculation engine, no imports from app
        workflow/
        documents/
        sync/
        audit/
      migrations/               # Alembic
      tests/
        unit/ api/ workflow/ sync/ security/ conftest.py
      pyproject.toml
    worker/                     # entrypoint that imports api modules and runs jobs
    web/                        # React + TS (Vite)
    desktop/                    # Tauri shell wrapping the web UI + local sync layer
  packages/
    api-client/                 # generated TS client from OpenAPI
    ui/                         # shared components
    rules/                      # shared validation helpers (UI hints only, never authoritative)
  infra/
    docker/ compose.dev.yml terraform-or-equivalent/ runbooks/
  docs/
    adr/                        # architecture decision records
    threat-model.md
  .github/workflows/            # CI
```

Note: this repository's planning package lives at `docs/build_docs/` (this folder) and the
running handover at `docs/handover_docs/`, beside `docs/adr/` and `docs/threat-model.md` from
the spec layout.

## Per-module internal shape

Each backend module has the same internal shape:

| File | Holds | Rule |
| --- | --- | --- |
| `router.py` | HTTP only | Never touches repositories directly |
| `service.py` | Business logic, transactions | Calls other modules through their service interfaces only |
| `repository.py` | SQL, always tenant-scoped | Extends the tenant-scoped base class |
| `models.py` | SQLAlchemy | — |
| `schemas.py` | Pydantic | — |

**Routers never touch repositories directly.** The chain is always
`router -> service -> repository`.

## The shared packages

- `packages/api-client/` — generated TS client from OpenAPI. Regenerated, never hand-edited
  (D10).
- `packages/ui/` — shared components.
- `packages/rules/` — shared validation helpers. **UI hints only, never authoritative** (D8).

## Import-linter

The module dependency rule (see
[`01-architecture-and-stack.md`](01-architecture-and-stack.md)) is enforced in CI by
import-linter. CI red on a boundary violation is a stop, not a warning.
