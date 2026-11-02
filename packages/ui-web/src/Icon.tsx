import { icons, type IconName } from "@icm/ui-tokens";

/**
 * Section 9.9: web icons render through Material Symbols Rounded only,
 * looked up from the single semantic icon table — never a third-party
 * icon library or an emoji. Phase 0 loads the glyphs from Google Fonts
 * (allowed by the Caddy CSP's font-src/style-src — see infra/Caddyfile);
 * self-hosting a subset is a Phase 1+ follow-up (docs/decision-log.md).
 */
export function Icon({
  name,
  filled = false,
  size = 20,
  className = "",
  label,
}: {
  name: IconName;
  filled?: boolean;
  size?: number;
  className?: string;
  label?: string;
}) {
  const spec = icons[name];
  return (
    <span
      className={`material-symbols-rounded select-none ${className}`}
      style={{ fontSize: size, fontVariationSettings: `'FILL' ${filled ? 1 : 0}` }}
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
      data-android-symbol={spec.android}
      data-ios-symbol={spec.ios}
    >
      {spec.android}
    </span>
  );
}
