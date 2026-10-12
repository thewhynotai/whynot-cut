// dev-install.mjs (C2.6): UPIA /remove -> /install -> verify, driven with injected deps. Nothing here installs anything.
// Fixtures captured read-only on this PC on 2026-10-13 (Premiere Pro 26.5.2 open, Creative Cloud running):
//   fixtures/upia/list-all.txt     `UnifiedPluginInstallerAgent.exe /list all` stdout, byte for byte (CRLF)
//   fixtures/upia/premierepro.json %APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json
// The /install and /remove outputs below are synthetic: only "Installation Successful" and "status = -642" are known
// strings (Addendum C evidence F7); the code relies on nothing else in them.
// The fake UPIA removes by NAME by default (Adobe's documented form, "/remove <extension-name>"), and by name it removes
// every plugin of that name, which is exactly why dev-install must never remove by a name another plugin shares.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
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
type Manifest = { id: string; name: string; version: string };
type Deps = {
  platform: string;
  env: Record<string, string | undefined>;
  cwd: string;
  upiaPath: string;
  creativeCloudExe: string;
  runUpia(args: string[]): { status: number | null; output: string };
  readFile(p: string): Uint8Array | string;
  exists(p: string): boolean;
  processes(): string[] | null;
  startCreativeCloud(): boolean | Promise<boolean>;
  sleep(ms: number): Promise<void>;
  now(): number;
  tmpdir(): string;
  mkdir(p: string): void;
  copyFile(src: string, dst: string): void;
  removeFile(p: string): void;
  out(line: string): void;
  err(line: string): void;
};
type Sys = {
  env?: Record<string, string | undefined>;
  platform?: string;
  exists?: (p: string) => boolean;
  spawn?: (cmd: string, args: string[], opts: object) => EventEmitter & { unref(): void };
  spawnSync?: (cmd: string, args: string[], opts: { timeout?: number }) => { error?: Error; status: number | null; stdout?: string; stderr?: string };
};
type DevInstall = {
  UPIA_PATH: string;
  CREATIVE_CLOUD_EXE: string;
  ASCII_TMP_FALLBACK: string;
  USAGE: string;
  parseArgs(argv: string[]): { ccx?: string; release: boolean; force: boolean; help: boolean; unknown: string[] };
  parseUpiaList(text: string): ListRow[];
  isPremiereRow(row: ListRow): boolean;
  parsePluginsInfo(text: string): PluginInfo[];
  resolvePluginPath(path: string, env: Record<string, string | undefined>): string;
  pluginsInfoPath(env: Record<string, string | undefined>): string;
  installSucceeded(output: string): boolean;
  upiaFailure(output: string): string;
  parseTasklist(csv: string): string[];
  readCcx(bytes: Uint8Array): { manifest: Manifest; build: Build };
  idRefusal(id: string, release: boolean): string | null;
  nameRefusal(manifest: Manifest): string | null;
  adobePaths(env: Record<string, string | undefined>): { upia: string; creativeCloud: string };
  tempCcxPath(tmpdir: string, manifest: Manifest, now: number): { dir: string; file: string };
  realDeps(sys?: Sys): Deps;
  devInstall(argv: string[], deps: Deps): Promise<number>;
};
type Ids = { RELEASE_ID: string; RELEASE_NAME: string; DEV_ID: string; SPIKE_ID: string };
// a non-literal specifier: tsc does not type a .mjs, the shape above does
const di = (await import(pathToFileURL(join(root, "scripts", "dev-install.mjs")).href)) as DevInstall;
const ids = (await import(pathToFileURL(join(root, "scripts", "ids.mjs")).href)) as Ids;

const APPDATA = String.raw`C:\Users\Ed\AppData\Roaming`;
const ENV = { APPDATA };
const INFO = win32.join(APPDATA, "Adobe", "UXP", "PluginsInfo", "v1", "premierepro.json");
const EXTERNAL = win32.join(APPDATA, "Adobe", "UXP", "Plugins", "External");
const TMP = String.raw`C:\Users\Ed\AppData\Local\Temp`;
const CCX = String.raw`D:\work\WhyNotCut-Premiere-3.0.0.ccx`;
const PKG_BUILD: Build = { product: "3.0.0", build: "20261013T142530Z", sha: "57d3211-dirty" };
const DEV: Manifest = { id: "ai.thewhynot.cut.dev", name: "WhyNot Cut (dev)", version: "3.0.0" };
const REL: Manifest = { id: "ai.thewhynot.cut", name: "WhyNot Cut", version: "3.0.0" };
const SPIKE: PluginInfo = { hostMinVersion: "26.5.0", name: "WhyNot Cut Spike", path: String.raw`$localPlugins\External\ai.thewhynot.cut.spike_0.1.4`, pluginId: "ai.thewhynot.cut.spike", status: "enabled", type: "uxp", versionString: "0.1.4" };
/** What this PC has now: the dev id installed under the product name (from before the "(dev)" stamp). */
const DEV_AS_PRODUCT: PluginInfo = { hostMinVersion: "26.5.0", name: "WhyNot Cut", path: String.raw`$localPlugins\External\ai.thewhynot.cut.dev_3.0.0`, pluginId: "ai.thewhynot.cut.dev", status: "enabled", type: "uxp", versionString: "3.0.0" };
const OLD_BUILD: Build = { product: "3.0.0", build: "20261012T101010Z", sha: "6961ccf" };

