// DaemonSource (src/daemon-source.ts): the panel as a requester of the local engine daemon (`reel serve`), driven here
// by a fake transport (fake clock + timers, fake engine.json, fake socket) and a fake daemon that answers like
// whynot-cut/engine/reel/serve/app.py. Every message the panel sends is validated with ajv against session.schema.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { DaemonSource, ENGINE_JSON_RETRIES, ENGINE_JSON_RETRY_MS, backoffMs, sessionUrl, statusUrl } from "../src/daemon-source.ts";
import type { DaemonSocket, DaemonTransport, LinkDiagnosis } from "../src/daemon-source.ts";
import { diagnosticsText } from "../src/diagnostics.ts";
import type { PanelState, Result } from "../src/source.ts";

// ---------------------------------------------------------------------------------------------------- schema
const CONTRACT = new URL("../../../whynot-cut/engine/reel/contract/", import.meta.url);
const ajv = new Ajv2020({ strictSchema: true, strictTypes: false, strictRequired: false, strictTuples: false, allErrors: true });
(addFormats as unknown as (a: unknown) => void)(ajv);
const loadSchema = (name: string) => {
  const schema = JSON.parse(readFileSync(new URL(`${name}.schema.json`, CONTRACT), "utf8")) as { $id: string };
  ajv.addSchema(schema);
  return schema;
};
for (const name of ["request", "result", "progress"]) loadSchema(name);
const session = loadSchema("session");
const validMessage = ajv.getSchema(session.$id)!;
const validPanelState = ajv.getSchema(`${session.$id}#/$defs/panel_state`)!;
for (const name of ["ping", "status", "open_project", "export_frames", "build_project", "set_player_position", "render_review"]) loadSchema(name);
const validData = (action: string) => ajv.getSchema(`https://thewhynot.ai/whynot-cut/contract/4/${action}.schema.json#/$defs/data`);

// ---------------------------------------------------------------------------------------------------- fakes
const TOKEN = "a1".repeat(32);
const TOKEN2 = "b2".repeat(32);
const flush = async () => {
  for (let i = 0; i < 6; i++) await new Promise<void>((r) => setImmediate(r));
};

class Clock {
  t = Date.parse("2026-10-12T10:00:00Z");
  private timers: { at: number; fn: () => void; live: boolean; seq: number }[] = [];
  private seq = 0;
  now = (): number => this.t;
  setTimer = (fn: () => void, ms: number): (() => void) => {
    const timer = { at: this.t + Math.max(0, ms), fn, live: true, seq: this.seq++ };
    this.timers.push(timer);
    return () => {
      timer.live = false;
    };
  };
  pending(): number {
    return this.timers.filter((x) => x.live).length;
  }
  async advance(ms: number): Promise<void> {
    const target = this.t + ms;
    await flush();
    for (;;) {
      const due = this.timers.filter((x) => x.live && x.at <= target).sort((a, b) => a.at - b.at || a.seq - b.seq)[0];
      if (!due) break;
      due.live = false;
      this.t = due.at;
      due.fn();
      await flush();
    }
    this.t = target;
    await flush();
  }
}

type Msg = Record<string, unknown> & { type: string };

