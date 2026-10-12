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
  for (const need of ["manifest.json", "index.html", "index.js", "index.css", "fonts.css", "tokens.css", "panel.css"]) {
    assert.ok(names.includes(need), `missing ${need} at zip root (got ${names.join(", ")})`);
  }
  assert.equal(names[0], "manifest.json", "manifest.json first");
  assert.ok(names.every((n) => !n.includes("\\") && !n.startsWith("plugin/") && !n.startsWith("build/") && !n.startsWith("..")), "entries are forward-slash and rooted at the plugin folder");
  const manifest = JSON.parse(text(files["manifest.json"]));
  assert.equal(manifest.id, "ai.thewhynot.cut.dev");
  assert.equal(manifest.version, version);
  // C2.6: the dev id ships visibly as a dev build (Window > UXP Plugins and UPIA /list all show names, not ids)
  assert.equal(manifest.name, "WhyNot Cut (dev)");
  assert.equal(manifest.entrypoints[0].label.default, "WhyNot Cut (dev)");
  assert.equal(manifest.entrypoints[0].id, "whynotCut");
  // C2.6: build.json {product, build, sha}: product = manifest version, build = UTC timestamp id, sha = git short hash
  const build = JSON.parse(text(files["build.json"]));
  assert.deepEqual(Object.keys(build), ["product", "build", "sha"]);
  assert.equal(build.product, version);
  assert.match(build.build, /^\d{8}T\d{6}Z$/);
  assert.match(build.sha, /^(?:[0-9a-f]{4,40}(?:-dirty)?|unknown)$/);
  const icons = names.filter((n) => n.startsWith("icons/") && n.endsWith(".png"));
  assert.ok(icons.length >= 12, `expected the icon set, got ${icons.length}`);
  // every icon the manifest names is in the package
  const all = [...manifest.entrypoints[0].icons, ...manifest.icons];
  for (const i of all) assert.ok(names.includes(i.path), `manifest icon ${i.path} not packaged`);
});

