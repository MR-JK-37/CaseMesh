import { Button, Card, Icon, Input, Table } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface SessionRow {
  id: string;
  device_label: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

/** Section 9.7 screen 15 (Phase 1 slice): TOTP enrollment + device/session list with remote sign-out. */
export function ProfileSecurityPage() {
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  const [enrolling, setEnrolling] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [enrollMessage, setEnrollMessage] = useState<string | null>(null);

  async function loadSessions() {
    const { data, error } = await api.GET("/api/v1/sessions");
    if (error) {
      setLoadError(true);
      return;
    }
    setSessions(data as SessionRow[]);
  }

  useEffect(() => {
    loadSessions();
  }, []);

  async function startEnroll() {
    setEnrollMessage(null);
    const { data, error } = await api.POST("/api/v1/totp/enroll/start", {});
    if (error || !data) {
      setEnrollMessage("Could not start enrollment.");
      return;
    }
    setSecret(data.secret);
    setProvisioningUri(data.provisioning_uri);
    setEnrolling(true);
  }

  async function confirmEnroll(e: React.FormEvent) {
    e.preventDefault();
    const { error } = await api.POST("/api/v1/totp/enroll/confirm", {
      body: { totp_code: confirmCode },
    });
    if (error) {
      setEnrollMessage("Invalid code — try again.");
      return;
    }
    setEnrolling(false);
    setSecret(null);
    setProvisioningUri(null);
    setConfirmCode("");
    setEnrollMessage("TOTP enrolled.");
  }

  async function revoke(id: string) {
    await api.POST("/api/v1/sessions/{session_id}/revoke", { params: { path: { session_id: id } } });
    await loadSessions();
  }

  return (
    <Shell active="security" title="Profile & security">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="totp" size={20} />
            <h2 className="text-lg font-semibold text-ink">Two-factor authentication</h2>
          </div>
          {!enrolling ? (
            <div className="flex flex-col gap-3">
              {enrollMessage && <p className="text-sm text-ink-muted">{enrollMessage}</p>}
              <Button variant="secondary" onClick={startEnroll} className="self-start">
                Enroll / re-enroll TOTP
              </Button>
            </div>
          ) : (
            <form onSubmit={confirmEnroll} className="flex max-w-sm flex-col gap-3">
              <p className="text-sm text-ink-muted">
                Add this secret to an authenticator app, then enter a code to confirm.
              </p>
              <code className="break-all rounded-input bg-surface-2 p-3 text-xs text-ink">{secret}</code>
              {provisioningUri && (
                <code className="break-all rounded-input bg-surface-2 p-3 text-xs text-ink-muted">
                  {provisioningUri}
                </code>
              )}
              <Input
                label="Confirmation code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value)}
              />
              {enrollMessage && (
                <p role="alert" className="text-sm" style={{ color: "var(--status-overdue-fg)" }}>
                  {enrollMessage}
                </p>
              )}
              <Button type="submit">Confirm</Button>
            </form>
          )}
        </Card>

        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="live-connection" size={20} />
            <h2 className="text-lg font-semibold text-ink">Sessions</h2>
          </div>
          {loadError ? (
            <p className="text-sm" style={{ color: "var(--status-overdue-fg)" }}>Could not load sessions.</p>
          ) : (
            <Table<SessionRow>
              caption="Active user authentication sessions"
              columns={[
                { key: "created", header: "Started", render: (r) => new Date(r.created_at).toLocaleString() },
                {
                  key: "last_used",
                  header: "Last used",
                  render: (r) => (r.last_used_at ? new Date(r.last_used_at).toLocaleString() : "—"),
                },
                { key: "status", header: "Status", render: (r) => (r.revoked ? "Revoked" : "Active") },
                {
                  key: "action",
                  header: "Actions",
                  render: (r) =>
                    r.revoked ? null : (
                      <button
                        type="button"
                        onClick={() => revoke(r.id)}
                        className="text-sm font-medium text-[#B42318] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                      >
                        Sign out
                      </button>
                    ),
                },
              ]}
              rows={sessions ?? []}
              emptyMessage="No sessions yet."
            />
          )}
        </Card>
      </div>
    </Shell>
  );
}
