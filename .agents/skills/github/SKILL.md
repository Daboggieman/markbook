---

name: github
description: Comprehensive GitHub engineering skill for repository inspection, remote state analysis, branches, commits, pull requests, issues, GitHub Actions, CI/CD, releases, repository configuration, API operations, security, troubleshooting, and verified GitHub workflows using the authenticated GitHub CLI.
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# GitHub Engineering Skill

## 1. Purpose

This skill defines how the coding agent interacts with GitHub for the Cee-Tailor project.

The agent must treat GitHub as a remote engineering system rather than merely a place to push commits.

GitHub operations can involve:

* repositories
* branches
* commits
* pull requests
* reviews
* issues
* labels
* milestones
* projects
* GitHub Actions
* workflows
* checks
* releases
* tags
* environments
* deployment state
* repository configuration
* permissions
* secrets
* variables
* collaborators
* branch protection
* rulesets
* webhooks
* GitHub API resources

The agent must use evidence from the actual repository and GitHub whenever the task depends on current remote state.

---

# 2. Core Operating Principle

Use:

> INSPECT → UNDERSTAND → PLAN → ACT → VALIDATE → VERIFY → REPORT

Never:

> ASSUME → ACT → CLAIM SUCCESS

The agent must not infer remote GitHub state from local files, previous conversations, model memory, or assumptions.

---

# 3. Git vs GitHub

Git and GitHub are related but different systems.

## Git

Git manages the local repository and its history.

Examples:

```bash
git status
git branch
git log
git diff
git commit
git fetch
git push
git pull
```

## GitHub

GitHub provides the remote repository and collaboration infrastructure.

Examples:

```bash
gh repo view
gh pr list
gh issue list
gh run list
gh release list
gh api
```

The agent must distinguish:

* local working tree
* local branches
* local commits
* remote Git refs
* GitHub repository state
* pull request state
* CI state
* deployment state

A successful local Git command does not automatically prove that the corresponding GitHub operation succeeded.

---

# 4. Tool Selection

Use the smallest toolset that establishes reliable evidence.

## Use Git when:

* inspecting local changes
* creating branches
* inspecting commits
* staging files
* committing
* fetching
* pushing
* inspecting local history
* comparing branches

## Use GitHub CLI when:

* inspecting GitHub repositories
* inspecting PRs
* inspecting issues
* inspecting Actions
* inspecting releases
* inspecting GitHub checks
* querying GitHub's API
* creating or updating GitHub resources
* verifying remote GitHub state

## Use Filesystem MCP when:

* exploring project files
* reading local source
* inspecting configuration
* inspecting workflow definitions
* locating implementation details

## Use Context7 when:

* current library/API behavior matters
* version-specific behavior matters
* a GitHub-related dependency requires documentation

## Use Fetch when:

* official documentation needs to be retrieved
* Context7 does not provide the required information
* a public web resource must be inspected

## Use Playwright when:

* a GitHub-hosted frontend must be tested through a browser
* an application deployment must be validated through its UI
* a web-based workflow needs browser verification

---

# 5. Authentication

Before GitHub operations that require authentication:

```bash
gh auth status
```

If authentication is unavailable:

1. Stop the GitHub operation.
2. Report the authentication problem.
3. Do not request credentials in chat.
4. Do not print tokens.
5. Do not create replacement authentication mechanisms.
6. Do not bypass authentication.

GitHub CLI supports authenticated commands through its configured authentication mechanisms.

Never expose:

```bash
gh auth token
```

output in an agent report.

Never place GitHub credentials inside:

```text
.claude/
.env
.env.local
source code
scripts
README files
skill files
commit messages
PR descriptions
```

---

# 6. Authentication Verification

Use:

```bash
gh auth status
```

If the task requires repository access:

```bash
gh repo view
```

Authentication alone is not proof of repository access.

Both may need to be verified.

---

# 7. Repository Identification

Before repository-specific operations:

```bash
gh repo view
```

For structured information:

```bash
gh repo view --json name,nameWithOwner,owner,url,isPrivate,defaultBranchRef
```

Use the returned repository identity.

Do not assume:

* owner
* repository name
* default branch
* visibility
* remote URL

when the CLI can determine them.

---

# 8. Explicit Repository Targeting

When operating on a repository other than the current repository, explicitly identify it:

```bash
gh <command> --repo OWNER/REPO
```

or:

```bash
gh api repos/OWNER/REPO
```

Do not accidentally operate on another repository because of:

* current working directory
* `GH_REPO`
* shell state
* copied commands
* stale context

Before consequential operations, verify the repository target.

---

# 9. Local Repository Baseline

Before modifying GitHub-related project state:

```bash
git status --short
git branch --show-current
git remote -v
```

Then inspect recent history:

```bash
git log --oneline --decorate -10
```

For modifications:

```bash
git diff
```

For staged modifications:

```bash
git diff --cached
```

---

# 10. Preserve Unrelated User Changes

If the working tree already contains unrelated modifications:

* do not discard them
* do not reset them
* do not overwrite them
* do not stage them accidentally
* do not include them in a commit unless requested

Before staging:

```bash
git status --short
```

Inspect individual files before adding them.

---

# 11. Repository State Model

When investigating a GitHub task, determine which state is relevant.

## State A — Working tree

Question:

> What has the user changed locally?

Use:

```bash
git status
git diff
```

## State B — Local Git history

Question:

> What commits exist locally?

Use:

```bash
git log
```

## State C — Remote Git refs

Question:

> What branches/tags exist on the configured remote?

Use:

```bash
git ls-remote
```

## State D — GitHub repository

Question:

> What does GitHub currently report?

Use:

```bash
gh repo view
gh api
```

## State E — Pull request

Question:

> What is the PR state?

Use:

```bash
gh pr view
gh pr checks
```

## State F — CI

Question:

> Did GitHub Actions actually execute successfully?

Use:

```bash
gh run list
gh run view
```

## State G — Deployment

Question:

> Did the deployment actually complete?

Use:

* GitHub Actions
* deployment provider
* application runtime
* Playwright where appropriate

Never substitute one state for another.

---

# 12. Branch Management

Inspect local branches:

```bash
git branch
```

Inspect remote branches:

```bash
git branch -r
```

Inspect the GitHub branch list:

```bash
gh api repos/{owner}/{repo}/branches
```

Inspect a specific branch:

```bash
gh api repos/{owner}/{repo}/branches/{branch}
```

---

# 13. Creating Branches

Before creating a branch:

```bash
git status --short
git branch --show-current
```

Create:

```bash
git switch -c <branch-name>
```

Use descriptive branch names.

Examples:

