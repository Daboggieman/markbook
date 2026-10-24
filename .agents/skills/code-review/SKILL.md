---
name: code-review
description: Use when reviewing changes, pull requests, diffs, implementations, or completed work for bugs, regressions, security problems, and maintainability issues.
---

# Code Review Skill

## Objective

Find meaningful problems before code reaches production.

## Review Order

Review in this order:

1. Correctness
2. Security
3. Data integrity
4. Error handling
5. Regression risk
6. Performance
7. Maintainability
8. Style

Correctness takes priority over stylistic preferences.

## Process

1. Inspect git status.
2. Inspect the complete diff.
3. Understand the surrounding implementation.
4. Trace affected execution paths.
5. Check edge cases.
6. Check error handling.
7. Check security implications.
8. Check compatibility with existing behavior.
9. Run relevant tests.

## Findings

For every real finding provide:

- Severity
- Location
- Problem
- Why it matters
- Concrete fix

Do not report purely stylistic preferences as bugs.

Do not invent hypothetical problems without a plausible execution path.

## Severity

Use:

- CRITICAL — severe security, data-loss, or system-breaking issue
- HIGH — major functional or security issue
- MEDIUM — meaningful defect or regression risk
- LOW — minor issue worth addressing

Do not assign severity without explaining the impact.

## Final Review

After reviewing, distinguish:

- Confirmed issues
- Potential risks
- Areas checked without findings

Never declare code safe merely because no obvious issue was found.