const enc = (s: string) => new TextEncoder().encode(s);
function ccx(manifest: object | null, build: object | null): Uint8Array {
  const files: Record<string, Uint8Array> = {};
  if (manifest) files["manifest.json"] = enc(JSON.stringify(manifest));
  files["index.html"] = enc("<html></html>");
  if (build) files["build.json"] = enc(JSON.stringify(build));
  return zipSync(files);
}

type Row = { status: string; name: string; version: string };
const HEAD = " Status                        Extension Name                         Version\r\n=========  =======================================================  ==========\r\n";
/** UPIA's /list all, rendered like the captured fixture: one section per product label. */
function listAll(sections: [string, Row[]][]): string {
  return sections
    .map(([label, rows]) => {
      const body = rows.map((p) => ` ${p.status.padEnd(10)} ${p.name.padEnd(56)} ${p.version.padStart(10)}\r\n`).join("");
      return `${rows.length} extension${rows.length > 1 ? "s" : ""} installed for ${label}\r\n${HEAD}${body}\r\n`;
    })
    .join("");
}

type Installed = { info: PluginInfo; build: Build | string | null };
type World = {
  procs: string[] | null;
  installed: Map<string, Installed>;
  calls: string[][];
  out: string[];
  err: string[];
  files: Map<string, Uint8Array | string>;
  removedFiles: string[];
  dirs: string[];
  removeBy: "id" | "name" | "never";
  collateral: string[];
  installOutput: (w: World) => string;
  installedBuild: Build | string | null;
  listOverride?: string;
  extraSections: [string, Row[]][];
  infoRaw?: string;
  infoBom: boolean;
  infoExists: boolean;
  infoLagMs: number;
  listLagMs: number;
  changedAt: number;
  infoView?: PluginInfo[];
  listView?: PluginInfo[];
  tmpdir: string;
  startable: boolean;
  ccAppearsAfterPolls: number;
  polls: number;
  slept: number;
  clock: number;
};

function world(over: Partial<World> = {}): World {
  return {
    procs: ["explorer.exe", "creative cloud.exe"],
    installed: new Map<string, Installed>([
      [SPIKE.pluginId, { info: SPIKE, build: null }],
      [DEV_AS_PRODUCT.pluginId, { info: DEV_AS_PRODUCT, build: OLD_BUILD }],
    ]),
    calls: [],
    out: [],
    err: [],
    files: new Map([[CCX, ccx(DEV, PKG_BUILD)]]),
    removedFiles: [],
    dirs: [],
    removeBy: "name",
    collateral: [],
    installOutput: () => "Installing extension...\r\nInstallation Successful\r\n",
    installedBuild: PKG_BUILD,
    extraSections: [],
    infoBom: false,
    infoExists: true,
    infoLagMs: 0,
    listLagMs: 0,
    changedAt: -Infinity,
    tmpdir: TMP,
    startable: true,
    ccAppearsAfterPolls: 0,
    polls: 0,
    slept: 0,
    clock: 1_000_000,
    ...over,
  };
}

/** PluginsInfo and /list all follow the real state only `lag` ms after the last change (Premiere/UPIA write late). */
function view(w: World, which: "infoView" | "listView", lag: number): PluginInfo[] {
  if (w[which] === undefined || w.clock - w.changedAt >= lag) w[which] = [...w.installed.values()].map((x) => x.info);
  return w[which]!;
}

