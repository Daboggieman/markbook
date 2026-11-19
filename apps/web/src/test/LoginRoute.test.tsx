/**
 * The /login route guard: a signed-in actor is redirected to the dashboard
 * (this was the login-flow bug — POST + GET succeeded but nothing ever
 * navigated out of the form), a signed-out actor sees the form.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import type { components } from "@markbook/api-client";

import { AuthContext, type AuthState } from "../auth/AuthContext";
import { AppRoutes } from "../routes";

type Profile = components["schemas"]["UserProfileResponse"];

const profile: Profile = {
  user_id: "00000000-0000-7000-8000-0000000000aa",
  school_id: "00000000-0000-7000-8000-0000000000aa",
  email: "t@x.local",
  username: "teacher",
  is_super_admin: false,
  roles: [],
  effective_permissions: [],
} as Profile;

const authWith = (p: Profile | null): AuthState => ({
  profile: p,
  booting: false,
  login: async () => {},
  logout: async () => {},
});

function renderLoginWith(auth: AuthState) {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthContext.Provider value={auth}>
        <AppRoutes />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("login route guard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("redirects a signed-in actor from /login to the dashboard", () => {
    renderLoginWith(authWith(profile));
    expect(screen.queryByRole("heading", { name: "Markbook" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeTruthy();
    expect(screen.getByText("Signed in as", { exact: false })).toBeTruthy();
  });

  it("shows the login form when signed out", () => {
    renderLoginWith(authWith(null));
    expect(screen.getByRole("heading", { name: "Markbook" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Dashboard" })).toBeNull();
  });

  it("shows a status line while the session check is in flight", () => {
    renderLoginWith({ profile: null, booting: true, login: async () => {}, logout: async () => {} });
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Markbook" })).toBeNull();
  });
});
