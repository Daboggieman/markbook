# ADR 004: Tenant context via set_config + RLS, applied in the session factory

Status: accepted
Date: 2026-10-24
Decides: D3 mechanism (spec §5)

## Context

Every tenant-owned query must be scoped by `school_id`. Developers cannot be relied on to
remember the WHERE clause; defence in depth requires the database to enforce it too. PostgreSQL
`SET LOCAL app.school_id` is transaction-scoped, but `SET LOCAL` cannot take bind parameters.

## Decision

- The session factory exposes `tenant_session(school_id)` which opens a transaction and calls
  `SELECT set_config('app.school_id', :school_id, true)` — the `is_local = true` argument makes
  it the functional equivalent of `SET LOCAL` (transaction-scoped, gone at commit/rollback, so
  pooled connections never leak a tenant).
- RLS policies compare `school_id = current_setting('app.school_id')::uuid` on every tenant
  table.
- The app role is not a superuser and does not bypass RLS; migrations and ops use a separate
  role (`DATABASE_MIGRATION_URL`).
- `school_id` is derived from the authenticated user, never from client input.

## Consequences

- A query that forgets its WHERE clause still cannot cross tenants — RLS is the second defence
  layer.
- `set_config(..., true)` must be called inside the transaction; the `tenant_session` helper
  guarantees ordering.
- One connection per tenant-scoped transaction; pooling is safe because the setting dies with
  the transaction.
