// Spike 0.1.6: the Addendum C2.7 ecosystem probes (one Claude <-> engine <-> Premiere ecosystem). Results go to the
// results file under `eco_probes`:
//   open_external       - uxp.shell.openExternal("whynotcut://engine/start"): what UXP does with a scheme that has no
//                          handler yet (resolved / rejected value, error text, elapsed ms: a consent dialog shows up as
//                          a long elapsed time). Mode "full" only.
//   quit_restart_names  - the property NAMES on require("premierepro"), its Application object and require("uxp").host
//                          (and uxp itself) that match /quit|exit|restart|relaunch|close/i. Names only: nothing found
//                          here is ever read or called (getters are not invoked either).
//   loopback            - with the spike manifest's explicit loopback network.domains (no "all"): a WebSocket to
//                          ws://{127.0.0.1,localhost}:<port>/session and a fetch of http://{127.0.0.1,localhost}:<port>/status,
//                          no token (a reachability check). Per form: allowed / denied and the error text.
//   hide_show           - the panel's lifecycle events (entrypoints panel create / show / hide / destroy, document
//                          visibilitychange) with timestamps, also kept in <spike dir>/lifecycle.json as they happen.
// The engine token is never recorded or logged: only the port is taken from engine.json, and every recorded text is
// passed through redact() with the token first.
import { ensureDir, readText, writeText } from "./fsutil.ts";
import type { ProbeDef } from "./runner.ts";
import { redact, type WsCtor, type WsLike } from "./ws-link.ts";
import { SPIKE_VERSION } from "./version.ts";
import type { UxpFs } from "../../src/uxp-types.ts";

// ---------------------------------------------------------------------------------------------- open_external

export const ENGINE_START_URL = "whynotcut://engine/start";
/** A call that takes at least this long was probably waiting for a click (Adobe's consent dialog). */
export const CONSENT_SUSPECT_MS = 1500;
export const OPEN_EXTERNAL_WHY = `WhyNot Cut spike ${SPIKE_VERSION} is measuring what happens when it asks to start the WhyNot Cut engine.`;

export interface EcoCtx {
  uxp: unknown;
  ppro: unknown;
  fs: UxpFs;
  home: string | null;
  WebSocket?: WsCtor;
  fetch?: (url: string, init?: unknown) => Promise<{ status: number; statusText?: string }>;
  now: () => number;
  timing?: { openExternalTimeoutMs?: number; wsWaitMs?: number; fetchTimeoutMs?: number };
  lifecycle?: LifecycleRecorder;
  lifecycleSetup?: LifecycleSetup;
}

const errText = (e: unknown): string => (e instanceof Error ? e.message : typeof e === "string" ? e : (() => {
  try {
    return JSON.stringify(e);
  } catch {
    return String(e);
  }
})());

function describeValue(v: unknown): { type: string; value: unknown } {
  if (v === undefined) return { type: "undefined", value: null };
  if (v === null) return { type: "null", value: null };
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return { type: typeof v, value: v };
  try {
    return { type: Array.isArray(v) ? "array" : typeof v, value: JSON.parse(JSON.stringify(v)) as unknown };
  } catch {
    return { type: typeof v, value: String(v) };
  }
}

