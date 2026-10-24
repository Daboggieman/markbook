# Deployment

## Purpose

Safely prepare, deploy, verify, and troubleshoot Cee-Tailor releases.

## Project Stack

Project-defined deployment platform, Next.js, FastAPI, PostgreSQL, Redis.

## Operating Principles

1. Inspect the actual deployment configuration before making assumptions.
2. Never assume a provider, environment, or service exists.
3. Keep production secrets outside source control.
4. Verify build and runtime commands.
5. Understand environment variables required by each service.
6. Database migrations must be considered part of deployment.
7. Use health checks where available.
8. Verify the deployed application after changes.
9. Keep rollback procedures clear.
10. Do not make destructive production changes without explicit confirmation.

## Required Workflow

1. Inspect deployment configuration.
2. Identify build, runtime, environment, and database requirements.
3. Validate locally where possible.
4. Deploy using the project's established mechanism.
5. Verify service health.
6. Verify critical user flows.
7. Check logs.
8. Confirm migration state.
9. Record deployment result and remaining uncertainty.

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
