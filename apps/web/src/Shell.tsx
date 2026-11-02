import { useNavigate } from "@tanstack/react-router";
import { Icon, PillNav, type PillNavItem } from "@icm/ui-web";
import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "./AuthContext";
import { useRealtimeToast } from "./useRealtimeToast";
import { useTheme } from "./useTheme";

const NAV_ITEMS: (PillNavItem & { to: string; roles?: string[] })[] = [
  { key: "home", label: "Home", icon: "dashboard", to: "/home" },
  { key: "cases", label: "Cases", icon: "cases", to: "/cases" },
  {
    key: "register",
    label: "Register",
    icon: "cases",
    to: "/cases/register",
    roles: ["registry_operator", "bureau_head", "case_officer"],
  },
  { key: "institutions", label: "Institutions", icon: "institution", to: "/institutions" },
  { key: "overlap", label: "Overlap", icon: "overlap-link", to: "/overlap" },
  { key: "alerts", label: "Alerts", icon: "alert", to: "/alerts" },
  { key: "reports", label: "Reports", icon: "report", to: "/reports" },
  { key: "import", label: "Import", icon: "upload", to: "/import", roles: ["super_admin"] },
  { key: "security", label: "Security", icon: "security", to: "/security" },
  { key: "admin-users", label: "Users", icon: "officer", to: "/admin/users", roles: ["super_admin"] },
];

/**
 * Not Section 9.7's full sidebar-rail shell (that's deferred until
 * there are enough real screens to justify it, Section 9.7) — a
 * minimal shell shared by every authenticated real screen so far, with
 * a working sign-out instead of each screen being an island.
 */
export function Shell({
  active,
  title,
  children,
}: {
  active: string;
  title: string;
  children: ReactNode;
}) {
  const { user, logout } = useAuth();
  const [theme, setTheme] = useTheme();
  const navigate = useNavigate();
  const latestEvent = useRealtimeToast();
  const [toastVisible, setToastVisible] = useState(false);

  useEffect(() => {
    if (!latestEvent) return;
    setToastVisible(true);
    const timer = setTimeout(() => setToastVisible(false), 6000);
    return () => clearTimeout(timer);
  }, [latestEvent]);

  const items = NAV_ITEMS.filter((i) => !i.roles || (user && i.roles.includes(user.role)));

  async function signOut() {
    await logout();
    navigate({ to: "/" });
  }

  return (
    <div className="min-h-screen p-6 md:p-10">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <PillNav activeKey={active} onSelect={(key) => navigate({ to: items.find((i) => i.key === key)!.to })} items={items} />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              className="flex min-h-11 min-w-11 items-center justify-center rounded-pill border backdrop-blur-xl
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              style={{ background: "var(--glass-fill)", borderColor: "var(--glass-border)" }}
            >
              <Icon name="settings" />
              <span className="sr-only">Switch to {theme === "light" ? "dark" : "light"} mode</span>
            </button>
            <button
              type="button"
              onClick={signOut}
              className="flex min-h-11 items-center gap-2 rounded-pill border px-4 text-sm font-medium backdrop-blur-xl
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              style={{ background: "var(--glass-fill)", borderColor: "var(--glass-border)" }}
            >
              <Icon name="sign-out" size={18} />
              Sign out
            </button>
          </div>
        </header>
        <main className="flex flex-col gap-6">
          <h1 className="sr-only">{title}</h1>
          {children}
        </main>
      </div>

      {toastVisible && latestEvent && (
        <div
          role="status"
          className="fixed bottom-6 right-6 flex max-w-sm items-start gap-2 rounded-input border p-3 text-sm shadow-lg backdrop-blur-xl"
          style={{ background: "var(--glass-fill)", borderColor: "var(--glass-border)", color: "var(--color-ink)" }}
        >
          <Icon name="alert" size={18} />
          <div>
            <p className="font-medium">Live update</p>
            <p className="text-ink-muted">
              {(latestEvent.payload.message as string | undefined) ??
                (latestEvent.payload.case_number as string | undefined) ??
                latestEvent.event_type}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