export const openExternalProbe: ProbeDef<EcoCtx> = {
  op: "open_external",
  timeoutMs: 200_000,
  run: async (ctx) => {
    const shell = (ctx.uxp as { shell?: { openExternal?: (url: string, why?: string) => unknown } } | undefined)?.shell;
    const fn = shell?.openExternal;
    const head = { url: ENGINE_START_URL, developer_text: OPEN_EXTERNAL_WHY, handler_registered: false, consent_suspect_ms: CONSENT_SUSPECT_MS };
    if (typeof fn !== "function") return { ok: false, detail: { ...head, settled: "unavailable", error: `uxp.shell.openExternal is ${typeof fn}` } };
    const limit = ctx.timing?.openExternalTimeoutMs ?? 180_000;
    const t0 = ctx.now();
    const calledAt = new Date(t0).toISOString();
    let settled: "resolved" | "rejected" | "threw" | "timeout";
    let value: { type: string; value: unknown } | null = null;
    let error: string | null = null;
    try {
      const p = Promise.resolve(fn.call(shell, ENGINE_START_URL, OPEN_EXTERNAL_WHY));
      let timer: ReturnType<typeof setTimeout> | undefined;
      const r = await Promise.race([
        p.then((v) => ({ kind: "resolved" as const, v }), (e: unknown) => ({ kind: "rejected" as const, e })),
        new Promise<{ kind: "timeout" }>((res) => {
          timer = setTimeout(() => res({ kind: "timeout" }), limit);
        }),
      ]);
      if (timer !== undefined) clearTimeout(timer);
      settled = r.kind;
      if (r.kind === "resolved") value = describeValue(r.v);
      if (r.kind === "rejected") error = errText(r.e);
    } catch (e) {
      settled = "threw";
      error = errText(e);
    }
    const elapsed = ctx.now() - t0;
    const detail = {
      ...head,
      called_at: calledAt,
      settled,
      elapsed_ms: elapsed,
      value,
      // UXP's openExternal resolves with "" on success and an error text otherwise (docs); record both shapes
      value_is_empty_string: value?.value === "",
      error,
      consent_dialog_suspected: elapsed >= CONSENT_SUSPECT_MS,
      timeout_ms: limit,
      note: "no whynotcut:// handler is registered on this machine yet: this records what UXP and the OS do with an unknown scheme. Whether a dialog was really shown is not visible to the probe (timing only)",
    };
    return { ok: settled === "resolved" ? true : settled === "timeout" ? null : false, detail };
  },
};

// ---------------------------------------------------------------------------------------------- quit / restart names

export const QUIT_NAME_RX = /quit|exit|restart|relaunch|close/i;

/** Own + inherited property names of `target` (stops at Object.prototype / Function.prototype). Reads NO values. */
export function propertyNames(target: unknown): string[] {
  const names = new Set<string>();
  const stopAt = new Set<unknown>([Object.prototype, Function.prototype, null]);
  let o: unknown = target;
  for (let depth = 0; depth < 8 && o !== null && o !== undefined && (typeof o === "object" || typeof o === "function") && !stopAt.has(o); depth++) {
    try {
      for (const n of Object.getOwnPropertyNames(o)) names.add(n);
    } catch {
      break;
    }
    try {
      o = Object.getPrototypeOf(o);
    } catch {
      break;
    }
  }
  return [...names].sort();
}

/** Where `name` sits on `target`'s chain and what kind it is, from the property descriptor only (no getter runs, nothing is called). */
function kindOf(target: unknown, name: string): string {
  let o: unknown = target;
  for (let depth = 0; depth < 8 && o !== null && o !== undefined; depth++) {
    let d: PropertyDescriptor | undefined;
    try {
      d = Object.getOwnPropertyDescriptor(o, name);
    } catch {
      return "unknown";
    }
    if (d) {
      if (d.get || d.set) return `accessor${d.get ? " get" : ""}${d.set ? " set" : ""}`;
      return typeof d.value === "function" ? "function" : typeof d.value;
    }
    try {
      o = Object.getPrototypeOf(o);
    } catch {
      return "unknown";
    }
  }
  return "unknown";
}

/** Reads one non-matching member (e.g. "Application") through its descriptor value or getter. Never a matching name. */
function member(target: unknown, name: string): unknown {
  if (QUIT_NAME_RX.test(name)) throw new Error(`refusing to read ${name}: it matches the quit/restart pattern`);
  if (target === null || target === undefined) return undefined;
  try {
    return (target as Record<string, unknown>)[name];
  } catch {
    return undefined;
  }
}

export const quitRestartNamesProbe: ProbeDef<EcoCtx> = {
  op: "quit_restart_names",
  run: async (ctx) => {
    const targets: Array<[string, unknown]> = [];
    const ppro = ctx.ppro;
    const uxp = ctx.uxp;
    targets.push(["premierepro", ppro]);
    for (const name of ["Application", "App", "app"]) {
      const v = member(ppro, name);
      if (v !== undefined && v !== null) {
        targets.push([`premierepro.${name}`, v]);
        const proto = typeof v === "function" ? member(v, "prototype") : undefined;
        if (proto) targets.push([`premierepro.${name}.prototype`, proto]);
      }
    }
    targets.push(["uxp", uxp]);
    targets.push(["uxp.host", member(uxp, "host")]);
    const scanned: Array<Record<string, unknown>> = [];
    let total = 0;
    for (const [path, target] of targets) {
      if (target === undefined || target === null) {
        scanned.push({ path, present: false });
        continue;
      }
      const names = propertyNames(target);
      const matches = names.filter((n) => QUIT_NAME_RX.test(n)).map((n) => ({ name: n, kind: kindOf(target, n) }));
      total += matches.length;
      scanned.push({ path, present: true, type: typeof target, names_count: names.length, names: names.slice(0, 300), matches });
    }
    return {
      ok: true,
      detail: { pattern: String(QUIT_NAME_RX), matches_total: total, called: false, rule: "names only: no matching member was read or called", scanned },
    };
  },
};

