// DaemonSource: the panel's live data source, a *requester* of the local engine daemon (`reel serve`,
// whynot-cut/engine/reel/serve/app.py) over its WebSocket session. It shows state, sends the approve /
// request_changes / rebuild intents, runs host commands and cancels them. It never touches fs, WebSocket or
// fetch itself: the shell (UXP / CEP, Task 4) injects a DaemonTransport, and node tests inject fakes.
//
// Link: read ~/.whynot-cut/bridge/engine.json ({port, token, pid, version, protocol, home?}; re-read on every
// attempt, retried briefly while the daemon swaps it) -> ws://localhost:<port>/session -> `hello` (kind "panel",
// protocol 4, no capabilities) -> `welcome` -> `snapshot` now and every POLL_MS (the daemon pushes nothing yet, and
// the poll is also the keepalive: the daemon pings after 30 s of silence and closes after 60 s). The daemon's state
// is a stub: only its `connection` is merged; everything else stays local. Reconnects back off 1-2-4-8-15 s.
//
// The token goes only into `hello` and the /status probe's Authorization header: never into a URL, a log line,
// PanelState, a diagnosis or an error text (every text the transport hands back is scrubbed of it).
import { ACTION_NAMES, PROTOCOL } from "./contract.ts";
import type { ActionName, RequestEnvelope } from "./contract.ts";
import { linkFixCommand, NOT_YET_CODE, scrubToken } from "./diagnostics.ts";
import { PANEL_UPDATE_STATES, SESSION_ERROR_CODES, SESSION_PROTOCOL } from "./session.ts";
import type {
  ApproveMessage, CancelMessage, CommandMessage, HelloMessage, PanelUpdate, RebuildMessage, ReplyIntent,
  RequestChangesMessage, SessionErrorCode, SnapshotMessage,
} from "./session.ts";
import { CLAUDE_STATES, STEP_IDS } from "./source.ts";
import type { ClaudeState, ConnectionState, HostState, Language, LogLine, PanelDataSource, PanelState, PipelineStep, Result, StepId } from "./source.ts";

// ------------------------------------------------------------------------------------------------ injected transport

/** engine.json as the daemon writes it (serve/security.py write_engine_json; the discovery copy adds `home`). */
export interface EngineRecord {
  port: number;
  token: string;
  pid?: number;
  version?: string;
  protocol?: number;
  home?: string;
}

/** A WebSocket reduced to what DaemonSource needs. The shell wraps the real one: text frames only, and it calls
 *  onopen / onmessage(text) / onclose(code, reason) as the real socket's events arrive (an `error` event needs no
 *  mapping: the real socket fires `close` after it). DaemonSource assigns the handlers right after openSocket(). */
export interface DaemonSocket {
  send(text: string): void;
  close(code?: number, reason?: string): void;
  onopen: (() => void) | null;
  onmessage: ((text: string) => void) | null;
  onclose: ((code: number, reason: string) => void) | null;
}

export interface DaemonTransport {
  /** The parsed JSON of ~/.whynot-cut/bridge/engine.json, or null when it is missing / unreadable. Called on every
   *  connection attempt (the port and token change on every daemon start). May throw: treated as missing. */
  readEngineJson(): unknown | Promise<unknown>;
  /** Open a WebSocket to `url` (always ws://localhost:<port>/session). May throw: treated as a refused connection. */
  openSocket(url: string): DaemonSocket;
  /** GET `url` (http://localhost:<port>/status) with these headers; resolves the HTTP status code, null when nothing
   *  answers in time, and THROWS when the request cannot be made at all (a network permission refusing the port, a
   *  refused connection): that is the "blocked" diagnosis. Optional: without it a failed upgrade is "unreachable". */
  httpGetStatus?(url: string, headers: { Authorization: string }): Promise<number | null>;
  /** Milliseconds since the epoch. */
  now(): number;
  /** Run fn once after ms; returns the function that cancels it. */
  setTimer(fn: () => void, ms: number): () => void;
  /** Optional console sink for link events (already scrubbed of the token). */
  log?(line: string): void;
}

// ------------------------------------------------------------------------------------------------ constants

export const ENGINE_JSON_PATH = "~/.whynot-cut/bridge/engine.json";
export const POLL_MS = 2000;
export const HELLO_TIMEOUT_MS = 5000;
export const INTENT_TIMEOUT_MS = 30_000;
export const CANCEL_WAIT_MS = 1500;
/** extra reads of a missing engine.json inside one attempt (the daemon's tombstone swap takes milliseconds) */
export const ENGINE_JSON_RETRIES = 3;
export const ENGINE_JSON_RETRY_MS = 100;
export const BACKOFF_MAX_MS = 15_000;
/** the daemon's post-auth message cap (app.py POST_AUTH_MAX): a bigger command is refused here, not by close 1009 */
export const MESSAGE_MAX_BYTES = 8 * 1024 * 1024;
/** seconds a command may run before it expires (request.expires_at); a few seconds of grace after that */
export const COMMAND_TIMEOUT_S: Partial<Record<ActionName, number>> & { default: number } = {
  default: 60,
  build_project: 900,
  export_frames: 300,
  render_review: 120,
  ae_build_motion: 900,
  ae_render: 1800,
};
const RESULT_GRACE_MS = 5000;
const LOG_MAX = 200;
const ID_RE = /^[A-Za-z0-9._-]{1,64}$/;

