// Spike 0.1.3: the live reel serve link (engine.json, hello/welcome, snapshot, 70 s idle keepalive, the Origin the daemon
// audits), the three unmeasured host calls (SourceMonitor.openFilePath, Sequence.setPlayerPosition, shell.openPath) and the
// ms-stamped sub-calls of sequence_settings / export_frame - all against hand-made fakes (no Premiere, no daemon).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildProbes, loadConfig, type Ctx, type SpikeConfig } from "../spike/src/probes.ts";
import { runProbe } from "../spike/src/runner.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const WT = "D:/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/whynot-test";
const WORK = `${WT}/_uxp-spike`;
const MP4_SRC = `${WT}/PODCAST-TEST/output/projects/EP02TEST_R02/08_quality_control/preview/EP02TEST_R02_preview.mp4`;
const CONFIG: SpikeConfig = { xml_path: `${WT}/a.xml`, work_dir: WORK, still_png: `${WT}/s.png`, mp4_source: MP4_SRC };
const TOKEN = "d4".repeat(32);
const HOME = "C:/Users/LOQ";
const ENGINE_JSON = `${HOME}/.whynot-cut/bridge/engine.json`;

function probe(op: string) {
  const p = buildProbes().find((d) => d.op === op);
  assert.ok(p, `no probe ${op}`);
  return p;
}

type Step = { step: string; ok: boolean; at: string; ms: number; info?: Record<string, unknown>; error?: string };
const stepsOf = (r: { detail: unknown }) => (r.detail as { steps: Step[] }).steps;
const stepNamed = (r: { detail: unknown }, prefix: string) => {
  const s = stepsOf(r).find((x) => x.step.startsWith(prefix));
  assert.ok(s, `no step starting with "${prefix}" in ${stepsOf(r).map((x) => x.step).join(" | ")}`);
  return s;
};
const hasStep = (r: { detail: unknown }, prefix: string) => stepsOf(r).some((x) => x.step.startsWith(prefix));

function baseCtx(ppro: unknown, extra: Partial<Ctx> = {}): Ctx {
  return {
    ppro: ppro as Ctx["ppro"],
    fs: {},
    uxp: { host: { name: "premierepro", version: "26.5.2" }, versions: { uxp: "uxp-9.3.0-local" } },
    os: undefined,
    home: HOME,
    homeVia: "os.homedir",
    stamp: "20261012-120000",
    config: CONFIG,
    configError: null,
    expect: {},
    notes: [],
    ...extra,
  };
}

// ---- fake fs with files in memory ------------------------------------------------------------------------------------

function memFs(initial: Record<string, string | ArrayBuffer> = {}) {
  const files = new Map<string, string | ArrayBuffer>(Object.entries(initial).map(([k, v]) => [k.replace(/\\/g, "/").toLowerCase(), v]));
  const reads: string[] = [];
  const norm = (p: string) => p.replace(/\\/g, "/").toLowerCase();
  const fs = {
    files,
    reads,
    readFile: async (p: string, opts?: unknown) => {
      reads.push(norm(p));
      const v = files.get(norm(p));
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      if (opts && typeof v !== "string") return new TextDecoder().decode(v);
      return v;
    },
    writeFile: async (p: string, data: string | ArrayBuffer) => void files.set(norm(p), data),
    lstat: async (p: string) => {
      const v = files.get(norm(p));
      if (v === undefined) {
        if (!/\.[a-z0-9]+$/i.test(p)) return { size: 0, isDirectory: () => true };
        throw new Error("ENOENT");
      }
      return { size: typeof v === "string" ? v.length : v.byteLength, isDirectory: () => false };
    },
    mkdir: async () => {},
  };
  return fs;
}

function engineFile(extra: Record<string, unknown> = {}) {
  return JSON.stringify({ port: 51234, token: TOKEN, pid: 4242, version: "3.0.0", protocol: 4, started_at: "2026-10-12T10:00:00Z", home: "C:/Users/LOQ/.whynot-cut", ...extra });
}

// ---- fake WebSocket + daemon -----------------------------------------------------------------------------------------

interface Behaviour {
  /** "open" (default), or "refuse": error + close 1006 without ever opening (a 403 on the upgrade looks like this) */
  connect?: "open" | "refuse";
  onSend?: (ws: FakeWs, msg: Record<string, unknown>) => void;
  /** the close reason the fake reports for a close() by the spike */
  closeReason?: string;
}

