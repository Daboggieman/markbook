/**
 * Academic setup: sessions → terms, levels → classes → sections, subjects,
 * class-subjects. Everything downstream (students, assessments, scores) keys
 * off rows created here, so this screen is create-only — the API exposes no
 * PATCH for these resources.
 *
 * Visibility: the page needs `academic.view`; mutating forms additionally
 * need `academic.manage` (UI filter only — the API re-checks everything).
 */
import type { components } from "@markbook/api-client";
import { useState, type FormEvent, type ReactNode } from "react";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { hasPermission, useAuth } from "../auth/AuthContext";
import { DataTable, Empty, ErrorBanner, Field, Loading, Panel } from "../components/ui";
import { unwrap, useApiQuery } from "../hooks/useApiQuery";

type Session = components["schemas"]["AcademicSessionResponse"];
type Term = components["schemas"]["TermResponse"];
type Level = components["schemas"]["EducationalLevelResponse"];
type Class = components["schemas"]["ClassResponse"];
type Section = components["schemas"]["SectionResponse"];
type Subject = components["schemas"]["SubjectResponse"];
type ClassSubject = components["schemas"]["ClassSubjectResponse"];

const dateOrNull = (v: string): string | null => (v === "" ? null : v);

/**
 * One inline create form. `children` are the Field inputs (uncontrolled —
 * read via FormData); submit runs, then the parent query reloads.
 */
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

