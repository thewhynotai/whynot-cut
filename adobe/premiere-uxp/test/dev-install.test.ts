// dev-install.mjs (C2.6): UPIA /remove -> /install -> verify, driven with injected deps. Nothing here installs anything.
// Fixtures captured read-only on this PC on 2026-10-13 (Premiere Pro 26.5.2 open, Creative Cloud running):
//   fixtures/upia/list-all.txt     `UnifiedPluginInstallerAgent.exe /list all` stdout, byte for byte (CRLF)
//   fixtures/upia/premierepro.json %APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json
// The /install and /remove outputs below are synthetic: only "Installation Successful" and "status = -642" are known
// strings (Addendum C evidence F7); the code relies on nothing else in them.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, win32 } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { zipSync } from "fflate";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const fixtures = join(root, "test", "fixtures", "upia");
const LIST_ALL = readFileSync(join(fixtures, "list-all.txt"), "utf8");
const PLUGINS_INFO = readFileSync(join(fixtures, "premierepro.json"), "utf8");

type ListRow = { host: string; hostVersion: string | null; status: string; name: string; version: string };
type PluginInfo = { hostMinVersion?: string; name: string; path: string; pluginId: string; status?: string; type?: string; versionString: string };
type Build = { product: string; build: string; sha: string };
type Deps = {
  platform: string;
  env: Record<string, string | undefined>;
  cwd: string;
  upiaPath: string;
  creativeCloudExe: string;
  runUpia(args: string[]): { status: number | null; output: string };
  readFile(p: string): Uint8Array | string;
  exists(p: string): boolean;
  processes(): string[];
  startCreativeCloud(): boolean;
  sleep(ms: number): Promise<void>;
  out(line: string): void;
  err(line: string): void;
};
type DevInstall = {
  UPIA_PATH: string;
  USAGE: string;
  parseArgs(argv: string[]): { ccx?: string; release: boolean; help: boolean; unknown: string[] };
  parseUpiaList(text: string): ListRow[];
  parsePluginsInfo(text: string): PluginInfo[];
  resolvePluginPath(path: string, env: Record<string, string | undefined>): string;
  pluginsInfoPath(env: Record<string, string | undefined>): string;
  installSucceeded(output: string): boolean;
  upiaFailure(output: string): string;
  parseTasklist(csv: string): string[];
  readCcx(bytes: Uint8Array): { manifest: { id: string; name: string; version: string }; build: Build };
  idRefusal(id: string, release: boolean): string | null;
  devInstall(argv: string[], deps: Deps): Promise<number>;
};
// a non-literal specifier: tsc does not type a .mjs, the shape above does
const di = (await import(pathToFileURL(join(root, "scripts", "dev-install.mjs")).href)) as DevInstall;

const APPDATA = String.raw`C:\Users\Ed\AppData\Roaming`;
const ENV = { APPDATA };
const INFO = win32.join(APPDATA, "Adobe", "UXP", "PluginsInfo", "v1", "premierepro.json");
const EXTERNAL = win32.join(APPDATA, "Adobe", "UXP", "Plugins", "External");
const CCX = String.raw`D:\work\WhyNotCut-Premiere-3.0.0.ccx`;
const PKG_BUILD: Build = { product: "3.0.0", build: "20261013T142530Z", sha: "57d3211-dirty" };
const DEV = { id: "ai.thewhynot.cut.dev", name: "WhyNot Cut (dev)", version: "3.0.0" };
const SPIKE: PluginInfo = { hostMinVersion: "26.5.0", name: "WhyNot Cut Spike", path: String.raw`$localPlugins\External\ai.thewhynot.cut.spike_0.1.4`, pluginId: "ai.thewhynot.cut.spike", status: "enabled", type: "uxp", versionString: "0.1.4" };

