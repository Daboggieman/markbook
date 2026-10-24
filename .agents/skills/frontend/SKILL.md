# Frontend Engineering

## Purpose

Build reliable Next.js and React interfaces that follow the Cee-Tailor frontend architecture.

## Project Stack

Next.js App Router, React, TypeScript, Tailwind CSS, React Query, React Hook Form, Zod, Framer Motion.

## Operating Principles

1. Inspect the existing App Router structure before adding pages or components.
2. Reuse existing components and design primitives before creating duplicates.
3. Keep server/client boundaries deliberate.
4. Use TypeScript types instead of implicit any.
5. Use React Query consistently for server-state management where the project uses it.
6. Use React Hook Form and Zod consistently for complex forms.
7. Validate user input on the client for UX but never rely on client validation for security.
8. Keep loading, empty, success, and error states explicit.
9. Do not introduce unnecessary client components.
10. Preserve responsive behavior.
11. Do not claim UI behavior without browser verification when the change is visual or interactive.

## Required Workflow

1. Inspect route and component architecture.
2. Identify reusable components and existing patterns.
3. Trace required API contracts.
4. Implement the smallest coherent UI change.
5. Run TypeScript/build checks.
6. Use Playwright for important interactive or visual behavior.
7. Verify responsive and failure states.
8. Review accessibility.
9. Inspect the final diff.

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
