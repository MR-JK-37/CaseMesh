import { useNavigate } from "@tanstack/react-router";
import { Button, Card, Icon, Input } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

const MATTER_TYPES = [
  "student_faculty_stakeholder_complaint",
  "cpgrams_grievance",
  "ragging",
  "norm_violation",
  "vip_ministry_reference",
  "court_case",
  "parliament_question",
  "rti",
  "miscellaneous",
];
const SOURCE_CHANNELS = ["letter", "email", "cpgrams", "walk_in", "phone", "other"];

interface Option {
  id: string;
  name: string;
}

interface DuplicateCandidate {
  id: string;
  case_number: string;
  status: string;
  matter_type: string;
}

/** Section 9.7 screen 12 (Phase 3 slice): registration with duplicate pre-check (R3/R4). */
export function CaseRegistrationPage() {
  const navigate = useNavigate();
  const [institutions, setInstitutions] = useState<Option[]>([]);
  const [bureaus, setBureaus] = useState<Option[]>([]);

  const [institutionId, setInstitutionId] = useState("");
  const [matterType, setMatterType] = useState(MATTER_TYPES[0]);
  const [sourceChannel, setSourceChannel] = useState(SOURCE_CHANNELS[0]);
  const [priority, setPriority] = useState("standard");
  const [bureauId, setBureauId] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [description, setDescription] = useState("");

  const [duplicates, setDuplicates] = useState<DuplicateCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.GET("/api/v1/institutions").then(({ data }) => {
      if (data) setInstitutions((data as { id: string; name: string; status: string }[]).filter((i) => i.status === "active"));
    });
    api.GET("/api/v1/bureaus").then(({ data }) => {
      if (data) setBureaus(data as Option[]);
    });
  }, []);

  useEffect(() => {
    if (!institutionId) {
      setDuplicates(null);
      return;
    }
    api.GET("/api/v1/cases/duplicate-check", { params: { query: { institution_id: institutionId } } }).then(
      ({ data }) => setDuplicates((data as DuplicateCandidate[]) ?? []),
    );
  }, [institutionId]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!institutionId || !bureauId) {
      setError("Institution and assigned bureau are required.");
      return;
    }
    setBusy(true);
    try {
      const { data, error: apiError } = await api.POST("/api/v1/cases", {
        body: {
          institution_ids: [institutionId],
          matter_type: matterType,
          source_channel: sourceChannel,
          priority,
          confidential: false,
          external_refs: [],
          assigned_bureau_id: bureauId,
          next_action_required: nextAction || null,
          description: description || null,
        },
      });
      if (apiError || !data) {
        setError("Could not register case — check you're permitted to register for this bureau.");
        return;
      }
      navigate({ to: "/cases/$id", params: { id: data.id } });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell active="register" title="Register case">
      <div className="flex flex-col gap-6">
        <Card>
          <div className="mb-3 flex items-center gap-2">
            <Icon name="cases" size={20} />
            <h2 className="text-lg font-semibold text-ink">Register case</h2>
          </div>
          <form onSubmit={submit} className="grid max-w-2xl gap-3 md:grid-cols-2">
            <div className="flex flex-col gap-1.5 md:col-span-2">
              <label className="text-sm font-medium text-ink-muted" htmlFor="inst-select">
                Institution
              </label>
              <select
                id="inst-select"
                required
                value={institutionId}
                onChange={(e) => setInstitutionId(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <option value="">— select —</option>
                {institutions.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="matter-select">
                Nature / category
              </label>
              <select
                id="matter-select"
                value={matterType}
                onChange={(e) => setMatterType(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {MATTER_TYPES.map((m) => (
                  <option key={m} value={m}>
                    {m.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="source-select">
                Source channel
              </label>
              <select
                id="source-select"
                value={sourceChannel}
                onChange={(e) => setSourceChannel(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                {SOURCE_CHANNELS.map((s) => (
                  <option key={s} value={s}>
                    {s.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="priority-select">
                Priority
              </label>
              <select
                id="priority-select"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <option value="standard">Standard</option>
                <option value="priority">Priority</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-ink-muted" htmlFor="bureau-select">
                Assigned Bureau / Cell
              </label>
              <select
                id="bureau-select"
                required
                value={bureauId}
                onChange={(e) => setBureauId(e.target.value)}
                className="min-h-11 rounded-input border border-outline bg-surface-0 px-3.5 text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <option value="">— select —</option>
                {bureaus.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="md:col-span-2">
              <Input
                label="Next action required (optional)"
                value={nextAction}
                onChange={(e) => setNextAction(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5 md:col-span-2">
              <label className="text-sm font-medium text-ink-muted" htmlFor="description-input">
                Description (optional)
              </label>
              <textarea
                id="description-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder="A line or two on the nature of the complaint — used only to help spot the same institution being handled elsewhere (Section 8), never shown outside this case's handling bureau."
                className="rounded-input border border-outline bg-surface-0 px-3.5 py-2.5 text-sm text-ink
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              />
            </div>

            {duplicates && duplicates.length > 0 && (
              <div
                className="md:col-span-2 rounded-input p-3 text-sm"
                style={{ color: "var(--status-overlap-fg)", background: "var(--status-overlap-bg)" }}
              >
                <p className="mb-1 flex items-center gap-1.5 font-medium">
                  <Icon name="overlap-link" size={16} /> Potential Overlapping Cases – Coordination Required
                </p>
                <ul className="list-inside list-disc">
                  {duplicates.map((d) => (
                    <li key={d.id}>
                      {d.case_number} — {d.status} ({d.matter_type.replaceAll("_", " ")})
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs opacity-80">
                  Same institution already has open case(s). You may still proceed.
                </p>
              </div>
            )}

            {error && (
              <p role="alert" className="md:col-span-2 text-sm text-[#B42318]">
                {error}
              </p>
            )}
            <div className="md:col-span-2">
              <Button type="submit" disabled={busy}>
                {busy ? "Registering…" : "Register case"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </Shell>
  );
}