class FakeSocket implements DaemonSocket {
  onopen: (() => void) | null = null;
  onmessage: ((text: string) => void) | null = null;
  onclose: ((code: number, reason: string) => void) | null = null;
  sent: Msg[] = [];
  closed: { code: number; reason: string } | null = null;
  url: string;
  private daemon: FakeDaemon;
  constructor(url: string, daemon: FakeDaemon) {
    this.url = url;
    this.daemon = daemon;
  }
  send(text: string): void {
    if (this.closed) throw new Error("socket closed");
    const msg = JSON.parse(text) as Msg;
    if (!validMessage(msg)) this.daemon.invalid.push(`${text}: ${JSON.stringify(validMessage.errors)}`);
    this.sent.push(msg);
    this.daemon.receive(this, msg);
  }
  close(code = 1000, reason = ""): void {
    if (this.closed) return;
    this.closed = { code, reason };
    setImmediate(() => this.onclose?.(code, reason));
  }
  // daemon side
  deliver(msg: object | string): void {
    if (!this.closed) this.onmessage?.(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  serverClose(code: number, reason = ""): void {
    if (this.closed) return;
    this.closed = { code, reason };
    this.onclose?.(code, reason);
  }
}

function stubState(host: "uxp" | "cep" | "offline" = "uxp", detail?: string, id?: string) {
  const h: Record<string, string> = { state: host };
  if (detail) h["detail"] = detail;
  const m: Record<string, unknown> = {
    type: "state",
    state: {
      connection: { engine: "connected", claude: "unknown", host: h },
      client: "", item: "", language: "en", editor_name: "",
      context: { project_path: null, sequence_name: null, folder: null, out_dir: null, review_mp4: null },
      pipeline: [], approval: null, qc: [], log: [],
    },
  };
  if (id) m["id"] = id;
  return m;
}

const NOT_YET = "not implemented in the serve core yet";
const NOT_YET_HOW = "Use the reel CLI for this step for now (e.g. `reel approve` / `reel build`); the panel will do it once the engine-state part of reel serve ships.";

class FakeDaemon {
  /** "ok": upgrades; "refuse": the HTTP upgrade is refused (onclose 1006, never onopen); "silent": opens, never answers */
  mode: "ok" | "refuse" | "silent" = "ok";
  token = TOKEN;
  statusCode: number | null = 200;
  host: "uxp" | "cep" | "offline" = "uxp";
  hostDetail: string | undefined = "Premiere Pro 26.5.2";
  sockets: FakeSocket[] = [];
  invalid: string[] = [];
  /** state.jobs (H1: the daemon's job journal); undefined = an older daemon that sends none */
  jobs: unknown[] | undefined = undefined;
  /** the error text of an intent reply (an older serve core said "not implemented"; serve/app.py NOT_YET now) */
  notYet = NOT_YET;
  /** welcome.update (C2.3); undefined = an older daemon that sends none */
  update: unknown = undefined;
  onCommand: (s: FakeSocket, m: Msg) => void = (s, m) => {
    const req = m["request"] as { id: string; action: string };
    s.deliver({ type: "result", result: { ok: true, action: req.action, readback: { position_s: 1 }, id: req.id } });
  };
  onCancel: (s: FakeSocket, m: Msg) => void = (s, m) => {
    s.deliver({ type: "error", code: "no_route", message: "This command runs through the CEP bridge and cannot be cancelled.", id: m["id"] });
  };
  open(url: string): FakeSocket {
    const s = new FakeSocket(url, this);
    this.sockets.push(s);
    if (this.mode === "refuse") setImmediate(() => s.serverClose(1006, ""));
    else setImmediate(() => s.onopen?.());
    return s;
  }
  get last(): FakeSocket {
    return this.sockets[this.sockets.length - 1]!;
  }
  receive(s: FakeSocket, m: Msg): void {
    if (this.mode === "silent") return;
    if (s.sent.length === 1) {
      // the first message: hello (app.py _authenticate)
      const client = m["client"] as { protocol?: unknown } | undefined;
      if (m.type === "hello" && client && client.protocol !== 4) {
        s.deliver({ type: "error", code: "schema", message: "protocol 4 required" });
        s.serverClose(1008, "protocol 4 required");
      } else if (m.type !== "hello" || m["token"] !== this.token) {
        s.deliver({ type: "error", code: "auth", message: "The first message must be a hello with the engine token from engine.json." });
        s.serverClose(1008, "authentication required");
      } else {
        s.deliver({ type: "welcome", session_id: "s-0123456789abcdef", protocol: 4, daemon_version: "3.0.0", ...(this.update === undefined ? {} : { update: this.update }) });
      }
      return;
    }
    switch (m.type) {
      case "snapshot": {
        const st = stubState(this.host, this.hostDetail, m["id"] as string | undefined);
        if (this.jobs) (st["state"] as Record<string, unknown>)["jobs"] = this.jobs;
        if (!validMessage(st)) this.invalid.push(`daemon state: ${JSON.stringify(validMessage.errors)}`);
        s.deliver(st);
        return;
      }
      case "approve":
      case "request_changes":
      case "rebuild":
        s.deliver({ type: "reply", id: m["id"], intent: m.type, ok: false, error: this.notYet, how: NOT_YET_HOW });
        return;
      case "command":
        this.onCommand(s, m);
        return;
      case "cancel":
        this.onCancel(s, m);
        return;
      default:
        s.deliver({ type: "error", code: "schema", message: `${m.type} is sent by the daemon, not by clients.` });
    }
  }
}

interface Rig {
  clock: Clock;
  daemon: FakeDaemon;
  engine: { value: unknown };
  reads: number;
  readTimes: number[];
  probes: { url: string; headers: Record<string, string> }[];
  logs: string[];
  opened: string[];
  transport: DaemonTransport;
  src: DaemonSource;
  states: PanelState[];
}

function rig(opts: { record?: unknown; noProbe?: boolean; openThrows?: boolean; probeThrows?: boolean; build?: string; update?: unknown } = {}): Rig {
  const r = {
    clock: new Clock(),
    daemon: new FakeDaemon(),
    engine: { value: "record" in opts ? opts.record : { port: 51234, token: TOKEN, pid: 4242, version: "3.0.0", protocol: 4 } },
    reads: 0,
    readTimes: [] as number[],
    probes: [] as Rig["probes"],
    logs: [] as string[],
    opened: [] as string[],
    states: [] as PanelState[],
  } as Rig;
  const transport: DaemonTransport = {
    readEngineJson: async () => {
      r.reads++;
      r.readTimes.push(r.clock.now());
      return r.engine.value === undefined ? null : structuredClone(r.engine.value);
    },
    openSocket: (url: string) => {
      r.opened.push(url);
      if (opts.openThrows) throw new Error(`refused ${url} with token ${TOKEN}`);
      return r.daemon.open(url);
    },
    now: r.clock.now,
    setTimer: r.clock.setTimer,
    log: (line: string) => {
      r.logs.push(line);
    },
  };
  if (!opts.noProbe) {
    transport.httpGetStatus = async (url: string, headers: { Authorization: string }) => {
      r.probes.push({ url, headers: { ...headers } });
      if (opts.probeThrows) throw new TypeError("Network request failed");
      return r.daemon.statusCode;
    };
  }
  r.transport = transport;
  if ("update" in opts) r.daemon.update = opts.update;
  r.src = new DaemonSource({ transport, version: "3.0.0", ...(opts.build !== undefined ? { build: opts.build } : {}), language: "ar", editor_name: "Yunus" });
  r.src.subscribe((s) => r.states.push(s));
  return r;
}

async function connected(opts: Parameters<typeof rig>[0] = {}): Promise<Rig> {
  const r = rig(opts);
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.src.diagnosis.code, "connected", JSON.stringify(r.src.diagnosis));
  return r;
}

const sentOf = (s: FakeSocket, type: string) => s.sent.filter((m) => m.type === type);
const ID_RE = /^[A-Za-z0-9._-]{1,64}$/;

// ---------------------------------------------------------------------------------------------------- tests
test("discovery and hello: engine.json -> ws://localhost:<port>/session exactly, hello first (panel, protocol 4, no capabilities)", async () => {
  const r = await connected();
  assert.deepEqual(r.opened, ["ws://localhost:51234/session"]);
  assert.equal(sessionUrl(51234), "ws://localhost:51234/session");
  const s = r.daemon.last;
  assert.deepEqual(s.sent[0], { type: "hello", token: TOKEN, client: { kind: "panel", version: "3.0.0", protocol: 4, capabilities: [] } });
  assert.equal(s.sent[1]!.type, "snapshot", "a snapshot right after welcome");
  assert.deepEqual(r.daemon.invalid, []);
});

test("snapshot: merges only the daemon's connection and keeps the local language / editor_name; the state validates", async () => {
  const r = await connected();
  const st = await r.src.snapshot();
  assert.deepEqual(st.connection, { engine: "connected", claude: "unknown", host: { state: "uxp", detail: "Premiere Pro 26.5.2" } });
  assert.equal(st.language, "ar");
  assert.equal(st.editor_name, "Yunus");
  assert.ok(validPanelState(st), JSON.stringify(validPanelState.errors));
  assert.equal(r.states.at(-1)!.connection.engine, "connected");
});

test("before the link is up the state is offline and validates; snapshot() never waits for the daemon", async () => {
  const r = rig();
  const st = await r.src.snapshot();
  assert.equal(st.connection.engine, "offline");
  assert.equal(st.connection.host.state, "offline");
  assert.ok(validPanelState(st), JSON.stringify(validPanelState.errors));
});

test("poll: a snapshot every 2 s with fresh valid ids (keepalive); a changed connection is pushed, an unchanged one is not", async () => {
  const r = await connected();
  const s = r.daemon.last;
  const pushes = r.states.length;
  await r.clock.advance(2000);
  await r.clock.advance(2000);
  await r.clock.advance(2000);
  const snaps = sentOf(s, "snapshot");
  assert.equal(snaps.length, 4);
  const ids = snaps.map((m) => m["id"] as string);
  assert.ok(ids.every((id) => ID_RE.test(id)));
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(r.states.length, pushes, "nothing changed: no re-render every 2 s");
  r.daemon.host = "cep";
  r.daemon.hostDetail = undefined;
  await r.clock.advance(2000);
  assert.deepEqual(r.states.at(-1)!.connection.host, { state: "cep" });
  assert.deepEqual(r.daemon.invalid, []);
});

test("engine.json briefly absent (tombstone swap): retried within the same attempt, no backoff", async () => {
  const r = rig({ record: undefined });
  const rec = { port: 51234, token: TOKEN, pid: 4242, version: "3.0.0", protocol: 4 };
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.opened.length, 0);
  r.engine.value = rec;
  await r.clock.advance(300);
  assert.equal(r.opened.length, 1);
  assert.equal(r.src.diagnosis.code, "connected");
});

