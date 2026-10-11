// The data the panel shows and the commands it can send. A local engine daemon will implement
// PanelDataSource later; until then MockSource (mock.ts) does. Nothing here talks to a host app.
import type { ActionName } from "./contract.ts";

export type Language = "en" | "ar";

export const STEP_IDS = ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"] as const;
export type StepId = (typeof STEP_IDS)[number];

/** done / running (progress may be set) / waiting (needs the editor) / pending (not reached) / failed */
export type StepStatus = "done" | "running" | "waiting" | "pending" | "failed";

export interface PipelineStep {
  id: StepId;
  state: StepStatus;
  progress?: { n: number; of: number; step?: string } | null;
  elapsed_s?: number | null;
  /** id of the running request; the Cancel button sends it back through PanelDataSource.cancel */
  request_id?: string | null;
}

/** Claude pill = Claude activity from the engine's last signal. Never a login state. */
export type ClaudeState = "active" | "idle" | "unknown";
export type EngineState = "connected" | "offline";
export type HostState = "uxp" | "cep" | "offline";

export interface ConnectionState {
  engine: EngineState;
  claude: ClaudeState;
  host: { state: HostState; /** e.g. "Premiere Pro 26.5.2" */ detail?: string };
}

export interface FlaggedItem {
  kind: "medical" | "religious";
  text: string;
  /** timecode of the statement on the sequence */
  tc: string;
}

export interface Approval {
  summary: string;
  preview_mp4: string | null;
  flagged: FlaggedItem[];
  /** content fingerprint of the plan the editor is looking at; Approve sends it back */
  fingerprint: string;
}

export type QcVerdict = "pass" | "fail" | "pending" | "media_pending";

export interface QcFrame {
  t_s: number;
  tc: string;
  file: string;
  label: string;
  verdict: QcVerdict;
  /** frame size in pixels; the tile follows its aspect. Absent or invalid = 1080 x 1920 (9:16). Reels are 9:16, sometimes 4:5. */
  w?: number;
  h?: number;
  /** optional loadable image URL (data:, file:, plugin: or http(s):) for the tile; the shell fills it */
  thumb?: string | null;
}

export interface LogLine {
  ts: string;
  level: "info" | "warn" | "error";
  text: string;
}

/** Where the current item lives; the panel builds host requests from this. */
export interface ItemContext {
  project_path: string | null;
  sequence_name: string | null;
  folder: string | null;
  out_dir: string | null;
  review_mp4: string | null;
}

export interface PanelState {
  connection: ConnectionState;
  client: string;
  item: string;
  language: Language;
  /** the editor's name for approvals (from whynot-cut.local.md); empty = the panel asks */
  editor_name: string;
  context: ItemContext;
  pipeline: PipelineStep[];
  approval: Approval | null;
  qc: QcFrame[];
  log: LogLine[];
}

/** An action result. Contract hosts answer with the v4 result envelope; approvals answer with this too. */
export interface Result {
  ok: boolean;
  action?: string;
  readback?: object;
  error?: string;
  how?: string;
}

export interface PanelDataSource {
  snapshot(): Promise<PanelState>;
  /** Calls cb on every state change; returns the unsubscribe function. */
  subscribe(cb: (s: PanelState) => void): () => void;
  approve(input: { item: string; editor_name: string; fingerprint: string }): Promise<Result>;
  requestChanges(input: { item: string; editor_name: string; text: string }): Promise<Result>;
  run(action: ActionName, data: object): Promise<Result>;
  /**
   * Rebuild the item's project. The daemon expands this into a full engine rebuild (`reel ppro-build --force`, plus
   * `--replace-edited` when replace_edited is true: the editor confirmed the edited-project warning) and then the
   * complete build_project request to the host. The panel never sends build_project itself.
   */
  rebuild(input: { item: string; project_path: string; replace_edited: boolean }): Promise<Result>;
  cancel(id: string): Promise<void>;
}
