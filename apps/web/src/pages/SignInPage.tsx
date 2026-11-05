import { useNavigate } from "@tanstack/react-router";
import { Button, GlassSurface, Icon, Input } from "@icm/ui-web";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import { useTheme } from "../useTheme";

/** Section 9.7 screen 1, wired to the real Phase 1 backend. */
export function SignInPage() {
  const [theme, setTheme] = useTheme();
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { data, error: apiError, response } = await api.POST("/api/v1/auth/login", {
        body: { email, password, totp_code: needsTotp ? totpCode : null },
      });

      if (apiError || !data) {
        if (response.status === 401 && !needsTotp) {
          // Could be a wrong password OR (for an already-TOTP-enrolled
          // account) a missing code — the backend deliberately returns
          // the same generic 401 for both (Section 4.1: never leak
          // which factor failed). Offering the TOTP field on the first
          // 401 covers the common case without a second round trip for
          // most real logins; a genuinely wrong password just fails
          // again with the field shown, which is an honest outcome.
          setNeedsTotp(true);
          setError("Invalid credentials, or enter your authenticator code below.");
        } else if (response.status === 423) {
          setError("Account temporarily locked after repeated failed attempts. Try again later.");
        } else if (response.status === 429) {
          setError("Too many attempts. Try again in a few minutes.");
        } else {
          setError("Sign-in failed.");
        }
        return;
      }

      setUser({ userId: data.user_id, role: data.role });
      navigate({ to: "/home" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <button
        type="button"
        onClick={() => setTheme(theme === "light" ? "dark" : "light")}
        className="fixed right-6 top-6 flex min-h-11 min-w-11 items-center justify-center rounded-pill
          border backdrop-blur-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        style={{ background: "var(--glass-fill)", borderColor: "var(--glass-border)" }}
      >
        <Icon name="settings" />
        <span className="sr-only">Switch to {theme === "light" ? "dark" : "light"} mode</span>
      </button>

      <GlassSurface className="w-full max-w-sm p-8">
        <div className="mb-6 flex items-center gap-2">
          <Icon name="institution" size={28} />
          <h1 className="text-xl font-semibold text-ink">CaseMesh — AICTE</h1>
        </div>

        <form className="flex flex-col gap-4" onSubmit={submit}>
          <Input
            label="Email"
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {needsTotp && (
            <Input
              label="Authenticator code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
            />
          )}
          {error && (
            <p role="alert" className="text-sm text-[#B42318]">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-muted">Prototype for SIH 2026</p>
      </GlassSurface>
    </main>
  );
}
