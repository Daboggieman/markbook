# ADR 002: Transactional outbox over a message broker

Status: accepted
Date: 2026-10-24
Decides: D5 (spec §1, §12)

## Context

Domain events (assessment state changed, results published, score changed) must be delivered
reliably without losing the "event committed iff state change committed" guarantee. A broker
(RabbitMQ, Kafka) gives that with an operational surface: another stateful system to run,
monitor, and secure.

## Decision

Transactional outbox in Postgres. `outbox_events` rows are inserted in the same transaction as
the state change; a worker dispatcher polls with `FOR UPDATE SKIP LOCKED`, delivers to
in-process handlers, and marks `dispatched_at`. Producers never change if a broker is added —
the dispatcher is the seam.

Topics at launch: `assessment.state_changed`, `results.published`, `score.changed`.

## Consequences

- Exactly-once *insert* semantics per transaction; delivery is at-least-once, so consumers must
  be idempotent.
- No broker to run at launch; adding one later changes the dispatcher, not producers.
- The outbox table grows with event volume; the dispatcher must mark dispatched promptly and a
  retention policy prunes dispatched rows.
