// Python <-> TypeScript end to end: the REAL engine daemon (`reel serve`, whynot-cut/engine/reel/serve/__main__.py run
// with the engine runtime's python, exactly like serve.daemon starts it) against the plugin's real TypeScript: the
// panel's DaemonSource (requester) and the host link + host adapter (host) over Node's own WebSocket / fetch, both
// finding the daemon through the discovery copy of engine.json in a temp ~/.whynot-cut. Premiere is the fake
// premierepro of host-adapter.fakes.ts. Covered: hello / welcome on both sessions, snapshot (the host pill from the
// daemon), a CLI-style `command` (a raw kind "cli" requester) for set_player_position routed by the daemon to the host
// adapter and its `result` back, the same through DaemonSource, cancel of a running export, then daemon stop ->
// DaemonSource and the host link back off and reconnect to the next daemon on their own.
// Temp homes only (HOME / USERPROFILE / WHYNOT_HOME / APPDATA point into a temp folder; the engine's test-sandbox flag
// is set); every daemon this file starts is killed in cleanup, also when an assertion fails.
// Skipped (not failed) when no engine runtime is installed: tools/test.sh's lookup (<home>/current -> runtimes/<id>,
// else the 2.x venv).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { delimiter, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { DaemonSource } from "../../panel-ui/src/daemon-source.ts";
import type { PanelState, Result } from "../../panel-ui/src/source.ts";
import { startHostLink } from "../src/host-link.ts";
import type { HostLink } from "../src/host-link.ts";
import { CAPABILITIES } from "../src/ops/index.ts";
import type { OpEnv } from "../src/ops/types.ts";
import { createDaemonTransport, readEngineJson, timerOf } from "../src/uxp-transport.ts";
import type { LinkGlobals, WebSocketCtor } from "../src/uxp-transport.ts";
import { SEQ, WIN_PROJECT, makeEnv } from "./host-adapter.fakes.ts";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const MAIN = join(REPO, "whynot-cut", "engine", "reel", "serve", "__main__.py");
const START_WAIT_MS = 60_000; // a cold daemon start on a loaded machine can take seconds

// ---- the engine runtime (tools/test.sh's lookup) -------------------------------------------------------------------

function enginePython(): { exe: string; flags: string[] } | null {
  const home = process.env["WHYNOT_HOME"] || join(homedir(), ".whynot-cut");
  try {
    const id = readFileSync(join(home, "current"), "utf8").replace(/^\uFEFF/, "").replace(/\s+/g, "");
    if (/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(id) && !id.includes("..") && existsSync(join(home, "runtimes", id, "pyvenv.cfg"))) {
      for (const c of [join(home, "runtimes", id, "Scripts", "python.exe"), join(home, "runtimes", id, "bin", "python")]) {
        if (existsSync(c)) return { exe: c, flags: ["-s"] };
      }
    }
  } catch {
    // no current runtime: the 2.x venv
  }
  for (const c of [join(home, "venv", "Scripts", "python.exe"), join(home, "venv", "bin", "python")]) {
    if (existsSync(c)) return { exe: c, flags: [] };
  }
  return null;
}

// ---- daemons: started like serve.daemon starts them, always killed ----------------------------------------------------

const DROP_ENV = [
  "CLAUDE_PLUGIN_DATA", "CLAUDE_ENV_FILE", "WHYNOT_OPTIONS_FILE", "WHYNOT_PREMIERE_APP", "WHYNOT_AE_APP", "WHYNOT_AERENDER",
  "WHYNOT_HOME", "CLAUDE_PLUGIN_OPTION_ENGINE_HOME", "REEL_HOME", "CLAUDE_PLUGIN_OPTION_REEL_HOME", "NH_ENV_DIR",
  "WHYNOT_CLIENTS_ROOT", "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT", "REEL_CLIENTS_ROOT",
];

interface Homes {
  root: string;
  user: string;
  engine: string;
}

const live = new Set<ChildProcess>();
/** the daemons' own pids (engine.json): on Windows a venv's python.exe is a launcher whose child is the daemon */
const livePids = new Set<number>();
function killPid(pid: number): void {
  try {
    process.kill(pid); // Windows: TerminateProcess
  } catch {
    // already gone
  }
}
function killAll(): void {
  for (const p of live) {
    if (p.exitCode === null && p.signalCode === null) {
      try {
        p.kill();
      } catch {
        // already gone
      }
    }
  }
  for (const pid of livePids) killPid(pid);
  livePids.clear();
}
process.on("exit", killAll);

