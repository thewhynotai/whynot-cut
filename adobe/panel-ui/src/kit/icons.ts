// Icons: inline SVG, one 16x16 path each. UXP (spike 0.1.7 CSS lab, docs/adobe/uxp-parity.md) paints NOTHING for
// fill="currentColor", for an explicit fill attribute or for an <img> of the svg: only a CSS fill on the svg (or its
// path) paints. So an icon carries NO fill attribute; it carries an ink class (kit-ink-<tone>) and kit.css sets the
// fill from the tokens. The ink is the icon's own status colour by default (ok / warn / error / info; pending and the
// non-status shapes are muted); whoever puts an icon on a coloured fill (a button, a step dot) names the ink.
// Status icons (ok / warn / error / info) go with every status colour (Addendum B: never colour alone). Directional
// icons have logical names (chevron-start / chevron-end) and are resolved to a physical direction for the language,
// so they point the way the text reads in RTL without relying on a CSS transform.
import type { Strings } from "../i18n.ts";
import { esc, trusted } from "./html.ts";
import type { Html } from "./html.ts";

export type StatusKind = "ok" | "warn" | "error" | "info";
/** Icons that point along the reading direction: whoever draws one must say which direction the panel reads. */
export type DirectionalIcon = "chevron-start" | "chevron-end";
/** "pending": an open ring (not checked yet), for the checklist's rows that are still being probed. */
export type IconName = StatusKind | DirectionalIcon | "chevron-down" | "close" | "pending";
export const isDirectional = (name: unknown): name is DirectionalIcon => name === "chevron-start" || name === "chevron-end";

// Shapes are drawn as one evenodd path: the inner marks (check, cross, bar, dot) are holes in the filled shape.
const PATHS: Readonly<Record<string, string>> = {
  ok: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M4.5 8.2l1.1-1.1 1.5 1.5 3.3-3.3 1.1 1.1-4.4 4.4z",
  error: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M5.2 4.1L8 6.9l2.8-2.8 1.1 1.1L9.1 8l2.8 2.8-1.1 1.1L8 9.1l-2.8 2.8-1.1-1.1L6.9 8 4.1 5.2z",
  info: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M7.1 4h1.8v1.8H7.1z M7.1 7h1.8v5H7.1z",
  pending: "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M8 2.8a5.2 5.2 0 1 0 0 10.4A5.2 5.2 0 1 0 8 2.8z",
  warn: "M8 1.2l7.2 13.2H.8z M7.1 5.5h1.8v4.6H7.1z M7.1 11.2h1.8V13H7.1z",
  "chevron-right": "M5.6 2.6L11 8l-5.4 5.4-1.2-1.2L8.6 8 4.4 3.8z",
  "chevron-left": "M10.4 2.6L5 8l5.4 5.4 1.2-1.2L7.4 8l4.2-4.2z",
  "chevron-down": "M2.6 5.6L8 11l5.4-5.4-1.2-1.2L8 8.6 3.8 4.4z",
  close: "M3.8 2.6L8 6.8l4.2-4.2 1.2 1.2L9.2 8l4.2 4.2-1.2 1.2L8 9.2l-4.2 4.2-1.2-1.2L6.8 8 2.6 3.8z",
};

/** The colour an icon is filled with (kit.css .kit-ink-<tone>, each a token). */
export type IconInk = "ok" | "warn" | "error" | "info" | "accent" | "text" | "muted" | "on-primary" | "on-ok" | "on-error" | "on-accent";
export const ICON_INKS: readonly IconInk[] = ["ok", "warn", "error", "info", "accent", "text", "muted", "on-primary", "on-ok", "on-error", "on-accent"];

/** The default ink: a status shape in its own status colour; pending and the other shapes muted. */
export function defaultInk(name: IconName): IconInk {
  return name === "ok" || name === "warn" || name === "error" || name === "info" ? name : "muted";
}

export interface IconOpts {
  /** the panel is right-to-left: chevron-start / chevron-end are mirrored */
  rtl?: boolean;
  /** a standalone icon that means something: role="img" with this label; otherwise aria-hidden (text sits next to it) */
  label?: string;
  /** the fill colour (default: defaultInk(name)) */
  ink?: IconInk;
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
  const ink: IconInk = opts.ink && ICON_INKS.includes(opts.ink) ? opts.ink : defaultInk(name);
  return trusted(
    `<svg class="kit-icon kit-icon-${esc(shape)} kit-ink-${ink}" data-icon="${esc(name)}" viewBox="0 0 16 16" width="16" height="16" focusable="false"${role}${a11y}>` +
      `<path fill-rule="evenodd" d="${d}"/></svg>`,
  );
}

/** A status icon labelled for screen readers ("Error", "Warning", ...). */
export function statusIcon(kind: StatusKind, t: Strings, ink?: IconInk): Html {
  return icon(kind, { label: t[`status.${kind}`], ...(ink ? { ink } : {}) });
}

export const STATUS_KINDS: readonly StatusKind[] = ["ok", "warn", "error", "info"];
export const isStatus = (k: unknown): k is StatusKind => typeof k === "string" && (STATUS_KINDS as readonly string[]).includes(k);
