import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@markbook/api-client";

import { api } from "../api/client";
import type { Profile } from "../api/auth";
import { AuthContext, type AuthState } from "../auth/AuthContext";
import { ReportsPage } from "../pages/ReportsPage";

type Assessment = components["schemas"]["AssessmentResponse"];
type DocumentItem = components["schemas"]["DocumentListItem"];

vi.mock("../api/client", () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
  tokens: { access: null, refresh: null, clear: vi.fn() },
  API_BASE_URL: "http://test",
}));

const mockedGet = vi.mocked(api.GET);
const mockedPost = vi.mocked(api.POST);

const A1 = "00000000-0000-7000-8000-0000000000b1";
const DOC = "00000000-0000-7000-8000-0000000000e1";
const ENROLMENT = "00000000-0000-7000-8000-0000000000a1";

const assessment = { id: A1, workflow_state: "published" } as Assessment;
const docItem = {
  id: DOC,
  kind: "report_card",
  doc_version: 1,
  enrolment_id: ENROLMENT,
  student_name: "Ada Test",
  supersedes_id: null,
  correction_reason: null,
  published_at: "2026-11-22T00:00:00Z",
} as DocumentItem;

/** GETs: assessments list first, document list second, download third. */
function mockGets(docs: DocumentItem[] = [docItem]) {
  mockedGet.mockImplementation((path: never) => {
    const p = path as string;
    if (p === "/api/v1/assessments")
      return Promise.resolve({ data: [assessment], error: undefined, response: new Response() } as never);
    if (p === "/api/v1/documents/assessment/{assessment_id}")
      return Promise.resolve({ data: docs, error: undefined, response: new Response() } as never);
    if (p === "/api/v1/documents/{document_id}/download")
      return Promise.resolve({
        data: { document_id: DOC, url: "https://objects.test/signed", expires_in: 300 },
        error: undefined,
        response: new Response(),
      } as never);
    return Promise.reject(new Error(`unexpected GET ${p}`));
  });
}

function renderReports(perms: [string, string][]) {
  const auth: AuthState = {
    profile: {
      user_id: "00000000-0000-7000-8000-0000000000aa",
      school_id: "00000000-0000-7000-8000-0000000000aa",
      email: "r@x.local",
      username: "registrar",
      is_super_admin: false,
      roles: [],
      effective_permissions: perms.map(([code, scope_type]) => ({ code, scope_type })),
    } as Profile,
    booting: false,
    login: async () => {},
    logout: async () => {},
  };
  render(
    <AuthContext.Provider value={auth}>
      <ReportsPage />
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  window.open = vi.fn();
});

describe("ReportsPage", () => {
  it("shows the no-permission note without reports.view", async () => {
    renderReports([]);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view reports.",
    );
    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("lists a published assessment's documents and downloads via presigned URL", async () => {
    mockGets();
    const user = userEvent.setup();
    renderReports([["reports.view", "school"]]);

    const picker = await screen.findByLabelText("Assessment");
    await user.selectOptions(picker, A1);

    expect(await screen.findByRole("cell", { name: "Ada Test" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "v1" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith("https://objects.test/signed", "_blank", "noopener"));
    // no transcript button without transcripts.generate
    expect(screen.queryByRole("button", { name: "Transcript" })).toBeNull();
  });

  it("offers the transcript request only with transcripts.generate", async () => {
    mockGets();
    const user = userEvent.setup();
    mockedPost.mockResolvedValue({
      data: { job_id: DOC, status_url: "/api/v1/jobs/x" },
      error: undefined,
      response: new Response(),
    } as never);
    renderReports([["reports.view", "school"], ["transcripts.generate", "school"]]);

    await user.selectOptions(await screen.findByLabelText("Assessment"), A1);
    const transcript = await screen.findByRole("button", { name: "Transcript" });
    await user.click(transcript);
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith("/api/v1/documents/transcripts", {
        body: { enrolment_id: ENROLMENT },
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Transcript queued");
  });

  it("queues report-card generation for the picked assessment", async () => {
    mockGets();
    const user = userEvent.setup();
    mockedPost.mockResolvedValue({
      data: { job_id: DOC, status_url: "/api/v1/jobs/x" },
      error: undefined,
      response: new Response(),
    } as never);
    renderReports([["reports.view", "school"]]);

    await user.selectOptions(await screen.findByLabelText("Assessment"), A1);
    await user.click(screen.getByRole("button", { name: "Generate report cards" }));
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith("/api/v1/documents/report-cards", {
        body: { assessment_id: A1 },
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Report-card generation queued");
  });
});
