# ADR 005: WeasyPrint for PDF generation

Status: accepted
Date: 2026-10-24
Decides: open decision #3 (default applied)

## Context

Report cards and transcripts are rendered documents (Phase 5). Options: WeasyPrint
(HTML/CSS → PDF), ReportLab (programmatic), a headless browser. Templates want to be
school-configurable, which favours HTML/CSS over imperative drawing code.

## Decision

**WeasyPrint**, running in the worker (never the API process): templates are HTML + CSS,
schools' report-card layouts become CSS, and the PDF generation job renders them to object
storage.

## Consequences

- Templates are reviewable as markup; report-card design changes are a deploy, not a migration.
- WeasyPrint is CPU-heavy — always run behind the `documents.report_cards` job, never inline.
- System font/CSS support in the worker image must be verified in the Phase 5 build.
