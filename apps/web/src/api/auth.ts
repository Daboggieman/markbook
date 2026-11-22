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

export interface ReauthResult {
  ok: boolean;
  /** "MFA_REQUIRED" when the account needs an authenticator code. */
  code?: string;
  detail?: string;
}

/**
 * Step-up credential check (spec §7.1). On success the NEW access token
 * (same session, carrying the reauth_at claim) replaces the current one —
 * the follow-up sensitive call goes out with it via authedFetch.
 *
 * Call it without a code first: a 401 MFA_REQUIRED tells you the account
 * has TOTP enrolled, and the dialog reveals the code field. No profile
 * round-trip needed to learn that.
 */
export async function reauth(password: string, totpCode?: string): Promise<ReauthResult> {
  const { data, error } = await api.POST("/api/v1/auth/reauth", {
    body: totpCode ? { password, totp_code: totpCode } : { password },
  });
  if (error || !data) {
    const problem = error as { code?: string; detail?: string } | null;
    return {
      ok: false,
      code: problem?.code,
      detail: problem?.detail ?? "Re-authentication failed",
    };
  }
  tokens.access = data.access_token;
  return { ok: true };
}
