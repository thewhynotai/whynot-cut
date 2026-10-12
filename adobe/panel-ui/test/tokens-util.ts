// Helpers shared by the token and contrast tests (not a test file itself).
import { readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const PANEL_UI = join(dirname(fileURLToPath(import.meta.url)), "..");
export const ADOBE = join(PANEL_UI, "..");
export const REPO = join(ADOBE, "..");
export const TOKENS = join(REPO, "brand", "tokens.css");

/** --twn-name -> value, from a :root block (comments removed). */
export function tokenMap(css: string): Map<string, string> {
  const flat = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const out = new Map<string, string>();
  for (const m of flat.matchAll(/(--twn-[a-z0-9-]+)\s*:\s*([^;}]+)[;}]/gi)) out.set(m[1]!, m[2]!.trim());
  return out;
}

/** Canonical form of a colour literal: lower case, #rgb -> #rrggbb, rgba() without spaces and with ".08" not "0.08". */
export function canon(c: string): string {
  let s = c.toLowerCase().replace(/\s+/g, "");
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(s);
  if (short) s = `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`;
  return s.replace(/([(,])0\./g, "$1.");
}

const COLOUR = /#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)|hsla?\([^)]*\)/g;
export const coloursIn = (text: string): string[] => [...text.matchAll(COLOUR)].map((m) => m[0]);

/** Files under dir (sorted), skipping dependency, build-output and upstream-import folders. */
export function walk(dir: string, keep: (p: string) => boolean): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (["node_modules", "build", "out", "tools", ".git"].includes(name)) continue;
      out.push(...walk(full, keep));
    } else if (keep(full)) out.push(full);
  }
  return out;
}

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

/** #rrggbb / #rgb / rgb() / rgba() -> {r,g,b,a}. */
export function parseCss(c: string): Rgb & { a: number } {
  const s = canon(c);
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/.exec(s);
  if (hex) return { r: parseInt(hex[1]!, 16), g: parseInt(hex[2]!, 16), b: parseInt(hex[3]!, 16), a: 1 };
  const fn = /^rgba?\(([\d.]+),([\d.]+),([\d.]+)(?:,([\d.]+))?\)$/.exec(s);
  if (fn) return { r: Number(fn[1]), g: Number(fn[2]), b: Number(fn[3]), a: fn[4] === undefined ? 1 : Number(fn[4]) };
  throw new Error(`not a colour: ${c}`);
}

/** A translucent colour composited over an opaque one (what the eye sees). */
export function over(top: Rgb & { a: number }, under: Rgb): Rgb {
  const mix = (t: number, u: number) => Math.round(t * top.a + u * (1 - top.a));
  return { r: mix(top.r, under.r), g: mix(top.g, under.g), b: mix(top.b, under.b) };
}

/** WCAG 2.x relative luminance and contrast ratio. */
export function luminance({ r, g, b }: Rgb): number {
  const lin = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}