test("engine.json missing: offline + no_engine diagnosis, backoff 1-2-4-8-15-15 s, engine.json re-read on every attempt", async () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6, 9].map(backoffMs), [1000, 2000, 4000, 8000, 15000, 15000, 15000]);
  const r = rig({ record: undefined });
  r.src.start();
  await r.clock.advance(1000);
  assert.equal(r.src.diagnosis.code, "no_engine");
  assert.equal((await r.src.snapshot()).connection.engine, "offline");
  assert.equal(r.reads, 1 + ENGINE_JSON_RETRIES, "the first attempt retries the read");
  // the attempts are spaced by the backoff, counted from the end of each attempt's read retries
  await r.clock.advance(60_000);
  const starts = r.readTimes.filter((t, i) => i === 0 || t - r.readTimes[i - 1]! > ENGINE_JSON_RETRY_MS);
  const window = ENGINE_JSON_RETRIES * ENGINE_JSON_RETRY_MS;
  const gaps = starts.slice(1).map((t, i) => t - starts[i]! - window);
  assert.deepEqual(gaps, [1000, 2000, 4000, 8000, 15000, 15000]);
  assert.equal(r.src.diagnosis.retry_in_s, 15);
  // the engine comes up with a new port and token: the next attempt reads them
  r.engine.value = { port: 50001, token: TOKEN2, pid: 1, version: "3.0.0", protocol: 4 };
  r.daemon.token = TOKEN2;
  await r.clock.advance(15000);
  assert.deepEqual(r.opened, ["ws://localhost:50001/session"]);
  assert.equal(r.src.diagnosis.code, "connected");
  assert.equal(r.daemon.last.sent[0]!["token"], TOKEN2);
});

test("a bad engine.json (no port / bad token / protocol 3) is diagnosed without connecting", async () => {
  for (const [record, code] of [
    [{ token: TOKEN }, "bad_engine_json"],
    [{ port: 51234, token: "short" }, "bad_engine_json"],
    [{ port: 70000, token: TOKEN }, "bad_engine_json"],
    ["not an object", "bad_engine_json"],
    [{ port: 51234, token: TOKEN, protocol: 3 }, "protocol"],
  ] as const) {
    const r = rig({ record });
    r.src.start();
    await r.clock.advance(1000);
    assert.equal(r.src.diagnosis.code, code, JSON.stringify(record));
    assert.equal(r.opened.length, 0);
    r.src.stop();
  }
});

test("intents: approve / request_changes / rebuild send their messages and resolve on the matching reply; not-implemented is a clear notice", async () => {
  const r = await connected();
  const s = r.daemon.last;
  const a = await r.src.approve({ item: "C0239", editor_name: "Yunus", fingerprint: "sha256:abc" });
  const c = await r.src.requestChanges({ item: "C0239", editor_name: "Yunus", text: "shorter hook" });
  const b = await r.src.rebuild({ item: "C0239", project_path: "D:/p/C0239.prproj", replace_edited: true });
  const ap = sentOf(s, "approve")[0]!;
  assert.deepEqual({ ...ap, id: "x" }, { type: "approve", id: "x", item: "C0239", editor_name: "Yunus", fingerprint: "sha256:abc" });
  assert.deepEqual({ ...sentOf(s, "request_changes")[0]!, id: "x" }, { type: "request_changes", id: "x", item: "C0239", editor_name: "Yunus", text: "shorter hook" });
  assert.deepEqual({ ...sentOf(s, "rebuild")[0]!, id: "x" }, { type: "rebuild", id: "x", item: "C0239", project_path: "D:/p/C0239.prproj", replace_edited: true });
  const ids = ["approve", "request_changes", "rebuild"].map((t) => sentOf(s, t)[0]!["id"] as string);
  assert.equal(new Set(ids).size, 3);
  for (const [res, intent] of [[a, "approve"], [c, "request_changes"], [b, "rebuild"]] as const) {
    assert.equal(res.ok, false);
    assert.equal(res.action, intent);
    assert.match(res.error!, /not available from the panel/i);
    assert.match(res.error!, /yet/);
    assert.equal(res.how, NOT_YET_HOW);
    assert.equal((res as Result & { code?: string }).code, "NOT_YET", "the same answer every time: the panel offers no Try again");
  }
  assert.deepEqual(r.daemon.invalid, []);
});

test("intents: an ok reply resolves ok; a reply for another id or intent is ignored; no reply in time -> a timeout result", async () => {
  const r = await connected();
  const s = r.daemon.last;
  r.daemon.mode = "silent";
  const p = r.src.approve({ item: "C0239", editor_name: "Yunus", fingerprint: "f" });
  await flush();
  const id = sentOf(s, "approve")[0]!["id"] as string;
  s.deliver({ type: "reply", id: "someone-else", intent: "approve", ok: true });
  s.deliver({ type: "reply", id, intent: "rebuild", ok: true });
  s.deliver({ type: "reply", id, intent: "approve", ok: true, readback: { approved: true } });
  assert.deepEqual(await p, { ok: true, action: "approve", readback: { approved: true } });
  const q = r.src.rebuild({ item: "C0239", project_path: "D:/p.prproj", replace_edited: false });
  await r.clock.advance(30_000);
  const res = await q;
  assert.equal(res.ok, false);
  assert.match(res.error!, /did not answer/);
});

test("intents with an empty item are refused by the daemon's schema: the error{id} answers them", async () => {
  const r = await connected();
  const s = r.daemon.last;
  r.daemon.mode = "silent";
  const p = r.src.approve({ item: "", editor_name: "Yunus", fingerprint: "f" });
  await flush();
  const id = sentOf(s, "approve")[0]!["id"] as string;
  s.deliver({ type: "error", code: "schema", message: "/item: should NOT have fewer than 1 characters", id });
  const res = await p;
  assert.equal(res.ok, false);
  assert.match(res.error!, /item/);
});

test("run: a command with a v4 request (protocol, id, expires_at) resolves on its result; progress drives the owning step", async () => {
  const r = await connected();
  const s = r.daemon.last;
  let cmd: Msg | null = null;
  r.daemon.onCommand = (_s, m) => {
    cmd = m;
  };
  const data = { sequence_name: "C0239_main", times: [1.5, 3], out_dir: "D:/out", project_path: null };
  const p = r.src.run("export_frames", data);
  await flush();
  assert.ok(cmd);
  const req = (cmd as Msg)["request"] as { protocol: number; id: string; action: string; data: object; expires_at: string };
  assert.equal(req.protocol, 4);
  assert.equal(req.action, "export_frames");
  assert.deepEqual(req.data, data);
  assert.ok(ID_RE.test(req.id));
  assert.ok(Date.parse(req.expires_at) > r.clock.now(), "expires in the future");
  assert.match(req.expires_at, /Z$/);
  assert.ok(validData("export_frames")!(req.data));
  let st = await r.src.snapshot();
  const frames = () => st.pipeline.find((x) => x.id === "frames");
  assert.equal(frames()!.state, "running");
  assert.equal(frames()!.request_id, req.id);
  s.deliver({ type: "progress", progress: { event: "progress", id: req.id, action: "export_frames", step: "frame 1", n: 1, of: 2, elapsed_s: 0.4 } });
  s.deliver({ type: "progress", progress: { event: "progress", id: "not-ours", action: "export_frames", step: "x", n: 9, of: 9 } });
  await flush();
  st = await r.src.snapshot();
  assert.deepEqual(frames()!.progress, { n: 1, of: 2, step: "frame 1" });
  assert.equal(frames()!.elapsed_s, 0.4);
  assert.ok(validPanelState(st), JSON.stringify(validPanelState.errors));
  const readback = { frames: [{ t: 1.5, file: "D:/out/a.png", called: true }, { t: 3, file: "D:/out/b.png", called: true }] };
  s.deliver({ type: "result", result: { ok: true, action: "export_frames", readback, id: req.id } });
  assert.deepEqual(await p, { ok: true, action: "export_frames", readback });
  st = await r.src.snapshot();
  assert.equal(frames()!.state, "done");
  assert.equal(frames()!.request_id, null);
  assert.deepEqual(r.daemon.invalid, []);
});