function deps(w: World, over: Partial<Deps> = {}): Deps {
  return {
    platform: "win32",
    env: ENV,
    cwd: String.raw`D:\work`,
    upiaPath: di.UPIA_PATH,
    creativeCloudExe: "cc.exe",
    runUpia(args) {
      w.calls.push(args);
      const [cmd, arg = ""] = args;
      if (cmd === "/remove") {
        const hits = [...w.installed.values()].filter((p) =>
          w.removeBy === "id" ? p.info.pluginId === arg : w.removeBy === "name" ? p.info.name.toLowerCase() === arg.toLowerCase() : false,
        );
        for (const h of hits) w.installed.delete(h.info.pluginId);
        if (hits.length) {
          for (const id of w.collateral) w.installed.delete(id);
          w.changedAt = w.clock;
        }
        return { status: 0, output: hits.length ? "Removal Successful\r\n" : "Failed to remove extension\r\n" };
      }
      if (cmd === "/install") {
        const bytes = w.files.get(arg);
        if (!bytes) return { status: 0, output: "Failed to install extension, file not found\r\n" };
        const output = w.installOutput(w);
        if (di.installSucceeded(output)) {
          const { manifest } = di.readCcx(bytes as Uint8Array);
          const info: PluginInfo = { hostMinVersion: "26.5.0", name: manifest.name, path: `$localPlugins\\External\\${manifest.id}_${manifest.version}`, pluginId: manifest.id, status: "enabled", type: "uxp", versionString: manifest.version };
          w.installed.set(manifest.id, { info, build: w.installedBuild });
          w.changedAt = w.clock;
        }
        return { status: 0, output }; // UPIA exits 0 even when it fails
      }
      if (cmd === "/list") {
        if (w.listOverride !== undefined) return { status: 0, output: w.listOverride };
        const premiere = view(w, "listView", w.listLagMs).map((p) => ({ status: "Enabled", name: p.name, version: p.versionString }));
        return { status: 0, output: listAll([["After Effects (ver 26.5.0)", []], ["Premiere Pro (ver 26.5.2)", premiere], ...w.extraSections, ["Others", []]]) };
      }
      return { status: 0, output: "" };
    },
    readFile(p) {
      if (w.files.has(p)) return w.files.get(p)!;
      if (p === INFO && w.infoExists) return w.infoRaw ?? `${w.infoBom ? "﻿" : ""}${JSON.stringify({ plugins: view(w, "infoView", w.infoLagMs) })}`;
      for (const x of w.installed.values()) {
        const dir = win32.join(EXTERNAL, `${x.info.pluginId}_${x.info.versionString}`);
        if (p === win32.join(dir, "build.json") && x.build) return typeof x.build === "string" ? x.build : JSON.stringify(x.build, null, 2);
      }
      throw Object.assign(new Error(`ENOENT: ${p}`), { code: "ENOENT" });
    },
    exists: (p) => p === di.UPIA_PATH || (p === INFO && w.infoExists),
    processes() {
      if (w.procs === null) return null;
      if (!w.procs.includes("creative cloud.exe") && w.polls > 0 && w.polls > w.ccAppearsAfterPolls && w.startable) w.procs.push("creative cloud.exe");
      return [...w.procs];
    },
    startCreativeCloud: () => w.startable,
    async sleep(ms) {
      w.slept += ms;
      w.polls += 1;
      w.clock += ms;
    },
    now: () => w.clock,
    tmpdir: () => w.tmpdir,
    mkdir: (p) => void w.dirs.push(p),
    copyFile(src, dst) {
      if (!w.files.has(src)) throw Object.assign(new Error(`ENOENT: ${src}`), { code: "ENOENT" });
      w.files.set(dst, w.files.get(src)!);
    },
    removeFile(p) {
      w.files.delete(p);
      w.removedFiles.push(p);
    },
    out: (l) => void w.out.push(l),
    err: (l) => void w.err.push(l),
    ...over,
  };
}

const installArg = (w: World) => w.calls.find((c) => c[0] === "/install")?.[1];
const mutating = (w: World) => w.calls.filter((c) => c[0] !== "/list");

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
  assert.deepEqual(di.parseUpiaList(listAll([["Premiere Pro (ver 26.5.2)", [{ status: "Disabled", name: "WhyNot Cut (dev)", version: "3.0.0" }]]])).map((r) => [r.status, r.name, r.version]), [["Disabled", "WhyNot Cut (dev)", "3.0.0"]]);
});

test("parseUpiaList: a status holding a space and an over-wide name (one space before the version) still parse", () => {
  const wide = "WhyNot Cut (dev) with a very long name that overflows the fifty-five column field";
  const text = listAll([
    [
      "Premiere Pro (ver 26.5.2)",
      [
        { status: "Not Ready", name: "WhyNot Cut (dev)", version: "3.0.0" },
        { status: "Enabled", name: wide, version: "26.5.0-beta.10" },
      ],
    ],
  ]);
  assert.ok(text.includes(`${wide} 26.5.0-beta.10`), "the over-wide row has a single space before its version");
  assert.deepEqual(di.parseUpiaList(text).map((r) => [r.status, r.name, r.version]), [
    ["Not Ready", "WhyNot Cut (dev)", "3.0.0"],
    ["Enabled", wide, "26.5.0-beta.10"],
  ]);
});

