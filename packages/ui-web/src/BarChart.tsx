import { useState } from "react";

/** Section 9.6: vertical bars, one highlighted gradient bar + marker dot, inactive bars brand-50. */
export function BarChart({
  data,
  className = "",
}: {
  data: { label: string; value: number }[];
  className?: string;
}) {
  if (data.length === 0) {
    return <div className={`text-sm text-ink-muted ${className}`}>No data available</div>;
  }
  const [active, setActive] = useState(data.length - 1);
  const max = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className={className}>
      <div className="flex items-end gap-3 h-40">
        {data.map((d, i) => {
          const isActive = i === active;
          const heightPct = (d.value / max) * 100;
          return (
            <button
              key={d.label}
              type="button"
              onClick={() => setActive(i)}
              aria-pressed={isActive}
              aria-label={`${d.label}: ${d.value}`}
              className="flex flex-1 flex-col items-center justify-end gap-2 h-full focus-visible:outline-none"
            >
              {isActive && <span className="h-2 w-2 rounded-full bg-brand-500" />}
              <div
                className="w-full rounded-t-md transition-all duration-200"
                style={{
                  height: `${heightPct}%`,
                  background: isActive ? "var(--grad-deco)" : "var(--color-brand-50)",
                }}
              />
              <span className="text-xs text-ink-muted">{d.label}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-sm text-ink" aria-live="polite">
        {data[active].label}: <span className="font-semibold tabular-nums">{data[active].value}</span>
      </p>
    </div>
  );
}
