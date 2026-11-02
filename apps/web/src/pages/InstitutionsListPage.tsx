import { Link } from "@tanstack/react-router";
import { Card, Icon, Table } from "@icm/ui-web";
import { useEffect, useState } from "react";
import { api } from "../api";
import { Shell } from "../Shell";

interface InstitutionRow {
  id: string;
  permanent_id: string;
  name: string;
  state: string | null;
  status: string;
  data_origin: string;
  source_name: string;
}

/** Section 9.7 screen 5 (Phase 2 slice): institutions list with provenance. */
export function InstitutionsListPage() {
  const [institutions, setInstitutions] = useState<InstitutionRow[] | null>(null);

  useEffect(() => {
    api.GET("/api/v1/institutions").then(({ data }) => {
      if (data) setInstitutions(data as InstitutionRow[]);
    });
  }, []);

  return (
    <Shell active="institutions" title="Institutions">
      <Card>
        <div className="mb-3 flex items-center gap-2">
          <Icon name="institution" size={20} />
          <h2 className="text-lg font-semibold text-ink">Institutions</h2>
        </div>
        <Table<InstitutionRow>
          columns={[
            {
              key: "name",
              header: "Name",
              render: (r) => (
                <Link to="/institutions/$id" params={{ id: r.id }} className="font-medium text-brand-600 hover:underline">
                  {r.name}
                </Link>
              ),
            },
            { key: "permanent_id", header: "Permanent ID", render: (r) => r.permanent_id },
            { key: "state", header: "State", render: (r) => r.state ?? "—" },
            {
              key: "status",
              header: "Status",
              render: (r) =>
                r.status === "active" ? (
                  <span className="text-[#0F7B4F]">Active</span>
                ) : (
                  <span className="text-[#8A5A00]">Pending review</span>
                ),
            },
            {
              key: "source",
              header: "Source",
              render: (r) => (
                <span className="text-sm text-ink-muted" title={r.data_origin}>
                  {r.source_name}
                </span>
              ),
            },
          ]}
          rows={institutions ?? []}
          emptyMessage="No institutions imported yet."
        />
      </Card>
    </Shell>
  );
}
