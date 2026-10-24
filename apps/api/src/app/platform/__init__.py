"""Markbook platform package — shared kernel.

Depends on nothing inside the app (enforced by import-linter). Everything here
is infrastructure: config, database, redis, jobs, outbox, logging, errors,
pagination, idempotency.
"""