class FakeWs {
  static all: FakeWs[] = [];
  static behaviour: Behaviour = {};
  url: string;
  readyState = 0;
  protocol = "";
  extensions = "";
  sent: string[] = [];
  onopen: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onclose: ((e: { code: number; reason: string; wasClean: boolean }) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeWs.all.push(this);
    setTimeout(() => {
      if (FakeWs.behaviour.connect === "refuse") {
        this.readyState = 3;
        this.onerror?.({ message: "error" });
        this.onclose?.({ code: 1006, reason: "", wasClean: false });
        return;
      }
      this.readyState = 1;
      this.onopen?.({});
    }, 1);
  }
  send(m: string) {
    this.sent.push(m);
    const msg = JSON.parse(m) as Record<string, unknown>;
    FakeWs.behaviour.onSend?.(this, msg);
  }
  emit(obj: unknown) {
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(obj) }), 1);
  }
  drop(code: number, reason: string) {
    if (this.readyState === 3) return;
    this.readyState = 3;
    setTimeout(() => this.onclose?.({ code, reason, wasClean: code === 1000 }), 1);
  }
  close(code = 1000, reason = "") {
    this.drop(code, FakeWs.behaviour.closeReason ?? reason);
  }
}

const STATE = { connection: "connected", pipeline: [], flagged: [], note: "x".repeat(10) };

/** a well-behaved daemon: welcome to a hello, a state to every snapshot */
const GOOD: Behaviour = {
  onSend: (ws, msg) => {
    if (msg.type === "hello") ws.emit({ type: "welcome", session_id: "sess-1", protocol: 4, daemon_version: "3.0.0" });
    if (msg.type === "snapshot") ws.emit({ type: "state", state: STATE, id: msg.id });
  },
};

async function withWs<T>(behaviour: Behaviour, fn: () => Promise<T>, fetchImpl?: unknown): Promise<T> {
  const g = globalThis as { WebSocket?: unknown; fetch?: unknown };
  const saved = { ws: g.WebSocket, fetch: g.fetch };
  FakeWs.all = [];
  FakeWs.behaviour = behaviour;
  g.WebSocket = FakeWs;
  g.fetch = fetchImpl ?? (async () => ({ status: 200, json: async () => ({ ok: true, protocol: 4, daemon_version: "3.0.0", port: 51234, pid: 4242 }) }));
  try {
    return await fn();
  } finally {
    g.WebSocket = saved.ws;
    g.fetch = saved.fetch;
  }
}

const FAST = { wsIdleMs: 40, wsRetryMs: 1, wsReplyMs: 400 };

// ---- ws_loopback ------------------------------------------------------------------------------------------------------

test("ws_loopback: reads engine.json, hellos as uxp/protocol 4 with the token, gets welcome + state, survives the idle, closes - and never records the token", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const ctx = baseCtx({}, { fs, timing: FAST });
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), ctx));
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 900));
  assert.equal(FakeWs.all.length, 1);
  const ws = FakeWs.all[0] as FakeWs;
  assert.equal(ws.url, "ws://127.0.0.1:51234/session");
  const hello = JSON.parse(ws.sent[0] ?? "{}") as { type: string; token: string; client: Record<string, unknown> };
  assert.equal(hello.type, "hello");
  assert.equal(hello.token, TOKEN);
  assert.deepEqual(hello.client, { kind: "uxp", version: "0.1.7", host: "premiere", hostVersion: "26.5.2", protocol: 4, capabilities: [] });
  assert.equal(JSON.parse(ws.sent[1] ?? "{}").type, "snapshot");

  const eng = stepNamed(r, "engine.json").info as Record<string, unknown>;
  assert.equal(eng.token_length, 64);
  assert.equal(eng.token_read, true);
  assert.equal(eng.port, 51234);
  assert.equal(eng.path, ENGINE_JSON);
  assert.ok(!("token" in eng), "the token itself is not a field");

  const welcome = stepNamed(r, "hello").info as Record<string, unknown>;
  assert.equal(welcome.welcome_type, "welcome");
  assert.equal(welcome.session_id, "sess-1");
  assert.equal(welcome.daemon_version, "3.0.0");
  const snap = stepNamed(r, "snapshot").info as { state_keys: string[]; state_connection: unknown; round_trip_ms: number };
  assert.deepEqual(snap.state_keys, Object.keys(STATE));
  assert.equal(snap.state_connection, "connected");
  assert.equal(typeof snap.round_trip_ms, "number");
  const idle = stepNamed(r, "idle");
  assert.equal(idle.ok, true);
  assert.equal((idle.info as { open_at_end: boolean }).open_at_end, true);
  assert.equal((idle.info as { post_idle_state_ok: boolean }).post_idle_state_ok, true);
  assert.equal(stepNamed(r, "close").ok, true);
  assert.equal(ws.readyState, 3, "the socket is closed at the end");

  // the controller matches the daemon's audit `origin` row by this time and finds the log next to engine.json's home
  const d = r.detail as { started_at: string; started_epoch_ms: number; audit_log: string };
  assert.match(d.started_at, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);
  assert.equal(typeof d.started_epoch_ms, "number");
  assert.match(d.audit_log, /serve-audit\.log$/);
  assert.ok(!JSON.stringify(r).includes(TOKEN), "the token must not appear anywhere in the results");
});

