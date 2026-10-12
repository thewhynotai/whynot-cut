// The UXP side of the engine link: what DaemonSource (the panel, a requester) and the host link (the Premiere ops, a
// host) need from the plugin runtime, built from injected globals so node tests run it on fakes and on Node's own
// WebSocket / fetch / fs (test/daemon-e2e.test.ts).
//   - engine.json: <os.homedir()>/.whynot-cut/bridge/engine.json through UXP fs (readFile with {encoding: "utf-8"},
//     the form the spike measured, else readFileSync(path, "utf-8")); bytes are decoded by hand when the runtime has
//     no TextDecoder (UXP). Missing -> null (DaemonSource retries); there but not JSON -> {} (a damaged file).
//     The discovery copy of a daemon serving another engine home looks the same (plus `home`): it is used as is.
//   - WebSocket: the global one (UXP has it, parity P1), wrapped to DaemonSocket for the panel; the host adapter takes
//     the raw socket (it fits HostSocket).
//   - GET /status: the global fetch with only the Authorization header; a fetch that throws is passed on (DaemonSource
//     calls it "blocked": engine.json names a port the panel cannot reach), no answer in time is null. The panel never
//     sets an Origin; whether UXP's
//     fetch adds one by itself is measured live (spike 0.1.3): if it does and the daemon refuses it, /status answers
//     403 and the panel says "refused (Host / Origin)", which is also the right diagnosis for the refused WebSocket.
// Nothing here logs, stores or returns the token except inside the parsed engine.json handed to its two users.
import type { DaemonSocket, DaemonTransport } from "../../panel-ui/src/daemon-source.ts";
import type { UxpFs, UxpOs } from "./uxp-types.ts";

/** A browser / UXP / Node WebSocket: property handlers, text frames. */
export interface WebSocketLike {
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  send(text: string): void;
  close(code?: number, reason?: string): void;
}
export type WebSocketCtor = new (url: string) => WebSocketLike;
export type FetchFn = (url: string, init: { method?: string; headers: Record<string, string> }) => Promise<{ status: number }>;

