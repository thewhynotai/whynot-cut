// clip_components (clip_components.schema.json): read-only, the components on one clip with their match names and
// param values, so `reel` can see Premiere's real names per version. Components are reported by match name (parity
// K0: Opacity comes before Motion, display names are not unique across generations); params by display name (some
// are blank or repeated: reported as they are). Values: UXP wraps them ({value: x}, from getStartValue); numbers,
// strings and booleans pass through, arrays use the CEP "x,y" form, other objects are JSON, unreadable ones are '?'.
import { findSequence, getPpro, requireActiveProject } from "./premiere.ts";
import { OpError } from "./types.ts";
import type { Op } from "./types.ts";

export interface ClipComponentsData { sequence_name: string; track?: number; clip?: number; audio?: boolean }
export interface ClipProp { name: string; value: unknown }
export interface ClipComponent { name: string; match: string; props: ClipProp[] }
export interface ClipComponentsReadback { clip: string; components: ClipComponent[] }

/** The plain value inside UXP's {value: ...} wrappers (a Keyframe's `value` is itself {value: x}). */
function unwrap(v: unknown): unknown {
  for (let i = 0; i < 3 && v !== null && typeof v === "object" && !Array.isArray(v) && "value" in v; i++) {
    v = (v as { value: unknown }).value;
  }
  return v;
}

export function propValue(raw: unknown): unknown {
  const v = unwrap(raw);
  if (v === null || typeof v === "number" || typeof v === "string" || typeof v === "boolean") return v;
  if (Array.isArray(v)) return v.map((x) => String(x)).join(",");
  if (typeof v === "object") {
    const o = v as { x?: unknown; y?: unknown };
    if (typeof o.x === "number" && typeof o.y === "number" && Object.keys(v).length === 2) return `${o.x},${o.y}`;
    try {
      return JSON.stringify(v) ?? "?";
    } catch {
      return "?";
    }
  }
  return "?";
}

export const clipComponents: Op<ClipComponentsData, ClipComponentsReadback> = {
  action: "clip_components",
  exclusive: true,
  async run(data, ctx) {
    const ppro = getPpro(ctx.env);
    const project = await requireActiveProject(ppro);
    const seq = await findSequence(project, data.sequence_name);
    const trackIndex = data.track ?? 0;
    const clipIndex = data.clip ?? 0;
    const kind = data.audio ? "audio" : "video";
    const count = data.audio ? await seq.getAudioTrackCount() : await seq.getVideoTrackCount();
    if (trackIndex >= count) {
      throw new OpError(`There is no ${kind} track ${trackIndex + 1} in "${seq.name}" (it has ${count}).`, "Check the track number (0 is the first track).");
    }
    const track = data.audio ? await seq.getAudioTrack(trackIndex) : await seq.getVideoTrack(trackIndex);
    const clips = track.getTrackItems(ppro.Constants.TrackItemType.CLIP, false) ?? [];
    const clip = clips[clipIndex];
    if (!clip) {
      throw new OpError(`There is no clip ${clipIndex + 1} on ${kind} track ${trackIndex + 1} of "${seq.name}" (it has ${clips.length}).`, "Check the clip number (0 is the first clip).");
    }
    const chain = await clip.getComponentChain();
    const components: ClipComponent[] = [];
    for (let i = 0; i < chain.getComponentCount(); i++) {
      ctx.throwIfCancelled();
      const comp = chain.getComponentAtIndex(i);
      const props: ClipProp[] = [];
      for (let j = 0; j < comp.getParamCount(); j++) {
        let name = "?";
        let value: unknown = "?";
        try {
          const param = comp.getParam(j);
          name = String(param.displayName ?? "");
          value = propValue(await param.getStartValue());
        } catch {
          // unreadable param: name (when known) and '?'
        }
        props.push({ name, value });
      }
      components.push({ name: String(await comp.getDisplayName()), match: String(await comp.getMatchName()), props });
    }
    return { clip: String(await clip.getName()), components };
  },
};
