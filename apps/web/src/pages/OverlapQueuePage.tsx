import { Link } from "@tanstack/react-router";
import { Card, Icon } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface OverlapReason {
  code: string;
  text: string;
}

interface OverlapCandidateRow {
  id: string;
  case_a_id: string;
  case_a_number: string;
  case_b_id: string;
  case_b_number: string;
  score: number;
  level: string;
  reasons: OverlapReason[];
  status: string;
}

interface OverlapGroupRow {
  id: string;
  institution_id: string;
  institution_name: string;
  max_level: string;
  candidates: OverlapCandidateRow[];
  updated_at: string;
}

const LEVEL_LABEL: Record<string, string> = { high: "High", potential: "Potential", info: "Info" };
const LEVEL_COLOR: Record<string, string> = {
  high: "var(--status-escalated-fg)",
  potential: "var(--status-overlap-fg)",
  info: "var(--color-ink-muted)",
};

/** Section 9.7's overlap queue (Phase 4 slice): grouped by institution
 * (Section 8.5 — "the institution-level picture, not 40 pairs"), every
 * authenticated role, T1-only content (scores/reasons, never raw
 * complaint text — see app/models.py's OverlapCandidate docstring). */
export function OverlapQueuePage() {
  const [groups, setGroups] = useState<OverlapGroupRow[] | null>(null);

  useEffect(() => {
    api.GET("/api/v1/overlap/groups").then(({ data }) => {
      if (data) setGroups(data as OverlapGroupRow[]);
    });
  }, []);

  return (
    <Shell active="overlap" title="Overlap coordination queue">
      <Card>
        <div className="mb-3 flex items-center gap-2">
          <Icon name="overlap-link" size={20} />
          <h2 className="text-lg font-semibold text-ink">Overlap coordination queue</h2>
        </div>
        {!groups ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : groups.length === 0 ? (
          <p className="text-sm text-ink-muted">No overlapping cases detected yet.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {groups.map((g) => (
              <div key={g.id} className="rounded-input border border-outline p-3">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-ink">{g.institution_name}</h3>
                  <span className="text-sm font-medium" style={{ color: LEVEL_COLOR[g.max_level] }}>
                    {LEVEL_LABEL[g.max_level] ?? g.max_level}
                  </span>
                </div>
                <ul className="flex flex-col gap-2">
                  {g.candidates.map((c) => (
                    <li key={c.id} className="rounded-input bg-surface-2 p-2 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span>
                          <Link to="/cases/$id" params={{ id: c.case_a_id }} className="font-medium text-brand-600 hover:underline">
                            {c.case_a_number}
                          </Link>{" "}
                          ↔{" "}
                          <Link to="/cases/$id" params={{ id: c.case_b_id }} className="font-medium text-brand-600 hover:underline">
                            {c.case_b_number}
                          </Link>
                        </span>
                        <span className="text-ink-muted">
                          {LEVEL_LABEL[c.level] ?? c.level} ({c.score}/100) — {c.status}
                        </span>
                      </div>
                      <ul className="mt-1 list-inside list-disc text-xs text-ink-muted">
                        {c.reasons.map((r) => (
                          <li key={r.code}>{r.text}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>
    </Shell>
  );
}
