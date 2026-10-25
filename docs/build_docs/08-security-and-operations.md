# Markbook — Security, Threat Model, and Operations

Source of record: spec §13 (Security and Threat Model), §15 (Deployment and Operations). The
full threat model lives in `docs/threat-model.md` and is reviewed before every production
release.

## 13.1 Controls checklist

- TLS everywhere; HSTS; secure cookies; strict CORS allowlist; CSP on web; security headers.
- Secrets from environment or a secret manager, never in the repo; pre-commit secret scanning.
- SQLAlchemy parameterised queries only; no string-built SQL.
- Pydantic validation on every input; request size limits; file upload type and size checks
  and virus scanning for imports.
- Rate limits: auth endpoints strict; sensitive endpoints (publish, export, role changes)
  moderate; global per-user default.
- Logs scrub passwords, tokens, and personal data fields by an allowlist logger.
- Backups encrypted, off-site, restore tested on a schedule (quarterly minimum, plus before
  each major release).
- Exports and downloads: signed short-lived URLs; each download audited; retention window
  defined and enforced by `retention.cleanup`.
- Dependency and container scanning in CI.

## 13.2 Threat model (STRIDE summary)

| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Stolen password | Argon2id, MFA for privileged roles, throttling, session revocation |
| Tampering | Teacher edits another class's scores via API | Server-side scoped authorize on every route, RLS, route-coverage CI test |
| Tampering | Silent change to published result | Edit blocked after submit; corrections create new document versions; audit hash chain |
| Repudiation | "I didn't change that score" | `score_changes` and tamper-evident audit events with actor, time, IP, reason |
| Information disclosure | Student data in logs or exports | Log scrubbing, scoped queries, signed URLs, export audit |
| Information disclosure | Lost laptop with cached data | Encrypted local DB, device revocation wipe, minimal cache scope |
| Denial of service | Login flood, huge imports | Rate limits, upload limits, jobs for heavy work |
| Elevation of privilege | Admin weakens Super Admin | Protected role rules in service layer and DB trigger |
| Replay | Resent sync batch | Idempotency keys, server-side dedupe |

## 15. Deployment and operations

- **Environments:** `dev` (docker compose), `staging` (production-like, anonymised data),
  `prod`.
- **Containers:** one image, entrypoints `api` and `worker`. Run migrations as a release step
  before new instances take traffic.
- **Hosting:** managed Postgres with PITR backups and automated daily snapshots; managed
  Redis; S3-compatible storage; container platform with autoscaling on CPU and request
  latency; TLS terminated at the load balancer.
- **Database connections:** pooled (PgBouncer or provider pooler); API instances limited so
  total connections stay under the database limit.
- **Zero-downtime releases:** rolling deploys; migrations follow expand-migrate-contract.
- **Observability:** structured JSON logs with request id; metrics (latency, error rate, queue
  depth, job duration, sync conflict rate); error tracking; alerts on failed jobs, audit chain
  break, backup failure, and elevated 5xx.
- **Runbooks** (in `infra/runbooks/`): restore from backup, rotate secrets, revoke a
  compromised account or device, rerun a failed processing job, roll back a release.
- **Backup policy:** daily full plus continuous WAL; retention defined by school policy;
  restore drill documented with timings (RTO and RPO recorded).

## Environments

`dev` (docker compose), `staging` (production-like, anonymised data), `prod`. Never test
against prod; never seed prod with real student data except through the school's own onboarding.
