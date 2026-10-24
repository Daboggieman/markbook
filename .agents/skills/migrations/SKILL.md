# Database Migrations

## Purpose

Create, review, apply, and troubleshoot Alembic migrations safely.

## Project Stack

Alembic, SQLAlchemy 2, PostgreSQL.

## Operating Principles

1. Never edit historical migrations casually.
2. Inspect the current migration head before creating a migration.
3. Ensure every migration has a clear upgrade and downgrade strategy when practical.
4. Review generated migrations instead of blindly trusting autogeneration.
5. Check for destructive operations.
6. Consider existing production data before changing constraints or column types.
7. Consider lock duration and migration runtime for large tables.
8. Never reset a shared database to solve a migration problem.
9. Verify migration ordering and dependency relationships.
10. Test both schema application and application compatibility.

## Required Workflow

1. Inspect migration history.
2. Inspect current models and database state.
3. Generate or write the migration.
4. Review the migration manually.
5. Apply it in a disposable/test environment.
6. Run application tests.
7. Verify downgrade behavior where applicable.
8. Check for destructive or long-running operations.
9. Inspect the final migration diff.

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