test("isPremiereRow: the section ^Premiere Pro(\\s*\\(ver|$) only; Premiere Pro (Beta) and look-alikes are excluded", () => {
  const rows = di.parseUpiaList(
    listAll([
      ["Premiere Pro (ver 26.5.2)", [{ status: "Enabled", name: "A", version: "1" }]],
      ["Premiere Pro", [{ status: "Enabled", name: "B", version: "1" }]],
      ["Premiere Pro (Beta) (ver 26.6.0)", [{ status: "Enabled", name: "C", version: "1" }]],
      ["Premiere Pro Beta (ver 26.6.0)", [{ status: "Enabled", name: "D", version: "1" }]],
      ["Premiere Rush (ver 2.0)", [{ status: "Enabled", name: "E", version: "1" }]],
    ]),
  );
  assert.deepEqual(rows.filter(di.isPremiereRow).map((r) => r.name), ["A", "B"]);
  assert.equal(rows.find((r) => r.name === "C")!.host, "Premiere Pro (Beta)");
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

test("id safety: only the .dev and .spike ids, or the release id with --release; any other ai.thewhynot.cut.* id is refused", () => {
  assert.match(di.idRefusal("ai.thewhynot.cut", false)!, /release id ai\.thewhynot\.cut; add --release/);
  assert.equal(di.idRefusal("ai.thewhynot.cut", true), null);
  assert.equal(di.idRefusal("ai.thewhynot.cut.dev", false), null);
  assert.equal(di.idRefusal("ai.thewhynot.cut.spike", false), null);
  for (const id of ["ai.thewhynot.cut.tools", "ai.thewhynot.cut.devx", "ai.thewhynot.cut.dev.extra", "ai.thewhynot.cut.x.spike"]) {
    assert.match(di.idRefusal(id, true) ?? "", /not a dev or spike id/, id);
  }
  assert.match(di.idRefusal("com.example.other", true)!, /not a WhyNot Cut plugin id/);
  assert.match(di.idRefusal("ai.thewhynot.cutter", true)!, /not a WhyNot Cut plugin id/);
  assert.deepEqual(di.parseArgs(["x.ccx", "--release", "--force"]), { ccx: "x.ccx", release: true, force: true, help: false, unknown: [] });
});

test("release-name safety: a non-release id named \"WhyNot Cut\" (any case, any spaces) is refused; prefixes are not the name", () => {
  assert.match(di.nameRefusal({ id: "ai.thewhynot.cut.dev", name: "WhyNot Cut", version: "3.0.0" })!, /release plugin's name/);
  assert.match(di.nameRefusal({ id: "ai.thewhynot.cut.spike", name: "  whynot CUT ", version: "0.1.4" })!, /release plugin's name/);
  assert.equal(di.nameRefusal(REL), null);
  assert.equal(di.nameRefusal(DEV), null);
  assert.equal(di.nameRefusal({ id: "ai.thewhynot.cut.spike", name: "WhyNot Cut Spike", version: "0.1.4" }), null);
});

test("ids.mjs: the release id and name match package-ccx's (read as text, never imported); dev-install loads neither package-ccx nor esbuild", () => {
  assert.equal(ids.RELEASE_ID, "ai.thewhynot.cut");
  assert.equal(ids.RELEASE_NAME, "WhyNot Cut");
  assert.equal(ids.DEV_ID, "ai.thewhynot.cut.dev");
  assert.equal(ids.SPIKE_ID, "ai.thewhynot.cut.spike");
  const pkgSrc = readFileSync(join(root, "scripts", "package-ccx.mjs"), "utf8");
  assert.equal(/export const RELEASE_ID = "([^"]+)"/.exec(pkgSrc)?.[1], ids.RELEASE_ID);
  const src = readFileSync(join(root, "scripts", "dev-install.mjs"), "utf8");
  assert.doesNotMatch(src, /from\s+["']\.\/(package-ccx|build)\.mjs["']|["']esbuild["']/);
  const idsSrc = readFileSync(join(root, "scripts", "ids.mjs"), "utf8");
  assert.doesNotMatch(idsSrc, /^import /m);
});

test("adobePaths: from %CommonProgramFiles% / %ProgramFiles%, falling back to C:\\Program Files", () => {
  assert.deepEqual(di.adobePaths({}), { upia: di.UPIA_PATH, creativeCloud: di.CREATIVE_CLOUD_EXE });
  assert.equal(di.CREATIVE_CLOUD_EXE, String.raw`C:\Program Files\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe`);
  assert.deepEqual(di.adobePaths({ ProgramFiles: String.raw`E:\Apps`, CommonProgramFiles: String.raw`E:\Apps\Shared` }), {
    upia: String.raw`E:\Apps\Shared\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe`,
    creativeCloud: String.raw`E:\Apps\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe`,
  });
  assert.equal(di.adobePaths({ ProgramFiles: String.raw`E:\Apps` }).upia, String.raw`E:\Apps\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe`);
  assert.deepEqual(di.adobePaths({ ProgramFiles: "relative", CommonProgramFiles: "" }), { upia: di.UPIA_PATH, creativeCloud: di.CREATIVE_CLOUD_EXE });
  const rd = di.realDeps({ env: { ProgramFiles: String.raw`E:\Apps` } });
  assert.equal(rd.creativeCloudExe, String.raw`E:\Apps\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe`);
});

test("realDeps.processes: tasklist errors, timeouts and non-zero exits are \"unknown\" (null), never \"not running\"; it has a timeout", () => {
  let opts: { timeout?: number } = {};
  const run = (r: { error?: Error; status: number | null; stdout?: string }) =>
    di.realDeps({
      spawnSync: (_c, _a, o) => {
        opts = o;
        return r;
      },
    }).processes();
  assert.equal(run({ error: Object.assign(new Error("spawnSync tasklist ETIMEDOUT"), { code: "ETIMEDOUT" }), status: null, stdout: "" }), null);
  assert.ok(typeof opts.timeout === "number" && opts.timeout > 0 && opts.timeout <= 30_000, `timeout ${opts.timeout}`);
  assert.equal(run({ status: 1, stdout: "ERROR: something\r\n" }), null);
  assert.equal(run({ status: 0, stdout: "" }), null, "an empty process list is not believable");
  assert.deepEqual(run({ status: 0, stdout: '"Adobe Premiere Pro.exe","1","Console","1","9 K"\r\n' }), ["adobe premiere pro.exe"]);
});

test("realDeps.startCreativeCloud: the spawn's 'error' event (and a throw) mean not started; 'spawn' means started and unref'd", async () => {
  const child = (event: string, err?: Error) => {
    const e = Object.assign(new EventEmitter(), { unrefd: false, unref() { this.unrefd = true; } });
    setImmediate(() => (err ? e.emit(event, err) : e.emit(event)));
    return e;
  };
  const bad = di.realDeps({ exists: () => true, spawn: () => child("error", Object.assign(new Error("spawn EACCES"), { code: "EACCES" })) });
  assert.equal(await bad.startCreativeCloud(), false);
  let made: ReturnType<typeof child> | undefined;
  const good = di.realDeps({ exists: () => true, spawn: () => (made = child("spawn")) });
  assert.equal(await good.startCreativeCloud(), true);
  assert.equal(made!.unrefd, true);
  const thrown = di.realDeps({ exists: () => true, spawn: () => { throw new Error("boom"); } });
  assert.equal(await thrown.startCreativeCloud(), false);
  assert.equal(await di.realDeps({ exists: () => false }).startCreativeCloud(), false);
});

test("tempCcxPath: an ASCII-only file under the temp dir; a non-ASCII temp dir falls back to the fixed ASCII folder", () => {
  const a = di.tempCcxPath(TMP, DEV, 1234);
  assert.equal(a.dir, TMP);
  assert.ok(a.file.startsWith(TMP + "\\") && a.file.endsWith(".ccx"), a.file);
  const b = di.tempCcxPath(String.raw`C:\Users\يونس\AppData\Local\Temp`, { ...DEV, version: "3.0.0+ü/x" }, 1234);
  assert.equal(b.dir, di.ASCII_TMP_FALLBACK);
  assert.ok(b.file.startsWith(di.ASCII_TMP_FALLBACK + "\\"), b.file);
  for (const p of [a.file, b.file, di.ASCII_TMP_FALLBACK]) assert.match(p, /^[\x20-\x7e]+$/, p);
  assert.doesNotMatch(win32.basename(b.file), /[\\/]/);
});

// ---------------------------------------------------------------- the whole run

test("happy path: /list all -> /remove <installed name> -> /install <ASCII temp copy> -> verify; the temp copy is cleaned up -> exit 0", async () => {
  const w = world();
  const code = await di.devInstall(["WhyNotCut-Premiere-3.0.0.ccx"], deps(w));
  assert.equal(code, 0, w.err.join("\n"));
  const tmp = installArg(w)!;
  assert.ok(tmp.startsWith(TMP + "\\") && /^[\x20-\x7e]+$/.test(tmp), tmp);
  assert.deepEqual(w.calls, [["/list", "all"], ["/remove", "WhyNot Cut"], ["/install", tmp], ["/list", "all"]]);
  assert.deepEqual(w.removedFiles, [tmp]);
  assert.ok(!w.files.has(tmp));
  assert.deepEqual(w.err, []);
  assert.match(w.out.join("\n"), /installed and verified: "WhyNot Cut \(dev\)" 3\.0\.0 \(Enabled\), build 20261013T142530Z, sha 57d3211-dirty/);
  assert.ok(w.installed.has(SPIKE.pluginId), "the spike is left alone");
});

test("UPIA in id mode: /remove <name> does nothing, /remove <id> does it", async () => {
  const w = world({ removeBy: "id" });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 0, w.err.join("\n"));
  assert.deepEqual(mutating(w).slice(0, 2), [["/remove", "WhyNot Cut"], ["/remove", "ai.thewhynot.cut.dev"]]);
});

test("the installed name is shared with another id (the release panel): never removed by name; /remove <id> only, which fails -> exit 1", async () => {
  const w = world();
  w.installed.set("ai.thewhynot.cut", { info: { name: "WhyNot Cut", path: String.raw`$localPlugins\External\ai.thewhynot.cut_3.0.0`, pluginId: "ai.thewhynot.cut", versionString: "3.0.0" }, build: null });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err.join("\n"), /name "WhyNot Cut" is not unique/);
  assert.deepEqual(mutating(w), [["/remove", "ai.thewhynot.cut.dev"]]);
  assert.ok(w.installed.has("ai.thewhynot.cut"), "the release panel is untouched");
});

test("shared name + UPIA in id mode: /remove <id> removes only ours, the install goes on", async () => {
  const w = world({ removeBy: "id" });
  w.installed.set("ai.thewhynot.cut", { info: { name: "WhyNot Cut", path: String.raw`$localPlugins\External\ai.thewhynot.cut_3.0.0`, pluginId: "ai.thewhynot.cut", versionString: "3.0.0" }, build: null });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  assert.deepEqual(mutating(w)[0], ["/remove", "ai.thewhynot.cut.dev"]);
  assert.ok(w.installed.has("ai.thewhynot.cut"));
});

test("the name-fallback clash check counts /list all rows on every host, case-insensitively", async () => {
  for (const [label, name] of [["After Effects (ver 26.5.0)", "WhyNot Cut"], ["Photoshop 2026 64 (ver 27.11.0)", "whynot cut"], ["Premiere Pro (Beta) (ver 26.6.0)", "WHYNOT CUT"]] as const) {
    const w = world({ extraSections: [[label, [{ status: "Enabled", name, version: "1.0.0" }]]] });
    assert.equal(await di.devInstall([CCX], deps(w)), 1, label);
    assert.match(w.err.join("\n"), /not unique/, label);
    assert.ok(!w.calls.some((c) => c[0] === "/remove" && c[1]!.toLowerCase() === "whynot cut"), `never removed by name (${label})`);
  }
});

test("name prefixes are not the name, either way: \"WhyNot Cut Spike\" / \"WhyNot Cut (dev) Tools\" do not block removing \"WhyNot Cut\"", async () => {
  const w = world({ extraSections: [["After Effects (ver 26.5.0)", [{ status: "Enabled", name: "WhyNot Cut (dev) Tools", version: "1.0.0" }, { status: "Enabled", name: "WhyNot", version: "1.0.0" }]]] });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  assert.deepEqual(mutating(w)[0], ["/remove", "WhyNot Cut"]);
});

test("a remove that takes another plugin with it (snapshot before/after): loud WARNING naming it, exit 1, nothing installed", async () => {
  const w = world({ collateral: [SPIKE.pluginId] });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err.join("\n"), /^WARNING: UPIA \/remove "WhyNot Cut" also removed ai\.thewhynot\.cut\.spike \("WhyNot Cut Spike" 0\.1\.4\)/m);
  assert.ok(!w.calls.some((c) => c[0] === "/install"));
  assert.equal(w.removedFiles.length, 1, "the temp copy is still cleaned up");
});

test("C1: a non-release id named \"WhyNot Cut\" is refused before any UPIA call (exit 2)", async () => {
  const w = world();
  w.files.set(CCX, ccx({ ...DEV, name: "WhyNot Cut" }, PKG_BUILD));
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /release plugin's name/);
  assert.deepEqual(w.calls, []);
});

test("C1: the package name equals (any case) a premierepro.json plugin with another id -> exit 2 before any UPIA call", async () => {
  const w = world();
  w.installed.set("ai.thewhynot.cut.spike", { info: { ...SPIKE, name: "whynot cut (DEV)" }, build: null });
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /package name "WhyNot Cut \(dev\)" is also the name of .*ai\.thewhynot\.cut\.spike/);
  assert.deepEqual(w.calls, []);
});

test("C1: the package name equals (any case) a /list all plugin on any host -> exit 2 after the read-only /list all, before any /remove or /install", async () => {
  const w = world({ extraSections: [["After Effects (ver 26.5.0)", [{ status: "Enabled", name: "WHYNOT CUT (DEV)", version: "9.9.9" }]]] });
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /package name "WhyNot Cut \(dev\)" is also the name of .*After Effects/);
  assert.deepEqual(w.calls, [["/list", "all"]]);
});