/** The command's owning pipeline step: its progress events update it. Other actions are quick and own no step. */
const ACTION_STEP: Partial<Record<ActionName, StepId>> = {
  build_project: "build",
  export_frames: "frames",
  render_review: "qc",
};

export function backoffMs(failures: number): number {
  return Math.min(1000 * 2 ** Math.max(0, failures - 1), BACKOFF_MAX_MS);
}
// `localhost`, never 127.0.0.1: Premiere 26.5.2's UXP allows exactly `ws://localhost:*` / `http://localhost:*` and
// denies the 127.0.0.1 forms ("Manifest entry not found"; spike 0.1.6, docs/adobe/uxp-parity.md). The daemon binds
// both 127.0.0.1 and ::1, so the name answers at once whichever address Windows tries first.
export function sessionUrl(port: number): string {
  return `ws://localhost:${port}/session`;
}
export function statusUrl(port: number): string {
  return `http://localhost:${port}/status`;
}

// ------------------------------------------------------------------------------------------------ diagnosis

export type LinkCode =
  | "idle" // not started
  | "connecting"
  | "connected"
  | "no_engine" // no engine.json: the daemon is not running
  | "bad_engine_json" // engine.json is there but unusable
  | "down" // engine.json names a port nothing answers on
  | "unreachable" // the upgrade failed and there is no /status probe to say why
  | "blocked" // engine.json names a port, but the socket or the /status request throws (a permission, a dead port)
  | "refused_host" // HTTP 403: the daemon refused this panel's Host / Origin
  | "refused_busy" // HTTP 503: the daemon's connection cap
  | "refused" // the daemon answers /status but the WebSocket failed
  | "auth" // the token was refused (stale engine.json)
  | "protocol" // panel and engine speak different protocols
  | "too_large" // close 1009
  | "no_welcome" // the socket opened but no welcome came
  | "lost" // a working connection ended
  | "stopped"; // stop() was called

export interface LinkDiagnosis {
  code: LinkCode;
  /** one plain sentence for the editor */
  text: string;
  how?: string;
  /** seconds until the next attempt, while reconnecting */
  retry_in_s?: number;
}

// What the editor reads: plain words, never a command (Addendum C1.4). The command that fixes a link problem goes into
// the log line (setDiag) and the Copy diagnostics payload, from diagnostics.ts.
const START_HOW = "Open your Claude session to start the engine, then wait a moment.";
const RESTART_HOW = "If this repeats, start the engine again from your Claude session.";
const BLOCKED: Omit<LinkDiagnosis, "retry_in_s"> = {
  code: "blocked",
  text: "The panel could not reach the engine on its port (engine.json names it, but the connection was refused or blocked).",
  how: "Copy the diagnostics and send them to support.",
};

// ------------------------------------------------------------------------------------------------ incoming messages

type Incoming =
  | { type: "welcome"; daemon_version: string; update: PanelUpdate }
  | { type: "state"; connection: ConnectionState; id?: string }
  | { type: "reply"; id: string; intent: ReplyIntent; ok: boolean; readback?: object; error?: string; how?: string }
  | { type: "result"; id: string | undefined; action: ActionName; ok: boolean; readback?: object; error?: string; how?: string }
  | { type: "progress"; id: string; step: string; n?: number; of?: number; elapsed_s?: number }
  | { type: "error"; code: SessionErrorCode; message: string; id?: string };

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const optStr = (v: unknown) => v === undefined || isStr(v);
const optNum = (v: unknown) => v === undefined || isNum(v);
const isId = (v: unknown): v is string => isStr(v) && ID_RE.test(v);
const isAction = (v: unknown): v is ActionName => isStr(v) && (ACTION_NAMES as readonly string[]).includes(v);
const INTENTS: readonly ReplyIntent[] = ["approve", "request_changes", "rebuild"];

function parseConnection(c: unknown): ConnectionState | null {
  if (!isObj(c) || !isObj(c["host"])) return null;
  const { engine, claude } = c;
  const host = c["host"];
  if (engine !== "connected" && engine !== "offline") return null;
  if (!CLAUDE_STATES.includes(claude as ClaudeState)) return null;
  const st = host["state"];
  if (st !== "uxp" && st !== "cep" && st !== "offline") return null;
  if (!optStr(host["detail"])) return null;
  const out: ConnectionState = { engine, claude: claude as ClaudeState, host: { state: st } };
  if (isStr(host["detail"])) out.host.detail = host["detail"].slice(0, 256);
  return out;
}

