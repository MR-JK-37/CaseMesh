import type { HTMLAttributes } from "react";

export interface GlassSurfaceProps extends HTMLAttributes<HTMLDivElement> {
  rounded?: "card" | "tile" | "pill";
  className?: string;
}

/**
 * Section 9.4: glass belongs to the functional layer (command bar,
 * sidebar rail, floating filter bar, dialogs) — never content cards.
 * Falls back to an opaque surface for `prefers-reduced-transparency`,
 * `prefers-contrast: more`, and browsers without `backdrop-filter`.
 */
export function GlassSurface({
  rounded = "card",
  className = "",
  style,
  ...props
}: GlassSurfaceProps) {
  const roundedClass =
    rounded === "pill"
      ? "rounded-pill"
      : rounded === "tile"
        ? "rounded-tile"
        : "rounded-card";

  return (
    <div
      className={`${roundedClass} backdrop-blur-xl backdrop-saturate-150
        supports-[not(backdrop-filter:blur(1px))]:bg-surface-0
        motion-reduce:backdrop-blur-none
        [@media(prefers-reduced-transparency)]:bg-surface-0
        [@media(prefers-contrast:more)]:bg-surface-0 ${className}`}
      style={{
        background: "var(--glass-fill)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--glass-border)",
        ...style,
      }}
      {...props}
    />
  );
}
