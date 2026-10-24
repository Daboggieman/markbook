---
name: debugging
description: Use when software behaves incorrectly, tests fail, errors occur, builds break, or runtime behavior differs from expectations.
---

# Debugging Skill

## Objective

Find the actual cause of a problem rather than treating symptoms.

## Process

1. Reproduce the problem.
2. Capture the complete error or unexpected behavior.
3. Identify the failing layer.
4. Inspect relevant source code and configuration.
5. Trace the execution path.
6. Form a specific hypothesis.
7. Make the smallest useful change.
8. Reproduce the original failure.
9. Verify the fix.
10. Check for regressions.

## Rules

Never repeatedly execute a failing command without learning something new.

Never suppress an error simply to make a command succeed.

Never remove functionality merely to eliminate an error.

Do not assume the first error-looking message is the root cause.

Distinguish between:
- Root cause
- Contributing factor
- Secondary symptom

## Evidence

Use:
- Error messages
- Logs
- Stack traces
- Source code
- Configuration
- Runtime state
- Dependency versions
- Reproduction steps

## Regression Check

After fixing a problem:

- Re-run the original failing operation.
- Run relevant tests.
- Check related functionality.
- Inspect the final diff.

## Completion

A bug is not considered fixed until the original failure has been reproduced successfully after the change or equivalent evidence demonstrates the behavior is resolved.
