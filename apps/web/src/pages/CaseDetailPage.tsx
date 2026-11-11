import { useParams } from "@tanstack/react-router";
import { Button, Card, Icon, Input, StatusBadge, type StatusKey } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface CaseDetail {
  id: string;
  case_number: string;
  matter_type: string;
  source_channel: string;
  priority: string;
  confidential: boolean;
  status: string;
  received_at: string;
  expected_disposal_date: string | null;
  disposed_at: string | null;
  disposal_type: string | null;
  assigned_bureau_id: string | null;
  assigned_officer_id: string | null;
  last_action_type: string;
  last_action_at: string;
  next_action_required: string | null;
  institution_ids: string[];
  due_at: string | null;
  sla_status: string;
}

interface CaseEventRow {
  id: string;
  event_type: string;
  actor_role: string;
  remark: string | null;
  created_at: string;
}

interface Option {
  id: string;
  name?: string;
  email?: string;
  display_name?: string;
}

interface TransferRow {
  id: string;
  to_bureau_id: string;
  state: string;
  reason: string | null;
  proposed_at: string;
}

interface OverlapReason {
  code: string;
  text: string;
}

interface OverlapCandidateRow {
  id: string;
  case_a_id: string;
  case_a_number: string;
  case_a_bureau_id: string | null;
  case_b_id: string;
  case_b_number: string;
  case_b_bureau_id: string | null;
  score: number;
  level: string;
  reasons: OverlapReason[];
  status: string;
  relationship_type: string | null;
  dismiss_reason: string | null;
  thread_id: string | null;
}

interface MessageRow {
  id: string;
  author_role: string;
  body: string;
  created_at: string;
}

const STATUS_MAP: Record<string, StatusKey> = {
  pending: "pending",
  under_process: "under_process",
  transferred: "transferred",
  escalated: "escalated",
  disposed: "disposed",
};