```text
feature/customer-measurements
feature/admin-dashboard
fix/authentication-redirect
fix/order-validation
refactor/api-client
docs/setup-guide
test/checkout-flow
```

Do not create meaningless names such as:

```text
test
new
branch2
stuff
fix-final
final-final
```

unless the user explicitly requests them.

---

# 14. Branch Naming

Prefer:

```text
<type>/<short-description>
```

Common types:

```text
feature/
fix/
refactor/
docs/
test/
chore/
security/
perf/
```

The branch name should communicate intent.

---

# 15. Pushing a New Branch

After validation:

```bash
git push -u origin <branch>
```

Verify:

```bash
git ls-remote --heads origin <branch>
```

Then optionally verify through GitHub:

```bash
gh api repos/{owner}/{repo}/branches/<branch>
```

Do not report:

> branch successfully pushed

until remote verification has succeeded.

---

# 16. Branch Deletion

Deleting branches is potentially destructive.

Never delete a branch unless explicitly authorized.

Before deletion:

```bash
git branch --show-current
```

Verify the target branch.

For remote deletion:

```bash
git push origin --delete <branch>
```

Afterward verify:

```bash
git ls-remote --heads origin <branch>
```

An empty result is evidence that the remote Git ref is gone.

---

# 17. Force Push

Never use:

```bash
git push --force
```

unless explicitly authorized.

Prefer:

```bash
git push --force-with-lease
```

when force-pushing has been explicitly authorized and is technically necessary.

Before force-pushing:

1. identify the branch
2. inspect the current remote state
3. inspect local commits
4. determine what history will be replaced
5. confirm authorization

Never force-push to the default branch unless explicitly requested and justified.

---

# 18. Commit Inspection

Inspect:

```bash
git log --oneline --decorate -20
```

Inspect a commit:

```bash
git show <commit>
```

Inspect changed files:

```bash
git show --stat <commit>
```

Inspect a remote commit through GitHub:

```bash
gh api repos/{owner}/{repo}/commits/<sha>
```

Do not claim a commit exists remotely without verifying remote state.

---

# 19. Commit Verification

After:

```bash
git push
```

verify the branch:

```bash
git ls-remote --heads origin <branch>
```

If the exact commit matters:

```bash
git ls-remote origin <branch>
```

Then compare the returned SHA with the intended commit.

---

# 20. Pull Request Discovery

List PRs:

```bash
gh pr list
```

List more:

```bash
gh pr list --limit 50
```

Search PRs:

```bash
gh search prs "<query>" --repo OWNER/REPO
```

Check the PR associated with the current branch:

```bash
gh pr status
```

---

# 21. Pull Request Inspection

View:

```bash
gh pr view <number>
```

Structured:

```bash
gh pr view <number> \
  --json number,title,state,author,headRefName,baseRefName,isDraft,mergeable,statusCheckRollup,url
```

Inspect comments when necessary:

```bash
gh pr view <number> --comments
```

Inspect the diff:

```bash
gh pr diff <number>
```

Inspect changed file names:

```bash
gh pr diff <number> --name-only
```

---

# 22. Pull Request Investigation

When investigating a PR:

1. identify the repository
2. identify the PR number
3. inspect title/body
4. inspect source branch
5. inspect target branch
6. inspect commits
7. inspect changed files
8. inspect diff
9. inspect checks
10. inspect reviews
11. inspect comments
12. inspect merge state
13. inspect conflicts if relevant
14. inspect linked issues if relevant

Do not review only the PR title.

---

# 23. Creating Pull Requests

Before creating a PR:

```bash
git status --short
git branch --show-current
git diff
git log --oneline --decorate -10
```

Run relevant validation.

Then push the branch:

```bash
git push -u origin <branch>
```

Create:

```bash
gh pr create
```

For explicit control:

```bash
gh pr create \
  --base <base> \
  --head <head> \
  --title "<title>" \
  --body "<body>"
```

GitHub CLI supports `gh pr create` with explicit base/head/title/body and can also use repository defaults when not explicitly supplied.

---

# 24. Pull Request Description Quality

A PR body should normally contain:

## Summary

What changed?

## Problem

Why was the change necessary?

## Implementation

What was changed technically?

## Validation

What was tested?

## Risk

What could potentially be affected?

## Verification

What was actually verified?

Do not claim tests were run if they were not run.

---

# 25. PR Title Rules

Prefer titles that describe the actual change.

Good:

```text
Add customer measurement persistence
Fix order creation validation
Implement admin order filtering
Add Playwright checkout coverage
```

Avoid:

```text
Update stuff
Fix things
Changes
Final fix
Important
```

---

# 26. Draft Pull Requests

Use draft PRs when implementation is incomplete but remote collaboration is useful:

```bash
gh pr create --draft
```

Do not mark a PR ready merely because the code compiles.

Before:

```bash
gh pr ready
```

verify:

* implementation complete
* tests complete
* review complete
* no known blocking errors
* intended CI checks are available

---

# 27. Pull Request Checks

Inspect:

```bash
gh pr checks <number>
```

Possible states include:

* queued
* in progress
* successful
* failed
* cancelled
* skipped

Do not call queued or running checks successful.

---

# 28. Pull Request Review

Inspect:

```bash
gh pr diff <number>
```

Then inspect relevant project files locally.

Review:

* correctness
* architecture
* error handling
* security
* type safety
* API contracts
* tests
* performance
* maintainability
* backwards compatibility
* database implications
* frontend behavior
* accessibility where applicable

Use the existing `code-review`, `security`, `testing`, and `verification` skills when relevant.

---

# 29. Review Comments

When reporting review findings, use evidence.

Each significant finding should identify:

* file
* relevant code
* problem
* consequence
* recommended direction

Do not manufacture issues merely to make the review appear thorough.

---

# 30. Approving PRs

Approval is a consequential GitHub action.

Do not approve a PR unless explicitly authorized.

If asked to review but not approve:

* inspect
* report findings
* do not submit approval

---

# 31. Requesting Changes

Requesting changes is also a consequential GitHub action.

Only do so when explicitly authorized.

Before requesting changes:

```bash
gh pr diff <number>
gh pr checks <number>
```

Base findings on concrete evidence.

---

# 32. Merging Pull Requests

Merging is consequential.

Never merge automatically unless the user explicitly requests it.

Before merging:

```bash
gh pr view <number>
gh pr checks <number>
```

Verify:

* correct repository
* correct PR
* correct base branch
* expected head branch
* required checks
* review requirements
* mergeability
* intended merge strategy

Possible strategies include:

```text
merge
squash
rebase
```

Use the strategy explicitly requested by the user.

If none is specified, do not silently make a consequential choice when the choice matters.

