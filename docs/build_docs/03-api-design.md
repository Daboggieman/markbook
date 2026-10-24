# Markbook — Authentication, Authorization, and API Design

Source of record: spec §7 (Authentication and Authorization), §8 (API Conventions).

## 7.1 Authentication

- Passwords hashed with **Argon2id** (tuned parameters in config).
- **Access token:** short-lived JWT (10 to 15 minutes) carrying `sub`, `school_id`,
  `token_version`, `session_id`. **Refresh token:** opaque random value stored hashed in
  `sessions`, rotated on every use, httpOnly secure cookie on web; OS keychain on desktop.
- **Refresh token reuse detection:** reuse of a rotated token revokes the whole session family.
- **Revocation:** bumping `users.token_version` or setting `sessions.revoked_at` invalidates
  tokens. Middleware checks `token_version` through a short Redis cache (30 s TTL) to avoid a
  DB hit on every request.
- **Login throttling:** Redis counters per (username, IP) and per IP; exponential backoff plus
  `locked_until`.
- **Re-authentication:** sensitive endpoints require a `reauth_at` claim within the last 5
  minutes (step-up).
- **MFA:** TOTP, mandatory for Super Admin and any role holding `results.publish`,
  `roles.manage`, `permissions.manage`.

## 7.2 Authorization engine

One function, used everywhere:

```python
authorize(actor, permission: str, resource: ResourceRef | None) -> Decision
```

Steps:

1. Load the actor's effective permissions (cached per `token_version`).
2. If no role grants `permission`, deny.
3. Take the broadest granted scope. If `school`, allow.
4. If `assigned`, check that `resource` resolves to a class/section/subject present in the
   actor's `teacher_assignments` for the relevant session. Deny if no resource is supplied for
   a scoped permission.
5. If `own`, check `resource.created_by == actor.id`.
6. Return the decision and write an audit event for denials on sensitive permissions.

**Enforcement:** a FastAPI dependency `require(permission, resource_loader)` is mandatory on
every route. A CI test iterates all registered routes and fails if any route lacks a `require`
dependency or an explicit `@public` marker. List queries apply the same scope as a SQL filter
(`scope_filter(actor, permission)`), so teachers never receive rows outside their assignments.

## 8. API conventions

- Base path `/api/v1`. Versioning by path; breaking changes require `/v2`.
- JSON; ISO 8601 UTC timestamps.
- **Errors:** RFC 7807 problem details with stable machine codes (`PERMISSION_DENIED`,
  `VERSION_CONFLICT`, `VALIDATION_ERROR`, `INVALID_STATE_TRANSITION`, `POSSIBLE_DUPLICATE`,
  `RATE_LIMITED`).
- **Pagination:** `?limit=50&cursor=...`, max limit 200. Response `{items, next_cursor}`.
- **Optimistic concurrency:** mutable resources return `ETag`/`version`; updates require
  `If-Match` or `version` in the body; mismatch returns `409 VERSION_CONFLICT`.
- **Idempotency:** all POSTs that create or transition accept `Idempotency-Key`. Stored 24 h in
  Redis plus durable record for sync operations.
- Every request gets an `X-Request-Id`, echoed in logs and audit events.
- Long operations return `202 Accepted` with `{job_id, status_url}`.

Full request/response schemas are Pydantic models; the OpenAPI document is the contract of
record and is diffed in CI to flag breaking changes. The TypeScript client in
`packages/api-client/` is generated from it (D10) — never hand-edited.

## Endpoint groups (contract summary)

| Group | Key endpoints | Permission |
| --- | --- | --- |
| Auth | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/mfa/verify`, `/auth/reauth` | public / session |
| Users | `GET/POST /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/suspend`, `POST /users/{id}/revoke-sessions` | `users.*` |
| Roles | `GET/POST /roles`, `PUT /roles/{id}/permissions` | `roles.manage`, `permissions.manage` |
| Students | `GET/POST /students`, `GET/PATCH /students/{id}`, `POST /students/{id}/archive`, `POST /students/check-duplicates` | `students.*` |
| Academic | `/academic-sessions`, `/terms`, `/classes`, `/sections`, `/subjects`, `/enrolments`, `/teacher-assignments`, `POST /promotions/run` | `*.manage` |
| Templates | `/assessment-templates`, `POST /assessment-templates/{id}/versions`, `POST /template-versions/{id}/activate` | `assessments.manage` |
| Assessments | `GET /assessments` (scope filtered), `GET /assessments/{id}/sheet` | `assessments.view` |
| Scores | `PUT /assessments/{id}/scores` (batch upsert), `POST /assessments/{id}/scores/import`, `GET /scores/{id}/history` | `scores.enter`, `scores.edit` |
| Workflow | `POST /assessments/{id}/submit`, `/start-review`, `/return`, `/approve`, `/lock`, `/publish`, `/correct` | `scores.submit`, `scores.review`, `results.*` |
| Results | `POST /assessments/{id}/process` (202), `GET /assessments/{id}/results`, `GET /jobs/{id}` | `results.process` |
| Documents | `POST /documents/report-cards` (202), `GET /documents/{id}/download` | `reports.view`, `transcripts.generate` |
| Audit | `GET /audit-events` | `audit_logs.view` |
| Sync | `POST /sync/devices/register`, `GET /sync/bootstrap`, `POST /sync/push`, `GET /sync/pull?since=...` | `scores.enter` + device check |

## Error codes

`PERMISSION_DENIED`, `VERSION_CONFLICT`, `VALIDATION_ERROR`, `INVALID_STATE_TRANSITION`,
`POSSIBLE_DUPLICATE`, `RATE_LIMITED` — stable machine codes on RFC 7807 problem details. The
error format helper lives in `platform` and is a Phase 0 deliverable.
