/**
 * The single HTTP seam for the whole app.
 *
 * - The access token lives in MEMORY only (never localStorage — an XSS
 *   there must not be able to read a long-lived credential; spec §13.1).
 * - The refresh token is persisted: the API hands it back in the login
 *   response body (identity contract, Phase 1), so the SPA has nowhere
 *   else to keep it. Revisit if the backend grows a refresh cookie.
 * - A 401 triggers ONE single-flight refresh, then replays the original
 *   request. Concurrent 401s share the same refresh promise, so N parallel
 *   failures never mint N refresh calls (rotation would revoke the family).
 */
import { createClient, type paths } from "@markbook/api-client";

export const API_BASE_URL: string =
  (import.meta.env?.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8001";

const REFRESH_KEY = "markbook.refresh";

const store = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null; // private window / storage disabled — auth still works in-memory
    }
  },
  set(key: string, value: string | null): void {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch {
      // as above — degrade, never crash
    }
  },
};

/** The access token lives in a module variable — genuinely in memory. */
let accessToken: string | null = null;

/** Session tokens. Access stays in memory; only the refresh token persists. */
export const tokens = {
  get access(): string | null {
    return accessToken;
  },
  set access(v: string | null) {
    accessToken = v;
  },
  get refresh(): string | null {
    return store.get(REFRESH_KEY);
  },
  set refresh(v: string | null) {
    store.set(REFRESH_KEY, v);
  },
  clear(): void {
    accessToken = null;
    store.set(REFRESH_KEY, null);
  },
};

/** True while a refresh round-trip is in flight — callers render a spinner. */
export let refreshInFlight = false;

let refreshing: Promise<string | null> | null = null;

/** Rotate the refresh token; returns the new access token or null. */
export async function refreshAccessToken(): Promise<string | null> {
  const rt = tokens.refresh;
  if (!rt) return null;
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  });
  if (!res.ok) {
    tokens.refresh = null; // reuse/rotation failure — the family is dead
    return null;
  }
  const body = (await res.json()) as { access_token: string };
  tokens.access = body.access_token;
  return body.access_token;
}

const authedFetch: typeof fetch = async (input, init) => {
  // openapi-fetch hands us a fully-formed Request (init may be empty), so the
  // headers must come from the REQUEST, not from init: building them from
  // init alone drops the Request's Content-Type, FastAPI can no longer parse
  // the body, and every POST dies as a 422 with an array detail ("[object
  // Object]" in the UI). With a string input, init still carries everything.
  const headers = new Headers(input instanceof Request ? input.headers : init?.headers);
  const access = tokens.access;
  if (access && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${access}`);
  }
  // A fresh Request per call so a 401-retry can re-send the body.
  const source = input instanceof Request ? input.clone() : input;
  const build = (): Request =>
    input instanceof Request
      ? new Request(source, { headers })
      : new Request(source, { ...(init ?? {}), headers });
  let res = await fetch(build());
  if (res.status === 401 && tokens.access) {
    refreshing ??= refreshAccessToken().finally(() => {
      refreshing = null;
    });
    refreshInFlight = refreshing !== null;
    const fresh = await refreshing;
    refreshInFlight = false;
    if (fresh) {
      headers.set("Authorization", `Bearer ${fresh}`);
      res = await fetch(build());
    }
  }
  return res;
};

export const api = createClient<paths>({ baseUrl: API_BASE_URL, fetch: authedFetch });
