// Install a packaged .ccx on this Windows PC and prove it landed: UPIA /remove -> /install -> verify.
//   npm run dev-install -- <path\to\plugin.ccx> [--release] [--force]          (from adobe/)
//   node premiere-uxp/scripts/dev-install.mjs <ccx> [--release] [--force]
//
// Why (Addendum C §3.3/§3.4, docs/adobe/uxp-parity.md): UPIA exits 0 even when it fails (Creative Cloud not running ->
// "status = -642"), and a same-version install reports "Installation Successful" but keeps the old files. So this
// removes first, installs, then checks three things and exits non-zero unless all hold:
//   1. the /install output contains "Installation Successful";
//   2. `/list all` lists the plugin's name and version under Premiere Pro (UPIA lists names, not ids);
//   3. the installed folder's build.json (found through %APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json) has the
//      packaged build.json's product, build and sha.
// PluginsInfo and /list all are written after UPIA returns, so both are polled for up to 15 s before deciding.
//
// UPIA works by NAME ("/remove <extension-name>"; /list all shows no ids), so names are guarded before anything
// changes: a non-release id may not be called "WhyNot Cut"; the package name may not be the name of any other plugin
// (premierepro.json, or /list all on any host, any case); and an installed plugin is removed by name only when exactly
// one /list all row and one premierepro.json entry carry that name. premierepro.json is snapshotted around every
// remove: if any other plugin disappeared, that is reported loudly and nothing is installed.
//
// Exit codes: 0 installed and verified; 1 UPIA failed or a check did not hold; 2 refused or could not start (usage, not
// Windows, APPDATA, no UPIA, no premierepro.json, Premiere running without --force, process list unknown, Creative
// Cloud not running, refused id or name, not a packaged .ccx, temp copy failed).
//
// Every side effect goes through `deps` (UPIA runner, files, process list, Creative Cloud start, clock, temp copy,
// output), so the tests drive it with fixtures and never install anything.
import { unzipSync } from "fflate";
import { spawn as nodeSpawn, spawnSync as nodeSpawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir as osTmpdir } from "node:os";
import { resolve, win32 } from "node:path";
import { pathToFileURL } from "node:url";
import { DEV_ID, RELEASE_ID, RELEASE_NAME, SPIKE_ID } from "./ids.mjs";