test("C1: our own installed row with the package name is not a clash; a second Premiere row with it is", async () => {
  const w = world();
  w.installed.set(DEV.id, { info: { ...DEV_AS_PRODUCT, name: "WhyNot Cut (dev)" }, build: OLD_BUILD });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  const w2 = world({ listOverride: listAll([["Premiere Pro (ver 26.5.2)", [{ status: "Enabled", name: "WhyNot Cut (dev)", version: "3.0.0" }, { status: "Enabled", name: "WhyNot Cut (dev)", version: "2.0.0" }]]]) });
  w2.installed.set(DEV.id, { info: { ...DEV_AS_PRODUCT, name: "WhyNot Cut (dev)" }, build: OLD_BUILD });
  assert.equal(await di.devInstall([CCX], deps(w2)), 2);
  assert.match(w2.err[0]!, /also the name of/);
  assert.deepEqual(mutating(w2), []);
});

test("--release while the dev id is installed as \"WhyNot Cut\": refused before any UPIA call (it would collide by name)", async () => {
  const w = world();
  w.files.set(CCX, ccx(REL, PKG_BUILD));
  assert.equal(await di.devInstall([CCX, "--release"], deps(w)), 2);
  assert.match(w.err[0]!, /also the name of .*ai\.thewhynot\.cut\.dev/);
  assert.deepEqual(w.calls, []);
});