test("H2 run: the synthetic CEP progress (queued, claimed, elapsed ticks) gives the running step its phase and elapsed time from the first event", async () => {
  const r = await connected();
  const s = r.daemon.last;
  let cmd: Msg | null = null;
  r.daemon.onCommand = (_s, m) => {
    cmd = m;
  };
  const p = r.src.run("export_frames", { sequence_name: "C0239_main", times: [1.5], out_dir: "D:/out", project_path: null });
  await flush();
  assert.ok(cmd);
  const id = ((cmd as Msg)["request"] as { id: string }).id;
  const frames = async () => (await r.src.snapshot()).pipeline.find((x) => x.id === "frames")!;
  const send = (phase: string, elapsed_s: number) => s.deliver({ type: "progress", progress: { event: "progress", id, action: "export_frames", step: phase, phase, elapsed_s } });
  assert.equal((await frames()).phase ?? null, null, "no phase before the first event");
  send("queued", 0);
  await flush();
  assert.equal((await frames()).phase, "queued");
  assert.equal((await frames()).elapsed_s, 0);
  send("claimed", 1.5);
  await flush();
  assert.equal((await frames()).phase, "claimed");
  send("elapsed", 2);
  send("elapsed", 4);
  await flush();
  const f = await frames();
  assert.equal(f.phase, "claimed", "an elapsed tick keeps the phase before it");
  assert.equal(f.elapsed_s, 4);
  assert.equal(f.progress ?? null, null, "no n/of is made up");
  assert.ok(validPanelState(await r.src.snapshot()), JSON.stringify(validPanelState.errors));
  s.deliver({ type: "progress", progress: { event: "progress", id, action: "export_frames", step: "frame 1", n: 1, of: 2, phase: "running", elapsed_s: 5 } });
  await flush();
  assert.equal((await frames()).phase, "running");
  assert.deepEqual((await frames()).progress, { n: 1, of: 2, step: "frame 1" });
  s.deliver({ type: "result", result: { ok: true, action: "export_frames", readback: { frames: [] }, id } });
  await p;
  const done = await frames();
  assert.equal(done.state, "done");
  assert.equal(done.phase ?? null, null, "a settled step carries no phase");
  assert.ok(validPanelState(await r.src.snapshot()), JSON.stringify(validPanelState.errors));
});

test("H2 run: a first event that is an elapsed tick (queued was dropped) still shows a phase; an unknown phase is ignored as a malformed message", async () => {
  const r = await connected();
  const s = r.daemon.last;
  let cmd: Msg | null = null;
  r.daemon.onCommand = (_s, m) => {
    cmd = m;
  };
  const p = r.src.run("export_frames", { sequence_name: "C0239_main", times: [1.5], out_dir: "D:/out", project_path: null });
  await flush();
  assert.ok(cmd);
  const id = ((cmd as Msg)["request"] as { id: string }).id;
  const bad = { type: "progress", progress: { event: "progress", id, action: "export_frames", step: "busy", phase: "busy", elapsed_s: 3 } };
  assert.equal(validMessage(bad), false);
  s.deliver(bad);
  await flush();
  let step = (await r.src.snapshot()).pipeline.find((x) => x.id === "frames")!;
  assert.equal(step.phase ?? null, null);
  assert.equal(step.elapsed_s ?? null, null);
  s.deliver({ type: "progress", progress: { event: "progress", id, action: "export_frames", step: "elapsed", phase: "elapsed", elapsed_s: 6 } });
  await flush();
  step = (await r.src.snapshot()).pipeline.find((x) => x.id === "frames")!;
  assert.equal(step.phase, "elapsed");
  assert.equal(step.elapsed_s, 6);
  s.deliver({ type: "result", result: { ok: false, action: "export_frames", error: "x", id } });
  await p;
});

test("run: a failed result keeps error + how and fails the step; error{no_route,id} answers a command; ids are unique", async () => {
  const r = await connected();
  r.daemon.onCommand = (s, m) => {
    const req = m["request"] as { id: string; action: string };
    if (req.action === "build_project") s.deliver({ type: "result", result: { ok: false, action: "build_project", error: "Premiere is busy.", how: "Wait.", id: req.id } });
    else s.deliver({ type: "error", code: "no_route", message: `Nothing can run ${req.action} now: no connected panel implements it.`, id: req.id });
  };
  const fail = await r.src.run("build_project", {});
  assert.deepEqual(fail, { ok: false, action: "build_project", error: "Premiere is busy.", how: "Wait." });
  assert.equal((await r.src.snapshot()).pipeline.find((x) => x.id === "build")!.state, "failed");
  const nr = await r.src.run("set_player_position", { sequence_name: "S", t_s: 2 });
  assert.equal(nr.ok, false);
  assert.match(nr.error!, /Nothing can run set_player_position/);
  assert.ok(nr.how && nr.how.length > 0);
  const ids = sentOf(r.daemon.last, "command").map((m) => (m["request"] as { id: string }).id);
  assert.equal(new Set(ids).size, ids.length);
});

test("run: no result before expiry -> a timeout result; a late result is ignored", async () => {
  const r = await connected();
  r.daemon.onCommand = () => {};
  const p = r.src.run("set_player_position", { sequence_name: "S", t_s: 2 });
  await flush();
  const req = sentOf(r.daemon.last, "command")[0]!["request"] as { id: string; expires_at: string };
  await r.clock.advance(Date.parse(req.expires_at) - r.clock.now() + 10_000);
  const res = await p;
  assert.equal(res.ok, false);
  assert.match(res.error!, /did not answer/);
  r.daemon.last.deliver({ type: "result", result: { ok: true, action: "set_player_position", readback: { position_s: 2 }, id: req.id } });
  await flush();
});

test("run while offline answers at once and sends nothing; an over-limit command is refused locally (no close 1009)", async () => {
  const off = rig({ record: undefined });
  const res = await off.src.run("status", {});
  assert.equal(res.ok, false);
  assert.match(res.error!, /not connected/);
  const r = await connected();
  const before = r.daemon.last.sent.length;
  const big = await r.src.run("export_frames", { sequence_name: "S", times: [1], out_dir: "x".repeat(9 * 1024 * 1024) });
  assert.equal(big.ok, false);
  assert.match(big.error!, /too large/);
  assert.equal(r.daemon.last.sent.length, before);
});

