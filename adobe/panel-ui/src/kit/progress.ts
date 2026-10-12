// Progress you can read (Addendum B4.3): a plain-language status ("Building your sequence…"), "23 of 47" as
// left-to-right numbers, the gradient bar, elapsed m:ss and Cancel (a secondary button). The bar is a flex row, so in
// Arabic it fills from the right. Without a count the bar is indeterminate (no aria-valuenow).
import type { Strings } from "../i18n.ts";
import { button } from "./button.ts";
import { clockOf, esc, fmtHtml, ltr, trusted } from "./html.ts";
import type { DataAttrs, Html } from "./html.ts";

export interface ProgressOpts {
  t: Strings;
  /** what is happening, in plain words (translated) */
  status: string;
  n?: number | null;
  of?: number | null;
  elapsedS?: number | null;
  /** shows Cancel; the shell sends the request id back */
  cancel?: { action: string; data?: DataAttrs } | null;
}

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function progress(o: ProgressOpts): Html {
  const n = num(o.n) ? o.n : 0;
  const of = num(o.of) ? o.of : 0;
  const counted = num(o.n) && of > 0;
  const pct = counted ? Math.max(0, Math.min(100, Math.round((n / of) * 100))) : null;
  const count = counted ? `<span class="kit-progress-count">${fmtHtml(o.t["pipeline.progress"], { n: ltr(n), of: ltr(of) })}</span>` : "";
  const bar =
    pct !== null
      ? `<div class="kit-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-valuetext="${esc(n)}/${esc(of)}"><div class="kit-fill" style="width:${pct}%"></div></div>`
      : `<div class="kit-track kit-track-indeterminate" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="kit-fill" style="width:30%"></div></div>`;
  const elapsed = num(o.elapsedS)
    ? `<span class="kit-meta"><span class="kit-meta-k">${esc(o.t["pipeline.elapsed"])}</span><span class="kit-meta-v">${ltr(clockOf(o.elapsedS))}</span></span>`
    : "";
  const cancel = o.cancel ? button({ label: o.t["pipeline.cancel"], action: o.cancel.action, data: o.cancel.data, variant: "secondary" }) : "";
  const foot = elapsed || cancel ? `<div class="kit-progress-foot">${elapsed}<span class="kit-spacer"></span>${cancel}</div>` : "";
  return trusted(
    `<div class="kit-progress" role="group" aria-label="${esc(o.status)}">` +
      `<div class="kit-progress-head"><span class="kit-progress-status">${esc(o.status)}</span>${count}</div>` +
      bar +
      foot +
      `</div>`,
  );
}