---

# 33. Merge Verification

After merging:

```bash
gh pr view <number>
```

Verify the PR state.

If branch deletion was requested, verify it separately.

Do not report:

> merged successfully

based solely on the command returning without an obvious error.

---

# 34. Issues

List:

```bash
gh issue list
```

View:

```bash
gh issue view <number>
```

Structured:

```bash
gh issue view <number> \
  --json number,title,state,author,labels,assignees,url
```

Search:

```bash
gh search issues "<query>" --repo OWNER/REPO
```

---

# 35. Creating Issues

Create only when explicitly requested:

```bash
gh issue create
```

Or:

```bash
gh issue create \
  --title "<title>" \
  --body "<body>"
```

A useful issue should contain:

* problem
* expected behavior
* actual behavior
* reproduction steps
* environment
* evidence
* relevant logs
* acceptance criteria

Do not create an issue simply because a problem was discovered unless the workflow calls for it.

---

# 36. Closing Issues

Closing is consequential.

Only close when explicitly authorized.

Before closing:

```bash
gh issue view <number>
```

Understand why it is being closed.

After closing:

```bash
gh issue view <number>
```

Verify the final state.

---

# 37. Issue Comments

Comment only when required.

Use:

```bash
gh issue comment <number> --body "<comment>"
```

Do not post speculative statements as facts.

Do not post credentials, tokens, private data, or secrets.

---

# 38. Issue Linking

When appropriate, link implementation to issues through PR descriptions.

Examples:

```text
Fixes #123
Closes #123
```

Do not claim an issue will close unless the GitHub semantics actually support the reference being used.

---

# 39. GitHub Actions

List workflow runs:

```bash
gh run list
```

List more:

```bash
gh run list --limit 50
```

Inspect:

```bash
gh run view <run-id>
```

Inspect failed logs:

```bash
gh run view <run-id> --log-failed
```

Watch:

```bash
gh run watch <run-id>
```

---

# 40. CI Failure Investigation

When CI fails:

## Step 1

Identify the failed run:

```bash
gh run list
```

## Step 2

Inspect:

```bash
gh run view <run-id>
```

## Step 3

Inspect failed logs:

```bash
gh run view <run-id> --log-failed
```

## Step 4

Identify:

* workflow
* job
* step
* command
* exact error

## Step 5

Inspect the corresponding local workflow.

## Step 6

Determine whether the problem is:

* application code
* dependency
* test
* environment
* workflow configuration
* secret/configuration
* permissions
* network
* external service

## Step 7

Reproduce locally where possible.

## Step 8

Fix the smallest root cause.

## Step 9

Validate locally.

## Step 10

Push.

## Step 11

Verify the new GitHub Actions run.

---

# 41. CI Completion Rule

Never say:

> CI is fixed.

until a new relevant run has been inspected.

Correct reporting:

> The previous run failed because X. The workflow was changed to Y. A new run was triggered, and run Z completed successfully.

If the new run is still running:

> The fix has been pushed and the new CI run is still in progress.

---

# 42. Workflow Inspection

List workflows:

```bash
gh workflow list
```

View a workflow:

```bash
gh workflow view <workflow>
```

Inspect workflow files locally:

```bash
find .github/workflows -type f -maxdepth 1 -print
```

Read the relevant YAML before modifying it.

---

# 43. Running Workflows

A workflow can be manually dispatched only when appropriate and supported.

Before dispatching:

1. identify exact workflow
2. inspect its inputs
3. confirm target branch/ref
4. understand consequences

Use:

```bash
gh workflow run <workflow>
```

When branch/ref matters, specify it explicitly.

After dispatch:

```bash
gh run list
```

Find the resulting run and verify it.

---

# 44. Cancelling Workflows

Cancellation is consequential.

Only cancel when authorized.

Before cancellation:

```bash
gh run view <run-id>
```

Then:

```bash
gh run cancel <run-id>
```

Verify:

```bash
gh run view <run-id>
```

---

# 45. Re-running Workflows

Only rerun when appropriate.

Understand whether the failure is transient or deterministic.

A rerun is not a fix.

If a workflow fails due to code/configuration, fix the cause instead of repeatedly rerunning it.

---

# 46. GitHub Actions Security

When inspecting workflows, look for:

* excessive permissions
* secret exposure
* untrusted input
* shell injection
* unsafe interpolation
* untrusted pull request code
* inappropriate event triggers
* dependency installation
* third-party actions
* mutable action tags
* unsafe artifact handling
* unsafe deployment credentials

Do not modify security-sensitive workflows casually.

Use the `security` skill when the issue is significant.

---

# 47. Action Versioning

When encountering:

```yaml
uses: owner/action@...
```

determine what reference is being used.

Possible references include:

* tag
* branch
* commit SHA

Do not blindly upgrade Actions.

When current behavior matters, research official documentation.

---

# 48. Releases

List:

```bash
gh release list
```

View:

```bash
gh release view <tag>
```

Structured:

```bash
gh release view <tag> \
  --json name,tagName,isDraft,isPrerelease,publishedAt,url
```

Creating a release is consequential.

Only do so when explicitly requested.

---

# 49. Release Validation

Before creating a release verify:

* intended commit
* intended tag
* tests
* build
* version
* changelog
* release artifacts
* deployment implications

After publishing:

```bash
gh release view <tag>
```

Verify:

* release exists
* correct tag
* correct status
* correct assets
* expected publication state

---

# 50. Tags

Inspect local tags:

```bash
git tag
```

Inspect remote tags:

```bash
git ls-remote --tags origin
```

Do not create/delete tags without authorization.

A release and a tag are related but not identical concepts.

---

# 51. GitHub API

Use `gh api` when the dedicated CLI commands do not expose enough information.

GitHub CLI's `gh api` performs authenticated GitHub API requests and supports options such as JSON filtering, pagination, custom methods, fields, headers, and request bodies.

Example:

```bash
gh api repos/{owner}/{repo}
```

Example:

```bash
gh api repos/{owner}/{repo}/branches
```

Example:

```bash
gh api repos/{owner}/{repo}/actions/runs
```

---

# 52. API Placeholder Rules

Within a repository, placeholders such as:

```text
{owner}
{repo}
{branch}
```

can be resolved by GitHub CLI in supported contexts.

Do not rely on that behavior blindly.

When clarity matters, use explicit values.

---

# 53. API Read Operations

Prefer GET/read operations when investigating.

Examples:

```bash
gh api repos/{owner}/{repo}
```

```bash
gh api repos/{owner}/{repo}/pulls
```

```bash
gh api repos/{owner}/{repo}/issues
```

