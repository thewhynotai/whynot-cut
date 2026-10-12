// The UXP transports (src/uxp-transport.ts) and the host link (src/host-link.ts) on fakes: engine.json through UXP fs
// and os.homedir(), the WebSocket wrapper DaemonSource gets, the /status probe (Authorization only, never an Origin),
// and the host link's connect -> hello (kind uxp) -> welcome -> reconnect-with-backoff cycle.
import { test } from "node:test";
import assert from "node:assert/strict";
import { startHostLink } from "../src/host-link.ts";
import type { HostLinkState } from "../src/host-link.ts";
import { createDaemonTransport, engineJsonPath, homeOf, readEngineJson, statusProbe, wrapSocket } from "../src/uxp-transport.ts";
import type { LinkGlobals, WebSocketLike } from "../src/uxp-transport.ts";
import { CAPABILITIES } from "../src/ops/index.ts";
import { SEQ, WIN_PROJECT, makeEnv } from "./host-adapter.fakes.ts";

const TOKEN = "c3".repeat(32);
const REC = { port: 51234, token: TOKEN, pid: 1, version: "3.0.0", protocol: 4 };
const flush = async () => {
  for (let i = 0; i < 8; i++) await new Promise<void>((r) => setImmediate(r));
};

class FakeWs implements WebSocketLike {
  static all: FakeWs[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sent: Array<Record<string, unknown>> = [];
  closed: { code?: number; reason?: string } | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeWs.all.push(this);
  }
  send(text: string): void {
    this.sent.push(JSON.parse(text));
  }
  close(code?: number, reason?: string): void {
    this.closed = { code, reason };
  }
  // daemon side
  open(): void {
    this.onopen?.({});
  }
  deliver(msg: unknown): void {
    this.onmessage?.({ data: JSON.stringify(msg) } as MessageEvent);
  }
  drop(code = 1006, reason = ""): void {
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

class Timers {
  t = 0;
  list: { at: number; fn: () => void; live: boolean }[] = [];
  setTimer = (fn: () => void, ms: number) => {
    const x = { at: this.t + ms, fn, live: true };
    this.list.push(x);
    return () => void (x.live = false);
  };
  pending(): number[] {
    return this.list.filter((x) => x.live).map((x) => x.at - this.t);
  }
  async advance(ms: number): Promise<void> {
    const end = this.t + ms;
    await flush();
    for (;;) {
      const due = this.list.filter((x) => x.live && x.at <= end).sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      due.live = false;
      this.t = due.at;
      due.fn();
      await flush();
    }
    this.t = end;
    await flush();
  }
}

// ---- engine.json / home ------------------------------------------------------------------------------------------

test("engine.json: <os.homedir()>/.whynot-cut/bridge/engine.json read with utf-8 (readFile, else readFileSync)", async () => {
  assert.equal(homeOf({ homedir: () => "C:\\Users\\Ed\\" }), "C:/Users/Ed");
  assert.equal(homeOf({ homedir: () => { throw new Error("x"); } }), null);
  assert.equal(homeOf(undefined), null);
  assert.equal(engineJsonPath("C:/Users/Ed"), "C:/Users/Ed/.whynot-cut/bridge/engine.json");
  const reads: Array<[string, unknown]> = [];
  const fs = {
    readFile: async (p: string, o?: unknown) => {
      reads.push([p, o]);
      return `\uFEFF${JSON.stringify(REC)}`;
    },
  };
  assert.deepEqual(await readEngineJson(fs, { homedir: () => "C:\\Users\\Ed" }), REC);
  assert.deepEqual(reads, [["C:/Users/Ed/.whynot-cut/bridge/engine.json", { encoding: "utf-8" }]]);
  const sync = { readFileSync: () => JSON.stringify(REC) };
  assert.deepEqual(await readEngineJson(sync, { homedir: () => "/Users/ed" }), REC);
});

test("engine.json: missing -> null (the daemon is not running); not JSON or not an object -> {} (a damaged file)", async () => {
  const os = { homedir: () => "/Users/ed" };
  assert.equal(await readEngineJson({ readFile: async () => { throw new Error("ENOENT"); } }, os), null);
  assert.equal(await readEngineJson({}, os), null);
  assert.equal(await readEngineJson(undefined, os), null);
  assert.equal(await readEngineJson({ readFile: async () => "{}" }, undefined), null);
  assert.deepEqual(await readEngineJson({ readFile: async () => `{"port": 1, "token": "${TOKEN}"` }, os), {});
  assert.deepEqual(await readEngineJson({ readFile: async () => "[1,2]" }, os), {});
});

// ---- the transport DaemonSource gets -------------------------------------------------------------------------------

function globals(over: Partial<LinkGlobals> = {}): LinkGlobals {
  return {
    fs: { readFile: async () => JSON.stringify(REC) },
    os: { homedir: () => "/Users/ed" },
    WebSocket: FakeWs,
    fetch: undefined,
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    now: () => 1_000,
    ...over,
  };
}

test("createDaemonTransport: null without a WebSocket, fs or home folder (the shell mounts the offline source)", () => {
  assert.equal(createDaemonTransport(globals({ WebSocket: undefined })), null);
  assert.equal(createDaemonTransport(globals({ fs: undefined })), null);
  assert.equal(createDaemonTransport(globals({ os: { homedir: () => "" } })), null);
  const t = createDaemonTransport(globals());
  assert.ok(t);
  assert.equal(t.httpGetStatus, undefined, "no fetch -> no probe (diagnosis 'unreachable')");
  assert.equal(t.now(), 1_000);
});

test("wrapSocket: open / text messages / close(code, reason) reach DaemonSource's handlers; binary frames are dropped", () => {
  FakeWs.all = [];
  const t = createDaemonTransport(globals())!;
  const s = t.openSocket("ws://127.0.0.1:51234/session");
  const ws = FakeWs.all[0]!;
  assert.equal(ws.url, "ws://127.0.0.1:51234/session");
  const seen: unknown[] = [];
  s.onopen = () => seen.push("open");
  s.onmessage = (text) => seen.push(text);
  s.onclose = (code, reason) => seen.push([code, reason]);
  ws.open();
  ws.onmessage?.({ data: '{"type":"welcome"}' } as MessageEvent);
  ws.onmessage?.({ data: new ArrayBuffer(4) } as MessageEvent);
  ws.onerror?.({});
  ws.onclose?.({ code: 1008, reason: "authentication required" } as CloseEvent);
  ws.onclose?.({} as CloseEvent);
  assert.deepEqual(seen, ["open", '{"type":"welcome"}', [1008, "authentication required"], [1006, ""]]);
  s.send("{\"type\":\"snapshot\"}");
  assert.deepEqual(ws.sent, [{ type: "snapshot" }]);
  s.close(1000, "panel closed");
  assert.deepEqual(ws.closed, { code: 1000, reason: "panel closed" });
  assert.ok(wrapSocket(new FakeWs("u")));
});

test("the /status probe: GET with the Authorization header only (never an Origin); a throw or a hang is null", async () => {
  const calls: Array<[string, unknown]> = [];
  const probe = statusProbe(globals({
    fetch: async (url, init) => {
      calls.push([url, init]);
      return { status: 403 };
    },
  }))!;
  assert.equal(await probe("http://127.0.0.1:51234/status", { Authorization: `Bearer ${TOKEN}` }), 403);
  assert.deepEqual(calls, [["http://127.0.0.1:51234/status", { method: "GET", headers: { Authorization: `Bearer ${TOKEN}` } }]]);
  const failing = statusProbe(globals({ fetch: async () => { throw new Error("ECONNREFUSED"); } }))!;
  assert.equal(await failing("http://127.0.0.1:1/status", { Authorization: "Bearer x" }), null);
  let fire: (() => void) | null = null;
  const hanging = statusProbe(globals({
    fetch: () => new Promise(() => {}),
    setTimeout: (fn) => ((fire = fn), 1),
    clearTimeout: () => {},
  }))!;
  const p = hanging("http://127.0.0.1:2/status", { Authorization: "Bearer x" });
  (fire as unknown as () => void)();
  assert.equal(await p, null);
  assert.equal(statusProbe(globals({ fetch: undefined })), undefined);
});

// ---- host link -------------------------------------------------------------------------------------------------------

function hostRig(engine: { value: unknown }) {
  FakeWs.all = [];
  const timers = new Timers();
  const states: HostLinkState[] = [];
  const logs: string[] = [];
  const e = makeEnv();
  e.pp.addOpen(WIN_PROJECT, [{ name: SEQ }]);
  const link = startHostLink({
    readEngineJson: async () => engine.value,
    openSocket: (url) => new FakeWs(url),
    env: e.env,
    setTimer: timers.setTimer,
    onState: (s) => states.push(s),
    log: (_l, t) => logs.push(t),
  });
  return { link, timers, states, logs, e };
}

const welcome = { type: "welcome", session_id: "s-0123456789abcdef", protocol: 4, daemon_version: "3.0.0" };

test("host link: engine.json -> ws://127.0.0.1:<port>/session -> hello kind uxp with the capabilities -> welcome = connected", async () => {
  const r = hostRig({ value: REC });
  await flush();
  const ws = FakeWs.all[0]!;
  assert.equal(ws.url, "ws://127.0.0.1:51234/session");
  assert.equal(r.link.state, "connecting");
  ws.open();
  const hello = ws.sent[0] as { type: string; token: string; client: Record<string, unknown> };
  assert.equal(hello.type, "hello");
  assert.equal(hello.token, TOKEN);
  assert.deepEqual(hello.client, { kind: "uxp", version: "3.0.0", host: "premiere", hostVersion: "26.5.2", protocol: 4, capabilities: [...CAPABILITIES] });
  ws.deliver(welcome);
  assert.equal(r.link.state, "connected");
  assert.ok(r.link.adapter);
  // a command through the link is answered on the same socket
  ws.deliver({ type: "command", request: { protocol: 4, id: "c-1", action: "set_player_position", data: { sequence_name: SEQ, t_s: 2 }, expires_at: new Date(Date.now() + 60_000).toISOString() } });
  await flush();
  const res = ws.sent.find((m) => m["type"] === "result") as { result: Record<string, unknown> } | undefined;
  assert.deepEqual(res?.result, { ok: true, action: "set_player_position", id: "c-1", readback: { position_s: 2 } });
  r.link.stop();
  assert.equal(r.link.state, "stopped");
  assert.deepEqual(ws.closed, { code: 1000, reason: "WhyNot Cut panel closed" });
  assert.deepEqual(r.timers.pending(), [], "no timer left behind");
});

test("host link: no engine.json / a refused socket / a closed session -> back off 1-2-4 s, re-read engine.json; a welcome resets it", async () => {
  const engine: { value: unknown } = { value: null };
  const r = hostRig(engine);
  await flush();
  assert.equal(FakeWs.all.length, 0);
  assert.equal(r.link.state, "waiting");
  assert.deepEqual(r.timers.pending(), [1000]);
  await r.timers.advance(1000);
  assert.deepEqual(r.timers.pending(), [2000]);
  engine.value = REC;
  await r.timers.advance(2000);
  const first = FakeWs.all[0]!;
  first.drop(1006); // refused before open
  await flush();
  assert.deepEqual(r.timers.pending(), [4000]);
  engine.value = { ...REC, port: 50001, token: "d4".repeat(32) };
  await r.timers.advance(4000);
  const second = FakeWs.all[1]!;
  assert.equal(second.url, "ws://127.0.0.1:50001/session", "engine.json is read again on every attempt");
  second.open();
  assert.equal((second.sent[0] as { token: string }).token, "d4".repeat(32));
  second.deliver(welcome);
  assert.equal(r.link.state, "connected");
  assert.deepEqual(r.timers.pending(), [], "the connect timeout is cleared by the welcome");
  second.drop(1001, "daemon stopping"); // the daemon stops
  await flush();
  assert.equal(r.link.state, "waiting");
  assert.deepEqual(r.timers.pending(), [1000], "the backoff starts again from 1 s after a welcome");
  assert.ok(r.logs.some((l) => /trying again in 1 s/.test(l)));
  assert.ok(r.logs.every((l) => !l.includes(TOKEN) && !l.includes("d4".repeat(32))), "no token in the log");
  assert.deepEqual(r.states.slice(0, 2), ["waiting", "connecting"]);
  r.link.stop();
  assert.deepEqual(r.timers.pending(), []);
});

test("host link: open but no welcome within the connect timeout -> closed and retried; a damaged engine.json waits too", async () => {
  const engine: { value: unknown } = { value: REC };
  const r = hostRig(engine);
  await flush();
  const ws = FakeWs.all[0]!;
  ws.open();
  await r.timers.advance(10_000);
  assert.ok(ws.closed, "the silent socket is closed");
  assert.equal(r.link.state, "waiting");
  engine.value = {};
  await r.timers.advance(1000);
  assert.equal(FakeWs.all.length, 1, "a damaged engine.json opens nothing");
  assert.equal(r.link.state, "waiting");
  r.link.stop();
});

test("host link: stop() while waiting or connecting leaves no socket and no timer", async () => {
  const r = hostRig({ value: REC });
  await flush();
  r.link.stop();
  assert.ok(FakeWs.all[0]!.closed);
  assert.deepEqual(r.timers.pending(), []);
  FakeWs.all[0]!.open(); // a late open after stop does nothing
  assert.equal(FakeWs.all[0]!.sent.length, 0);
});
