import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { unzipSync } from "fflate";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "..", "..");
const version = JSON.parse(readFileSync(join(repo, "whynot-cut", ".claude-plugin", "plugin.json"), "utf8")).version as string;
const ccx = join(repo, "whynot-cut", "adobe", `WhyNotCut-Premiere-${version}.ccx`);
const text = (b: Uint8Array | undefined) => new TextDecoder().decode(b);
const run = (script: string, args: string[], env: Record<string, string> = {}) =>
  spawnSync(process.execPath, [join(root, "scripts", script), ...args], { cwd: root, encoding: "utf8", env: { ...process.env, WNC_MOCK: "", ...env } });

// These tests share build/plugin, so their order matters (a mock build first, the real package last).

test("build plugin --mock bundles the panel kit's MockSource (visual checks); WNC_MOCK=1 does the same", () => {
  for (const [args, env] of [[["plugin", "--mock"], {}], [["plugin"], { WNC_MOCK: "1" }]] as const) {
    const r = run("build.mjs", [...args], { ...env });
    assert.equal(r.status, 0, r.stderr);
    const js = readFileSync(join(root, "build", "plugin", "index.js"), "utf8");
    assert.match(js, /PODCAST-TEST/, "mock data is in a mock build");
  }
});

test("a mock build is never packaged into a .ccx", () => {
  for (const [args, env] of [[["plugin", "--mock"], {}], [["plugin"], { WNC_MOCK: "1" }]] as const) {
    const r = run("package-ccx.mjs", [...args], { ...env });
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, /refusing to package/);
  }
});

test("package-ccx plugin writes whynot-cut/adobe/WhyNotCut-Premiere-<version>.ccx with the plugin files at the zip root", () => {
  execFileSync(process.execPath, [join(root, "scripts", "package-ccx.mjs"), "plugin"], { cwd: root, stdio: "pipe", env: { ...process.env, WNC_MOCK: "" } });
  assert.ok(existsSync(ccx), `ccx not written: ${ccx}`);
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  const names = Object.keys(files);
  for (const need of ["manifest.json", "index.html", "index.js", "index.css", "tokens.css", "panel.css"]) {
    assert.ok(names.includes(need), `missing ${need} at zip root (got ${names.join(", ")})`);
  }
  assert.equal(names[0], "manifest.json", "manifest.json first");
  assert.ok(names.every((n) => !n.includes("\\") && !n.startsWith("plugin/") && !n.startsWith("build/") && !n.startsWith("..")), "entries are forward-slash and rooted at the plugin folder");
  const manifest = JSON.parse(text(files["manifest.json"]));
  assert.equal(manifest.id, "ai.thewhynot.cut.dev");
  assert.equal(manifest.version, version);
  const icons = names.filter((n) => n.startsWith("icons/") && n.endsWith(".png"));
  assert.ok(icons.length >= 12, `expected the icon set, got ${icons.length}`);
  // every icon the manifest names is in the package
  const all = [...manifest.entrypoints[0].icons, ...manifest.icons];
  for (const i of all) assert.ok(names.includes(i.path), `manifest icon ${i.path} not packaged`);
});

test("the panel stylesheets in the package are the panel kit's own files", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  assert.equal(text(files["tokens.css"]), readFileSync(join(root, "..", "panel-ui", "styles", "tokens.css"), "utf8"));
  assert.equal(text(files["panel.css"]), readFileSync(join(root, "..", "panel-ui", "styles", "panel.css"), "utf8"));
  assert.match(text(files["tokens.css"]), /--twn-primary:#5400FB/);
});

test("the shipped bundle: UXP host modules stay external, offline source only (no mock data), brand footer, no 'Claude Code'", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  const js = text(files["index.js"]);
  assert.match(js, /require\(\s*["']premierepro["']\s*\)/);
  assert.match(js, /require\(\s*["']uxp["']\s*\)/);
  assert.doesNotMatch(js, /@adobe\/premierepro/);
  assert.doesNotMatch(js, /PODCAST-TEST|عيادة النور/, "MockSource data must not ship");
  assert.doesNotMatch(js, /Claude Code/);
  assert.match(js, /Powered by Claude/);
  assert.match(js, /reel serve \(coming in 3\.0\)/);
  const html = text(files["index.html"]);
  assert.match(html, /<script[^>]+src="index\.js"/);
  assert.deepEqual([...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map((m) => m[1]), ["tokens.css", "panel.css", "index.css"]);
  assert.ok(!js.includes("sourceMappingURL"), "no source map reference in a shipped file");
});

test("the shipped index.js boots like Premiere would run it: classic script, host modules via require, panel painted into #root", async () => {
  const js = text(unzipSync(new Uint8Array(readFileSync(ccx)))["index.js"]);
  const painted: string[] = [];
  const listeners: string[] = [];
  const rootEl = {
    set innerHTML(v: string) {
      painted.push(v);
    },
    get innerHTML() {
      return painted[painted.length - 1] ?? "";
    },
    addEventListener: (t: string) => void listeners.push(t),
    removeEventListener: () => {},
  };
  const required: string[] = [];
  const sandbox: Record<string, unknown> = {
    document: {
      getElementById: (id: string) => (id === "root" ? rootEl : null),
      documentElement: { style: { setProperty: () => {} } },
      body: {},
    },
    require: (id: string) => {
      required.push(id);
      if (id === "uxp") return { host: { version: "26.5.2", uiLocale: "en_US", getBackgroundColor: () => ({}) } };
      throw new Error(`not needed at startup: ${id}`);
    },
    // the host provides these; the bundle must not reach for a Node-only global
    setTimeout,
    console,
  };
  runInNewContext(js, sandbox);
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(required, ["uxp"], "only the uxp module is touched at startup; premierepro waits for a button press");
  assert.deepEqual(listeners.sort(), ["click", "input"]);
  const html = painted[painted.length - 1] ?? "";
  assert.match(html, /not running/);
  assert.match(html, /Premiere Pro 26\.5\.2/);
});