```bash
gh api repos/{owner}/{repo}/actions/runs
```

Read before write.

---

# 54. API Write Operations

API writes include:

* POST
* PATCH
* PUT
* DELETE

Treat them as consequential.

Before performing a write:

1. identify target
2. identify endpoint
3. identify method
4. identify payload
5. confirm authorization
6. execute
7. verify resulting state

Never use a write request merely because it is technically available.

---

# 55. API Pagination

When a result can contain many records, consider pagination.

Example:

```bash
gh api --paginate repos/{owner}/{repo}/issues
```

Do not assume the first page contains the complete dataset.

---

# 56. API Filtering

Use `--jq` when structured output is required:

```bash
gh api repos/{owner}/{repo} --jq '.full_name'
```

For machine-readable output, prefer JSON or structured output over parsing human-formatted text.

---

# 57. API Troubleshooting

If `gh api` fails:

1. inspect the exact HTTP/API error
2. verify authentication
3. verify repository
4. verify endpoint
5. verify method
6. verify permissions
7. verify request payload
8. verify API documentation if behavior is uncertain

Do not blindly retry destructive requests.

---

# 58. GitHub Search

Search repository code:

```bash
gh search code "<query>" --repo OWNER/REPO
```

Search issues:

```bash
gh search issues "<query>" --repo OWNER/REPO
```

Search PRs:

```bash
gh search prs "<query>" --repo OWNER/REPO
```

Search repositories:

```bash
gh search repos "<query>"
```

Search is discovery, not proof.

After finding a relevant result, inspect the actual object.

---

# 59. Repository File Inspection

If remote file contents are required:

```bash
gh api repos/{owner}/{repo}/contents/{path}
```

For a branch:

```bash
gh api "repos/{owner}/{repo}/contents/{path}?ref=<branch>"
```

Use local filesystem tools when the local repository is authoritative for the task.

Use GitHub API when the remote version matters.

---

# 60. GitHub Configuration

Repository configuration can include:

* Actions
* variables
* secrets
* rulesets
* environments
* branch protection
* permissions
* labels
* collaborators
* project settings

Configuration changes are high-impact.

Inspect before modifying.

Never change repository settings without explicit authorization.

---

# 61. Secrets

Never retrieve and display secret values.

Never place secret values in:

* logs
* PRs
* issues
* commits
* source files
* skill files

When a secret is required, use the appropriate GitHub secret mechanism.

When inspecting secret configuration, verify existence/status without exposing values whenever possible.

---

# 62. Accidental Secret Detection

Before pushing:

```bash
git diff
git status --short
```

Look for:

```text
API_KEY=
TOKEN=
PASSWORD=
SECRET=
PRIVATE_KEY
DATABASE_URL=
```

Also inspect suspicious files.

If a secret is found:

1. stop
2. do not push
3. determine whether it has already been committed
4. notify the user
5. rotate the credential if exposure occurred
6. remove it safely
7. verify repository history as necessary

Do not simply delete the current copy if the secret already exists in Git history.

---

# 63. GitHub Environment Variables

Distinguish:

* local `.env`
* GitHub Actions variables
* GitHub Actions secrets
* repository variables
* environment variables
* organization-level configuration

Never assume one is automatically available in another environment.

---

# 64. Deployment Verification

A successful GitHub Actions workflow does not automatically prove the deployed application is functioning.

Deployment verification may require:

1. GitHub Actions verification
2. deployment provider verification
3. runtime health check
4. API verification
5. browser verification

Use Playwright when UI behavior needs verification.

Use backend/runtime tests for APIs.

---

# 65. Deployment Failure Investigation

Determine:

* workflow failure?
* build failure?
* deployment failure?
* environment configuration?
* database migration?
* runtime crash?
* health check failure?
* DNS?
* external service?

Do not collapse these into "deployment failed" without evidence.

---

# 66. Repository Health Check

When asked to assess repository health, inspect:

```bash
git status --short
git branch --show-current
git remote -v
git log --oneline --decorate -10
gh repo view
gh pr status
gh issue status
gh run list
```

Then inspect relevant project configuration.

Report each category independently.

---

# 67. GitHub Status Investigation

For a broad question such as:

> What's happening with this repository?

Inspect:

```bash
gh repo view
gh pr list
gh issue list
gh run list
```

Then determine:

* current branch
* active PRs
* open issues
* recent CI activity
* recent releases
* local uncommitted changes

Do not provide a vague summary when concrete state is available.

---

# 68. GitHub + Git Recovery

If local Git history and GitHub state appear inconsistent:

Do not immediately reset anything.

First inspect:

```bash
git status
git branch -avv
git remote -v
git log --all --decorate --graph --oneline -30
git ls-remote origin
```

Then inspect GitHub:

```bash
gh repo view
gh pr list
```

Determine:

* local-only commits
* remote-only commits
* divergent branches
* missing refs
* unrelated histories
* deleted branches
* incorrect upstream tracking

Only then plan recovery.

---

# 69. Unrelated Histories

If Git reports:

```text
fatal: refusing to merge unrelated histories
```

Do not immediately use:

```bash
git pull --allow-unrelated-histories
```

First determine why the histories are unrelated.

Inspect:

```bash
git log --all --graph --decorate --oneline
git remote -v
git branch -avv
```

Inspect the GitHub repository:

```bash
gh repo view
```

Determine whether:

* wrong remote
* wrong branch
* repository reinitialization
* independent history
* accidental repository replacement
* branch mismatch

Only then choose a recovery strategy.

---

# 70. Remote Branch Conflicts

If a remote branch exists unexpectedly:

```bash
git ls-remote --heads origin
```

Inspect GitHub:

```bash
gh api repos/{owner}/{repo}/branches
```

Do not delete or overwrite the branch before understanding its purpose.

---

# 71. Push Rejection

If:

```bash
git push
```

is rejected:

Determine whether it is:

* non-fast-forward
* permissions
* protected branch
* authentication
* remote hook
* workflow policy
* repository rule

Inspect:

```bash
git status
git branch -vv
git fetch origin
```

Then inspect GitHub state if needed.

Never force-push as the first response.

---

# 72. Protected Branches and Rules

If GitHub rejects a push or merge because of repository rules:

Do not attempt to bypass them.

Inspect the relevant PR/check/rules state.

If necessary, use the intended workflow:

```text
branch → PR → checks → review → merge
```

Repository protection is a constraint to work with, not something to circumvent.

---

# 73. GitHub Actions Permissions

When Actions fail due to permissions:

Inspect the workflow's:

```yaml
permissions:
```

and relevant GitHub configuration.

Use least privilege.

Do not grant:

```yaml
permissions: write-all
```

