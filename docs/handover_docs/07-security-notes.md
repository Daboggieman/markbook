# Security notes — the audit chain, Super Admin, and MFA

The controls checklist and threat model are in
[`../build_docs/08-security-and-operations.md`](../build_docs/08-security-and-operations.md).
This file records the implementation details that live at the intersections — the ones easy to
get subtly wrong.

## The audit hash chain

`audit_events` is append-only at the database level: the app role has `INSERT` only, no
`UPDATE`, no `DELETE`. Each row stores:

- `prev_hash BYTEA` — the `hash` of the previous event
- `hash BYTEA` — `SHA256(prev_hash || canonical_json(event))`

A nightly job (`audit.verify_chain`) walks the chain and recomputes each hash. A mismatch means
tampering, and raises an alert. The chain verifier is a Phase 1 deliverable and its passing is
a Phase 1 exit criterion.

`canonical_json` means: keys sorted, no whitespace, UTC ISO-8601 timestamps. A future session
writing a new event producer must use the same serialisation or the chain breaks on the next
verify. The helper lives in `platform`.

## Super Admin protection is enforced twice

The rule — you cannot delete, deactivate, or demote the last active Super Admin — is enforced:

1. In `access.service`, before the mutation.
2. In a DB trigger, as the backstop.

The service layer is not trusted as the only check. The Phase 1 exit criterion requires both:
the API test (service layer refuses) and the DB test (the trigger blocks a raw UPDATE that
bypasses the service).

## MFA enforcement

TOTP is mandatory for: Super Admin, and any role holding `results.publish`, `roles.manage`, or
`permissions.manage`. This is not a UI hint — the `authorize()` engine checks MFA status when
the permission being exercised is in the mandatory list, and denies if the actor's
`mfa_enabled` is false.

## Refresh token rotation and reuse detection

The refresh token is an opaque random value, stored hashed in `sessions`, rotated on every use.
If a **rotated** token is presented again (a replay), the whole session family is revoked — not
just the token. The client must treat any reuse-detected response as "log in again from
scratch".

## Step-up authentication

Sensitive endpoints (lock, publish, correct, role changes) require a `reauth_at` claim within
the last 5 minutes. The client re-prompts for the password; the server issues a short-lived
`reauth_at` claim. This is separate from MFA — a user with MFA still needs step-up on publish.

## What is never in a log

Passwords, tokens, personal data fields. The logger is allowlist-based — a field is logged only
if the allowlist names it. Adding a field to the allowlist is a reviewed change.

## Sync device security

- Device keys are per-device, not per-user.
- Bootstrap data is scoped to the user's `teacher_assignments` — a revoked scope removes the
  cached rows on the next pull.
- On logout, revocation (`DEVICE_REVOKED`), or repeated auth failure, the local database is
  wiped. The wipe is not optional and not deferred.
- Sync operations are stored with their result, so a replayed batch returns the stored response
  (status `duplicate`), never a re-apply.