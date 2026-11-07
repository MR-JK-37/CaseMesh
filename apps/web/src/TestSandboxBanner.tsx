import { useEffect, useState } from "react";
import { api } from "./api";

/**
 * Section 1.4(b): this deployment shows TEST DATA, not real AICTE data
 * (user decision, docs/decision-log.md Phase 2) — a permanent, visible
 * banner on every screen, driven by the backend's own config (never a
 * hardcoded frontend assumption, so it can never silently drift from
 * what the API is actually doing).
 */
export function TestSandboxBanner() {
  const [tenantMode, setTenantMode] = useState<string | null>(null);

  useEffect(() => {
    api.GET("/api/v1/system/info").then(({ data }) => {
      if (data) setTenantMode(data.tenant_mode);
    });
  }, []);

  if (tenantMode !== "test_sandbox") return null;

  return (
    <div
      role="status"
      aria-label="Sandbox environment notice"
      className="sticky top-0 z-50 w-full bg-[#B42318] px-4 py-2 text-center text-sm font-semibold text-white"
    >
      TEST DATA — NOT REAL. This instance shows synthetic sandbox data only, never real AICTE records.
    </div>
  );
}