as a generic fix.

Grant only the permission required by the operation.

---

# 74. Dependency Changes Through GitHub

When a GitHub workflow requires a dependency change:

1. identify dependency
2. inspect package manager
3. inspect current version
4. inspect lockfile
5. research current documentation if necessary
6. make minimal change
7. run tests
8. inspect diff
9. push
10. verify CI

Do not upgrade unrelated dependencies.

---

# 75. GitHub Actions Dependency Failures

If a CI job fails because a package/action changed:

Determine:

* exact dependency
* installed version
* requested version
* lockfile state
* runtime version
* operating system
* relevant GitHub runner
* official documentation

Do not assume the latest version is compatible.

---

# 76. GitHub Documentation Research

When GitHub behavior is uncertain:

Prefer:

1. official GitHub CLI documentation
2. official GitHub documentation
3. installed command help
4. current repository configuration
5. runtime evidence
6. community sources when necessary

Use Context7 or Fetch when appropriate.

Do not rely solely on model memory for current CLI behavior.

---

# 77. Version-Sensitive CLI Behavior

Before using unfamiliar `gh` functionality:

```bash
gh --version
```

Then:

```bash
gh <command> --help
```

For current documentation, consult the official GitHub CLI documentation.

Do not invent flags.

If a command fails because a flag does not exist, inspect:

```bash
gh <command> --help
```

before attempting alternatives.

---

# 78. GitHub CLI Extensions

Do not install arbitrary `gh` extensions automatically.

If an extension appears useful:

1. identify why it is needed
2. inspect its source/repository
3. assess trust
4. assess whether built-in `gh` functionality is sufficient
5. install only when explicitly authorized

Prefer built-in commands.

---

# 79. GitHub CLI Aliases

Do not create global aliases automatically.

Project-specific automation should normally live in project documentation/scripts rather than modifying the user's global CLI configuration.

If an alias is requested, verify the exact command it will execute.

---

# 80. GitHub Agent Skills

The installed `gh` version may expose additional GitHub CLI functionality beyond the core commands.

Do not automatically install external agent skills.

If an external GitHub skill is proposed:

1. inspect its source
2. understand its permissions
3. determine whether it duplicates existing project skills
4. assess trust
5. obtain explicit authorization before installing

The project's `.claude/skills/` system remains the primary project instruction layer.

---

# 81. Cee-Tailor GitHub Architecture

For Cee-Tailor, use this conceptual architecture:

```text
Claude Code / FCC
        │
        ▼
Project Instructions
        │
        ├── CLAUDE.md
        ├── AGENT_WORKFLOW.md
        │
        ▼
Skills
        │
        ├── github
        ├── git
        ├── testing
        ├── verification
        ├── security
        ├── debugging
        ├── research
        └── code-review
        │
        ▼
Tools
        │
        ├── Filesystem MCP
        ├── Context7 MCP
        ├── Fetch MCP
        ├── Playwright MCP
        ├── Git
        └── GitHub CLI
        │
        ▼
Cee-Tailor Repository
```

The GitHub skill should coordinate with the other skills rather than duplicate them.

---

# 82. GitHub Task Classification

Classify the task before acting.

## Type A — Information

Examples:

* What PRs exist?
* What failed?
* What branch is remote?
* What issues are open?

Read-only investigation.

## Type B — Local Git

Examples:

* create branch
* inspect commit
* prepare changes

Use Git primarily.

## Type C — Remote Git

Examples:

* push branch
* inspect remote refs

Use Git + verification.

## Type D — Collaboration

Examples:

* create PR
* comment on issue
* request review

Use `gh`.

## Type E — CI/CD

Examples:

* investigate failed Actions
* rerun workflow
* inspect deployment

Use `gh run`, `gh workflow`, Git, and relevant project tools.

## Type F — Repository Administration

Examples:

* rules
* secrets
* variables
* permissions
* settings

High-impact. Explicit authorization required.

## Type G — Release

Examples:

* tag
* release
* assets

High-impact. Explicit authorization required.

---

# 83. Read-Only First

When uncertain, begin with read-only commands.

Examples:

```bash
git status
git log
git branch -avv
gh repo view
gh pr list
gh issue list
gh run list
gh release list
```

Only transition to write operations after understanding the state.

---

# 84. Minimal Change Principle

GitHub-related changes must be minimal.

Do not:

* reorganize unrelated files
* rewrite workflows unnecessarily
* upgrade unrelated dependencies
* change repository settings unnecessarily
* alter branch strategy unnecessarily
* create unnecessary issues
* create unnecessary PRs

Make the smallest change that solves the requested problem.

---

# 85. Evidence Categories

Every important GitHub conclusion should be categorized mentally as:

## FACT

Directly observed.

Example:

> `gh pr checks 12` reports three successful checks.

## INFERENCE

Derived from evidence.

Example:

> The failing test appears related to the changed API contract.

## UNKNOWN

Not established.

Example:

> The production deployment status has not been verified.

Never present inference or unknown information as fact.

---

# 86. Completion Criteria

A GitHub task is complete only when the requested end state has been verified.

Examples:

## "Push this branch"

Complete when:

```bash
git push
```

succeeds and remote state is verified.

## "Create a PR"

Complete when:

```bash
gh pr create
```

succeeds and:

```bash
gh pr view <number>
```

confirms the PR.

## "Fix CI"

Complete only after the new relevant CI run is inspected.

## "Merge the PR"

Complete only after the PR state confirms it is merged.

## "Publish the release"

Complete only after:

```bash
gh release view <tag>
```

confirms the release state.

---

# 87. Never Claim Unverified Success

Never say:

```text
Done.
Everything works.
CI passes.
The PR is ready.
The deployment succeeded.
The branch is pushed.
The release is live.
```

unless the relevant state has actually been verified.

Prefer:

> Implemented locally; CI has not yet been verified.

or:

> The branch was pushed and the remote branch was confirmed. CI is still running.

---

# 88. Final GitHub Verification Loop

For meaningful GitHub tasks:

```text
1. Inspect local state
        ↓
2. Inspect GitHub state
        ↓
3. Understand target
        ↓
4. Make change
        ↓
5. Validate locally
        ↓
6. Inspect diff
        ↓
7. Commit
        ↓
8. Push
        ↓
9. Verify remote state
        ↓
10. Verify CI / PR / release if applicable
        ↓
11. Report evidence
```

---

# 89. Security Review Trigger

Invoke the security skill when the task involves:

* authentication
* authorization
* secrets
* tokens
* GitHub Actions permissions
* deployment credentials
* repository permissions
* environment configuration
* third-party GitHub Actions
* dependency supply chain
* webhooks
* GitHub Apps
* OAuth
* API credentials

