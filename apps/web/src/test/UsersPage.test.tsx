import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@markbook/api-client";

import { api } from "../api/client";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import { UsersPage } from "../pages/UsersPage";

type UserListItem = components["schemas"]["UserListItem"];
type Profile = components["schemas"]["UserProfileResponse"];

vi.mock("../api/client", () => ({
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() },
}));

const mockedGet = vi.mocked(api.GET);
const mockedPost = vi.mocked(api.POST);
const mockedPatch = vi.mocked(api.PATCH);

function userRow(overrides: Partial<UserListItem> = {}): UserListItem {
  return {
    id: "00000000-0000-7000-8000-000000000001",
    email: "jdoe@x.local",
    username: "jdoe",
    is_super_admin: false,
    status: "active",
    mfa_enabled: false,
    created_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

function profileWith(perms: [string, string][]): Profile {
  return {
    user_id: "00000000-0000-7000-8000-0000000000aa",
    school_id: "00000000-0000-7000-8000-0000000000aa",
    email: "t@x.local",
    username: "admin",
    is_super_admin: false,
    roles: [],
    effective_permissions: perms.map(([code, scope_type]) => ({ code, scope_type })),
  } as Profile;
}

const baseAuth = (profile: Profile | null): AuthState => ({
  profile,
  booting: false,
  login: async () => {},
  logout: async () => {},
});

function renderUsersPage(perms: [string, string][]) {
  return render(
    <AuthContext.Provider value={baseAuth(profileWith(perms))}>
      <UsersPage />
    </AuthContext.Provider>,
  );
}

/** The list GET resolves with these rows; each test re-points it. */
function getUsersReturns(rows: UserListItem[]) {
  mockedGet.mockResolvedValue({ data: rows, error: undefined, response: new Response() });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("UsersPage", () => {
  it("renders the user list rows with status, MFA and super-admin badges", async () => {
    getUsersReturns([
      userRow(),
      userRow({
        id: "00000000-0000-7000-8000-000000000002",
        email: "sa@x.local",
        username: "root",
        is_super_admin: true,
        mfa_enabled: true,
      }),
    ]);
    renderUsersPage([["users.view", "school"], ["users.create", "school"], ["users.edit", "school"]]);

    expect(await screen.findByRole("cell", { name: "jdoe" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "root" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "jdoe@x.local" })).toBeTruthy();
    // badges are row-scoped: jdoe (no MFA, not super admin) shows "—"/blank,
    // root shows the ✓ badge in both columns
    const jdoeRow = screen.getByRole("cell", { name: "jdoe" }).closest("tr");
    const rootRow = screen.getByRole("cell", { name: "root" }).closest("tr");
    expect(jdoeRow?.textContent).toContain("—");
    expect(jdoeRow?.textContent).not.toContain("✓");
    expect(rootRow?.textContent).toContain("✓");
  });

  it("shows the problem detail in an error banner when the list fails", async () => {
    mockedGet.mockResolvedValue({
      data: undefined,
      error: {
        type: "about:blank",
        title: "Forbidden",
        status: 403,
        code: "PERMISSION_DENIED",
        detail: "You do not hold users.view.",
      },
      response: new Response(),
    });
    renderUsersPage([["users.view", "school"]]);

    expect(await screen.findByRole("alert")).toHaveTextContent("You do not hold users.view.");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("creates a user and reloads the list", async () => {
    const user = userEvent.setup();
    getUsersReturns([userRow()]);
    mockedPost.mockResolvedValue({
      data: {
        id: "00000000-0000-7000-8000-000000000003",
        school_id: "00000000-0000-7000-8000-0000000000aa",
        email: "new@x.local",
        username: "newbie",
        is_super_admin: false,
        status: "active",
        mfa_enabled: false,
        failed_login_count: 0,
        locked_until: null,
        created_at: "2026-11-18T00:00:00Z",
        updated_at: "2026-11-18T00:00:00Z",
        version: 1,
      },
      error: undefined,
      response: new Response(),
    });
    renderUsersPage([["users.view", "school"], ["users.create", "school"]]);

    await screen.findByRole("cell", { name: "jdoe" });
    const getCallsBefore = mockedGet.mock.calls.length;

    await user.type(screen.getByLabelText("Email"), "new@x.local");
    await user.type(screen.getByLabelText("Username"), "newbie");
    await user.type(screen.getByLabelText("Password"), "s3cret!");
    await user.click(screen.getByRole("button", { name: "Create user" }));

    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith("/api/v1/auth/users", {
        body: {
          email: "new@x.local",
          username: "newbie",
          password: "s3cret!",
          role_ids: [],
          is_super_admin: false,
        },
      }),
    );
    // the list reloaded after the create
    await waitFor(() => expect(mockedGet.mock.calls.length).toBe(getCallsBefore + 1));
  });

  it("suspends an active user via PATCH and hides the control on super-admin rows", async () => {
    const user = userEvent.setup();
    getUsersReturns([
      userRow(),
      userRow({
        id: "00000000-0000-7000-8000-000000000002",
        email: "sa@x.local",
        username: "root",
        is_super_admin: true,
      }),
    ]);
    mockedPatch.mockResolvedValue({
      data: {
        ...userRow({ status: "suspended" }),
        school_id: "00000000-0000-7000-8000-0000000000aa",
        failed_login_count: 0,
        locked_until: null,
        updated_at: "2026-11-18T00:00:00Z",
        version: 2,
      },
      error: undefined,
      response: new Response(),
    });
    renderUsersPage([["users.view", "school"], ["users.edit", "school"]]);

    await screen.findByRole("cell", { name: "root" });
    // the super-admin row carries no status control (last-SA protection)
    const rootRow = screen.getByRole("cell", { name: "root" }).closest("tr");
    expect(rootRow?.querySelector("button")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Suspend" }));
    await waitFor(() =>
      expect(mockedPatch).toHaveBeenCalledWith("/api/v1/auth/users/{user_id}", {
        params: { path: { user_id: "00000000-0000-7000-8000-000000000001" } },
        body: { status: "suspended" },
      }),
    );
  });

  it("hides the create form and status controls without the manage permissions", async () => {
    getUsersReturns([
      userRow(),
      userRow({
        id: "00000000-0000-7000-8000-000000000002",
        username: "root",
        is_super_admin: true,
      }),
    ]);
    renderUsersPage([["users.view", "school"]]);

    expect(await screen.findByRole("cell", { name: "jdoe" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create user" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Suspend" })).toBeNull();
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  it("renders the no-permission note without users.view", async () => {
    renderUsersPage([]);
    expect(await screen.findByText("You do not have permission to view users.")).toBeTruthy();
    expect(mockedGet).not.toHaveBeenCalled();
  });
});