test("release id: refused without --release (exit 2, UPIA never called); installed over the release with --release", async () => {
  const w = world();
  w.files.set(CCX, ccx(REL, PKG_BUILD));
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /release id ai\.thewhynot\.cut; add --release/);
  assert.deepEqual(w.calls, []);
  const w2 = world();
  w2.installed.delete(DEV.id);
  w2.installed.set(REL.id, { info: { name: "WhyNot Cut", path: String.raw`$localPlugins\External\ai.thewhynot.cut_2.9.0`, pluginId: REL.id, versionString: "2.9.0" }, build: OLD_BUILD });
  w2.files.set(CCX, ccx(REL, PKG_BUILD));
  assert.equal(await di.devInstall([CCX, "--release"], deps(w2)), 0, w2.err.join("\n"));
  assert.deepEqual(mutating(w2)[0], ["/remove", "WhyNot Cut"]);
});

test("PluginsInfo is late: polled (injected clock) until the remove and the install show, within 15 s -> exit 0", async () => {
  const w = world({ infoLagMs: 4_000, listLagMs: 3_000 });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  assert.ok(w.slept >= 8_000 && w.slept < 30_000, `slept ${w.slept}`);
});

test("PluginsInfo never shows the remove within 15 s: exit 1 before any install", async () => {
  const w = world({ infoLagMs: 60_000 });
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.match(w.err.join("\n"), /UPIA did not remove ai\.thewhynot\.cut\.dev \("WhyNot Cut" 3\.0\.0 is still installed/);
  // 15 s after /remove <name>, then 15 s after the /remove <id> fallback
  assert.deepEqual(mutating(w), [["/remove", "WhyNot Cut"], ["/remove", "ai.thewhynot.cut.dev"]]);
  assert.ok(w.slept >= 30_000 && w.slept < 33_000, `slept ${w.slept}`);
  assert.ok(!w.calls.some((c) => c[0] === "/install"));
});

test("PluginsInfo never shows the install within 15 s: exit 1 after polling", async () => {
  const w = world({ infoLagMs: 0 });
  w.installed.delete(DEV.id);
  w.installOutput = (x) => {
    x.infoLagMs = 60_000;
    return "Installation Successful\r\n";
  };
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.match(w.err[0]!, /has no entry for ai\.thewhynot\.cut\.dev/);
  assert.ok(w.slept >= 15_000, `slept ${w.slept}`);
});

test("UPIA exits 0 but the output has no \"Installation Successful\" (status = -642): exit 1; it says the old one was removed and the one step", async () => {
  const w = world({ installOutput: () => "Failed to install extension, status = -642\r\n" });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  const msg = w.err.join("\n");
  assert.match(msg, /^Install failed: UPIA reported status = -642 \(Creative Cloud is not running or not ready\) \(UPIA exit code 0\)\./);
  assert.match(msg, /"WhyNot Cut" 3\.0\.0 \(ai\.thewhynot\.cut\.dev\) was removed/);
  assert.ok(msg.includes(`double-click ${CCX}`), msg);
  assert.deepEqual(mutating(w).map((c) => c[0]), ["/remove", "/install"]);
  assert.equal(w.removedFiles.length, 1, "the temp copy is cleaned up after a failure too");
});

test("install fails with nothing installed before: no \"was removed\" claim", async () => {
  const w = world({ installOutput: () => "Failed to install extension, status = -402\r\n" });
  w.installed.delete(DEV.id);
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.doesNotMatch(w.err.join("\n"), /was removed/);
  assert.deepEqual(mutating(w).map((c) => c[0]), ["/install"]);
});

test("\"Installation Successful\" but /list all does not show the name and version: exit 1", async () => {
  const w = world({ listOverride: LIST_ALL });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err[0]!, /UPIA \/list all shows "WhyNot Cut" 3\.0\.0, "WhyNot Cut Spike" 0\.1\.4 for Premiere Pro, not "WhyNot Cut \(dev\)" 3\.0\.0/);
});