const enc = (s: string) => new TextEncoder().encode(s);
function ccx(manifest: object | null, build: object | null): Uint8Array {
  const files: Record<string, Uint8Array> = {};
  if (manifest) files["manifest.json"] = enc(JSON.stringify(manifest));
  files["index.html"] = enc("<html></html>");
  if (build) files["build.json"] = enc(JSON.stringify(build));
  return zipSync(files);
}

/** UPIA's /list all, rendered like the captured fixture. */
function listAll(premiere: { status: string; name: string; version: string }[]): string {
  const head = " Status                        Extension Name                         Version\r\n=========  =======================================================  ==========\r\n";
  const rows = premiere.map((p) => ` ${p.status.padEnd(10)} ${p.name.padEnd(56)} ${p.version.padStart(10)}\r\n`).join("");
  const n = premiere.length;
  return `0 extension installed for After Effects (ver 26.5.0)\r\n${head}\r\n${n} extension${n === 1 ? "" : "s"} installed for Premiere Pro (ver 26.5.2)\r\n${head}${rows}\r\n0 extension installed for Others\r\n${head}`;
}

type Installed = { info: PluginInfo; build: Build | null };
type World = {
  procs: string[];
  installed: Map<string, Installed>;
  calls: string[][];
  out: string[];
  err: string[];
  files: Map<string, Uint8Array | string>;
  removeBy: "id" | "name" | "never";
  installOutput: (w: World) => string;
  installedBuild: Build | null;
  listOverride?: string;
  startable: boolean;
  ccAppearsAfterPolls: number;
  polls: number;
  slept: number;
};

function world(over: Partial<World> = {}): World {
  const w: World = {
    procs: ["explorer.exe", "creative cloud.exe", "adobe premiere pro.exe"],
    installed: new Map([
      [SPIKE.pluginId, { info: SPIKE, build: null }],
      // what this PC has now: the dev id installed under the product name
      ["ai.thewhynot.cut.dev", { info: { hostMinVersion: "26.5.0", name: "WhyNot Cut", path: String.raw`$localPlugins\External\ai.thewhynot.cut.dev_3.0.0`, pluginId: "ai.thewhynot.cut.dev", status: "enabled", type: "uxp", versionString: "3.0.0" }, build: { product: "3.0.0", build: "20261012T101010Z", sha: "6961ccf" } }],
    ]),
    calls: [],
    out: [],
    err: [],
    files: new Map([[CCX, ccx(DEV, PKG_BUILD)]]),
    removeBy: "id",
    installOutput: () => "Installing extension...\r\nInstallation Successful\r\n",
    installedBuild: PKG_BUILD,
    startable: true,
    ccAppearsAfterPolls: 0,
    polls: 0,
    slept: 0,
    ...over,
  };
  return w;
}

