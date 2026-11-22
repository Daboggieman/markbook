/**
 * The score sheet — the keyboard-first grid teachers live in (spec §6.4,
 * Phase 6's flagship screen).
 *
 * Keyboard model (gradebook conventions):
 *   - typing digits  → status "entered" with that value
 *   - typing m/a/e   → missing / absent / exempt (value stays empty)
 *   - Enter or ↓     → same column, next student; ↑ → previous student;
 *     Tab moves right natively — column-per-component walk, no mouse.
 *
 * Concurrency: every cell carries `base_version` from the sheet as loaded;
 * the PUT is one atomic batch. A 409 VERSION_CONFLICT opens the conflict
 * dialog — the sheet is reloaded rather than force-overwritten (Phase 3
 * contract; the API is the referee, the UI never guesses).
 *
 * Client-side validation (over-max highlight) is a HINT only — the API
 * re-validates authoritatively (rules-package rule: UI never gates).
 */
import type { components } from "@markbook/api-client";
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useParams } from "react-router";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { hasPermission, useAuth } from "../auth/AuthContext";
import { ErrorBanner, Loading, Panel } from "../components/ui";
import { WorkflowBar } from "../components/WorkflowBar";
import { unwrap, useApiQuery } from "../hooks/useApiQuery";

type Sheet = components["schemas"]["ScoreSheetResponse"];
type Row = components["schemas"]["SheetRow"];
type Cell = components["schemas"]["ScoreCell"];
type Component = components["schemas"]["ComponentDef-Output"];
type ScoreStatus = components["schemas"]["ScoreRowInput"]["status"];

const EDITABLE_STATES = new Set(["draft", "returned"]);
const LETTER_STATUS: Record<string, ScoreStatus> = {
  m: "missing",
  a: "absent",
  e: "exempt",
};
const STATUS_LETTER: Record<string, string> = {
  missing: "m",
  absent: "a",
  exempt: "e",
};

interface CellEdit {
  status: ScoreStatus;
  /** The input's raw text: digits while entered, the letter otherwise. */
  raw: string;
  baseVersion: number | null;
}

const cellKey = (seId: string, component: string): string => `${seId}|${component}`;

function fromCell(cell: Cell | undefined): CellEdit {
  if (!cell) return { status: "entered", raw: "", baseVersion: null };
  if (cell.status === "entered") {
    return { status: "entered", raw: cell.value === null ? "" : String(cell.value), baseVersion: cell.version };
  }
  return { status: cell.status, raw: STATUS_LETTER[cell.status] ?? "", baseVersion: cell.version };
}

function parsed(edit: CellEdit): { status: ScoreStatus; value: number | null } | null {
  if (edit.raw === "") return null; // nothing typed — not an edit
  if (LETTER_STATUS[edit.raw.toLowerCase()]) {
    return { status: LETTER_STATUS[edit.raw.toLowerCase()]!, value: null };
  }
  const n = Number(edit.raw);
  return { status: "entered", value: n };
}

