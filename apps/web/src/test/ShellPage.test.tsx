import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import type { components } from "@markbook/api-client";

import { AuthContext, hasPermission, type AuthState } from "../auth/AuthContext";
import { ShellPage } from "../pages/ShellPage";

type Profile = components["schemas"]["UserProfileResponse"];

function profileWith(perms: [string, string][]): Profile {
  return {
    user_id: "00000000-0000-7000-8000-0000000000aa",
    school_id: "00000000-0000-7000-8000-0000000000aa",
    email: "t@x.local",
    username: "teacher",
    is_super_admin: false,
    roles: [],
    effective_permissions: perms.map(([code, scope_type]) => ({ code, scope_type })),
  } as Profile;
}

function renderShellWith(auth: AuthState) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthContext.Provider value={auth}>
        <ShellPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

const baseAuth = (profile: Profile | null): AuthState => ({
  profile,
  booting: false,
  login: async () => {},
  logout: async () => {},
});

describe("shell navigation (UI hides unauthorised actions)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows only the items the actor's effective permissions allow", () => {
    renderShellWith(
      baseAuth(profileWith([["assessments.view", "school"], ["scores.enter", "assigned"]])),
    );
    expect(screen.getByRole("link", { name: "Assessments" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Reports" })).toBeNull();
  });

  it("shows everything for an actor holding every nav permission", () => {
    renderShellWith(
      baseAuth(
        profileWith([
          ["assessments.view", "school"],
          ["users.view", "school"],
          ["reports.view", "school"],
        ]),
      ),
    );
    for (const name of ["Assessments", "Users", "Reports"]) {
      expect(screen.getByRole("link", { name })).toBeTruthy();
    }
  });
});

describe("hasPermission", () => {
  it("matches on code at any scope and denies when signed out", () => {
    const p = profileWith([["scores.enter", "assigned"]]);
    expect(hasPermission(p, "scores.enter")).toBe(true);
    expect(hasPermission(p, "users.view")).toBe(false);
    expect(hasPermission(null, "scores.enter")).toBe(false);
  });
});
