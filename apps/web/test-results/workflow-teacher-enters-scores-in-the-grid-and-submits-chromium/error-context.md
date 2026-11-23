# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workflow.spec.ts >> teacher enters scores in the grid and submits
- Location: e2e/workflow.spec.ts:34:1

# Error details

```
Error: process run failed
```

# Test source

```ts
  207 | 
  208 |   // three students (shared across runs), enrolled into the fresh session —
  209 |   // enrol_student creates one subject_enrolment per class subject
  210 |   const allStudents = (await (await call("GET", "/api/v1/students?limit=200")).json()) as {
  211 |     id: string;
  212 |     admission_no: string | null;
  213 |   }[];
  214 |   const studentIds: string[] = [];
  215 |   for (const [first, adm] of [
  216 |     ["Ada", "E2E-ADA"],
  217 |     ["Bayo", "E2E-BAYO"],
  218 |     ["Chidi", "E2E-CHIDI"],
  219 |   ] as const) {
  220 |     const existing = allStudents.find((s) => s.admission_no === adm);
  221 |     const studentId =
  222 |       existing?.id ??
  223 |       (await (async () => {
  224 |         const res = await call("POST", "/api/v1/students", {
  225 |           first_name: first,
  226 |           last_name: "E2E",
  227 |           admission_no: adm,
  228 |         });
  229 |         if (res.status !== 201) throw new Error(`student create failed: ${res.status}`);
  230 |         return ((await res.json()) as { id: string }).id;
  231 |       })());
  232 |     await call("POST", "/api/v1/enrolments", {
  233 |       student_id: studentId,
  234 |       session_id: session.id,
  235 |       class_id: classId,
  236 |     }); // 409 on re-run within the same session — fine either way
  237 |     studentIds.push(studentId);
  238 |   }
  239 | 
  240 |   // the teacher's assigned-scope cover (scores.enter/submit re-check this)
  241 |   await call("POST", "/api/v1/teacher-assignments", {
  242 |     teacher_user_id: teacherId,
  243 |     session_id: session.id,
  244 |     class_id: classId,
  245 |     subject_id: subject.id,
  246 |     role: "subject",
  247 |   });
  248 | 
  249 |   const aRes = await call("POST", "/api/v1/assessments", {
  250 |     term_id: term.id,
  251 |     class_id: classId,
  252 |     subject_id: subject.id,
  253 |     template_version_id: versionId,
  254 |   });
  255 |   if (aRes.status !== 201) throw new Error(`assessment create failed: ${aRes.status}`);
  256 |   const assessmentId = ((await aRes.json()) as { id: string }).id;
  257 | 
  258 |   // the sheet: enter every cell as the TEACHER (assigned scope path)
  259 |   await loginAs(TEACHER.email, TEACHER.password);
  260 |   const sheet = (await (await call("GET", `/api/v1/assessments/${assessmentId}/sheet`)).json()) as {
  261 |     rows: { subject_enrolment_id: string; student_name: string; scores: Record<string, unknown> }[];
  262 |   };
  263 |   const rows = sheet.rows.map((r) => ({
  264 |     student_name: r.student_name,
  265 |     subject_enrolment_id: r.subject_enrolment_id,
  266 |   }));
  267 |   if (sheet.rows.every((r) => Object.keys(r.scores).length === 0)) {
  268 |     const put = await call("PUT", `/api/v1/assessments/${assessmentId}/scores`, {
  269 |       rows: sheet.rows.flatMap((r) =>
  270 |         ["CA1", "Exam"].map((component_key, i) => ({
  271 |           subject_enrolment_id: r.subject_enrolment_id,
  272 |           component_key,
  273 |           status: "entered",
  274 |           value: 8 + i * 20,
  275 |         })),
  276 |       ),
  277 |     });
  278 |     if (!put.ok) throw new Error(`score entry failed: ${put.status}`);
  279 |   }
  280 | 
  281 |   // the approval guard needs a CURRENT SUCCESSFUL processing run: create
  282 |   // (or find) the scheme, fire the process job, and wait for the worker
  283 |   // to consume it — no worker means the walk dead-ends at Approve.
  284 |   // Back to the ADMIN: scheme create/activate (assessments.manage) and
  285 |   // process (results.process) are admin permissions the teacher lacks.
  286 |   await loginAs(ADMIN.email, ADMIN.password);
  287 |   const scheme = await findOrCreate<{ id: string; name: string }>(
  288 |     "/api/v1/grading-schemes",
  289 |     (s) => s.name === "E2E Scheme",
  290 |     () => call("POST", "/api/v1/grading-schemes", { name: "E2E Scheme", definition: SCHEME_DEFINITION }),
  291 |   );
  292 |   // activating an already-active version 409s — harmless, call() passes it
  293 |   await call("POST", `/api/v1/grading-schemes/${scheme.id}/activate`, {});
  294 |   const procRes = await call("POST", `/api/v1/assessments/${assessmentId}/process`, {
  295 |     scheme_id: scheme.id,
  296 |   });
  297 |   if (procRes.status !== 202 && procRes.status !== 200) {
  298 |     throw new Error(`process enqueue failed: ${procRes.status}`);
  299 |   }
  300 |   const procJob = ((await procRes.json()) as { job_id?: string }).job_id;
  301 |   if (procJob) {
  302 |     for (let i = 0; i < 60; i++) {
  303 |       const job = (await (await call("GET", `/api/v1/jobs/${procJob}`)).json()) as {
  304 |         status: string;
  305 |       };
  306 |       if (job.status === "succeeded") break;
> 307 |       if (job.status === "failed") throw new Error("process run failed");
      |                                          ^ Error: process run failed
  308 |       await new Promise((r) => setTimeout(r, 500));
  309 |     }
  310 |   }
  311 | 
  312 |   return { templateVersionId: versionId, assessmentId, componentKeys: ["CA1", "Exam"], rows };
  313 | }
  314 | 
  315 | const SCHEME_DEFINITION = {
  316 |   rounding_mode: "ROUND_HALF_UP",
  317 |   precision: 0,
  318 |   missing_policy: "flag_incomplete",
  319 |   absent_policy: "treat_zero",
  320 |   exempt_policy: "exclude_and_renormalise",
  321 |   boundaries: [
  322 |     { grade: "A", min: 70, max: 100 },
  323 |     { grade: "B", min: 60, max: 69 },
  324 |     { grade: "C", min: 50, max: 59 },
  325 |     { grade: "D", min: 45, max: 49 },
  326 |     { grade: "E", min: 40, max: 44 },
  327 |     { grade: "F", min: 0, max: 39 },
  328 |   ],
  329 |   tie_policy: "dense",
  330 | };
  331 | 
  332 | /** UI login for a test's own browser context (the honest path — the form). */
  333 | export async function loginToken(
  334 |   page: import("@playwright/test").Page,
  335 |   email: string,
  336 |   password: string,
  337 | ): Promise<void> {
  338 |   await page.goto("/login");
  339 |   await page.getByLabel("Email").fill(email);
  340 |   await page.getByLabel("Password").fill(password);
  341 |   await page.getByRole("button", { name: "Sign in" }).click();
  342 |   await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  343 | }
  344 | 
  345 | /** Enroll the dev admin in MFA through the API; returns the base32 secret. */
  346 | export async function enrollMfa(): Promise<{ secret: string }> {
  347 |   await loginAs(ADMIN.email, ADMIN.password);
  348 |   const setup = await call("GET", "/api/v1/auth/users/me/mfa/setup");
  349 |   if (!setup.ok) throw new Error(`mfa setup failed: ${setup.status}`);
  350 |   const body = (await setup.json()) as { secret: string };
  351 |   const verify = await call("POST", "/api/v1/auth/users/me/mfa/verify", {
  352 |     totp_code: totpNow(body.secret),
  353 |   });
  354 |   if (!verify.ok) throw new Error(`mfa verify failed: ${verify.status}`);
  355 |   return { secret: body.secret };
  356 | }
  357 | 
```