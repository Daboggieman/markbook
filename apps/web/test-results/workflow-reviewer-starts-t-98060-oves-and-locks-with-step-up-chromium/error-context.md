# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: workflow.spec.ts >> reviewer starts the review; admin approves and locks with step-up
- Location: e2e/workflow.spec.ts:54:1

# Error details

```
Error: create failed: /api/v1/class-subjects?class_id=9b82e49e-6586-44bb-b795-719ac7edeffd → 409
```

# Test source

```ts
  77  |   }[];
  78  |   const existing = roles.find((r) => r.name === name);
  79  |   if (existing) return existing.id;
  80  |   const res = await call("POST", "/api/v1/roles", {
  81  |     name,
  82  |     permission_ids: permissions,
  83  |   });
  84  |   const body = (await res.json()) as { id: string };
  85  |   return body.id;
  86  | }
  87  | 
  88  | /** One permission grant per call — assign_permission_to_role upserts scope. */
  89  | async function grant(roleId: string, code: string, scope: string): Promise<void> {
  90  |   await call("POST", `/api/v1/roles/${roleId}/permissions`, {
  91  |     permission_codes: [code],
  92  |     scope_type: scope,
  93  |   });
  94  | }
  95  | 
  96  | export interface SeededWorld {
  97  |   templateVersionId: string;
  98  |   assessmentId: string;
  99  |   componentKeys: string[];
  100 |   /** subject_enrolment_id per student name, from the sheet. */
  101 |   rows: { student_name: string; subject_enrolment_id: string }[];
  102 | }
  103 | 
  104 | /**
  105 |  * Build the full Phase 3-4 structure for one class+subject: template +
  106 |  * active version + term + assessment + three students with all-entered
  107 |  * scores. Re-running advances nothing: the assessment is found by its
  108 |  * stable label and returned as-is.
  109 |  */
  110 | export async function seedAssessmentWorld(): Promise<SeededWorld> {
  111 |   await loginAs(ADMIN.email, ADMIN.password);
  112 | 
  113 |   // Fresh session per run — the downstream chain (term, enrolments,
  114 |   // assessment) hangs off it, so repeated walks never collide.
  115 |   const sessionName = `E2E ${new Date().toISOString().replace("T", " ").slice(0, 19)}`;
  116 | 
  117 |   const teacherId = await ensureUser(TEACHER.email, TEACHER.password);
  118 |   const reviewerId = await ensureUser(REVIEWER.email, REVIEWER.password);
  119 |   const teacherRole = await ensureRoleWith("E2E Teacher", [["scores.enter", "assigned"]]);
  120 |   await grant(teacherRole, "assessments.view", "school");
  121 |   await grant(teacherRole, "scores.submit", "assigned");
  122 |   const reviewerRole = await ensureRoleWith("E2E Reviewer", [["scores.review", "school"]]);
  123 |   await grant(reviewerRole, "assessments.view", "school");
  124 |   await call("POST", `/api/v1/users/${teacherId}/roles`, { role_id: teacherRole });
  125 |   await call("POST", `/api/v1/users/${reviewerId}/roles`, { role_id: reviewerRole });
  126 | 
  127 |   // template + version (unique name → idempotent via 409 skip + list lookup)
  128 |   const definition = {
  129 |     components: [
  130 |       { key: "CA1", label: "First CA", max_score: "10.00", weight: "10", required: true },
  131 |       { key: "Exam", label: "Exam", max_score: "60.00", weight: "60", required: true },
  132 |     ],
  133 |   };
  134 |   const tRes = await call("POST", "/api/v1/assessment-templates", {
  135 |     name: "E2E Template",
  136 |     definition,
  137 |   });
  138 |   let versionId: string;
  139 |   if (tRes.status === 201) {
  140 |     const t = (await tRes.json()) as { id: string };
  141 |     const vRes = await call("POST", `/api/v1/assessment-templates/${t.id}/versions`, {
  142 |       definition,
  143 |     });
  144 |     const v = (await vRes.json()) as { id: string };
  145 |     await call("POST", `/api/v1/template-versions/${v.id}/activate`, {});
  146 |     versionId = v.id;
  147 |   } else {
  148 |     const templates = (await (await call("GET", "/api/v1/assessment-templates")).json()) as {
  149 |       id: string;
  150 |       name: string;
  151 |     }[];
  152 |     const t = templates.find((x) => x.name === "E2E Template");
  153 |     if (!t) throw new Error("E2E Template neither created nor found");
  154 |     const versions = (await (
  155 |       await call("GET", `/api/v1/assessment-templates/${t.id}/versions`)
  156 |     ).json()) as { id: string; status: string }[];
  157 |     const active = versions.find((v) => v.status === "active");
  158 |     if (!active) throw new Error("no active version on the E2E template");
  159 |     versionId = active.id;
  160 |   }
  161 | 
  162 |   // --- academic structure: fresh SESSION per run → everything downstream
  163 |   // (term, assessment) is new each run, so the walk is rerun-safe; the
  164 |   // class/subject/template are shared and found-or-created.
  165 |   const classes = (await (await call("GET", "/api/v1/classes")).json()) as { id: string }[];
  166 |   const classId = classes[0]!.id;
  167 | 
  168 |   async function findOrCreate<T>(
  169 |     listPath: string,
  170 |     match: (x: T) => boolean,
  171 |     create: () => Promise<Response>,
  172 |   ): Promise<T> {
  173 |     const existing = (await (await call("GET", listPath)).json()) as T[];
  174 |     const found = existing.find(match);
  175 |     if (found) return found;
  176 |     const res = await create();
> 177 |     if (res.status !== 201) throw new Error(`create failed: ${listPath} → ${res.status}`);
      |                                   ^ Error: create failed: /api/v1/class-subjects?class_id=9b82e49e-6586-44bb-b795-719ac7edeffd → 409
  178 |     return (await res.json()) as T;
  179 |   }
  180 | 
  181 |   const session = await findOrCreate<{ id: string; name: string }>(
  182 |     "/api/v1/academic-sessions",
  183 |     (s) => s.name === sessionName,
  184 |     () => call("POST", "/api/v1/academic-sessions", { name: sessionName, is_current: true }),
  185 |   );
  186 |   const term = await findOrCreate<{ id: string; name: string }>(
  187 |     `/api/v1/terms?session_id=${session.id}`,
  188 |     () => false,
  189 |     () =>
  190 |       call("POST", "/api/v1/terms", {
  191 |         session_id: session.id,
  192 |         name: "First Term",
  193 |         ordinal: 1,
  194 |         is_current: true,
  195 |       }),
  196 |   );
  197 |   const subject = await findOrCreate<{ id: string; name: string }>(
  198 |     "/api/v1/subjects",
  199 |     (s) => s.name === "E2E Subject",
  200 |     () => call("POST", "/api/v1/subjects", { name: "E2E Subject", code: "E2E" }),
  201 |   );
  202 |   await findOrCreate<{ id: string }>(
  203 |     `/api/v1/class-subjects?class_id=${classId}`,
  204 |     () => false,
  205 |     () => call("POST", "/api/v1/class-subjects", { class_id: classId, subject_id: subject.id }),
  206 |   );
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
```