Do not treat GitHub access as inherently safe.

---

# 90. Testing Review Trigger

Invoke the testing skill when:

* code changes
* CI changes
* workflow changes
* PR creation
* bug fixes
* API changes
* frontend changes
* database changes

Testing should be proportionate to the change.

---

# 91. Verification Skill Trigger

Invoke the verification skill when:

* the user asks whether something works
* CI status matters
* a PR status matters
* a deployment matters
* a remote branch matters
* a release matters
* an API operation matters
* a GitHub state claim needs proof

---

# 92. Research Skill Trigger

Invoke research when:

* current GitHub CLI behavior is uncertain
* a GitHub API endpoint is unclear
* repository rules are unclear
* a third-party Action needs investigation
* a dependency/action version matters
* GitHub behavior has changed

Use authoritative sources first.

---

# 93. Debugging Skill Trigger

Invoke debugging when:

* GitHub Actions fail
* pushes fail
* PR creation fails
* API requests fail
* authentication fails
* remote state appears inconsistent
* deployment workflows fail

Capture the exact error before diagnosing.

---

# 94. Multi-Skill Workflow

For a typical feature:

```text
planning
    ↓
architecture
    ↓
implementation
    ↓
testing
    ↓
code-review
    ↓
security
    ↓
verification
    ↓
git
    ↓
github
```

Not every task requires every skill.

Select only the relevant skills.

---

# 95. GitHub + Planning

Before a complex GitHub operation, planning should establish:

* desired outcome
* affected repository
* branch
* expected changes
* validation
* remote operation
* verification criteria

Do not start with GitHub writes.

---

# 96. GitHub + Architecture

For architectural changes:

Inspect:

* repository structure
* existing PRs
* existing issues
* workflow architecture
* deployment architecture
* package boundaries

Avoid designing around assumptions.

---

# 97. GitHub + Code Review

When reviewing a PR:

```text
Repository
    ↓
PR metadata
    ↓
Diff
    ↓
Changed files
    ↓
Related implementation
    ↓
Tests
    ↓
CI
    ↓
Security
    ↓
Review findings
```

---

# 98. GitHub + Documentation

When creating GitHub-facing documentation:

Ensure it explains:

* purpose
* setup
* usage
* validation
* limitations
* operational workflow

Do not document commands that have not been verified.

---

# 99. GitHub + Frontend Verification

For Cee-Tailor frontend changes:

1. inspect PR
2. inspect diff
3. run frontend checks
4. start application when appropriate
5. use Playwright
6. verify the actual browser behavior
7. inspect GitHub checks
8. report both local and remote evidence

Do not treat successful TypeScript compilation as proof that the UI works.

---

# 100. GitHub + Backend Verification

For backend changes:

1. inspect diff
2. run type/static checks
3. run tests
4. start application if necessary
5. test affected endpoints
6. inspect CI
7. verify PR state

Do not treat a successful build as proof of runtime correctness.

---

# 101. Database Changes

For database migrations:

Inspect:

* migration files
* migration ordering
* model changes
* API contract
* deployment process
* CI migration behavior

Do not modify production database state unless explicitly authorized.

---

# 102. GitHub Actions and Database Migrations

If CI/deployment runs migrations:

Determine:

* where migration executes
* which database it targets
* what credentials are used
* whether migrations are reversible
* whether deployment ordering matters

Never blindly rerun destructive migrations.

---

# 103. Monorepo Awareness

Cee-Tailor contains multiple application/package areas.

Potential areas include:

```text
apps/web
apps/api
packages/config
packages/contracts
packages/ui
scripts
```

When a GitHub change affects one area:

* inspect affected package
* inspect related packages
* inspect root configuration
* inspect CI workflows
* avoid unrelated modifications

---

# 104. Commit Scope

A commit should normally represent one coherent logical change.

Avoid mixing:

```text
feature code
dependency upgrades
unrelated formatting
workflow changes
documentation cleanup
```

unless they are intentionally part of the same change.

---

# 105. PR Scope

A PR should normally have one coherent purpose.

If the work contains unrelated changes, separate them when practical.

Do not create multiple PRs merely for the sake of separation when the architecture genuinely requires one change.

---

# 106. Generated Files

Before committing generated files, determine whether they are:

* source-controlled intentionally
* generated automatically
* ignored
* required by deployment

Do not commit generated artifacts simply because they appear in `git status`.

---

# 107. Lockfiles

When dependencies change:

Inspect lockfiles.

Do not manually edit lockfiles unless necessary.

Use the project's package manager.

Verify resulting changes.

---

# 108. `.github` Directory

Treat `.github` as important infrastructure.

Potential contents:

```text
.github/workflows/
.github/ISSUE_TEMPLATE/
.github/PULL_REQUEST_TEMPLATE.md
.github/dependabot.yml
.github/CODEOWNERS
```

Inspect before modifying.

Do not delete or replace existing GitHub configuration without understanding its purpose.

---

# 109. CODEOWNERS

If CODEOWNERS exists:

Inspect it before changing ownership-sensitive files.

Do not modify ownership rules casually.

Changes can affect review requirements.

---

# 110. Pull Request Templates

If a PR template exists:

Read it before creating a PR.

Follow required sections.

Do not omit required validation information.

---

# 111. Issue Templates

If issue templates exist:

Use the appropriate template.

Do not create free-form issues when the project has a structured template unless appropriate.

---

# 112. GitHub Projects

Project-board operations are consequential.

Before modifying projects:

* identify the project
* inspect existing state
* understand intended change
* verify required authorization

Do not reorganize project boards automatically.

---

# 113. Labels

Inspect existing labels before creating new ones:

```bash
gh label list
```

Do not create duplicate labels.

Prefer existing project conventions.

---

# 114. Milestones

If milestones are used:

Inspect existing milestones before creating new ones.

Do not create duplicate planning structures.

---

# 115. Discussions

If GitHub Discussions are used:

Treat them as communication artifacts.

Do not post automatically unless explicitly requested.

---

# 116. Comments as External Communication

GitHub comments are public or repository-visible communication.

Before posting:

* verify repository
* verify issue/PR
* verify message
* remove secrets
* avoid unsupported claims
* avoid unnecessary verbosity

Posting is an external side effect.

---

# 117. Public Repository Awareness

If the repository is public:

Assume commits, issues, PRs, comments, releases, and workflow metadata may be publicly visible.

Do not expose private information.

---

# 118. Private Repository Awareness

Private does not mean safe for secrets.

Do not commit credentials to private repositories.

Repository access can change.

---

# 119. External Contributors

