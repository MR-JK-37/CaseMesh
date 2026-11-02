import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { useAuth } from "./AuthContext";

/**
 * Client-side route gate only — convenience, not the real boundary. The
 * actual authorization boundary is server-side (`can()` + RLS, Section
 * 4.2); every page below this still gets a real 401/403 from the API
 * if the HttpOnly session cookie is missing or expired regardless of
 * what this component does.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) navigate({ to: "/" });
  }, [user, navigate]);

  if (!user) return null;
  return <>{children}</>;
}
