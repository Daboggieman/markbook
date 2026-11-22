# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workflow.spec.ts >> teacher enters scores in the grid and submits
- Location: e2e/workflow.spec.ts:34:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.fill: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByLabel(/Ada E2E First CA/)

```

# Page snapshot

```yaml
- generic [ref=f1e3]:
  - heading "Markbook" [level=1] [ref=f1e4]
  - generic [ref=f1e5]:
    - text: Email
    - textbox "Email" [ref=f1e6]
  - generic [ref=f1e7]:
    - text: Password
    - textbox "Password" [ref=f1e8]
  - button "Sign in" [ref=f1e9] [cursor=pointer]
```

# Test source

```ts
  1  | /**
  2  |  * The Phase 6 exit walk, over the REAL app and REAL API (spec §16):
  3  |  * teacher enters + submits → reviewer starts review → admin approves,
  4  |  * locks (step-up), publishes (step-up + MFA) → correction after publish.
  5  |  *
  6  |  * Run (runbook):
  7  |  *   1. compose dev DB + `scripts/upgrade_dev.py` + `scripts/seed_dev_admin.py`
  8  |  *   2. API on :8001, then `npm run e2e` in apps/web (starts Vite itself)
  9  |  *
  10 |  * MFA: seeding enrolls the ADMIN via /users/me/mfa/setup + /verify using
  11 |  * the local TOTP helper — the publish step then completes the real
  12 |  * reauth+TOTP dialog the spec demands.
  13 |  */
  14 | import { expect, test } from "@playwright/test";
  15 | 
  16 | import {
  17 |   REVIEWER,
  18 |   TEACHER,
  19 |   loginToken,
  20 |   enrollMfa,
  21 |   seedAssessmentWorld,
  22 |   type SeededWorld,
  23 | } from "./seed";
  24 | import { totpNow } from "./totp";
  25 | 
  26 | let world: SeededWorld;
  27 | let adminMfa: { secret: string };
  28 | 
  29 | test.beforeAll(async () => {
  30 |   world = await seedAssessmentWorld();
  31 |   adminMfa = await enrollMfa();
  32 | });
  33 | 
  34 | test("teacher enters scores in the grid and submits", async ({ page }) => {
  35 |   await page.goto("/login");
  36 |   await page.getByLabel("Email").fill(TEACHER.email);
  37 |   await page.getByLabel("Password").fill(TEACHER.password);
  38 |   await page.getByRole("button", { name: "Sign in" }).click();
  39 |   await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  40 | 
  41 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  42 |   // keyboard entry: focus the first CA1 cell, type, Enter walks down
  43 |   const firstCell = page.getByLabel(new RegExp(`${world.rows[0]!.student_name} First CA`));
> 44 |   await firstCell.fill("9");
     |                   ^ Error: locator.fill: Test timeout of 30000ms exceeded.
  45 |   await firstCell.press("Enter");
  46 |   await expect(page.getByLabel(new RegExp(`${world.rows[1]!.student_name} First CA`))).toBeFocused();
  47 |   await page.keyboard.type("8");
  48 |   await page.getByRole("button", { name: /Save \d+ change/ }).click();
  49 |   await expect(page.getByRole("button", { name: "Submit for review" })).toBeVisible();
  50 |   await page.getByRole("button", { name: "Submit for review" }).click();
  51 |   await expect(page.getByText("submitted", { exact: true })).toBeVisible();
  52 | });
  53 | 
  54 | test("reviewer starts the review; admin approves and locks with step-up", async ({ page }) => {
  55 |   await loginToken(page, REVIEWER.email, REVIEWER.password);
  56 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  57 |   await page.getByRole("button", { name: "Start review" }).click();
  58 |   await expect(page.getByText("under_review").first()).toBeVisible();
  59 | 
  60 |   await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  61 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  62 |   await page.getByRole("button", { name: "Approve" }).click();
  63 |   await expect(page.getByText("approved").first()).toBeVisible();
  64 | 
  65 |   // lock — the step-up dialog demands the password
  66 |   await page.getByRole("button", { name: "Lock results" }).click();
  67 |   await page.getByLabel("Confirm password").fill("Dev-Admin-2026");
  68 |   await page.getByRole("button", { name: "Confirm" }).click();
  69 |   await expect(page.getByText("locked").first()).toBeVisible();
  70 | });
  71 | 
  72 | test("publish demands re-auth with the authenticator code", async ({ page }) => {
  73 |   await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  74 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  75 |   await page.getByRole("button", { name: "Publish" }).click();
  76 |   await page.getByLabel("Confirm password").fill("Dev-Admin-2026");
  77 |   await page.getByRole("button", { name: "Confirm" }).click();
  78 |   // MFA_REQUIRED reveals the field; the seed enrolled the admin
  79 |   const totp = page.getByLabel("Authenticator code");
  80 |   await expect(totp).toBeVisible();
  81 |   await totp.fill(totpNow(adminMfa.secret));
  82 |   await page.getByRole("button", { name: "Confirm" }).click();
  83 |   await expect(page.getByText("published").first()).toBeVisible();
  84 | });
  85 | 
  86 | test("correction after publish creates a superseding document version", async ({ page }) => {
  87 |   await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  88 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  89 |   await page.getByRole("button", { name: "Correct results" }).click();
  90 |   await page.getByLabel("Correct results reason").fill("E2E: exam recheck");
  91 |   await page.getByRole("button", { name: "Confirm Correct results" }).click();
  92 |   // the document list (Reports screen) then shows v2 rows superseding v1
  93 |   await page.goto("/reports");
  94 |   await page.getByLabel("Assessment").selectOption(world.assessmentId);
  95 |   await expect(page.getByRole("cell", { name: "v2" }).first()).toBeVisible();
  96 | });
  97 | 
```