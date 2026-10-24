# Markbook — Architecture and Stack

Source of record: spec §3 (System Architecture), §2 (Scalability Principles), §12 (Background
Jobs and Events).

## System architecture

```
[Web: React+TS]   [Desktop: Tauri+React+TS]
        \               /
         HTTPS (JWT access + refresh cookie)
                |
         [Load Balancer / TLS]
                |
   [FastAPI API instances x N]  (stateless)
     |        |         |
[Postgres] [Redis]  [Object storage]
     |        |
 [Outbox]  [Job queue] --> [Worker processes x M]
```

The API is stateless (D2). Everything shared lives in Postgres, Redis, or object storage — the
scaling principles below make this a code rule, not an aspiration.

## The bounded contexts

Eleven modules, one shared kernel. Each owns its tables end to end — router, service,
repository, models, schemas (see
[`07-repo-structure.md`](07-repo-structure.md) for the per-module internal shape).

| Module | Owns |
| --- | --- |
| `identity` | users, sessions, devices, MFA, password reset |
| `access` | roles, permissions, scopes, authorization engine |
| `people` | students, guardians, staff profiles |
| `academic` | sessions, terms, levels, classes, sections, subjects, enrolments, teacher assignments, promotions |
| `assessment` | templates, template versions, assessments, scores |
| `grading` | grading schemes, calculation engine, processing runs, processed results |
| `workflow` | approval state machine, approval records, locks, publication |
| `documents` | report cards, transcripts, PDF generation, exports |
| `sync` | desktop sync operations, device registration, conflict handling |
| `audit` | audit events (append-only) |
| `platform` | config, db, redis, jobs, outbox, logging, errors (shared kernel) |

## The dependency rule

- `platform` depends on nothing.
- `audit` and `access` may be called by all.
- Other modules may depend on `people` and `academic` read interfaces.
- `workflow` may depend on `grading`.
- No cycles.

This is not convention — it is enforced by an import-linter rule in CI (Phase 0 deliverable,
test gate in [`05-testing-strategy.md`](05-testing-strategy.md)).

## Scaling principles (rules the code must follow)

1. **No in-process state.** No module-level caches of user data, no sticky sessions, no
   local-disk files. Anything shared lives in Postgres, Redis, or object storage.
2. **No module reaches into another module's tables.** Cross-module access goes through that
   module's service interface. This is what makes later extraction possible.
3. **Every list endpoint is paginated** (cursor-based) and has a hard max page size.
4. **Every long operation is a job.** Anything over roughly 500 ms of expected work (result
   processing for a class, bulk import, PDF batch) is enqueued, returns a job id, and is
   polled.
5. **Every write that can be retried is idempotent** (idempotency key).
6. **Every tenant-owned query is scoped by `school_id`**, enforced by a repository base class
   plus RLS. Developers cannot forget it.
7. **Schema changes are backward compatible** (expand, migrate, contract), so deploys never
   require downtime.
8. **Config over code.** Roles, templates, grading rules, and workflow stages are data, not
   code branches.
9. **Indexes are designed with the schema,** not added after complaints.
10. **Observability from phase 1:** structured logs, request ids, metrics, and error tracking.

## Background jobs and events

- **Queue:** Redis-backed — Arq by default, RQ as the alternative; whichever is chosen is
  recorded in an ADR (open decision 2, [`09-open-decisions.md`](09-open-decisions.md)). Workers
  are the same codebase, started with a different entrypoint (`apps/worker/`).
- **Job table:** `jobs(id, school_id, type, status, params, result, error, created_by,
  created_at, finished_at)` so job status survives Redis loss.
- **Job types:** `results.process`, `scores.import`, `documents.report_cards`,
  `documents.transcript`, `audit.verify_chain`, `retention.cleanup`.
- Jobs are idempotent and re-runnable; they take row locks and check state at start.
- **Outbox dispatcher:** a worker polls `outbox_events` (using `FOR UPDATE SKIP LOCKED`),
  delivers to in-process handlers, and marks dispatched. Topics at launch:
  `assessment.state_changed`, `results.published`, `score.changed`. This is the seam where a
  broker such as RabbitMQ or Kafka plugs in later, and where parent notifications attach in the
  future.

## Scaling path (what changes, and when)

| Stage | Trigger | Change |
| --- | --- | --- |
| 0. Launch | One school | One API instance, one worker, managed Postgres, Redis |
| 1. Busy school | Peak load at result time | Run 2 to 4 API instances behind a load balancer; scale workers |
| 2. Read pressure | Reports and dashboards slow | Add a Postgres read replica for reporting queries |
| 3. Multi-school | Second school onboarded | Add tenant admin UI and school onboarding flow; RLS and `school_id` already in place |
| 4. Large multi-school | Thousands of users, heavy reports | Partition large tables (`scores`, `audit_events`) by `school_id` or time; extract Reporting and Sync into separate services if needed |

Nothing past stage 0 is built at launch. The table exists so the foundations laid now are the
ones each stage needs.