test("listed only under Premiere Pro (Beta): not accepted, and the Beta listing is reported", async () => {
  const beta = listAll([["Premiere Pro (ver 26.5.2)", [{ status: "Enabled", name: "WhyNot Cut Spike", version: "0.1.4" }]], ["Premiere Pro (Beta) (ver 26.6.0)", [{ status: "Enabled", name: "WhyNot Cut (dev)", version: "3.0.0" }]]]);
  const w = world();
  // before the install the real list (so the clash check passes), after it the Beta-only one
  w.installOutput = (x) => {
    x.listOverride = beta;
    return "Installation Successful\r\n";
  };
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.match(w.err[0]!, /not "WhyNot Cut \(dev\)" 3\.0\.0/);
  assert.match(w.err[0]!, /Premiere Pro \(Beta\)/);
});

test("same-version trap: installed build.json is the old build -> exit 1 naming both builds", async () => {
  const w = world({ installedBuild: OLD_BUILD });
  const code = await di.devInstall([CCX], deps(w));
  assert.equal(code, 1);
  assert.match(w.err[0]!, /installed build\.json is 3\.0\.0 build 20261012T101010Z sha 6961ccf, the package is 3\.0\.0 build 20261013T142530Z sha 57d3211-dirty/);
});

test("installed build.json: BOM + CRLF is read; malformed or missing is exit 1", async () => {
  const w = world({ installedBuild: `\uFEFF{\r\n  "product": "3.0.0",\r\n  "build": "20261013T142530Z",\r\n  "sha": "57d3211-dirty"\r\n}\r\n` });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  const w2 = world({ installedBuild: '{"product": "3.0.0", "build": ' });
  assert.equal(await di.devInstall([CCX], deps(w2)), 1);
  assert.match(w2.err[0]!, /build\.json is missing or unreadable/);
  const w3 = world({ installedBuild: null });
  assert.equal(await di.devInstall([CCX], deps(w3)), 1);
  assert.match(w3.err[0]!, /build\.json is missing or unreadable/);
});

test("same sha but a different build id still fails: build AND sha must equal the packaged ones", async () => {
  const w = world({ installedBuild: { ...PKG_BUILD, build: "20261013T000000Z" } });
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
});

