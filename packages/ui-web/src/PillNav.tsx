import type { IconName } from "@icm/ui-tokens";
import { Icon } from "./Icon";

export interface PillNavItem {
  key: string;
  label: string;
  icon: IconName;
}

export interface PillNavProps {
  items: PillNavItem[];
  activeKey: string;
  onSelect: (key: string) => void;
  orientation?: "horizontal" | "vertical";
  className?: string;
  ariaLabel?: string;
}

/** Section 9.6/9.8: floating pill navigation, active item expands into a gradient pill + label. */
export function PillNav({
  items,
  activeKey,
  onSelect,
  orientation = "horizontal",
  className = "",
  ariaLabel = "Primary",
}: PillNavProps) {
  return (
    <nav
      aria-label={ariaLabel}
      className={`flex max-w-full gap-1 overflow-x-auto rounded-pill p-1.5 backdrop-blur-xl border
        ${orientation === "vertical" ? "flex-col" : "flex-row"} ${className}`}
      style={{ background: "var(--glass-fill)", borderColor: "var(--glass-border)" }}
    >
      {items.map((item) => {
        const isActive = item.key === activeKey;
        return (
          <button
            key={item.key}
            type="button"
            aria-current={isActive ? "page" : undefined}
            onClick={() => onSelect(item.key)}
            className={`flex min-h-11 items-center gap-2 rounded-pill px-4 text-sm font-medium
              transition-all duration-200 focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-brand-500
              ${isActive ? "text-white" : "text-ink-muted hover:text-ink"}`}
            // grad-deco is decorative-only (no body text, Section 9.2) —
            // the active pill carries a text label, so it uses grad-text
            // (verified >=4.5:1 for white text) instead.
            style={isActive ? { background: "var(--grad-text)" } : undefined}
          >
            <Icon name={item.icon} size={18} filled={isActive} />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
