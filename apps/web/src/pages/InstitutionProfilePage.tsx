import { Link, useParams } from "@tanstack/react-router";
import { Button, Card, Icon, StatusBadge, type StatusKey } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import { Shell } from "../Shell";

interface InstitutionDetail {
  id: string;
  permanent_id: string;
  name: string;
  address: string | null;
  state: string | null;
  district: string | null;
  programmes: string | null;
  approved_intake: number | null;
  status: string;
  data_origin: string;
  source_name: string;
  source_url: string | null;
  verified_by_email: string | null;
  verified_at: string | null;
  created_at: string;
}

interface CaseHistoryRow {
  id: string;
  case_number: string;
  matter_type: string;
  status: string;
  assigned_bureau_id: string | null;
  received_at: string;
}

interface OverlapReason {
  code: string;
  text: string;
}

interface OverlapCandidateRow {
  id: string;
  case_a_number: string;
  case_b_number: string;
  score: number;
  level: string;
  reasons: OverlapReason[];
  status: string;
}

interface OverlapGroupRow {
  max_level: string;
  candidates: OverlapCandidateRow[];
}

const STATUS_MAP: Record<string, StatusKey> = {
  pending: "pending",
  under_process: "under_process",
  transferred: "transferred",
  escalated: "escalated",
  disposed: "disposed",
};

/** Section 9.7 screen 6 (Phase 2 slice): identity block + provenance
 * badge + consolidated case history (honestly empty — Phase 3). */
export function InstitutionProfilePage() {
  const { id } = useParams({ from: "/institutions/$id" });
  const { user } = useAuth();
  const [inst, setInst] = useState<InstitutionDetail | null>(null);
  const [cases, setCases] = useState<CaseHistoryRow[]>([]);
  const [casesNote, setCasesNote] = useState<string | null>(null);
  const [overlapGroup, setOverlapGroup] = useState<OverlapGroupRow | null>(null);
  const [notFound, setNotFound] = useState(false);

  async function load() {
    const { data, error } = await api.GET("/api/v1/institutions/{institution_id}", {
      params: { path: { institution_id: id } },
    });
    if (error) {
      setNotFound(true);
      return;
    }
    setInst(data as InstitutionDetail);

    const caseHistory = await api.GET("/api/v1/institutions/{institution_id}/cases", {
      params: { path: { institution_id: id } },
    });
    if (caseHistory.data) {
      setCases((caseHistory.data.cases as CaseHistoryRow[]) ?? []);
      setCasesNote(caseHistory.data.note ?? null);
    }

    const overlap = await api.GET("/api/v1/institutions/{institution_id}/overlap-group", {
      params: { path: { institution_id: id } },
    });
    if (overlap.data) setOverlapGroup(overlap.data as OverlapGroupRow);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function verify() {
    await api.POST("/api/v1/institutions/{institution_id}/verify", {
      params: { path: { institution_id: id } },
    });
    await load();
  }

  if (notFound) {
    return (
      <Shell active="institutions" title="Institution profile">
        <Card>Institution not found.</Card>
      </Shell>
    );
  }

  if (!inst) {
    return (
      <Shell active="institutions" title="Institution profile">
        <Card>Loading…</Card>
      </Shell>
    );
  }

  return (
    <Shell active="institutions" title="Institution profile">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              <Icon name="institution" size={24} />
              <div>
                <h2 className="text-xl font-semibold text-ink">{inst.name}</h2>
                <p className="text-sm text-ink-muted">{inst.permanent_id}</p>
              </div>
            </div>
            {inst.status === "pending_review" && user?.role === "super_admin" && (
              <Button variant="secondary" onClick={verify}>
                Verify &amp; activate
              </Button>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div>
              <dt className="text-ink-muted">Status</dt>
              <dd className="text-ink">{inst.status === "active" ? "Active" : "Pending review"}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">State / District</dt>
              <dd className="text-ink">
                {inst.state ?? "—"} {inst.district ? `/ ${inst.district}` : ""}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-ink-muted">Address</dt>
              <dd className="text-ink">{inst.address ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Programmes</dt>
              <dd className="text-ink">{inst.programmes ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Approved intake</dt>
              <dd className="text-ink tabular-nums">{inst.approved_intake ?? "—"}</dd>
            </div>
          </dl>

          <div className="mt-4 rounded-input bg-surface-2 p-3 text-sm text-ink-muted">
            Source: {inst.source_name}
            {inst.source_url ? (
              <>
                {" "}
                (
                <a href={inst.source_url} className="text-brand-600 underline" target="_blank" rel="noreferrer">
                  link
                </a>
                )
              </>
            ) : null}
            , data origin: {inst.data_origin}, retrieved {new Date(inst.created_at).toLocaleDateString()}.
            {inst.verified_by_email && (
              <> Verified by {inst.verified_by_email} on {new Date(inst.verified_at!).toLocaleDateString()}.</>
            )}
          </div>
        </Card>

        {overlapGroup && overlapGroup.candidates.length > 0 && (
          <Card>
            <div
              className="rounded-input p-3 text-sm"
              style={{ color: "var(--status-overlap-fg)", background: "var(--status-overlap-bg)" }}
            >
              <p className="mb-2 flex items-center gap-1.5 font-medium">
                <Icon name="overlap-link" size={16} /> Potential Overlapping Cases – Coordination Required
              </p>
              <ul className="flex flex-col gap-1 text-xs">
                {overlapGroup.candidates.map((c) => (
                  <li key={c.id}>
                    {c.case_a_number} ↔ {c.case_b_number} — {c.level} ({c.score}/100, {c.status})
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        )}

        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="timeline" size={20} />
            <h2 className="text-lg font-semibold text-ink">Case history</h2>
          </div>
          {cases.length === 0 ? (
            <p className="text-sm text-ink-muted">{casesNote}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {cases.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-input border border-outline p-2 text-sm">
                  <Link to="/cases/$id" params={{ id: c.id }} className="font-medium text-brand-600 hover:underline">
                    {c.case_number}
                  </Link>
                  <span className="text-ink-muted">{c.matter_type.replaceAll("_", " ")}</span>
                  <StatusBadge status={STATUS_MAP[c.status] ?? "pending"} />
                  <span className="text-ink-muted">{new Date(c.received_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </Shell>
  );
}
