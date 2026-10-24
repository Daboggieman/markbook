# Markbook — Open Decisions

Source of record: spec §18 (Open Decisions to Resolve Before or During Phase 0). Each row holds
the default that applies if the decision is not made explicitly. When a decision IS made, it
moves from this table into an ADR in `docs/adr/` and this table is updated to say so.

| # | Question | Default if undecided | Status |
| --- | --- | --- | --- |
| 1 | Hosting provider and region (latency and data-residency considerations for Nigeria) | Managed Postgres and containers in the nearest low-latency region with a Nigeria-friendly provider | Open |
| 2 | Job queue library | Arq | Open — ADR due Phase 0 |
| 3 | PDF generation approach | WeasyPrint (HTML to PDF) in worker | Open |
| 4 | Exact retention periods for audit logs, exports, and archived students | Set by school policy; configurable per school | Open |
| 5 | Whether separation of duties (submitter cannot approve) is strict | On by default, configurable | Open |
| 6 | Local encryption method on desktop | SQLCipher with key held in OS keychain | Open |
| 7 | Product name | **Decided: Markbook.** Package names stay neutral so a future rename stays cheap | Closed |

## How to close one

Record it as an ADR in `docs/adr/` (numbering continues from Phase 0's ADRs 001–005), then move
the row's status to Closed with the ADR number. Do not edit the spec's §18 table to record the
decision — that table is the spec's record of what was open when the spec was written; this file
tracks the current state.