test("ws_loopback: needs no config.json (the link is read-only); engine.json is retried 5 times x delay, then 'daemon not running' with no socket opened", async () => {
  const fs = memFs({});
  const ctx = baseCtx({}, { fs, timing: FAST, config: null, configError: "no config" });
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), ctx));
  assert.equal(r.ok, false);
  assert.equal(FakeWs.all.length, 0);
  assert.equal(fs.reads.filter((p) => p === ENGINE_JSON.toLowerCase()).length, 5, "5 attempts");
  const step = stepNamed(r, "engine.json");
  assert.equal(step.ok, false);
  assert.match(step.error ?? "", /not found|reel serve/i);
  assert.equal((step.info as { attempts: number }).attempts, 5);
  assert.ok(!hasStep(r, "connect"));
});

test("ws_loopback: an engine.json that appears on the 3rd read is used", async () => {
  const fs = memFs({});
  let n = 0;
  const realRead = fs.readFile;
  fs.readFile = async (p: string, o?: unknown) => {
    if (++n === 3) fs.files.set(ENGINE_JSON.toLowerCase(), engineFile());
    return realRead(p, o);
  };
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 600));
  assert.equal((stepNamed(r, "engine.json").info as { attempts: number }).attempts, 3);
});

test("ws_loopback: a bad engine.json (no port / no token) fails the first step and keeps the field names, not values", async () => {
  const fs = memFs({ [ENGINE_JSON]: JSON.stringify({ pid: 1, token: "" }) });
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  assert.equal(r.ok, false);
  const step = stepNamed(r, "engine.json");
  assert.equal(step.ok, false);
  assert.match(step.error ?? "", /port|token/);
  assert.equal(FakeWs.all.length, 0);
});

test("ws_loopback: a refused upgrade (HTTP 403 for a rejected Origin looks like error + close 1006) is recorded as the connect failure and stops the probe", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const r = await withWs({ connect: "refuse" }, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  assert.equal(r.ok, false);
  const step = stepNamed(r, "connect");
  assert.equal(step.ok, false);
  const info = step.info as { opened: boolean; close_code: number; error_events: number; started_at: string };
  assert.equal(info.opened, false);
  assert.equal(info.close_code, 1006);
  assert.ok(info.error_events >= 1);
  assert.match(step.error ?? "", /did not open|upgrade|403/i);
  assert.ok(!hasStep(r, "hello"), "no hello is sent on a socket that never opened");
  assert.ok(!JSON.stringify(r).includes(TOKEN));
});

test("ws_loopback: a daemon error to the hello (auth / origin / schema) is recorded with its code; the token is redacted from the message", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const behaviour: Behaviour = { onSend: (ws, msg) => msg.type === "hello" && ws.emit({ type: "error", code: "auth", message: `bad token ${TOKEN} given` }) };
  const r = await withWs(behaviour, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  assert.equal(r.ok, false);
  const step = stepNamed(r, "hello");
  assert.equal(step.ok, false);
  const info = step.info as { welcome_type: string; error_code: string; error_message: string };
  assert.equal(info.welcome_type, "error");
  assert.equal(info.error_code, "auth");
  assert.match(info.error_message, /\[redacted\]/);
  assert.ok(!JSON.stringify(r).includes(TOKEN));
  assert.ok(!hasStep(r, "snapshot"), "no snapshot after a failed hello");
});

test("ws_loopback: the daemon closing during the idle (code + reason + how long it held) fails the keepalive step", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const behaviour: Behaviour = {
    onSend: (ws, msg) => {
      GOOD.onSend?.(ws, msg);
      if (msg.type === "snapshot") setTimeout(() => ws.drop(1001, "idle timeout"), 10);
    },
  };
  const r = await withWs(behaviour, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: { ...FAST, wsIdleMs: 300 } })));
  assert.equal(r.ok, false);
  const idle = stepNamed(r, "idle");
  assert.equal(idle.ok, false);
  const info = idle.info as { closed: boolean; close_code: number; close_reason: string; closed_after_idle_ms: number };
  assert.equal(info.closed, true);
  assert.equal(info.close_code, 1001);
  assert.equal(info.close_reason, "idle timeout");
  assert.ok(info.closed_after_idle_ms < 300);
});

test("ws_loopback: a silent daemon (no state to the snapshot) fails the snapshot step but the probe still closes the socket", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const behaviour: Behaviour = { onSend: (ws, msg) => msg.type === "hello" && ws.emit({ type: "welcome", session_id: "s", protocol: 4, daemon_version: "3.0.0" }) };
  const r = await withWs(behaviour, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: { ...FAST, wsReplyMs: 40 } })));
  assert.equal(r.ok, false);
  assert.equal(stepNamed(r, "snapshot").ok, false);
  assert.equal((FakeWs.all[0] as FakeWs).readyState, 3);
});

