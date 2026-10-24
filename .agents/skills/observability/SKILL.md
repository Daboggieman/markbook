# Observability

## Purpose

Make production behavior understandable through logs, metrics, traces, health checks, and diagnostics.

## Project Stack

FastAPI, Next.js, application logs, deployment infrastructure.

## Operating Principles

1. Log meaningful events rather than arbitrary noise.
2. Never log passwords, tokens, secrets, or sensitive personal data.
3. Use structured logging where the project supports it.
4. Include useful request or correlation context where appropriate.
5. Health checks should represent meaningful service health.
6. Separate liveness from readiness where relevant.
7. Errors should contain enough context to diagnose failures.
8. Do not use logging as a substitute for proper error handling.
9. Observability changes must preserve privacy and security.

## Required Workflow

1. Identify the operational question.
2. Determine what evidence is currently available.
3. Add the smallest useful telemetry.
4. Verify emitted logs/metrics/health responses.
5. Check for sensitive-data leakage.
6. Document important operational signals.

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
