import type { IconName } from "@icm/ui-tokens";
import { Icon } from "./Icon";

export type StatusKey =
  | "pending"
  | "under_process"
  | "disposed"
  | "transferred"
  | "escalated"
  | "overdue"
  | "overlap";

const labels: Record<StatusKey, string> = {
  pending: "Pending",
  under_process: "Under process",
  disposed: "Disposed",
  transferred: "Transferred",
  escalated: "Escalated",
  overdue: "Beyond timeline",
  overlap: "Coordination required",
};

const iconFor: Record<StatusKey, IconName> = {
  pending: "pending",
  under_process: "under-process",
  disposed: "disposed",
  transferred: "transferred",
  escalated: "escalated",
  overdue: "overdue",
  overlap: "overlap",
};

export function getStatusLabel(status: StatusKey): string {
  return labels[status] ?? status;
}

/** Section 9.2/9.1 rule 6: every status pairs an icon with a text label — never color alone. */
export function StatusBadge({
  status,
  className = "",
}: {
  status: StatusKey;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1 text-sm font-medium ${className}`}
      style={{ color: `var(--status-${status}-fg)`, background: `var(--status-${status}-bg)` }}
    >
      <Icon name={iconFor[status]} size={16} />
      {labels[status]}
    </span>
  );
}
