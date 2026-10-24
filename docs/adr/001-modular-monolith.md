# ADR 001: Modular monolith over microservices

Status: accepted
Date: 2026-10-24
Decides: D1 (spec §1)

## Context

Markbook's peak load is a school entering results in the last week of term — write bursts on
`scores`, then heavy reads on `processed_results`. That is a write-then-read burst, not a
scale-out-per-module pattern. Microservices would add deployment, testing, and network-failure
surface with no benefit at launch.

## Decision

One FastAPI deployable. Module boundaries (`identity`, `access`, `people`, `academic`,
`assessment`, `grading`, `workflow`, `documents`, `sync`, `audit`, `platform`) are strict and
enforced by import-linter, so a module can be extracted into a service later without a
rewrite.

## Consequences

- One deployable to build, test, and operate.
- Extracting a module later requires zero refactor of boundaries — only of deployment.
- A single bad deploy takes down everything; mitigated by CI gates and expand-migrate-contract
  migrations.