const DEFAULT_PROGRAM_FILES = String.raw`C:\Program Files`;
const UPIA_REL = String.raw`Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe`;
const CC_REL = String.raw`Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe`;
export const UPIA_PATH = win32.join(DEFAULT_PROGRAM_FILES, "Common Files", UPIA_REL);
export const CREATIVE_CLOUD_EXE = win32.join(DEFAULT_PROGRAM_FILES, CC_REL);
/** Where the .ccx is copied for /install when the temp dir's path is not plain ASCII (UPIA and non-ASCII paths). */
export const ASCII_TMP_FALLBACK = String.raw`C:\Users\Public\WhyNotCut-dev-install`;
/** Every WhyNot Cut UXP id: the release id itself, or `ai.thewhynot.cut.<something>`. */
const ID_FAMILY = /^ai\.thewhynot\.cut(\.[a-z0-9-]+)*$/;
/** The `/list all` section that is Premiere Pro itself ("Premiere Pro (ver 26.5.2)"), not "Premiere Pro (Beta)". */
const PREMIERE_HOST = /^Premiere Pro(\s*\(ver|$)/;
const CC_PROCESS = "creative cloud.exe";
const PREMIERE_PROCESS = "adobe premiere pro.exe";
const CC_WAIT_MS = 60_000;
const CC_POLL_MS = 2_000;
const CC_SETTLE_MS = 5_000;
const POLL_MS = 1_000;
const POLL_LIMIT_MS = 15_000;
const TASKLIST_TIMEOUT_MS = 15_000;

export const USAGE = "usage: npm run dev-install -- <path to .ccx> [--release] [--force]";

export function parseArgs(argv) {
  const out = { ccx: undefined, release: false, force: false, help: false, unknown: [] };
  for (const a of argv) {
    if (a === "--release") out.release = true;
    else if (a === "--force") out.force = true;
    else if (a === "--help" || a === "-h") out.help = true;
    else if (a.startsWith("-")) out.unknown.push(a);
    else if (out.ccx === undefined) out.ccx = a;
    else out.unknown.push(a);
  }
  return out;
}

/** A drive path (C:\...) or a UNC path (\\server\share\...): what %APPDATA% and %ProgramFiles% must be. */
function fullyQualified(p) {
  return typeof p === "string" && (/^[A-Za-z]:[\\/]/.test(p) || /^\\\\[^\\/]+[\\/][^\\/]+/.test(p));
}

/** UPIA and Creative Cloud from %CommonProgramFiles% / %ProgramFiles%, falling back to C:\Program Files. */
export function adobePaths(env) {
  const programFiles = fullyQualified(env.ProgramFiles) ? env.ProgramFiles : DEFAULT_PROGRAM_FILES;
  const common = fullyQualified(env.CommonProgramFiles) ? env.CommonProgramFiles : win32.join(programFiles, "Common Files");
  return { upia: win32.join(common, UPIA_REL), creativeCloud: win32.join(programFiles, CC_REL) };
}

/** %APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json: the list of installed UXP plugins Premiere reads. */
export function pluginsInfoPath(env) {
  return win32.join(env.APPDATA ?? "", "Adobe", "UXP", "PluginsInfo", "v1", "premierepro.json");
}

/** What `$localPlugins` in a PluginsInfo `path` stands for (seen on this PC: `$localPlugins\External\<id>_<version>`
 *  is the folder %APPDATA%\Adobe\UXP\Plugins\External\<id>_<version>). */
export function localPluginsDir(env) {
  return win32.join(env.APPDATA ?? "", "Adobe", "UXP", "Plugins");
}

/** PluginsInfo shape (premierepro.json on this PC, 2026-10-13): {"plugins":[{hostMinVersion, name, path, pluginId,
 *  status, type, versionString}]}. Returns the plugins array; throws on anything else. */
export function parsePluginsInfo(text) {
  const doc = JSON.parse(stripBom(text));
  if (!doc || !Array.isArray(doc.plugins)) throw new Error("no \"plugins\" array");
  return doc.plugins.filter((p) => p && typeof p.pluginId === "string");
}

export function resolvePluginPath(path, env) {
  const m = /^\$localPlugins[\\/](.+)$/.exec(String(path));
  if (m) return win32.join(localPluginsDir(env), ...m[1].split(/[\\/]+/));
  if (/^[A-Za-z]:[\\/]/.test(String(path))) return win32.normalize(path);
  throw new Error(`unknown plugin path form "${path}"`);
}

/** `UPIA /list all`: per product, "N extension(s) installed for <product> (ver <v>)", a header, a ==== rule, then rows
 *  " <Status>    <Extension Name>    <Version>". Status and name are split by 2+ spaces (either may hold single
 *  spaces); the version is the last token, so an over-wide name with one space before the version still parses. */
export function parseUpiaList(text) {
  const out = [];
  let host = null;
  let hostVersion = null;
  for (const raw of String(text).split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, "");
    const head = /^\d+ extensions? installed for (.+?)(?: \(ver ([^)]+)\))?$/.exec(line);
    if (head) {
      host = head[1];
      hostVersion = head[2] ?? null;
      continue;
    }
    if (!host || !line.trim() || /^=+[\s=]*$/.test(line) || /^\s*Status\s{2,}Extension Name\s{2,}Version$/.test(line)) continue;
    const row = /^\s*(\S+(?: \S+)*)\s{2,}(.+?)\s+(\S+)$/.exec(line);
    if (row) out.push({ host, hostVersion, status: row[1], name: row[2], version: row[3] });
  }
  return out;
}

/** The section label as UPIA printed it ("Premiere Pro (ver 26.5.2)"). */
function hostLabel(row) {
  return row.hostVersion ? `${row.host} (ver ${row.hostVersion})` : row.host;
}

/** True for rows in Premiere Pro's own section; "Premiere Pro (Beta)" and look-alikes are not it. */
export function isPremiereRow(row) {
  return PREMIERE_HOST.test(hostLabel(row));
}