When reviewing contributions from outside the trusted repository context:

Pay particular attention to:

* CI execution
* scripts
* dependency installation
* shell commands
* workflow triggers
* secret exposure

Use the security skill.

---

# 120. Pull Request Head Branch Trust

Do not assume code from a PR branch is trusted.

Inspect:

* source repository
* source branch
* author
* workflow trigger
* permissions
* changed scripts

This is especially important for CI.

---

# 121. Fork Awareness

A PR may originate from a fork.

Inspect:

```bash
gh pr view <number> \
  --json headRepository,headRepositoryOwner,headRefName,baseRepository,baseRefName
```

Do not assume the head branch belongs to the main repository.

---

# 122. Remote URL Changes

Changing Git remotes is consequential.

Before:

```bash
git remote -v
```

After changing:

```bash
git remote -v
```

Then verify:

```bash
gh repo view
```

Do not silently switch repositories.

---

# 123. Repository Transfer

Repository transfers are high-impact.

Never initiate one automatically.

---

# 124. Repository Deletion

Repository deletion is destructive.

Never perform it unless explicitly requested and unmistakably authorized.

Before deletion, require confirmation of:

* exact repository
* intended consequence

Do not infer authorization from general cleanup requests.

---

# 125. Fork Creation

Forking creates a new remote repository.

Only fork when needed and authorized.

Verify the resulting fork.

---

# 126. Clone Operations

If cloning:

```bash
gh repo clone OWNER/REPO
```

Verify:

```bash
git remote -v
gh repo view
```

Do not accidentally clone into an existing project directory containing unrelated work.

---

# 127. GitHub Codespaces

Do not create, stop, delete, or modify Codespaces unless explicitly requested.

If Codespaces are relevant:

Inspect the current repository configuration first.

---

# 128. GitHub Actions Artifacts

When debugging CI:

Inspect artifacts when logs are insufficient.

Determine:

* artifact name
* producing job
* retention
* contents
* relevance

Do not assume an artifact proves the complete deployment state.

---

# 129. CI Logs

Logs are evidence.

When reporting an error:

Prefer the exact meaningful error over a vague description.

Example:

Bad:

> CI is broken.

Better:

> The `web-build` job exits during `npm run build` with a TypeScript error in `apps/web/...`.

Do not reproduce secrets from logs.

---

# 130. GitHub Status vs Application Status

These are separate.

A GitHub Actions deployment job can be successful while:

* the application crashes
* environment variables are missing
* database migrations fail later
* a health endpoint fails
* frontend runtime behavior is broken

Verify the application independently when required.

---

# 131. Release vs Deployment

A GitHub release does not necessarily mean production deployment.

A successful deployment does not necessarily mean a GitHub release exists.

Verify each independently.

---

# 132. CI vs Tests

A local test passing does not prove GitHub CI passes.

GitHub CI passing does not prove every local scenario works.

Use both where appropriate.

---

# 133. Remote Verification After Push

Preferred:

```bash
git push
git ls-remote --heads origin <branch>
```

Then:

```bash
gh pr status
```

if a PR exists.

Then:

```bash
gh pr checks
```

if CI exists.

---

# 134. Final Diff Review

Before committing:

```bash
git diff
```

Before pushing:

```bash
git diff HEAD~1
```

or inspect the relevant commit range.

Ensure only intended changes are included.

---

# 135. Final Repository Check

Before reporting completion:

```bash
git status --short
git branch --show-current
```

Then relevant GitHub verification:

```bash
gh repo view
```

and task-specific commands.

---

# 136. Failure Handling

If a GitHub command fails:

Do not immediately try random alternatives.

Use:

```text
ERROR
  ↓
CLASSIFY
  ↓
INSPECT
  ↓
UNDERSTAND
  ↓
MINIMAL FIX
  ↓
RETRY
  ↓
VERIFY
```

---

# 137. Never Hide Failures

If an operation partially succeeds:

Report the partial state.

Example:

> The branch was pushed, but PR creation failed because the repository requires a different base branch.

Do not say:

> GitHub setup completed.

---

# 138. Partial Success

When multiple requested operations exist, report them separately.

Example:

```text
Branch: verified
Commit: verified
PR: created
CI: running
Deployment: not verified
```

This is preferable to a single vague completion statement.

---

# 139. Unknown State

If verification cannot be performed:

Say:

> The operation was attempted, but the final remote state could not be verified.

Do not convert unknown state into success.

---

# 140. Current-State Preference

For current GitHub information, prefer live commands over remembered information.

Examples:

Instead of remembering the default branch:

```bash
gh repo view --json defaultBranchRef
```

Instead of remembering open PRs:

```bash
gh pr list
```

Instead of remembering CI:

```bash
gh run list
```

Instead of remembering releases:

```bash
gh release list
```

---

# 141. Avoid Stale Context

Previous conversation state can be outdated.

Re-check:

* branch
* PR
* CI
* issue
* release
* repository configuration

when the current state matters.

---

# 142. Command Output Discipline

When command output is large:

* extract relevant information
* do not dump enormous logs unnecessarily
* preserve exact errors
* preserve identifiers
* preserve URLs when useful
* preserve evidence needed for conclusions

---

# 143. Structured Output Preference

When scripting or reasoning over GitHub state, prefer:

```bash
--json
```

and:

```bash
--jq
```

when supported.

This reduces parsing ambiguity.

---

# 144. Interactive Commands

Avoid interactive commands when a deterministic non-interactive form exists and is appropriate.

For example:

```bash
gh pr create --title "..." --body "..."
```

can be preferable to an interactive prompt when the required information is already known.

However, do not sacrifice safety merely to avoid interaction.

---

# 145. Browser Operations

Use:

```bash
gh pr view --web
```

or other browser-opening commands only when browser navigation is actually useful.

Do not depend on a browser opening successfully as proof of GitHub state.

CLI/API output is generally better evidence.

---

# 146. API vs CLI Preference

Prefer dedicated `gh` commands when available.

Use:

```bash
gh pr
gh issue
gh run
gh repo
gh release
gh workflow
```

before reaching for:

```bash
gh api
```

Use `gh api` when:

* a dedicated command lacks required information
* a specific endpoint is needed
* structured data is required
* repository configuration requires API access

---

# 147. No Fake Commands

Never invent:

* `gh` subcommands
* flags
* API endpoints
* JSON fields

If uncertain:

```bash
gh <command> --help
```

or consult current official documentation.

---

# 148. Current CLI Verification

The installed CLI should be treated as the authoritative local interface.

Check:

```bash
gh --version
```

For command syntax:

```bash
gh <command> --help
```

For current official behavior, use GitHub CLI documentation.

