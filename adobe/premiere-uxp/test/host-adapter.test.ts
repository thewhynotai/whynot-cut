// The UXP host adapter's session behaviour: hello with the capabilities, command -> op -> result validated against the
// action's readback, cancel, progress, expiry, one Premiere op at a time, and a dropped socket. Every message the adapter
// sends is checked against session.schema.json (what the daemon validates on receipt) and every result against
// result.schema.json + the action's $defs/readback (what the router checks).
import { test } from "node:test";
import assert from "node:assert/strict";
import { startHostAdapter } from "../src/host-adapter.ts";
import type { HostAdapterOptions } from "../src/host-adapter.ts";
import { CAPABILITIES } from "../src/ops/index.ts";
import { OpError } from "../src/ops/types.ts";
import type { Op } from "../src/ops/types.ts";
import { FakeSocket, SEQ, WIN_PROJECT, makeEnv, request, resultErrors, sessionErrors, settle } from "./host-adapter.fakes.ts";

const TOKEN = "a".repeat(64);
type Result = { ok: boolean; action: string; id?: string; readback?: Record<string, unknown>; error?: string; how?: string };

function start(over: Partial<HostAdapterOptions> = {}) {
  const sock = new FakeSocket();
  const e = makeEnv();
  e.pp.addOpen(WIN_PROJECT, [{ name: SEQ, video: [[]] }]);
  const adapter = startHostAdapter({ socket: sock, token: TOKEN, env: e.env, ...over });
  const results = () => sock.of<{ result: Result }>("result").map((m) => m.result);
  const resultFor = async (id: string) => {
    await settle(() => results().some((r) => r.id === id));
    const r = results().find((x) => x.id === id);
    assert.ok(r, `no result for ${id}; sent: ${JSON.stringify(sock.sent)}`);
    return r;
  };
  return { sock, adapter, ...e, results, resultFor };
}

/** every message the adapter sent is a valid session message, and every result passes the router's check */
function assertAllValid(sock: FakeSocket) {
  for (const m of sock.sent) {
    assert.deepEqual(sessionErrors(m), [], JSON.stringify(m));
    const r = (m as { type: string; result?: Result }).result;
    if (r) assert.deepEqual(resultErrors(r), [], JSON.stringify(r));
  }
}

test("the first message is a hello: kind uxp, host premiere, protocol 4, the token and exactly the capabilities", () => {
  const { sock, adapter } = start();
  assert.equal(sock.sent.length, 1);
  assert.deepEqual(sock.sent[0], {
    type: "hello",
    token: TOKEN,
    client: { kind: "uxp", version: "3.0.0", host: "premiere", hostVersion: "26.5.2", protocol: 4, capabilities: [...CAPABILITIES] },
  });
  assert.deepEqual(CAPABILITIES, ["ping", "status", "open_project", "set_player_position", "export_frames", "close_project_path", "clip_components"]);
  assert.deepEqual(adapter.capabilities, CAPABILITIES);
  assertAllValid(sock);
});

test("welcome is remembered (session id); a daemon error message is handed to onError, never answered", () => {
  const errors: unknown[] = [];
  const { sock, adapter } = start({ onError: (e) => void errors.push(e) });
  assert.equal(adapter.sessionId, null);
  sock.deliver({ type: "welcome", session_id: "s-0123456789abcdef", protocol: 4, daemon_version: "3.0.0" });
  assert.equal(adapter.sessionId, "s-0123456789abcdef");
  sock.deliver({ type: "error", code: "schema", message: "bad" });
  assert.equal(errors.length, 1);
  assert.equal(sock.sent.length, 1, "nothing answers a daemon error");
});

test("ping: a valid result with the request id, the version from uxp.host.version and the path without \\\\?\\", async () => {
  const { sock, resultFor } = start();
  sock.deliver(request("ping", {}, "p-1"));
  const r = await resultFor("p-1");
  assert.equal(r.ok, true);
  assert.equal(r.action, "ping");
  assert.deepEqual(r.readback, { version: "26.5.2", project: WIN_PROJECT, projects_open: 1 });
  assertAllValid(sock);
});

test("an op's input is checked against $defs/data before Premiere is touched", async () => {
  const { sock, resultFor, pp } = start();
  sock.deliver(request("set_player_position", { sequence_name: SEQ, t_s: -2 }, "bad-1"));
  const r = await resultFor("bad-1");
  assert.equal(r.ok, false);
  assert.match(r.error ?? "", /not valid/i);
  assert.match(r.error ?? "", /t_s/);
  assert.deepEqual(pp.calls, [], "Premiere was not called");
  assertAllValid(sock);
});

