---
name: verification
description: Evidence-driven verification of implementations, dependencies, APIs, builds, tests, and runtime behavior.
---

# Verification Skill

## Purpose

Never treat an implementation as correct merely because it looks correct.

Verify important claims against the actual repository, installed dependencies, documentation, tests, or runtime behavior.

## Verification hierarchy

Prefer evidence in this order:

1. Actual runtime behavior
2. Passing tests
3. Compiler/type checker/build output
4. Installed package source/API
5. Official documentation
6. Repository configuration
7. Code inspection
8. Model knowledge

## Before declaring success

Check the smallest relevant validation set:

- changed code compiles or type-checks
- relevant tests pass
- affected API/UI behavior works
- configuration is valid
- no obvious regression was introduced

## For bugs

Reproduce first.

Record:

- exact command/action
- exact error
- affected component
- expected behavior
- actual behavior

After fixing:

1. reproduce the original failure again if practical
2. apply the smallest appropriate fix
3. rerun the failing check
4. run adjacent regression checks
5. inspect the final diff

## For dependency/API questions

Do not assume an API exists.

Verify using:

- installed package metadata/source
- Context7
- official documentation
- actual runtime behavior

Prefer version-specific evidence.

## For UI work

Use Playwright when available.

Verify:

- page loads
- relevant interaction works
- browser console/network errors
- responsive behavior when relevant
- resulting state

## For external information

Use web/fetch/Context7 when appropriate.

Distinguish:

- verified fact
- repository evidence
- documentation
- inference
- unresolved uncertainty

## Final rule

If something was not actually verified, say so explicitly.

Never report an unverified assumption as a completed result.