function deps(w: World, over: Partial<Deps> = {}): Deps {
  const pkg = () => di.readCcx(w.files.get(CCX) as Uint8Array);
  return {
    platform: "win32",
    env: ENV,
    cwd: String.raw`D:\work`,
    upiaPath: di.UPIA_PATH,
    creativeCloudExe: "cc.exe",
    runUpia(args) {
      w.calls.push(args);
      const [cmd, arg] = args;
      if (cmd === "/remove") {
        const hit = [...w.installed.values()].find((p) => (w.removeBy === "id" ? p.info.pluginId === arg : w.removeBy === "name" ? p.info.name === arg : false));
        if (hit) w.installed.delete(hit.info.pluginId);
        return { status: 0, output: hit ? "Removal Successful\r\n" : "Failed to remove extension\r\n" };
      }
      if (cmd === "/install") {
        const output = w.installOutput(w);
        if (di.installSucceeded(output)) {
          const { manifest } = pkg();
          w.installed.set(manifest.id, { info: { hostMinVersion: "26.5.0", name: manifest.name, path: `$localPlugins\\External\\${manifest.id}_${manifest.version}`, pluginId: manifest.id, status: "enabled", type: "uxp", versionString: manifest.version }, build: w.installedBuild });
        }
        return { status: 0, output }; // UPIA exits 0 even when it fails
      }
      if (cmd === "/list") {
        if (w.listOverride !== undefined) return { status: 0, output: w.listOverride };
        return { status: 0, output: listAll([...w.installed.values()].map((p) => ({ status: "Enabled", name: p.info.name, version: p.info.versionString }))) };
      }
      return { status: 0, output: "" };
    },
    readFile(p) {
      if (w.files.has(p)) return w.files.get(p)!;
      if (p === INFO) return JSON.stringify({ plugins: [...w.installed.values()].map((x) => x.info) });
      for (const x of w.installed.values()) {
        const dir = win32.join(EXTERNAL, `${x.info.pluginId}_${x.info.versionString}`);
        if (p === win32.join(dir, "build.json") && x.build) return JSON.stringify(x.build, null, 2);
      }
      throw Object.assign(new Error(`ENOENT: ${p}`), { code: "ENOENT" });
    },
    exists: (p) => p === di.UPIA_PATH,
    processes() {
      if (!w.procs.includes("creative cloud.exe") && w.polls > 0 && w.polls > w.ccAppearsAfterPolls && w.startable) w.procs.push("creative cloud.exe");
      return [...w.procs];
    },
    startCreativeCloud: () => w.startable,
    async sleep(ms) {
      w.slept += ms;
      w.polls += 1;
    },
    out: (l) => void w.out.push(l),
    err: (l) => void w.err.push(l),
    ...over,
  };
}

// ---------------------------------------------------------------- parsers, on the real captures

test("parseUpiaList reads the real `/list all` capture: every product section, the two Premiere Pro panels with status, name and version", () => {
  const rows = di.parseUpiaList(LIST_ALL);
  assert.deepEqual(rows, [
    { host: "Premiere Pro", hostVersion: "26.5.2", status: "Enabled", name: "WhyNot Cut", version: "3.0.0" },
    { host: "Premiere Pro", hostVersion: "26.5.2", status: "Enabled", name: "WhyNot Cut Spike", version: "0.1.4" },
  ]);
  assert.ok(LIST_ALL.includes("\r\n"), "the capture keeps UPIA's CRLF");
  assert.deepEqual(di.parseUpiaList(LIST_ALL.replace(/\r\n/g, "\n")), rows, "LF works the same");
  // UPIA lists names, not ids: the id is nowhere in the output
  assert.ok(!LIST_ALL.includes("ai.thewhynot.cut"));
  // a name with "(dev)" and the rendered helper parse back
  assert.deepEqual(di.parseUpiaList(listAll([{ status: "Disabled", name: "WhyNot Cut (dev)", version: "3.0.0" }])).map((r) => [r.status, r.name, r.version]), [["Disabled", "WhyNot Cut (dev)", "3.0.0"]]);
});

test("parsePluginsInfo reads the real premierepro.json; $localPlugins resolves under %APPDATA%\\Adobe\\UXP\\Plugins", () => {
  const plugins = di.parsePluginsInfo(PLUGINS_INFO);
  assert.deepEqual(plugins.map((p) => [p.pluginId, p.name, p.versionString, p.path]), [
    ["ai.thewhynot.cut.spike", "WhyNot Cut Spike", "0.1.4", String.raw`$localPlugins\External\ai.thewhynot.cut.spike_0.1.4`],
    ["ai.thewhynot.cut.dev", "WhyNot Cut", "3.0.0", String.raw`$localPlugins\External\ai.thewhynot.cut.dev_3.0.0`],
  ]);
  assert.deepEqual(Object.keys(plugins[0]!).sort(), ["hostMinVersion", "name", "path", "pluginId", "status", "type", "versionString"]);
  assert.equal(di.resolvePluginPath(plugins[1]!.path, ENV), win32.join(EXTERNAL, "ai.thewhynot.cut.dev_3.0.0"));
  assert.equal(di.pluginsInfoPath(ENV), INFO);
  assert.deepEqual(di.parsePluginsInfo(`\uFEFF${PLUGINS_INFO}`), plugins, "a BOM is tolerated");
  assert.throws(() => di.parsePluginsInfo("{}"), /plugins/);
  assert.throws(() => di.resolvePluginPath(String.raw`$sharedPlugins\x`, ENV), /unknown plugin path/);
});

