// Contract v4 types used by the panel. Hand-written from whynot-cut/engine/reel/contract/*.schema.json;
// the protocol number and the action list are read from protocol.json (one source) and a test keeps them equal.
import protocol from "../../../whynot-cut/engine/reel/contract/protocol.json" with { type: "json" };

export const PROTOCOL: number = protocol.protocol;

export const ACTION_NAMES = [
  "ping",
  "status",
  "probe",
  "build_project",
  "export_frames",
  "close_project_path",
  "clip_components",
  "open_project",
  "set_player_position",
  "render_review",
  "ae_build_motion",
  "ae_readback",
  "ae_render",
  "ae_fonts",
  "ae_probe_text",
] as const;
export type ActionName = (typeof ACTION_NAMES)[number];

// Compile-time guard: if protocol.json gains or loses an action this stops compiling.
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
export const ACTION_LIST_MATCHES_PROTOCOL: Same<ActionName, keyof typeof protocol.actions> = true;

// ---- envelopes ----

export interface RequestEnvelope<A extends ActionName = ActionName, D = object> {
  protocol: number;
  id: string;
  action: A;
  data: D;
  expires_at: string;
}

/** One shape per outcome (result.schema.json): ok:true needs a readback and carries no error; ok:false needs an error,
 *  with how to fix it and, sometimes, a partial readback. */
export type ResultEnvelope<R = object> =
  | { ok: true; action: ActionName; readback: R; error?: never; how?: string; id?: string }
  | { ok: false; action: ActionName; readback?: object; error: string; how?: string; id?: string };

export interface ProgressEvent {
  event: "progress";
  id: string;
  action: ActionName;
  step: string;
  n?: number;
  of?: number;
  elapsed_s?: number;
}

// ---- per-action data / readback (only the actions the panel uses) ----

export interface StatusReadback {
  host: "premiere" | "aftereffects";
  hostVersion: string;
  bundle: string;
  protocol: number;
  busy: boolean;
  project: string | null;
}

/** Premiere ping (ping.schema.json $defs/premiere). `build` is optional: UXP has no source for it (version comes from uxp.host.version). */
export interface PingPremiereReadback { version: string; build?: string; project: string | null; projects_open: number | null }

export interface OpenProjectData { path: string }
export interface OpenProjectReadback { opened: boolean; project: string | null }

export interface ExportFramesData {
  sequence_name: string;
  times: number[];
  out_dir: string;
  project_path?: string | null;
}
/** `tc` is optional: UXP exports by TickTime and has no timecode string. `called`: the export call reported success
 *  (UXP: exportSequenceFrame returned true); a false return is the `{ t, error }` form. */
export type ExportedFrame = { t: number; tc?: string; file: string; called: boolean } | { t: number; error: string };
export interface ExportFramesReadback { frames: ExportedFrame[] }

export interface RenderReviewData { sequence_name: string; out_path: string; preset_path?: string }
export interface RenderReviewReadback { started: boolean; out_path: string; mode: string }

export interface SetPlayerPositionData { sequence_name: string; t_s: number }
export interface SetPlayerPositionReadback { position_s: number }

// build_project data, mirrored from build_project.schema.json $defs/data. The panel never builds one: it asks the
// engine to rebuild (PanelDataSource.rebuild) and the engine sends this to the host. test/mock.test.ts checks the
// property names and the required set against the schema.
export interface BuildGraphic {
  id: string;
  png: string;
  track_index: number;
  anim: "flash" | "text_pop" | "bar_sweep" | "slide" | "push" | "card" | "fade";
  start_s: number;
  end_s: number;
  fade_in_s?: number;
  fade_out_s?: number;
  peak?: number;
  delay_f?: number;
  sweep_f?: number;
}
export interface BuildMarker { t: number; name: string; comment: string }
export interface BuildSettings {
  previewCodec?: string;
  previewFrameWidth?: number;
  previewFrameHeight?: number;
  maximumBitDepth?: boolean;
  maximumRenderQuality?: boolean;
  compositeLinearColor?: boolean;
}
export interface BuildProjectData {
  project_path: string;
  overwrite_existing?: boolean;
  xml_path: string;
  sequence_name: string;
  settings: BuildSettings;
  graphics: BuildGraphic[];
  srt_path?: string;
  native_caption_track?: boolean;
  markers: BuildMarker[];
  track_names: { video: string[]; audio: string[] };
  blur_v1_clips?: number[];
  sharpen_v1?: { amount: number; grain: number } | null;
  duration_s?: number;
}
export interface BuildTrack { i: number; name: string; clips: number }
export interface BuildProjectReadback {
  project: string;
  saved: boolean;
  settings_after: {
    previewCodec: string;
    videoFrameWidth: number;
    videoFrameHeight: number;
    videoFrameRate: { seconds: number; ticks: string };
    compositeLinearColor: boolean;
    maximumBitDepth: boolean;
    maximumRenderQuality: boolean;
    [key: string]: unknown;
  };
  placed: { id: string; track: number; start: number; end: number; anim: string }[];
  sharpened: { clip: number; ok: boolean; amount?: number; grain?: number }[];
  tracks: { video: BuildTrack[]; audio: BuildTrack[] };
  [key: string]: unknown;
}
