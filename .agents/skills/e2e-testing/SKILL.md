# End-to-End Testing

## Purpose

Verify complete user workflows through the real frontend and backend integration.

## Project Stack

Playwright, Next.js, FastAPI.

## Operating Principles

1. Test user-visible behavior rather than implementation details.
2. Use stable selectors.
3. Cover critical business workflows.
4. Include important validation and failure states.
5. Keep tests independent where practical.
6. Do not use arbitrary sleeps when reliable waits are available.
7. Clean up test data appropriately.
8. Keep authentication setup reusable and secure.
9. Do not claim an E2E workflow passes without actually executing it.

## Required Workflow

1. Identify the user journey.
2. Define prerequisites and test data.
3. Write the smallest useful test.
4. Run it against the actual application.
5. Investigate failures rather than weakening assertions.
6. Check browser console/network evidence when useful.
7. Keep the test deterministic.
8. Record the verification result.

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