test("install output: success needs the exact phrase; a failure names the UPIA status (-642 = Creative Cloud) or UPIA's last line", () => {
  assert.equal(di.installSucceeded("...\r\nInstallation Successful\r\n"), true);
  assert.equal(di.installSucceeded("Installation failed, status = -642"), false);
  assert.match(di.upiaFailure("Failed to install, status = -642!"), /status = -642 \(Creative Cloud is not running or not ready\)/);
  assert.match(di.upiaFailure("Failed to install, status = -402"), /status = -402$/);
  assert.equal(di.upiaFailure("line one\r\nsomething broke\r\n"), "UPIA said: something broke");
  assert.equal(di.upiaFailure(""), "UPIA printed nothing");
});

test("parseTasklist: image names from tasklist /FO CSV /NH, lower-cased", () => {
  const csv = '"System Idle Process","0","Services","0","8 K"\r\n"Creative Cloud.exe","137304","Console","1","120,000 K"\r\n"Adobe Premiere Pro.exe","126228","Console","1","2,000,000 K"\r\n';
  assert.deepEqual(di.parseTasklist(csv), ["system idle process", "creative cloud.exe", "adobe premiere pro.exe"]);
});

test("readCcx: manifest.json and build.json from the zip; a ccx without build.json or manifest.json is refused", () => {
  const { manifest, build } = di.readCcx(ccx(DEV, PKG_BUILD));
  assert.equal(manifest.id, "ai.thewhynot.cut.dev");
  assert.deepEqual(build, PKG_BUILD);
  assert.throws(() => di.readCcx(ccx(DEV, null)), /no build\.json/);
  assert.throws(() => di.readCcx(ccx(null, PKG_BUILD)), /no manifest\.json/);
  assert.throws(() => di.readCcx(enc("not a zip")), /not a zip/);
  assert.throws(() => di.readCcx(ccx(DEV, { product: "3.0.0", build: "x" })), /no sha/);
});

test("id safety: the release id needs --release; dev and spike ids are fine; a foreign id is refused", () => {
  assert.match(di.idRefusal("ai.thewhynot.cut", false)!, /release id ai\.thewhynot\.cut; add --release/);
  assert.equal(di.idRefusal("ai.thewhynot.cut", true), null);
  assert.equal(di.idRefusal("ai.thewhynot.cut.dev", false), null);
  assert.equal(di.idRefusal("ai.thewhynot.cut.spike", false), null);
  assert.match(di.idRefusal("com.example.other", true)!, /not a WhyNot Cut plugin id/);
  assert.match(di.idRefusal("ai.thewhynot.cutter", true)!, /not a WhyNot Cut plugin id/);
  assert.deepEqual(di.parseArgs(["x.ccx", "--release"]), { ccx: "x.ccx", release: true, help: false, unknown: [] });
});

// ---------------------------------------------------------------- the whole run

test("happy path: /remove <id> -> /install <ccx> -> /list all; name, version and the installed build.json all match -> exit 0", async () => {
  const w = world();
  const code = await di.devInstall(["WhyNotCut-Premiere-3.0.0.ccx"], deps(w));
  assert.equal(code, 0, w.err.join("\n"));
  assert.deepEqual(w.calls, [["/remove", "ai.thewhynot.cut.dev"], ["/install", CCX], ["/list", "all"]]);
  assert.deepEqual(w.err, []);
  assert.match(w.out.join("\n"), /installed and verified: "WhyNot Cut \(dev\)" 3\.0\.0 \(Enabled\), build 20261013T142530Z, sha 57d3211-dirty/);
  assert.match(w.out.at(-1)!, /Premiere Pro is open: restart it/);
  assert.ok(w.installed.has(SPIKE.pluginId), "the spike is left alone");
});

