// The waveform frame: the container Hush / Kalam draw their waveform into (data-wave-slot), with a centre line and a
// placeholder until then. No audio logic here. A timeline is never mirrored: the box and the start/end ruler stay
// left-to-right in Arabic too (kit.css), only the placeholder sentence follows the language.
import type { Strings } from "../i18n.ts";
import { esc, ltr, trusted } from "./html.ts";
import type { Html } from "./html.ts";

export interface WaveformOpts {
  t: Strings;
  /** the group's label; default "Audio waveform" */
  label?: string;
  /** timecodes under the start and end of the box */
  start?: string;
  end?: string;
  /** box height in px, clamped to 32..240; default 64 */
  height?: number;
  /** what the tool puts in the box (data-wave-slot) */
  slot?: string;
}

export function waveformFrame(o: WaveformOpts): Html {
  const h = typeof o.height === "number" && Number.isFinite(o.height) ? Math.round(Math.max(32, Math.min(240, o.height))) : 64;
  const slot = o.slot ? ` data-wave-slot="${esc(o.slot)}"` : "";
  const ruler =
    o.start || o.end
      ? `<div class="kit-wave-ruler"><span class="kit-wave-tc">${ltr(o.start ?? "")}</span><span class="kit-spacer"></span><span class="kit-wave-tc">${ltr(o.end ?? "")}</span></div>`
      : "";
  return trusted(
    `<div class="kit-wave" role="group" aria-label="${esc(o.label ?? o.t["wave.label"])}">` +
      `<div class="kit-wave-box"${slot} style="height:${h}px"><div class="kit-wave-mid" aria-hidden="true"></div>` +
      `<div class="kit-wave-placeholder">${esc(o.t["wave.placeholder"])}</div></div>${ruler}</div>`,
  );
}
