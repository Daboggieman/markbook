# Accessibility

## Purpose

Ensure Cee-Tailor interfaces are usable with keyboard navigation, assistive technologies, and varied user needs.

## Project Stack

Next.js, React, semantic HTML, Tailwind, Playwright.

## Operating Principles

1. Prefer semantic HTML before ARIA.
2. Every meaningful form control needs an accessible name.
3. Keyboard navigation must work for interactive controls.
4. Do not use color alone to communicate important state.
5. Maintain visible focus indicators.
6. Use correct heading hierarchy.
7. Provide meaningful labels and error messages.
8. Ensure dialogs and menus have appropriate focus behavior.
9. Images need appropriate alternative text when informative.
10. Decorative images should not create unnecessary screen-reader noise.
11. Verify accessibility behavior in the browser.

## Required Workflow

1. Inspect the affected UI.
2. Check semantic structure.
3. Check keyboard behavior.
4. Check labels, focus, errors, and announcements.
5. Use Playwright where useful.
6. Fix accessibility issues without unnecessary redesign.
7. Re-test the complete interaction.

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
