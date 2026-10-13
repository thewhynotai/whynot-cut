// The frame grid: one tile per frame Premiere exported. The frame box follows the frame's aspect (w/h; 9:16 when
// absent or invalid; clamped). A thumbnail is shown only from a local URL (src/media.ts, shared with the panel:
// data:image, file:/// with an empty host, plugin: or a local path), never from the network or a UNC share. Each
// tile is a seek control (<div role="button">, html.ts control()) labelled with its timecode, then the timecode (LTR)
// and a verdict chip with its icon.
import { fmt } from "../i18n.ts";
import type { StringKey, Strings } from "../i18n.ts";
import { aspectPct, isSafeImg } from "../media.ts";
import type { QcFrame, QcVerdict } from "../source.ts";
import { auto, control, esc, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";
import { chip } from "./chip.ts";
import type { ChipTone } from "./chip.ts";

const VERDICTS: readonly QcVerdict[] = ["pass", "fail", "pending", "media_pending"];
const TONE: Readonly<Record<QcVerdict, ChipTone>> = { pass: "ok", fail: "error", pending: "info", media_pending: "warn" };

/** The shared frame-aspect and local-thumbnail helpers (src/media.ts), part of the kit's API. */
export { aspectPct, isSafeImg };

export interface FrameGridOpts {
  t: Strings;
  frames: readonly QcFrame[];
}

function tile(q: QcFrame, t: Strings): string {
  const verdict: QcVerdict = VERDICTS.includes(q.verdict) ? q.verdict : "pending";
  const label = t[`qc.${verdict}` as StringKey];
  const img = isSafeImg(q.thumb) ? `<img class="kit-frame-img" src="${esc(q.thumb)}" alt="">` : `<span class="kit-frame-empty">${esc(label)}</span>`;
  return (
    `<div class="kit-frame-tile kit-verdict-${verdict}" role="listitem" data-t="${esc(q.t_s)}">` +
    control({
      cls: ["kit-frame", "kit-focus"],
      attrs: { "data-action": "seek", "data-t": q.t_s, "aria-label": fmt(t["frame.seek"], { tc: q.tc }) },
      body: `<span class="kit-frame-box" style="padding-top:${aspectPct(q.w, q.h)}%">${img}</span>`,
    }) +
    `<div class="kit-frame-meta"><span class="kit-frame-tc">${ltr(q.tc)}</span>${chip({ label, tone: TONE[verdict] })}</div>` +
    `<div class="kit-frame-label">${auto(q.label)}</div></div>`
  );
}

export function frameGrid(o: FrameGridOpts): Html {
  return trusted(`<div class="kit-frames" role="list" aria-label="${esc(o.t["section.qc"])}">${o.frames.map((q) => tile(q, o.t)).join("")}</div>`);
}