test("a readback that fails the action's $defs/readback becomes ok:false \"adapter produced an invalid readback\"", async () => {
  const bogus: Op = { action: "ping", exclusive: false, run: async () => ({ version: 26 }) };
  const { sock, resultFor } = start({ ops: { ping: bogus } });
  sock.deliver(request("ping", {}, "rb-1"));
  const r = await resultFor("rb-1");
  assert.equal(r.ok, false);
  assert.equal(r.error, "adapter produced an invalid readback");
  assert.match(r.how ?? "", /version/);
  assert.equal(r.readback, undefined, "the invalid readback is not sent");
  assertAllValid(sock);
});

test("an OpError keeps its sentence and how; any other throw becomes one plain sentence", async () => {
  const ops: Record<string, Op> = {
    ping: { action: "ping", exclusive: false, run: async () => { throw new OpError("Premiere said no.", "Try again."); } },
    status: { action: "status", exclusive: false, run: async () => { throw new TypeError("x is undefined"); } },
  };
  const { sock, resultFor } = start({ ops });
  sock.deliver(request("ping", {}, "e-1"));
  sock.deliver(request("status", {}, "e-2"));
  const a = await resultFor("e-1");
  assert.deepEqual([a.ok, a.error, a.how], [false, "Premiere said no.", "Try again."]);
  const b = await resultFor("e-2");
  assert.equal(b.ok, false);
  assert.match(b.error ?? "", /status/);
  assert.match(b.error ?? "", /x is undefined/);
  assertAllValid(sock);
});

test("an action this panel does not implement is refused with ok:false (never silence)", async () => {
  const { sock, resultFor } = start();
  sock.deliver(request("build_project", {}, "nb-1"));
  const r = await resultFor("nb-1");
  assert.equal(r.ok, false);
  assert.equal(r.action, "build_project");
  assert.match(r.error ?? "", /does not run build_project/);
  assertAllValid(sock);
});

test("an expired request is refused without running", async () => {
  const { sock, resultFor, pp } = start();
  sock.deliver(request("ping", {}, "old-1", -5));
  const r = await resultFor("old-1");
  assert.equal(r.ok, false);
  assert.match(r.error ?? "", /expired/i);
  assert.deepEqual(pp.calls, []);
});

test("garbage, a command without an id and messages meant for panels are ignored; a duplicate running id is not answered twice", async () => {
  let release!: () => void;
  const slow: Op = { action: "ping", exclusive: false, run: () => new Promise((r) => (release = () => r({ version: "1", project: "", projects_open: 0 }))) };
  const { sock, results } = start({ ops: { ping: slow } });
  sock.deliver("not json");
  sock.deliver({ type: "command", request: { protocol: 4, action: "ping", data: {} } });
  sock.deliver({ type: "state", state: {} });
  sock.deliver({ type: "reply", id: "x", intent: "approve", ok: true });
  sock.deliver(request("ping", {}, "dup-1"));
  sock.deliver(request("ping", {}, "dup-1"));
  await settle(() => typeof release === "function");
  release();
  await settle(() => results().length > 0);
  await settle();
  assert.equal(results().filter((r) => r.id === "dup-1").length, 1);
  assert.equal(sock.sent.length, 2, "hello + one result");
});

test("Premiere ops run one at a time (exclusive), while ping and status answer at once; status reports busy", async () => {
  const order: string[] = [];
  let release!: () => void;
  const ops: Record<string, Op> = {
    open_project: {
      action: "open_project",
      exclusive: true,
      run: () => new Promise((r) => { order.push("open start"); release = () => { order.push("open end"); r({ opened: true, project: WIN_PROJECT }); }; }),
    },
    close_project_path: { action: "close_project_path", exclusive: true, run: async () => (order.push("close"), { closed: false, reason: "not open" }) },
  };
  const { sock, resultFor, results, adapter } = start({ ops });
  sock.deliver(request("open_project", { path: WIN_PROJECT }, "x-1"));
  sock.deliver(request("close_project_path", { path: WIN_PROJECT }, "x-2"));
  await settle(() => order.length > 0);
  sock.deliver(request("status", {}, "st-1"));
  const st = await resultFor("st-1");
  assert.equal(st.readback?.busy, true);
  assert.deepEqual(adapter.running().sort(), ["x-1", "x-2"]);
  assert.deepEqual(order, ["open start"], "the second Premiere op waits");
  release();
  await resultFor("x-2");
  assert.deepEqual(order, ["open start", "open end", "close"]);
  assert.deepEqual(results().map((r) => r.id), ["st-1", "x-1", "x-2"]);
  sock.deliver(request("status", {}, "st-2"));
  assert.equal((await resultFor("st-2")).readback?.busy, false);
  assertAllValid(sock);
});

