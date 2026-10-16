// The daemon-link session messages: every WebSocket message between the local engine daemon (`reel serve`) and its clients
// (Premiere UXP panel, After Effects CEP panel, the `reel` CLI). Hand-written mirror of
// whynot-cut/engine/reel/contract/session.schema.json; test/session.test.ts validates typed samples (and every MockSource
// state) against the schema with ajv, and the engine's SessionContractTests compare the PanelState keys with source.ts.
// Types only (plus two name lists the test checks): it changes no panel behaviour. PanelState is source.ts's, not a copy.
import type { ActionName, ProgressEvent, RequestEnvelope, ResultEnvelope } from "./contract.ts";
import type { PanelDataSource, PanelState } from "./source.ts";
import type { PerfMark } from "./perf.ts";

export const SESSION_PROTOCOL = 4 as const;

/** The `type` of every message, in the order of the schema's `message` oneOf. */
export const SESSION_MESSAGE_TYPES = [
  "hello",
  "welcome",
  "command",
  "result",
  "progress",
  "state",
  "approve",
  "request_changes",
  "rebuild",
  "snapshot",
  "cancel",
  "reply",
  "error",
  "perf",
] as const;
export type SessionMessageType = (typeof SESSION_MESSAGE_TYPES)[number];

export const SESSION_ERROR_CODES = ["auth", "origin", "host", "too_large", "rate", "schema", "unknown_type", "no_route", "timeout", "internal"] as const;
export type SessionErrorCode = (typeof SESSION_ERROR_CODES)[number];

export type ClientKind = "uxp" | "cep" | "cli" | "panel";

/** client -> daemon, the FIRST message of a connection. `token` comes from <engine home>/bridge/engine.json, never from a URL. */
export interface HelloMessage {
  type: "hello";
  token: string;
  client: {
    kind: ClientKind;
    version: string;
    /** the panel package's build id (C1.8 / C2.3): UTC YYYYMMDDTHHMMSSZ, the same id as the .ccx's build.json `build`;
     *  the daemon compares it with the plugin's expected.json (1-64 characters) */
    build?: string;
    /** the Adobe host the client runs in; absent for the CLI */
    host?: "premiere" | "aftereffects";
    hostVersion?: string;
    protocol: 4;
    /** the actions this client implements; routing uses them */
    capabilities: ActionName[];
  };
}

/** Is the connecting panel the build the plugin expects (welcome.update.panel): ok = the same id, stale = an older id or
 *  any other differing value (restart Premiere to load the update), newer = a newer id than the plugin's, unknown = no
 *  build, no expected.json or a malformed value. */
export const PANEL_UPDATE_STATES = ["ok", "stale", "newer", "unknown"] as const;
export type PanelUpdate = (typeof PANEL_UPDATE_STATES)[number];

/** What a daemon does beyond protocol 4's core (G2 H3): perf = it takes the panel's perf batches; push = it pushes a
 *  state when the engine state changes. */
export const DAEMON_FEATURES = ["perf", "push"] as const;
export type DaemonFeature = (typeof DAEMON_FEATURES)[number];

/** daemon -> client, the answer to an accepted hello. `update` is absent from a daemon older than C2.3, `features` from
 *  one older than G2 H3 (the panel then sends no perf batch). */
export interface WelcomeMessage {
  type: "welcome";
  session_id: string;
  protocol: 4;
  daemon_version: string;
  update?: { panel: PanelUpdate };
  features?: DaemonFeature[];
}

/** A v4 request (client -> daemon, or daemon -> host client). `request.data` is checked by the action's schema. */
export interface CommandMessage {
  type: "command";
  request: RequestEnvelope;
  context?: { root?: string; profile?: string };
}

export interface ResultMessage {
  type: "result";
  result: ResultEnvelope;
}

export interface ProgressMessage {
  type: "progress";
  progress: ProgressEvent;
}

/** daemon -> panel: pushed on every change and as the answer to a snapshot (`id` echoes it). */
export interface StateMessage {
  type: "state";
  state: PanelState;
  id?: string;
}

// Panel intents: one per PanelDataSource method (source.ts). `id` correlates the reply.
export interface ApproveMessage {
  type: "approve";
  id: string;
  item: string;
  editor_name: string;
  fingerprint: string;
}

export interface RequestChangesMessage {
  type: "request_changes";
  id: string;
  item: string;
  editor_name: string;
  text: string;
}

/** The engine finds the project from the item; project_path is optional (C2.4), a panel that sends it keeps working. */
export interface RebuildMessage {
  type: "rebuild";
  id: string;
  item: string;
  project_path?: string;
  replace_edited: boolean;
}

export interface SnapshotMessage {
  type: "snapshot";
  id?: string;
}

/** `id` is the id of the running request to cancel (PipelineStep.request_id). */
export interface CancelMessage {
  type: "cancel";
  id: string;
}

/** daemon -> panel: the answer to approve / request_changes / rebuild (the panel's Result). ok:true carries no error. */
export type ReplyMessage =
  | { type: "reply"; id: string; intent: ReplyIntent; ok: true; readback?: object; error?: never; how?: string }
  | { type: "reply"; id: string; intent: ReplyIntent; ok: false; readback?: object; error: string; how?: string };
export type ReplyIntent = "approve" | "request_changes" | "rebuild";

/** daemon -> client: a refusal or failure that is not a command result. `id` is the offending message's id, when it had one. */
export interface ErrorMessage {
  type: "error";
  code: SessionErrorCode;
  message: string;
  id?: string;
}

/** panel -> daemon (G2 H3): a batch of perf marks (src/perf.ts), 1-50, only to a daemon whose welcome lists "perf".
 *  The daemon appends them to perf.jsonl and answers nothing. */
export interface PerfMessage {
  type: "perf";
  marks: PerfMark[];
}

export type SessionMessage =
  | HelloMessage
  | WelcomeMessage
  | CommandMessage
  | ResultMessage
  | ProgressMessage
  | StateMessage
  | ApproveMessage
  | RequestChangesMessage
  | RebuildMessage
  | SnapshotMessage
  | CancelMessage
  | ReplyMessage
  | ErrorMessage
  | PerfMessage;

// Compile-time guards: the union covers exactly the listed types, and the panel intents are the PanelDataSource inputs.
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
export const SESSION_TYPES_MATCH: Same<SessionMessage["type"], SessionMessageType> = true;
export const SESSION_ERROR_CODES_MATCH: Same<ErrorMessage["code"], SessionErrorCode> = true;
type Input<K extends "approve" | "requestChanges" | "rebuild"> = Parameters<PanelDataSource[K]>[0];
export const APPROVE_MATCHES_SOURCE: Same<Omit<ApproveMessage, "type" | "id">, Input<"approve">> = true;
export const REQUEST_CHANGES_MATCHES_SOURCE: Same<Omit<RequestChangesMessage, "type" | "id">, Input<"requestChanges">> = true;
export const REBUILD_MATCHES_SOURCE: Same<Omit<RebuildMessage, "type" | "id">, Input<"rebuild">> = true;
