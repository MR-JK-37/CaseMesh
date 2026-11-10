import { Button, Card, Icon, Input } from "@icm/ui-web";
import { useRef, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface ImportRow {
  id: string;
  row_number: number;
  permanent_id: string | null;
  action: "create" | "update" | "unchanged" | "error";
  diff: Record<string, { old: unknown; new: unknown }> | null;
  errors: string[];
}

interface ImportJob {
  id: string;
  status: string;
  row_count: number;
  error_count: number;
  source_filename: string;
  source_name: string;
  rows: ImportRow[];
}

const ACTION_COLOR: Record<string, string> = {
  create: "var(--status-disposed-fg)",
  update: "var(--color-brand-600)",
  unchanged: "var(--color-ink-muted)",
  error: "var(--status-overdue-fg)",
};


/** Section 9.7 screen 13 (Phase 2 slice): upload, preview/diff, commit. */
export function ImportPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [sourceName, setSourceName] = useState("");
  const [job, setJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [committedNotice, setCommittedNotice] = useState<string | null>(null);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setCommittedNotice(null);
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a CSV or XLSX file.");
      return;
    }
    setBusy(true);
    try {
      // The generated client types multipart bodies as a plain object,
      // not FormData, with no clean escape hatch for a real file
      // upload — a raw fetch is simpler than fighting that here. CSRF
      // still needs the same double-submit header every other
      // mutating call gets from the client (Section 7.4).
      const form = new FormData();
      form.append("file", file);
      form.append("source_name", sourceName);
      const csrf = document.cookie.match(/(?:^|; )icm_csrf=([^;]+)/)?.[1];
      const resp = await fetch("http://localhost:8000/api/v1/imports", {
        method: "POST",
        credentials: "include",
        headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : undefined,
        body: form,
      });
      if (!resp.ok) {
        setError("Upload failed — check the role you're signed in as and the file format.");
        return;
      }
      setJob((await resp.json()) as ImportJob);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!job) return;
    const { data, error: apiError } = await api.POST("/api/v1/imports/{job_id}/commit", {
      params: { path: { job_id: job.id } },
    });
    if (apiError) {
      setError("Commit failed.");
      return;
    }
    setCommittedNotice(`Committed: ${data.created} created, ${data.updated} updated.`);
  }

  return (
    <Shell active="import" title="Import institutions">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="upload" size={20} />
            <h2 className="text-lg font-semibold text-ink">Import institutions</h2>
          </div>
          <form onSubmit={upload} className="flex flex-col gap-3 md:max-w-md">
            <Input
              label="Source name (provenance — e.g. the document this came from)"
              required
              value={sourceName}
              onChange={(e) => setSourceName(e.target.value)}
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="import-file">
                CSV or XLSX file
              </label>
              <input
                id="import-file"
                ref={fileRef}
                type="file"
                accept=".csv,.xlsx"
                required
                className="rounded-input border border-outline bg-surface-0 px-3.5 py-2 text-ink"
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-[#B42318]">
                {error}
              </p>
            )}
            <Button type="submit" disabled={busy} className="self-start">
              <Icon name="upload" size={18} />
              {busy ? "Uploading…" : "Preview import"}
            </Button>
          </form>
        </Card>

        {job && (
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-ink">
                Preview: {job.source_filename} ({job.row_count} rows, {job.error_count} errors)
              </h2>
              {job.status === "previewed" && job.error_count < job.row_count && (
                <Button onClick={commit}>Commit import</Button>
              )}
            </div>
            {committedNotice && <p className="mb-3 text-sm text-[#0F7B4F]">{committedNotice}</p>}
            <div className="flex flex-col gap-2">
              {job.rows.map((r) => (
                <div key={r.id} className="rounded-input border border-outline p-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-medium" style={{ color: ACTION_COLOR[r.action] }}>
                      {r.action.toUpperCase()}
                    </span>
                    <span className="text-ink-muted">
                      row {r.row_number} — {r.permanent_id ?? "(no permanent_id)"}
                    </span>
                  </div>
                  {r.errors.length > 0 && <p className="mt-1 text-[#B42318]">{r.errors.join("; ")}</p>}
                  {r.diff && Object.keys(r.diff).length > 0 && (
                    <ul className="mt-1 list-inside list-disc text-ink-muted">
                      {Object.entries(r.diff).map(([field, { old, new: newVal }]) => (
                        <li key={field}>
                          <span className="font-medium">{field}</span>: {String(old ?? "—")} →{" "}
                          <span className="text-ink">{String(newVal)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </Shell>
  );
}
