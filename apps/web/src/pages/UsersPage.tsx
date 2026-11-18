/**
 * User administration: the school's users, a create form, and an
 * active/suspended status flip. There is no roles-list endpoint yet, so
 * there is deliberately no role picker — role assignment lands when the
 * API exposes one; new users start with no roles.
 *
 * Visibility: the page needs `users.view`; the create form additionally
 * needs `users.create` and the status control `users.edit` (UI filters
 * only — the API re-checks everything). The status control is hidden for
 * super-admin rows (last-super-admin protection is enforced server-side;
 * a rejected PATCH surfaces in the error banner).
 */
import type { components } from "@markbook/api-client";
import { useState, type FormEvent, type ReactNode } from "react";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { hasPermission, useAuth } from "../auth/AuthContext";
import { DataTable, Empty, ErrorBanner, Field, Loading, Panel } from "../components/ui";
import { unwrap, useApiQuery } from "../hooks/useApiQuery";

type UserListItem = components["schemas"]["UserListItem"];

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

function UsersPanel({ canCreate, canEdit }: { canCreate: boolean; canEdit: boolean }) {
  const q = useApiQuery(() => unwrap(api.GET("/api/v1/auth/users", {})), []);
  const [statusError, setStatusError] = useState<string | null>(null);

  const setStatus = async (user: UserListItem, status: "active" | "suspended"): Promise<void> => {
    setStatusError(null);
    try {
      await unwrap(
        api.PATCH("/api/v1/auth/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body: { status },
        }),
      );
      q.reload();
    } catch (err) {
      setStatusError(problemMessage(err));
    }
  };

  return (
    <Panel title="Users">
      <CreateForm
        can={canCreate}
        submitLabel="Create user"
        onSubmit={async (f) => {
          await unwrap(
            api.POST("/api/v1/auth/users", {
              body: {
                email: String(f.get("email") || ""),
                username: String(f.get("username") || ""),
                password: String(f.get("password") || ""),
                // No roles-list endpoint yet, so no role picker: new users
                // start role-less; assignment lands when GET /roles exists.
                role_ids: [],
                is_super_admin: f.get("is_super_admin") === "on",
              },
            }),
          );
          q.reload();
        }}
      >
        <Field label="Email">
          <input name="email" type="email" required placeholder="teacher@school.example" />
        </Field>
        <Field label="Username">
          <input name="username" required placeholder="jdoe" />
        </Field>
        <Field label="Password">
          <input name="password" type="password" required />
        </Field>
        <Field label="Super admin">
          <input name="is_super_admin" type="checkbox" />
        </Field>
      </CreateForm>
      {q.loading && <Loading />}
      {q.error && <ErrorBanner message={q.error} />}
      {statusError && <ErrorBanner message={statusError} />}
      {q.data && q.data.length === 0 && <Empty label="No users yet." />}
      {q.data && q.data.length > 0 && (
        <DataTable headers={["Username", "Email", "Status", "MFA", "Super admin", ""]}>
          {q.data.map((u: UserListItem) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>{u.email}</td>
              <td>{u.status}</td>
              <td>{u.mfa_enabled ? "✓" : "—"}</td>
              <td>{u.is_super_admin ? "✓" : ""}</td>
              <td>
                {u.is_super_admin || !canEdit ? null : (
                  <button
                    type="button"
                    onClick={() => setStatus(u, u.status === "suspended" ? "active" : "suspended")}
                  >
                    {u.status === "suspended" ? "Reactivate" : "Suspend"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </Panel>
  );
}

export function UsersPage() {
  const { profile } = useAuth();
  const canCreate = hasPermission(profile, "users.create");
  const canEdit = hasPermission(profile, "users.edit");
  if (!hasPermission(profile, "users.view")) {
    return (
      <section>
        <h2>Users</h2>
        <Empty label="You do not have permission to view users." />
      </section>
    );
  }
  return (
    <section>
      <h2>Users</h2>
      <p className="page-note">
        Sign-in accounts for your school. Role assignment lands when the API exposes a roles list —
        new users start with no roles.
      </p>
      <UsersPanel canCreate={canCreate} canEdit={canEdit} />
    </section>
  );
}
