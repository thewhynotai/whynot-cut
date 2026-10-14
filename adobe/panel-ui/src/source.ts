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

/**
 * The Claude pill (Addendum C1.6, ecosystem.md 3.5c): the engine's local probe of the editor's own Claude CLI and session
 * (installed? signed in? WhyNot Cut plugin up to date? a session working on the item, or waiting for the editor?). It is
 * a probe of the editor's own login, never a login WhyNot Cut offers. "unknown" = not probed yet: the daemon reports it
 * until the T6.2b probe exists. "active" / "idle" are the round-1 values: no daemon sends them; they stay only until the
 * renderer maps the new states.
 */
export type ClaudeState =
  | "not_installed"
  | "signed_out"
  | "plugin_outdated"
  | "ready"
  | "working"
  | "waiting"
  | "unknown"
  | "active"
  | "idle";
export const CLAUDE_STATES: readonly ClaudeState[] = [
  "not_installed",
  "signed_out",
  "plugin_outdated",
  "ready",
  "working",
  "waiting",
  "unknown",
  "active",
  "idle",
];
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

/** A journaled command's state (reel serve's job journal, serve/jobs.py; Addendum G2 H1). */
export type JobState = "received" | "queued" | "claimed" | "done" | "failed" | "interrupted";
export const JOB_STATES: readonly JobState[] = ["received", "queued", "claimed", "done", "failed", "interrupted"];

/** One command in the daemon's job journal (docs/adobe/eng-data-contract.md 2.6). After a reconnect the panel finds its
 *  request id here and re-sends the same command: still running = it attaches, settled = the stored result is replayed. */
export interface JobSummary {
  request_id: string;
  action: ActionName;
  state: JobState;
  submitted_at: string;
  updated_at: string;
  /** the item the job was for, when the engine knows it */
  item?: string;
  /** the stored result's outcome (settled jobs only); never the host's text */
  result?: { ok: boolean; code?: string; n?: number; of?: number };
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
  /** the daemon's newest journaled commands, newest first (absent from an older daemon and from the mock) */
  jobs?: JobSummary[];
}

/** An action result. Contract hosts answer with the v4 result envelope; approvals answer with this too. */
export interface Result {
  ok: boolean;
  action?: string;
  readback?: object;
  error?: string;
  how?: string;
  /** why it failed, as a code the panel can localize (a session error code, timeout, lost, too_large, NOT_YET, or the
   *  link's diagnosis code): the panel shows its own sentence for it when the engine's words hold a command */
  code?: string;
}

export interface PanelDataSource {
  snapshot(): Promise<PanelState>;
  /** Calls cb on every state change; returns the unsubscribe function. */
  subscribe(cb: (s: PanelState) => void): () => void;
  approve(input: { item: string; editor_name: string; fingerprint: string }): Promise<Result>;
  requestChanges(input: { item: string; editor_name: string; text: string }): Promise<Result>;
  run(action: ActionName, data: object): Promise<Result>;
  /**
   * Rebuild the item's project. The engine expands this into a full rebuild (`--replace-edited` when replace_edited is
   * true: the editor confirmed the edited-project warning) and then the complete build_project request to the host. The
   * engine finds the project from the item; project_path is optional (C2.4). The panel never sends build_project itself.
   */
  rebuild(input: { item: string; project_path?: string; replace_edited: boolean }): Promise<Result>;
  cancel(id: string): Promise<void>;
}
