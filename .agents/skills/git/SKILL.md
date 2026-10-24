---
name: git
description: Use when inspecting repository state, creating branches, preparing commits, resolving Git problems, reviewing diffs, or performing version-control operations.
---

# Git Skill

## Objective

Perform safe, deliberate Git operations while preserving user work.

## Before Changes

Run:

git status

Understand:
- Current branch
- Modified files
- Untracked files
- Staged files

Never assume the working tree is clean.

## Before Committing

Inspect:

git diff
git diff --cached

Ensure only intended changes are included.

## Branching

Before creating or switching branches:

- Check current branch.
- Check working-tree state.
- Preserve uncommitted work.
- Use descriptive branch names.

## Commits

Create focused commits.

A commit should represent one coherent change.

Do not include unrelated modifications.

Commit messages should describe the actual change.

## Destructive Operations

Treat these as high-risk:

- git reset --hard
- git clean
- git checkout -- file
- git restore --source
- force push
- branch deletion
- history rewriting

Never use them casually.

Before destructive operations, determine exactly what would be lost.

## Remote Operations

Before pushing:

- Verify the branch.
- Inspect the diff.
- Confirm the intended remote.
- Confirm the intended destination branch.

Do not force push unless explicitly required.

## Merge and Rebase

Before resolving conflicts:

- Understand both sides.
- Preserve intended functionality.
- Inspect the resulting diff.
- Run tests afterward.

## Completion

After important Git operations, verify:

git status

Never claim a commit or push succeeded without checking the command result.
