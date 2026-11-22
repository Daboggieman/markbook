import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@markbook/api-client";

import { api } from "../api/client";
import type { Profile } from "../api/auth";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import { WorkflowBar } from "../components/WorkflowBar";

type Sheet = components["schemas"]["ScoreSheetResponse"];

vi.mock("../api/client", () => ({
  api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn() },
  tokens: { access: null, refresh: null, clear: vi.fn() },
  API_BASE_URL: "http://test",
}));

const mockedPost = vi.mocked(api.POST);

const ASSESSMENT = "00000000-0000-7000-8000-0000000000b1";

function sheetWith(state: string): Sheet {
  return {
    assessment_id: ASSESSMENT,
    workflow_state: state,
    components: [],
    rows: [],
  } as Sheet;
}

function profileWith(perms: [string, string][]): Profile {
  return {
    user_id: "00000000-0000-7000-8000-0000000000aa",
    school_id: "00000000-0000-7000-8000-0000000000aa",
    email: "t@x.local",
    username: "actor",
    is_super_admin: false,
    roles: [],
    effective_permissions: perms.map(([code, scope_type]) => ({ code, scope_type })),
  } as Profile;
}

function renderBar(state: string, perms: [string, string][]) {
  const auth: AuthState = {
    profile: profileWith(perms),
    booting: false,
    login: async () => {},
    logout: async () => {},
  };
  const onChanged = vi.fn();
  render(
    <AuthContext.Provider value={auth}>
      <WorkflowBar sheet={sheetWith(state)} onChanged={onChanged} />
    </AuthContext.Provider>,
  );
  return { onChanged };
}

const okPost = () =>
  mockedPost.mockResolvedValue({
    data: { assessment_id: ASSESSMENT, workflow_state: "x", record_id: ASSESSMENT, from_state: "x", to_state: "x", actor_id: ASSESSMENT, at: "2026-11-22T00:00:00Z" },
    error: undefined,
    response: new Response(),
  } as never);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("WorkflowBar (§10 as UI)", () => {
  it("offers Submit only, to a school-scope scores.submit holder, in draft", () => {
    okPost();
    renderBar("draft", [["scores.submit", "school"]]);
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("an assigned-scope scores.submit holder also sees Submit (server re-checks)", () => {
    renderBar("returned", [["scores.submit", "assigned"]]);
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeTruthy();
  });

  it("results.* buttons need school scope — assigned holders see nothing", () => {
    renderBar("approved", [["results.lock", "assigned"]]);
    expect(screen.queryByRole("button", { name: "Lock results" })).toBeNull();
  });

  it("under_review shows Return (reason required) and Approve per grants", async () => {
    okPost();
    const user = userEvent.setup();
    renderBar("under_review", [["scores.review", "school"], ["results.approve", "school"]]);
    await user.click(screen.getByRole("button", { name: "Return to teacher" }));
    // reason is required — confirm without one is blocked client-side
    await user.click(screen.getByRole("button", { name: "Confirm Return to teacher" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A reason is required.");
    expect(mockedPost).not.toHaveBeenCalled();
    // with a reason it fires and the parent reloads
    await user.type(screen.getByLabelText("Return to teacher reason"), "CA1 needs a recheck");
    await user.click(screen.getByRole("button", { name: "Confirm Return to teacher" }));
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith("/api/v1/assessments/{assessment_id}/return", {
        params: { path: { assessment_id: ASSESSMENT } },
        body: { reason: "CA1 needs a recheck" },
      }),
    );
  });

  it("an actor without results.approve sees no Approve button", () => {
    renderBar("under_review", [["scores.review", "school"]]);
    expect(screen.getByRole("button", { name: "Return to teacher" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("Lock opens the step-up dialog: wrong-password error, then success fires the transition", async () => {
    okPost();
    const user = userEvent.setup();
    // reauth call first returns INVALID_CREDENTIALS, then success
    mockedPost
      .mockResolvedValueOnce({
        data: undefined,
        error: {
          type: "about:blank",
          title: "Unauthorized",
          status: 401,
          code: "INVALID_CREDENTIALS",
          detail: "Password did not match",
        },
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: { access_token: "reauthed-token", expires_in: 900, token_type: "bearer" },
        error: undefined,
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: { assessment_id: ASSESSMENT, workflow_state: "locked", record_id: ASSESSMENT, from_state: "approved", to_state: "locked", actor_id: ASSESSMENT, at: "2026-11-22T00:00:00Z" },
        error: undefined,
        response: new Response(),
      } as never);

    renderBar("approved", [["results.lock", "school"]]);
    await user.click(screen.getByRole("button", { name: "Lock results" }));
    expect(screen.getByLabelText("Confirm password")).toBeTruthy();
    expect(screen.queryByLabelText("Authenticator code")).toBeNull(); // hidden until MFA_REQUIRED

    await user.type(screen.getByLabelText("Confirm password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Password did not match");

    await user.clear(screen.getByLabelText("Confirm password"));
    await user.type(screen.getByLabelText("Confirm password"), "right");
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(mockedPost).toHaveBeenLastCalledWith("/api/v1/assessments/{assessment_id}/lock", {
        params: { path: { assessment_id: ASSESSMENT } },
        body: {},
      }),
    );
  });

  it("publish with MFA_REQUIRED reveals the TOTP field and retries with the code", async () => {
    okPost();
    const user = userEvent.setup();
    mockedPost
      .mockResolvedValueOnce({
        data: undefined,
        error: {
          type: "about:blank",
          title: "Unauthorized",
          status: 401,
          code: "MFA_REQUIRED",
          detail: "MFA code required",
        },
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: { access_token: "reauthed-mfa", expires_in: 900, token_type: "bearer" },
        error: undefined,
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: { assessment_id: ASSESSMENT, workflow_state: "published", record_id: ASSESSMENT, from_state: "locked", to_state: "published", actor_id: ASSESSMENT, at: "2026-11-22T00:00:00Z" },
        error: undefined,
        response: new Response(),
      } as never);

    renderBar("locked", [["results.publish", "school"]]);
    await user.click(screen.getByRole("button", { name: "Publish" }));
    await user.type(screen.getByLabelText("Confirm password"), "pw");
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    // the API's MFA_REQUIRED reveals the field; retry carries the code
    await waitFor(() => expect(screen.getByLabelText("Authenticator code")).toBeTruthy());
    await user.type(screen.getByLabelText("Authenticator code"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(mockedPost).toHaveBeenLastCalledWith("/api/v1/assessments/{assessment_id}/publish", {
        params: { path: { assessment_id: ASSESSMENT } },
        body: {},
      }),
    );
    // the reauth response body carried totp semantics: first call had no code, second did
    const reauthCalls = mockedPost.mock.calls.filter((c) => c[0] === "/api/v1/auth/reauth");
    expect(reauthCalls).toHaveLength(2);
  });

  it("renders nothing in a state with no available transitions for this actor", () => {
    renderBar("published", [["scores.enter", "school"]]); // no results.correct
    expect(screen.queryByRole("region", { name: "Workflow actions" })).toBeNull();
  });
});