---

# 149. Repository-Specific Conventions

Before performing GitHub work, inspect:

```text
CLAUDE.md
AGENT_WORKFLOW.md
.claude/skills/
.github/
README.md
```

Follow project-specific conventions.

If project instructions conflict with generic GitHub procedures, follow the higher-priority project instructions unless doing so would create an unsafe operation.

---

# 150. Cee-Tailor Specific Verification

For Cee-Tailor, the agent should generally consider these areas when a change touches them:

## Frontend

```text
apps/web
```

Potential validation:

* lint
* typecheck
* build
* Playwright

## Backend

```text
apps/api
```

Potential validation:

* Python checks
* tests
* API runtime verification

## Shared packages

```text
packages/
```

Potential validation:

* typecheck
* dependent package builds
* tests

## GitHub Actions

```text
.github/workflows/
```

Potential validation:

* YAML/config inspection
* local equivalent commands
* GitHub Actions run verification

---

# 151. End-to-End Feature PR

For a complete Cee-Tailor feature:

```text
1. Understand request
2. Read CLAUDE.md
3. Read AGENT_WORKFLOW.md
4. Inspect repository
5. Inspect Git state
6. Inspect GitHub state
7. Plan implementation
8. Implement
9. Run static checks
10. Run tests
11. Run browser verification if applicable
12. Run security review if applicable
13. Inspect diff
14. Commit
15. Push branch
16. Verify remote branch
17. Create PR
18. Inspect PR
19. Inspect CI
20. Fix failures if any
21. Re-run verification
22. Report final state
```

---

# 152. Bug Fix PR

For a bug:

```text
1. Reproduce
2. Capture exact failure
3. Inspect relevant implementation
4. Identify root cause
5. Implement smallest fix
6. Add/update regression test
7. Run test
8. Run broader checks
9. Inspect diff
10. Commit
11. Push
12. Create/update PR
13. Verify CI
14. Report evidence
```

---

# 153. CI Fix PR

For CI:

```text
1. Identify failed run
2. Inspect failed job
3. Inspect logs
4. Inspect workflow
5. Determine root cause
6. Reproduce locally if possible
7. Modify workflow minimally
8. Validate
9. Commit
10. Push
11. Inspect new run
12. Confirm result
```

---

# 154. Release Workflow

For a release:

```text
1. Confirm requested version
2. Inspect current version
3. Inspect recent commits
4. Inspect tests
5. Inspect CI
6. Prepare release changes
7. Commit
8. Tag
9. Push
10. Create release
11. Verify release
12. Verify assets
13. Verify deployment separately if applicable
```

---

# 155. Emergency / High-Risk Changes

For changes involving:

* production
* secrets
* database
* authentication
* repository permissions
* branch protection
* deployment
* destructive Git operations

slow down.

Require:

* exact target
* explicit authorization
* pre-operation inspection
* post-operation verification

Do not optimize for speed at the expense of recoverability.

---

# 156. Destructive Operation Checklist

Before destructive GitHub operations:

```text
[ ] Correct repository
[ ] Correct branch/resource
[ ] Correct account
[ ] User explicitly authorized operation
[ ] Current state inspected
[ ] Consequence understood
[ ] Recovery path understood
[ ] Exact command reviewed
[ ] Operation executed
[ ] Result verified
```

---

# 157. GitHub Communication Standards

When writing PRs/issues/comments:

Be:

* factual
* concise
* technically precise
* evidence-based

Avoid:

* exaggerated claims
* unsupported certainty
* vague statements
* blaming individuals
* exposing private information

---

# 158. PR Summary Standard

Prefer:

```text
## Summary

- Added ...
- Updated ...
- Fixed ...

## Validation

- ...
- ...

## Notes

- ...
```

Only include validations actually performed.

---

# 159. CI Report Standard

Prefer:

```text
Workflow: <workflow>
Run: <run-id>
Job: <job>
Result: <status>

Failure:
<actual error>

Fix:
<what changed>

Verification:
<new run/result>
```

---

# 160. Final Response Standard

At the end of GitHub work, report:

```text
Operation:
Repository:
Branch:
Commit:
PR/Issue/Run:
Validation:
GitHub verification:
Remaining uncertainty:
```

Omit fields that genuinely do not apply.

Do not invent identifiers.

---

# 161. Absolute Rules

The following rules are mandatory.

1. Never fabricate GitHub state.
2. Never expose credentials.
3. Never commit secrets.
4. Never force-push without authorization.
5. Never delete remote branches without authorization.
6. Never merge without authorization.
7. Never publish releases without authorization.
8. Never modify repository settings without authorization.
9. Never discard unrelated user changes.
10. Never report unverified success.
11. Never invent CLI commands.
12. Never assume local Git state equals GitHub state.
13. Never assume CI success without inspecting CI.
14. Never assume deployment success without deployment verification.
15. Never assume authentication implies repository access.
16. Inspect before consequential actions.
17. Verify after consequential actions.
18. Use the smallest change that solves the problem.
19. Prefer authoritative/current evidence.
20. Preserve user control over consequential GitHub actions.

---

# 162. Final Decision Tree

When asked to perform a GitHub operation:

```text
Is this GitHub-related?
        │
        ├── No → use normal project workflow
        │
        └── Yes
             │
             ▼
      Inspect repository
             │
             ▼
      Inspect Git state
             │
             ▼
      Inspect GitHub state
             │
             ▼
      Is operation read-only?
          │             │
         Yes            No
          │             │
          ▼             ▼
       Execute     Is it consequential?
                         │
                  ┌──────┴──────┐
                 No             Yes
                  │              │
                  ▼              ▼
              Execute      Confirm authorization
                                 │
                                 ▼
                              Execute
                                 │
                                 ▼
                              Verify
                                 │
                                 ▼
                              Report
```

---

# 163. Final Mental Model

The agent must think of GitHub work as a state machine:

```text
UNKNOWN
   ↓
INSPECTED
   ↓
UNDERSTOOD
   ↓
PLANNED
   ↓
CHANGED LOCALLY
   ↓
VALIDATED
   ↓
COMMITTED
   ↓
PUSHED
   ↓
REMOTE VERIFIED
   ↓
CI VERIFIED
   ↓
PR VERIFIED
   ↓
MERGED / RELEASED / DEPLOYED
   ↓
FINAL STATE VERIFIED
```

Never skip directly from:

```text
local code changed
```

to:

```text
GitHub task completed
```

without verifying the intermediate states that matter.

---

# 164. Primary Principle

The most important rule in this skill is:

> **Do not tell the user what you think GitHub's state is. Inspect GitHub's state, then tell the user what the evidence shows.**