/** A daemon -> panel message, checked by hand (no ajv in the panel bundle); null = malformed or not for a panel. */
export function parseIncoming(text: string): Incoming | null {
  let m: unknown;
  try {
    m = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isObj(m)) return null;
  switch (m["type"]) {
    case "welcome": {
      if (!isStr(m["session_id"]) || m["protocol"] !== SESSION_PROTOCOL || !isStr(m["daemon_version"])) return null;
      // C2.3: absent from an older daemon; a value this panel does not know reads as unknown
      const u = isObj(m["update"]) ? m["update"]["panel"] : undefined;
      const update: PanelUpdate = (PANEL_UPDATE_STATES as readonly unknown[]).includes(u) ? (u as PanelUpdate) : "unknown";
      return { type: "welcome", daemon_version: m["daemon_version"], update };
    }
    case "state": {
      if (!isObj(m["state"]) || !(m["id"] === undefined || isId(m["id"]))) return null;
      const connection = parseConnection(m["state"]["connection"]);
      if (!connection) return null;
      return isStr(m["id"]) ? { type: "state", connection, id: m["id"] } : { type: "state", connection };
    }
    case "reply": {
      const { id, intent, ok, readback, error, how } = m;
      if (!isId(id) || !INTENTS.includes(intent as ReplyIntent) || typeof ok !== "boolean") return null;
      if (!(readback === undefined || isObj(readback)) || !optStr(how)) return null;
      if (ok ? error !== undefined : !(isStr(error) && error.length > 0)) return null;
      return { type: "reply", id, intent: intent as ReplyIntent, ok, ...(readback ? { readback } : {}), ...(isStr(error) ? { error } : {}), ...(isStr(how) ? { how } : {}) };
    }
    case "result": {
      const r = m["result"];
      if (!isObj(r)) return null;
      const { ok, action, readback, error, how, id } = r;
      if (typeof ok !== "boolean" || !isAction(action) || !(id === undefined || isId(id)) || !optStr(how)) return null;
      if (ok ? !(isObj(readback) && error === undefined) : !(isStr(error) && error.length > 0 && (readback === undefined || isObj(readback)))) return null;
      return { type: "result", id, action, ok, ...(isObj(readback) ? { readback } : {}), ...(isStr(error) ? { error } : {}), ...(isStr(how) ? { how } : {}) };
    }
    case "progress": {
      const p = m["progress"];
      if (!isObj(p) || p["event"] !== "progress" || !isId(p["id"]) || !isAction(p["action"]) || !isStr(p["step"])) return null;
      if (!optNum(p["n"]) || !optNum(p["of"]) || !optNum(p["elapsed_s"])) return null;
      const out: Extract<Incoming, { type: "progress" }> = { type: "progress", id: p["id"], step: p["step"] };
      if (isNum(p["n"])) out.n = p["n"];
      if (isNum(p["of"])) out.of = p["of"];
      if (isNum(p["elapsed_s"])) out.elapsed_s = p["elapsed_s"];
      return out;
    }
    case "error": {
      const { code, message, id } = m;
      if (!(SESSION_ERROR_CODES as readonly string[]).includes(code as string) || !isStr(message) || !(id === undefined || isId(id))) return null;
      return isStr(id) ? { type: "error", code: code as SessionErrorCode, message, id } : { type: "error", code: code as SessionErrorCode, message };
    }
    default:
      return null;
  }
}

/** UTF-8 byte length without TextEncoder (not every host has it). */
function utf8Bytes(s: string): number {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 0x80) n += 1;
    else if (c < 0x800) n += 2;
    else if (c >= 0xd800 && c <= 0xdbff) {
      n += 4;
      i++;
    } else n += 3;
  }
  return n;
}

function readRecord(raw: unknown): EngineRecord | "invalid" | "protocol" {
  if (!isObj(raw)) return "invalid";
  const { port, token, protocol } = raw;
  if (typeof port !== "number" || !Number.isInteger(port) || port <= 0 || port >= 65536) return "invalid";
  if (!isStr(token) || !/^[0-9a-f]{64}$/.test(token)) return "invalid";
  if (protocol !== undefined && protocol !== SESSION_PROTOCOL) return "protocol";
  return { port, token };
}

// ------------------------------------------------------------------------------------------------ the source

export interface DaemonSourceOptions {
  transport: DaemonTransport;
  /** the panel's version, sent in hello (1-64 characters) */
  version?: string;
  /** the panel package's build stamp, sent in hello as client.build (C2.3; 1-64 characters, empty = not sent) */
  build?: string;
  /** local, never taken from the daemon's stub state */
  language?: Language;
  editor_name?: string;
  pollMs?: number;
  helloTimeoutMs?: number;
  intentTimeoutMs?: number;
  cancelWaitMs?: number;
  /** seconds per action before the request expires; merged over COMMAND_TIMEOUT_S */
  commandTimeoutS?: Partial<Record<ActionName, number>>;
  /** the host the panel itself runs in (e.g. {state: "uxp", detail: "Premiere Pro 26.5.2"}): the host pill while the
   *  engine is offline. Default {state: "offline"}. Online, the daemon's connection wins. */
  localHost?: { state: HostState; detail?: string };
  /** a number in [0, 1) for the request-id base (default Math.random) */
  random?: () => number;
}

interface PendingCommand {
  action: ActionName;
  step: StepId | null;
  stop: () => void;
  resolve: (r: Result) => void;
}
interface PendingIntent {
  intent: ReplyIntent;
  stop: () => void;
  resolve: (r: Result) => void;
}
interface PendingCancel {
  stop: () => void;
  resolve: () => void;
  reject: (e: Error) => void;
}

const INTENT_LABEL: Record<ReplyIntent, string> = { approve: "Approving", request_changes: "Requesting changes", rebuild: "Rebuilding" };