test("UPIA exits 0 but the output has no \"Installation Successful\" (status = -642): exit 1 with the reason", async () => {
  const w = world({ installOutput: () => "Failed to install extension, status = -642\r\n" });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err.join("\n"), /^Install failed: UPIA reported status = -642 \(Creative Cloud is not running or not ready\) \(UPIA exit code 0\)\.$/);
  assert.deepEqual(w.calls.map((c) => c[0]), ["/remove", "/install"]);
});

test("\"Installation Successful\" but /list all does not show the name and version: exit 1", async () => {
  const w = world({ listOverride: LIST_ALL });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err[0]!, /UPIA \/list all shows "WhyNot Cut" 3\.0\.0, "WhyNot Cut Spike" 0\.1\.4 for Premiere Pro, not "WhyNot Cut \(dev\)" 3\.0\.0/);
});

test("same-version trap: installed build.json is the old build -> exit 1 naming both builds", async () => {
  const w = world({ installedBuild: { product: "3.0.0", build: "20261012T101010Z", sha: "6961ccf" } });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err[0]!, /installed build\.json is 3\.0\.0 build 20261012T101010Z sha 6961ccf, the package is 3\.0\.0 build 20261013T142530Z sha 57d3211-dirty/);
});

test("installed folder has no build.json (a build from before C2.6): exit 1", async () => {
  const w = world({ installedBuild: null });
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.match(w.err[0]!, /build\.json is missing or unreadable/);
});

test("same sha but a different build id still fails: build AND sha must equal the packaged ones", async () => {
  const w = world({ installedBuild: { ...PKG_BUILD, build: "20261013T000000Z" } });
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
});

test("/remove <id> leaves it installed: retried by the installed name (UPIA help: /remove <extension-name>)", async () => {
  const w = world({ removeBy: "name" });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 0, w.err.join("\n"));
  assert.deepEqual(w.calls.slice(0, 2), [["/remove", "ai.thewhynot.cut.dev"], ["/remove", "WhyNot Cut"]]);
});

test("never removes by a name another id shares (it could be the release panel): exit 1, nothing installed", async () => {
  const w = world({ removeBy: "name" });
  w.installed.set("ai.thewhynot.cut", { info: { name: "WhyNot Cut", path: String.raw`$localPlugins\External\ai.thewhynot.cut_3.0.0`, pluginId: "ai.thewhynot.cut", versionString: "3.0.0" }, build: null });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err[0]!, /name "WhyNot Cut" is also used by ai\.thewhynot\.cut/);
  assert.deepEqual(w.calls, [["/remove", "ai.thewhynot.cut.dev"]]);
});

test("nothing removes it: exit 1 before any install", async () => {
  const w = world({ removeBy: "never" });
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.match(w.err[0]!, /UPIA did not remove ai\.thewhynot\.cut\.dev \("WhyNot Cut" 3\.0\.0 is still installed\)/);
  assert.ok(!w.calls.some((c) => c[0] === "/install"));
});

test("Creative Cloud not running and it cannot be started: exit 2, one sentence, UPIA never called", async () => {
  const w = world({ procs: ["explorer.exe"], startable: false });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 2);
  assert.deepEqual(w.err, ["Creative Cloud is not running and could not be started; open Creative Cloud, then run this again."]);
  assert.deepEqual(w.calls, []);
});

test("Creative Cloud not running: started, polled until its process appears, then the install goes on", async () => {
  const w = world({ procs: ["explorer.exe"], ccAppearsAfterPolls: 3 });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 0, w.err.join("\n"));
  assert.match(w.out[0]!, /starting it/);
  assert.ok(w.slept >= 4 * 2000, `waited ${w.slept} ms`);
});