test("cancel: sends cancel{id}; no_route (a CEP-routed command) -> can't be cancelled; silence -> resolved; own command's result fails its step", async () => {
  const r = await connected();
  const s = r.daemon.last;
  await assert.rejects(r.src.cancel("req-cli-7"), (e: Error) => /can't be cancelled/.test(e.message) && /CEP/.test(e.message));
  assert.deepEqual(sentOf(s, "cancel")[0], { type: "cancel", id: "req-cli-7" });
  r.daemon.onCancel = () => {};
  const done = r.src.cancel("req-cli-8");
  await r.clock.advance(2000);
  await done;
  // the panel's own running command: the cancel is forwarded, the command's own result answers
  r.daemon.onCommand = () => {};
  const p = r.src.run("build_project", {});
  await flush();
  const id = (sentOf(s, "command")[0]!["request"] as { id: string }).id;
  assert.equal((await r.src.snapshot()).pipeline.find((x) => x.id === "build")!.request_id, id);
  r.daemon.onCancel = (sock, m) => {
    sock.deliver({ type: "result", result: { ok: false, action: "build_project", error: "cancelled", id: m["id"] } });
  };
  const c = r.src.cancel(id);
  await r.clock.advance(2000);
  await c;
  assert.equal((await p).ok, false);
  assert.equal((await r.src.snapshot()).pipeline.find((x) => x.id === "build")!.state, "failed");
  await assert.rejects(r.src.cancel("bad id with spaces"));
  assert.deepEqual(r.daemon.invalid, []);
});

test("diagnosis: wrong protocol -> error{schema, protocol 4 required} + 1008 is a protocol notice, not a token one", async () => {
  const r = rig();
  r.daemon.receive = function (this: FakeDaemon, s: FakeSocket) {
    s.deliver({ type: "error", code: "schema", message: "protocol 4 required" });
    s.serverClose(1008, "protocol 4 required");
  };
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.src.diagnosis.code, "protocol");
  assert.match(r.src.diagnosis.text, /version/i);
  assert.equal((await r.src.snapshot()).connection.engine, "offline");
  assert.ok((await r.src.snapshot()).log.some((l) => /protocol/i.test(l.text)));
});

test("diagnosis: wrong token -> auth + 1008; the next attempt re-reads engine.json and connects with the new token", async () => {
  const r = rig();
  r.daemon.token = TOKEN2;
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.src.diagnosis.code, "auth");
  assert.equal(r.src.diagnosis.retry_in_s, 1);
  r.engine.value = { port: 51234, token: TOKEN2, pid: 9, version: "3.0.0", protocol: 4 };
  await r.clock.advance(1000);
  assert.equal(r.src.diagnosis.code, "connected");
});

test("diagnosis: close 1009 -> too_large; a lost connection reconnects (hello, then snapshot) and a command the daemon does not know is lost", async () => {
  const r = await connected();
  r.daemon.onCommand = () => {};
  let settled = false;
  const p = r.src.run("build_project", {}).then((x) => ((settled = true), x));
  await flush();
  r.daemon.last.serverClose(1009, "message too big");
  await flush();
  assert.equal(r.src.diagnosis.code, "too_large");
  assert.equal(settled, false, "H1: a pending command waits for the reconnect's jobs[]");
  assert.equal((await r.src.snapshot()).pipeline.find((x) => x.id === "build")!.state, "running");
  assert.equal((await r.src.snapshot()).connection.engine, "offline");
  await r.clock.advance(1000);
  assert.equal(r.daemon.sockets.length, 2);
  assert.deepEqual(r.daemon.last.sent.map((m) => m.type).slice(0, 2), ["hello", "snapshot"]);
  assert.equal(r.src.diagnosis.code, "connected");
  const res = await p; // an older daemon: no jobs[], so the command is lost
  assert.equal(res.ok, false);
  assert.equal(res.code, "lost");
  assert.match(res.error!, /connection/i);
  assert.equal((await r.src.snapshot()).pipeline.find((x) => x.id === "build")!.state, "failed");
  // after a good session the backoff starts again at 1 s
  r.daemon.last.serverClose(1001, "reel serve is stopping");
  await flush();
  assert.equal(r.src.diagnosis.code, "lost");
  assert.equal(r.src.diagnosis.retry_in_s, 1);
});

test("diagnosis: refused before the upgrade -> GET /status with the bearer header tells down / Host-Origin / busy / stale token", async () => {
  for (const [status, code] of [[null, "down"], [403, "refused_host"], [503, "refused_busy"], [401, "auth"], [200, "refused_host"], [500, "refused"]] as const) {
    const r = rig();
    r.daemon.mode = "refuse";
    r.daemon.statusCode = status;
    r.src.start();
    await r.clock.advance(0);
    assert.equal(r.src.diagnosis.code, code, `status ${status}`);
    assert.deepEqual(r.probes, [{ url: "http://localhost:51234/status", headers: { Authorization: `Bearer ${TOKEN}` } }]);
    assert.equal(statusUrl(51234), "http://localhost:51234/status");
    r.src.stop();
  }
  const r = rig({ noProbe: true });
  r.daemon.mode = "refuse";
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.src.diagnosis.code, "unreachable");
});

test("diagnosis: the socket opens but no welcome comes -> no_welcome after the hello timeout, then retry", async () => {
  const r = rig();
  r.daemon.mode = "silent";
  r.src.start();
  await r.clock.advance(5000);
  assert.equal(r.src.diagnosis.code, "no_welcome");
  assert.ok(r.daemon.sockets[0]!.closed);
  await r.clock.advance(1000);
  assert.equal(r.daemon.sockets.length, 2);
});

test("malformed messages from the daemon are ignored (ajv agrees they are invalid), never crash, never change state", async () => {
  const r = await connected();
  const s = r.daemon.last;
  const before = JSON.stringify((await r.src.snapshot()).connection);
  const bad: unknown[] = [
    { type: "state", state: { connection: { engine: "sideways", claude: "unknown", host: { state: "uxp" } } } },
    { type: "state" },
    { type: "reply", id: "p", intent: "run", ok: true },
    { type: "result", result: { ok: true, action: "ping" } },
    { type: "result", result: { ok: true, action: "run_script", readback: {}, id: "x" } },
    { type: "progress", progress: { event: "progress", id: "r", action: "ping" } },
    { type: "error", code: "oops", message: "m" },
    { type: "welcome", session_id: "s", protocol: 3, daemon_version: "3" },
    { type: "run_script", code: "1+1" },
    {},
    [],
    "hello",
    null,
  ];
  for (const b of bad) {
    assert.equal(validMessage(b), false, JSON.stringify(b));
    s.deliver(JSON.stringify(b));
  }
  s.deliver("{not json");
  s.deliver("x".repeat(100));
  await flush();
  assert.equal(JSON.stringify((await r.src.snapshot()).connection), before);
  assert.equal(r.src.diagnosis.code, "connected");
  const warns = (await r.src.snapshot()).log.filter((l) => /malformed|unexpected/i.test(l.text));
  assert.equal(warns.length, 1, "one warning per connection, not one per message");
  assert.ok(!warns[0]!.text.includes("run_script"), "the payload is never echoed into the log");
});

test("stop(): closes the socket, fails nothing silently, and no timer reconnects afterwards", async () => {
  const r = await connected();
  r.src.stop();
  await flush();
  assert.ok(r.daemon.last.closed);
  await r.clock.advance(60_000);
  assert.equal(r.daemon.sockets.length, 1);
  assert.equal(r.src.diagnosis.code, "stopped");
  assert.equal(r.clock.pending(), 0);
});

