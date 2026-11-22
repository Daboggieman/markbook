import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import type { components } from "@markbook/api-client";

import { api } from "../api/client";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import { ScoreSheetPage } from "../pages/ScoreSheetPage";

type Sheet = components["schemas"]["ScoreSheetResponse"];
type Profile = components["schemas"]["UserProfileResponse"];

vi.mock("../api/client", () => ({
  api: { GET: vi.fn(), PUT: vi.fn(), POST: vi.fn() },
}));

const mockedGet = vi.mocked(api.GET);
const mockedPut = vi.mocked(api.PUT);

const SE_A = "00000000-0000-7000-8000-0000000000a1";
const SE_B = "00000000-0000-7000-8000-0000000000a2";

function sheet(overrides: Partial<Sheet> = {}): Sheet {
  return {
    assessment_id: "00000000-0000-7000-8000-0000000000b1",
    workflow_state: "draft",
    components: [
      { key: "CA1", label: "First CA", max_score: "10", weight: "10", required: true },
      { key: "Exam", label: "Exam", max_score: "60", weight: "60", required: true },
    ],
    rows: [
      {
        subject_enrolment_id: SE_A,
        student_id: "00000000-0000-7000-8000-0000000000c1",
        student_name: "Ada Obi",
        admission_no: null,
        scores: {},
      },
      {
        subject_enrolment_id: SE_B,
        student_id: "00000000-0000-7000-8000-0000000000c2",
        student_name: "Bayo Musa",
        admission_no: null,
        scores: {
          CA1: { id: "00000000-0000-7000-8000-0000000000d1", status: "entered", value: "8", version: 3 },
        },
      },
    ],
    ...overrides,
  } as Sheet;
}

function renderSheet(perms: [string, string][] = [["assessments.view", "school"], ["scores.enter", "school"]]) {
  const auth: AuthState = {
    profile: {
      user_id: "00000000-0000-7000-8000-0000000000aa",
      school_id: "00000000-0000-7000-8000-0000000000aa",
      email: "t@x.local",
      username: "teacher",
      is_super_admin: false,
      roles: [],
      effective_permissions: perms.map(([code, scope_type]) => ({ code, scope_type })),
    } as Profile,
    booting: false,
    login: async () => {},
    logout: async () => {},
  };
  return render(
    <MemoryRouter initialEntries={["/assessments/x/sheet"]}>
      <AuthContext.Provider value={auth}>
        <ScoreSheetPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

function getReturns(s: Sheet, error?: unknown) {
  mockedGet.mockResolvedValue({
    data: error ? undefined : s,
    error,
    response: new Response(),
  } as never);
}

const okPut = () =>
  mockedPut.mockResolvedValue({ data: { updated: 1 }, error: undefined, response: new Response() } as never);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("ScoreSheetPage", () => {
  it("renders the roster with per-component columns and existing values", async () => {
    getReturns(sheet());
    renderSheet();
    expect(await screen.findByRole("cell", { name: "Ada Obi" })).toBeTruthy();
    const adaCA1 = screen.getByLabelText("Ada Obi First CA") as HTMLInputElement;
    expect(adaCA1.value).toBe("");
    const bayoCA1 = screen.getByLabelText("Bayo Musa First CA") as HTMLInputElement;
    expect(bayoCA1.value).toBe("8");
  });

  it("Enter moves focus to the next student in the same column", async () => {
    getReturns(sheet());
    renderSheet();
    const first = (await screen.findByLabelText("Ada Obi First CA")) as HTMLInputElement;
    first.focus();
    await userEvent.keyboard("{Enter}");
    expect(document.activeElement).toBe(screen.getByLabelText("Bayo Musa First CA"));
  });

  it("sends the typed cell with the sheet's base_version and no-op cells skipped", async () => {
    getReturns(sheet());
    okPut();
    renderSheet();
    const adaExam = (await screen.findByLabelText("Ada Obi Exam")) as HTMLInputElement;
    await userEvent.type(adaExam, "48");
    await userEvent.click(screen.getByRole("button", { name: /Save 1 change/ }));
    await waitFor(() =>
      expect(mockedPut).toHaveBeenCalledWith("/api/v1/assessments/{assessment_id}/scores", {
        params: { path: { assessment_id: sheet().assessment_id } },
        body: {
          rows: [
            {
              subject_enrolment_id: SE_A,
              component_key: "Exam",
              status: "entered",
              value: 48,
              base_version: null,
            },
          ],
        },
      }),
    );
  });

  it("a letter sets the status with a null value (m → missing)", async () => {
    getReturns(sheet());
    okPut();
    renderSheet();
    const adaCA1 = (await screen.findByLabelText("Ada Obi First CA")) as HTMLInputElement;
    await userEvent.type(adaCA1, "m");
    await userEvent.click(screen.getByRole("button", { name: /Save 1 change/ }));
    await waitFor(() =>
      expect(mockedPut).toHaveBeenCalledWith(
        "/api/v1/assessments/{assessment_id}/scores",
        expect.objectContaining({
          body: {
            rows: [
              { subject_enrolment_id: SE_A, component_key: "CA1", status: "missing", value: null, base_version: null },
            ],
          },
        }),
      ),
    );
  });

  it("a VERSION_CONFLICT opens the conflict dialog instead of erroring away", async () => {
    getReturns(sheet());
    mockedPut.mockResolvedValue({
      data: undefined,
      error: {
        type: "about:blank",
        title: "Conflict",
        status: 409,
        code: "VERSION_CONFLICT",
        detail: "Cell was changed by someone else",
      },
      response: new Response(),
    } as never);
    renderSheet();
    const adaExam = (await screen.findByLabelText("Ada Obi Exam")) as HTMLInputElement;
    await userEvent.type(adaExam, "48");
    await userEvent.click(screen.getByRole("button", { name: /Save 1 change/ }));
    const dialog = await screen.findByRole("alertdialog", { name: "Sheet changed" });
    expect(dialog.textContent).toContain("changed after you loaded it");
  });

  it("frozen states disable every cell and hide save", async () => {
    getReturns(sheet({ workflow_state: "submitted" }));
    renderSheet();
    expect(await screen.findByLabelText("Ada Obi First CA")).toHaveProperty("disabled", true);
    expect(screen.queryByRole("button", { name: /Save/ })).toBeNull();
  });

  it("flags an over-max value and refuses to save it", async () => {
    getReturns(sheet());
    renderSheet();
    const adaExam = (await screen.findByLabelText("Ada Obi Exam")) as HTMLInputElement;
    await userEvent.type(adaExam, "70");
    expect(adaExam.className).toContain("cell-over");
    const save = screen.getByRole("button", { name: /Save/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(mockedPut).not.toHaveBeenCalled();
  });
});
