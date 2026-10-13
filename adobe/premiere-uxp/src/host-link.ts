// The host link: keeps the Premiere host adapter (src/host-adapter.ts) connected to the engine daemon for as long as
// the plugin runs, so `reel` commands (and the panel's own commands) reach Premiere. Each attempt reads engine.json
// afresh (the port and token change on every daemon start), opens ws://localhost:<port>/session and, once the socket
// is open, hands it to startHostAdapter (which says hello as kind "uxp" with its capabilities). When the socket closes,
// fails to open or opens but never gets a welcome, the link waits and tries again: 1-2-4-8-15 s, the panel's backoff,
// reset by a welcome. It is independent of the panel's own (requester) session: hiding the panel does not stop it.
// Keepalive: the daemon pings a silent session after 30 s and closes it after 60 s, and whether UXP's WebSocket
// answers pings is unmeasured, so a connected host sends a `snapshot` every KEEPALIVE_MS itself (the daemon answers
// with `state`, which the host adapter ignores).
import { backoffMs, sessionUrl } from "../../panel-ui/src/daemon-source.ts";
import { startHostAdapter } from "./host-adapter.ts";
import type { HostAdapter } from "./host-adapter.ts";
import type { OpEnv } from "./ops/types.ts";
import type { WebSocketLike } from "./uxp-transport.ts";

export type HostLinkState = "connecting" | "connected" | "waiting" | "stopped";

export interface HostLinkOptions {
  /** the parsed engine.json (null when missing); may throw (= missing) */
  readEngineJson: () => unknown | Promise<unknown>;
  /** a new WebSocket to url (the global one in UXP) */
  openSocket: (url: string) => WebSocketLike;
  env: OpEnv;
  setTimer: (fn: () => void, ms: number) => () => void;
  /** how long an attempt may take from open to welcome (default 10 s) */
  connectTimeoutMs?: number;
  log?: (level: "info" | "warn" | "error", text: string) => void;
  onState?: (state: HostLinkState) => void;
}

export interface HostLink {
  readonly state: HostLinkState;
  /** the adapter of the current connection, null between connections */
  readonly adapter: HostAdapter | null;
  /** ends the link for good: closes the socket (cancelling every running op) and every timer */
  stop(): void;
}

export const HOST_CONNECT_TIMEOUT_MS = 10_000;
/** a connected host session sends a snapshot this often (the daemon closes a session silent for 60 s) */
export const KEEPALIVE_MS = 20_000;

function recordOf(raw: unknown): { port: number; token: string } | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const { port, token, protocol } = raw as Record<string, unknown>;
  if (typeof port !== "number" || !Number.isInteger(port) || port <= 0 || port >= 65536) return null;
  if (typeof token !== "string" || !/^[0-9a-f]{64}$/.test(token)) return null;
  if (protocol !== undefined && protocol !== 4) return null;
  return { port, token };
}

export function startHostLink(opts: HostLinkOptions): HostLink {
  const connectTimeout = opts.connectTimeoutMs ?? HOST_CONNECT_TIMEOUT_MS;
  let state: HostLinkState = "connecting";
  let stopped = false;
  let failures = 0;
  let gen = 0;
  let ws: WebSocketLike | null = null;
  let adapter: HostAdapter | null = null;
  let stopRetry: (() => void) | null = null;
  let stopConnect: (() => void) | null = null;
  let stopKeepalive: (() => void) | null = null;
  let keepaliveSeq = 0;
  let lastWhy = "";

  const log = (level: "info" | "warn" | "error", text: string) => {
    try {
      opts.log?.(level, text);
    } catch {
      // a logger never breaks the link
    }
  };
  const setState = (s: HostLinkState) => {
    if (state === s) return;
    state = s;
    try {
      opts.onState?.(s);
    } catch {
      // nor does a listener
    }
  };

  function clearTimers(): void {
    stopRetry?.();
    stopConnect?.();
    stopKeepalive?.();
    stopRetry = stopConnect = stopKeepalive = null;
  }

  /** every KEEPALIVE_MS while this connection is the current one and welcomed */
  function keepalive(g: number, sock: WebSocketLike): void {
    stopKeepalive = opts.setTimer(() => {
      stopKeepalive = null;
      if (stopped || g !== gen || ws !== sock || state !== "connected") return;
      try {
        sock.send(JSON.stringify({ type: "snapshot", id: `host-keepalive-${++keepaliveSeq}` }));
      } catch {
        return; // the close that follows retries
      }
      keepalive(g, sock);
    }, KEEPALIVE_MS);
  }

  function drop(): void {
    const a = adapter;
    const s = ws;
    adapter = null;
    ws = null;
    if (a) a.stop();
    else if (s) {
      s.onopen = s.onmessage = s.onerror = s.onclose = null;
      try {
        s.close(1000, "WhyNot Cut panel closed");
      } catch {
        // already closed
      }
    }
  }

  function retry(why: string): void {
    if (stopped) return;
    clearTimers();
    drop();
    failures++;
    const ms = backoffMs(failures);
    if (why !== lastWhy) log("warn", `WhyNot Cut: the Premiere link to the engine is down (${why}); trying again in ${Math.round(ms / 1000)} s`);
    lastWhy = why;
    setState("waiting");
    stopRetry = opts.setTimer(() => {
      stopRetry = null;
      void attempt();
    }, ms);
  }

  async function attempt(): Promise<void> {
    if (stopped) return;
    const g = ++gen;
    setState("connecting");
    let raw: unknown = null;
    try {
      raw = await opts.readEngineJson();
    } catch {
      raw = null;
    }
    if (stopped || g !== gen) return;
    if (raw === null || raw === undefined) return retry("the engine is not running");
    const rec = recordOf(raw);
    if (!rec) return retry("engine.json is not usable");
    let sock: WebSocketLike;
    try {
      sock = opts.openSocket(sessionUrl(rec.port));
    } catch {
      return retry("the connection could not be opened");
    }
    ws = sock;
    stopConnect = opts.setTimer(() => {
      if (g === gen && state !== "connected") retry("no welcome from the engine");
    }, connectTimeout);
    sock.onerror = () => {};
    sock.onclose = () => {
      if (g === gen && ws === sock) retry("the engine refused or closed the connection");
    };
    sock.onopen = () => {
      if (stopped || g !== gen || ws !== sock) return;
      adapter = startHostAdapter({
        socket: sock as unknown as Parameters<typeof startHostAdapter>[0]["socket"],
        token: rec.token,
        env: opts.env,
        log,
        onWelcome: () => {
          if (g !== gen) return;
          failures = 0;
          lastWhy = "";
          stopConnect?.();
          stopConnect = null;
          setState("connected");
          stopKeepalive?.();
          keepalive(g, sock);
        },
        onClose: () => {
          if (g !== gen) return;
          adapter = null;
          ws = null;
          retry("the engine closed the connection");
        },
      });
    };
  }

  void attempt();

  return {
    get state() {
      return state;
    },
    get adapter() {
      return adapter;
    },
    stop() {
      if (stopped) return;
      stopped = true;
      gen++;
      clearTimers();
      drop();
      setState("stopped");
    },
  };
}