test("the token is never in a URL, a log line, PanelState, diagnostics, a diagnosis or an error/result text", async () => {
  const seen: string[] = [];
  const collect = async (r: Rig, extra: unknown[] = []) => {
    const st = await r.src.snapshot();
    seen.push(JSON.stringify(st), diagnosticsText(st), JSON.stringify(r.src.diagnosis), ...r.logs, ...r.opened, ...r.probes.map((p) => p.url));
    for (const s of r.states) seen.push(JSON.stringify(s));
    for (const e of extra) seen.push(e instanceof Error ? `${e.message} ${e.stack}` : JSON.stringify(e));
  };
  // a full happy session with intents, commands, cancel
  const a = await connected();
  const results: unknown[] = [];
  results.push(await a.src.approve({ item: "C", editor_name: "Y", fingerprint: "f" }));
  results.push(await a.src.run("status", {}));
  results.push(await a.src.cancel("req-1").catch((e: unknown) => e));
  a.daemon.last.serverClose(1006, "");
  await a.clock.advance(1000);
  await collect(a, results);
  // auth failure (token named in nothing the panel shows)
  const b = rig();
  b.daemon.token = TOKEN2;
  b.src.start();
  await b.clock.advance(0);
  await collect(b);
  // refused + probe, and a transport that throws an error naming the token
  const c = rig();
  c.daemon.mode = "refuse";
  c.daemon.statusCode = 403;
  c.src.start();
  await c.clock.advance(0);
  await collect(c);
  const d = rig({ openThrows: true });
  d.src.start();
  await d.clock.advance(0);
  await collect(d);
  assert.ok(d.logs.length > 0 && (await d.src.snapshot()).log.length > 0, "the throw was logged (scrubbed)");
  for (const text of seen) {
    assert.ok(!text.includes(TOKEN), `token leaked: ${text.slice(0, 200)}`);
    assert.ok(!text.includes(TOKEN2), `token leaked: ${text.slice(0, 200)}`);
  }
  // the token only travels in hello and in the probe's Authorization header
  assert.equal(c.probes[0]!.headers["Authorization"], `Bearer ${TOKEN}`);
});

test("PanelState stays schema-valid through a whole session (connect, progress, result, loss, reconnect)", async () => {
  const r = await connected();
  const answer = r.daemon.onCommand;
  r.daemon.onCommand = (s, m) => {
    const req = m["request"] as { id: string };
    s.deliver({ type: "progress", progress: { event: "progress", id: req.id, action: "build_project", step: "s".repeat(400), n: 2.7, of: 0 } });
  };
  void r.src.run("build_project", {});
  await flush();
  r.daemon.last.serverClose(1006, "");
  await r.clock.advance(1000);
  for (const st of r.states) assert.ok(validPanelState(st), JSON.stringify(validPanelState.errors));
  const diag: LinkDiagnosis = r.src.diagnosis;
  assert.equal(diag.code, "connected");
  r.daemon.onCommand = answer;
  const res: Result = await r.src.run("status", {});
  assert.equal(res.ok, true);
});

// ---------------------------------------------------------------------------------------------------- Task 4 carried
test("no structuredClone (older UXP / CEP): snapshot and pushes fall back to a JSON copy and stay independent", async () => {
  const g = globalThis as { structuredClone?: unknown };
  const saved = g.structuredClone;
  g.structuredClone = undefined;
  try {
    const r = rig();
    // rig() already subscribed (the first read used structuredClone and failed): the in-attempt re-reads use this one
    r.transport.readEngineJson = async () => ({ port: 51234, token: TOKEN, pid: 4242, version: "3.0.0", protocol: 4 });
    await r.clock.advance(ENGINE_JSON_RETRIES * ENGINE_JSON_RETRY_MS);
    assert.equal(r.src.diagnosis.code, "connected");
    const a = await r.src.snapshot();
    assert.equal(a.connection.engine, "connected");
    assert.ok(validPanelState(a), JSON.stringify(validPanelState.errors));
    a.connection.engine = "offline";
    a.log.push({ ts: "00:00:00", level: "info", text: "mutated by the caller" });
    const b = await r.src.snapshot();
    assert.equal(b.connection.engine, "connected", "the caller's copy is not the source's state");
    assert.ok(!b.log.some((l) => l.text === "mutated by the caller"));
    assert.ok(r.states.length > 0 && r.states.every((s) => validPanelState(s)));
    r.src.stop();
  } finally {
    g.structuredClone = saved;
  }
});

test("request ids: two panels created in the same millisecond never share an id base (random suffix)", async () => {
  const a = await connected();
  const b = await connected();
  assert.equal(a.clock.now(), b.clock.now(), "same clock reading");
  void a.src.run("set_player_position", { sequence_name: "S", t_s: 1 });
  void b.src.run("set_player_position", { sequence_name: "S", t_s: 1 });
  await a.clock.advance(0);
  await b.clock.advance(0);
  const idOf = (r: Rig) => sentOf(r.daemon.last, "command").map((m) => (m["request"] as { id: string }).id)[0]!;
  const [ia, ib] = [idOf(a), idOf(b)];
  assert.ok(ID_RE.test(ia) && ID_RE.test(ib), `${ia} ${ib}`);
  assert.notEqual(ia, ib);
  assert.notEqual(ia.split("-")[1], ib.split("-")[1], "the id bases differ");
  assert.ok(ia.length <= 64);
  a.src.stop();
  b.src.stop();
});

test("localHost: while offline the host pill shows the panel's own host (validates); online it is the daemon's", async () => {
  const r = rig();
  const src = new DaemonSource({ transport: r.transport, localHost: { state: "uxp", detail: "Premiere Pro 26.5.2" } });
  const off = await src.snapshot();
  assert.deepEqual(off.connection, { engine: "offline", claude: "unknown", host: { state: "uxp", detail: "Premiere Pro 26.5.2" } });
  assert.ok(validPanelState(off), JSON.stringify(validPanelState.errors));
  await r.clock.advance(0);
  r.daemon.host = "cep";
  r.daemon.hostDetail = undefined;
  await r.clock.advance(2000);
  assert.deepEqual((await src.snapshot()).connection.host, { state: "cep" });
  src.stop();
  assert.deepEqual((await src.snapshot()).connection.host, { state: "uxp", detail: "Premiere Pro 26.5.2" });
  r.src.stop();
});

