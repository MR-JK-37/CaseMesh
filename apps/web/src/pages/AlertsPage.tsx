import { Button, Card, Icon } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface AlertRow {
  id: string;
  code: string;
  severity: string;
  resource_type: string;
  resource_id: string | null;
  message: string;
  created_at: string;
  acked_by: string | null;
  acked_at: string | null;
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: "var(--status-overdue-fg)",
  warning: "var(--status-pending-fg)",
  info: "var(--color-ink-muted)",
};

/** Section 9.7's alert inbox (Phase 5 slice): the alert catalogue
 * (Section 7.3), broadly listable T1-equivalent metadata (see
 * app/models.py's Alert docstring — never raw case content). */
export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertRow[] | null>(null);
  const [unackedOnly, setUnackedOnly] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const { data } = await api.GET("/api/v1/alerts", { params: { query: { unacked_only: unackedOnly } } });
    if (data) setAlerts(data as AlertRow[]);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unackedOnly]);

  async function ack(id: string) {
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/alerts/{alert_id}/ack", { params: { path: { alert_id: id } } });
    if (apiError) {
      setError("Could not acknowledge — check your role/bureau permits this.");
      return;
    }
    await load();
  }

  return (
    <Shell active="alerts" title="Alerts">
      <Card>
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Icon name="alert" size={20} />
            <h2 className="text-lg font-semibold text-ink">Alerts</h2>
          </div>
          <label className="flex items-center gap-2 text-sm text-ink-muted">
            <input type="checkbox" checked={unackedOnly} onChange={(e) => setUnackedOnly(e.target.checked)} />
            Unacknowledged only
          </label>
        </div>
        {error && (
          <p role="alert" className="mb-3 text-sm text-[#B42318]">
            {error}
          </p>
        )}
        {!alerts ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : alerts.length === 0 ? (
          <p className="text-sm text-ink-muted">No alerts.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {alerts.map((a) => (
              <li key={a.id} className="rounded-input border border-outline p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium" style={{ color: SEVERITY_COLOR[a.severity] }}>
                      {a.code.replaceAll("_", " ")}
                    </p>
                    <p className="text-sm text-ink">{a.message}</p>
                    <p className="text-xs text-ink-muted">{new Date(a.created_at).toLocaleString()}</p>
                    {a.acked_at && <p className="text-xs text-ink-muted">Acknowledged {new Date(a.acked_at).toLocaleString()}</p>}
                  </div>
                  {!a.acked_at && (
                    <Button variant="secondary" onClick={() => ack(a.id)}>
                      Acknowledge
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Shell>
  );
}