export function ScoreSheetPage() {
  const { profile } = useAuth();
  const canEnter = hasPermission(profile, "scores.enter");
  const { assessmentId = "" } = useParams();
  const sheetQ = useApiQuery(
    () => unwrap(api.GET("/api/v1/assessments/{assessment_id}/sheet", { params: { path: { assessment_id: assessmentId } } })),
    [assessmentId],
  );

  const sheet: Sheet | null = sheetQ.data;
  const [edits, setEdits] = useState<Record<string, CellEdit>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const cellRefs = useRef(new Map<string, HTMLInputElement>());

  // The edit buffer seeds from each load; after a save the sheet reloads
  // and the buffer re-seeds with the fresh versions.
  const seedKey = `${sheet?.assessment_id ?? ""}:${sheet?.rows.map((r) => r.subject_enrolment_id).join(",") ?? ""}`;
  const [seededFor, setSeededFor] = useState("");
  if (sheet && seededFor !== seedKey) {
    const seeded: Record<string, CellEdit> = {};
    for (const row of sheet.rows) {
      for (const c of sheet.components) {
        seeded[cellKey(row.subject_enrolment_id, c.key)] = fromCell(row.scores[c.key]);
      }
    }
    setEdits(seeded);
    setSeededFor(seedKey);
  }

  const editable = sheet !== null && EDITABLE_STATES.has(sheet.workflow_state) && canEnter;

  const changedRows = useMemo(() => {
    if (!sheet) return [];
    const rows: components["schemas"]["ScoreRowInput"][] = [];
    for (const [key, edit] of Object.entries(edits)) {
      const [seId, component] = key.split("|");
      const original = fromCell(
        sheet.rows.find((r) => r.subject_enrolment_id === seId)?.scores[component ?? ""],
      );
      if (original.raw === edit.raw && original.status === edit.status) continue;
      const p = parsed(edit);
      if (!p) continue;
      rows.push({
        subject_enrolment_id: seId ?? "",
        component_key: component ?? "",
        status: p.status,
        value: p.value,
        base_version: edit.baseVersion,
      });
    }
    return rows;
  }, [edits, sheet]);

  const overMax = useMemo(() => {
    if (!sheet) return false;
    const maxes = new Map(sheet.components.map((c: Component) => [c.key, Number(c.max_score)]));
    return Object.entries(edits).some(([key, edit]) => {
      const [, component] = key.split("|");
      const p = parsed(edit);
      return p !== null && p.value !== null && p.value > (maxes.get(component ?? "") ?? Infinity);
    });
  }, [edits, sheet]);

  function focusCell(r: number, c: number) {
    cellRefs.current.get(`${r}:${c}`)?.focus();
  }

  function onKeyDown(r: number, c: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "Enter") {
      e.preventDefault();
      focusCell(r + 1, c);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusCell(r - 1, c);
    }
  }

  async function save() {
    if (!sheet || changedRows.length === 0) return;
    setSaving(true);
    setSaveError(null);
    setConflict(false);
    try {
      await unwrap(
        api.PUT("/api/v1/assessments/{assessment_id}/scores", {
          params: { path: { assessment_id: sheet.assessment_id } },
          body: { rows: changedRows },
        }),
      );
      sheetQ.reload(); // fresh versions re-seed the buffer
    } catch (err) {
      const problem = err as { code?: string };
      if (problem?.code === "VERSION_CONFLICT") setConflict(true);
      else setSaveError(problemMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (!hasPermission(profile, "assessments.view") && !canEnter) {
    return (
      <section>
        <h2>Score sheet</h2>
        <ErrorBanner message="You do not have permission to view score sheets." />
      </section>
    );
  }
  if (sheetQ.loading) return <Loading label="Loading sheet…" />;
  if (sheetQ.error) return <ErrorBanner message={sheetQ.error} />;
  if (!sheet) return null;

  return (
    <section>
      <h2>
        Score sheet{" "}
        <span className={`state-badge state-${sheet.workflow_state}`}>{sheet.workflow_state}</span>
      </h2>
      <p className="hint">
        Type scores; m = missing, a = absent, e = exempt. Enter/↓ next student, ↑ back, Tab next
        column.
      </p>
      {conflict && (
        <div role="alertdialog" aria-label="Sheet changed" className="conflict-dialog">
          <p>This sheet changed after you loaded it — someone else saved first.</p>
          <button
            type="button"
            onClick={() => {
              setConflict(false);
              sheetQ.reload();
            }}
          >
            Reload sheet
          </button>
        </div>
      )}
      <Panel title={`${sheet.rows.length} students`}>
        <table className="data-table score-grid">
          <thead>
            <tr>
              <th>Student</th>
              {sheet.components.map((c: Component) => (
                <th key={c.key}>
                  {c.label} <span className="max">/{Number(c.max_score)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row: Row, r: number) => (
              <tr key={row.subject_enrolment_id}>
                <td>{row.student_name}</td>
                {sheet.components.map((c: Component, ci: number) => {
                  const key = cellKey(row.subject_enrolment_id, c.key);
                  const edit = edits[key] ?? fromCell(row.scores[c.key]);
                  const status = parsed(edit)?.status ?? edit.status;
                  const p = parsed(edit);
                  const over =
                    p !== null &&
                    p.value !== null &&
                    p.value > Number(sheet.components[ci]?.max_score ?? Infinity);
                  return (
                    <td key={c.key}>
                      <input
                        ref={(el) => {
                          if (el) cellRefs.current.set(`${r}:${ci}`, el);
                          else cellRefs.current.delete(`${r}:${ci}`);
                        }}
                        data-r={r}
                        data-c={ci}
                        className={[
                          "cell",
                          `cell-${status}`,
                          over ? "cell-over" : "",
                          edit.raw !== "" && edit.raw !== (row.scores[c.key]?.value ?? "") ? "cell-dirty" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        value={edit.raw}
                        disabled={!editable}
                        inputMode="decimal"
                        aria-label={`${row.student_name} ${c.label}`}
                        onChange={(e) => {
                          const raw = e.target.value.trim();
                          setEdits((prev) => ({ ...prev, [key]: { ...edit, raw } }));
                        }}
                        onKeyDown={(e) => onKeyDown(r, ci, e)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {editable && (
          <div className="inline-form">
            <button type="button" onClick={save} disabled={saving || overMax || changedRows.length === 0}>
              {saving ? "Saving…" : `Save ${changedRows.length} change${changedRows.length === 1 ? "" : "s"}`}
            </button>
            {overMax && <ErrorBanner message="A value exceeds its component maximum — fix the highlighted cells." />}
            {saveError && <ErrorBanner message={saveError} />}
          </div>
        )}
        {!editable && sheet.workflow_state !== "draft" && sheet.workflow_state !== "returned" && (
          <p className="hint">Scores are frozen in the {sheet.workflow_state} state.</p>
        )}
      </Panel>
      <WorkflowBar sheet={sheet} onChanged={sheetQ.reload} />
    </section>
  );
}
