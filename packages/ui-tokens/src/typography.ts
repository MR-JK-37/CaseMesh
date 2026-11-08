/**
 * Section 9.3. Web font choice (Urbanist vs Plus Jakarta Sans) logged in
 * docs/decision-log.md after an eyeball comparison against
 * ui-refrence-iamge.png — defaulting to Plus Jakarta Sans pending that
 * review; both are SIL OFL and self-hostable. Noto Sans Devanagari / Noto
 * Sans Tamil are fallbacks so hi/ta never render in tofu (never shipped to
 * native apps — iOS uses SF Pro / Dynamic Type, Android uses Roboto Flex).
 */
export const fontFamily = {
  web: '"Plus Jakarta Sans", "Noto Sans Devanagari", "Noto Sans Tamil", system-ui, sans-serif',
} as const;

export const scale = [12, 14, 16, 18, 20, 24, 32, 40] as const;
export const weight = { regular: 400, medium: 500, semibold: 600, bold: 700 } as const;
export const lineHeight = { tight: 1.25, normal: 1.5, relaxed: 1.75 } as const;
export const letterSpacing = { tighter: "-0.02em", tight: "-0.01em", normal: "0em", wide: "0.02em" } as const;

