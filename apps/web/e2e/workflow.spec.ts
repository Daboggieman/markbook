/**
 * The Phase 6 exit walk, over the REAL app and REAL API (spec §16):
 * teacher enters + submits → reviewer starts review → admin approves,
 * locks (step-up), publishes (step-up + MFA) → correction after publish.
 *
 * Run (runbook):
 *   1. compose dev DB + `scripts/upgrade_dev.py` + `scripts/seed_dev_admin.py`
 *   2. API on :8001, then `npm run e2e` in apps/web (starts Vite itself)
 *
 * MFA: seeding enrolls the ADMIN via /users/me/mfa/setup + /verify using
 * the local TOTP helper — the publish step then completes the real
 * reauth+TOTP dialog the spec demands.
 */
import { expect, test } from "@playwright/test";

import {
  REVIEWER,
  TEACHER,
  loginToken,
  enrollMfa,
  seedAssessmentWorld,
  type SeededWorld,
} from "./seed";
import { totpNow } from "./totp";

let world: SeededWorld;
let adminMfa: { secret: string };

test.beforeAll(async () => {
  world = await seedAssessmentWorld();
  adminMfa = await enrollMfa();
});

test("teacher enters scores in the grid and submits", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(TEACHER.email);
  await page.getByLabel("Password").fill(TEACHER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.goto(`/assessments/${world.assessmentId}/sheet`);
  // keyboard entry: focus the first CA1 cell, replace its value, Enter walks
  // down (fill() replaces — keyboard.type would append to the seeded value)
  const firstCell = page.getByLabel(new RegExp(`${world.rows[0]!.student_name} First CA`));
  await firstCell.fill("9");
  await firstCell.press("Enter");
  const secondCell = page.getByLabel(new RegExp(`${world.rows[1]!.student_name} First CA`));
  await expect(secondCell).toBeFocused();
  await secondCell.fill("8");
  await page.getByRole("button", { name: /Save \d+ change/ }).click();
  await expect(page.getByRole("button", { name: "Submit for review" })).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("submitted", { exact: true })).toBeVisible();
});

test("reviewer starts the review; admin approves and locks with step-up", async ({ page }) => {
  await loginToken(page, REVIEWER.email, REVIEWER.password);
  await page.goto(`/assessments/${world.assessmentId}/sheet`);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByText("under_review").first()).toBeVisible();

  await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  await page.goto(`/assessments/${world.assessmentId}/sheet`);
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("approved").first()).toBeVisible();

  // lock — the step-up dialog demands the password
  await page.getByRole("button", { name: "Lock results" }).click();
  await page.getByLabel("Confirm password").fill("Dev-Admin-2026");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("locked").first()).toBeVisible();
});

test("publish demands re-auth with the authenticator code", async ({ page }) => {
  await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  await page.goto(`/assessments/${world.assessmentId}/sheet`);
  await page.getByRole("button", { name: "Publish" }).click();
  await page.getByLabel("Confirm password").fill("Dev-Admin-2026");
  await page.getByRole("button", { name: "Confirm" }).click();
  // MFA_REQUIRED reveals the field; the seed enrolled the admin
  const totp = page.getByLabel("Authenticator code");
  await expect(totp).toBeVisible();
  await totp.fill(totpNow(adminMfa.secret));
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("published").first()).toBeVisible();
});

test("correction after publish creates a superseding document version", async ({ page }) => {
  await loginToken(page, "admin@seed.school", "Dev-Admin-2026");
  await page.goto(`/assessments/${world.assessmentId}/sheet`);
  await page.getByRole("button", { name: "Correct results" }).click();
  await page.getByLabel("Correct results reason").fill("E2E: exam recheck");
  await page.getByRole("button", { name: "Confirm Correct results" }).click();
  // the document list (Reports screen) then shows v2 rows superseding v1
  await page.goto("/reports");
  await page.getByLabel("Assessment").selectOption(world.assessmentId);
  await expect(page.getByRole("cell", { name: "v2" }).first()).toBeVisible();
});