test("cancel: a queued op is dropped and a running op stops; each answers its own id with ok:false", async () => {
  let started = false;
  const ops: Record<string, Op> = {
    open_project: {
      action: "open_project",
      exclusive: true,
      run: async (_d, ctx) => {
        started = true;
        while (!ctx.cancelled()) await ctx.env.sleep(10);
        ctx.throwIfCancelled();
        return { opened: true, project: null };
      },
    },
    close_project_path: { action: "close_project_path", exclusive: true, run: async () => ({ closed: true }) },
  };
  const { sock, resultFor } = start({ ops });
  sock.deliver(request("open_project", { path: WIN_PROJECT }, "c-1"));
  sock.deliver(request("close_project_path", { path: WIN_PROJECT }, "c-2"));
  await settle(() => started);
  sock.deliver({ type: "cancel", id: "c-2" });
  const queued = await resultFor("c-2");
  assert.equal(queued.ok, false);
  assert.match(queued.error ?? "", /cancel/i);
  sock.deliver({ type: "cancel", id: "c-1" });
  const running = await resultFor("c-1");
  assert.equal(running.ok, false);
  assert.match(running.error ?? "", /cancel/i);
  sock.deliver({ type: "cancel", id: "nobody" });
  await settle();
  assertAllValid(sock);
});

test("progress: an op's steps go out as valid progress messages with the request id and action", async () => {
  const op: Op = {
    action: "open_project",
    exclusive: true,
    run: async (_d, ctx) => {
      ctx.progress("Opening the project", 0, 1);
      ctx.progress("Opened", 1, 1);
      return { opened: true, project: WIN_PROJECT };
    },
  };
  const { sock, resultFor } = start({ ops: { open_project: op } });
  sock.deliver(request("open_project", { path: WIN_PROJECT }, "pg-1"));
  await resultFor("pg-1");
  const prog = sock.of<{ progress: Record<string, unknown> }>("progress").map((m) => m.progress);
  assert.equal(prog.length, 2);
  assert.deepEqual(prog[0], { event: "progress", id: "pg-1", action: "open_project", step: "Opening the project", n: 0, of: 1, elapsed_s: 0 });
  assertAllValid(sock);
});

test("a dropped socket cancels the running op and nothing more is sent; stop() closes the socket", async () => {
  let ctxSeen: { cancelled(): boolean } | undefined;
  const op: Op = {
    action: "open_project",
    exclusive: true,
    run: async (_d, ctx) => {
      ctxSeen = ctx;
      while (!ctx.cancelled()) await ctx.env.sleep(10);
      ctx.throwIfCancelled();
      return { opened: true, project: null };
    },
  };
  const closed: string[] = [];
  const { sock, adapter } = start({ ops: { open_project: op }, onClose: () => void closed.push("closed") });
  sock.deliver(request("open_project", { path: WIN_PROJECT }, "d-1"));
  await settle(() => ctxSeen !== undefined);
  sock.sendThrows = true;
  sock.drop();
  await settle();
  assert.equal(ctxSeen?.cancelled(), true);
  assert.deepEqual(closed, ["closed"]);
  assert.equal(sock.of("result").length, 0);
  assert.deepEqual(adapter.running(), []);

  const s2 = start();
  s2.adapter.stop();
  assert.deepEqual(s2.sock.closed, { code: 1000, reason: "WhyNot Cut panel closed" });
  s2.sock.deliver(request("ping", {}, "after-stop"));
  await settle();
  assert.equal(s2.sock.of("result").length, 0, "a stopped adapter answers nothing");
});

test("a socket whose send throws never crashes the adapter", async () => {
  const { sock, adapter } = start();
  sock.sendThrows = true;
  sock.deliver(request("ping", {}, "t-1"));
  await settle();
  assert.deepEqual(adapter.running(), []);
});