export interface LinkGlobals {
  /** UXP require("fs") (undefined when it cannot be loaded) */
  fs: UxpFs | undefined;
  /** UXP require("os") */
  os: UxpOs | undefined;
  WebSocket: WebSocketCtor | undefined;
  fetch: FetchFn | undefined;
  setTimeout: (fn: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
  now: () => number;
  /** console sink for link events (already free of the token) */
  log?: (line: string) => void;
}

/** How long the /status probe may take before it counts as "nothing answers". */
export const STATUS_TIMEOUT_MS = 3000;

/** The user's home folder with forward slashes and no trailing slash, or null. */
export function homeOf(os: UxpOs | undefined): string | null {
  try {
    const h = typeof os?.homedir === "function" ? String(os.homedir() ?? "") : "";
    const clean = h.trim().replace(/\\/g, "/").replace(/\/+$/, "");
    return clean || null;
  } catch {
    return null;
  }
}

/** <home>/.whynot-cut/bridge/engine.json, the only place the panel can find the daemon by itself. */
export function engineJsonPath(home: string): string {
  return `${home.replace(/\\/g, "/").replace(/\/+$/, "")}/.whynot-cut/bridge/engine.json`;
}

/** UTF-8 bytes to text: TextDecoder when the runtime has it (UXP does not), else by hand (invalid bytes -> U+FFFD). */
export function decodeUtf8(data: ArrayBuffer | ArrayBufferView): string {
  const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  const TD = (globalThis as { TextDecoder?: new () => { decode(b: Uint8Array): string } }).TextDecoder;
  if (typeof TD === "function") return new TD().decode(bytes);
  const BAD = "�";
  let out = "";
  for (let i = 0; i < bytes.length; ) {
    const b = bytes[i]!;
    if (b < 0x80) {
      out += String.fromCharCode(b);
      i += 1;
      continue;
    }
    // continuation bytes after a lead byte: 110xxxxx -> 1, 1110xxxx -> 2, 11110xxx -> 3
    const need = b >= 0xf0 && b < 0xf8 ? 3 : b >= 0xe0 && b < 0xf0 ? 2 : b >= 0xc0 && b < 0xe0 ? 1 : 0;
    if (need === 0 || i + need >= bytes.length) {
      out += BAD;
      i += 1;
      continue;
    }
    let cp = b & (0x3f >> need);
    let ok = true;
    for (let k = 1; k <= need; k++) {
      const c = bytes[i + k]!;
      if ((c & 0xc0) !== 0x80) ok = false;
      cp = (cp << 6) | (c & 0x3f);
    }
    if (!ok || cp > 0x10ffff) {
      out += BAD;
      i += 1;
      continue;
    }
    out += String.fromCodePoint(cp);
    i += need + 1;
  }
  return out;
}

async function readText(fs: UxpFs, path: string): Promise<string> {
  let data: string | ArrayBuffer | ArrayBufferView;
  if (typeof fs.readFile === "function") data = await fs.readFile(path, { encoding: "utf-8" });
  else if (typeof fs.readFileSync === "function") data = fs.readFileSync(path, "utf-8");
  else throw new Error("UXP fs cannot read files here");
  return typeof data === "string" ? data : decodeUtf8(data);
}

/** The parsed engine.json: null when it is missing or unreadable, {} when it is there but not a JSON object. */
export async function readEngineJson(fs: UxpFs | undefined, os: UxpOs | undefined): Promise<unknown> {
  const home = homeOf(os);
  if (!fs || !home) return null;
  let text: string;
  try {
    text = await readText(fs, engineJsonPath(home));
  } catch {
    return null;
  }
  try {
    const v: unknown = JSON.parse(text.replace(/^﻿/, ""));
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch {
    return {};
  }
}

/** The real socket as DaemonSource's DaemonSocket: text frames only; `error` needs no mapping (close follows it). */
export function wrapSocket(ws: WebSocketLike): DaemonSocket {
  const s: DaemonSocket = {
    send: (text) => ws.send(text),
    close: (code, reason) => ws.close(code, reason),
    onopen: null,
    onmessage: null,
    onclose: null,
  };
  ws.onopen = () => s.onopen?.();
  ws.onmessage = (ev) => {
    if (typeof ev?.data === "string") s.onmessage?.(ev.data);
  };
  ws.onerror = () => {};
  ws.onclose = (ev) => s.onclose?.(typeof ev?.code === "number" ? ev.code : 1006, String(ev?.reason ?? ""));
  return s;
}

/** run fn once after ms; returns the function that cancels it */
export function timerOf(g: Pick<LinkGlobals, "setTimeout" | "clearTimeout">): (fn: () => void, ms: number) => () => void {
  return (fn, ms) => {
    const h = g.setTimeout(fn, ms);
    return () => g.clearTimeout(h);
  };
}

/** GET url with these headers: the HTTP status, null when nothing answers within STATUS_TIMEOUT_MS; a fetch that
 *  throws (the port is blocked or refused) rejects, which DaemonSource diagnoses as "blocked". */
export function statusProbe(g: Pick<LinkGlobals, "fetch" | "setTimeout" | "clearTimeout">): ((url: string, headers: { Authorization: string }) => Promise<number | null>) | undefined {
  const f = g.fetch;
  if (typeof f !== "function") return undefined;
  return async (url, headers) => {
    let stop: (() => void) | null = null;
    try {
      const timeout = new Promise<null>((resolve) => {
        const h = g.setTimeout(() => resolve(null), STATUS_TIMEOUT_MS);
        stop = () => g.clearTimeout(h);
      });
      // only Authorization: never an Origin (the daemon refuses browser origins)
      const res = await Promise.race([f(url, { method: "GET", headers: { Authorization: headers.Authorization } }), timeout]);
      return res && typeof res.status === "number" ? res.status : null;
    } finally {
      (stop as (() => void) | null)?.();
    }
  };
}

/** The DaemonTransport over the UXP runtime, or null when it has no WebSocket, no fs or no home folder (the shell then
 *  mounts the offline source). */
export function createDaemonTransport(g: LinkGlobals): DaemonTransport | null {
  const WS = g.WebSocket;
  if (typeof WS !== "function" || !g.fs || !homeOf(g.os)) return null;
  const probe = statusProbe(g);
  const t: DaemonTransport = {
    readEngineJson: () => readEngineJson(g.fs, g.os),
    openSocket: (url) => wrapSocket(new WS(url)),
    now: g.now,
    setTimer: timerOf(g),
  };
  if (probe) t.httpGetStatus = probe;
  if (g.log) t.log = g.log;
  return t;
}
