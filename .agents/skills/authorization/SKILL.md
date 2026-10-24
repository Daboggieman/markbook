# Authorization

## Purpose

Control what authenticated users are allowed to access or modify.

## Project Stack

FastAPI dependencies, JWT/user identity, application services.

## Operating Principles

1. Authentication answers who the user is; authorization answers what they may do.
2. Perform authorization on the server.
3. Never rely on hidden frontend controls for access control.
4. Check object ownership where resources belong to specific users.
5. Centralize reusable authorization rules where practical.
6. Use least privilege.
7. Return appropriate authorization errors without leaking sensitive information.
8. Test both allowed and denied cases.
9. Review indirect object reference risks.
10. Do not infer authorization from UI visibility.

## Required Workflow

1. Identify protected resources.
2. Map roles, ownership, and permissions.
3. Trace every relevant endpoint.
4. Implement server-side authorization.
5. Test authorized and unauthorized users.
6. Test cross-user resource access.
7. Review privilege escalation paths.
8. Inspect final changes.

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