test("ws_loopback: the HTTP side is measured too (fetch /status with the bearer token: status code + body KEYS only), and a fetch failure never fails the link", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const seen: Array<{ url: string; auth: string | undefined }> = [];
  const fetchOk = async (url: string, init?: { headers?: Record<string, string> }) => {
    seen.push({ url, auth: init?.headers?.Authorization });
    return { status: 200, json: async () => ({ ok: true, protocol: 4, token: TOKEN }) };
  };
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })), fetchOk);
  assert.equal(r.ok, true);
  assert.equal(seen[0]?.url, "http://127.0.0.1:51234/status");
  assert.equal(seen[0]?.auth, `Bearer ${TOKEN}`);
  const http = stepNamed(r, "http").info as { status: number; body_keys: string[] };
  assert.equal(http.status, 200);
  assert.deepEqual(http.body_keys, ["ok", "protocol", "token"]);
  assert.ok(!JSON.stringify(r).includes(TOKEN));

  const fs2 = memFs({ [ENGINE_JSON]: engineFile() });
  const boom = async () => {
    throw new Error("Network request failed");
  };
  const r2 = await withWs(GOOD, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs: fs2, timing: FAST })), boom);
  assert.equal(r2.ok, true, "a fetch failure is informational");
  assert.match(String((stepNamed(r2, "http").info as { error: string }).error), /Network request failed/);
});

// ---- host_calls -------------------------------------------------------------------------------------------------------

function mp4Bytes(n = 2048) {
  const b = new Uint8Array(n);
  for (let i = 0; i < n; i++) b[i] = i % 251;
  return b.buffer;
}

function hostRig(opts: { openFile?: () => Promise<boolean>; openPath?: (p: string, t?: string) => Promise<string | undefined>; skipShell?: boolean; sourceMissing?: boolean } = {}) {
  const fs = memFs(opts.sourceMissing ? {} : { [MP4_SRC]: mp4Bytes() });
  const calls: string[] = [];
  const openedPaths: Array<{ path: string; text?: string }> = [];
  let player = 7;
  const items: string[] = [];
  const seq = {
    name: "SEQ",
    guid: { toString: () => "seq-guid" },
    getEndTime: async () => ({ seconds: 20 }),
    setPlayerPosition: async (t: { seconds: number }) => {
      calls.push(`setPlayerPosition(${t.seconds})`);
      if (t.seconds < 0) throw new Error("negative time");
      player = Math.min(t.seconds, 20);
      return true;
    },
    getPlayerPosition: async () => ({ seconds: player }),
  };
  const project = {
    name: "spike.prproj",
    path: `\\\\?\\${WORK}/spike-1.prproj`,
    getActiveSequence: async () => seq,
    setActiveSequence: async () => true,
    openSequence: async () => true,
    getRootItem: async () => ({ getItems: async () => items.map((name) => ({ name })) }),
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: () => true,
  };
  const ppro = {
    TickTime: { createWithSeconds: (seconds: number) => ({ seconds }) },
    Project: { getActiveProject: async () => project },
    SourceMonitor: {
      openFilePath: async (p: string) => {
        calls.push(`openFilePath(${p})`);
        items.push("spike-source.mp4");
        return opts.openFile ? opts.openFile() : true;
      },
      getProjectItem: async () => ({ name: "spike-source.mp4" }),
      getPosition: async () => ({ seconds: 0 }),
      closeClip: async () => {
        calls.push("closeClip");
        return true;
      },
    },
  };
  const uxp: Record<string, unknown> = { host: { name: "premierepro", version: "26.5.2" }, versions: {} };
  if (!opts.skipShell)
    uxp.shell = {
      openPath: async (p: string, text?: string) => {
        openedPaths.push({ path: p, ...(text === undefined ? {} : { text }) });
        return opts.openPath ? opts.openPath(p, text) : "";
      },
    };
  const ctx = baseCtx(ppro, { fs, uxp: uxp as Ctx["uxp"], project: project as never, sequence: seq as never, timing: { shellTimeoutMs: 150 } });
  return { ctx, fs, calls, openedPaths, seq };
}

test("host_calls: copies the scratch mp4 into work_dir, opens it in the Source Monitor with the native backslash path, reads the position back", async () => {
  const { ctx, fs, calls } = hostRig();
  const r = await runProbe(probe("host_calls"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 1200));
  const copy = stepNamed(r, "scratch media").info as { path: string; bytes: number; source_bytes: number };
  assert.equal(copy.path, `${WORK}/spike-20261012-120000-source.mp4`);
  assert.equal(copy.bytes, 2048);
  assert.equal(copy.source_bytes, 2048);
  const written = fs.files.get(copy.path.toLowerCase()) as ArrayBuffer;
  assert.deepEqual(new Uint8Array(written), new Uint8Array(mp4Bytes()), "an exact copy");
  const native = `${WORK.replace(/\//g, "\\")}\\spike-20261012-120000-source.mp4`;
  assert.ok(calls.includes(`openFilePath(${native})`), calls.join(" | "));
  const sm = stepNamed(r, "SourceMonitor.openFilePath").info as { returned: boolean; items_before: number; items_after: number; path_used: string; source_item_name: string };
  assert.equal(sm.returned, true);
  assert.equal(sm.path_used, native);
  assert.equal(sm.items_before, 0);
  assert.equal(sm.items_after, 1);
  assert.equal(sm.source_item_name, "spike-source.mp4");
  assert.ok(calls.includes("closeClip"), "the Source Monitor clip is closed afterwards");
});

