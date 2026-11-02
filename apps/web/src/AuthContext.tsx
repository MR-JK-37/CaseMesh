import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

export interface CurrentUser {
  userId: string;
  role: string;
}

interface AuthState {
  user: CurrentUser | null;
  setUser: (u: CurrentUser | null) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

const STORAGE_KEY = "icm-current-user";

/**
 * The access token itself is an HttpOnly cookie the frontend can never
 * read (Section 7.4) — this context only remembers who's logged in
 * (user id + role, neither secret) so the UI doesn't flash a logged-out
 * state on every page reload. The server-side cookie is what actually
 * gates every API call; if it's expired, calls fail with 401 regardless
 * of what's cached here.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<CurrentUser | null>(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as CurrentUser) : null;
    } catch {
      return null;
    }
  });

  const setUser = (u: CurrentUser | null) => {
    setUserState(u);
    try {
      if (u) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(u));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // per-viewer convenience only; ignore storage failures
    }
  };

  useEffect(() => {
    document.title = user ? `ICM — ${user.role}` : "ICM — AICTE Case Monitor";
  }, [user]);

  const logout = async () => {
    await api.POST("/api/v1/auth/logout", {});
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, setUser, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
