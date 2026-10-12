import { test } from "node:test";
import assert from "node:assert/strict";
import { startShell } from "../src/shell.ts";
import type { ShellDoc, ShellEnv } from "../src/shell.ts";
import { OfflineSource } from "../src/offline-source.ts";

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
