// The log drawer: where raw codes go (Addendum B4.4, never on screen elsewhere). A toggle with aria-expanded and a
// chevron (down when open, pointing the reading direction when closed), then the last lines as left-to-right runs with
// a level icon for warnings and errors, the build stamp and "Copy diagnostics".
import { fmt } from "../i18n.ts";
import type { Strings } from "../i18n.ts";
import type { BuildInfo } from "../diagnostics.ts";
import type { LogLine } from "../source.ts";
import { button } from "./button.ts";
import { esc, fmtHtml, ltr, safeId, trusted } from "./html.ts";
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
  const toggle =
    `<button type="button" class="kit-log-toggle kit-focus" data-action="toggle-log" aria-expanded="${o.open ? "true" : "false"}" aria-controls="${id}">` +
    icon(o.open ? "chevron-down" : "chevron-end", { rtl: o.rtl }) +
    `<span class="kit-log-title">${esc(o.t["log.toggle"])}</span><span class="kit-log-count">${fmtHtml(o.t["log.lines"], { n: ltr(o.lines.length) })}</span></button>`;
  const head = `<section class="kit-log" aria-label="${esc(o.t["section.log"])}">${toggle}`;
  if (!o.open) return trusted(`${head}</section>`);
  const max = typeof o.max === "number" && o.max > 0 ? Math.floor(o.max) : 100;
  const lines = o.lines.length
    ? `<ul class="kit-log-lines" id="${id}">${o.lines
        .slice(-max)
        .map((l) => {
          const level = l.level === "warn" || l.level === "error" ? l.level : "info";
          const ic = level === "info" ? "" : `<span class="kit-log-icon">${icon(level)}</span>`;
          return `<li class="kit-log-line kit-log-${level}"><span class="kit-log-ts">${ltr(l.ts)}</span>${ic}<span class="kit-log-text">${ltr(l.text)}</span></li>`;
        })
        .join("")}</ul>`
    : `<p class="kit-log-empty">${esc(o.t["log.empty"])}</p>`;
  const build = o.build ? `<span class="kit-log-build">${ltr(fmt(o.t["log.build"], { version: o.build.version, build: o.build.build }))}</span>` : `<span class="kit-spacer"></span>`;
  const foot = `<div class="kit-log-foot">${build}${button({ label: o.t["actions.diagnostics"], action: "copy-diagnostics", variant: "secondary" })}</div>`;
  return trusted(`${head}${lines}${foot}</section>`);
}
