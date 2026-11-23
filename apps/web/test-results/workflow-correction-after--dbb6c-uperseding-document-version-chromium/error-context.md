# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workflow.spec.ts >> correction after publish creates a superseding document version
- Location: e2e/workflow.spec.ts:88:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: 'Correct results' })

```

# Page snapshot

```yaml
- generic [ref=f1e3]:
  - navigation "Main" [ref=f1e4]:
    - list [ref=f1e5]:
      - listitem [ref=f1e6]:
        - link "Dashboard" [ref=f1e7] [cursor=pointer]:
          - /url: /
      - listitem [ref=f1e8]:
        - link "Academic" [ref=f1e9] [cursor=pointer]:
          - /url: /academic
      - listitem [ref=f1e10]:
        - link "Students" [ref=f1e11] [cursor=pointer]:
          - /url: /students
      - listitem [ref=f1e12]:
        - link "Assessments" [ref=f1e13] [cursor=pointer]:
          - /url: /assessments
      - listitem [ref=f1e14]:
        - link "Users" [ref=f1e15] [cursor=pointer]:
          - /url: /users
      - listitem [ref=f1e16]:
        - link "Reports" [ref=f1e17] [cursor=pointer]:
          - /url: /reports
  - main [ref=f1e18]:
    - generic [ref=f1e19]:
      - paragraph [ref=f1e20]: admin · admin@seed.school
      - button "Sign out" [ref=f1e21] [cursor=pointer]
    - generic [ref=f1e22]:
      - heading "Score sheet draft" [level=2] [ref=f1e23]
      - paragraph [ref=f1e24]: Type scores; m = missing, a = absent, e = exempt. Enter/↓ next student, ↑ back, Tab next column.
      - generic [ref=f1e25]:
        - heading "3 students" [level=3] [ref=f1e27]
        - table [ref=f1e28]:
          - rowgroup [ref=f1e29]:
            - row [ref=f1e30]:
              - columnheader "Student" [ref=f1e31]
              - columnheader "First CA /10" [ref=f1e32]:
                - text: First CA
                - generic [ref=f1e33]: /10
              - columnheader "Exam /60" [ref=f1e34]:
                - text: Exam
                - generic [ref=f1e35]: /60
          - rowgroup [ref=f1e36]:
            - row [ref=f1e37]:
              - cell "Ada E2E" [ref=f1e38]
              - cell [ref=f1e39]:
                - textbox "Ada E2E First CA" [ref=f1e40]: "8.00"
              - cell [ref=f1e41]:
                - textbox "Ada E2E Exam" [ref=f1e42]: "28.00"
            - row [ref=f1e43]:
              - cell "Bayo E2E" [ref=f1e44]
              - cell [ref=f1e45]:
                - textbox "Bayo E2E First CA" [ref=f1e46]: "8.00"
              - cell [ref=f1e47]:
                - textbox "Bayo E2E Exam" [ref=f1e48]: "28.00"
            - row [ref=f1e49]:
              - cell "Chidi E2E" [ref=f1e50]
              - cell [ref=f1e51]:
                - textbox "Chidi E2E First CA" [ref=f1e52]: "8.00"
              - cell [ref=f1e53]:
                - textbox "Chidi E2E Exam" [ref=f1e54]: "28.00"
        - button "Save 0 changes" [disabled] [ref=f1e56]
      - region "Workflow actions" [ref=f1e57]:
        - button "Submit for review" [ref=f1e58] [cursor=pointer]
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
  42 |   // keyboard entry: focus the first CA1 cell, replace its value, Enter walks
  43 |   // down (fill() replaces — keyboard.type would append to the seeded value)
  44 |   const firstCell = page.getByLabel(new RegExp(`${world.rows[0]!.student_name} First CA`));
  45 |   await firstCell.fill("9");
  46 |   await firstCell.press("Enter");
  47 |   const secondCell = page.getByLabel(new RegExp(`${world.rows[1]!.student_name} First CA`));
  48 |   await expect(secondCell).toBeFocused();
  49 |   await secondCell.fill("8");
  50 |   await page.getByRole("button", { name: /Save \d+ change/ }).click();
  51 |   await expect(page.getByRole("button", { name: "Submit for review" })).toBeVisible();
  52 |   await page.getByRole("button", { name: "Submit for review" }).click();
  53 |   await expect(page.getByText("submitted", { exact: true })).toBeVisible();
  54 | });
  55 | 
  56 | test("reviewer starts the review; admin approves and locks with step-up", async ({ page }) => {
  57 |   await loginToken(page, REVIEWER.email, REVIEWER.password);
  58 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  59 |   await page.getByRole("button", { name: "Start review" }).click();
  60 |   await expect(page.getByText("under_review").first()).toBeVisible();
  61 | 
  62 |   await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  63 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  64 |   await page.getByRole("button", { name: "Approve" }).click();
  65 |   await expect(page.getByText("approved").first()).toBeVisible();
  66 | 
  67 |   // lock — the step-up dialog demands the password
  68 |   await page.getByRole("button", { name: "Lock results" }).click();
  69 |   await page.getByLabel("Confirm password").fill("Dev-Admin-2026");
  70 |   await page.getByRole("button", { name: "Confirm" }).click();
  71 |   await expect(page.getByText("locked").first()).toBeVisible();
  72 | });
  73 | 
  74 | test("publish demands re-auth with the authenticator code", async ({ page }) => {
  75 |   await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  76 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
  77 |   await page.getByRole("button", { name: "Publish" }).click();
  78 |   await page.getByLabel("Confirm password").fill("Dev-Admin-2026");
  79 |   await page.getByRole("button", { name: "Confirm" }).click();
  80 |   // MFA_REQUIRED reveals the field; the seed enrolled the admin
  81 |   const totp = page.getByLabel("Authenticator code");
  82 |   await expect(totp).toBeVisible();
  83 |   await totp.fill(totpNow(adminMfa.secret));
  84 |   await page.getByRole("button", { name: "Confirm" }).click();
  85 |   await expect(page.getByText("published").first()).toBeVisible();
  86 | });
  87 | 
  88 | test("correction after publish creates a superseding document version", async ({ page }) => {
  89 |   await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  90 |   await page.goto(`/assessments/${world.assessmentId}/sheet`);
> 91 |   await page.getByRole("button", { name: "Correct results" }).click();
     |                                                               ^ Error: locator.click: Test timeout of 30000ms exceeded.
  92 |   await page.getByLabel("Correct results reason").fill("E2E: exam recheck");
  93 |   await page.getByRole("button", { name: "Confirm Correct results" }).click();
  94 |   // the document list (Reports screen) then shows v2 rows superseding v1
  95 |   await page.goto("/reports");
  96 |   await page.getByLabel("Assessment").selectOption(world.assessmentId);
  97 |   await expect(page.getByRole("cell", { name: "v2" }).first()).toBeVisible();
  98 | });
  99 | 
```