/** Product sections in a `/list all` output (0 when UPIA printed none, e.g. Creative Cloud not ready). */
function upiaSections(text) {
  return String(text).split(/\r?\n/).filter((l) => /^\d+ extensions? installed for /.test(l)).length;
}

export function installSucceeded(output) {
  return String(output).includes("Installation Successful");
}

/** One line saying why an /install did not succeed: the UPIA status code when there is one, else its last line. */
export function upiaFailure(output) {
  const text = String(output);
  const status = /status\s*=\s*(-?\d+)/i.exec(text);
  if (status) {
    const hint = status[1] === "-642" ? " (Creative Cloud is not running or not ready)" : "";
    return `UPIA reported status = ${status[1]}${hint}`;
  }
  const last = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).pop();
  return last ? `UPIA said: ${last}` : "UPIA printed nothing";
}

/** Image names from `tasklist /FO CSV /NH`, lower-cased. */
export function parseTasklist(csv) {
  return String(csv)
    .split(/\r?\n/)
    .map((l) => /^"([^"]+)"/.exec(l)?.[1]?.toLowerCase())
    .filter(Boolean);
}

/** manifest.json and build.json from a .ccx (a zip). */
export function readCcx(bytes) {
  let files;
  try {
    files = unzipSync(new Uint8Array(bytes));
  } catch {
    throw new Error("it is not a .ccx (not a zip file)");
  }
  const text = (n) => (files[n] ? new TextDecoder().decode(files[n]) : undefined);
  const m = text("manifest.json");
  if (m === undefined) throw new Error("it is not a .ccx (no manifest.json at its root)");
  const b = text("build.json");
  if (b === undefined) throw new Error("it has no build.json; package it with npm run package:plugin (or package:spike) first");
  const manifest = JSON.parse(stripBom(m));
  const build = JSON.parse(stripBom(b));
  for (const k of ["id", "name", "version"]) if (typeof manifest[k] !== "string") throw new Error(`its manifest.json has no ${k}`);
  for (const k of ["product", "build", "sha"]) if (typeof build[k] !== "string") throw new Error(`its build.json has no ${k}`);
  return { manifest, build };
}

/** null when the id may be installed, else the one-sentence refusal. Only the dev and spike ids, or the release id
 *  with --release. */
export function idRefusal(id, release) {
  if (!ID_FAMILY.test(id)) return `"${id}" is not a WhyNot Cut plugin id, so dev-install will not install it.`;
  if (id === RELEASE_ID) return release ? null : `This .ccx has the release id ${RELEASE_ID}; add --release to install it on purpose.`;
  if (id === DEV_ID || id === SPIKE_ID) return null;
  return `${id} is not a dev or spike id; dev-install installs only ${DEV_ID}, ${SPIKE_ID} or (with --release) ${RELEASE_ID}.`;
}

const nameKey = (s) => String(s).trim().toLowerCase();

/** null unless a non-release id carries the release name "WhyNot Cut" (any case, surrounding spaces ignored). */
export function nameRefusal(manifest) {
  if (manifest.id === RELEASE_ID || nameKey(manifest.name) !== nameKey(RELEASE_NAME)) return null;
  return `The package is named "${manifest.name}", the release plugin's name, but its id is ${manifest.id}; UPIA lists and removes plugins by name, so it could replace or remove the release panel. Package it again with npm run package:plugin (a dev build is named "... (dev)").`;
}

/** The ASCII-only path the .ccx is copied to for /install: under the temp dir, or the fixed ASCII folder when the temp
 *  dir's path is not plain ASCII. */
export function tempCcxPath(tmp, manifest, now) {
  const ascii = (s) => /^[\x20-\x7e]+$/.test(s);
  const dir = ascii(String(tmp)) && fullyQualified(tmp) ? String(tmp).replace(/[\\/]+$/, "") : ASCII_TMP_FALLBACK;
  const safe = (s) => String(s).replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 60) || "x";
  return { dir, file: win32.join(dir, `whynotcut-dev-install-${safe(manifest.id)}-${safe(manifest.version)}-${Math.floor(now)}.ccx`) };
}