test("host_calls: the source must exist and be under whynot-test; a missing mp4_source fails that step only and the other host calls still run", async () => {
  const noCfg = hostRig();
  noCfg.ctx.config = { ...CONFIG };
  delete (noCfg.ctx.config as { mp4_source?: string }).mp4_source;
  const r = await runProbe(probe("host_calls"), noCfg.ctx);
  assert.equal(r.ok, false);
  const m = stepNamed(r, "scratch media");
  assert.equal(m.ok, false);
  assert.match(m.error ?? "", /mp4_source/);
  assert.ok(!hasStep(r, "SourceMonitor.openFilePath"), "no source monitor step without a copy");
  assert.equal(stepNamed(r, "Sequence.setPlayerPosition").ok, true);
  assert.equal(noCfg.openedPaths.length, 2, "the folder (twice) is still opened; the mp4 is not");

  const gone = hostRig({ sourceMissing: true });
  const r2 = await runProbe(probe("host_calls"), gone.ctx);
  assert.match(stepNamed(r2, "scratch media").error ?? "", /does not exist/);
});

test("host_calls: a source outside whynot-test is refused by the safety guard (the config is rejected at load time and the copy re-checks)", async () => {
  const rig = hostRig();
  rig.ctx.config = { ...CONFIG, mp4_source: "D:/WhyNot Clients/C0239/assets/raw.mp4" };
  const r = await runProbe(probe("host_calls"), rig.ctx);
  assert.match(stepNamed(r, "scratch media").error ?? "", /whynot clients|not under/i);
  assert.equal([...rig.fs.files.keys()].filter((k) => k.endsWith("-source.mp4")).length, 0);
  const loaded = await loadConfig(memFs({ [`${HOME}/.whynot-cut/uxp-spike/config.json`]: JSON.stringify({ ...CONFIG, mp4_source: "D:/WhyNot Clients/C0239/assets/raw.mp4" }) }), `${HOME}/.whynot-cut/uxp-spike`);
  assert.equal(loaded.config, null);
  assert.match(loaded.error ?? "", /mp4_source/);
});

test("host_calls: SourceMonitor.openFilePath returning false fails that step but keeps the return value and the item counts", async () => {
  const { ctx } = hostRig({ openFile: async () => false });
  const r = await runProbe(probe("host_calls"), ctx);
  const sm = stepNamed(r, "SourceMonitor.openFilePath");
  assert.equal(sm.ok, false);
  assert.equal((sm.info as { returned: boolean }).returned, false);
  assert.match(sm.error ?? "", /false/);
  assert.equal(stepNamed(r, "Sequence.setPlayerPosition").ok, true, "the next host call still ran");
});

test("host_calls: setPlayerPosition is set at three times and read back with getPlayerPosition; the player position is restored; beyond-end / negative are informational", async () => {
  const { ctx, calls, seq } = hostRig();
  const r = await runProbe(probe("host_calls"), ctx);
  const step = stepNamed(r, "Sequence.setPlayerPosition");
  assert.equal(step.ok, true, JSON.stringify(step));
  const info = step.info as { initial_s: number; active_sequence_is_scratch: boolean; points: Array<{ wanted_s: number; returned: boolean; read_back_s: number; delta_s: number }>; restored_s: number };
  assert.equal(info.initial_s, 7);
  assert.equal(info.active_sequence_is_scratch, true);
  assert.equal(info.points.length, 3);
  assert.deepEqual(info.points.map((p) => p.wanted_s), [5, 10, 15]);
  assert.ok(info.points.every((p) => p.returned === true && Math.abs(p.delta_s) <= 0.05));
  assert.equal(info.restored_s, 7);
  assert.ok(calls.includes("setPlayerPosition(5)") && calls.includes("setPlayerPosition(15)"));
  const edge = stepNamed(r, "setPlayerPosition beyond").info as { beyond_end: Record<string, unknown>; negative: Record<string, unknown> };
  assert.equal(edge.beyond_end.wanted_s, 30);
  assert.match(String(edge.negative.error), /negative time/);
  assert.equal(stepNamed(r, "setPlayerPosition beyond").ok, true);
  // the beyond-end probe moved the playhead (clamped to 20 s): the original position is put back so later probes start clean
  const restored = (edge as unknown as { restored_original: { wanted_s: number; read_back_s: number } }).restored_original;
  assert.equal(restored.wanted_s, 7);
  assert.equal(restored.read_back_s, 7);
  assert.equal((await seq.getPlayerPosition()).seconds, 7);
  assert.equal(calls.filter((c) => c.startsWith("setPlayerPosition(")).at(-1), "setPlayerPosition(7)");
});

