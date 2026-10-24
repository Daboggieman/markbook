---
name: security
description: Use when implementing, reviewing, debugging, or researching authentication, authorization, secrets, user data, APIs, dependencies, file handling, or other security-sensitive code.
---

# Security Skill

## Objective

Identify and prevent realistic security vulnerabilities.

## Review Areas

Check for:

- Authentication bypass
- Authorization failures
- Secret exposure
- Injection vulnerabilities
- Unsafe deserialization
- Path traversal
- Command injection
- Cross-site scripting
- CSRF
- Insecure file uploads
- Sensitive information leakage
- Weak session handling
- Unsafe redirects
- Dependency vulnerabilities
- Excessive permissions
- Insecure defaults

Only report issues supported by the implementation.

## Secrets

Never expose or commit:

- API keys
- Passwords
- Tokens
- Private keys
- Session cookies
- Credentials
- Production secrets

Check configuration and environment handling.

## Input Handling

Treat external input as untrusted.

Trace input through:
- Validation
- Parsing
- Business logic
- Database operations
- Shell commands
- HTML rendering
- File operations
- External APIs

## Authentication

Verify:

- Credentials are validated correctly.
- Sessions/tokens are handled securely.
- Protected routes enforce authentication.
- Authorization is checked independently of authentication.
- Users cannot access another user's resources.

## Dependencies

When a security issue involves a dependency:

- Identify the installed version.
- Check whether the issue applies to that version.
- Prefer official security advisories.

## Reporting

For each confirmed issue provide:

- Severity
- Location
- Attack/trigger condition
- Impact
- Recommended fix

Do not exaggerate theoretical risks.

## Verification

After security changes:
- Re-run relevant tests.
- Check the affected path.
- Inspect the final diff.
- Confirm secrets were not introduced.
