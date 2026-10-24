# Error Handling

## Purpose

Create predictable, secure, debuggable error behavior across the application.

## Project Stack

FastAPI, Python, Next.js, React, TypeScript.

## Operating Principles

1. Handle expected failures explicitly.
2. Do not expose stack traces or internal secrets to users.
3. Preserve useful diagnostic information in server-side logs.
4. Use consistent API error shapes.
5. Distinguish validation, authentication, authorization, not-found, conflict, dependency, and unexpected failures.
6. Do not catch broad exceptions unless there is a deliberate recovery strategy.
7. Never silently ignore errors.
8. Frontend code must provide useful user-facing failure states.
9. Retry only operations that are safe to retry.
10. Test failure paths as deliberately as success paths.

## Required Workflow

1. Reproduce the failure.
2. Capture the exact error.
3. Identify where the error crosses a system boundary.
4. Decide whether it is expected or unexpected.
5. Implement the smallest appropriate handling.
6. Test the original failure.
7. Test neighboring failure cases.
8. Review logging and information disclosure.

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