/** The real side effects. `sys` overrides node's spawn / spawnSync / existsSync / env (tests only). */
export function realDeps(sys = {}) {
  const env = sys.env ?? process.env;
  const spawn = sys.spawn ?? nodeSpawn;
  const spawnSync = sys.spawnSync ?? nodeSpawnSync;
  const exists = sys.exists ?? existsSync;
  const paths = adobePaths(env);
  return {
    platform: sys.platform ?? process.platform,
    env,
    cwd: env.INIT_CWD || process.cwd(),
    upiaPath: paths.upia,
    creativeCloudExe: paths.creativeCloud,
    runUpia(args) {
      const r = spawnSync(paths.upia, args, { encoding: "utf8", windowsHide: true, timeout: 180_000 });
      if (r.error) return { status: null, output: String(r.error.message) };
      return { status: r.status, output: `${r.stdout ?? ""}${r.stderr ?? ""}` };
    },
    readFile: (p) => readFileSync(p),
    exists: (p) => exists(p),
    /** Lower-cased image names, or null when the list is unknown (tasklist failed, timed out or printed nothing). */
    processes() {
      const r = spawnSync("tasklist", ["/FO", "CSV", "/NH"], { encoding: "utf8", windowsHide: true, timeout: TASKLIST_TIMEOUT_MS });
      if (r.error || r.status !== 0) return null;
      const names = parseTasklist(r.stdout ?? "");
      return names.length ? names : null;
    },
    startCreativeCloud() {
      if (!exists(paths.creativeCloud)) return Promise.resolve(false);
      return new Promise((done) => {
        try {
          const child = spawn(paths.creativeCloud, [], { detached: true, stdio: "ignore", windowsHide: false });
          child.once("error", () => done(false));
          child.once("spawn", () => {
            child.unref();
            done(true);
          });
        } catch {
          done(false);
        }
      });
    },
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    now: () => Date.now(),
    tmpdir: () => osTmpdir(),
    mkdir: (p) => void mkdirSync(p, { recursive: true }),
    copyFile: (src, dst) => copyFileSync(src, dst),
    removeFile: (p) => rmSync(p, { force: true }),
    out: (line) => console.log(line),
    err: (line) => console.error(line),
  };
}

/** "ok", "failed" (not running and could not be started) or "unknown" (process list unreadable). */
async function ensureCreativeCloud(deps) {
  const procs = deps.processes();
  if (procs === null) return "unknown";
  if (procs.includes(CC_PROCESS)) return "ok";
  deps.out("Creative Cloud is not running; starting it ...");
  if (!(await deps.startCreativeCloud())) return "failed";
  for (let waited = 0; waited < CC_WAIT_MS; waited += CC_POLL_MS) {
    await deps.sleep(CC_POLL_MS);
    const now = deps.processes();
    if (now === null) return "unknown";
    if (now.includes(CC_PROCESS)) {
      // UPIA talks to Creative Cloud's services; give them a moment after the window process appears
      await deps.sleep(CC_SETTLE_MS);
      return "ok";
    }
  }
  return "failed";
}

/** Calls `check` until it returns a value or 15 s pass on the injected clock; returns the last value (or undefined). */
async function poll(deps, check) {
  const start = deps.now();
  for (;;) {
    const got = check();
    if (got.done || deps.now() - start >= POLL_LIMIT_MS) return got;
    await deps.sleep(POLL_MS);
  }
}

const UNKNOWN_PROCS = "Cannot tell whether Premiere Pro or Creative Cloud is running (tasklist failed or timed out); run this again.";

