/**
 * User administration: the school's users, a create form, an active/suspended
 * status flip, and per-user role management (grant/revoke) on top of the
 * Phase 6 roles endpoints. New users start role-less — grant roles from the
 * row's "Roles" action; a user with no roles sees only the dashboard, which
 * is the permission model doing its job (UI hides, backend enforces).
 *
 * Visibility: the page needs `users.view`; the create form additionally
 * needs `users.create`, the status control and role grants `users.edit`, and
 * the role picker only renders with `roles.view` (it lists the school's
 * roles). UI filters only — the API re-checks everything. The status control
 * is hidden for super-admin rows (last-super-admin protection is enforced
 * server-side; a rejected PATCH surfaces in the error banner).
 */
import type { components } from "@markbook/api-client";
import { useState, type FormEvent, type ReactNode } from "react";

import { api } from "../api/client";
import { problemMessage } from "../api/problem";
import { hasPermission, useAuth } from "../auth/AuthContext";
import { DataTable, Empty, ErrorBanner, Field, Loading, Panel } from "../components/ui";
import { unwrap, useApiQuery } from "../hooks/useApiQuery";

type UserListItem = components["schemas"]["UserListItem"];
type Role = components["schemas"]["RoleResponse"];

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
        // Capture the element now: React nulls e.currentTarget once this
        // handler yields at the await, so reset() must use the local ref.
        const form = e.currentTarget;
        try {
          await onSubmit(new FormData(form));
          form.reset();
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

/** Grant/revoke roles for one user (users.edit gates both directions). */
function UserRolesManager({
  userId,
  schoolRoles,
  canEdit,
}: {
  userId: string;
  schoolRoles: Role[];
  canEdit: boolean;
}) {
  const q = useApiQuery(
    () => unwrap(api.GET("/api/v1/users/{user_id}/roles", { params: { path: { user_id: userId } } })),
    [userId],
  );
  const [roleId, setRoleId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      q.reload();
    } catch (err) {
      setError(problemMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const held = q.data ?? [];
  const available = schoolRoles.filter((r) => !held.some((h) => h.id === r.id));
  return (
    <div className="detail-box">
      {q.loading && <Loading />}
      {q.error && <ErrorBanner message={q.error} />}
      {error && <ErrorBanner message={error} />}
      {held.length === 0 && !q.loading && <Empty label="No roles granted." />}
      {held.length > 0 && (
        <DataTable headers={["Role", "Super admin", ""]}>
          {held.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td>{r.is_super_admin ? "✓" : ""}</td>
              <td>
                {canEdit && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api.DELETE("/api/v1/users/{user_id}/roles/{role_id}", {
                          params: { path: { user_id: userId, role_id: r.id } },
                        }),
                      )
                    }
                  >
                    Revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </DataTable>
      )}
      {canEdit && (
        <form
          className="inline-form"
          onSubmit={(e: FormEvent<HTMLFormElement>) => {
            e.preventDefault();
            if (!roleId) return;
            void run(() =>
              api.POST("/api/v1/users/{user_id}/roles", {
                params: { path: { user_id: userId } },
                body: { role_id: roleId },
              }),
            );
            setRoleId("");
          }}
        >
          <Field label="Grant role">
            <select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
              <option value="">—</option>
              {available.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                  {r.is_super_admin ? " (super admin)" : ""}
                </option>
              ))}
            </select>
          </Field>
          <button type="submit" disabled={busy || !roleId}>
            Grant
          </button>
        </form>
      )}
    </div>
  );
}

function UsersPanel({
  canCreate,
  canEdit,
  canRolesView,
}: {
  canCreate: boolean;
  canEdit: boolean;
  canRolesView: boolean;
}) {
  const q = useApiQuery(() => unwrap(api.GET("/api/v1/auth/users", {})), []);
  const rolesQ = useApiQuery(
    () => (canRolesView ? unwrap(api.GET("/api/v1/roles", {})) : Promise.resolve([] as Role[])),
    [canRolesView],
  );
  const [open, setOpen] = useState<string | null>(null);
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
                // Users always start role-less; roles are granted per user
                // afterwards via POST /users/{id}/roles.
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
                {canRolesView && (
                  <button type="button" onClick={() => setOpen(open === u.id ? null : u.id)}>
                    Roles
                  </button>
                )}{" "}
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
      {open && canRolesView && (
        <UserRolesManager userId={open} schoolRoles={rolesQ.data ?? []} canEdit={canEdit} />
      )}
    </Panel>
  );
}

export function UsersPage() {
  const { profile } = useAuth();
  const canCreate = hasPermission(profile, "users.create");
  const canEdit = hasPermission(profile, "users.edit");
  const canRolesView = hasPermission(profile, "roles.view");
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
        Sign-in accounts for your school. New users start with no roles — use the row's
        &quot;Roles&quot; action to grant them (they see only the dashboard until a role grants
        permissions).
      </p>
      <UsersPanel canCreate={canCreate} canEdit={canEdit} canRolesView={canRolesView} />
    </section>
  );
}
