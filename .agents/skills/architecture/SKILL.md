---
name: architecture
description: Use when designing systems, changing application structure, introducing services, changing data flow, or making decisions affecting multiple components.
---

# Architecture Skill

## Objective

Make architectural changes deliberately and consistently with the existing system.

## Before Designing

Inspect:

- Repository structure
- Application entry points
- Major modules
- Data flow
- APIs
- Database schema
- Configuration
- Authentication
- External services
- Deployment architecture
- Existing architectural documentation

Do not design against an imagined architecture.

## Principles

Prefer:

- Simple designs
- Existing project conventions
- Clear boundaries
- Minimal coupling
- Explicit interfaces
- Testable components
- Incremental changes

Avoid:

- Unnecessary microservices
- Premature abstractions
- Duplicate systems
- New infrastructure without justification
- Large rewrites when incremental change is possible

## Change Analysis

For architectural changes identify:

1. Current architecture
2. Proposed architecture
3. Components affected
4. Data flow
5. Dependencies
6. Migration requirements
7. Failure modes
8. Security implications
9. Testing strategy
10. Rollback strategy

## Compatibility

Consider:

- Existing users
- Existing data
- Existing APIs
- Existing clients
- Deployment environment
- Backward compatibility

## Decision Records

For significant architectural decisions, document:

- Context
- Decision
- Alternatives considered
- Consequences

## Completion

The resulting architecture should be understandable from the repository documentation without relying on hidden assumptions.