function offlineConnection(host?: { state: HostState; detail?: string }): ConnectionState {
  const h: ConnectionState["host"] = { state: host?.state ?? "offline" };
  if (host?.detail) h.detail = host.detail.slice(0, 256);
  return { engine: "offline", claude: "unknown", host: h };
}

/** A deep copy of plain JSON data: structuredClone where the host has it (not every UXP / CEP runtime does). */
function clone<T>(v: T): T {
  const sc = (globalThis as { structuredClone?: (x: unknown) => unknown }).structuredClone;
  return typeof sc === "function" ? (sc(v) as T) : (JSON.parse(JSON.stringify(v)) as T);
}

function emptyState(language: Language, editor_name: string, host?: { state: HostState; detail?: string }): PanelState {
  return {
    connection: offlineConnection(host),
    client: "",
    item: "",
    language,
    editor_name,
    context: { project_path: null, sequence_name: null, folder: null, out_dir: null, review_mp4: null },
    pipeline: [],
    approval: null,
    qc: [],
    log: [],
  };
}

export class DaemonSource implements PanelDataSource {
  private readonly t: DaemonTransport;
  private readonly version: string;
  private readonly build: string;
  private panelUpdateState: PanelUpdate = "unknown";
  private readonly pollMs: number;
  private readonly helloTimeoutMs: number;
  private readonly intentTimeoutMs: number;
  private readonly cancelWaitMs: number;
  private readonly timeouts: Partial<Record<ActionName, number>> & { default: number };
  private state: PanelState;
  private subs = new Set<(s: PanelState) => void>();
  private started = false;
  private stopped = false;
  /** bumped by every attempt and by stop(): callbacks of an older attempt do nothing */
  private gen = 0;
  private sock: DaemonSocket | null = null;
  private opened = false;
  private welcomed = false;
  private failures = 0;
  private port = 0;
  /** held for hello, the /status probe and scrubbing; never stored anywhere visible */
  private token: string | null = null;
  private lastError: { code: SessionErrorCode; message: string } | null = null;
  private malformedLogged = false;
  private stopHello: (() => void) | null = null;
  private stopPoll: (() => void) | null = null;
  private stopRetry: (() => void) | null = null;
  private commands = new Map<string, PendingCommand>();
  private intents = new Map<string, PendingIntent>();
  private cancels = new Map<string, PendingCancel>();
  private readonly idBase: string;
  private readonly localHost: { state: HostState; detail?: string } | undefined;
  private seq = 0;
  private diag: LinkDiagnosis = { code: "idle", text: "Not connected to the engine yet." };
  private lastLogged: LinkCode | null = null;

  constructor(opts: DaemonSourceOptions) {
    this.t = opts.transport;
    this.version = (opts.version || "0.0.0").slice(0, 64);
    this.build = (opts.build ?? "").slice(0, 64);
    this.pollMs = opts.pollMs ?? POLL_MS;
    this.helloTimeoutMs = opts.helloTimeoutMs ?? HELLO_TIMEOUT_MS;
    this.intentTimeoutMs = opts.intentTimeoutMs ?? INTENT_TIMEOUT_MS;
    this.cancelWaitMs = opts.cancelWaitMs ?? CANCEL_WAIT_MS;
    this.timeouts = { ...COMMAND_TIMEOUT_S, ...opts.commandTimeoutS };
    this.localHost = opts.localHost;
    this.state = emptyState(opts.language ?? "en", opts.editor_name ?? "", this.localHost);
    // time + a random suffix: two panels created in the same millisecond must not share ids (the daemon's id map is global)
    const r = (opts.random ?? Math.random)();
    const rand = Math.floor((Number.isFinite(r) ? Math.abs(r) % 1 : 0) * 36 ** 5).toString(36).padStart(5, "0");
    this.idBase = Math.floor(this.t.now()).toString(36).slice(-8) + rand;
  }

  // ---------------------------------------------------------------------------------------------- public

  /** The link's current diagnosis (what the engine pill and the log say, in more detail). */
  get diagnosis(): LinkDiagnosis {
    return { ...this.diag };
  }

  /** The daemon's answer to this panel's build stamp (welcome.update.panel); "unknown" until a welcome says otherwise. */
  get panelUpdate(): PanelUpdate {
    return this.panelUpdateState;
  }

  /** Starts the link (idempotent). snapshot() and subscribe() call it too. */
  start(): void {
    if (this.started || this.stopped) return;
    this.started = true;
    void this.connect();
  }