test("nothing removes it: exit 1 before any install", async () => {
  const w = world({ removeBy: "never" });
  assert.equal(await di.devInstall([CCX], deps(w)), 1);
  assert.match(w.err[0]!, /UPIA did not remove ai\.thewhynot\.cut\.dev \("WhyNot Cut" 3\.0\.0 is still installed/);
  assert.ok(!w.calls.some((c) => c[0] === "/install"));
});

test("Premiere Pro is running: refused before anything (exit 2) unless --force, which warns and goes on", async () => {
  const w = world({ procs: ["explorer.exe", "creative cloud.exe", "adobe premiere pro.exe"] });
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /Premiere Pro is running.*--force/);
  assert.deepEqual(w.calls, []);
  assert.deepEqual(w.removedFiles, []);
  const w2 = world({ procs: ["explorer.exe", "creative cloud.exe", "adobe premiere pro.exe"] });
  assert.equal(await di.devInstall([CCX, "--force"], deps(w2)), 0, w2.err.join("\n"));
  assert.match(w2.out[0]!, /Premiere Pro is running \(--force\)/);
});

test("tasklist unknown (error / non-zero / timeout): exit 2 with that reason, never treated as \"not running\"", async () => {
  const w = world({ procs: null });
  assert.equal(await di.devInstall([CCX], deps(w)), 2);
  assert.match(w.err[0]!, /Cannot tell whether Premiere Pro or Creative Cloud is running/);
  assert.deepEqual(w.calls, []);
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

test("spike ccx installs (its id is fine), first install with nothing to remove", async () => {
  const w = world();
  w.installed.delete(SPIKE.pluginId);
  w.files.set(CCX, ccx({ id: "ai.thewhynot.cut.spike", name: "WhyNot Cut Spike", version: "0.1.6" }, { product: "0.1.6", build: "20261013T142530Z", sha: "57d3211" }));
  w.installedBuild = { product: "0.1.6", build: "20261013T142530Z", sha: "57d3211" };
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  assert.match(w.out.join("\n"), /ai\.thewhynot\.cut\.spike is not installed/);
  assert.deepEqual(mutating(w).map((c) => c[0]), ["/install"]);
});

test("a non-ASCII temp dir: the ccx is copied to the ASCII fallback folder (created) and removed afterwards", async () => {
  const w = world({ tmpdir: String.raw`C:\Users\يونس\AppData\Local\Temp` });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
  const tmp = installArg(w)!;
  assert.ok(tmp.startsWith(di.ASCII_TMP_FALLBACK + "\\"), tmp);
  assert.deepEqual(w.dirs, [di.ASCII_TMP_FALLBACK]);
  assert.deepEqual(w.removedFiles, [tmp]);
});

test("start-up refusals exit 2 with one line and no UPIA call: args, Windows, APPDATA, ccx, ids, UPIA, premierepro.json, temp copy", async () => {
  const cases: [string, string[], Partial<Deps>, (w: World) => void, RegExp][] = [
    ["no args", [], {}, () => {}, /^usage: npm run dev-install -- <path to \.ccx> \[--release\] \[--force\]$/],
    ["unknown flag", [CCX, "--bogus"], {}, () => {}, /^Unknown argument --bogus/],
    ["not Windows", [CCX], { platform: "darwin" }, () => {}, /Windows only/],
    ["APPDATA unset", [CCX], { env: {} }, () => {}, /APPDATA is not set to an absolute path/],
    ["APPDATA relative", [CCX], { env: { APPDATA: "AppData\\Roaming" } }, () => {}, /APPDATA is not set to an absolute path/],
    ["APPDATA rooted, no drive", [CCX], { env: { APPDATA: "\\Users\\Ed" } }, () => {}, /APPDATA is not set to an absolute path/],
    ["missing ccx", [String.raw`D:\work\missing.ccx`], {}, () => {}, /missing\.ccx: it does not exist\.$/],
    ["no build.json", [CCX], {}, (w) => void w.files.set(CCX, ccx(DEV, null)), /no build\.json; package it with npm run package:plugin/],
    ["tools id", [CCX], {}, (w) => void w.files.set(CCX, ccx({ ...DEV, id: "ai.thewhynot.cut.tools" }, PKG_BUILD)), /not a dev or spike id/],
    ["no UPIA", [CCX], { exists: (p) => p === INFO }, () => {}, /UPIA\) is not at /],
    ["no premierepro.json", [CCX], {}, (w) => void (w.infoExists = false), /premierepro\.json does not exist; open Premiere Pro once/],
    ["malformed premierepro.json", [CCX], {}, (w) => void (w.infoRaw = '{"plugins": ['), /Cannot read .*premierepro\.json/],
    ["premierepro.json without plugins", [CCX], {}, (w) => void (w.infoRaw = "{}"), /Cannot read .*premierepro\.json/],
    ["copy fails", [CCX], { copyFile: () => { throw new Error("EACCES: denied"); } }, () => {}, /Cannot copy the \.ccx to .*EACCES/],
  ];
  for (const [what, argv, over, setup, re] of cases) {
    const w = world();
    setup(w);
    assert.equal(await di.devInstall(argv, deps(w, over)), 2, what);
    assert.equal(w.err.length, 1, `${what}: ${w.err.join(" | ")}`);
    assert.match(w.err[0]!, re, what);
    assert.deepEqual(w.calls, [], what);
  }
});

test("premierepro.json with a BOM (Premiere writes one at times) is read before and after every UPIA call", async () => {
  const w = world({ infoBom: true });
  assert.equal(await di.devInstall([CCX], deps(w)), 0, w.err.join("\n"));
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
