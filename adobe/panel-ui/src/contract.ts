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

export interface ResultEnvelope<R = object> {
  ok: boolean;
  action: ActionName;
  readback?: R;
  error?: string;
  how?: string;
  id?: string;
}

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

export interface OpenProjectData { path: string }
export interface OpenProjectReadback { opened: boolean; project: string | null }

export interface ExportFramesData {
  sequence_name: string;
  times: number[];
  out_dir: string;
  project_path?: string | null;
}
export type ExportedFrame = { t: number; tc: string; file: string; called: boolean } | { t: number; error: string };
export interface ExportFramesReadback { frames: ExportedFrame[] }

export interface RenderReviewData { sequence_name: string; out_path: string; preset_path?: string }
export interface RenderReviewReadback { started: boolean; out_path: string; mode: string }

export interface SetPlayerPositionData { sequence_name: string; t_s: number }
export interface SetPlayerPositionReadback { position_s: number }

// The panel sends only the fields it knows for a rebuild; the engine daemon adds the plan files
// (xml_path, graphics, settings, ...) before it reaches the host.
export interface BuildProjectData {
  project_path: string;
  overwrite_existing?: boolean;
  xml_path?: string;
  sequence_name?: string;
}
