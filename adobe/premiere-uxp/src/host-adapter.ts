// The Premiere UXP host adapter: inside Premiere, the WhyNot Cut panel is a *host* session of the local engine daemon
// (`reel serve`). It says hello as kind "uxp" with the actions it implements (CAPABILITIES), receives `command`
// messages, runs each op with Premiere's UXP API (src/ops/*.ts) and answers one v4 `result` per command id:
//   - the command's data is checked against the action's $defs/data before Premiere is touched;
//   - the op's readback is checked against $defs/readback before it is sent; an invalid one is never sent, the answer
//     is ok:false "adapter produced an invalid readback" (the daemon would reject it, the requester would wait);
//   - ok:true carries a readback and no error; ok:false carries an error (one plain sentence) and how to fix it;
//   - `cancel {id}` from the daemon (timeout, requester gone, Cancel in a panel) stops a running op between steps or
//     drops a queued one, and the command's own result answers it;
//   - long ops send `progress` with the command's id;
//   - Premiere ops run one at a time (they drive the active project, sequence and playhead); ping and status answer
//     at once, even while one runs.
// The socket is injected (HostSocket): Task 4 passes the UXP WebSocket once it is open; node tests pass a fake.
// Nothing here evaluates code: the actions are the contract's closed list.
import { ACTION_NAMES, PROTOCOL } from "../../panel-ui/src/contract.ts";
import type { ActionName, ProgressEvent, ResultEnvelope } from "../../panel-ui/src/contract.ts";
import type { ErrorMessage, HelloMessage, WelcomeMessage } from "../../panel-ui/src/session.ts";
import { OPS } from "./ops/index.ts";
import { hostVersionOf } from "./ops/premiere.ts";
import { OpError, cancelledError } from "./ops/types.ts";
import type { Op, OpContext, OpEnv } from "./ops/types.ts";
import { validateData, validateReadback } from "./ops/validate.ts";

/** The part of a WebSocket the adapter uses. A UXP/DOM WebSocket fits as is (checked below). */
export interface HostSocket {
  send(text: string): void;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  close(code?: number, reason?: string): void;
}

// Compile-time guard for Task 4: the real WebSocket can be handed over without a wrapper.
type Fits<A, B> = A extends B ? true : never;
export const WEBSOCKET_IS_A_HOST_SOCKET: Fits<WebSocket, HostSocket> = true;

export interface HostAdapterOptions {
  /** an OPEN socket to reel serve (the adapter sends hello at once) */
  socket: HostSocket;
  /** the engine token from <engine home>/bridge/engine.json */
  token: string;
  env: OpEnv;
  /** replace or add ops (tests); default: src/ops/index.ts OPS */
  ops?: Partial<Record<ActionName, Op<never>>>;
  onWelcome?: (msg: WelcomeMessage) => void;
  /** a daemon `error` message (auth, schema, rate, ...): never answered */
  onError?: (msg: ErrorMessage) => void;
  /** the socket closed (not called by stop()) */
  onClose?: () => void;
  log?: (level: "info" | "warn" | "error", text: string) => void;
}

export interface HostAdapter {
  /** the actions declared in the hello */
  readonly capabilities: readonly ActionName[];
  /** the daemon's session id once welcomed, else null */
  readonly sessionId: string | null;
  /** ids of the commands running or queued */
  running(): string[];
  /** cancel everything, detach from the socket and close it */
  stop(): void;
}

const ID_RE = /^[A-Za-z0-9._-]{1,64}$/;
export const INVALID_READBACK = "adapter produced an invalid readback";
const UPDATE_HOW = "Update the WhyNot Cut panel and the engine to the same version, then run the command again.";

interface Entry {
  id: string;
  action: ActionName;
  op: Op<never>;
  data: unknown;
  cancelled: boolean;
  started: boolean;
  answered: boolean;
}

function failure(action: ActionName, id: string, error: string, how?: string): ResultEnvelope {
  return how ? { ok: false, action, id, error, how } : { ok: false, action, id, error };
}

