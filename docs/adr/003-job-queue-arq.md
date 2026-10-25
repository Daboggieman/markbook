# ADR 003: Arq as the job queue

Status: accepted
Date: 2026-10-24
Decides: open decision #2 (default applied); D4, D6 context

## Context

Heavy work (result processing for a class, bulk imports, PDF batches) must never run in request
threads (rule: every long operation is a job). The queue is Redis-backed; the choice was Arq vs
RQ. Both are Redis-backed and simple; the job status survives Redis loss either way because the
`jobs` table is the durable record.

## Decision

**Arq.** Rationale: async-native (matches the async SQLAlchemy stack), supports job timeouts
and retries natively, workers are plain Python modules — same codebase, different entrypoint
(`apps/worker/worker.py`).

## Consequences

- Workers are asyncio processes; job functions are async.
- Arq's retry semantics are configured per job; jobs must still be idempotent (spec §12) —
  retries are expected, not exceptional.
- If a future requirement outgrows Arq, the `jobs` table and the worker entrypoint are the
  seam; producers enqueue by job type and do not know the library.
