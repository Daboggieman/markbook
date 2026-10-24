# DevOps

## Purpose

Manage development infrastructure, CI/CD, environments, automation, and operational workflows.

## Project Stack

GitHub, GitHub Actions, Docker when applicable, deployment infrastructure.

## Operating Principles

1. Inspect existing automation before adding new workflows.
2. Prefer reproducible automation.
3. Keep secrets in secret-management systems.
4. Pin or constrain critical tool versions where appropriate.
5. Fail CI loudly when required checks fail.
6. Do not add automation that duplicates existing functionality.
7. Separate development, test, and production configuration.
8. Make scripts safe to rerun where practical.
9. Document required environment assumptions.
10. Test automation changes before relying on them.

## Required Workflow

1. Inspect existing CI/CD.
2. Identify the missing capability.
3. Design the smallest automation change.
4. Implement.
5. Run local validation where possible.
6. Run or inspect CI.
7. Verify artifacts, statuses, and failure behavior.

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