// ---------------------------------------------------------------------------------------------- final fix wave
test("I2: engine.json is there but the port cannot be reached (the socket throws at once, or /status throws) -> blocked, not 'not running'", async () => {
  // the WebSocket constructor throws (a network permission refusing the port): no probe needed
  const a = rig({ openThrows: true });
  a.src.start();
  await a.clock.advance(0);
  assert.equal(a.src.diagnosis.code, "blocked");
  assert.match(a.src.diagnosis.text, /could not reach the engine on its port/);
  // C2.2: the how the editor may read names no command; the command that fixes it is in the log line (and diagnostics)
  assert.match(a.src.diagnosis.how ?? "", /Copy the diagnostics/);
  assert.doesNotMatch(a.src.diagnosis.how ?? "", /reel /);
  assert.ok((await a.src.snapshot()).log.some((l) => l.text.endsWith("[fix: reel serve --status]")), "the log line names the fix command");
  assert.deepEqual(a.probes, []);
  a.src.stop();
  // the socket fails before it opens and the /status probe throws too
  const b = rig({ probeThrows: true });
  b.daemon.mode = "refuse";
  b.src.start();
  await b.clock.advance(0);
  assert.equal(b.src.diagnosis.code, "blocked");
  assert.equal(b.probes.length, 1);
  b.src.stop();
  // a probe that answers nothing in time (null) is still "down"; no engine.json is still no_engine
  const c = rig();
  c.daemon.mode = "refuse";
  c.daemon.statusCode = null;
  c.src.start();
  await c.clock.advance(0);
  assert.equal(c.src.diagnosis.code, "down");
  c.src.stop();
  const d = rig({ record: undefined, openThrows: true });
  d.src.start();
  await d.clock.advance(1000);
  assert.equal(d.src.diagnosis.code, "no_engine");
  d.src.stop();
});

test("M1: error{auth} before a close that UXP reports as 1006 is still the wrong-key diagnosis", async () => {
  const r = rig();
  r.daemon.token = TOKEN2;
  r.daemon.receive = (s, m) => {
    if (m.type !== "hello") return;
    s.deliver({ type: "error", code: "auth", message: "The first message must be a hello with the engine token from engine.json." });
    s.serverClose(1006, "");
  };
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.src.diagnosis.code, "auth");
  r.src.stop();
});

test("M2: the socket is refused but /status answers 200 with the token -> the Origin was refused (refused_host)", async () => {
  const r = rig();
  r.daemon.mode = "refuse";
  r.daemon.statusCode = 200;
  r.src.start();
  await r.clock.advance(0);
  assert.equal(r.src.diagnosis.code, "refused_host");
  assert.match(r.src.diagnosis.text, /Origin/);
  r.src.stop();
});

test("C2.3 build stamp: hello carries client.build when the panel has one (valid); welcome.update.panel is kept, an unknown or missing one reads unknown", async () => {
  const r = await connected({ build: "3.0.0.142", update: { panel: "stale" } });
  assert.deepEqual(r.daemon.last.sent[0], { type: "hello", token: TOKEN, client: { kind: "panel", version: "3.0.0", build: "3.0.0.142", protocol: 4, capabilities: [] } });
  assert.ok(validMessage(r.daemon.last.sent[0]), JSON.stringify(validMessage.errors));
  assert.equal(r.src.panelUpdate, "stale");
  r.src.stop();
  for (const [update, want] of [[undefined, "unknown"], [{ panel: "ok" }, "ok"], [{ panel: "newer" }, "newer"], [{ panel: "sideways" }, "unknown"], ["ok", "unknown"]] as const) {
    const q = await connected({ build: "", update });
    assert.equal((q.daemon.last.sent[0]!["client"] as Record<string, unknown>)["build"], undefined, "an empty build is not sent");
    assert.equal(q.src.panelUpdate, want, JSON.stringify(update));
    q.src.stop();
  }
  assert.deepEqual(r.daemon.invalid, []);
});

test("C2.4 Claude pill: every probe state from the daemon is merged (and validates); an unknown word is malformed", async () => {
  const r = await connected();
  for (const claude of ["not_installed", "signed_out", "plugin_outdated", "ready", "working", "waiting", "unknown"]) {
    const st = stubState("uxp", "Premiere Pro 26.5.2");
    (st["state"] as { connection: { claude: string } }).connection.claude = claude;
    r.daemon.last.deliver(st);
    await r.clock.advance(0);
    const now = await r.src.snapshot();
    assert.equal(now.connection.claude, claude);
    assert.ok(validPanelState(now), JSON.stringify(validPanelState.errors));
  }
  const bad = stubState("uxp");
  (bad["state"] as { connection: { claude: string } }).connection.claude = "maybe";
  r.daemon.last.deliver(bad);
  await r.clock.advance(0);
  assert.equal((await r.src.snapshot()).connection.claude, "unknown");
  r.src.stop();
});

test("C2.4 rebuild: without a project_path the message leaves it out (valid); with one it is sent as before", async () => {
  const r = await connected();
  const s = r.daemon.last;
  await r.src.rebuild({ item: "C0239", replace_edited: false });
  assert.deepEqual({ ...sentOf(s, "rebuild")[0]!, id: "x" }, { type: "rebuild", id: "x", item: "C0239", replace_edited: false });
  await r.src.rebuild({ item: "C0239", project_path: "D:/عميل/C0239.prproj", replace_edited: true });
  assert.deepEqual({ ...sentOf(s, "rebuild")[1]!, id: "x" }, { type: "rebuild", id: "x", item: "C0239", project_path: "D:/عميل/C0239.prproj", replace_edited: true });
  assert.deepEqual(r.daemon.invalid, []);
  r.src.stop();
});

// ---------------------------------------------------------------------------------- C2.2 review round 1

test("C2.2 r1: the serve core's own NOT_YET text ('... is not available from the panel yet.') is kept and carries code NOT_YET", async () => {
  const r = await connected();
  r.daemon.notYet = "Approving is not available from the panel yet.";
  const res = await r.src.approve({ item: "C0239", editor_name: "Yunus", fingerprint: "sha256:abc" });
  assert.equal(res.ok, false);
  assert.equal(res.error, "Approving is not available from the panel yet.");
  assert.equal((res as Result & { code?: string }).code, "NOT_YET");
  r.daemon.notYet = "The project file is locked.";
  const other = await r.src.approve({ item: "C0239", editor_name: "Yunus", fingerprint: "sha256:abc" });
  assert.equal((other as Result & { code?: string }).code, undefined, "any other refusal can be tried again");
});