/** Runs the whole remove -> install -> verify sequence. Returns the exit code. */
export async function devInstall(argv, deps = realDeps()) {
  const fail = (code, line) => {
    deps.err(line);
    return code;
  };
  const args = parseArgs(argv);
  if (args.help) {
    deps.out(USAGE);
    return 0;
  }
  if (!args.ccx || args.unknown.length) return fail(2, args.unknown.length ? `Unknown argument ${args.unknown[0]}; ${USAGE}` : USAGE);
  if (deps.platform !== "win32") return fail(2, "dev-install runs on Windows only (it drives Adobe's UPIA installer at its Windows path).");
  if (!fullyQualified(deps.env.APPDATA)) return fail(2, "APPDATA is not set to an absolute path, so premierepro.json (the installed-plugin list) cannot be found; run this from a normal Windows session.");

  // ---- the package, its id and its name (no UPIA call yet)
  const ccx = resolve(deps.cwd, args.ccx);
  let pkg;
  try {
    pkg = readCcx(deps.readFile(ccx));
  } catch (e) {
    const why = e && e.code === "ENOENT" ? "it does not exist" : e instanceof Error ? e.message : String(e);
    return fail(2, `Cannot install ${ccx}: ${why}.`);
  }
  const { manifest, build } = pkg;
  const refusal = idRefusal(manifest.id, args.release) ?? nameRefusal(manifest);
  if (refusal) return fail(2, refusal);
  if (!deps.exists(deps.upiaPath)) return fail(2, `Adobe's installer agent (UPIA) is not at ${deps.upiaPath}; install or repair Creative Cloud first.`);

  // ---- premierepro.json must exist and parse before anything changes
  const infoPath = pluginsInfoPath(deps.env);
  if (!deps.exists(infoPath)) return fail(2, `${infoPath} does not exist; open Premiere Pro once so it creates its plugin list, close it, then run this again.`);
  /** The installed plugins, or null when premierepro.json cannot be read (Premiere may be rewriting it). */
  const readInfo = () => {
    try {
      return parsePluginsInfo(String(deps.readFile(infoPath)));
    } catch {
      return null;
    }
  };
  let initial;
  try {
    initial = parsePluginsInfo(String(deps.readFile(infoPath)));
  } catch (e) {
    return fail(2, `Cannot read ${infoPath} (${e instanceof Error ? e.message : e}); open and close Premiere Pro once, then run this again.`);
  }
  const entryFor = (plugins) => plugins.find((p) => p.pluginId === manifest.id);
  const pkgKey = nameKey(manifest.name);
  const infoClash = initial.filter((p) => p.pluginId !== manifest.id && nameKey(p.name) === pkgKey);
  if (infoClash.length) {
    const who = infoClash.map((p) => `"${p.name}" (${p.pluginId}, in premierepro.json)`).join(", ");
    return fail(2, `Refusing to install: the package name "${manifest.name}" is also the name of ${who}; UPIA works by name, so installing or removing it could hit that plugin. Remove that plugin in Creative Cloud (or rename the package) first.`);
  }

  // ---- Premiere and Creative Cloud
  const procs = deps.processes();
  if (procs === null) return fail(2, UNKNOWN_PROCS);
  const premiereOpen = procs.includes(PREMIERE_PROCESS);
  if (premiereOpen && !args.force) return fail(2, "Premiere Pro is running. Close it and run this again (or add --force to install anyway, then restart Premiere Pro).");
  if (premiereOpen) deps.out("warning: Premiere Pro is running (--force); restart it after the install to load this build.");
  const cc = await ensureCreativeCloud(deps);
  if (cc === "unknown") return fail(2, UNKNOWN_PROCS);
  if (cc !== "ok") return fail(2, "Creative Cloud is not running and could not be started; open Creative Cloud, then run this again.");

  // ---- an ASCII-only copy of the .ccx for UPIA
  const tmp = tempCcxPath(deps.tmpdir(), manifest, deps.now());
  try {
    if (tmp.dir === ASCII_TMP_FALLBACK) deps.mkdir(tmp.dir);
    deps.copyFile(ccx, tmp.file);
  } catch (e) {
    try {
      deps.removeFile(tmp.file);
    } catch {}
    return fail(2, `Cannot copy the .ccx to ${tmp.file}: ${e instanceof Error ? e.message : e}.`);
  }
  try {
    return await removeInstallVerify({ deps, fail, ccx, tmpFile: tmp.file, manifest, build, infoPath, readInfo, entryFor, initial });
  } finally {
    try {
      deps.removeFile(tmp.file);
    } catch {}
  }
}

