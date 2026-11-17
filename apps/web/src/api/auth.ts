/**
 * Typed auth calls against the generated client. The generated `paths` type
 * means a renamed or restructured endpoint fails here at compile time.
 */
import type { components } from "@markbook/api-client";

import { api, tokens } from "./client";

export type Profile = components["schemas"]["UserProfileResponse"];
export type EffectivePermission = components["schemas"]["EffectivePermission"];

export interface LoginResult {
  ok: boolean;
  /** Set when login failed; the RFC 7807 `detail` from the API. */
  detail?: string;
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const { data, error } = await api.POST("/api/v1/auth/login", {
    body: { email, password },
  });
  if (error || !data) {
    // problem details shape: {detail, code, status, ...}
    return { ok: false, detail: (error as { detail?: string } | null)?.detail ?? "Login failed" };
  }
  tokens.access = data.access_token;
  tokens.refresh = data.refresh_token;
  return { ok: true };
}

export async function logout(): Promise<void> {
  try {
    await api.POST("/api/v1/auth/logout", {});
  } catch {
    // best-effort — clearing local state is the part that matters
  }
  tokens.clear();
}

export async function fetchProfile(): Promise<Profile | null> {
  const { data } = await api.GET("/api/v1/auth/users/me", {});
  return data ?? null;
}
