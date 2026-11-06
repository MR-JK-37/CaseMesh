import { Button, Card, Icon, Table } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface ReportDef {
  id: string;
  title: string;
  description: string;
}

interface ReportResult {
  report_id: string;
  title: string;
  generated_at: string;
  columns: string[];
  rows: (string | number)[][];
}

/** Section 9.7's report catalogue (R11): parameter-free previews for
 * Phase 6's four reports, each backed by the same `app/services/
 * dashboard.py` functions the Command Dashboard uses — see
 * docs/metrics.md. Export downloads the formula-safe, watermarked CSV
 * the backend builds (`app/services/csv_export.py`), never a
 * client-side re-serialization of the preview rows. */
export function ReportsPage() {
  const [catalogue, setCatalogue] = useState<ReportDef[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api.GET("/api/v1/reports").then(({ data }) => {
      if (data) setCatalogue(data as ReportDef[]);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    setResult(null);
    api
      .GET("/api/v1/reports/{report_id}/run", {
        params: { path: { report_id: selected }, query: { format: "json" } },
      })
      .then(({ data }) => {
        if (data) setResult(data as unknown as ReportResult);
      });
  }, [selected]);

  async function exportCsv() {
    if (!selected) return;
    setExporting(true);
    try {
      const { data } = await api.GET("/api/v1/reports/{report_id}/run", {
        params: { path: { report_id: selected }, query: { format: "csv" } },
        parseAs: "blob",
      });
      if (!data) return;
      const url = URL.createObjectURL(data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `casemesh-${selected}-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <Shell active="reports" title="Reports">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="report" size={20} />
            <h2 className="text-lg font-semibold text-ink">Report catalogue</h2>
          </div>
          {!catalogue ? (
            <p className="text-sm text-ink-muted">Loading…</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {catalogue.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(r.id)}
                    className={`w-full rounded-input px-3 py-2 text-left text-sm transition-colors
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500
                      ${selected === r.id ? "bg-brand-600 text-white" : "text-ink hover:bg-surface-2"}`}
                  >
                    <div className="font-medium">{r.title}</div>
                    <div className={selected === r.id ? "text-white/80" : "text-ink-muted"}>{r.description}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          {!selected ? (
            <p className="text-ink-muted">Select a report from the catalogue.</p>
          ) : !result ? (
            <p className="text-ink-muted">Running report…</p>
          ) : (
            <>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-ink">{result.title}</h2>
                  <p className="text-sm text-ink-muted">
                    As of {new Date(result.generated_at).toLocaleString()} — Section 9.7's export carries the same
                    watermark and a SHA-256 hash
                  </p>
                </div>
                <Button variant="secondary" onClick={exportCsv} disabled={exporting}>
                  <Icon name="export" size={16} />
                  {exporting ? "Exporting…" : "Export CSV"}
                </Button>
              </div>
              <Table<{ id: string; cells: (string | number)[] }>
                columns={result.columns.map((header, colIndex) => ({
                  key: `col-${colIndex}`,
                  header,
                  render: (row) => <span className="tabular-nums">{row.cells[colIndex]}</span>,
                }))}
                rows={result.rows.map((cells, i) => ({ id: String(i), cells }))}
                emptyMessage="No data for this report yet."
              />
            </>
          )}
        </Card>
      </div>
    </Shell>
  );
}
