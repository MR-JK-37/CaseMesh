import en from "./locales/en.json";
import hi from "./locales/hi.json";
import ta from "./locales/ta.json";

export const locales = { en, hi, ta } as const;
export type Locale = keyof typeof locales;
export type MessageKey = keyof typeof en;

export function hasAllKeys(locale: Locale): boolean {
  const keys = Object.keys(en) as MessageKey[];
  return keys.every((key) => key in locales[locale]);
}
