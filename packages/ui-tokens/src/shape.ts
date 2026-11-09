/** Section 9.3. */
export const radius = {
  card: 24,
  tile: 18,
  input: 14,
  button: 16,
  pill: 999,
  badge: 6,
} as const;

export const spacing = {
  grid: 4,
  gutter: { mobile: 16, tablet: 24, desktop: 32 },
} as const;

export const elevation = {
  soft: "0 8px 24px rgba(10,46,69,.12)",
  tight: "0 2px 8px rgba(10,46,69,.08)",
  hover: "0 12px 32px rgba(10,46,69,.16)",
} as const;

export const motion = {
  stateMs: [180, 280] as const,
  spring: { damping: 18, stiffness: 220 },
  highlightFadeMs: 600,
  durationFastMs: 150,
  durationNormalMs: 250,
} as const;

export const zIndex = {
  base: 0,
  card: 1,
  header: 10,
  dropdown: 20,
  modal: 30,
  toast: 40,
  tooltip: 50,
} as const;

export type RadiusKey = keyof typeof radius;
export type ElevationKey = keyof typeof elevation;
export type ZIndexKey = keyof typeof zIndex;


