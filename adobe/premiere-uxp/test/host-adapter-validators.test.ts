// The compiled contract checks the host adapter ships (src/ops/validators.gen.js, ajv standalone): they are current with
// the contract, have no runtime import, never compile code at runtime, and agree with ajv on every golden fixture.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { validateData, validateReadback } from "../src/ops/validate.ts";
import { CAPABILITIES } from "../src/ops/index.ts";
import { schemaFn } from "./host-adapter.fakes.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURES = join(root, "..", "..", "whynot-cut", "tests", "fixtures", "contract");

test("the generated validators are up to date with the contract (scripts/gen-validators.mjs --check)", () => {
  const r = spawnSync(process.execPath, [join(root, "scripts", "gen-validators.mjs"), "--check"], { cwd: root, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr || r.stdout);
});

test("the generated file needs nothing at runtime: no require/import, no eval or new Function (UXP forbids code from strings)", () => {
  const js = readFileSync(join(root, "src", "ops", "validators.gen.js"), "utf8");
  assert.doesNotMatch(js, /\brequire\(|^\s*import\s/m);
  assert.doesNotMatch(js, /\bnew Function\b|\beval\(/);
});

test("the generator compiles exactly the capabilities (data and readback for each)", () => {
  const src = readFileSync(join(root, "scripts", "gen-validators.mjs"), "utf8");
  const ops = JSON.parse(/export const OPS = (\[[^\]]*\])/.exec(src)?.[1] ?? "[]") as string[];
  assert.deepEqual([...ops].sort(), [...CAPABILITIES].sort());
  const dts = readFileSync(join(root, "src", "ops", "validators.gen.d.ts"), "utf8");
  for (const op of CAPABILITIES) {
    assert.match(dts, new RegExp(`export declare const ${op}_data:`));
    assert.match(dts, new RegExp(`export declare const ${op}_readback:`));
  }
});

test("compiled checks agree with ajv on every golden fixture of the seven actions (data and readback)", () => {
  let n = 0;
  for (const action of CAPABILITIES) {
    const dir = join(FIXTURES, action);
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir)) {
      if (f.includes("cep-")) continue;
      const doc = JSON.parse(readFileSync(join(dir, f), "utf8")) as { data?: unknown; ok?: boolean; readback?: unknown };
      if (f.endsWith("request.json")) {
        assert.equal(validateData(action, doc.data), null, `${action}/${f}`);
        assert.ok(schemaFn(action, "data")(doc.data));
        n++;
      } else if (f.endsWith("result.json") && doc.ok === true) {
        assert.equal(validateReadback(action, doc.readback), null, `${action}/${f}`);
        n++;
      }
    }
  }
  assert.ok(n >= 14, `expected the fixtures, checked ${n}`);
});

test("compiled checks reject what ajv rejects, with a short path + reason", () => {
  const bad: Array<[string, unknown]> = [
    ["ping", { extra: 1 }],
    ["open_project", {}],
    ["open_project", { path: "" }],
    ["set_player_position", { sequence_name: "S", t_s: -1 }],
    ["set_player_position", { sequence_name: "S", t_s: "1" }],
    ["export_frames", { sequence_name: "S", times: [], out_dir: "D:\\x" }],
    ["export_frames", { sequence_name: "S", times: [-0.5], out_dir: "D:\\x" }],
    ["close_project_path", { path: 3 }],
    ["clip_components", { sequence_name: "S", track: 1.5 }],
    ["clip_components", { sequence_name: "S", audio: "yes" }],
    ["status", null],
  ];
  for (const [action, data] of bad) {
    assert.equal(schemaFn(action, "data")(data), false, `ajv accepts ${action} ${JSON.stringify(data)}`);
    const why = validateData(action, data);
    assert.ok(typeof why === "string" && why.length > 0 && why.length < 200, `${action} ${JSON.stringify(data)}: ${why}`);
  }
  assert.match(validateData("open_project", {}) ?? "", /path/);
  assert.match(validateData("ping", { extra: 1 }) ?? "", /extra/);
  const badReadbacks: Array<[string, unknown]> = [
    ["export_frames", { frames: [{ t: 1, file: "x.png" }] }],
    ["export_frames", { frames: [{ t: 1, file: "x.png", called: true, tc: 5 }] }],
    ["ping", { version: "26.5.2", project: "" }],
    ["status", { host: "premiere", hostVersion: "26.5.2", bundle: "3.0.0", protocol: 4, busy: "no", project: null }],
    ["open_project", { opened: true }],
    ["set_player_position", {}],
    ["close_project_path", { closed: "yes" }],
    ["clip_components", { clip: "c", components: [{ name: "n", props: [] }] }],
  ];
  for (const [action, rb] of badReadbacks) {
    assert.equal(schemaFn(action, "readback")(rb), false, `ajv accepts ${action} readback ${JSON.stringify(rb)}`);
    assert.ok(validateReadback(action, rb), `${action} readback ${JSON.stringify(rb)} passed the compiled check`);
  }
});

test("an action without a compiled check is refused, never waved through", () => {
  assert.match(validateData("build_project", {}) ?? "", /no check/i);
  assert.match(validateReadback("render_review", {}) ?? "", /no check/i);
});

test("bundled as the plugin bundles it, the adapter runs where code generation from strings is forbidden (UXP), without ajv", async () => {
  const { build } = await import("esbuild");
  const { runInNewContext } = await import("node:vm");
  const out = await build({
    entryPoints: [join(root, "src", "host-adapter.ts")],
    bundle: true, write: false, format: "cjs", platform: "node", target: "es2022",
    external: ["premierepro", "uxp", "fs", "os", "path", "process"], logLevel: "silent",
  });
  const js = out.outputFiles[0]!.text;
  assert.doesNotMatch(js, /ajv\/dist\/(core|compile)|new Function\(|\beval\(/);
  assert.ok(js.length < 200_000, `adapter bundle is ${js.length} bytes`);
  const mod = { exports: {} as Record<string, unknown> };
  runInNewContext(js, { module: mod, exports: mod.exports, Date, JSON, Math, Promise, setTimeout }, { contextCodeGeneration: { strings: false, wasm: false } });
  const bundled = mod.exports as { startHostAdapter: (o: unknown) => unknown };
  assert.equal(typeof bundled.startHostAdapter, "function");
  const sent: Array<{ type: string; result?: { ok: boolean; error?: string } }> = [];
  const sock = { send: (t: string) => void sent.push(JSON.parse(t)), onmessage: null as null | ((e: { data: string }) => void), onclose: null, close: () => undefined };
  bundled.startHostAdapter({ socket: sock, token: "a".repeat(64), env: { ppro: () => ({}), fs: () => ({}), hostVersion: () => "26.5.2", bundleVersion: "3.0.0", sleep: async () => undefined, now: () => 0 } });
  const exp = new Date(Date.now() + 60_000).toISOString();
  sock.onmessage?.({ data: JSON.stringify({ type: "command", request: { protocol: 4, id: "vm-1", action: "set_player_position", data: { sequence_name: "S", t_s: -1 }, expires_at: exp } }) });
  await new Promise((r) => setImmediate(r));
  const res = sent.find((m) => m.type === "result")?.result;
  assert.equal(res?.ok, false);
  assert.match(res?.error ?? "", /t_s/, "the compiled data check ran inside the no-eval context");
});