class Daemon {
  readonly proc: ChildProcess;
  port = 0;
  token = "";
  pid = 0;
  stderr = "";
  private exited: Promise<number | null>;
  constructor(proc: ChildProcess) {
    this.proc = proc;
    live.add(proc);
    this.exited = new Promise((resolve) => proc.once("exit", (code) => resolve(code)));
    proc.stderr?.setEncoding("utf8");
    proc.stderr?.on("data", (d: string) => void (this.stderr = (this.stderr + d).slice(-4000)));
  }

  static async start(py: { exe: string; flags: string[] }, homes: Homes): Promise<Daemon> {
    const env: Record<string, string | undefined> = { ...process.env };
    for (const k of DROP_ENV) delete env[k];
    const real = homedir();
    Object.assign(env, {
      HOME: homes.user,
      USERPROFILE: homes.user,
      APPDATA: join(homes.root, "appdata"),
      CLAUDE_CONFIG_DIR: join(homes.root, "claude"),
      WHYNOT_HOME: homes.engine,
      WHYNOT_TEST_SANDBOX: homes.root,
      WHYNOT_TEST_LIVE_ROOTS: [join(real, ".whynot-cut"), join(real, ".reel-editor"), join(real, ".dr-nahla-editor"), join(process.env["APPDATA"] ?? real, "Adobe", "CEP", "extensions")].join(delimiter),
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
    });
    const proc = spawn(py.exe, [...py.flags, "-B", "-P", MAIN, "--foreground", "--home", homes.engine], {
      cwd: homes.engine,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    const d = new Daemon(proc);
    const line = await new Promise<string>((resolve, reject) => {
      let out = "";
      const timer = setTimeout(() => reject(new Error(`reel serve did not start within ${START_WAIT_MS} ms: ${d.stderr}`)), START_WAIT_MS);
      proc.stdout?.setEncoding("utf8");
      proc.stdout?.on("data", (chunk: string) => {
        out += chunk;
        const first = out.split("\n").find((l) => l.includes('"state": "running"'));
        if (first) {
          clearTimeout(timer);
          resolve(first);
        }
      });
      proc.once("exit", (code) => {
        clearTimeout(timer);
        reject(new Error(`reel serve exited while starting (code ${code}): ${d.stderr}`));
      });
    });
    const ann = JSON.parse(line) as { pid: number; port: number };
    const rec = JSON.parse(readFileSync(join(homes.engine, "bridge", "engine.json"), "utf8")) as { port: number; token: string; pid: number };
    assert.equal(rec.port, ann.port);
    d.port = rec.port;
    d.token = rec.token;
    d.pid = rec.pid;
    if (d.pid !== proc.pid) livePids.add(d.pid);
    return d;
  }

  /** The authenticated POST /shutdown, then wait for the process to exit. */
  async shutdown(): Promise<void> {
    const r = await fetch(`http://127.0.0.1:${this.port}/shutdown`, { method: "POST", headers: { Authorization: `Bearer ${this.token}` } });
    assert.equal(r.status, 202);
    await this.waitExit(15_000);
  }

  async waitExit(ms: number): Promise<number | null> {
    const code = await Promise.race([this.exited, new Promise<"timeout">((r) => setTimeout(() => r("timeout"), ms))]);
    if (code === "timeout") throw new Error(`reel serve (pid ${this.pid}) did not exit within ${ms} ms`);
    live.delete(this.proc);
    livePids.delete(this.pid);
    return code;
  }

  async kill(): Promise<void> {
    if (this.proc.exitCode === null && this.proc.signalCode === null) {
      if (this.pid && this.pid !== this.proc.pid) killPid(this.pid); // the daemon behind a venv launcher
      this.proc.kill();
    }
    await this.waitExit(15_000).catch(() => undefined);
  }
}

// ---- helpers --------------------------------------------------------------------------------------------------------

async function until<T>(what: string, fn: () => T | undefined | null | false, ms = 20_000, every = 25): Promise<T> {
  const end = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out after ${ms} ms waiting for ${what}`);
    await new Promise((r) => setTimeout(r, every));
  }
}

type Msg = Record<string, unknown> & { type: string };

/** A raw requester the way the reel CLI talks to the daemon: hello kind "cli", then `command` messages. */
class CliClient {
  private ws: WebSocket;
  private inbox: Msg[] = [];
  closed: { code: number; reason: string } | null = null;
  constructor(port: number) {
    this.ws = new WebSocket(`ws://127.0.0.1:${port}/session`);
    this.ws.onmessage = (ev) => void this.inbox.push(JSON.parse(String(ev.data)) as Msg);
    this.ws.onclose = (ev) => void (this.closed = { code: ev.code, reason: ev.reason });
  }
  async open(token: string): Promise<Msg> {
    await until("the CLI socket to open", () => this.ws.readyState === WebSocket.OPEN || this.closed, 10_000);
    assert.equal(this.closed, null, `the daemon refused the CLI socket: ${JSON.stringify(this.closed)}`);
    this.ws.send(JSON.stringify({ type: "hello", token, client: { kind: "cli", version: "3.0.0", protocol: 4, capabilities: [] } }));
    return this.next("welcome");
  }
  send(msg: object): void {
    this.ws.send(JSON.stringify(msg));
  }
  async next(type: string, pred: (m: Msg) => boolean = () => true): Promise<Msg> {
    return until(`a ${type} message`, () => {
      const i = this.inbox.findIndex((m) => m.type === type && pred(m));
      return i >= 0 ? this.inbox.splice(i, 1)[0]! : undefined;
    });
  }
  close(): void {
    this.ws.close(1000, "done");
  }
}

// ---- the test ----------------------------------------------------------------------------------------------------------

const py = enginePython();

test("Python <-> TS: reel serve with DaemonSource (requester) and the host adapter (host): route, result, cancel, stop -> reconnect", { skip: py ? false : "no engine runtime (run reel setup)", timeout: 240_000 }, async (t) => {
  const root = mkdtempSync(join(tmpdir(), "wnc-e2e-"));
  const homes: Homes = { root, user: join(root, "user"), engine: join(root, "engine") };
  for (const d of [homes.user, homes.engine, join(root, "appdata"), join(root, "claude")]) mkdirSync(d, { recursive: true });
  const daemons: Daemon[] = [];
  let src: DaemonSource | null = null;
  let link: HostLink | null = null;
  const cli: CliClient[] = [];
  t.after(async () => {
    for (const c of cli) c.close();
    src?.stop();
    link?.stop();
    for (const d of daemons) await d.kill();
    killAll();
    rmSync(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  });

  // ---- daemon A, found through the discovery copy in the temp ~/.whynot-cut
  const a = await Daemon.start(py!, homes);
  daemons.push(a);
  const discoveryPath = join(homes.user, ".whynot-cut", "bridge", "engine.json");
  const disc = JSON.parse(readFileSync(discoveryPath, "utf8")) as { port: number; token: string; home?: string };
  assert.equal(disc.port, a.port);
  assert.equal(disc.home, homes.engine, "the discovery copy names the engine home it points at");

  // the plugin's runtime, made of Node's own globals (UXP has the same shapes)
  const linkLog: string[] = [];
  const globals: LinkGlobals = {
    fs: { readFile: (p: string) => readFile(p, "utf8") },
    os: { homedir: () => homes.user },
    WebSocket: globalThis.WebSocket as unknown as WebSocketCtor,
    fetch: (url, init) => fetch(url, init),
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    now: () => Date.now(),
    log: (line) => void linkLog.push(line),
  };

  // ---- the host side: the fake Premiere behind the real host adapter
  const fake = makeEnv();
  fake.pp.addOpen(WIN_PROJECT, [{ name: "Other" }, { name: SEQ }]);
  const opEnv: OpEnv = {
    ...fake.env,
    sleep: (ms) => new Promise<void>((r) => setTimeout(r, ms)),
    now: () => Date.now(),
    timing: { pollMs: 50, appearMs: 30_000, settleMs: 30_000 },
  };
  const hostLog: string[] = [];
  link = startHostLink({
    readEngineJson: () => readEngineJson(globals.fs, globals.os),
    openSocket: (url) => new (globals.WebSocket!)(url),
    env: opEnv,
    setTimer: timerOf(globals),
    log: (_l, text) => void hostLog.push(text),
  });
  await until("the host link to connect", () => link!.state === "connected");

  // ---- the panel side: DaemonSource
  const transport = createDaemonTransport(globals);
  assert.ok(transport, "Node has WebSocket, fs and a home: the live transport");
  src = new DaemonSource({ transport, version: "3.0.0", language: "en", localHost: { state: "uxp", detail: "Premiere Pro 26.5.2" } });
  const diags: Array<{ code: string; retry_in_s?: number; at: number }> = [];
  let state: PanelState | null = null;
  src.subscribe((s) => {
    state = s;
    const d = src!.diagnosis;
    const last = diags[diags.length - 1];
    if (!last || last.code !== d.code || last.retry_in_s !== d.retry_in_s) diags.push({ code: d.code, ...(d.retry_in_s !== undefined ? { retry_in_s: d.retry_in_s } : {}), at: Date.now() });
  });
  await until("DaemonSource to connect", () => src!.diagnosis.code === "connected");

  await t.test("hello / welcome on both sessions; /status lists the uxp host with its capabilities and the panel", async () => {
    const r = await fetch(`http://127.0.0.1:${a.port}/status`, { headers: { Authorization: `Bearer ${a.token}` } });
    assert.equal(r.status, 200);
    const st = (await r.json()) as { protocol: number; sessions: Array<{ kind: string; host: string | null; hostVersion: string | null; capabilities: string[] }> };
    assert.equal(st.protocol, 4);
    const uxp = st.sessions.find((s) => s.kind === "uxp");
    assert.ok(uxp, JSON.stringify(st.sessions));
    assert.equal(uxp.host, "premiere");
    assert.equal(uxp.hostVersion, "26.5.2");
    assert.deepEqual(uxp.capabilities, [...CAPABILITIES]);
    assert.ok(st.sessions.some((s) => s.kind === "panel"), "DaemonSource is a panel session");
    assert.ok(link!.adapter?.sessionId, "the adapter has the daemon's session id");
  });

  await t.test("snapshot: the daemon's state says a UXP Premiere is connected; the panel merges it (engine connected)", async () => {
    const s = await until("a state from the daemon", () => (state && (state as PanelState).connection.engine === "connected" ? (state as PanelState) : null));
    assert.deepEqual(s.connection.host, { state: "uxp", detail: "Premiere Pro 26.5.2" });
    assert.equal(s.connection.engine, "connected");
  });

  await t.test("a CLI-style command for set_player_position is routed by the daemon to the host adapter; its result comes back", async () => {
    const c = new CliClient(a.port);
    cli.push(c);
    const welcome = await c.open(a.token);
    assert.equal(welcome["protocol"], 4);
    const id = "cli-spp-0001";
    c.send({ type: "command", request: { protocol: 4, id, action: "set_player_position", data: { sequence_name: SEQ, t_s: 12.5 }, expires_at: new Date(Date.now() + 60_000).toISOString() } });
    const res = (await c.next("result")).result as Record<string, unknown>;
    assert.deepEqual(res, { ok: true, action: "set_player_position", id, readback: { position_s: 12.5 } });
    assert.ok(fake.pp.calls.includes(`setPlayerPosition ${SEQ} 12.5`), fake.pp.calls.join(" | "));
    assert.ok(fake.pp.calls.includes(`setActiveSequence ${SEQ}`), "the named sequence was made active first");
    // a command whose data breaks the contract is refused by the daemon (schema) and never reaches Premiere
    const calls = fake.pp.calls.length;
    c.send({ type: "command", request: { protocol: 4, id: "cli-spp-0002", action: "set_player_position", data: { t_s: 1 }, expires_at: new Date(Date.now() + 60_000).toISOString() } });
    const refused = await c.next("error", (m) => m["id"] === "cli-spp-0002");
    assert.equal(refused["code"], "schema");
    assert.equal(fake.pp.calls.length, calls);
  });

  await t.test("the same through DaemonSource.run: set_player_position and ping answer with the adapter's readbacks", async () => {
    const r1: Result = await src!.run("set_player_position", { sequence_name: SEQ, t_s: 3 });
    assert.deepEqual(r1, { ok: true, action: "set_player_position", readback: { position_s: 3 } });
    const r2 = await src!.run("ping", {});
    assert.equal(r2.ok, true, JSON.stringify(r2));
    assert.deepEqual(r2.readback, { version: "26.5.2", project: WIN_PROJECT, projects_open: 1 });
  });

  await t.test("cancel: a running export_frames is cancelled through the daemon; its own result fails the frames step", async () => {
    fake.pp.exportWritesNothing = true; // Premiere says true and writes nothing: the op waits for the PNG
    const out = "D:\\wnc-e2e\\08_quality_control\\premiere_frames\\run-1";
    const running = src!.run("export_frames", { sequence_name: SEQ, times: [1.5], out_dir: out });
    const step = await until("the export's progress", () => {
      const f = (state as PanelState | null)?.pipeline.find((p) => p.id === "frames");
      return f && f.state === "running" && f.request_id && f.progress ? f : null;
    });
    assert.deepEqual(link!.adapter?.running(), [step.request_id]);
    await src!.cancel(step.request_id!);
    const r = await running;
    assert.equal(r.ok, false);
    assert.equal(r.error, "Cancelled before it finished.");
    const f = (state as PanelState | null)?.pipeline.find((p) => p.id === "frames");
    assert.equal(f?.state, "failed");
    assert.deepEqual(link!.adapter?.running(), []);
    fake.pp.exportWritesNothing = false;
  });

  await t.test("daemon stop -> both sessions back off (1 s, 2 s, ...) and reconnect to the next daemon by themselves", async () => {
    const before = diags.length;
    await a.shutdown();
    assert.ok(!existsSync(discoveryPath), "the discovery copy is removed with its daemon");
    await until("DaemonSource to notice", () => src!.diagnosis.code !== "connected");
    await until("the host link to notice", () => link!.state !== "connected");
    // wait until the panel has backed off at least twice (lost, then no engine.json)
    await until("two failed attempts", () => diags.slice(before).filter((d) => d.retry_in_s !== undefined).length >= 2, 20_000);
    const offline = await src!.snapshot();
    assert.equal(offline.connection.engine, "offline");
    assert.deepEqual(offline.connection.host, { state: "uxp", detail: "Premiere Pro 26.5.2" }, "offline, the host pill is the panel's own host");
    const r = await src!.run("ping", {});
    assert.equal(r.ok, false, "offline: answered at once, nothing sent");

    const b = await Daemon.start(py!, homes);
    daemons.push(b);
    await until("DaemonSource to reconnect", () => src!.diagnosis.code === "connected", 30_000);
    await until("the host link to reconnect", () => link!.state === "connected", 30_000);
    const after = diags.slice(before);
    const codes = after.map((d) => d.code);
    assert.ok(codes.includes("lost"), codes.join(", "));
    assert.ok(codes.includes("no_engine") || codes.includes("down"), codes.join(", "));
    const waits = after.filter((d) => d.retry_in_s !== undefined).map((d) => d.retry_in_s);
    assert.deepEqual(waits.slice(0, 2), [1, 2], `the backoff grows: ${JSON.stringify(after)}`);
    assert.equal(codes[codes.length - 1], "connected");
    // the reconnected pair works end to end on the new daemon
    const again = await src!.run("set_player_position", { sequence_name: SEQ, t_s: 7 });
    assert.deepEqual(again, { ok: true, action: "set_player_position", readback: { position_s: 7 } });
    assert.ok(hostLog.some((l) => /trying again in 1 s/.test(l)), hostLog.join(" | "));
    for (const text of [...linkLog, ...hostLog, JSON.stringify(diags)]) {
      assert.ok(!text.includes(a.token) && !text.includes(b.token), "no token in any log line");
    }
  });

  // ---- shut down cleanly: the panel, the host link, the daemon; nothing left running
  src.stop();
  link.stop();
  await daemons[daemons.length - 1]!.shutdown();
  for (const d of daemons) assert.notEqual(d.proc.exitCode, null, `daemon pid ${d.pid} still running`);
});
