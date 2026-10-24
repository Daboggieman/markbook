# Database Engineering

## Purpose

Design and maintain PostgreSQL data models and SQLAlchemy persistence safely.

## Project Stack

PostgreSQL, SQLAlchemy 2, Alembic.

## Operating Principles

1. Inspect existing models and relationships before creating new tables.
2. Understand cardinality and ownership of every relationship.
3. Use explicit constraints for important invariants.
4. Use appropriate indexes based on actual query patterns.
5. Do not add indexes blindly.
6. Protect referential integrity with foreign keys where appropriate.
7. Consider nullability deliberately.
8. Use transactions for multi-step state changes.
9. Never delete production data as part of exploratory work.
10. Do not assume development and production schemas are identical.
11. Verify generated SQL and migration behavior for significant changes.

## Required Workflow

1. Inspect current schema and ORM models.
2. Identify affected queries and relationships.
3. Design constraints and indexes.
4. Implement model changes.
5. Create or update migrations.
6. Run migrations in a safe environment.
7. Run relevant database/API tests.
8. Inspect query behavior where necessary.
9. Review data-loss and rollback risks.

## Evidence Rules

Use the strongest available evidence in this order:

1. Runtime behavior
2. Automated test results
3. Type checking, linting, and build results
4. Installed package/source behavior
5. Official framework or library documentation
6. Repository configuration
7. Static code inspection
8. General model knowledge

Never report an assumption as a verified result.

## Tool Selection

- Use Filesystem MCP for repository exploration and file inspection.
- Use Context7 for current, version-specific library/framework documentation.
- Use Fetch when official documentation or public web resources need to be retrieved.
- Use Playwright for browser behavior, frontend interaction, forms, authentication flows, and UI verification.
- Use GitHub CLI for repository, branch, pull request, issue, workflow, and CI operations.
- Prefer the smallest tool set that establishes reliable evidence.

## Failure Handling

When something fails:

1. Reproduce the failure.
2. Capture the exact error.
3. Identify the failing layer.
4. Check whether the failure is environmental, dependency-related, configuration-related, or caused by application code.
5. Research uncertain behavior using authoritative sources.
6. Apply the smallest appropriate fix.
7. Reproduce the original failure again.
8. Run regression checks.
9. Inspect the final diff.

Do not hide failures by weakening tests, suppressing errors, deleting evidence, or claiming success without verification.

## Security

- Never expose secrets.
- Never commit credentials.
- Treat all external input as untrusted.
- Preserve authentication and authorization boundaries.
- Avoid leaking internal implementation details through errors.
- Review security implications whenever the skill touches users, data, credentials, networking, or deployment.

## Completion Criteria

A task using this skill is complete only when:

- The requested behavior is implemented.
- Existing project conventions are preserved.
- Relevant static checks pass.
- Relevant tests pass or their absence is explicitly reported.
- Browser verification is performed when the task affects user-facing behavior.
- Security implications have been considered.
- The final diff has been inspected.
- Verified facts are clearly distinguished from assumptions or remaining uncertainty.