test("host_calls: a read-back that differs from what was set fails the step and keeps every point", async () => {
  const { ctx, seq } = hostRig();
  seq.getPlayerPosition = async () => ({ seconds: 0 });
  const r = await runProbe(probe("host_calls"), ctx);
  const step = stepNamed(r, "Sequence.setPlayerPosition");
  assert.equal(step.ok, false);
  assert.equal((step.info as { points: unknown[] }).points.length, 3);
});

test("host_calls: shell.openPath on the work_dir folder, the mp4, and the folder again - native backslash paths, developer text, return value and consent timing", async () => {
  const { ctx, openedPaths } = hostRig({
    openPath: async (p: string) => {
      if (p.endsWith(".mp4")) await new Promise((res) => setTimeout(res, 30));
      return "";
    },
  });
  const r = await runProbe(probe("host_calls"), ctx);
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 800));
  const native = WORK.replace(/\//g, "\\");
  assert.deepEqual(openedPaths.map((o) => o.path), [native, `${native}\\spike-20261012-120000-source.mp4`, native]);
  assert.ok(openedPaths.every((o) => typeof o.text === "string" && o.text.length > 0), "developer text is passed");
  const folder = stepNamed(r, "shell.openPath folder").info as { path_used: string; returned: string; ms: number; started_at: string; timed_out: boolean; consent_dialog_suspected: boolean };
  assert.equal(folder.path_used, native);
  assert.equal(folder.returned, "");
  assert.equal(folder.timed_out, false);
  assert.equal(folder.consent_dialog_suspected, false);
  assert.match(folder.started_at, /^\d{4}-\d\d-\d\dT/);
  assert.ok(hasStep(r, "shell.openPath mp4"));
  assert.ok(hasStep(r, "shell.openPath folder again"));
});

test("host_calls: openPath answering with an error text, throwing, hanging (a consent dialog nobody answered) or missing are each a failed step that keeps the measurement", async () => {
  const err = hostRig({ openPath: async () => "Permission denied" });
  const r1 = await runProbe(probe("host_calls"), err.ctx);
  const s1 = stepNamed(r1, "shell.openPath folder");
  assert.equal(s1.ok, false);
  assert.equal((s1.info as { returned: string }).returned, "Permission denied");

  const boom = hostRig({
    openPath: async () => {
      throw new Error("not allowed by the manifest");
    },
  });
  const r2 = await runProbe(probe("host_calls"), boom.ctx);
  assert.match(stepNamed(r2, "shell.openPath folder").error ?? "", /not allowed by the manifest/);

  const hang = hostRig({ openPath: () => new Promise<string>(() => {}) });
  const r3 = await runProbe(probe("host_calls"), hang.ctx);
  const s3 = stepNamed(r3, "shell.openPath folder");
  assert.equal(s3.ok, false);
  assert.equal((s3.info as { timed_out: boolean }).timed_out, true);
  assert.equal(hasStep(r3, "shell.openPath mp4"), true, "the next call is still attempted after a timeout");

  const none = hostRig({ skipShell: true });
  const r4 = await runProbe(probe("host_calls"), none.ctx);
  assert.match(stepNamed(r4, "shell.openPath folder").error ?? "", /not available/);
});

test("host_calls: never touches a project that is not the scratch project (no scratch project -> refuses before any host call)", async () => {
  const { ctx, calls, openedPaths, fs } = hostRig();
  ctx.project = undefined;
  const r = await runProbe(probe("host_calls"), ctx);
  assert.equal(r.ok, false);
  assert.match(r.error ?? "", /no scratch project|refusing/);
  assert.deepEqual(calls, []);
  assert.deepEqual(openedPaths, []);
  assert.equal([...fs.files.keys()].filter((k) => k.endsWith("-source.mp4")).length, 0);
});

test("probe order: host_calls runs after project_views and before undo_transaction (the last mutating probe); it is not read-only (needs the config)", () => {
  const ops = buildProbes().map((p) => p.op);
  assert.ok(ops.indexOf("host_calls") > ops.indexOf("project_views"));
  assert.ok(ops.indexOf("host_calls") < ops.indexOf("undo_transaction"));
  assert.ok(ops.indexOf("export_frame") < ops.indexOf("host_calls"));
});

// ---- 0.1.3 packaging --------------------------------------------------------------------------------------------------

