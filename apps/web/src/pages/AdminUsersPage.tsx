import { Button, Card, Icon, Input, Table } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface UserRow {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  totp_enrolled: boolean;
}

interface BureauOption {
  id: string;
  name: string;
}

const ROLES = [
  "super_admin",
  "competent_authority",
  "senior_management",
  "bureau_head",
  "case_officer",
  "regional_officer",
  "nodal_pg_officer",
  "registry_operator",
  "auditor",
];

/** Section 9.7 screen 14 (Admin, Phase 1 slice): user directory + create + assign. */
export function AdminUsersPage() {
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [bureaus, setBureaus] = useState<BureauOption[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(ROLES[3]);
  const [bureauId, setBureauId] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);

  async function load() {
    const [usersRes, bureausRes] = await Promise.all([
      api.GET("/api/v1/users"),
      api.GET("/api/v1/bureaus"),
    ]);
    if (usersRes.error) {
      setLoadError("Not permitted, or no users visible in your scope.");
    } else {
      setUsers(usersRes.data as UserRow[]);
    }
    if (!bureausRes.error) setBureaus(bureausRes.data as BureauOption[]);
  }

  useEffect(() => {
    load();
  }, []);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreatedNotice(null);
    const { data, error } = await api.POST("/api/v1/users", {
      body: {
        email,
        display_name: displayName,
        password,
        role,
        bureau_ids: bureauId ? [bureauId] : [],
        region_ids: [],
      },
    });
    if (error || !data) {
      setCreateError("Could not create user (duplicate email, weak password, or not permitted).");
      return;
    }
    setCreatedNotice(
      data.totp_provisioning_uri
        ? `Created. This role requires TOTP — hand the user this provisioning URI out-of-band: ${data.totp_provisioning_uri}`
        : "Created.",
    );
    setEmail("");
    setDisplayName("");
    setPassword("");
    setBureauId("");
    await load();
  }

  return (
    <Shell active="admin-users" title="Admin / Users">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="officer" size={20} />
            <h2 className="text-lg font-semibold text-ink">Create user</h2>
          </div>
          <form onSubmit={createUser} className="grid max-w-xl gap-3 md:grid-cols-2">
            <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <Input
              label="Display name"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
            <Input
              label="Temporary password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="role-select">
                Role
              </label>
              <select
                id="role-select"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="bureau-select">
                Bureau (optional)
              </label>
              <select
                id="bureau-select"
                value={bureauId}
                onChange={(e) => setBureauId(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <option value="">— none —</option>
                {bureaus.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              {createError && (
                <p role="alert" className="mb-2 text-sm text-[#B42318]">
                  {createError}
                </p>
              )}
              {createdNotice && <p className="mb-2 text-sm text-ink break-all">{createdNotice}</p>}
              <Button type="submit">Create user</Button>
            </div>
          </form>
        </Card>

        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="cases" size={20} />
            <h2 className="text-lg font-semibold text-ink">All users in your scope</h2>
          </div>
          {loadError ? (
            <p className="text-sm text-[#B42318]">{loadError}</p>
          ) : (
            <Table<UserRow>
              columns={[
                { key: "email", header: "Email", render: (r) => r.email },
                { key: "name", header: "Name", render: (r) => r.display_name },
                { key: "role", header: "Role", render: (r) => r.role },
                { key: "status", header: "Status", render: (r) => (r.is_active ? "Active" : "Inactive") },
                { key: "totp", header: "TOTP", render: (r) => (r.totp_enrolled ? "Enrolled" : "Not enrolled") },
              ]}
              rows={users ?? []}
              emptyMessage="No users visible yet."
            />
          )}
        </Card>
      </div>
    </Shell>
  );
}