/** Section 9.7 screen 4 (Phase 3 slice): status + T2 timeline (bureau-restricted) + workflow actions. */
export function CaseDetailPage() {
  const { id } = useParams({ from: "/cases/$id" });
  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<CaseEventRow[] | null>(null);
  const [eventsDenied, setEventsDenied] = useState(false);
  const [bureaus, setBureaus] = useState<Option[]>([]);
  const [users, setUsers] = useState<Option[]>([]);
  const [transfers, setTransfers] = useState<TransferRow[]>([]);
  const [overlaps, setOverlaps] = useState<OverlapCandidateRow[]>([]);
  const [threadMessages, setThreadMessages] = useState<Record<string, MessageRow[]>>({});
  const [newMessage, setNewMessage] = useState<Record<string, string>>({});
  const [decisionReason, setDecisionReason] = useState<Record<string, string>>({});
  const [decisionType, setDecisionType] = useState<Record<string, string>>({});
  const [dismissReason, setDismissReason] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [remark, setRemark] = useState("");
  const [officerId, setOfficerId] = useState("");
  const [transferBureauId, setTransferBureauId] = useState("");
  const [transferReason, setTransferReason] = useState("");
  const [disposalType, setDisposalType] = useState("resolved");
  const [disposalRemark, setDisposalRemark] = useState("");

  async function load() {
    const { data } = await api.GET("/api/v1/cases/{case_id}", { params: { path: { case_id: id } } });
    if (data) setCaseData(data as CaseDetail);

    const ev = await api.GET("/api/v1/cases/{case_id}/events", { params: { path: { case_id: id } } });
    if (ev.error) {
      setEventsDenied(true);
    } else {
      setEvents(ev.data as CaseEventRow[]);
      setEventsDenied(false);
    }

    const b = await api.GET("/api/v1/bureaus");
    if (b.data) setBureaus(b.data as Option[]);
    const u = await api.GET("/api/v1/users");
    if (u.data) setUsers(u.data as Option[]);
    const t = await api.GET("/api/v1/cases/{case_id}/transfers", { params: { path: { case_id: id } } });
    if (t.data) setTransfers(t.data as TransferRow[]);

    const ov = await api.GET("/api/v1/cases/{case_id}/overlaps", { params: { path: { case_id: id } } });
    const overlapRows = (ov.data as OverlapCandidateRow[]) ?? [];
    setOverlaps(overlapRows);
    for (const o of overlapRows) {
      if (o.thread_id) {
        const m = await api.GET("/api/v1/overlap/threads/{thread_id}/messages", {
          params: { path: { thread_id: o.thread_id } },
        });
        if (m.data) setThreadMessages((prev) => ({ ...prev, [o.thread_id as string]: m.data as MessageRow[] }));
      }
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function runAction(label: string, fn: () => Promise<{ error?: unknown }>) {
    setError(null);
    setNotice(null);
    const result = await fn();
    if (result.error) {
      setError(`${label} failed — check your role/bureau permits this.`);
      return;
    }
    setNotice(`${label} recorded.`);
    await load();
  }

  if (!caseData) {
    return (
      <Shell active="cases" title="Case detail">
        <Card>Loading…</Card>
      </Shell>
    );
  }

  return (
    <Shell active="cases" title="Case detail">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Icon name="cases" size={24} />
              <div>
                <h2 className="text-xl font-semibold text-ink">{caseData.case_number}</h2>
                <p className="text-sm text-ink-muted">{caseData.matter_type.replaceAll("_", " ")}</p>
              </div>
            </div>
            <StatusBadge status={STATUS_MAP[caseData.status] ?? "pending"} />
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm md:grid-cols-3">
            <div>
              <dt className="text-ink-muted">Received</dt>
              <dd className="text-ink">{new Date(caseData.received_at).toLocaleDateString()}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Priority</dt>
              <dd className="text-ink">{caseData.priority}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Source</dt>
              <dd className="text-ink">{caseData.source_channel}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Last action</dt>
              <dd className="text-ink">
                {caseData.last_action_type.replaceAll("_", " ")} ({new Date(caseData.last_action_at).toLocaleString()})
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">Next action required</dt>
              <dd className="text-ink">{caseData.next_action_required ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Expected disposal</dt>
              <dd className="text-ink">
                {caseData.expected_disposal_date ? new Date(caseData.expected_disposal_date).toLocaleDateString() : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">SLA (Section 7.2)</dt>
              <dd className="text-ink">
                {caseData.sla_status === "not_set" ? (
                  <span className="text-ink-muted">Policy not set — contact admin</span>
                ) : (
                  <>
                    {caseData.sla_status === "breached" && <StatusBadge status="overdue" />}
                    {caseData.sla_status !== "breached" && (
                      <span>{caseData.sla_status === "approaching" ? "Due soon" : "On track"}</span>
                    )}
                    {caseData.due_at && ` — due ${new Date(caseData.due_at).toLocaleDateString()}`}
                  </>
                )}
              </dd>
            </div>
          </dl>
        </Card>

        {error && (
          <p role="alert" className="text-sm" style={{ color: "var(--status-overdue-fg)" }}>
            {error}
          </p>
        )}
        {notice && <p className="text-sm" style={{ color: "var(--status-disposed-fg)" }}>{notice}</p>}


        {overlaps.filter((o) => o.status === "pending" || o.thread_id).length > 0 && (
          <Card>
            <div
              className="rounded-input p-3 text-sm"
              style={{ color: "var(--status-overlap-fg)", background: "var(--status-overlap-bg)" }}
            >
              <p className="mb-2 flex items-center gap-1.5 font-medium">
                <Icon name="overlap-link" size={16} /> Potential Overlapping Cases – Coordination Required
              </p>
              <div className="flex flex-col gap-3">
                {overlaps.map((o) => {
                  const otherCaseNumber = o.case_a_id === id ? o.case_b_number : o.case_a_number;
                  const otherBureauId = o.case_a_id === id ? o.case_b_bureau_id : o.case_a_bureau_id;
                  return (
                    <div key={o.id} className="rounded-input border border-[color-mix(in_srgb,currentColor_25%,transparent)] p-3">
                      <p className="font-medium">
                        {otherCaseNumber} ({bureaus.find((b) => b.id === otherBureauId)?.name ?? "another bureau"}) —{" "}
                        {o.level} ({o.score}/100) — {o.status}
                      </p>
                      <ul className="mt-1 list-inside list-disc text-xs opacity-90">
                        {o.reasons.map((r) => (
                          <li key={r.code}>{r.text}</li>
                        ))}
                      </ul>
                      {o.status === "confirmed" && o.relationship_type && (
                        <p className="mt-1 text-xs opacity-90">Confirmed and linked: {o.relationship_type}</p>
                      )}
                      {o.status === "dismissed" && o.dismiss_reason && (
                        <p className="mt-1 text-xs opacity-90">Dismissed: {o.dismiss_reason}</p>
                      )}

                      {o.status === "pending" && (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <Button
                            variant="secondary"
                            onClick={() =>
                              runAction("Confirmation", () =>
                                api.POST("/api/v1/overlap/candidates/{candidate_id}/confirm", {
                                  params: { path: { candidate_id: o.id } },
                                  body: { relationship_type: "duplicate" },
                                }),
                              )
                            }
                          >
                            Confirm and link
                          </Button>
                          <Input
                            label="Dismiss reason"
                            value={dismissReason[o.id] ?? ""}
                            onChange={(e) => setDismissReason((p) => ({ ...p, [o.id]: e.target.value }))}
                          />
                          <Button
                            variant="destructive"
                            disabled={!dismissReason[o.id]}
                            onClick={() =>
                              runAction("Dismissal", () =>
                                api.POST("/api/v1/overlap/candidates/{candidate_id}/dismiss", {
                                  params: { path: { candidate_id: o.id } },
                                  body: { reason: dismissReason[o.id] },
                                }),
                              )
                            }
                          >
                            Dismiss
                          </Button>
                          {!o.thread_id && (
                            <Button
                              variant="ghost"
                              onClick={() =>
                                runAction("Coordination", () =>
                                  api.POST("/api/v1/overlap/candidates/{candidate_id}/coordinate", {
                                    params: { path: { candidate_id: o.id } },
                                    body: {},
                                  }),
                                )
                              }
                            >
                              Start coordination
                            </Button>
                          )}
                        </div>
                      )}

                      {o.thread_id && (
                        <div className="mt-3 border-t border-[color-mix(in_srgb,currentColor_25%,transparent)] pt-2">
                          <p className="mb-1 text-xs font-medium opacity-90">Coordination thread</p>
                          <ul className="mb-2 flex flex-col gap-1 text-xs">
                            {(threadMessages[o.thread_id] ?? []).map((m) => (
                              <li key={m.id}>
                                <span className="font-medium">{m.author_role}:</span> {m.body}
                              </li>
                            ))}
                          </ul>
                          <div className="flex flex-wrap items-end gap-2">
                            <Input
                              label="Message"
                              value={newMessage[o.thread_id] ?? ""}
                              onChange={(e) => setNewMessage((p) => ({ ...p, [o.thread_id as string]: e.target.value }))}
                            />
                            <Button
                              variant="secondary"
                              disabled={!newMessage[o.thread_id]}
                              onClick={() =>
                                runAction("Message", () =>
                                  api.POST("/api/v1/overlap/threads/{thread_id}/messages", {
                                    params: { path: { thread_id: o.thread_id as string } },
                                    body: { body: newMessage[o.thread_id as string] },
                                  }),
                                )
                              }
                            >
                              Post
                            </Button>
                          </div>
                          <div className="mt-2 flex flex-wrap items-end gap-2">
                            <div className="flex flex-col gap-1.5">
                              <label className="text-xs font-medium opacity-90" htmlFor={`decision-type-${o.id}`}>
                                Decision
                              </label>
                              <select
                                id={`decision-type-${o.id}`}
                                value={decisionType[o.id] ?? "proceed_in_parallel"}
                                onChange={(e) => setDecisionType((p) => ({ ...p, [o.id]: e.target.value }))}
                                className="min-h-9 rounded-input border border-outline bg-surface-0 px-2 text-ink"
                              >
                                <option value="proceed_in_parallel">Proceed in parallel</option>
                                <option value="consolidate">Consolidate</option>
                                <option value="hold">Hold</option>
                              </select>
                            </div>
                            <Input
                              label="Reason (required)"
                              value={decisionReason[o.id] ?? ""}
                              onChange={(e) => setDecisionReason((p) => ({ ...p, [o.id]: e.target.value }))}
                            />
                            <Button
                              variant="secondary"
                              disabled={!decisionReason[o.id]}
                              onClick={() =>
                                runAction("Decision", () =>
                                  api.POST("/api/v1/overlap/threads/{thread_id}/decision", {
                                    params: { path: { thread_id: o.thread_id as string } },
                                    body: {
                                      decision_type: decisionType[o.id] ?? "proceed_in_parallel",
                                      reason: decisionReason[o.id],
                                    },
                                  }),
                                )
                              }
                            >
                              Record decision
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </Card>
        )}

        {transfers.some((t) => t.state === "proposed") && (
          <Card>
            <div className="mb-3 flex items-center gap-2">
              <Icon name="transfer" size={20} />
              <h2 className="text-lg font-semibold text-ink">Transfer awaiting acceptance</h2>
            </div>
            {transfers
              .filter((t) => t.state === "proposed")
              .map((t) => (
                <div key={t.id} className="flex flex-wrap items-center justify-between gap-3 rounded-input border border-outline p-3">
                  <div>
                    <p className="text-sm text-ink">
                      To: {bureaus.find((b) => b.id === t.to_bureau_id)?.name ?? t.to_bureau_id}
                    </p>
                    <p className="text-sm text-ink-muted">{t.reason}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      onClick={() =>
                        runAction("Transfer acceptance", () =>
                          api.POST("/api/v1/cases/{case_id}/transfer/{transfer_id}/accept", {
                            params: { path: { case_id: id, transfer_id: t.id } },
                          }),
                        )
                      }
                    >
                      Accept
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={() =>
                        runAction("Transfer rejection", () =>
                          api.POST("/api/v1/cases/{case_id}/transfer/{transfer_id}/reject", {
                            params: { path: { case_id: id, transfer_id: t.id } },
                          }),
                        )
                      }
                    >
                      Reject
                    </Button>
                  </div>
                </div>
              ))}
          </Card>
        )}

        {caseData.status !== "disposed" && (
          <Card>
            <h2 className="mb-3 text-lg font-semibold text-ink">Workflow actions</h2>
            <div className="flex flex-col gap-6">
              <div className="flex flex-wrap items-end gap-2">
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-ink-muted" htmlFor="officer-select">
                    Assign officer
                  </label>
                  <select
                    id="officer-select"
                    value={officerId}
                    onChange={(e) => setOfficerId(e.target.value)}
                    className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink"
                  >
                    <option value="">— select —</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.display_name ?? u.email}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  variant="secondary"
                  disabled={!officerId}
                  onClick={() =>
                    runAction("Assignment", () =>
                      api.POST("/api/v1/cases/{case_id}/assign", {
                        params: { path: { case_id: id } },
                        body: { officer_id: officerId },
                      }),
                    )
                  }
                >
                  Assign
                </Button>
              </div>

              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  runAction("Remark", () =>
                    api.POST("/api/v1/cases/{case_id}/remark", {
                      params: { path: { case_id: id } },
                      body: { remark },
                    }),
                  );
                  setRemark("");
                }}
              >
                <div className="min-w-[280px] flex-1">
                  <Input label="Add remark" value={remark} onChange={(e) => setRemark(e.target.value)} required />
                </div>
                <Button type="submit" variant="secondary">
                  Add remark
                </Button>
              </form>

              <div className="flex flex-wrap items-end gap-2">
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-ink-muted" htmlFor="transfer-bureau-select">
                    Propose transfer to
                  </label>
                  <select
                    id="transfer-bureau-select"
                    value={transferBureauId}
                    onChange={(e) => setTransferBureauId(e.target.value)}
                    className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink"
                  >
                    <option value="">— select —</option>
                    {bureaus
                      .filter((b) => b.id !== caseData.assigned_bureau_id)
                      .map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="min-w-[200px]">
                  <Input label="Reason" value={transferReason} onChange={(e) => setTransferReason(e.target.value)} />
                </div>
                <Button
                  variant="secondary"
                  disabled={!transferBureauId || !transferReason}
                  onClick={() =>
                    runAction("Transfer proposal", () =>
                      api.POST("/api/v1/cases/{case_id}/transfer/propose", {
                        params: { path: { case_id: id } },
                        body: { to_bureau_id: transferBureauId, reason: transferReason },
                      }),
                    )
                  }
                >
                  Propose transfer
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => runAction("Escalation", () => api.POST("/api/v1/cases/{case_id}/escalate", { params: { path: { case_id: id } } }))}
                >
                  <Icon name="escalate" size={16} /> Escalate
                </Button>
              </div>

              <form
                className="flex flex-wrap items-end gap-2 border-t border-outline pt-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  runAction("Disposal", () =>
                    api.POST("/api/v1/cases/{case_id}/dispose", {
                      params: { path: { case_id: id } },
                      body: { disposal_type: disposalType, remark: disposalRemark },
                    }),
                  );
                }}
              >
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-ink-muted" htmlFor="disposal-type-select">
                    Disposal type
                  </label>
                  <select
                    id="disposal-type-select"
                    value={disposalType}
                    onChange={(e) => setDisposalType(e.target.value)}
                    className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink"
                  >
                    <option value="resolved">Resolved</option>
                    <option value="not_substantiated">Not substantiated</option>
                    <option value="withdrawn">Withdrawn</option>
                    <option value="referred_elsewhere">Referred elsewhere</option>
                  </select>
                </div>
                <div className="min-w-[280px] flex-1">
                  <Input
                    label="Disposal remark"
                    value={disposalRemark}
                    onChange={(e) => setDisposalRemark(e.target.value)}
                    required
                  />
                </div>
                <Button type="submit" variant="destructive">
                  <Icon name="dispose" size={16} /> Dispose
                </Button>
              </form>
            </div>
          </Card>
        )}

        {caseData.status === "disposed" && (
          <Card>
            <Button
              variant="secondary"
              onClick={() => runAction("Reopening", () => api.POST("/api/v1/cases/{case_id}/reopen", { params: { path: { case_id: id } } }))}
            >
              Reopen case
            </Button>
          </Card>
        )}

        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="timeline" size={20} />
            <h2 className="text-lg font-semibold text-ink">Timeline</h2>
          </div>
          {eventsDenied ? (
            <p className="text-sm text-ink-muted">
              This case's history is visible only to its handling bureau and the competent authority.
            </p>
          ) : (
            <ol className="flex flex-col gap-3">
              {(events ?? []).map((e) => (
                <li key={e.id} className="border-l-2 border-outline pl-3">
                  <p className="text-sm font-medium text-ink">
                    {e.event_type.replaceAll("_", " ")} <span className="text-ink-muted">· {e.actor_role}</span>
                  </p>
                  <p className="text-xs text-ink-muted">{new Date(e.created_at).toLocaleString()}</p>
                  {e.remark && <p className="mt-1 text-sm text-ink">{e.remark}</p>}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
    </Shell>
  );
}