test("spike 0.1.7 (the 0.1.3 probes + C2.7): manifest version + launchProcess (the product's entry plus the whynotcut scheme), SPIKE_VERSION, example config", () => {
  const manifest = JSON.parse(readFileSync(join(root, "spike", "manifest.json"), "utf8"));
  const product = JSON.parse(readFileSync(join(root, "plugin", "manifest.json"), "utf8"));
  assert.equal(manifest.version, "0.1.7");
  // C2.7: openExternal("whynotcut://engine/start") needs its scheme in launchProcess; everything else is the product's entry
  assert.deepEqual(manifest.requiredPermissions.launchProcess, { schemes: ["file", "whynotcut"], extensions: [".mp4", ".mov", ".prproj", ""] });
  assert.deepEqual(manifest.requiredPermissions.launchProcess.extensions, product.requiredPermissions.launchProcess.extensions);
  assert.deepEqual(product.requiredPermissions.launchProcess.schemes, ["file"]);
  assert.equal(manifest.requiredPermissions.clipboard, "readAndWrite");
  assert.equal(manifest.requiredPermissions.localFileSystem, "fullAccess");
  // C2.7: the spike measures an explicit loopback list (test/spike-016.test.ts); the product stays at "all" until that
  // list is shown to work live (round-1 evidence for "all": results-20261012-211920, parity W1/W2)
  assert.ok(Array.isArray(manifest.requiredPermissions.network.domains));
  assert.equal(product.requiredPermissions.network.domains, "all");
  assert.match(readFileSync(join(root, "spike", "src", "version.ts"), "utf8"), /SPIKE_VERSION = "0.1.7"/);
  const spike = readFileSync(join(root, "spike", "src", "spike.ts"), "utf8");
  assert.match(spike, /import \{ SPIKE_VERSION \} from "\.\/version\.ts"/);
  assert.doesNotMatch(spike, /SPIKE_VERSION = "/, "one source of truth for the version");
  const example = JSON.parse(readFileSync(join(root, "spike", "config.example.json"), "utf8"));
  assert.match(example.mp4_source, /whynot-test\/PODCAST-TEST\/.+\.mp4$/);
  assert.ok(!("ws_url" in example) || example.ws_url === null);
});

// ---- ms stamps for the "Project Modified" attribution ------------------------------------------------------------------

type Call = { call: string; at: string; at_ms: number; ms: number; ok: boolean; error?: string };
const callsOf = (r: { detail: unknown }) => (r.detail as { calls?: Call[] }).calls ?? [];

function assertStamped(calls: Call[], expected: RegExp[]) {
  assert.ok(calls.length > 0, "calls are recorded");
  for (const c of calls) {
    assert.match(c.at, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/, c.call);
    assert.equal(typeof c.at_ms, "number");
    assert.equal(typeof c.ms, "number");
  }
  for (let i = 1; i < calls.length; i++) assert.ok((calls[i] as Call).at_ms >= (calls[i - 1] as Call).at_ms, "calls are in time order");
  for (const rx of expected) assert.ok(calls.some((c) => rx.test(c.call)), `no call matching ${rx} in ${calls.map((c) => c.call).join(" | ")}`);
}

test("sequence_settings: every setter, createSetSettingsAction transaction and read-back is stamped with an ISO ms time (Project Modified attribution)", async () => {
  const state = { codec: "Animation", format: "QuickTime" };
  const settings = () => {
    const pending = { ...state };
    return {
      pending,
      getPreviewCodec: async () => state.codec,
      getPreviewFileFormat: async () => state.format,
      setPreviewCodec: async (v: string) => {
        pending.codec = v;
        return true;
      },
      setPreviewFileFormat: async () => true,
      getCompositeInLinearColor: async () => true,
      getMaximumBitDepth: async () => false,
      getMaxRenderQuality: async () => false,
      getEditingMode: async () => "Custom",
      getVideoFrameRect: async () => ({ width: 1080, height: 1920 }),
      getPreviewFrameRect: async () => ({ width: 1080, height: 1920 }),
      getVideoPixelAspectRatio: async () => "1:1",
      getVideoFieldType: async () => 0,
      getVideoFrameRate: () => ({ value: 24 }),
      getAudioChannelType: async () => 1,
      getAudioChannelCount: async () => 2,
      setCompositeInLinearColor: async () => true,
      setMaximumBitDepth: async () => true,
      setMaxRenderQuality: async () => true,
      setPreviewFrameRect: async () => true,
    };
  };
  const sequence = { name: "SEQ", getSettings: async () => settings(), createSetSettingsAction: (s: { pending: typeof state }) => ({ apply: () => Object.assign(state, s.pending) }) };
  const project = {
    path: `\\\\?\\${WORK}/spike-1.prproj`,
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: (cb: (ca: { addAction: (a: { apply: () => void }) => boolean }) => void) => {
      cb({ addAction: (a) => (a.apply(), true) });
      return true;
    },
  };
  const ctx = baseCtx({ SequenceSettings: {}, Constants: {}, RectF: function () {} }, { project: project as never, sequence: sequence as never });
  const r = await runProbe(probe("sequence_settings"), ctx);
  assertStamped(callsOf(r), [/read_all/, /setPreviewCodec/, /createSetSettingsAction/, /getSettings/, /setCompositeInLinearColor/, /setMaximumBitDepth/, /setMaxRenderQuality/, /setPreviewFrameRect/]);
  assert.ok(callsOf(r).every((c) => c.ok === true || typeof c.error === "string"));
});

async function stampedExport(works: boolean) {
  const files = new Map<string, number>();
  const fs = {
    lstat: async (p: string) => {
      const k = p.replace(/\\/g, "/").toLowerCase();
      if (files.has(k)) return { size: files.get(k), isDirectory: () => false };
      if (!/\.(png|jpg|tif|bmp)$/.test(k)) return { size: 0, isDirectory: () => true };
      throw new Error("ENOENT");
    },
    mkdir: async () => {},
  };
  const track = { getTrackItems: () => [{ getStartTime: async () => ({ seconds: 0.1667 }) }] };
  const project = {
    path: `\\\\?\\${WORK}/spike-1.prproj`,
    openSequence: async () => true,
    setActiveSequence: async () => true,
    getRootItem: async () => ({ getItems: async () => [] }),
    lockedAccess: (cb: () => void) => cb(),
    executeTransaction: () => true,
  };
  const ppro = {
    TickTime: { createWithSeconds: (seconds: number) => ({ seconds }) },
    Constants: { TrackItemType: { CLIP: 1 } },
    ClipProjectItem: { cast: () => ({ isOffline: async () => false }) },
    Exporter: {
      exportSequenceFrame: async (_s: unknown, _t: unknown, filename: string, filepath: string) => {
        if (works && filepath.endsWith("\\") && !/^[A-Za-z]:/.test(filename)) {
          files.set(`${filepath.replace(/\\/g, "/")}${filename}`.toLowerCase(), 99);
          return true;
        }
        return false;
      },
    },
  };
  const sequence = {
    name: "SEQ",
    getFrameSize: async () => ({ width: 1080, height: 1920 }),
    getEndTime: async () => ({ seconds: 30 }),
    getVideoTrack: async () => track,
    isDoneAnalyzingForVideoEffects: async () => true,
    setPlayerPosition: async () => true,
  };
  const ctx = baseCtx(ppro, { fs, project: project as never, sequence: sequence as never, timing: { shortPollMs: 20, longPollMs: 40 } });
  ctx.uxp = { host: { name: "premierepro" }, storage: { localFileSystem: { getTemporaryFolder: async () => ({ nativePath: "C:\\Users\\LOQ\\AppData\\Local\\Temp\\uxp" }) } } };
  return runProbe(probe("export_frame"), ctx);
}

test("export_frame: the prepare calls and every export attempt (exportSequenceFrame, poll) are stamped with an ISO ms time", async () => {
  const r = await stampedExport(true);
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 500));
  assertStamped(callsOf(r), [/openSequence/, /setActiveSequence/, /isDoneAnalyzingForVideoEffects/, /getFrameSize/, /isOffline/, /exportSequenceFrame/, /poll/]);
  const attempts = (stepNamed(r, "frame 1").info as { attempts: Array<{ at: string }> }).attempts;
  assert.ok(attempts.every((a) => /^\d{4}-\d\d-\d\dT/.test(a.at)), "every attempt record has its own ISO start time");
});

