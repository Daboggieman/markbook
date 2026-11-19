/**
 * Students admin: list with filters, duplicate-gated create, archive,
 * enrolment and guardian management per student.
 *
 * The create flow mirrors the backend contract: a plain POST may be refused
 * with POSSIBLE_DUPLICATE; the UI checks first (check-duplicates) and offers
 * an explicit "create anyway" (allow_duplicate) only when candidates exist.
 */
import type { components } from "@markbook/api-client";
import { useState, type FormEvent, type ReactNode } from "react";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { hasPermission, useAuth } from "../auth/AuthContext";
import { DataTable, Empty, ErrorBanner, Field, Loading, Panel } from "../components/ui";
import { unwrap, useApiQuery } from "../hooks/useApiQuery";

type Student = components["schemas"]["StudentResponse"];
type Candidate = components["schemas"]["DuplicateCandidate"];
type Session = components["schemas"]["AcademicSessionResponse"];
type Class = components["schemas"]["ClassResponse"];
type Section = components["schemas"]["SectionResponse"];
type Guardian = components["schemas"]["GuardianResponse"];

const dateOrNull = (v: FormDataEntryValue | null): string | null => {
  const s = String(v ?? "");
  return s === "" ? null : s;
};

/** Local copy of AcademicPage's CreateForm (module-private by design). */
function CreateForm({
  can,
  submitLabel,
  onSubmit,
  children,
}: {
  can: boolean;
  submitLabel: string;
  onSubmit: (form: FormData) => Promise<void>;
  children: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!can) return null;
  return (
    <form
      className="inline-form"
      onSubmit={async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await onSubmit(new FormData(e.currentTarget));
          e.currentTarget.reset();
        } catch (err) {
          setError(problemMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
      <button type="submit" disabled={busy}>
        {submitLabel}
      </button>
      {error && <ErrorBanner message={error} />}
    </form>
  );
}

interface StudentDraft {
  first_name: string;
  middle_name: string | null;
  last_name: string;
  dob: string | null;
  sex: string | null;
  admission_no: string | null;
}

const draftFrom = (f: FormData): StudentDraft => ({
  first_name: String(f.get("first_name") || ""),
  middle_name: String(f.get("middle_name") || "") || null,
  last_name: String(f.get("last_name") || ""),
  dob: dateOrNull(f.get("dob")),
  sex: String(f.get("sex") || "") || null,
  admission_no: String(f.get("admission_no") || "") || null,
});

/**
 * Create panel with the duplicate gate: submit runs check-duplicates first;
 * candidates are shown with an explicit "create anyway" confirmation.
 */
function CreateStudentPanel({ canCreate, onCreated }: { canCreate: boolean; onCreated: () => void }) {
  const [candidates, setCandidates] = useState<{ draft: StudentDraft; hits: Candidate[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const create = async (draft: StudentDraft, allow: boolean) => {
    await unwrap(
      api.POST("/api/v1/students", {
        body: { ...draft, guardian_ids: [], allow_duplicate: allow },
      }),
    );
    setDone(`${draft.first_name} ${draft.last_name} created`);
    setCandidates(null);
    onCreated();
  };

  const check = async (f: FormData) => {
    setBusy(true);
    setError(null);
    setDone(null);
    const draft = draftFrom(f);
    try {
      const check = await unwrap(
        api.POST("/api/v1/students/check-duplicates", {
          body: { first_name: draft.first_name, last_name: draft.last_name },
        }),
      );
      if (check.candidates.length > 0) {
        setCandidates({ draft, hits: check.candidates });
      } else {
        await create(draft, false);
      }
    } catch (err) {
      setError(problemMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (!canCreate) return null;
  return (
    <Panel title="Enrol a student">
      <form
        className="inline-form"
        onSubmit={async (e: FormEvent<HTMLFormElement>) => {
          e.preventDefault();
          await check(new FormData(e.currentTarget));
        }}
      >
        <Field label="First name">
          <input name="first_name" required />
        </Field>
        <Field label="Middle">
          <input name="middle_name" />
        </Field>
        <Field label="Last name">
          <input name="last_name" required />
        </Field>
        <Field label="Date of birth">
          <input name="dob" type="date" />
        </Field>
        <Field label="Sex">
          <select name="sex" defaultValue="">
            <option value="">—</option>
            <option value="m">Male</option>
            <option value="f">Female</option>
          </select>
        </Field>
        <Field label="Admission no.">
          <input name="admission_no" />
        </Field>
        <button type="submit" disabled={busy}>
          Check &amp; create
        </button>
      </form>
      {error && <ErrorBanner message={error} />}
      {done && <p className="loading">{done}</p>}
      {candidates && (
        <div className="duplicate-confirm">
          <p>
            <strong>{candidates.hits.length} similar student(s) found:</strong>
          </p>
          <DataTable headers={["Name", "DOB", "Admission no.", "Similarity"]}>
            {candidates.hits.map((c) => (
              <tr key={c.student_id}>
                <td>
                  {c.first_name} {c.last_name}
                </td>
                <td>{c.dob ?? "—"}</td>
                <td>{c.admission_no ?? "—"}</td>
                <td>{Math.round(c.similarity * 100)}%</td>
              </tr>
            ))}
          </DataTable>
          <button type="button" disabled={busy} onClick={() => create(candidates.draft, true)}>
            Create anyway (allow duplicate)
          </button>{" "}
          <button
            type="button"
            onClick={() => {
              setCandidates(null);
            }}
          >
            Cancel
          </button>
        </div>
      )}
    </Panel>
  );
}

function EnrolForm({ studentId, onDone }: { studentId: string; onDone: () => void }) {
  const sessionsQ = useApiQuery(() => unwrap(api.GET("/api/v1/academic-sessions", {})), []);
  const classesQ = useApiQuery(() => unwrap(api.GET("/api/v1/classes", {})), []);
  const [sessionId, setSessionId] = useState("");
  const [classId, setClassId] = useState("");
  const sectionsQ = useApiQuery(
    () =>
      classId
        ? unwrap(api.GET("/api/v1/sections", { params: { query: { class_id: classId } } }))
        : Promise.resolve([] as Section[]),
    [classId],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="inline-form"
      onSubmit={async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          const f = new FormData(e.currentTarget);
          const section = String(f.get("section_id") || "");
          await unwrap(
            api.POST("/api/v1/enrolments", {
              body: {
                student_id: studentId,
                session_id: String(f.get("session_id") || ""),
                class_id: String(f.get("class_id") || ""),
                ...(section ? { section_id: section } : {}),
              },
            }),
          );
          onDone();
        } catch (err) {
          setError(problemMessage(err));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Field label="Session">
        <select name="session_id" required value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
          <option value="">—</option>
          {(sessionsQ.data ?? []).map((s: Session) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Class">
        <select name="class_id" required value={classId} onChange={(e) => setClassId(e.target.value)}>
          <option value="">—</option>
          {(classesQ.data ?? []).map((c: Class) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Section">
        <select name="section_id" defaultValue="">
          <option value="">—</option>
          {(sectionsQ.data ?? []).map((s: Section) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </Field>
      <button type="submit" disabled={busy || !sessionId || !classId}>
        Enrol
      </button>
      {error && <ErrorBanner message={error} />}
    </form>
  );
}

function GuardiansPanel({ studentId, canCreate }: { studentId: string; canCreate: boolean }) {
  const q = useApiQuery(
    () => unwrap(api.GET("/api/v1/students/{student_id}/guardians", { params: { path: { student_id: studentId } } })),
    [studentId],
  );
  return (
    <div>
      {q.loading && <Loading />}
      {q.error && <ErrorBanner message={q.error} />}
      {q.data && q.data.length === 0 && <Empty label="No guardians linked." />}
      {q.data && q.data.length > 0 && (
        <DataTable headers={["Name", "Phone", "Email"]}>
          {q.data.map((g: Guardian) => (
            <tr key={g.id}>
              <td>{g.name}</td>
              <td>{g.phone ?? "—"}</td>
              <td>{g.email ?? "—"}</td>
            </tr>
          ))}
        </DataTable>
      )}
      {canCreate && (
        <CreateForm
          can={canCreate}
          submitLabel="Create & link guardian"
          onSubmit={async (f) => {
            const g = await unwrap(
              api.POST("/api/v1/guardians", {
                body: {
                  name: String(f.get("name") || ""),
                  phone: String(f.get("phone") || "") || null,
                  email: String(f.get("email") || "") || null,
                  address: String(f.get("address") || "") || null,
                },
              }),
            );
            await unwrap(
              api.POST("/api/v1/students/{student_id}/guardians", {
                params: { path: { student_id: studentId } },
                body: { guardian_id: g.id, is_primary: false },
              }),
            );
            q.reload();
          }}
        >
          <Field label="Guardian name">
            <input name="name" required />
          </Field>
          <Field label="Phone">
            <input name="phone" />
          </Field>
          <Field label="Email">
            <input name="email" />
          </Field>
        </CreateForm>
      )}
    </div>
  );
}

function StudentsPageInner() {
  const { profile } = useAuth();
  const canCreate = hasPermission(profile, "students.create");
  const canArchive = hasPermission(profile, "students.archive");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const sessionsQ = useApiQuery(() => unwrap(api.GET("/api/v1/academic-sessions", {})), []);
  const listQ = useApiQuery(() => {
    const query: Record<string, string> = {};
    if (q) query.q = q;
    if (status) query.status = status;
    if (sessionId) query.session_id = sessionId;
    return unwrap(api.GET("/api/v1/students", { params: { query } }));
  }, [q, status, sessionId]);
  return (
    <section>
      <h2>Students</h2>
      <CreateStudentPanel canCreate={canCreate} onCreated={listQ.reload} />
      <Panel title="All students">
        <div className="inline-form">
          <Field label="Search">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="name…" />
          </Field>
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">all</option>
              <option value="active">active</option>
              <option value="archived">archived</option>
            </select>
          </Field>
          <Field label="Session">
            <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
              <option value="">all</option>
              {(sessionsQ.data ?? []).map((s: Session) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {listQ.loading && <Loading />}
        {listQ.error && <ErrorBanner message={listQ.error} />}
        {listQ.data && listQ.data.length === 0 && <Empty label="No students match." />}
        {listQ.data && listQ.data.length > 0 && (
          <DataTable headers={["Name", "Admission no.", "Sex", "DOB", "Status", ""]}>
            {listQ.data.map((s: Student) => (
              <tr key={s.id}>
                <td>
                  {s.first_name} {s.middle_name ?? ""} {s.last_name}
                </td>
                <td>{s.admission_no ?? "—"}</td>
                <td>{s.sex === "m" ? "Male" : s.sex === "f" ? "Female" : (s.sex ?? "—")}</td>
                <td>{s.dob ?? "—"}</td>
                <td>{s.status}</td>
                <td>
                  {s.status === "active" && (
                    <>
                      <button type="button" onClick={() => setOpen(open === s.id ? null : s.id)}>
                        Enrol / guardians
                      </button>{" "}
                      {canArchive && (
                        <button
                          type="button"
                          onClick={async () => {
                            setRowError(null);
                            try {
                              await unwrap(
                                api.POST("/api/v1/students/{student_id}/archive", {
                                  params: { path: { student_id: s.id } },
                                  body: { version: s.version },
                                }),
                              );
                              listQ.reload();
                            } catch (err) {
                              setRowError(problemMessage(err));
                            }
                          }}
                        >
                          Archive
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </DataTable>
        )}
        {rowError && <ErrorBanner message={rowError} />}
        {open && listQ.data && (
          <div className="student-detail">
            {(() => {
              const s = listQ.data.find((x: Student) => x.id === open);
              if (!s || s.status !== "active") return null;
              return (
                <>
                  <p>
                    <strong>
                      {s.first_name} {s.last_name}
                    </strong>{" "}
                    — actions
                  </p>
                  <EnrolForm studentId={s.id} onDone={listQ.reload} />
                  <GuardiansPanel studentId={s.id} canCreate={canCreate} />
                </>
              );
            })()}
          </div>
        )}
      </Panel>
    </section>
  );
}

export function StudentsPage() {
  const { profile } = useAuth();
  if (!hasPermission(profile, "students.view")) {
    return (
      <section>
        <h2>Students</h2>
        <ErrorBanner message="You do not have permission to view students." />
      </section>
    );
  }
  return <StudentsPageInner />;
}