// ---------------------------------------------------------------------------------------------- loopback

/** The spike manifest's network.domains (test/spike-016.test.ts keeps the two equal). */
export const LOOPBACK_DOMAINS: readonly string[] = [
  // port wildcard forms (the form this probe is about)
  "ws://127.0.0.1:*",
  "ws://localhost:*",
  "http://127.0.0.1:*",
  "http://localhost:*",
  // the exact port-less forms; ws://127.0.0.1 and http://127.0.0.1 are the round-1 entries that failed (parity W1/W2)
  "ws://127.0.0.1",
  "ws://localhost",
  "http://127.0.0.1",
  "http://localhost",
];

const DENIED_RX = /permission denied|manifest entry not found/i;

export interface LoopbackForm {
  form: string;
  kind: "ws" | "http";
  host: "127.0.0.1" | "localhost";
}

export const LOOPBACK_FORMS: readonly LoopbackForm[] = [
  { form: "ws://127.0.0.1:<port>/session", kind: "ws", host: "127.0.0.1" },
  { form: "ws://localhost:<port>/session", kind: "ws", host: "localhost" },
  { form: "http://127.0.0.1:<port>/status", kind: "http", host: "127.0.0.1" },
  { form: "http://localhost:<port>/status", kind: "http", host: "localhost" },
];

/** engine.json's port only. The token is returned for redaction and nothing else; it never enters a result. */
async function enginePort(fs: UxpFs, home: string): Promise<{ port: number; token: string; path: string }> {
  const path = `${home}/.whynot-cut/bridge/engine.json`;
  const text = await readText(fs, path);
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(text.replace(/^﻿/, "")) as Record<string, unknown>;
  } catch (e) {
    // V8's message quotes part of the file (it can hold part of the token): never record it
    throw new Error(`engine.json is not valid JSON (${e instanceof Error ? e.name : "parse error"})`);
  }
  const port = parsed?.port;
  const token = typeof parsed?.token === "string" ? parsed.token : "";
  if (typeof port !== "number" || !Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`engine.json has no valid port (keys: ${Object.keys(parsed ?? {}).join(", ")})`);
  return { port, token, path };
}

async function tryWs(WS: WsCtor | undefined, url: string, waitMs: number, now: () => number, token: string): Promise<Record<string, unknown>> {
  const t0 = now();
  if (typeof WS !== "function") return { allowed: null, outcome: "no WebSocket global", error: null, ms: 0 };
  let ws: WsLike;
  try {
    ws = new WS(url);
  } catch (e) {
    const msg = redact(errText(e), token);
    return { allowed: DENIED_RX.test(msg) ? false : null, outcome: "constructor threw", error: msg, ms: now() - t0 };
  }
  const ev = await new Promise<{ kind: "open" | "error" | "close" | "timeout"; code?: number | null; reason?: string; message?: string }>((resolve) => {
    let done = false;
    const finish = (v: { kind: "open" | "error" | "close" | "timeout"; code?: number | null; reason?: string; message?: string }) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(v);
    };
    const timer = setTimeout(() => finish({ kind: "timeout" }), waitMs);
    ws.onopen = () => finish({ kind: "open" });
    ws.onerror = (e: unknown) => {
      const m = (e as { message?: unknown } | null)?.message;
      finish({ kind: "error", ...(typeof m === "string" ? { message: m } : {}) });
    };
    ws.onclose = (e) => finish({ kind: "close", code: typeof e?.code === "number" ? e.code : null, reason: typeof e?.reason === "string" ? e.reason : "" });
  });
  const ms = now() - t0;
  try {
    ws.onopen = null;
    ws.onerror = null;
    ws.onclose = null;
    ws.onmessage = null;
    ws.close(1000, "spike loopback probe");
  } catch {
    // already closed
  }
  if (ev.kind === "open") return { allowed: true, outcome: "open", error: null, ms };
  const message = ev.message ? redact(ev.message, token) : null;
  if (message && DENIED_RX.test(message)) return { allowed: false, outcome: ev.kind, error: message, ms };
  return {
    allowed: null,
    outcome: ev.kind === "timeout" ? `no open / error / close within ${waitMs} ms` : `${ev.kind} before open`,
    error: message,
    ...(ev.kind === "close" ? { close_code: ev.code ?? null, close_reason: redact(ev.reason ?? "", token) } : {}),
    ms,
    note: "the request was not refused by the manifest (no permission error) but did not open: it probably reached the daemon, which refused the upgrade; see serve-audit.log",
  };
}

