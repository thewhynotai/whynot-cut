// The log drawer: where raw codes go (Addendum B4.4, never on screen elsewhere). A toggle with aria-expanded and a
// chevron (down when open, pointing the reading direction when closed); aria-controls only while open (it names the
// lines list or the empty line, which exist only then). The lines are machine output: a dir="ltr" block, left-aligned in
// both languages, with a level icon for warnings and errors; the drawer's own label stays localized. Then the build
// stamp (each token a nowrap run, so it wraps only between tokens) and "Copy diagnostics". The toggle is a kit control
// (<div role="button">, html.ts control()); its title and count carry kit-gap-s (flex drops the whitespace).
import { fmt } from "../i18n.ts";
import type { Strings } from "../i18n.ts";
import type { BuildInfo } from "../diagnostics.ts";
import type { LogLine } from "../source.ts";
import { button } from "./button.ts";
import { control, esc, fmtHtml, ltr, safeId, trusted } from "./html.ts";
import type { Html } from "./html.ts";
import { icon } from "./icons.ts";

export interface LogDrawerOpts {
  t: Strings;
  open: boolean;
  lines: readonly LogLine[];
  rtl: boolean;
  build?: BuildInfo | null;
  /** id of the lines list (aria-controls); default "kit-log-lines" */
  id?: string;
  /** how many of the last lines to show; default 100 */
  max?: number;
}

export function logDrawer(o: LogDrawerOpts): Html {
  const id = safeId(o.id ?? "kit-log-lines");
  const toggle = control({
    cls: ["kit-log-toggle", "kit-focus"],
    attrs: { "data-action": "toggle-log", "aria-expanded": String(o.open), "aria-controls": o.open && id },
    body:
      icon(o.open ? "chevron-down" : "chevron-end", { rtl: o.rtl }) +
      `<span class="kit-log-title kit-gap-s">${esc(o.t["log.toggle"])}</span><span class="kit-log-count kit-gap-s">${fmtHtml(o.t["log.lines"], { n: ltr(o.lines.length) })}</span>`,
  });
  const head = `<section class="kit-log" aria-label="${esc(o.t["section.log"])}">${toggle}`;
  if (!o.open) return trusted(`${head}</section>`);
  const max = typeof o.max === "number" && o.max > 0 ? Math.floor(o.max) : 100;
  const lines = o.lines.length
    ? `<ul class="kit-log-lines" id="${id}" dir="ltr">${o.lines
        .slice(-max)
        .map((l) => {
          const level = l.level === "warn" || l.level === "error" ? l.level : "info";
          const ic = level === "info" ? "" : `<span class="kit-log-icon">${icon(level)}</span>`;
          return `<li class="kit-log-line kit-log-${level}"><span class="kit-log-ts">${ltr(l.ts)}</span>${ic}<span class="kit-log-text">${ltr(l.text)}</span></li>`;
        })
        .join("")}</ul>`
    : `<p class="kit-log-empty" id="${id}">${esc(o.t["log.empty"])}</p>`;
  const build = o.build ? `<span class="kit-log-build">${buildStamp(o.t, o.build)}</span>` : `<span class="kit-spacer"></span>`;
  const foot = `<div class="kit-log-foot">${build}${button({ label: o.t["actions.diagnostics"], action: "copy-diagnostics", variant: "secondary" })}</div>`;
  return trusted(`${head}${lines}${foot}</section>`);
}

/** The build stamp: a left-to-right flex row (kit.css .kit-stamp, direction ltr in both languages) of nowrap tokens,
 *  so it wraps only between tokens, never inside one (a version, a commit, a timestamp). The product name is one token.
 *  The space between tokens is kit-gap-s on every token after the first: UXP (and flexbox) drop literal whitespace
 *  between flex children, and only a physical margin shows (spike 0.1.7). */
export function buildStamp(t: Strings, b: BuildInfo): Html {
  const product = t["product.name"];
  const text = fmt(t["log.build"], { version: b.version, build: b.build }).split(product).join(product.replace(/ /g, " "));
  const tokens = text.split(/ +/).filter((w) => w !== "");
  return trusted(`<span class="kit-stamp" dir="ltr">${tokens.map((w, i) => `<span class="kit-nowrap${i ? " kit-gap-s" : ""}">${esc(w)}</span>`).join("")}</span>`);
}
