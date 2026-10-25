# API conventions — follow these for every route

These were decided once in the spec. Re-deciding them per route is how the API ends up
inconsistent. Everything here binds all routes.

## Structure rules

- **Base path:** `/api/v1`. Breaking changes go to `/v2`.
- **Routers never touch repositories directly.** The chain is always
  `router -> service -> repository`. Never shortcut it.
- **Every route must declare `require(...)` or `@public`.** The route-coverage guard in CI
  fails if any route is missing one. A missing `require` is a CI red, not a warning.
- **`@public` only for truly unauthenticated routes** (login, refresh, health). If in doubt,
  use `require`.

## Request and response rules

- JSON; ISO 8601 UTC timestamps.
- **Pagination:** `?limit=50&cursor=...`, max limit 200. Response shape: `{items, next_cursor}`.
  Never return unbounded lists.
- **Optimistic concurrency:** mutable resources return `ETag`/`version` in the response.
  Updates require `If-Match` or `version` in the body; mismatch returns `409 VERSION_CONFLICT`.
- **Idempotency:** all POSTs that create or transition accept `Idempotency-Key`. Re-sending the
  same key returns the stored response. Store it 24 h in Redis plus the durable `sync_operations`
  record for sync ops.
- Every request gets an `X-Request-Id` header. Echo it in logs and in the audit event.
- Long operations return `202 Accepted` with `{job_id, status_url}`. The caller polls
  `GET /jobs/{id}`.

## Error rules

Use RFC 7807 problem details. Stable machine codes:

| Code | When |
| --- | --- |
| `PERMISSION_DENIED` | `authorize()` returned deny |
| `VERSION_CONFLICT` | Optimistic lock mismatch |
| `VALIDATION_ERROR` | Pydantic validation failed |
| `INVALID_STATE_TRANSITION` | Workflow transition not allowed |
| `POSSIBLE_DUPLICATE` | Student duplicate detection hit |
| `RATE_LIMITED` | Throttle triggered |
| `ASSESSMENT_NOT_EDITABLE` | Score edit on a locked assessment |

The error-format helper lives in `platform`. Never inline it.

## Tenant-scoped queries

Every repository method must call the tenant-scoped base — never raw SQL that omits
`school_id`. The base class enforces the `WHERE school_id = ?` clause. If a method needs
cross-school access, it must be explicitly authorised and documented.