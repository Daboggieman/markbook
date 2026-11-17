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

const ACCESS_KEY = "markbook.access";
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

/** Session tokens. Access is mirrored here for the in-memory-only rule. */
export const tokens = {
  get access(): string | null {
    return store.get(ACCESS_KEY);
  },
  set access(v: string | null) {
    store.set(ACCESS_KEY, v);
  },
  get refresh(): string | null {
    return store.get(REFRESH_KEY);
  },
  set refresh(v: string | null) {
    store.set(REFRESH_KEY, v);
  },
  clear(): void {
    store.set(ACCESS_KEY, null);
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
  const headers = new Headers(init?.headers);
  const access = tokens.access;
  if (access && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${access}`);
  }
  let res = await fetch(input, { ...init, headers });
  if (res.status === 401 && tokens.access) {
    refreshing ??= refreshAccessToken().finally(() => {
      refreshing = null;
    });
    refreshInFlight = refreshing !== null;
    const fresh = await refreshing;
    refreshInFlight = false;
    if (fresh) {
      headers.set("Authorization", `Bearer ${fresh}`);
      res = await fetch(input, { ...init, headers });
    }
  }
  return res;
};

export const api = createClient<paths>({ baseUrl: API_BASE_URL, fetch: authedFetch });
