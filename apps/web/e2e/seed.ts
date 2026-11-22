/**
 * E2E seeding — everything the §16 walk needs, via the REAL API (no SQL,
 * no shortcuts: the E2E proves the HTTP path end to end).
 *
 * Prerequisites (runbook):
 *   1. compose dev DB up + `scripts/upgrade_dev.py` migrated
 *   2. `scripts/seed_dev_admin.py` — admin@seed.school / Dev-Admin-2026
 *   3. API on :8001, Vite on :5173
 *
 * The teacher and reviewer start as bare users; this module creates a role
 * per persona through the roles API and grants it — the same path an
 * admin's first day in the UI would take.
 */
import { API_BASE_URL, tokens } from "../src/api/client";
import { totpNow } from "./totp";

const ADMIN = { email: "admin@seed.school", password: "Dev-Admin-2026" };
const SCHOOL = "00000000-0000-7000-8000-000000000001";

export const TEACHER = { email: "e2e-teacher@seed.school", password: "E2E-Teacher-1" };
export const REVIEWER = { email: "e2e-reviewer@seed.school", password: "E2E-Reviewer-1" };

async function call(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 409 || res.status === 422) {
    // idempotent re-seeds are fine; anything else is a setup bug
    const problem = (await res.json()) as { detail?: string };
    if (res.status === 409) return res;
    throw new Error(`seed call failed: ${method} ${path} ${res.status} ${problem.detail ?? ""}`);
  }
  return res;
}

async function loginAs(email: string, password: string): Promise<void> {
  const res = await call("POST", "/api/v1/auth/login", { email, password });
  if (!res.ok) throw new Error(`login ${email} failed: ${res.status}`);
  const body = (await res.json()) as { access_token: string };
  tokens.access = body.access_token;
}

/** Created (or found) user's id, for role grants. */
async function ensureUser(email: string, password: string): Promise<string> {
  const res = await call("POST", "/api/v1/auth/users", {
    email,
    username: email.split("@")[0],
    password,
  });
  if (res.status === 201) {
    const body = (await res.json()) as { id: string };
    return body.id;
  }
  // exists (409) → find it in the list
  const list = (await (await call("GET", "/api/v1/auth/users")).json()) as {
    id: string;
    email: string;
  }[];
  const found = list.find((u) => u.email === email);
  if (!found) throw new Error(`user ${email} neither created nor found`);
  return found.id;
}

async function ensureRoleWith(name: string, permissions: [string, string][]): Promise<string> {
  const roles = (await (await call("GET", "/api/v1/roles")).json()) as {
    id: string;
    name: string;
  }[];
  const existing = roles.find((r) => r.name === name);
  if (existing) return existing.id;
  const res = await call("POST", "/api/v1/roles", {
    name,
    permission_ids: permissions,
  });
  const body = (await res.json()) as { id: string };
  return body.id;
}

/** One permission grant per call — assign_permission_to_role upserts scope. */
async function grant(roleId: string, code: string, scope: string): Promise<void> {
  await call("POST", `/api/v1/roles/${roleId}/permissions`, {
    permission_codes: [code],
    scope_type: scope,
  });
}

export interface SeededWorld {
  templateVersionId: string;
  assessmentId: string;
  componentKeys: string[];
  /** subject_enrolment_id per student name, from the sheet. */
  rows: { student_name: string; subject_enrolment_id: string }[];
}

/**
 * Build the full Phase 3-4 structure for one class+subject: template +
 * active version + term + assessment + three students with all-entered
 * scores. Re-running advances nothing: the assessment is found by its
 * stable label and returned as-is.
 */