function SessionsPanel({ canManage }: { canManage: boolean }) {
  const q = useApiQuery(() => unwrap(api.GET("/api/v1/academic-sessions", {})), []);
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <>
      <Panel title="Academic sessions">
        <CreateForm
          can={canManage}
          submitLabel="Add session"
          onSubmit={async (f) => {
            await unwrap(
              api.POST("/api/v1/academic-sessions", {
                body: {
                  name: String(f.get("name") || ""),
                  start_date: dateOrNull(String(f.get("start_date") || "")),
                  end_date: dateOrNull(String(f.get("end_date") || "")),
                  is_current: f.get("is_current") === "on",
                },
              }),
            );
            q.reload();
          }}
        >
          <Field label="Name">
            <input name="name" required placeholder="2026/2027" />
          </Field>
          <Field label="Start">
            <input name="start_date" type="date" />
          </Field>
          <Field label="End">
            <input name="end_date" type="date" />
          </Field>
          <Field label="Current">
            <input name="is_current" type="checkbox" />
          </Field>
        </CreateForm>
        {q.loading && <Loading />}
        {q.error && <ErrorBanner message={q.error} />}
        {q.data && q.data.length === 0 && <Empty label="No sessions yet." />}
        {q.data && q.data.length > 0 && (
          <DataTable headers={["Name", "Dates", "Current", ""]}>
            {q.data.map((s: Session) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>
                  {s.start_date ?? "—"} → {s.end_date ?? "—"}
                </td>
                <td>{s.is_current ? "✓" : ""}</td>
                <td>
                  <button type="button" onClick={() => setSelected(s.id)}>
                    Terms
                  </button>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>
      {selected && <TermsPanel sessionId={selected} canManage={canManage} />}
    </>
  );
}

function TermsPanel({ sessionId, canManage }: { sessionId: string; canManage: boolean }) {
  const q = useApiQuery(
    () => unwrap(api.GET("/api/v1/terms", { params: { query: { session_id: sessionId } } })),
    [sessionId],
  );
  return (
    <Panel title="Terms of selected session">
      <CreateForm
        can={canManage}
        submitLabel="Add term"
        onSubmit={async (f) => {
          await unwrap(
            api.POST("/api/v1/terms", {
              body: {
                session_id: sessionId,
                name: String(f.get("name") || ""),
                ordinal: Number(f.get("ordinal")),
                start_date: dateOrNull(String(f.get("start_date") || "")),
                end_date: dateOrNull(String(f.get("end_date") || "")),
                is_current: f.get("is_current") === "on",
              },
            }),
          );
          q.reload();
        }}
      >
        <Field label="Name">
          <input name="name" required placeholder="First Term" />
        </Field>
        <Field label="Ordinal">
          <input name="ordinal" type="number" min={1} required />
        </Field>
        <Field label="Start">
          <input name="start_date" type="date" />
        </Field>
        <Field label="End">
          <input name="end_date" type="date" />
        </Field>
        <Field label="Current">
          <input name="is_current" type="checkbox" />
        </Field>
      </CreateForm>
      {q.loading && <Loading />}
      {q.error && <ErrorBanner message={q.error} />}
      {q.data && q.data.length === 0 && <Empty label="No terms in this session." />}
      {q.data && q.data.length > 0 && (
        <DataTable headers={["Name", "Ordinal", "Dates", "Current"]}>
          {q.data.map((t: Term) => (
            <tr key={t.id}>
              <td>{t.name}</td>
              <td>{t.ordinal}</td>
              <td>
                {t.start_date ?? "—"} → {t.end_date ?? "—"}
              </td>
              <td>{t.is_current ? "✓" : ""}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

function LevelsAndClassesPanel({
  canManage,
  onClassSelected,
}: {
  canManage: boolean;
  onClassSelected: (classId: string) => void;
}) {
  const levelsQ = useApiQuery(() => unwrap(api.GET("/api/v1/educational-levels", {})), []);
  const [levelId, setLevelId] = useState<string | null>(null);
  const classesQ = useApiQuery(
    () =>
      levelId
        ? unwrap(api.GET("/api/v1/classes", { params: { query: { level_id: levelId } } }))
        : Promise.resolve([] as Class[]),
    [levelId],
  );
  return (
    <Panel title="Levels and classes">
      <Field label="Level (seeded)">
        <select
          defaultValue=""
          onChange={(e) => {
            setLevelId(e.target.value || null);
          }}
        >
          <option value="">— pick a level —</option>
          {(levelsQ.data ?? []).map((l: Level) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
      </Field>
      {levelsQ.loading && <Loading />}
      {levelsQ.error && <ErrorBanner message={levelsQ.error} />}
      {levelId && (
        <CreateForm
          can={canManage}
          submitLabel="Add class"
          onSubmit={async (f) => {
            await unwrap(
              api.POST("/api/v1/classes", {
                body: {
                  level_id: levelId,
                  name: String(f.get("name") || ""),
                  ordinal: f.get("ordinal") ? Number(f.get("ordinal")) : null,
                },
              }),
            );
            classesQ.reload();
          }}
        >
          <Field label="Class name">
            <input name="name" required placeholder="Primary 1" />
          </Field>
          <Field label="Ordinal">
            <input name="ordinal" type="number" />
          </Field>
        </CreateForm>
      )}
      {classesQ.loading && levelId && <Loading />}
      {classesQ.error && <ErrorBanner message={classesQ.error} />}
      {levelId && classesQ.data && classesQ.data.length === 0 && (
        <Empty label="No classes at this level." />
      )}
      {levelId && classesQ.data && classesQ.data.length > 0 && (
        <DataTable headers={["Name", "Ordinal", ""]}>
          {classesQ.data.map((c: Class) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td>{c.ordinal ?? "—"}</td>
              <td>
                <button type="button" onClick={() => onClassSelected(c.id)}>
                  Sections / subjects
                </button>
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

function ClassDetailPanel({
  classId,
  canManage,
}: {
  classId: string;
  canManage: boolean;
}) {
  const sectionsQ = useApiQuery(
    () => unwrap(api.GET("/api/v1/sections", { params: { query: { class_id: classId } } })),
    [classId],
  );
  const subjectsQ = useApiQuery(() => unwrap(api.GET("/api/v1/subjects", {})), []);
  const csQ = useApiQuery(
    () => unwrap(api.GET("/api/v1/class-subjects", { params: { query: { class_id: classId } } })),
    [classId],
  );
  const subjectName = (subjectId: string): string =>
    (subjectsQ.data ?? []).find((s: Subject) => s.id === subjectId)?.name ?? subjectId.slice(0, 8);
  return (
    <>
      <Panel title="Sections of selected class">
        <CreateForm
          can={canManage}
          submitLabel="Add section"
          onSubmit={async (f) => {
            await unwrap(
              api.POST("/api/v1/sections", {
                body: { class_id: classId, name: String(f.get("name") || "") },
              }),
            );
            sectionsQ.reload();
          }}
        >
          <Field label="Section name">
            <input name="name" required placeholder="A" />
          </Field>
        </CreateForm>
        {sectionsQ.loading && <Loading />}
        {sectionsQ.error && <ErrorBanner message={sectionsQ.error} />}
        {sectionsQ.data && sectionsQ.data.length === 0 && <Empty label="No sections." />}
        {sectionsQ.data && sectionsQ.data.length > 0 && (
          <DataTable headers={["Name"]}>
            {sectionsQ.data.map((s: Section) => (
              <tr key={s.id}>
                <td>{s.name}</td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>
      <Panel title="Subjects taught in this class">
        <CreateForm
          can={canManage}
          submitLabel="Assign subject"
          onSubmit={async (f) => {
            await unwrap(
              api.POST("/api/v1/class-subjects", {
                body: {
                  class_id: classId,
                  subject_id: String(f.get("subject_id") || ""),
                  is_optional: f.get("is_optional") === "on",
                },
              }),
            );
            csQ.reload();
          }}
        >
          <Field label="Subject">
            <select name="subject_id" required defaultValue="">
              <option value="">— pick a subject —</option>
              {(subjectsQ.data ?? []).map((s: Subject) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.code ? ` (${s.code})` : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Optional">
            <input name="is_optional" type="checkbox" />
          </Field>
        </CreateForm>
        {csQ.loading && <Loading />}
        {csQ.error && <ErrorBanner message={csQ.error} />}
        {csQ.data && csQ.data.length === 0 && <Empty label="No subjects assigned." />}
        {csQ.data && csQ.data.length > 0 && (
          <DataTable headers={["Subject", "Optional"]}>
            {csQ.data.map((cs: ClassSubject) => (
              <tr key={cs.id}>
                <td>{subjectName(cs.subject_id)}</td>
                <td>{cs.is_optional ? "✓" : ""}</td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>
    </>
  );
}

function SubjectsPanel({ canManage }: { canManage: boolean }) {
  const q = useApiQuery(() => unwrap(api.GET("/api/v1/subjects", {})), []);
  return (
    <Panel title="Subjects">
      <CreateForm
        can={canManage}
        submitLabel="Add subject"
        onSubmit={async (f) => {
          await unwrap(
            api.POST("/api/v1/subjects", {
              body: {
                name: String(f.get("name") || ""),
                code: String(f.get("code") || "") || null,
              },
            }),
          );
          q.reload();
        }}
      >
        <Field label="Name">
          <input name="name" required placeholder="Mathematics" />
        </Field>
        <Field label="Code">
          <input name="code" placeholder="MTH" />
        </Field>
      </CreateForm>
      {q.loading && <Loading />}
      {q.error && <ErrorBanner message={q.error} />}
      {q.data && q.data.length === 0 && <Empty label="No subjects yet." />}
      {q.data && q.data.length > 0 && (
        <DataTable headers={["Name", "Code"]}>
          {q.data.map((s: Subject) => (
            <tr key={s.id}>
              <td>{s.name}</td>
              <td>{s.code ?? "—"}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

export function AcademicPage() {
  const { profile } = useAuth();
  const canManage = hasPermission(profile, "academic.manage");
  const [classId, setClassId] = useState<string | null>(null);
  return (
    <section>
      <h2>Academic setup</h2>
      <p className="page-note">Sessions and terms first; then levels, classes and subjects.</p>
      <div className="page-grid">
        <SessionsPanel canManage={canManage} />
        <div className="page-stack">
          <LevelsAndClassesPanel canManage={canManage} onClassSelected={setClassId} />
          <SubjectsPanel canManage={canManage} />
        </div>
        <div className="page-stack">
          {classId ? (
            <ClassDetailPanel classId={classId} canManage={canManage} />
          ) : (
            <Panel title="Sections and class subjects">
              <Empty label="Pick a class on the left to manage its sections and subjects." />
            </Panel>
          )}
        </div>
      </div>
    </section>
  );
}