export function startHostAdapter(opts: HostAdapterOptions): HostAdapter {
  const { socket, env } = opts;
  const ops: Partial<Record<ActionName, Op<never>>> = { ...(OPS as Partial<Record<ActionName, Op<never>>>), ...opts.ops };
  const capabilities = (Object.keys(ops) as ActionName[]).filter((a) => ACTION_NAMES.includes(a) && ops[a]);
  const entries = new Map<string, Entry>();
  let chain: Promise<void> = Promise.resolve();
  let closed = false;
  let sessionId: string | null = null;
  const log = (level: "info" | "warn" | "error", text: string) => {
    try {
      opts.log?.(level, text);
    } catch {
      // a logger must never break the session
    }
  };

  function send(msg: object): void {
    if (closed) return;
    try {
      socket.send(JSON.stringify(msg));
    } catch (e) {
      log("warn", `WhyNot Cut: could not send to the engine (${e instanceof Error ? e.message : String(e)})`);
    }
  }

  function answer(entry: Entry, result: ResultEnvelope): void {
    if (entry.answered) return;
    entry.answered = true;
    entries.delete(entry.id);
    send({ type: "result", result });
  }

  async function execute(entry: Entry): Promise<void> {
    if (entry.cancelled || closed) return;
    entry.started = true;
    const t0 = env.now();
    const ctx: OpContext = {
      env,
      id: entry.id,
      cancelled: () => entry.cancelled || closed,
      throwIfCancelled: () => {
        if (entry.cancelled || closed) throw cancelledError();
      },
      progress: (step, n, of) => {
        if (entry.cancelled || closed) return;
        const p: ProgressEvent = { event: "progress", id: entry.id, action: entry.action, step: String(step), elapsed_s: Math.max(0, Math.round(env.now() - t0) / 1000) };
        if (Number.isInteger(n) && (n as number) >= 0) p.n = n as number;
        if (Number.isInteger(of) && (of as number) >= 1) p.of = of as number;
        send({ type: "progress", progress: p });
      },
      busy: () => [...entries.keys()].some((id) => id !== entry.id),
    };
    let result: ResultEnvelope;
    try {
      const readback = await entry.op.run(entry.data as never, ctx);
      const why = validateReadback(entry.action, readback);
      result = why
        ? failure(entry.action, entry.id, INVALID_READBACK, `${UPDATE_HOW} (${entry.action} ${why})`)
        : { ok: true, action: entry.action, id: entry.id, readback };
      if (why) log("error", `WhyNot Cut: ${entry.action} produced an invalid readback: ${why}`);
    } catch (e) {
      if (e instanceof OpError) {
        result = failure(entry.action, entry.id, e.message, e.how);
      } else {
        const text = e instanceof Error ? e.message : String(e);
        result = failure(entry.action, entry.id, `Premiere failed while running ${entry.action}: ${text.replace(/\.$/, "")}.`,
          "Run the command again; if it repeats, restart Premiere Pro and send the WhyNot Cut log.");
      }
    }
    if (closed) return;
    answer(entry, result);
  }

  function onCommand(msg: Record<string, unknown>): void {
    const req = msg.request as Record<string, unknown> | undefined;
    if (!req || typeof req !== "object") return log("warn", "WhyNot Cut: a command without a request was ignored");
    const { id, action } = req;
    if (typeof id !== "string" || !ID_RE.test(id)) return log("warn", "WhyNot Cut: a command without a usable id was ignored");
    if (typeof action !== "string" || !(ACTION_NAMES as readonly string[]).includes(action)) {
      return log("warn", `WhyNot Cut: command ${id} names no contract action; ignored`);
    }
    const a = action as ActionName;
    if (entries.has(id)) return log("warn", `WhyNot Cut: command ${id} is already running; the repeat was ignored`);
    const op = ops[a];
    const entry: Entry = { id, action: a, op: op as Op<never>, data: req.data, cancelled: false, started: false, answered: false };
    if (!op || !capabilities.includes(a)) {
      return answer(entry, failure(a, id, `This WhyNot Cut panel does not run ${a}.`, "Run it through the WhyNot Cut Bridge (CEP), or update the panel."));
    }
    const expires = Date.parse(String(req.expires_at ?? ""));
    if (!Number.isFinite(expires) || expires <= Date.now()) {
      return answer(entry, failure(a, id, "The request expired before it could run.", "Run the command again."));
    }
    const why = validateData(a, req.data);
    if (why) return answer(entry, failure(a, id, `The request data is not valid for ${a}: ${why}.`, UPDATE_HOW));
    entries.set(id, entry);
    if (op.exclusive) {
      const turn = chain.then(() => execute(entry));
      chain = turn.catch(() => undefined);
    } else {
      void execute(entry);
    }
  }

  function onCancel(id: unknown): void {
    if (typeof id !== "string") return;
    const entry = entries.get(id);
    if (!entry) return;
    entry.cancelled = true;
    // a queued op is answered now; a running one answers when it stops (throwIfCancelled)
    if (!entry.started) answer(entry, failure(entry.action, id, "Cancelled before it started.", "Nothing was changed. Run the command again when you want it."));
  }

  function shutdown(): void {
    closed = true;
    for (const e of entries.values()) e.cancelled = true;
    entries.clear();
  }

  socket.onmessage = (ev: MessageEvent) => {
    if (closed || typeof ev?.data !== "string") return;
    let msg: unknown;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return log("warn", "WhyNot Cut: a message from the engine is not JSON; ignored");
    }
    if (!msg || typeof msg !== "object" || Array.isArray(msg)) return;
    const m = msg as Record<string, unknown>;
    switch (m.type) {
      case "command":
        return onCommand(m);
      case "cancel":
        return onCancel(m.id);
      case "welcome":
        sessionId = typeof m.session_id === "string" ? m.session_id : sessionId;
        log("info", `WhyNot Cut: connected to the engine as a Premiere host (${capabilities.join(", ")})`);
        opts.onWelcome?.(m as unknown as WelcomeMessage);
        return;
      case "error":
        log("warn", `WhyNot Cut: the engine refused a message (${String(m.code)}: ${String(m.message)})`);
        opts.onError?.(m as unknown as ErrorMessage);
        return;
      default:
        return; // state, reply, progress, result...: meant for panels and requesters, not for a host
    }
  };
  socket.onclose = () => {
    if (closed) return;
    shutdown();
    opts.onClose?.();
  };

  const hostVersion = hostVersionOf(env) || undefined;
  const hello: HelloMessage = {
    type: "hello",
    token: opts.token,
    client: {
      kind: "uxp",
      version: env.bundleVersion,
      host: "premiere",
      ...(hostVersion ? { hostVersion } : {}),
      protocol: PROTOCOL as 4,
      capabilities: [...capabilities],
    },
  };
  send(hello);

  return {
    capabilities,
    get sessionId() {
      return sessionId;
    },
    running: () => [...entries.keys()],
    stop: () => {
      if (closed) return;
      shutdown();
      socket.onmessage = null;
      socket.onclose = null;
      try {
        socket.close(1000, "WhyNot Cut panel closed");
      } catch {
        // already closed
      }
    },
  };
}
