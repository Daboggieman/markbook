/**
 * Session state: the profile (user + effective_permissions) for the
 * signed-in actor. The nav renders from effective_permissions — the UI
 * hides actions the actor lacks; the backend enforces everything
 * independently (spec §7: UI hiding is UX, never the gate).
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { fetchProfile, login as apiLogin, logout as apiLogout, type Profile } from "../api/auth";
import { refreshAccessToken, tokens } from "../api/client";

export interface AuthState {
  profile: Profile | null;
  /** True until the initial refresh/profile check resolves. */
  booting: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

/** Raw context — exported so tests can inject a fixed AuthState. */
export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // A persisted refresh token means a page reload mid-session: the
      // access token lives only in memory, so mint a fresh one from the
      // refresh FIRST (the 401 interceptor can't do it — it only fires
      // when an access token was already attached), then load the profile.
      if (tokens.refresh) {
        const minted = await refreshAccessToken();
        if (minted) {
          const p = await fetchProfile();
          if (!cancelled) setProfile(p);
        } else {
          tokens.clear(); // dead refresh family — sign out cleanly
        }
      }
      if (!cancelled) setBooting(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const value: AuthState = {
    profile,
    booting,
    login: async (email, password) => {
      const result = await apiLogin(email, password);
      if (!result.ok) throw new Error(result.detail ?? "Login failed");
      setProfile(await fetchProfile());
    },
    logout: async () => {
      await apiLogout();
      setProfile(null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

/**
 * True when the signed-in actor holds the permission at any scope. The nav
 * filter is a UX filter only — every screen's data still comes from the
 * API, which enforces the real gate.
 */
export function hasPermission(
  profile: Profile | null,
  permission: string,
): boolean {
  if (!profile) return false;
  return profile.effective_permissions.some((p) => p.code === permission);
}
