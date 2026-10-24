# API Design

## Purpose

Design, review, implement, and evolve stable HTTP APIs for the Cee-Tailor system.

## Project Stack

FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL, JWT authentication, Next.js clients.

## Operating Principles

1. Inspect existing routes, schemas, dependencies, services, and response models before adding an endpoint.
2. Follow existing API naming, versioning, pagination, filtering, sorting, and error conventions.
3. Prefer resource-oriented HTTP APIs with explicit request and response schemas.
4. Never expose SQLAlchemy models directly when a dedicated response schema is appropriate.
5. Validate all external input with Pydantic or equivalent schema validation.
6. Document authentication and authorization requirements for protected endpoints.
7. Keep API contracts backward compatible unless a breaking change is explicitly planned.
8. Use appropriate HTTP status codes consistently.
9. Do not silently change an existing response shape.
10. Consider idempotency for operations that may be retried.
11. Consider pagination for potentially unbounded collections.
12. Keep business logic out of route handlers when it belongs in service/domain layers.

## Required Workflow

1. Inspect existing API architecture.
2. Locate related routes, schemas, services, models, and tests.
3. Identify the existing contract and compatibility requirements.
4. Research uncertain framework behavior using Context7 or official documentation.
5. Design request, response, error, authentication, and authorization behavior.
6. Implement the smallest coherent change.
7. Run static checks and API tests.
8. Verify the endpoint through the actual application when possible.
9. Review security and compatibility implications.
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
