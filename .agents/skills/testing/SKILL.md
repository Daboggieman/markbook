---
name: testing
description: Use when implementing features, fixing bugs, validating changes, or determining how a project should be tested.
---

# Testing Skill

## Objective

Obtain evidence that a change works and does not break existing behavior.

## Test Selection

Choose tests based on the change:

- Unit tests for isolated logic.
- Integration tests for component interaction.
- API tests for endpoints.
- UI tests for user-facing flows.
- Type checking for typed projects.
- Linting for static quality checks.
- Build checks for compilation and packaging.
- Runtime checks for environment-dependent behavior.

## Process

1. Inspect existing test infrastructure.
2. Identify tests covering the affected behavior.
3. Add or modify tests when appropriate.
4. Run the smallest relevant test first.
5. Run broader validation when practical.
6. Investigate failures rather than ignoring them.

## Test Quality

Tests should verify behavior, not implementation details unnecessarily.

Prefer tests that:
- Reproduce the reported bug.
- Cover important edge cases.
- Verify user-visible behavior.
- Remain stable under reasonable refactoring.

## Failure Handling

When tests fail:

- Read the complete failure.
- Determine whether the failure is caused by the change.
- Fix the implementation or update the test only when the expected behavior genuinely changed.
- Never weaken a test merely to obtain a passing result.

## Completion

Report exactly which validation commands were executed and whether they passed.
