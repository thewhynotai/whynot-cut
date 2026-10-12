import { test } from "node:test";
import assert from "node:assert/strict";
import { startShell } from "../src/shell.ts";
import type { ShellDoc, ShellEnv } from "../src/shell.ts";
import { OfflineSource } from "../src/offline-source.ts";
import { DaemonSource } from "../../panel-ui/src/daemon-source.ts";
import type { DaemonTransport } from "../../panel-ui/src/daemon-source.ts";

class FakeRoot {
  innerHTML = "";
  listeners: Record<string, (e: unknown) => void> = {};
  addEventListener(type: string, fn: (e: unknown) => void): void {
    this.listeners[type] = fn;
  }
  removeEventListener(type: string): void {
    delete this.listeners[type];
  }
  setAttribute(): void {}
  appendChild(): void {}
  className = "";
  textContent: string | null = "";
  remove(): void {}
  addListener(): void {}
}

function makeEnv(over: { uxp?: unknown; root?: FakeRoot | null; requireThrows?: boolean; mock?: boolean } = {}) {
  const root = over.root === undefined ? new FakeRoot() : over.root;
  const vars: Record<string, string> = {};
  const body = new FakeRoot();
  const doc = {
    body,
    documentElement: { style: { setProperty: (k: string, v: string) => void (vars[k] = v) } },
    getElementById: (id: string) => (id === "root" ? root : null),
    createElement: () => new FakeRoot(),
  } as unknown as ShellDoc;
  const uxp = "uxp" in over ? over.uxp : { host: { version: "26.5.2", uiLocale: "en_US", getBackgroundColor: () => ({}) } };
  const env: ShellEnv = {
    document: doc,
    navigator: undefined,
    require: (id: string) => {
      if (over.requireThrows) throw new Error(`no ${id}`);
      if (id === "uxp") return uxp;
      throw new Error(`unexpected require(${id})`);
    },
    createSource: (info) => new OfflineSource(info),
  };
  return { env, root, vars, body };
}

test("startShell mounts the panel into #root with the offline source: Engine not running, real Premiere version", async () => {
  const { env, root } = makeEnv();
  const shell = startShell(env);
  await shell.ready;
  assert.match(root!.innerHTML, /not running/);
  assert.match(root!.innerHTML, /Premiere Pro 26\.5\.2/);
  assert.match(root!.innerHTML, /Powered by thewhynot.ai/);
  assert.doesNotMatch(root!.innerHTML, /Claude Code/);
  assert.equal(typeof root!.listeners["click"], "function", "buttons are wired by event delegation on the root");
  shell.unmount();
  assert.equal(root!.listeners["click"], undefined);
});

test("startShell hands the host's version and UI locale to the source factory", async () => {
  const seen: unknown[] = [];
  const { env, root } = makeEnv({ uxp: { host: { version: "26.5.9", uiLocale: "ar_AE" } } });
  env.createSource = (info) => (seen.push(info), new OfflineSource(info));
  await startShell(env).ready;
  assert.deepEqual(seen, [{ hostVersion: "26.5.9", uiLocale: "ar_AE" }]);
  assert.match(root!.innerHTML, /dir="rtl"/);
});

test("startShell applies the host background to --twn-bg only when it is a usable dark colour", async () => {
  const a = makeEnv({ uxp: { host: { version: "1", getBackgroundColor: () => "#2b2b2b" } } });
  await startShell(a.env).ready;
  assert.equal(a.vars["--twn-bg"], "#2b2b2b");
  const b = makeEnv(); // returns {}
  await startShell(b.env).ready;
  assert.deepEqual(b.vars, {});
});

test("startShell copes with require('uxp') missing: still mounts, host version unknown", async () => {
  const { env, root } = makeEnv({ requireThrows: true });
  await startShell(env).ready;
  assert.match(root!.innerHTML, /not running/);
  assert.match(root!.innerHTML, /Premiere Pro/);
});

