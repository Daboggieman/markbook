/**
 * Playwright E2E — the Phase 6 exit criterion (spec §16):
 *   teacher enters and submits → reviewer returns → admin approves, locks,
 *   publishes → correction after publish.
 *
 * The suite assumes a REAL stack running (compose dev DB + API on :8001 +
 * the Vite dev server on :5173) — unlike the component tests, these prove
 * the full HTTP path against the built app. `npm run e2e` drives it.
 */
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:5173",
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
