# Backend Engineering

## Purpose

Build and maintain reliable FastAPI backend functionality using the project's existing architecture.

## Project Stack

Python 3.11+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Celery, JWT, bcrypt.

## Operating Principles

1. Inspect the existing backend architecture before creating new modules.
2. Separate routing, schemas, services, persistence, and infrastructure responsibilities.
3. Prefer dependency injection through FastAPI dependencies where appropriate.
4. Keep route handlers thin.
5. Validate all untrusted input.
6. Handle database transactions explicitly and predictably.
7. Never swallow exceptions without a deliberate reason.
8. Use async code only where the surrounding architecture supports it correctly.
9. Do not introduce a new architectural pattern when an existing project pattern already solves the problem.
10. Keep secrets and credentials out of source code.
11. Do not claim backend functionality works without executing relevant verification.

## Required Workflow

1. Map the affected backend modules.
2. Trace the request path from route to persistence.
3. Identify data and transaction boundaries.
4. Research framework behavior if uncertain.
5. Implement using existing project conventions.
6. Run lint/type/static checks available in the repository.
7. Run relevant unit/integration/API tests.
8. Verify failure paths as well as successful paths.
9. Review security and transaction behavior.
10. Inspect the final diff.

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
