import { Link } from "@tanstack/react-router";
import { Button, Card, Chip, Icon, Input, StatusBadge, Table, type StatusKey } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface CaseRow {
  id: string;
  case_number: string;
  matter_type: string;
  status: string;
  priority: string;
  received_at: string;
  last_action_type: string;
  due_at: string | null;
  sla_status: string;
}

const STATUS_MAP: Record<string, StatusKey> = {
  pending: "pending",
  under_process: "under_process",
  transferred: "transferred",
  escalated: "escalated",
  disposed: "disposed",
  overdue: "overdue",
  overlap: "overlap",
};

const STATUS_FILTERS = ["pending", "under_process", "escalated", "transferred", "disposed"] as const;

/** Section 9.7 screen 3, Phase 6 slice: R9 search/filter + keyset
 * pagination against `GET /cases`'s `{items, next_cursor}` shape. */
export function CasesListPage() {
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  async function loadPage(cursor: string | null, replace: boolean) {
    setLoading(true);
    const { data } = await api.GET("/api/v1/cases", {
      params: {
        query: {
          q: q || undefined,
          status: status ?? undefined,
          cursor: cursor ? Number(cursor) : undefined,
          limit: 50,
        },
      },
    });
    if (data) {
      setCases((prev) => (replace ? (data.items as CaseRow[]) : [...prev, ...(data.items as CaseRow[])]));
      setNextCursor(data.next_cursor ?? null);
    }
    setLoading(false);
  }

  useEffect(() => {
    loadPage(null, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status]);

  return (
    <Shell active="cases" title="Cases">
      <Card>
        <div className="mb-3 flex items-center gap-2">
          <Icon name="cases" size={20} />
          <h2 className="text-lg font-semibold text-ink">Cases</h2>
        </div>

        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="w-64">
            <Input
              label="Search"
              placeholder="Case ID, reference, institution…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Chip active={status === null} onClick={() => setStatus(null)}>
              All
            </Chip>
            {STATUS_FILTERS.map((s) => (
              <Chip key={s} active={status === s} onClick={() => setStatus(s)}>
                {s.replaceAll("_", " ")}
              </Chip>
            ))}
          </div>
        </div>

        <Table<CaseRow>
          caption="Cases register directory"
          columns={[
            {
              key: "case_number",
              header: "Case ID",
              render: (c) => (
                <Link to="/cases/$id" params={{ id: c.id }} className="font-medium text-brand-600 hover:underline">
                  {c.case_number}
                </Link>
              ),
            },
            { key: "matter_type", header: "Nature", render: (c) => c.matter_type.replaceAll("_", " ") },
            { key: "status", header: "Status", render: (c) => <StatusBadge status={STATUS_MAP[c.status] ?? "pending"} /> },
            { key: "priority", header: "Priority", render: (c) => c.priority },
            { key: "received", header: "Received", render: (c) => new Date(c.received_at).toLocaleDateString() },
            { key: "last_action", header: "Last action", render: (c) => c.last_action_type.replaceAll("_", " ") },
            {
              key: "sla",
              header: "SLA",
              render: (c) =>
                c.sla_status === "not_set" ? (
                  <span className="text-sm text-ink-muted">not set</span>
                ) : c.sla_status === "breached" ? (
                  <StatusBadge status="overdue" />
                ) : (
                  <span className="text-sm text-ink-muted">
                    {c.sla_status === "approaching" ? "due soon" : "on track"}
                    {c.due_at ? ` · ${new Date(c.due_at).toLocaleDateString()}` : ""}
                  </span>
                ),
            },
          ]}
          rows={cases}
          emptyMessage={loading ? "Loading…" : "No cases match these filters."}
        />

        {nextCursor && (
          <div className="mt-4 flex justify-center">
            <Button variant="secondary" disabled={loading} onClick={() => loadPage(nextCursor, false)}>
              {loading ? "Loading…" : "Load more"}
            </Button>
          </div>
        )}
      </Card>
    </Shell>
  );
}
