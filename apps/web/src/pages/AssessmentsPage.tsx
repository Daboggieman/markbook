/**
 * Assessments admin: list with filters and create. The create form needs
 * reference data (sessions/terms/classes/subjects) plus the ACTIVE template
 * version — the API refuses a draft version with a validation error, so the
 * picker only offers status === "active".
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
type Class = components["schemas"]["ClassResponse"];
type Section = components["schemas"]["SectionResponse"];
type Subject = components["schemas"]["SubjectResponse"];
type Template = components["schemas"]["AssessmentTemplateResponse"];
type Version = components["schemas"]["TemplateVersionResponse"];
type Assessment = components["schemas"]["AssessmentResponse"];

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

interface Reference {
  sessions: Session[];
  terms: Term[];
  classes: Class[];
  sections: Section[];
  subjects: Subject[];
  /** Active template versions labelled "<template name> v<n>". */
  versions: { id: string; label: string }[];
}

/** One fetcher for every lookup list the create form and filters need. */
function useReference(sessionId: string, classId: string): { ref: Reference | null; error: string | null } {
  const q = useApiQuery(async () => {
    const [sessions, classes, subjects, templates] = await Promise.all([
      unwrap(api.GET("/api/v1/academic-sessions", {})),
      unwrap(api.GET("/api/v1/classes", {})),
      unwrap(api.GET("/api/v1/subjects", {})),
      unwrap(api.GET("/api/v1/assessment-templates", {})),
    ]);
    const terms = sessionId
      ? await unwrap(api.GET("/api/v1/terms", { params: { query: { session_id: sessionId } } }))
      : [];
    const sections = classId
      ? await unwrap(api.GET("/api/v1/sections", { params: { query: { class_id: classId } } }))
      : [];
    const versions = (
      await Promise.all(
        templates.map(async (t: Template) => {
          const vs = await unwrap(
            api.GET("/api/v1/assessment-templates/{template_id}/versions", {
              params: { path: { template_id: t.id } },
            }),
          );
          return vs
            .filter((v: Version) => v.status === "active")
            .map((v: Version) => ({ id: v.id, label: `${t.name} v${v.version_no}` }));
        }),
      )
    ).flat();
    return { sessions, terms, classes, sections, subjects, versions };
  }, [sessionId, classId]);
  return { ref: q.data, error: q.error };
}

function CreateAssessmentPanel({ ref_, canManage, onCreated }: { ref_: Reference | null; canManage: boolean; onCreated: () => void }) {
  const [sessionId, setSessionId] = useState("");
  const [classId, setClassId] = useState("");
  if (!canManage) return null;
  if (!ref_) return <Loading label="Loading reference data…" />;
  return (
    <Panel title="Create assessment">
      <CreateForm
        can={canManage}
        submitLabel="Create"
        onSubmit={async (f) => {
          const section = String(f.get("section_id") || "");
          await unwrap(
            api.POST("/api/v1/assessments", {
              body: {
                term_id: String(f.get("term_id") || ""),
                class_id: String(f.get("class_id") || ""),
                subject_id: String(f.get("subject_id") || ""),
                template_version_id: String(f.get("template_version_id") || ""),
                ...(section ? { section_id: section } : {}),
              },
            }),
          );
          onCreated();
        }}
      >
        <Field label="Session">
          <select value={sessionId} onChange={(e) => setSessionId(e.target.value)} required>
            <option value="">—</option>
            {ref_.sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Term">
          <select name="term_id" required defaultValue="">
            <option value="">—</option>
            {ref_.terms.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Class">
          <select value={classId} onChange={(e) => setClassId(e.target.value)} required>
            <option value="">—</option>
            {ref_.classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Section (optional)">
          <select name="section_id" defaultValue="">
            <option value="">—</option>
            {ref_.sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Subject">
          <select name="subject_id" required defaultValue="">
            <option value="">—</option>
            {ref_.subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
                {s.code ? ` (${s.code})` : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Template version (active only)">
          <select name="template_version_id" required defaultValue="">
            <option value="">—</option>
            {ref_.versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </Field>
      </CreateForm>
    </Panel>
  );
}

function AssessmentsPageInner() {
  const { profile } = useAuth();
  const canManage = hasPermission(profile, "assessments.manage");
  const [sessionId, setSessionId] = useState("");
  const [classId, setClassId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const { ref, error: refError } = useReference(sessionId, classId);
  const listQ = useApiQuery(() => {
    const query: Record<string, string> = {};
    if (classId) query.class_id = classId;
    if (subjectId) query.subject_id = subjectId;
    return unwrap(api.GET("/api/v1/assessments", { params: { query } }));
  }, [classId, subjectId]);
  const termName = (id: string): string => ref?.terms.find((t) => t.id === id)?.name ?? id.slice(0, 8);
  const className = (id: string): string => ref?.classes.find((c) => c.id === id)?.name ?? id.slice(0, 8);
  const subjectName = (id: string): string => ref?.subjects.find((s) => s.id === id)?.name ?? id.slice(0, 8);
  return (
    <section>
      <h2>Assessments</h2>
      <CreateAssessmentPanel ref_={ref} canManage={canManage} onCreated={listQ.reload} />
      <Panel title="All assessments">
        <div className="inline-form">
          <Field label="Session">
            <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
              <option value="">all</option>
              {(ref?.sessions ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Class">
            <select value={classId} onChange={(e) => setClassId(e.target.value)}>
              <option value="">all</option>
              {(ref?.classes ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Subject">
            <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">all</option>
              {(ref?.subjects ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {refError && <ErrorBanner message={refError} />}
        {listQ.loading && <Loading />}
        {listQ.error && <ErrorBanner message={listQ.error} />}
        {listQ.data && listQ.data.length === 0 && <Empty label="No assessments yet." />}
        {listQ.data && listQ.data.length > 0 && (
          <DataTable headers={["Subject", "Term", "Class", "Workflow state"]}>
            {listQ.data.map((a: Assessment) => (
              <tr key={a.id}>
                <td>{subjectName(a.subject_id)}</td>
                <td>{termName(a.term_id)}</td>
                <td>{className(a.class_id)}</td>
                <td>
                  <span className={`state-badge state-${a.workflow_state}`}>{a.workflow_state}</span>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>
    </section>
  );
}

export function AssessmentsPage() {
  const { profile } = useAuth();
  if (!hasPermission(profile, "assessments.view")) {
    return (
      <section>
        <h2>Assessments</h2>
        <ErrorBanner message="You do not have permission to view assessments." />
      </section>
    );
  }
  return <AssessmentsPageInner />;
}
