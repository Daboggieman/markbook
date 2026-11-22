/**
 * Reports screen (Phase 6): per published assessment — generate report
 * cards, list what's been published (student-named, versioned), download
 * via the audited presigned-URL endpoint, and request a per-student
 * transcript (202; the job appears when the worker renders it).
 *
 * Downloads open the presigned URL in a new tab — every download is
 * audited server-side (documents.downloaded).
 */
import type { components } from "@markbook/api-client";
import { useState } from "react";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { hasPermission, useAuth } from "../auth/AuthContext";
import { DataTable, Empty, ErrorBanner, Field, Loading, Panel } from "../components/ui";
import { unwrap, useApiQuery } from "../hooks/useApiQuery";

type Assessment = components["schemas"]["AssessmentResponse"];
type DocumentItem = components["schemas"]["DocumentListItem"];

export function ReportsPage() {
  const { profile } = useAuth();
  const canReport = hasPermission(profile, "reports.view");
  const canTranscript = hasPermission(profile, "transcripts.generate");

  const publishedQ = useApiQuery(async () => {
    const all = await unwrap(api.GET("/api/v1/assessments", {}));
    return all.filter((a: Assessment) => a.workflow_state === "published");
  }, []);
  const [assessmentId, setAssessmentId] = useState("");
  const docsQ = useApiQuery(
    () =>
      assessmentId
        ? unwrap(api.GET("/api/v1/documents/assessment/{assessment_id}", { params: { path: { assessment_id: assessmentId } } }))
        : Promise.resolve([] as DocumentItem[]),
    [assessmentId],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canReport) {
    return (
      <section>
        <h2>Reports</h2>
        <ErrorBanner message="You do not have permission to view reports." />
      </section>
    );
  }

  async function generateReportCards() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await unwrap(
        api.POST("/api/v1/documents/report-cards", {
          body: { assessment_id: assessmentId },
        }),
      );
      setNotice(`Report-card generation queued — job ${res.job_id?.slice(0, 8) ?? "?"}…; refresh to see the documents.`);
    } catch (err) {
      setError(problemMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function requestTranscript(enrolmentId: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await unwrap(
        api.POST("/api/v1/documents/transcripts", { body: { enrolment_id: enrolmentId } }),
      );
      setNotice(`Transcript queued — job ${res.job_id?.slice(0, 8) ?? "?"}…; refresh to see the document.`);
    } catch (err) {
      setError(problemMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function download(docId: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await unwrap(api.GET("/api/v1/documents/{document_id}/download", { params: { path: { document_id: docId } } }));
      window.open(res.url, "_blank", "noopener");
    } catch (err) {
      setError(problemMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Reports</h2>
      {publishedQ.loading && <Loading label="Loading published assessments…" />}
      {publishedQ.error && <ErrorBanner message={publishedQ.error} />}
      {publishedQ.data && publishedQ.data.length === 0 && (
        <Empty label="Nothing is published yet — publish an assessment first." />
      )}
      {publishedQ.data && publishedQ.data.length > 0 && (
        <Panel title="Published assessments">
          <Field label="Assessment">
            <select
              value={assessmentId}
              onChange={(e) => {
                setAssessmentId(e.target.value);
                setNotice(null);
                setError(null);
              }}
            >
              <option value="">—</option>
              {publishedQ.data.map((a: Assessment) => (
                <option key={a.id} value={a.id}>
                  {a.id.slice(0, 8)}… ({a.workflow_state})
                </option>
              ))}
            </select>
          </Field>
          {assessmentId && (
            <button type="button" onClick={generateReportCards} disabled={busy}>
              Generate report cards
            </button>
          )}
        </Panel>
      )}
      {notice && (
        <p role="status" className="hint">
          {notice}
        </p>
      )}
      {error && <ErrorBanner message={error} />}
      {assessmentId && docsQ.loading && <Loading label="Loading documents…" />}
      {assessmentId && docsQ.error && <ErrorBanner message={docsQ.error} />}
      {assessmentId && docsQ.data && docsQ.data.length === 0 && (
        <Empty label="No documents yet for this assessment." />
      )}
      {assessmentId && docsQ.data && docsQ.data.length > 0 && (
        <Panel title="Published documents">
          <DataTable headers={["Student", "Kind", "Version", "Correction", "Published", ""]}>
            {docsQ.data.map((d: DocumentItem) => (
              <tr key={d.id}>
                <td>{d.student_name ?? d.enrolment_id?.slice(0, 8)}</td>
                <td>{d.kind}</td>
                <td>v{d.doc_version}</td>
                <td>{d.correction_reason ?? "—"}</td>
                <td>{new Date(d.published_at).toLocaleDateString()}</td>
                <td>
                  <button type="button" disabled={busy} onClick={() => download(d.id)}>
                    Download
                  </button>
                  {canTranscript && d.enrolment_id && (
                    <button type="button" disabled={busy} onClick={() => requestTranscript(d.enrolment_id!)}>
                      Transcript
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </DataTable>
        </Panel>
      )}
    </section>
  );
}