test("export_frame: the playhead-moving attempts stamp setPlayerPosition too", async () => {
  const r = await stampedExport(false);
  assertStamped(callsOf(r), [/setPlayerPosition/, /exportSequenceFrame/]);
});

// ---- review fixes -----------------------------------------------------------------------------------------------------

test("ws_loopback: a malformed engine.json never leaks a token fragment (V8's JSON.parse message quotes the file): only 'invalid JSON (name)' is recorded", async () => {
  const frag = TOKEN.slice(0, 24);
  // broken after the token's start, so the parse error message would quote part of the token
  const fs = memFs({ [ENGINE_JSON]: `{"port": 51234, "token": "${TOKEN}" "pid": 4242}` });
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  assert.equal(r.ok, false);
  const step = stepNamed(r, "engine.json");
  assert.equal(step.ok, false);
  assert.match(step.error ?? "", /invalid JSON \(SyntaxError\)/);
  const json = JSON.stringify(r);
  assert.ok(!json.includes(frag), "no part of the token (24 chars) in the results");
  assert.ok(!json.includes(TOKEN));
  assert.equal(FakeWs.all.length, 0);
});

test("ws_loopback: the Origin instructions say that no origin row means no Origin header", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const r = await withWs(GOOD, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  const how = (r.detail as { how_to_read_origin: string }).how_to_read_origin;
  assert.match(how, /NO origin row/);
  assert.match(how, /no Origin header/);
  assert.match(how, /session/);
});

test("ws_loopback: the close reason of a successful close is redacted too", async () => {
  const fs = memFs({ [ENGINE_JSON]: engineFile() });
  const r = await withWs({ ...GOOD, closeReason: `bye ${TOKEN}` }, () => runProbe(probe("ws_loopback"), baseCtx({}, { fs, timing: FAST })));
  assert.equal(r.ok, true, JSON.stringify(r).slice(0, 500));
  assert.equal((stepNamed(r, "close").info as { close_reason: string }).close_reason, "bye [redacted]");
  assert.ok(!JSON.stringify(r).includes(TOKEN));
});