  /** Ends the link for good: closes the socket, cancels every timer, answers every pending call. */
  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.gen++;
    this.clearTimers();
    const sock = this.sock;
    this.sock = null;
    this.welcomed = false;
    if (sock) {
      try {
        sock.close(1000, "panel closed");
      } catch {
        // already gone
      }
    }
    this.failAll("The panel closed its engine connection.");
    this.diag = { code: "stopped", text: "The panel stopped its engine connection." };
    this.update({ connection: offlineConnection(this.localHost) });
  }

  /** Local settings the daemon's stub state does not carry. */
  setLocal(local: { language?: Language; editor_name?: string }): void {
    this.update({ ...(local.language ? { language: local.language } : {}), ...(local.editor_name !== undefined ? { editor_name: local.editor_name } : {}) });
  }

  async snapshot(): Promise<PanelState> {
    this.start();
    return clone(this.state);
  }

  subscribe(cb: (s: PanelState) => void): () => void {
    this.subs.add(cb);
    this.start();
    return () => {
      this.subs.delete(cb);
    };
  }

  approve(input: { item: string; editor_name: string; fingerprint: string }): Promise<Result> {
    return this.intent("approve", { item: input.item, editor_name: input.editor_name, fingerprint: input.fingerprint });
  }

  requestChanges(input: { item: string; editor_name: string; text: string }): Promise<Result> {
    return this.intent("request_changes", { item: input.item, editor_name: input.editor_name, text: input.text });
  }

  rebuild(input: { item: string; project_path?: string; replace_edited: boolean }): Promise<Result> {
    // the engine finds the project from the item (C2.4): project_path goes along only when the panel has one
    const body = input.project_path ? { item: input.item, project_path: input.project_path, replace_edited: input.replace_edited } : { item: input.item, replace_edited: input.replace_edited };
    return this.intent("rebuild", body);
  }

  run(action: ActionName, data: object): Promise<Result> {
    const sock = this.sock;
    if (!sock || !this.welcomed) return Promise.resolve(this.notConnected(action));
    const id = this.newId("cmd");
    const seconds = this.timeouts[action] ?? this.timeouts.default;
    const request: RequestEnvelope = { protocol: PROTOCOL, id, action, data, expires_at: new Date(this.t.now() + seconds * 1000).toISOString() };
    const msg: CommandMessage = { type: "command", request };
    const text = JSON.stringify(msg);
    if (utf8Bytes(text) > MESSAGE_MAX_BYTES) {
      return Promise.resolve({
        ok: false,
        action,
        error: "This request is too large for the engine (over 8 MB).",
        how: "Send fewer items at once.",
        code: "too_large",
      });
    }
    return new Promise<Result>((resolve) => {
      const step = ACTION_STEP[action] ?? null;
      const stop = this.t.setTimer(() => {
        this.settleCommand(id, { ok: false, action, error: "The engine did not answer this request in time.", how: "Check that Premiere and the WhyNot Cut panel are open, then press Try again.", code: "timeout" });
      }, seconds * 1000 + RESULT_GRACE_MS);
      this.commands.set(id, { action, step, stop, resolve });
      if (step) this.setStep(step, { state: "running", request_id: id, progress: null, elapsed_s: null });
      this.sendText(sock, text);
    });
  }

  /** Cancels a running request (PipelineStep.request_id), whoever started it: the daemon forwards it to the panel
   *  running it, and that command's own result answers. A command the daemon cannot cancel (CEP-routed, or not
   *  running) is answered with no_route: that throws "can't be cancelled". Silence means it was forwarded. */
  cancel(id: string): Promise<void> {
    if (!ID_RE.test(id)) return Promise.reject(new Error("This request can't be cancelled: its id is not valid."));
    const sock = this.sock;
    if (!sock || !this.welcomed) return Promise.reject(new Error("The engine is not connected, so nothing can be cancelled now."));
    return new Promise<void>((resolve, reject) => {
      this.cancels.get(id)?.resolve();
      const stop = this.t.setTimer(() => {
        if (this.cancels.get(id)?.stop === stop) this.cancels.delete(id);
        this.logLine("info", `Cancel sent for ${id}.`);
        resolve();
      }, this.cancelWaitMs);
      this.cancels.set(id, { stop, resolve, reject });
      const msg: CancelMessage = { type: "cancel", id };
      this.sendText(sock, JSON.stringify(msg));
    });
  }

  // ---------------------------------------------------------------------------------------------- connecting

  private async connect(): Promise<void> {
    if (this.stopped) return;
    const gen = ++this.gen;
    this.stopRetry = null;
    this.setDiag({ code: "connecting", text: "Connecting to the WhyNot Cut engine..." }, false);
    let raw: unknown = null;
    for (let i = 0; i <= ENGINE_JSON_RETRIES; i++) {
      if (i > 0) await new Promise<void>((r) => this.t.setTimer(r, ENGINE_JSON_RETRY_MS));
      if (gen !== this.gen) return;
      try {
        raw = await this.t.readEngineJson();
      } catch {
        raw = null;
      }
      if (gen !== this.gen) return;
      if (raw !== null && raw !== undefined) break;
    }
    if (raw === null || raw === undefined) {
      return this.retry({ code: "no_engine", text: "The WhyNot Cut engine is not running (no engine.json).", how: START_HOW });
    }
    const rec = readRecord(raw);
    if (rec === "invalid") {
      return this.retry({ code: "bad_engine_json", text: "The engine's connection file (engine.json) is incomplete or damaged.", how: START_HOW });
    }
    if (rec === "protocol") {
      return this.retry({ code: "protocol", text: "The engine is a different version from this panel (protocol 4 required).", how: "Update the WhyNot Cut panel and engine to the same version." });
    }
    this.port = rec.port;
    this.token = rec.token;
    this.opened = false;
    this.welcomed = false;
    this.lastError = null;
    this.malformedLogged = false;
    let sock: DaemonSocket;
    try {
      sock = this.t.openSocket(sessionUrl(rec.port));
    } catch (e) {
      this.logLine("warn", `The engine connection could not be opened: ${this.scrub(e instanceof Error ? e.message : String(e))}`);
      return this.retry({ ...BLOCKED });
    }
    this.sock = sock;
    sock.onopen = () => {
      if (this.sock !== sock) return;
      this.opened = true;
      const hello: HelloMessage = { type: "hello", token: rec.token, client: { kind: "panel", version: this.version, ...(this.build ? { build: this.build } : {}), protocol: SESSION_PROTOCOL, capabilities: [] } };
      this.sendText(sock, JSON.stringify(hello));
    };
    sock.onmessage = (text) => {
      if (this.sock === sock) this.onMessage(sock, text);
    };
    sock.onclose = (code, reason) => {
      if (this.sock === sock) void this.ended(sock, gen, code, String(reason ?? ""), false);
    };
    this.stopHello = this.t.setTimer(() => {
      if (this.sock !== sock || this.welcomed) return;
      try {
        sock.close(1000, "no welcome");
      } catch {
        // already gone
      }
      void this.ended(sock, gen, 0, "", true);
    }, this.helloTimeoutMs);
  }

  /** The connection attempt or the session ended. */
  private async ended(sock: DaemonSocket, gen: number, code: number, _reason: string, timedOut: boolean): Promise<void> {
    if (this.sock !== sock) return;
    this.sock = null;
    const wasOpened = this.opened;
    this.welcomed = false;
    this.clearTimers();
    this.failAll("The engine connection was lost before it answered.");
    this.update({ connection: offlineConnection(this.localHost) });
    const err = this.lastError;
    if (code === 1008 && err?.code === "schema" && /protocol/i.test(err.message)) {
      return this.retry({ code: "protocol", text: "The engine is a different version from this panel (protocol 4 required).", how: "Update the WhyNot Cut panel and engine to the same version." });
    }
    // UXP may report the daemon's 1008 as 1006: the error{auth} that came before it says the same
    if (code === 1008 || err?.code === "auth") {
      return this.retry({ code: "auth", text: "The engine refused the panel's key (engine.json is out of date or from another engine).", how: "The panel tries again by itself; if this repeats, start the engine again from your Claude session." });
    }
    if (code === 1009) {
      return this.retry({ code: "too_large", text: "The engine closed the connection: a message was larger than it accepts.", how: "Send fewer items at once; the panel reconnects by itself." });
    }
    if (timedOut && wasOpened) {
      return this.retry({ code: "no_welcome", text: "The engine did not answer the panel's hello.", how: RESTART_HOW });
    }
    if (!wasOpened) return this.unreached(gen);
    return this.retry({ code: "lost", text: `The engine connection was lost (code ${code || "none"}).`, how: "The panel reconnects by itself." });
  }

  /** The WebSocket never opened: the daemon is down, or it refused the upgrade (HTTP 403 / 503). Ask /status. */
  private async unreached(gen: number): Promise<void> {
    const probe = this.t.httpGetStatus;
    const token = this.token;
    if (!probe || !token) {
      return this.retry({ code: "unreachable", text: "The panel could not reach the WhyNot Cut engine.", how: START_HOW });
    }
    let status: number | null = null;
    let threw = false;
    try {
      status = await probe.call(this.t, statusUrl(this.port), { Authorization: `Bearer ${token}` });
    } catch {
      threw = true;
    }
    if (gen !== this.gen || this.stopped) return;
    if (threw) return this.retry({ ...BLOCKED });
    if (status === null) return this.retry({ code: "down", text: "The WhyNot Cut engine is not running.", how: START_HOW });
    if (status === 200) {
      // /status accepts the token, so the daemon is up and the key is right: only the WebSocket's Origin was refused
      return this.retry({ code: "refused_host", text: "The engine is running, but it refused the panel's connection (Origin check).", how: "Copy the diagnostics and send them to support." });
    }
    if (status === 403) {
      return this.retry({ code: "refused_host", text: "The engine refused the panel's connection (Host / Origin check).", how: "Copy the diagnostics and send them to support." });
    }
    if (status === 503) return this.retry({ code: "refused_busy", text: "The engine has too many connections open.", how: "Close other WhyNot Cut panels or restart the engine." });
    if (status === 401) {
      return this.retry({ code: "auth", text: "The engine refused the panel's key (engine.json is out of date or from another engine).", how: "The panel tries again by itself; if this repeats, start the engine again from your Claude session." });
    }
    return this.retry({ code: "refused", text: `The engine is running but refused the panel's session (HTTP ${status}).`, how: "Copy the diagnostics and send them to support." });
  }

  private retry(d: LinkDiagnosis): void {
    if (this.stopped) return;
    this.failures++;
    const ms = backoffMs(this.failures);
    this.setDiag({ ...d, retry_in_s: Math.round(ms / 1000) }, true);
    this.update({ connection: offlineConnection(this.localHost) });
    this.stopRetry = this.t.setTimer(() => {
      this.stopRetry = null;
      void this.connect();
    }, ms);
  }

  // ---------------------------------------------------------------------------------------------- messages

  private onMessage(sock: DaemonSocket, text: string): void {
    const m = parseIncoming(String(text));
    if (!m) return this.malformed();
    if (!this.welcomed) {
      if (m.type === "welcome") {
        this.panelUpdateState = m.update;
        return this.onWelcome(sock, m.daemon_version);
      }
      if (m.type === "error") {
        this.lastError = { code: m.code, message: m.message };
        return;
      }
      return this.malformed();
    }
    switch (m.type) {
      case "state":
        return this.onState(m.connection);
      case "reply":
        return this.onReply(m);
      case "result":
        return this.onResult(m);
      case "progress":
        return this.onProgress(m);
      case "error":
        return this.onError(m);
      case "welcome":
        return this.malformed();
    }
  }

  private onWelcome(sock: DaemonSocket, daemonVersion: string): void {
    this.welcomed = true;
    this.failures = 0;
    this.stopHello?.();
    this.stopHello = null;
    this.setDiag({ code: "connected", text: `Connected to the WhyNot Cut engine ${this.scrub(daemonVersion).slice(0, 64)}.` }, true);
    this.update({ connection: { ...this.state.connection, engine: "connected" } });
    this.poll(sock);
  }

  private poll(sock: DaemonSocket): void {
    if (this.sock !== sock || !this.welcomed) return;
    const msg: SnapshotMessage = { type: "snapshot", id: this.newId("snap") };
    this.sendText(sock, JSON.stringify(msg));
    if (this.sock !== sock) return;
    this.stopPoll = this.t.setTimer(() => this.poll(sock), this.pollMs);
  }

  private onState(c: ConnectionState): void {
    const next: ConnectionState = { ...c, engine: "connected" };
    if (JSON.stringify(next) !== JSON.stringify(this.state.connection)) this.update({ connection: next });
  }

  private onReply(m: Extract<Incoming, { type: "reply" }>): void {
    const p = this.intents.get(m.id);
    if (!p || p.intent !== m.intent) return;
    if (m.ok) return this.settleIntent(m.id, { ok: true, action: m.intent, ...(m.readback ? { readback: m.readback } : {}), ...(m.how ? { how: m.how } : {}) });
    // the engine has no panel side for this intent yet (serve/app.py NOT_YET): the same answer every time, so the
    // panel offers no Try again (code NOT_YET, read by mount)
    const notImplemented = /not implemented/i.test(m.error ?? "");
    const notYet = notImplemented || /not available from the panel/i.test(m.error ?? "");
    const error = notImplemented ? `${INTENT_LABEL[m.intent]} is not available from the panel in this engine yet.` : (m.error ?? "The engine refused this.");
    const r: Result & { code?: string } = { ok: false, action: m.intent, error, ...(m.how ? { how: m.how } : {}), ...(m.readback ? { readback: m.readback } : {}) };
    if (notYet) r.code = NOT_YET_CODE;
    this.settleIntent(m.id, r);
  }

  private onResult(m: Extract<Incoming, { type: "result" }>): void {
    if (!m.id) return;
    const p = this.commands.get(m.id);
    if (!p || p.action !== m.action) return;
    this.settleCommand(m.id, { ok: m.ok, action: m.action, ...(m.readback ? { readback: m.readback } : {}), ...(m.error ? { error: m.error } : {}), ...(m.how ? { how: m.how } : {}) });
  }

  private onProgress(m: Extract<Incoming, { type: "progress" }>): void {
    const step = this.state.pipeline.find((p) => p.request_id === m.id);
    if (!step) return;
    const patch: Partial<PipelineStep> = { state: "running" };
    if (m.n !== undefined && m.of !== undefined) {
      patch.progress = { n: Math.max(0, Math.floor(m.n)), of: Math.max(1, Math.floor(m.of)), step: m.step.slice(0, 256) };
    }
    if (m.elapsed_s !== undefined && m.elapsed_s >= 0) patch.elapsed_s = m.elapsed_s;
    this.setStep(step.id, patch);
  }

  private onError(m: Extract<Incoming, { type: "error" }>): void {
    const text = this.scrub(m.message);
    if (m.id) {
      const c = this.cancels.get(m.id);
      if (c) {
        this.cancels.delete(m.id);
        c.stop();
        const why = /CEP/i.test(text)
          ? "it runs through the CEP bridge, which has no cancel."
          : /no running command/i.test(text)
            ? "it is not running any more."
            : text;
        return c.reject(new Error(m.code === "no_route" ? `This command can't be cancelled: ${why}` : `The cancel was refused: ${text}`));
      }
      const cmd = this.commands.get(m.id);
      if (cmd) return this.settleCommand(m.id, { ok: false, action: cmd.action, error: text, how: HOW_BY_CODE[m.code], code: m.code });
      const intent = this.intents.get(m.id);
      if (intent) return this.settleIntent(m.id, { ok: false, action: intent.intent, error: text, how: HOW_BY_CODE[m.code], code: m.code });
      if (m.id.startsWith("snap-")) return; // a snapshot over the rate limit: the next poll asks again
    }
    this.logLine(m.code === "rate" ? "warn" : "error", `Engine: ${text}`);
  }

  private malformed(): void {
    if (this.malformedLogged) return;
    this.malformedLogged = true;
    this.logLine("warn", "The engine sent a malformed or unexpected message; it was ignored.");
  }

  // ---------------------------------------------------------------------------------------------- pending calls

  private intent(intent: ReplyIntent, body: Record<string, unknown>): Promise<Result> {
    const sock = this.sock;
    if (!sock || !this.welcomed) return Promise.resolve(this.notConnected(intent));
    const id = this.newId("int");
    const msg = { type: intent, id, ...body } as ApproveMessage | RequestChangesMessage | RebuildMessage;
    return new Promise<Result>((resolve) => {
      const stop = this.t.setTimer(() => {
        this.settleIntent(id, { ok: false, action: intent, error: "The engine did not answer in time.", how: "Check the engine is running, then press Try again.", code: "timeout" });
      }, this.intentTimeoutMs);
      this.intents.set(id, { intent, stop, resolve });
      this.sendText(sock, JSON.stringify(msg));
    });
  }

  private settleIntent(id: string, r: Result): void {
    const p = this.intents.get(id);
    if (!p) return;
    this.intents.delete(id);
    p.stop();
    p.resolve(r);
  }

  private settleCommand(id: string, r: Result): void {
    const p = this.commands.get(id);
    if (!p) return;
    this.commands.delete(id);
    p.stop();
    if (p.step) {
      const step = this.state.pipeline.find((s) => s.id === p.step);
      if (step && step.request_id === id) this.setStep(p.step, { state: r.ok ? "done" : "failed", request_id: null });
    }
    p.resolve(r);
  }

  private failAll(error: string): void {
    for (const id of [...this.commands.keys()]) {
      const action = this.commands.get(id)!.action;
      this.settleCommand(id, { ok: false, action, error, how: "The panel reconnects by itself; once the engine pill says connected, do it again.", code: "lost" });
    }
    for (const id of [...this.intents.keys()]) {
      const intent = this.intents.get(id)!.intent;
      this.settleIntent(id, { ok: false, action: intent, error, how: "The panel reconnects by itself; once the engine pill says connected, do it again.", code: "lost" });
    }
    for (const [id, c] of [...this.cancels]) {
      this.cancels.delete(id);
      c.stop();
      c.reject(new Error("The engine connection was lost before the cancel was confirmed."));
    }
  }

  private notConnected(action: string): Result {
    return { ok: false, action, error: "The WhyNot Cut engine is not connected.", how: this.diag.how ?? START_HOW, code: this.diag.code };
  }

  // ---------------------------------------------------------------------------------------------- helpers

  private sendText(sock: DaemonSocket, text: string): void {
    try {
      sock.send(text);
    } catch {
      if (this.sock === sock) void this.ended(sock, this.gen, 1006, "", false);
    }
  }

  private newId(prefix: string): string {
    return `${prefix}-${this.idBase}-${++this.seq}`;
  }

  private clearTimers(): void {
    this.stopHello?.();
    this.stopPoll?.();
    this.stopRetry?.();
    this.stopHello = this.stopPoll = this.stopRetry = null;
  }

  /** The token never leaves in a text. */
  private scrub(text: string): string {
    return scrubToken(text, this.token);
  }

  private setDiag(d: LinkDiagnosis, log: boolean): void {
    this.diag = { ...d, text: this.scrub(d.text) };
    if (!log || this.lastLogged === d.code) return;
    this.lastLogged = d.code;
    const level: LogLine["level"] = d.code === "connected" ? "info" : d.code === "lost" || d.code === "no_engine" ? "warn" : "error";
    // the log drawer is where the command goes (never the banner): it names what fixes this diagnosis
    const fix = linkFixCommand(d.code);
    this.logLine(level, (d.how ? `${this.diag.text} ${this.scrub(d.how)}` : this.diag.text) + (fix ? ` [fix: ${fix}]` : ""));
  }

  private logLine(level: LogLine["level"], text: string): void {
    const clean = this.scrub(text).slice(0, 4000);
    this.t.log?.(clean);
    const line: LogLine = { ts: new Date(this.t.now()).toISOString().slice(11, 19), level, text: clean };
    this.update({ log: [...this.state.log, line].slice(-LOG_MAX) });
  }

  private setStep(id: StepId, patch: Partial<PipelineStep>): void {
    const has = this.state.pipeline.some((p) => p.id === id);
    const base: PipelineStep[] = has ? this.state.pipeline : [...this.state.pipeline, { id, state: "pending", progress: null, elapsed_s: null, request_id: null }];
    const order = STEP_IDS as readonly StepId[];
    const pipeline = base.map((p) => (p.id === id ? { ...p, ...patch } : p)).sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    this.update({ pipeline });
  }

  private update(patch: Partial<PanelState>): void {
    this.state = { ...this.state, ...patch };
    for (const cb of [...this.subs]) {
      try {
        cb(clone(this.state));
      } catch {
        // a subscriber's failure is the subscriber's (mount turns render errors into an error view)
      }
    }
  }
}

const HOW_BY_CODE: Record<SessionErrorCode, string> = {
  auth: "Start the engine again from your Claude session; the panel reconnects by itself.",
  origin: "Reinstall the WhyNot Cut panel.",
  host: "Reinstall the WhyNot Cut panel.",
  too_large: "Send fewer items at once.",
  rate: "Wait a moment, then press Try again.",
  schema: "Update the WhyNot Cut panel and engine to the same version.",
  unknown_type: "Update the WhyNot Cut panel and engine to the same version.",
  no_route: "Open Premiere with the WhyNot Cut panel, then press Try again.",
  timeout: "Press Try again.",
  internal: "Press Try again; if it repeats, copy the diagnostics and send them to support.",
};
