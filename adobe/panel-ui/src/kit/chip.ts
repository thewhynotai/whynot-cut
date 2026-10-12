// Pills / chips: small 999 px labels. Status tones (ok, warn, error, info) always carry their icon. LTR chips
// (timecodes, file names, commands) are mono <bdi dir="ltr"> runs. Chips sit in a .kit-chips flex row, never inside a
// sentence (UXP draws inline-flex over running text).
import { esc, join, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";
import { icon, isStatus } from "./icons.ts";

export type ChipTone = "neutral" | "ok" | "warn" | "error" | "info" | "accent";
const TONES: readonly ChipTone[] = ["neutral", "ok", "warn", "error", "info", "accent"];

export interface ChipOpts {
  label: string;
  tone?: ChipTone;
  /** a left-to-right token in the mono face (timecode, file name, command) */
  ltr?: boolean;
}

export function chip(o: ChipOpts): Html {
  const tone: ChipTone = o.tone && TONES.includes(o.tone) ? o.tone : "neutral";
  const ic = isStatus(tone) ? icon(tone) : "";
  const text = o.ltr ? ltr(o.label) : esc(o.label);
  return trusted(`<span class="kit-chip kit-chip-${tone}${o.ltr ? " kit-chip-mono" : ""}">${ic}<span class="kit-chip-text">${text}</span></span>`);
}

export const chips = (list: readonly Html[]): Html => trusted(`<div class="kit-chips">${join(list)}</div>`);