async function tryFetch(f: EcoCtx["fetch"], url: string, timeoutMs: number, now: () => number, token: string): Promise<Record<string, unknown>> {
  const t0 = now();
  if (typeof f !== "function") return { allowed: null, outcome: "no fetch global", error: null, ms: 0 };
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    // no Authorization header: a reachability check (401 still proves the request left Premiere)
    const res = await Promise.race([
      f(url),
      new Promise<never>((_, rej) => {
        timer = setTimeout(() => rej(new Error(`fetch timed out after ${timeoutMs} ms`)), timeoutMs);
      }),
    ]);
    return { allowed: true, outcome: "response", status: res.status, status_text: typeof res.statusText === "string" ? redact(res.statusText, token) : null, error: null, ms: now() - t0 };
  } catch (e) {
    const msg = redact(errText(e), token);
    return { allowed: DENIED_RX.test(msg) ? false : null, outcome: "rejected", error: msg, ms: now() - t0 };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export const loopbackProbe: ProbeDef<EcoCtx> = {
  op: "loopback",
  timeoutMs: 60_000,
  run: async (ctx) => {
    const head = { manifest_domains: LOOPBACK_DOMAINS, denied_pattern: String(DENIED_RX), token_sent: false };
    if (!ctx.home) return { ok: null, detail: { ...head, error: "no home folder: cannot locate ~/.whynot-cut/bridge/engine.json" } };
    let eng: { port: number; token: string; path: string };
    try {
      eng = await enginePort(ctx.fs, ctx.home);
    } catch (e) {
      return { ok: null, detail: { ...head, error: `engine.json not usable: ${errText(e)} (start the daemon with: reel serve --ensure)` } };
    }
    const { port, token } = eng;
    const forms: Array<Record<string, unknown>> = [];
    for (const f of LOOPBACK_FORMS) {
      const url = f.form.replace("<port>", String(port));
      const r = f.kind === "ws" ? await tryWs(ctx.WebSocket, url, ctx.timing?.wsWaitMs ?? 5000, ctx.now, token) : await tryFetch(ctx.fetch, url, ctx.timing?.fetchTimeoutMs ?? 5000, ctx.now, token);
      forms.push({ form: f.form, url, kind: f.kind, host: f.host, ...r });
    }
    const allowed = (kind: string, host: string) => forms.find((x) => x.kind === kind && x.host === host)?.allowed;
    const ws127 = allowed("ws", "127.0.0.1");
    const http127 = allowed("http", "127.0.0.1");
    // ok = the two forms the product uses (127.0.0.1) both got past the manifest
    const ok = ws127 === true && http127 === true ? true : ws127 === false || http127 === false ? false : null;
    return { ok, detail: { ...head, engine_json: eng.path, port, forms } };
  },
};

// ---------------------------------------------------------------------------------------------- hide / show

export interface LifecycleEvent {
  seq: number;
  event: string;
  at: string;
  /** ms since the panel script loaded */
  t_ms: number;
  detail?: unknown;
}

export interface LifecycleRecorder {
  record(event: string, detail?: unknown): void;
  events(): LifecycleEvent[];
}

export const LIFECYCLE_MAX = 200;

/** Keeps the last LIFECYCLE_MAX events; `persist` (lifecycle.json) is called after each one and must not throw. */
export function createLifecycle(now: () => number, persist?: (events: LifecycleEvent[]) => void): LifecycleRecorder {
  const start = now();
  const list: LifecycleEvent[] = [];
  let seq = 0;
  return {
    record(event, detail) {
      const t = now();
      list.push({ seq: ++seq, event, at: new Date(t).toISOString(), t_ms: t - start, ...(detail === undefined ? {} : { detail }) });
      if (list.length > LIFECYCLE_MAX) list.splice(0, list.length - LIFECYCLE_MAX);
      try {
        persist?.(list.slice());
      } catch {
        // recording never breaks the panel
      }
    },
    events: () => list.slice(),
  };
}

export interface LifecycleSetup {
  entrypoints_setup: "called" | "unavailable" | "threw";
  error?: string;
  panel_id: string;
  listeners: string[];
}

/** What UXP passes a panel callback, reduced to plain data (it may be a root node or an event object). */
function argInfo(args: unknown[]): unknown {
  return args.map((a) => {
    if (a === null || a === undefined) return String(a);
    if (typeof a !== "object") return typeof a;
    const o = a as Record<string, unknown>;
    const node = (o.node ?? o) as { tagName?: unknown; nodeName?: unknown };
    return { keys: Object.keys(o).slice(0, 20), tag: typeof node.tagName === "string" ? node.tagName : typeof node.nodeName === "string" ? node.nodeName : null };
  });
}

/** Registers the panel's create / show / hide / destroy with entrypoints.setup (once, at load) and document visibilitychange. */
export function setupLifecycle(uxp: unknown, panelId: string, rec: LifecycleRecorder, doc?: { addEventListener?: (t: string, l: () => void) => void; visibilityState?: string }): LifecycleSetup {
  const listeners: string[] = [];
  const out: LifecycleSetup = { entrypoints_setup: "unavailable", panel_id: panelId, listeners };
  const entrypoints = (uxp as { entrypoints?: { setup?: (cfg: unknown) => unknown } } | undefined)?.entrypoints;
  if (typeof entrypoints?.setup === "function") {
    const cb = (name: string) => (...args: unknown[]) => void rec.record(`panel.${name}`, argInfo(args));
    try {
      entrypoints.setup({ panels: { [panelId]: { create: cb("create"), show: cb("show"), hide: cb("hide"), destroy: cb("destroy") } } });
      out.entrypoints_setup = "called";
      listeners.push("panel.create", "panel.show", "panel.hide", "panel.destroy");
    } catch (e) {
      out.entrypoints_setup = "threw";
      out.error = errText(e);
    }
  }
  if (typeof doc?.addEventListener === "function") {
    try {
      doc.addEventListener("visibilitychange", () => rec.record("document.visibilitychange", { visibilityState: doc.visibilityState ?? null }));
      listeners.push("document.visibilitychange");
    } catch {
      // not available
    }
  }
  rec.record("script.loaded", { listeners: listeners.slice(), entrypoints_setup: out.entrypoints_setup });
  return out;
}

/** Writes lifecycle.json (best effort, never throws). 0.1.7: makes the spike folder first (the panel loads, and
 *  script.loaded is recorded, before any run has created ~/.whynot-cut/uxp-spike on a fresh machine). */
export function lifecycleWriter(fs: UxpFs, dir: string): (events: LifecycleEvent[]) => void {
  let chain: Promise<void> = Promise.resolve();
  return (events) => {
    const body = JSON.stringify({ spike: SPIKE_VERSION, updated_at: new Date().toISOString(), events }, null, 2);
    chain = chain
      .then(async () => {
        await ensureDir(fs, dir);
        await writeText(fs, `${dir}/lifecycle.json`, body);
      })
      .catch(() => {});
  };
}

export const hideShowProbe: ProbeDef<EcoCtx> = {
  op: "hide_show",
  run: async (ctx) => {
    const setup = ctx.lifecycleSetup ?? null;
    const events = ctx.lifecycle?.events() ?? [];
    const order = events.map((e) => e.event);
    return {
      ok: setup?.entrypoints_setup === "threw" ? false : setup?.entrypoints_setup === "called" ? true : null,
      detail: {
        setup,
        events,
        order,
        file: "lifecycle.json next to the results (updated on every event, so hiding and showing the panel after the run is recorded too)",
        how: "dock the panel in a tab group, switch to another tab and back (hide/show), or close and reopen it from Window > UXP Plugins; then read lifecycle.json",
      },
    };
  },
};