test("startShell with no #root says so on the page instead of throwing", () => {
  const { env, body } = makeEnv({ root: null });
  const shell = startShell(env);
  assert.match(body.textContent ?? "", /#root/);
  return shell.ready;
});

test("a QC tile click reaches the UXP host adapter, and a refused move shows as a notice (not a blank panel)", async () => {
  const root = new FakeRoot();
  const { env } = makeEnv({ root });
  // a source with one QC frame so a tile exists
  env.createSource = (info) => {
    const src = new OfflineSource(info);
    const snap = src.snapshot.bind(src);
    src.snapshot = async () => ({
      ...(await snap()),
      client: "PODCAST-TEST",
      item: "EP01_R03",
      qc: [{ t_s: 3.2, tc: "00:00:03:05", file: "f.png", label: "Statement bar", verdict: "pass" as const }],
    });
    return src;
  };
  const shell = startShell(env);
  await shell.ready;
  const click = root.listeners["click"]!;
  const target = {
    closest: (sel: string) => (sel === "[data-action]" ? { getAttribute: (n: string) => ({ "data-action": "seek", "data-t": "3.2" })[n] ?? null } : null),
    getAttribute: () => null,
  };
  click({ target });
  await new Promise((r) => setTimeout(r, 20));
  // require("premierepro") is not available in the test env: the failure is a notice in the panel
  assert.match(root.innerHTML, /banner-error/);
  assert.match(root.innerHTML, /unexpected require\(premierepro\)/);
});

// ------------------------------------------------------------------------------------ Task 4: the engine link wiring

/** A DaemonSource over a transport with no engine.json: short waits run at once, the backoff timers are only recorded. */
function noEngineSource(info: { hostVersion?: string | undefined }) {
  const held: Array<{ ms: number; live: boolean }> = [];
  const transport: DaemonTransport = {
    readEngineJson: () => null,
    openSocket: () => {
      throw new Error("not reached");
    },
    now: () => Date.parse("2026-10-12T10:00:00Z"),
    setTimer: (fn, ms) => {
      if (ms <= 100) {
        const h = setImmediate(fn);
        return () => clearImmediate(h);
      }
      const x = { ms, live: true };
      held.push(x);
      return () => void (x.live = false);
    },
  };
  const src = new DaemonSource({ transport, localHost: { state: "uxp", detail: `Premiere Pro ${info.hostVersion ?? ""}`.trim() } });
  return { src, held };
}

const settleShell = async () => {
  for (let i = 0; i < 20; i++) await new Promise<void>((r) => setImmediate(r));
};

test("with a DaemonSource the offline banner names the diagnosis (no engine.json -> one sentence + Start engine, no command) and the host pill stays Premiere", async () => {
  const { env, root } = makeEnv();
  const made: ReturnType<typeof noEngineSource>[] = [];
  env.createSource = (info) => {
    const m = noEngineSource(info);
    made.push(m);
    return m.src;
  };
  const shell = startShell(env);
  await shell.ready;
  await settleShell();
  assert.equal(made[0]!.src.diagnosis.code, "no_engine");
  assert.match(root!.innerHTML, /data-link="no_engine"/);
  assert.match(root!.innerHTML, /data-action="start-engine"/);
  assert.doesNotMatch(root!.innerHTML.replace(/<section class="sec sec-log">[\s\S]*?<\/section>/, ""), /reel /, "no command outside the log drawer");
  assert.match(root!.innerHTML, /tries again by itself/);
  assert.match(root!.innerHTML, /Premiere Pro 26\.5\.2/);
  shell.unmount();
  assert.equal(made[0]!.src.diagnosis.code, "stopped");
  assert.ok(made[0]!.held.every((x) => !x.live), "no retry timer survives unmount");
});

test("I1: hide and show keep both sessions (a hidden panel's commands are not cancelled; Premiere may fire show once); only destroy stops them", async () => {
  const { env, root } = makeEnv();
  const made: ReturnType<typeof noEngineSource>[] = [];
  env.createSource = (info) => {
    const m = noEngineSource(info);
    made.push(m);
    return m.src;
  };
  const hostLinks: Array<{ stopped: boolean }> = [];
  env.startHostLink = () => {
    const h = { stopped: false };
    hostLinks.push(h);
    return { stop: () => void (h.stopped = true) };
  };
  const reg: { lifecycle: { show(): void; hide(): void; destroy(): void } | null } = { lifecycle: null };
  env.onLifecycle = (h) => void (reg.lifecycle = h);
  const shell = startShell(env);
  await shell.ready;
  await settleShell();
  assert.ok(reg.lifecycle, "show / hide / destroy were registered with the host");
  assert.equal(hostLinks.length, 1);
  reg.lifecycle!.hide();
  reg.lifecycle!.hide();
  await settleShell();
  assert.equal(made[0]!.src.diagnosis.code, "no_engine", "hiding does not stop the panel's session");
  assert.equal(typeof root!.listeners["click"], "function", "still mounted");
  assert.equal(hostLinks[0]!.stopped, false);
  reg.lifecycle!.show();
  reg.lifecycle!.show();
  assert.equal(made.length, 1, "show mounts nothing new: the one session lives on");
  assert.match(root!.innerHTML, /data-link="no_engine"/);
  reg.lifecycle!.destroy();
  assert.equal(made[0]!.src.diagnosis.code, "stopped");
  assert.equal(root!.listeners["click"], undefined);
  assert.equal(hostLinks[0]!.stopped, true);
  reg.lifecycle!.show(); // after destroy: nothing comes back
  assert.equal(made.length, 1);
  assert.equal(hostLinks.length, 1);
});

test("M8: the shell hands the plugin version and build stamp to the panel: Copy diagnostics carries them, the log drawer shows them", async () => {
  const { env, root } = makeEnv();
  const copied: string[] = [];
  env.navigator = { clipboard: { writeText: async (t: string) => void copied.push(t) } };
  env.build = { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" };
  const shell = startShell(env);
  await shell.ready;
  const click = (action: string) =>
    root!.listeners["click"]!({ target: { closest: (sel: string) => (sel === "[data-action]" ? { getAttribute: (n: string) => (n === "data-action" ? action : null) } : null), getAttribute: () => null } });
  click("copy-diagnostics");
  await settleShell();
  assert.deepEqual((JSON.parse(copied[0]!) as Record<string, unknown>)["plugin"], { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" });
  click("toggle-log");
  assert.match(root!.innerHTML, /WhyNot Cut 3\.0\.0 · build 61b12aa 2026-10-12T18:40Z/);
  shell.unmount();
});

test("a failing host link start never blanks the panel", async () => {
  const { env, root } = makeEnv();
  env.startHostLink = () => {
    throw new Error("no WebSocket here");
  };
  const shell = startShell(env);
  await shell.ready;
  assert.match(root!.innerHTML, /not running/);
  shell.unmount();
});
