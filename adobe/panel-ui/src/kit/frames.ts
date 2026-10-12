// The frame grid: one tile per frame Premiere exported. The frame box follows the frame's aspect (w/h; 9:16 when
// absent or invalid; clamped). A thumbnail is shown only from a local URL (data:image, file:, plugin: or a relative
// path), never from the network. Each tile is a seek button labelled with its timecode, then the timecode (LTR) and a
// verdict chip with its icon.
import { fmt } from "../i18n.ts";
import type { StringKey, Strings } from "../i18n.ts";
import type { QcFrame, QcVerdict } from "../source.ts";
import { auto, esc, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";
import { chip } from "./chip.ts";
import type { ChipTone } from "./chip.ts";

const SAFE_IMG = /^(?:data:image\/|file:|plugin:|(?![a-z][a-z0-9+.-]*:|\/\/)\S)/i;
const VERDICTS: readonly QcVerdict[] = ["pass", "fail", "pending", "media_pending"];
const TONE: Readonly<Record<QcVerdict, ChipTone>> = { pass: "ok", fail: "error", pending: "info", media_pending: "warn" };

/** Height as a percentage of the width (padding-top of the frame box). Default 9:16; clamped to 40..300. */
export function aspectPct(w: unknown, h: unknown): number {
  const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n > 0;
  const pct = ok(w) && ok(h) ? (h / w) * 100 : (1920 / 1080) * 100;
  return Math.round(Math.max(40, Math.min(300, pct)) * 100) / 100;
}

export interface FrameGridOpts {
  t: Strings;
  frames: readonly QcFrame[];
}

function tile(q: QcFrame, t: Strings): string {
  const verdict: QcVerdict = VERDICTS.includes(q.verdict) ? q.verdict : "pending";
  const label = t[`qc.${verdict}` as StringKey];
  const img = q.thumb && SAFE_IMG.test(q.thumb) ? `<img class="kit-frame-img" src="${esc(q.thumb)}" alt="">` : `<span class="kit-frame-empty">${esc(label)}</span>`;
  return (
    `<div class="kit-frame-tile kit-verdict-${verdict}" role="listitem" data-t="${esc(q.t_s)}">` +
    `<button type="button" class="kit-frame kit-focus" data-action="seek" data-t="${esc(q.t_s)}" aria-label="${esc(fmt(t["frame.seek"], { tc: q.tc }))}">` +
    `<span class="kit-frame-box" style="padding-top:${aspectPct(q.w, q.h)}%">${img}</span></button>` +
    `<div class="kit-frame-meta"><span class="kit-frame-tc">${ltr(q.tc)}</span>${chip({ label, tone: TONE[verdict] })}</div>` +
    `<div class="kit-frame-label">${auto(q.label)}</div></div>`
  );
}

export function frameGrid(o: FrameGridOpts): Html {
  return trusted(`<div class="kit-frames" role="list" aria-label="${esc(o.t["section.qc"])}">${o.frames.map((q) => tile(q, o.t)).join("")}</div>`);
}
