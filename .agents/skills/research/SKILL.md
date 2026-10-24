---
name: research
description: Use when answering technical questions, investigating unfamiliar code, checking APIs, resolving uncertainty, or when current documentation or external information matters.
---

# Research Skill

## Objective

Replace assumptions with evidence.

## Evidence Hierarchy

Prefer evidence in this order:

1. Current repository source code
2. Installed package/source code
3. Official documentation
4. Official project repositories
5. Maintainer documentation
6. Reliable technical references
7. Community discussions when necessary

## Process

1. Define the exact question.
2. Search the repository first.
3. Inspect installed versions when relevant.
4. Check official documentation when behavior is version-dependent.
5. Compare evidence from multiple sources when uncertainty remains.
6. Form the answer from observed evidence.

## Anti-Hallucination Rules

Never invent:

- APIs
- CLI flags
- configuration options
- package behavior
- framework behavior
- file paths
- environment variables
- version compatibility
- undocumented features

If something cannot be verified, say so.

## Version Awareness

When investigating software:

- Determine the installed version.
- Prefer documentation matching that version.
- Do not silently apply behavior from another major version.

## Repository Research

When the repository can answer the question:

- Search it.
- Read the relevant implementation.
- Follow imports and references when necessary.

Do not replace repository evidence with generic knowledge.

## Output

Separate:

- Verified facts
- Reasonable inferences
- Unverified possibilities

Never present an inference as a verified fact.
