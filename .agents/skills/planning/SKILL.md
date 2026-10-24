---
name: planning
description: Use when a task is non-trivial, spans multiple files, changes architecture, or has unclear implementation steps. Produces an evidence-based implementation plan before coding.
---

# Planning Skill

## Objective

Turn a user request into a precise, executable engineering plan.

## Process

1. Understand the requested outcome.
2. Inspect the repository before proposing implementation details.
3. Identify relevant files, modules, dependencies, APIs, and configuration.
4. Search for existing implementations that can be reused.
5. Identify constraints and potential side effects.
6. Determine the smallest coherent set of changes.
7. Define validation requirements.

## Repository Inspection

Before planning implementation:

- Check git status.
- Inspect the repository structure.
- Search for relevant symbols, routes, components, services, schemas, and configuration.
- Read the relevant existing code.
- Inspect tests when available.

Do not invent files or architecture.

## Plan Format

For substantial tasks, produce:

### Goal
What the final state should accomplish.

### Current State
What currently exists and is relevant.

### Changes
List each required change and the file/module involved.

### Implementation
Describe the implementation sequence.

### Validation
Specify exactly how the result will be tested.

### Risks
Identify compatibility, security, migration, or regression risks.

## Planning Rules

- Prefer existing project patterns.
- Avoid unnecessary refactors.
- Avoid introducing dependencies without justification.
- Keep unrelated functionality untouched.
- Do not begin implementation until the plan is sufficiently understood.
- If information is missing, inspect the repository before asking the user.

## Completion Criteria

A plan is complete when another competent developer could implement the task from it without needing to rediscover the architecture.
