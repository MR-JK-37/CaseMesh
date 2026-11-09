import { Link } from "@tanstack/react-router";
import { BarChart, Card, Gauge, Icon, Tile } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import { Shell } from "../Shell";

interface Tiles {
  as_of: string;
  total_cases: number;
  pending: number;
  under_process: number;
  escalated: number;
  transferred: number;
  disposed: number;
  beyond_timeline: number;
  approaching: number;
  ageing_buckets: Record<string, number>;
  bureau_workload: { bureau_id: string | null; bureau_name: string; open: number; overdue: number }[];
  transfers_awaiting_acceptance: number;
  overlap_queue_total: number;
  overlap_queue_top_institutions: { institution_id: string; pending_candidates: number }[];
}

interface MonthPoint {
  month: string;
  received: number;
  disposed: number;
}

function TileCard({ label, value, icon }: { label: string; value: number; icon: string }) {
  return (
    <Tile className="flex items-center gap-3 transition-transform duration-200 hover:-translate-y-0.5">
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-pill text-white"
        style={{ background: "var(--grad-deco)" }}
      >
        <Icon name={icon as never} size={20} />
      </div>
      <div>
        <div className="text-2xl font-semibold tabular-nums text-ink">{value}</div>
        <div className="text-sm text-ink-muted">{label}</div>
      </div>
    </Tile>
  );
}

/** Section 9.6's Command Dashboard, Phase 6: real tiles, SLA compliance
 * gauge and the monthly received-vs-disposed bar chart, all computed
 * live from `app/services/dashboard.py` (Section 6.5's metrics
 * registry) — "No cases registered yet" is still the honest zero-state,
 * not a fabricated number (Section 9.10). */
export function HomePage() {
  const { user } = useAuth();
  const [tiles, setTiles] = useState<Tiles | null>(null);
  const [monthly, setMonthly] = useState<MonthPoint[] | null>(null);

  useEffect(() => {
    api.GET("/api/v1/dashboard/tiles").then(({ data }) => {
      if (data) setTiles(data as unknown as Tiles);
    });
    api.GET("/api/v1/dashboard/monthly").then(({ data }) => {
      if (data) setMonthly(data as unknown as MonthPoint[]);
    });
  }, []);

  const openTotal = tiles ? tiles.total_cases - tiles.disposed : 0;
  const slaCompliance =
    tiles && openTotal > 0 ? Math.round(((openTotal - tiles.beyond_timeline) / openTotal) * 100) : 100;

  return (
    <Shell active="home" title="Dashboard">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-1 flex items-center gap-2">
            <Icon name="dashboard" size={22} />
            <h2 className="text-lg font-semibold text-ink">
              Welcome, <span className="font-normal text-ink-muted">{user?.role}</span>
            </h2>
          </div>
          {tiles && (
            <p className="text-sm text-ink-muted">As of {new Date(tiles.as_of).toLocaleString()}</p>
          )}
        </Card>

        {!tiles ? (
          <Card>
            <p className="text-ink-muted">Loading dashboard…</p>
          </Card>
        ) : tiles.total_cases === 0 ? (
          <Card>
            <p className="text-ink-muted">
              No cases registered yet. Totals, SLA compliance and workload will appear here once the
              first case is registered.
            </p>
          </Card>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <TileCard label="Total cases" value={tiles.total_cases} icon="cases" />
              <TileCard label="Pending" value={tiles.pending} icon="pending" />
              <TileCard label="Under process" value={tiles.under_process} icon="under-process" />
              <TileCard label="Escalated" value={tiles.escalated} icon="escalated" />
              <TileCard label="Transferred" value={tiles.transferred} icon="transfer" />
              <TileCard label="Disposed" value={tiles.disposed} icon="disposed" />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Tile className="border border-outline">
                <div className="text-2xl font-semibold tabular-nums" style={{ color: "var(--status-overdue-fg)" }}>{tiles.beyond_timeline}</div>
                <div className="text-sm text-ink-muted">Beyond timeline</div>
              </Tile>
              <Tile className="border border-outline">
                <div className="text-2xl font-semibold tabular-nums text-ink">
                  {tiles.transfers_awaiting_acceptance}
                </div>
                <div className="text-sm text-ink-muted">Transfers awaiting acceptance</div>
              </Tile>
              <Link to="/overlap">
                <Tile className="border border-outline transition-colors hover:bg-surface-2">
                  <div className="text-2xl font-semibold tabular-nums text-ink">{tiles.overlap_queue_total}</div>
                  <div className="text-sm text-ink-muted">Overlap queue — coordination required</div>
                </Tile>
              </Link>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink-muted">SLA compliance</h3>
                <Gauge percent={slaCompliance} label={`${tiles.beyond_timeline} beyond timeline`} />
              </Card>
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink-muted">Monthly received cases</h3>
                {monthly && monthly.some((m) => m.received > 0 || m.disposed > 0) ? (
                  <BarChart data={monthly.map((m) => ({ label: m.month.slice(5), value: m.received }))} />
                ) : (
                  <p className="text-sm text-ink-muted">Not enough history yet.</p>
                )}
              </Card>
            </div>

            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink-muted">Bureau/Cell workload</h3>
              {tiles.bureau_workload.length === 0 ? (
                <p className="text-sm text-ink-muted">No open cases assigned yet.</p>
              ) : (
                <ul className="flex flex-col divide-y divide-outline">
                  {tiles.bureau_workload.map((row) => (
                    <li key={row.bureau_id ?? "unassigned"} className="flex items-center justify-between py-2">
                      <span className="text-ink">{row.bureau_name}</span>
                      <span className="text-sm text-ink-muted">
                        <span className="font-medium tabular-nums text-ink">{row.open}</span> open
                        {row.overdue > 0 && (
                          <span className="ml-2 text-[#B42318]">· {row.overdue} overdue</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        )}
      </div>
    </Shell>
  );
}