test("Creative Cloud started but never appears within a minute: exit 2", async () => {
  const w = world({ procs: ["explorer.exe"], ccAppearsAfterPolls: 1000 });
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.ok(w.slept >= 60_000);
  assert.deepEqual(w.calls, []);
});

test("release id: refused without --release (exit 2, UPIA never called); installed with --release", async () => {
  const rel = { id: "ai.thewhynot.cut", name: "WhyNot Cut", version: "3.0.0" };
  const w = world();
  w.files.set(CCX, ccx(rel, PKG_BUILD));
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /release id ai\.thewhynot\.cut; add --release/);
  assert.deepEqual(w.calls, []);
  const w2 = world();
  w2.files.set(CCX, ccx(rel, PKG_BUILD));
  assert.equal(await di.devInstall([CCX, "--release"], deps(w2)), 0, w2.err.join("\n"));
  assert.deepEqual(w2.calls[0], ["/remove", "ai.thewhynot.cut"]);
});

test("spike ccx installs (its id is fine), first install with nothing to remove", async () => {
  const w = world();
  w.installed.delete(SPIKE.pluginId);
  w.files.set(CCX, ccx({ id: "ai.thewhynot.cut.spike", name: "WhyNot Cut Spike", version: "0.1.6" }, { product: "0.1.6", build: "20261013T142530Z", sha: "57d3211" }));
  w.installedBuild = { product: "0.1.6", build: "20261013T142530Z", sha: "57d3211" };
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  assert.match(w.out.join("\n"), /removing ai\.thewhynot\.cut\.spike \(not installed\)/);
});

test("start-up refusals exit 2 with one line: no args, unknown flag, not Windows, missing ccx, ccx without build.json, no UPIA", async () => {
  const cases: [string[], Partial<Deps>, (w: World) => void, RegExp][] = [
    [[], {}, () => {}, /^usage: npm run dev-install -- <path to \.ccx> \[--release\]$/],
    [[CCX, "--force"], {}, () => {}, /^Unknown argument --force/],
    [[CCX], { platform: "darwin" }, () => {}, /Windows only/],
    [[String.raw`D:\work\missing.ccx`], {}, () => {}, /missing\.ccx: it does not exist\.$/],
    [[CCX], {}, (w) => void w.files.set(CCX, ccx(DEV, null)), /no build\.json; package it with npm run package:plugin/],
    [[CCX], { exists: () => false }, () => {}, /UPIA\) is not at /],
  ];
  for (const [argv, over, setup, re] of cases) {
    const w = world();
    setup(w);
    assert.equal(await di.devInstall(argv, deps(w, over)), 2, argv.join(" "));
    assert.equal(w.err.length, 1);
    assert.match(w.err[0]!, re);
    assert.deepEqual(w.calls, []);
  }
});

test("the CLI: npm run dev-install is wired in adobe/package.json; no args -> exit 2 + usage, --help -> exit 0 (no UPIA call either way)", () => {
  const pkg = JSON.parse(readFileSync(join(root, "..", "package.json"), "utf8")) as { scripts: Record<string, string> };
  assert.equal(pkg.scripts["dev-install"], "node premiere-uxp/scripts/dev-install.mjs");
  const script = join(root, "scripts", "dev-install.mjs");
  const none = spawnSync(process.execPath, [script], { encoding: "utf8" });
  assert.equal(none.status, 2);
  assert.match(none.stderr, /usage: npm run dev-install/);
  const help = spawnSync(process.execPath, [script, "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /usage: npm run dev-install/);
});

test("dev-install source: the UPIA path is the one in the parity doc; it never reaches into adobe/tools", () => {
  assert.equal(di.UPIA_PATH, String.raw`C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe`);
  const src = readFileSync(join(root, "scripts", "dev-install.mjs"), "utf8");
  assert.doesNotMatch(src, /adobe[\\/]tools|\.\.\/tools/);
});
