import type { Language } from "./source.ts";
import enTable from "../i18n/en.json" with { type: "json" };
import arTable from "../i18n/ar.json" with { type: "json" };

// The panel's ONE string table lives in i18n/en.json and i18n/ar.json (Addendum B3); this module only loads and types
// it. English is the source table: StringKey is its key set, and the Arabic table is typed against it, so a key missing
// from ar.json does not compile (test/i18n.test.ts also checks both files directly). esbuild bundles both tables into
// the plugin's index.js. The product name stays "WhyNot Cut"; the footer is "Powered by thewhynot.ai" in both languages.
export const EN = enTable;

export type StringKey = keyof typeof EN;
export type Strings = { readonly [K in StringKey]: string };

export const AR: Strings = arTable;

export function stringsFor(lang: Language): Strings {
  return lang === "ar" ? AR : EN;
}

/** Fills {name} placeholders. Unknown placeholders are left as they are. */
export function fmt(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}
