import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthState } from "../auth/AuthContext";
import { LoginPage } from "../pages/LoginPage";

function renderLoginWith(overrides: Partial<AuthState> = {}) {
  const auth: AuthState = {
    profile: null,
    booting: false,
    login: vi.fn().mockRejectedValue(new Error("Invalid credentials")),
    logout: async () => {},
    ...overrides,
  };
  render(
    <MemoryRouter>
      <AuthContext.Provider value={auth}>
        <LoginPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
  return auth;
}

describe("LoginPage", () => {
  it("submits email and password", async () => {
    const user = userEvent.setup();
    const login = vi.fn().mockResolvedValue(undefined);
    renderLoginWith({ login });
    await user.type(screen.getByLabelText("Email"), "t@x.local");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("t@x.local", "secret"));
  });

  it("shows the API's problem detail on a failed login", async () => {
    const user = userEvent.setup();
    renderLoginWith(); // login rejects with "Invalid credentials"
    await user.type(screen.getByLabelText("Email"), "t@x.local");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
  });
});
