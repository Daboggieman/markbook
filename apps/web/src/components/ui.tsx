/**
 * The four UI atoms every admin screen composes: Panel, Field, ErrorBanner,
 * DataTable. Styling lives in index.css; no component library by design —
 * this app is form/table CRUD over a typed client, and the dependency budget
 * stays near zero.
 */
import type { ReactNode } from "react";

export function Panel({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>{title}</h3>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <p role="alert" className="error-banner">
      {message}
    </p>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p role="status" className="loading">
      {label}
    </p>
  );
}

/** Plain table with fixed column alignment; rows come from the caller. */
export function DataTable({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          {headers.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

/** Renders nothing when there are none — used under every list. */
export function Empty({ label = "Nothing yet." }: { label?: string }) {
  return <p className="empty">{label}</p>;
}