test("the panel stylesheets in the package are the brand token source and the panel kit's own files", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  assert.equal(text(files["tokens.css"]), readFileSync(join(repo, "brand", "tokens.css"), "utf8"), "tokens.css is brand/tokens.css (the one source)");
  assert.equal(text(files["panel.css"]), readFileSync(join(root, "..", "panel-ui", "styles", "panel.css"), "utf8"));
  assert.equal(text(files["fonts.css"]), readFileSync(join(root, "..", "panel-ui", "styles", "fonts.css"), "utf8"));
  assert.match(text(files["tokens.css"]), /--twn-primary:#5400FB/);
  assert.match(text(files["tokens.css"]), /--twn-bg:#000000/);
});

test("font bundle: every @font-face src in the package resolves to a font file inside the .ccx, with its OFL licence; no network URL", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  const css = text(files["fonts.css"]);
  assert.doesNotMatch(css, /https?:|\/\//i);
  const urls = [...css.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map((m) => m[1]!);
  assert.ok(urls.length >= 7, `expected the brand faces, got ${urls.join(", ")}`);
  for (const u of urls) {
    assert.ok(u in files, `${u} is not in the .ccx`);
    assert.ok(files[u]!.length > 10_000, `${u} is not a font file`);
    assert.deepEqual([...files[u]!.subarray(0, 4)], [0, 1, 0, 0], `${u} is not a TrueType file`);
    const ofl = `${u.slice(0, u.lastIndexOf("/"))}/OFL.txt`;
    assert.match(text(files[ofl]), /SIL Open Font License/, `${ofl} missing`);
  }
  for (const fam of ["Syne", "Inter", "IBM Plex Sans Arabic", "IBM Plex Mono"]) assert.match(css, new RegExp(`font-family:\\s*"${fam}"`));
});

test("one string table ships in the bundle: index.js carries the en.json and ar.json copy", () => {
  const js = text(unzipSync(new Uint8Array(readFileSync(ccx)))["index.js"]);
  const en = JSON.parse(readFileSync(join(root, "..", "panel-ui", "i18n", "en.json"), "utf8")) as Record<string, string>;
  const ar = JSON.parse(readFileSync(join(root, "..", "panel-ui", "i18n", "ar.json"), "utf8")) as Record<string, string>;
  // esbuild may write non-ASCII as \uXXXX escapes: accept the literal text or its escaped form
  const escaped = (s: string) => s.replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`).toLowerCase();
  const has = (s: string) => js.includes(s) || js.toLowerCase().includes(escaped(s));
  for (const k of ["offline.title", "rebuild.backup", "qc.hint"]) {
    assert.ok(has(en[k]!), `EN ${k}`);
    assert.ok(has(ar[k]!), `AR ${k}`);
  }
});

test("the shipped bundle: UXP host modules stay external, no mock data, the engine link wired in, brand footer, no 'Claude Code'", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  const js = text(files["index.js"]);
  assert.match(js, /require\(\s*["']premierepro["']\s*\)/);
  assert.match(js, /require\(\s*["']uxp["']\s*\)/);
  assert.doesNotMatch(js, /@adobe\/premierepro/);
  assert.doesNotMatch(js, /PODCAST-TEST|عيادة النور/, "MockSource data must not ship");
  assert.doesNotMatch(js, /Claude Code/);
  assert.match(js, /Powered by thewhynot.ai/);
  assert.match(js, /Open your Claude session to start the engine, then wait a moment\./);
  assert.doesNotMatch(js, /In your Claude session run/, "C2.2: no command lead-in ships");
  // T6.5: the panel is wired to `reel serve` (DaemonSource + the host link), offline banner per diagnosis
  assert.match(js, /require\(\s*["']fs["']\s*\)/);
  assert.match(js, /require\(\s*["']os["']\s*\)/);
  assert.match(js, /\.whynot-cut\/bridge\/engine\.json/);
  assert.match(js, /ws:\/\/127\.0\.0\.1:/);
  assert.match(js, /reel serve --ensure/);
  assert.match(js, /kind: "uxp"/);
  // M8: the build stamp (short git hash [+dirty] + UTC build time) is baked in for the log drawer and the diagnostics
  assert.match(js, /build: "(?:[0-9a-f]{7,}|nogit)(?:\+dirty)? \d{4}-\d\d-\d\dT\d\d:\d\dZ"/);
  const html = text(files["index.html"]);
  assert.match(html, /<script[^>]+src="index\.js"/);
  assert.deepEqual([...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map((m) => m[1]), ["fonts.css", "tokens.css", "panel.css", "index.css"]);
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
  assert.ok(!required.includes("premierepro"), "premierepro waits for a button press or an engine command");
  assert.deepEqual([...new Set(required)].sort(), ["fs", "os", "uxp"], "only uxp, and fs / os for engine.json, at startup");
  assert.deepEqual(listeners.sort(), ["click", "input"]);
  const html = painted[painted.length - 1] ?? "";
  assert.match(html, /not running/);
  assert.match(html, /Premiere Pro 26\.5\.2/);
});

test("the shipped index.js with a WebSocket and no engine.json: DaemonSource diagnoses it in the banner, the host link waits, entrypoints get show/hide", async () => {
  const js = text(unzipSync(new Uint8Array(readFileSync(ccx)))["index.js"]);
  const painted: string[] = [];
  const rootEl = {
    set innerHTML(v: string) {
      painted.push(v);
    },
    get innerHTML() {
      return painted[painted.length - 1] ?? "";
    },
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  const reads: string[] = [];
  const sockets: string[] = [];
  let panels: Record<string, { show(): void; hide(): void; destroy(): void }> = {};
  const sandbox: Record<string, unknown> = {
    document: { getElementById: (id: string) => (id === "root" ? rootEl : null), documentElement: { style: { setProperty: () => {} } }, body: {} },
    require: (id: string) => {
      if (id === "uxp") return { host: { version: "26.5.2", uiLocale: "ar_AE" }, versions: { plugin: version }, entrypoints: { setup: (cfg: { panels: typeof panels }) => void (panels = cfg.panels) } };
      if (id === "fs") return { readFile: async (p: string) => { reads.push(p); throw new Error("ENOENT"); } };
      if (id === "os") return { homedir: () => "C:\\Users\\Ed" };
      throw new Error(`not needed at startup: ${id}`);
    },
    WebSocket: class {
      constructor(url: string) {
        sockets.push(url);
      }
    },
    // unref'd: the panel's retry timers must not keep this test process alive
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms).unref(),
    clearTimeout: (h: ReturnType<typeof setTimeout>) => clearTimeout(h),
    Date,
    console: { log: () => {} },
  };
  runInNewContext(js, sandbox);
  await new Promise((r) => setTimeout(r, 600));
  assert.ok(reads.length >= 2, "engine.json was read (the panel and the host link)");
  assert.ok(reads.every((p) => p === "C:/Users/Ed/.whynot-cut/bridge/engine.json"), reads.join(", "));
  assert.deepEqual(sockets, [], "no engine.json: no socket");
  const html = painted[painted.length - 1] ?? "";
  assert.match(html, /data-link="no_engine"/);
  assert.match(html, /data-action="start-engine"/, "one fix button, no command (C2.2)");
  assert.doesNotMatch(html.replace(/<section class="sec sec-log">[\s\S]*?<\/section>/, ""), /reel /);
  assert.match(html, /dir="rtl"/, "Arabic UI locale: the banner is the Arabic one");
  assert.match(html, /Premiere Pro 26\.5\.2/);
  assert.deepEqual(Object.keys(panels), ["whynotCut"], "the manifest's panel id");
  panels["whynotCut"]!.destroy();
});

test("network \"all\" guard: the shipped code only ever builds ws://127.0.0.1:<port> and http://127.0.0.1:<port> URLs", () => {
  // The manifest grants network "all" because Premiere 26.5.2 refused the explicit 127.0.0.1 entries for a URL with a
  // port (spike 0.1.3, results-20261012-211920). The code stays loopback-only: every URL literal in the bundle is the
  // daemon's session or status URL, nothing else (no other host, no https, no wss).
  const js = text(unzipSync(new Uint8Array(readFileSync(ccx)))["index.js"]);
  const urls = [...js.matchAll(/\b(?:wss?|https?):\/\/[^\s"'`)<>\\]*/gi)].map((m) => m[0]);
  assert.deepEqual([...new Set(urls)].sort(), ["http://127.0.0.1:${port}/status", "ws://127.0.0.1:${port}/session"], urls.join(", "));
  // the two builders, as written in the panel kit
  const src = readFileSync(join(root, "..", "panel-ui", "src", "daemon-source.ts"), "utf8");
  assert.match(src, /return `ws:\/\/127\.0\.0\.1:\$\{port\}\/session`;/);
  assert.match(src, /return `http:\/\/127\.0\.0\.1:\$\{port\}\/status`;/);
  // every socket and fetch in the plugin's own code goes through them (or through the URL handed in by DaemonSource)
  for (const f of ["host-link.ts", "uxp-transport.ts", "main.ts"]) {
    const code = readFileSync(join(root, "src", f), "utf8").replace(/^\s*\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
    assert.doesNotMatch(code, /(?:wss?|https?):\/\//i, `${f} has its own URL literal`);
  }
  const manifest = JSON.parse(text(unzipSync(new Uint8Array(readFileSync(ccx)))["manifest.json"]));
  assert.equal(manifest.requiredPermissions.network.domains, "all");
});