test("C2.2 r1: no how or error the editor reads names engine.json or a raw action id; host-op hows say 'press Try again'", () => {
  const src = readFileSync(new URL("../src/daemon-source.ts", import.meta.url), "utf8");
  const hows = [...src.matchAll(/\bhow: "([^"]*)"/g)].map((m) => m[1]!);
  hows.push(...[...src.matchAll(/^const (?:START|RESTART)_HOW = "([^"]*)"/gm)].map((m) => m[1]!));
  const byCode = src.slice(src.indexOf("const HOW_BY_CODE"));
  hows.push(...[...byCode.matchAll(/^ {2}[a-z_]+: "([^"]*)",$/gm)].map((m) => m[1]!));
  assert.ok(hows.length >= 20, `found ${hows.length} hows`);
  for (const h of hows) assert.doesNotMatch(h, /engine\.json|\$\{/, h);
  assert.doesNotMatch(src, /error: `[^`]*\$\{action\}[^`]*`/, "a raw action id in an error");
  for (const code of ["no_route", "timeout", "rate"]) {
    assert.match(new RegExp(`^ {2}${code}: "([^"]*)",$`, "m").exec(src)![1]!, /press Try again/i, code);
  }
});

// ---------------------------------------------------------------------------------- C2.2 review round 2

test("C2.2 r2: no how names serve-audit.log or 'send the engine log': it says to copy the diagnostics and send them to support", () => {
  const src = readFileSync(new URL("../src/daemon-source.ts", import.meta.url), "utf8");
  assert.doesNotMatch(src, /serve-audit\.log|send the engine log/);
  assert.ok((src.match(/how: "Copy the diagnostics and send them to support\."/g) ?? []).length >= 3);
});

test("C2.2 r2: a failed answer carries a code the panel can localize: the session error code, timeout, lost, too_large, or the link's code when not connected", async () => {
  const r = await connected();
  r.daemon.onCommand = (s, m) => {
    const req = m["request"] as { id: string };
    s.deliver({ type: "error", code: "no_route", message: "No Premiere panel is connected (run reel doctor).", id: req.id });
  };
  const res = await r.src.run("open_project", { path: "D:/x.prproj" });
  assert.equal(res.ok, false);
  assert.equal(res.code, "no_route");
  r.src.stop();
  const off = await r.src.run("open_project", { path: "D:/x.prproj" });
  assert.equal(off.code, "stopped");
});

// ---------------------------------------------------------------------------------------------------- G2 H1 jobs
const job = (request_id: string, action: string, state: string, result?: object) => ({
  request_id, action, state, submitted_at: "2026-10-14T11:40:02Z", updated_at: "2026-10-14T11:41:30Z", ...(result ? { result } : {}),
});
const reqId = (m: Msg | undefined) => (m!["request"] as { id: string }).id;
const answerOk = (seen?: string[]) => (s: FakeSocket, m: Msg) => {
  const req = m["request"] as { id: string; action: string };
  seen?.push(req.id);
  s.deliver({ type: "result", result: { ok: true, action: req.action, readback: {}, id: req.id } });
};

test("H1 reattach: a command outlives a lost link; after the reconnect jobs[] reattaches it by request id and the real outcome shows, not lost", async () => {
  const r = await connected();
  r.daemon.onCommand = () => {}; // Premiere is still working on it
  const p = r.src.run("build_project", {});
  await flush();
  const id = reqId(sentOf(r.daemon.last, "command")[0]);
  r.daemon.last.serverClose(1006, ""); // the panel's session drops mid-job
  await flush();
  const running = (await r.src.snapshot()).pipeline.find((x) => x.id === "build")!;
  assert.deepEqual([running.state, running.request_id], ["running", id]);
  // meanwhile the daemon finished it and journaled the result
  r.daemon.jobs = [job(id, "build_project", "done", { ok: true }), job("other-1", "ping", "interrupted", { ok: false, code: "interrupted" })];
  const resent: string[] = [];
  r.daemon.onCommand = (s, m) => {
    const req = m["request"] as { id: string; action: string };
    resent.push(req.id);
    s.deliver({ type: "result", result: { ok: true, action: req.action, readback: { project_path: "D:/p.prproj" }, id: req.id } });
  };
  await r.clock.advance(1000);
  assert.equal(r.src.diagnosis.code, "connected");
  const res = await p;
  assert.deepEqual(resent, [id], "the same request id is sent again: the daemon replays it, the host runs it once");
  assert.equal(res.ok, true);
  assert.deepEqual(res.readback, { project_path: "D:/p.prproj" });
  assert.equal((await r.src.snapshot()).pipeline.find((x) => x.id === "build")!.state, "done");
  for (const st of r.states) assert.ok(validPanelState(st), JSON.stringify(validPanelState.errors));
  assert.deepEqual(r.daemon.invalid, []);
});

test("H1 reattach: an interrupted job answers with its stored failure and code interrupted; Try again is then a new request id", async () => {
  const r = await connected();
  r.daemon.onCommand = () => {};
  const p = r.src.run("status", {});
  await flush();
  const id = reqId(sentOf(r.daemon.last, "command")[0]);
  r.daemon.last.serverClose(1006, "");
  await flush();
  r.daemon.jobs = [job(id, "status", "interrupted", { ok: false, code: "interrupted" })];
  r.daemon.onCommand = (s, m) => {
    const req = m["request"] as { id: string; action: string };
    s.deliver({ type: "result", result: { ok: false, action: req.action, error: "The job stopped before it finished.", how: "Press Try again.", id: req.id } });
  };
  await r.clock.advance(1000);
  const res = await p;
  assert.deepEqual([res.ok, res.code, res.error], [false, "interrupted", "The job stopped before it finished."]);
  const seen: string[] = [];
  r.daemon.onCommand = answerOk(seen);
  assert.equal((await r.src.run("status", {})).ok, true);
  assert.equal(seen.length, 1);
  assert.notEqual(seen[0], id);
});

test("H1 Try again: after a lost answer the same request id is reused (attach / replay), unless jobs[] says failed or interrupted", async () => {
  const r = await connected();
  r.daemon.onCommand = () => {};
  const p = r.src.run("status", {});
  await flush();
  const id1 = reqId(sentOf(r.daemon.last, "command")[0]);
  r.daemon.last.serverClose(1006, "");
  await flush();
  r.daemon.jobs = []; // the daemon never got it
  await r.clock.advance(1000);
  assert.equal((await p).code, "lost");
  const seen: string[] = [];
  r.daemon.onCommand = answerOk(seen);
  assert.equal((await r.src.run("status", {})).ok, true); // Try again
  assert.deepEqual(seen, [id1], "Try again reuses the unsettled request id");
  assert.equal((await r.src.run("status", {})).ok, true); // after a settled answer the next run is a new id
  assert.notEqual(seen[1], id1);
  // a lost answer whose job the journal later shows as interrupted: Try again is a new run
  r.daemon.onCommand = () => {};
  const p3 = r.src.run("status", { again: 1 });
  await flush();
  const id3 = reqId(sentOf(r.daemon.last, "command").at(-1));
  r.daemon.last.serverClose(1006, "");
  await flush();
  r.daemon.jobs = [];
  await r.clock.advance(1000);
  assert.equal((await p3).code, "lost");
  r.daemon.jobs = [job(id3, "status", "interrupted", { ok: false, code: "interrupted" })];
  await r.clock.advance(2000); // the next poll's state carries it
  r.daemon.onCommand = answerOk(seen);
  assert.equal((await r.src.run("status", { again: 1 })).ok, true);
  assert.notEqual(seen.at(-1), id3);
  assert.deepEqual(r.daemon.invalid, []);
});

test("H1: a jobs[] entry that is malformed is skipped, never the whole state", async () => {
  const r = await connected();
  r.daemon.onCommand = () => {};
  const p = r.src.run("status", {});
  await flush();
  const id = reqId(sentOf(r.daemon.last, "command")[0]);
  r.daemon.last.serverClose(1006, "");
  await flush();
  const st = stubState("uxp") as { state: Record<string, unknown> };
  st.state["jobs"] = [{ request_id: "a b", action: "status", state: "done" }, job("x-1", "nope", "done"), job("x-2", "status", "weird"), job(id, "status", "done", { ok: true })];
  r.daemon.onCommand = answerOk();
  const realReceive = r.daemon.receive.bind(r.daemon);
  r.daemon.receive = (s, m) => (m.type === "snapshot" && s.sent.length === 2 ? s.deliver(st) : realReceive(s, m));
  await r.clock.advance(1000);
  assert.equal(r.src.diagnosis.code, "connected");
  assert.equal((await r.src.snapshot()).connection.engine, "connected");
  assert.equal((await p).ok, true); // the good entry still reattached it
});