async function removeInstallVerify({ deps, fail, ccx, tmpFile, manifest, build, infoPath, readInfo, entryFor, initial }) {
  const pkgKey = nameKey(manifest.name);
  const listAll = () => {
    const r = deps.runUpia(["/list", "all"]);
    return { output: r.output, rows: parseUpiaList(r.output), sections: upiaSections(r.output) };
  };

  // ---- C1: the package name must not be another plugin's name on any host (/list all is read-only)
  const first = listAll();
  if (!first.sections) return fail(2, `UPIA /list all listed no products (${upiaFailure(first.output)}), so the plugin names cannot be checked; open Creative Cloud, then run this again.`);
  const before = entryFor(initial);
  const ours = (rows) => rows.filter((r) => nameKey(r.name) === pkgKey);
  {
    const same = ours(first.rows);
    const premiereSame = same.filter(isPremiereRow);
    const mine = before && nameKey(before.name) === pkgKey ? 1 : 0;
    const clash = [...same.filter((r) => !isPremiereRow(r)), ...(premiereSame.length > mine ? premiereSame : [])];
    if (clash.length) {
      const who = clash.map((r) => `"${r.name}" ${r.version} (${hostLabel(r)}, in UPIA /list all)`).join(", ");
      return fail(2, `Refusing to install: the package name "${manifest.name}" is also the name of ${who}; UPIA works by name, so installing or removing it could hit that plugin. Remove that plugin in Creative Cloud (or rename the package) first.`);
    }
  }

  // ---- 1. remove (a same-version install would otherwise keep the old files)
  let removed = false;
  if (!before) {
    deps.out(`${manifest.id} is not installed; nothing to remove`);
  } else {
    deps.out(`removing ${manifest.id} (installed: "${before.name}" ${before.versionString})`);
    const key = nameKey(before.name);
    const listCount = first.rows.filter((r) => nameKey(r.name) === key).length;
    const infoCount = initial.filter((p) => nameKey(p.name) === key).length;
    const nameIsOurs = listCount === 1 && infoCount === 1;
    // Adobe's documented form is /remove <extension-name>; by name only when exactly one plugin has that name.
    const attempts = nameIsOurs ? [before.name, manifest.id] : [manifest.id];
    let left = before;
    for (const target of attempts) {
      const snapshot = readInfo() ?? initial;
      const r = deps.runUpia(["/remove", target]);
      deps.out(`  UPIA /remove "${target}": ${lastLine(r.output)}`);
      const got = await poll(deps, () => {
        const now = readInfo();
        if (!now) return { done: false, now };
        const lost = snapshot.filter((p) => p.pluginId !== manifest.id && !now.some((x) => x.pluginId === p.pluginId));
        return { done: lost.length > 0 || !entryFor(now), now, lost };
      });
      if (!got.now) return fail(1, `Cannot read ${infoPath} after UPIA /remove "${target}", so it is unknown what was removed; check Window > UXP Plugins in Premiere Pro, then run this again.`);
      if (got.lost.length) {
        const who = got.lost.map((p) => `${p.pluginId} ("${p.name}" ${p.versionString})`).join(", ");
        return fail(1, `WARNING: UPIA /remove "${target}" also removed ${who}: it is gone from ${infoPath}. Reinstall it (double-click its .ccx). Nothing was installed.`);
      }
      left = entryFor(got.now);
      if (!left) break;
    }
    if (left) {
      if (!nameIsOurs) return fail(1, `UPIA did not remove ${manifest.id} by its id, and its name "${before.name}" is not unique (UPIA /list all: ${listCount} matching rows, premierepro.json: ${infoCount} entries), so dev-install will not remove it by name; remove it in Creative Cloud, then run this again.`);
      return fail(1, `UPIA did not remove ${manifest.id} ("${left.name}" ${left.versionString} is still installed after ${POLL_LIMIT_MS / 1000} s); remove it in Creative Cloud, then run this again.`);
    }
    removed = true;
  }

  // ---- 2. install (from the ASCII temp copy)
  deps.out(`installing ${ccx}`);
  const ins = deps.runUpia(["/install", tmpFile]);
  deps.out(`  UPIA /install: ${lastLine(ins.output)}`);
  if (!installSucceeded(ins.output)) {
    const was = removed ? ` The old "${before.name}" ${before.versionString} (${manifest.id}) was removed and this build is not installed: to install it, double-click ${ccx}.` : "";
    return fail(1, `Install failed: ${upiaFailure(ins.output)} (UPIA exit code ${ins.status}).${was}`);
  }

  // ---- 3a/3b. /list all shows the name and version under Premiere Pro; premierepro.json lists the id and version
  const res = await poll(deps, () => {
    const list = listAll();
    const premiere = list.rows.filter(isPremiereRow);
    const row = premiere.find((r) => r.name.trim() === manifest.name.trim() && r.version === manifest.version);
    const plugins = readInfo();
    const entry = plugins ? entryFor(plugins) : undefined;
    return { done: Boolean(row && entry && entry.versionString === manifest.version), list, premiere, row, plugins, entry };
  });
  if (!res.row) {
    const seen = res.premiere.map((r) => `"${r.name}" ${r.version}`).join(", ") || "nothing";
    const elsewhere = ours(res.list.rows).filter((r) => !isPremiereRow(r)).map(hostLabel);
    const note = elsewhere.length ? ` (it is listed under ${elsewhere.join(", ")}, which dev-install does not check)` : "";
    return fail(1, `Install not confirmed: UPIA /list all shows ${seen} for Premiere Pro, not "${manifest.name}" ${manifest.version}${note}.`);
  }
  if (!res.plugins) return fail(1, `Install not confirmed: cannot read ${infoPath}.`);
  const entry = res.entry;
  if (!entry) return fail(1, `Install not confirmed: ${infoPath} has no entry for ${manifest.id}.`);
  if (entry.versionString !== manifest.version) return fail(1, `Install not confirmed: ${infoPath} lists ${manifest.id} ${entry.versionString}, not ${manifest.version}.`);
  const lost = initial.filter((p) => p.pluginId !== manifest.id && !res.plugins.some((x) => x.pluginId === p.pluginId));
  if (lost.length) {
    const who = lost.map((p) => `${p.pluginId} ("${p.name}" ${p.versionString})`).join(", ");
    return fail(1, `WARNING: ${who} is gone from ${infoPath} after this install. Reinstall it (double-click its .ccx).`);
  }

  // ---- 3c. PluginsInfo names the installed folder; its build.json must be the packaged one
  let dir;
  try {
    dir = resolvePluginPath(entry.path, deps.env);
  } catch (e) {
    return fail(1, `Install not confirmed: ${e instanceof Error ? e.message : e} in ${infoPath}.`);
  }
  let got;
  try {
    got = JSON.parse(stripBom(deps.readFile(win32.join(dir, "build.json"))));
  } catch {
    return fail(1, `Install not confirmed: ${win32.join(dir, "build.json")} is missing or unreadable, so the installed files are not this build.`);
  }
  const diff = ["product", "build", "sha"].filter((k) => got?.[k] !== build[k]);
  if (diff.length) {
    const show = (b) => `${b?.product} build ${b?.build} sha ${b?.sha}`;
    return fail(1, `Install not confirmed: the installed build.json is ${show(got)}, the package is ${show(build)} (close Premiere Pro and run this again).`);
  }

  deps.out(`installed and verified: "${manifest.name}" ${manifest.version} (${res.row.status}), build ${build.build}, sha ${build.sha}, in ${dir}`);
  const beta = [...new Set(res.list.rows.map(hostLabel).filter((h) => /^Premiere Pro/.test(h) && !PREMIERE_HOST.test(h)))];
  if (beta.length) deps.out(`note: UPIA also lists ${beta.join(", ")}; dev-install installs for and checks Premiere Pro only.`);
  return 0;
}

function stripBom(text) {
  const s = String(text);
  return s.charCodeAt(0) === 0xfeff ? s.slice(1) : s;
}

function lastLine(output) {
  return String(output ?? "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean).pop() ?? "(no output)";
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  devInstall(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (e) => {
      console.error(String(e instanceof Error ? e.message : e));
      process.exit(1);
    },
  );
}
