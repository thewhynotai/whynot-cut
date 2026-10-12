// Icons: inline SVG drawn in currentColor (so an icon takes its text colour from CSS tokens), one 16x16 path each.
// Status icons (ok / warn / error / info) go with every status colour (Addendum B: never colour alone). Directional
// icons have logical names (chevron-start / chevron-end) and are resolved to a physical direction for the language,
// so they point the way the text reads in RTL without relying on a CSS transform.
import type { Strings } from "../i18n.ts";
import { esc, trusted } from "./html.ts";
import type { Html } from "./html.ts";

export type StatusKind = "ok" | "warn" | "error" | "info";
/** Icons that point along the reading direction: whoever draws one must say which direction the panel reads. */
export type DirectionalIcon = "chevron-start" | "chevron-end";
export type IconName = StatusKind | DirectionalIcon | "chevron-down" | "close";
export const isDirectional = (name: unknown): name is DirectionalIcon => name === "chevron-start" || name === "chevron-end";

// Shapes are drawn as one evenodd path: the inner marks (check, cross, bar, dot) are holes in the filled shape.
const PATHS: Readonly<Record<string, string>> = {
  ok: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M4.5 8.2l1.1-1.1 1.5 1.5 3.3-3.3 1.1 1.1-4.4 4.4z",
  error: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M5.2 4.1L8 6.9l2.8-2.8 1.1 1.1L9.1 8l2.8 2.8-1.1 1.1L8 9.1l-2.8 2.8-1.1-1.1L6.9 8 4.1 5.2z",
  info: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M7.1 4h1.8v1.8H7.1z M7.1 7h1.8v5H7.1z",
  warn: "M8 1.2l7.2 13.2H.8z M7.1 5.5h1.8v4.6H7.1z M7.1 11.2h1.8V13H7.1z",
  "chevron-right": "M5.6 2.6L11 8l-5.4 5.4-1.2-1.2L8.6 8 4.4 3.8z",
  "chevron-left": "M10.4 2.6L5 8l5.4 5.4 1.2-1.2L7.4 8l4.2-4.2z",
  "chevron-down": "M2.6 5.6L8 11l5.4-5.4-1.2-1.2L8 8.6 3.8 4.4z",
  close: "M3.8 2.6L8 6.8l4.2-4.2 1.2 1.2L9.2 8l4.2 4.2-1.2 1.2L8 9.2l-4.2 4.2-1.2-1.2L6.8 8 2.6 3.8z",
};

export interface IconOpts {
  /** the panel is right-to-left: chevron-start / chevron-end are mirrored */
  rtl?: boolean;
  /** a standalone icon that means something: role="img" with this label; otherwise aria-hidden (text sits next to it) */
  label?: string;
}

function physical(name: IconName, rtl: boolean): string {
  if (name === "chevron-start") return rtl ? "chevron-right" : "chevron-left";
  if (name === "chevron-end") return rtl ? "chevron-left" : "chevron-right";
  return name;
}

export function icon(name: IconName, opts: IconOpts = {}): Html {
  const shape = physical(name, opts.rtl === true);
  const d = PATHS[shape] ?? PATHS.info!;
  const role = opts.label ? ` role="img"` : "";
  const a11y = opts.label ? ` aria-label="${esc(opts.label)}"` : ` aria-hidden="true"`;
  return trusted(
    `<svg class="kit-icon kit-icon-${esc(shape)}" data-icon="${esc(name)}" viewBox="0 0 16 16" width="16" height="16" fill="currentColor" focusable="false"${role}${a11y}>` +
      `<path fill-rule="evenodd" d="${d}"/></svg>`,
  );
}

/** A status icon labelled for screen readers ("Error", "Warning", ...). */
export function statusIcon(kind: StatusKind, t: Strings): Html {
  return icon(kind, { label: t[`status.${kind}`] });
}

export const STATUS_KINDS: readonly StatusKind[] = ["ok", "warn", "error", "info"];
export const isStatus = (k: unknown): k is StatusKind => typeof k === "string" && (STATUS_KINDS as readonly string[]).includes(k);