export async function seedAssessmentWorld(): Promise<SeededWorld> {
  await loginAs(ADMIN.email, ADMIN.password);

  const teacherId = await ensureUser(TEACHER.email, TEACHER.password);
  const reviewerId = await ensureUser(REVIEWER.email, REVIEWER.password);
  const teacherRole = await ensureRoleWith("E2E Teacher", [["scores.enter", "assigned"]]);
  await grant(teacherRole, "assessments.view", "school");
  await grant(teacherRole, "scores.submit", "assigned");
  const reviewerRole = await ensureRoleWith("E2E Reviewer", [["scores.review", "school"]]);
  await grant(reviewerRole, "assessments.view", "school");
  await call("POST", `/api/v1/users/${teacherId}/roles`, { role_id: teacherRole });
  await call("POST", `/api/v1/users/${reviewerId}/roles`, { role_id: reviewerRole });

  // template + version (unique name → idempotent via 409 skip + list lookup)
  const tRes = await call("POST", "/api/v1/assessment-templates", {
    name: "E2E Template",
    components: [
      { key: "CA1", label: "First CA", max_score: "10.00", weight: "10", required: true },
      { key: "Exam", label: "Exam", max_score: "60.00", weight: "60", required: true },
    ],
  });
  let versionId: string;
  if (tRes.status === 201) {
    const t = (await tRes.json()) as { id: string };
    const vRes = await call("POST", `/api/v1/assessment-templates/${t.id}/versions`, {});
    const v = (await vRes.json()) as { id: string };
    await call("POST", `/api/v1/assessment-templates/${t.id}/versions/${v.id}/activate`, {});
    versionId = v.id;
  } else {
    const templates = (await (await call("GET", "/api/v1/assessment-templates")).json()) as {
      id: string;
      name: string;
    }[];
    const t = templates.find((x) => x.name === "E2E Template");
    if (!t) throw new Error("E2E Template neither created nor found");
    const versions = (await (
      await call("GET", `/api/v1/assessment-templates/${t.id}/versions`)
    ).json()) as { id: string; status: string }[];
    const active = versions.find((v) => v.status === "active");
    if (!active) throw new Error("no active version on the E2E template");
    versionId = active.id;
  }

  // academic structure + students are seeded by migrations (Seed School);
  // reuse its single class + subject via the reference lists
  const classes = (await (await call("GET", "/api/v1/classes")).json()) as { id: string }[];
  const subjects = (await (await call("GET", "/api/v1/subjects")).json()) as { id: string }[];
  const classId = classes[0]!.id;
  const subjectId = subjects[0]!.id;
  const sessions = (await (await call("GET", "/api/v1/academic-sessions")).json()) as {
    id: string;
  }[];
  const terms = (await (
    await call("GET", "/api/v1/terms", { session_id: sessions[0]!.id })
  ).json()) as { id: string }[];
  const termId = terms[0]!.id;

  const aRes = await call("POST", "/api/v1/assessments", {
    term_id: termId,
    class_id: classId,
    subject_id: subjectId,
    template_version_id: versionId,
  });
  let assessmentId: string;
  if (aRes.status === 201) {
    assessmentId = ((await aRes.json()) as { id: string }).id;
  } else {
    const list = (await (await call("GET", "/api/v1/assessments", { class_id: classId })).json()) as {
      id: string;
      term_id: string;
      subject_id: string;
    }[];
    const found = list.find((a) => a.term_id === termId && a.subject_id === subjectId);
    if (!found) throw new Error("assessment neither created nor found");
    assessmentId = found.id;
  }

  // the sheet: enter every cell as the TEACHER (assigned scope path)
  await loginAs(TEACHER.email, TEACHER.password);
  const sheet = (await (await call("GET", `/api/v1/assessments/${assessmentId}/sheet`)).json()) as {
    rows: { subject_enrolment_id: string; student_name: string; scores: Record<string, unknown> }[];
  };
  const rows = sheet.rows.map((r) => ({
    student_name: r.student_name,
    subject_enrolment_id: r.subject_enrolment_id,
  }));
  if (sheet.rows.every((r) => Object.keys(r.scores).length === 0)) {
    const put = await call("PUT", `/api/v1/assessments/${assessmentId}/scores`, {
      rows: sheet.rows.flatMap((r) =>
        ["CA1", "Exam"].map((component_key, i) => ({
          subject_enrolment_id: r.subject_enrolment_id,
          component_key,
          status: "entered",
          value: 8 + i * 20,
        })),
      ),
    });
    if (!put.ok) throw new Error(`score entry failed: ${put.status}`);
  }

  return { templateVersionId: versionId, assessmentId, componentKeys: ["CA1", "Exam"], rows };
}

/** UI login for a test's own browser context (the honest path — the form). */
export async function loginToken(
  page: import("@playwright/test").Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();
}

/** Enroll the dev admin in MFA through the API; returns the base32 secret. */
export async function enrollMfa(): Promise<{ secret: string }> {
  await loginAs(ADMIN.email, ADMIN.password);
  const setup = await call("GET", "/api/v1/auth/users/me/mfa/setup");
  if (!setup.ok) throw new Error(`mfa setup failed: ${setup.status}`);
  const body = (await setup.json()) as { secret: string };
  const verify = await call("POST", "/api/v1/auth/users/me/mfa/verify", {
    totp_code: totpNow(body.secret),
  });
  if (!verify.ok) throw new Error(`mfa verify failed: ${verify.status}`);
  return { secret: body.secret };
}
