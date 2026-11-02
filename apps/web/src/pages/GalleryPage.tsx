import {
  BarChart,
  Button,
  Card,
  Chip,
  Gauge,
  GlassSurface,
  Icon,
  Input,
  PillNav,
  StatusBadge,
  Table,
  Tile,
  type StatusKey,
} from "@icm/ui-web";
import { useState } from "react";
import { useTheme } from "../useTheme";

const statuses: StatusKey[] = [
  "pending",
  "under_process",
  "disposed",
  "transferred",
  "escalated",
  "overdue",
  "overlap",
];

interface Row {
  id: string;
  caseId: string;
  institution: string;
  status: StatusKey;
}

const rows: Row[] = [
  { id: "1", caseId: "ICM-2026-000001", institution: "—", status: "pending" },
  { id: "2", caseId: "ICM-2026-000002", institution: "—", status: "under_process" },
];

/** Section 9.11 point 1-2: component gallery, every component, light + dark. */
export function GalleryPage() {
  const [theme, setTheme] = useTheme();
  const [activeChip, setActiveChip] = useState("all");
  const [navKey, setNavKey] = useState("dashboard");

  return (
    <main className="min-h-screen p-6 md:p-10">
      <div className="mx-auto flex max-w-5xl flex-col gap-10">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-white">Component gallery</h1>
          <Button variant="secondary" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            <Icon name="settings" size={18} /> {theme === "light" ? "Dark" : "Light"} mode
          </Button>
        </header>

        <section aria-labelledby="buttons-h">
          <h2 id="buttons-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Buttons
          </h2>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="primary" pill>
              Pill
            </Button>
            <Button variant="primary" disabled>
              Disabled
            </Button>
          </div>
        </section>

        <section aria-labelledby="inputs-h">
          <h2 id="inputs-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Inputs
          </h2>
          <div className="grid max-w-sm gap-4">
            <Input label="Case ID" placeholder="ICM-2026-000001" />
            <Input label="With error" error="This field is required" />
          </div>
        </section>

        <section aria-labelledby="chips-h">
          <h2 id="chips-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Chips
          </h2>
          <div className="flex gap-2">
            {["all", "rb", "pgrc", "others"].map((c) => (
              <Chip key={c} active={activeChip === c} onClick={() => setActiveChip(c)}>
                {c.toUpperCase()}
              </Chip>
            ))}
          </div>
        </section>

        <section aria-labelledby="cards-h">
          <h2 id="cards-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Cards &amp; tiles
          </h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Card>
              <p className="text-sm text-ink-muted">Total open cases</p>
              <p className="text-3xl font-semibold tabular-nums text-ink">0</p>
            </Card>
            <Tile>
              <p className="text-sm text-ink-muted">Pending</p>
              <p className="text-2xl font-semibold tabular-nums text-ink">0</p>
            </Tile>
            <Tile>
              <p className="text-sm text-ink-muted">Beyond timeline</p>
              <p className="text-2xl font-semibold tabular-nums text-ink">0</p>
            </Tile>
            <Tile>
              <p className="text-sm text-ink-muted">Overlap queue</p>
              <p className="text-2xl font-semibold tabular-nums text-ink">0</p>
            </Tile>
          </div>
        </section>

        <section aria-labelledby="status-h">
          <h2 id="status-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Status badges
          </h2>
          <div className="flex flex-wrap gap-2">
            {statuses.map((s) => (
              <StatusBadge key={s} status={s} />
            ))}
          </div>
        </section>

        <section aria-labelledby="gauge-h" className="flex flex-wrap gap-10">
          <div>
            <h2 id="gauge-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
              SLA gauge
            </h2>
            <Card>
              <Gauge percent={0} label="SLA compliance — no cases registered yet" />
            </Card>
          </div>
          <div className="min-w-[280px] flex-1">
            <h2 className="mb-3 text-sm font-semibold uppercase text-white/80">Received vs. disposed</h2>
            <Card>
              <BarChart
                data={[
                  { label: "Jun", value: 0 },
                  { label: "Jul", value: 0 },
                  { label: "Aug", value: 0 },
                  { label: "Sep", value: 0 },
                ]}
              />
            </Card>
          </div>
        </section>

        <section aria-labelledby="table-h">
          <h2 id="table-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Table
          </h2>
          <Table<Row>
            columns={[
              { key: "caseId", header: "Case ID", render: (r) => r.caseId },
              { key: "institution", header: "Institution", render: (r) => r.institution },
              { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
            ]}
            rows={[]}
            emptyMessage="No cases registered yet."
          />
          <div className="mt-4">
            <Table<Row>
              columns={[
                { key: "caseId", header: "Case ID", render: (r) => r.caseId },
                { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
              ]}
              rows={rows}
              emptyMessage="No cases registered yet."
            />
          </div>
        </section>

        <section aria-labelledby="nav-h">
          <h2 id="nav-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Pill navigation
          </h2>
          <PillNav
            activeKey={navKey}
            onSelect={setNavKey}
            items={[
              { key: "dashboard", label: "Home", icon: "dashboard" },
              { key: "cases", label: "Cases", icon: "cases" },
              { key: "institutions", label: "Institutions", icon: "institution" },
              { key: "alerts", label: "Alerts", icon: "alert" },
            ]}
          />
        </section>

        <section aria-labelledby="glass-h">
          <h2 id="glass-h" className="mb-3 text-sm font-semibold uppercase text-white/80">
            Glass surface (functional layer only — Section 9.1 rule 3)
          </h2>
          <GlassSurface className="p-6">
            <p className="text-ink">
              Command bars, filter bars, and dialogs use glass. Content cards above stay solid.
            </p>
          </GlassSurface>
        </section>
      </div>
    </main>
  );
}
