/**
 * Section 9.2 color tokens. Light theme re-based 2026-10-29 on a
 * smart-home-app reference (light canvas, solid white cards, blue
 * gradient accent widgets, pill nav — see docs/decision-log.md) while
 * keeping every value that was already contrast-verified and already
 * matched that reference's component patterns (brand ramp, status
 * palette, card/pill shapes) unchanged — only `canvas.light` and the
 * light `surface`/`outline` tints moved, from a dark navy glass-over-
 * gradient canvas to a near-white one. Dark theme is unchanged (the
 * reference showed no dark variant). Re-verified for contrast (see
 * ../scripts/check-contrast.mjs and docs/design-contrast.md). No raw
 * hex may appear outside this file (enforced by
 * scripts/check-data-origin.sh's sibling lint — see
 * scripts/check-no-raw-hex.sh).
 */

export const canvas = {
  light:
    "radial-gradient(130% 100% at 72% 0%, #EAF6FF 0%, #F3F9FD 42%, #FFFFFF 78%)",
  dark:
    "radial-gradient(120% 90% at 70% 15%, #134563 0%, #0D3753 45%, #06283D 100%)",
} as const;

export const surface = {
  light: { "0": "#FFFFFF", "1": "#F3F8FC", "2": "#EAF3FA" },
  dark: { "0": "#0D3753", "1": "#134563", "2": "#0B3048" },
} as const;

export const outline = { light: "#E3EDF5", dark: "#2A5775" } as const;

export const ink = { light: "#0A2E45", dark: "#E6F2FA" } as const;
export const inkMuted = { light: "#5B7088", dark: "#A9C4D8" } as const;

/** Brand ramp — brand-500 is the seed color for the Material 3 scheme (Section 9.5). */
export const brand = {
  "700": "#0B5F94",
  "600": "#0F6FA8",
  "500": "#1787C7",
  "400": "#2496D5",
  "300": "#3DA7E3",
  "200": "#55BFFD",
  "100": "#A6E0FF",
  "50": { light: "#EAF9FF", dark: "#134563" },
} as const;

export const gradDeco =
  "linear-gradient(135deg,#1787C7 0%,#3DA7E3 55%,#55BFFD 100%)";
export const gradText =
  "linear-gradient(135deg,#0B5F94 0%,#0F6FA8 100%)";

export const focusRing = {
  light: "2px solid #1787C7, 0 0 0 4px #FFFFFF",
  dark: "2px solid #6CC4FF, 0 0 0 4px #0D3753",
} as const;

/**
 * Status palette. Every pair here is verified >=4.5:1 (text on tint) by
 * ../scripts/check-contrast.mjs. Each status also carries an icon
 * (see icons.ts) — color is never the only signal (Section 9.1 rule 6).
 */
export const status = {
  pending: { light: { fg: "#8A5A00", bg: "#FFF4DC" }, dark: { fg: "#F5C451", bg: "#0D3753" } },
  under_process: { light: { fg: "#0F6FA8", bg: "#EAF9FF" }, dark: { fg: "#6CC4FF", bg: "#0D3753" } },
  disposed: { light: { fg: "#0F7B4F", bg: "#E6F6EE" }, dark: { fg: "#5FD3A0", bg: "#0D3753" } },
  transferred: { light: { fg: "#5B4BC4", bg: "#EEEBFF" }, dark: { fg: "#B7ACFF", bg: "#0D3753" } },
  escalated: { light: { fg: "#B3411B", bg: "#FFEBE3" }, dark: { fg: "#FF9B73", bg: "#0D3753" } },
  overdue: { light: { fg: "#B42318", bg: "#FEECEA" }, dark: { fg: "#FF8A80", bg: "#0D3753" } },
  overlap: { light: { fg: "#0B6B7A", bg: "#E3F6F8" }, dark: { fg: "#6FD6E3", bg: "#0D3753" } },
} as const;

export type StatusKey = keyof typeof status;
