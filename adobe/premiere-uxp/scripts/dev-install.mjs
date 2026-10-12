// Install a packaged .ccx on this Windows PC and prove it landed: UPIA /remove -> /install -> verify.
//   npm run dev-install -- <path\to\plugin.ccx> [--release]          (from adobe/)
//   node premiere-uxp/scripts/dev-install.mjs <ccx> [--release]
//
// Why (Addendum C §3.3/§3.4, docs/adobe/uxp-parity.md): UPIA exits 0 even when it fails (Creative Cloud not running ->
// "status = -642"), and a same-version install reports "Installation Successful" but keeps the old files. So this
// removes first, installs, then checks three things and exits non-zero unless all hold:
//   1. the /install output contains "Installation Successful";
//   2. `/list all` lists the plugin's name and version under Premiere Pro (UPIA lists names, not ids);
//   3. the installed folder's build.json (found through %APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json) has the
//      packaged build.json's product, build and sha.
// Exit codes: 0 installed and verified; 1 UPIA failed or a check did not hold; 2 could not start (usage, not Windows,
// no UPIA, Creative Cloud not running, refused id, not a packaged .ccx).
//
// Every side effect goes through `deps` (UPIA runner, files, process list, Creative Cloud start, clock, output), so the
// tests drive it with fixtures and never install anything.
import { unzipSync } from "fflate";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve, win32 } from "node:path";
import { pathToFileURL } from "node:url";
import { RELEASE_ID } from "./package-ccx.mjs";

export const UPIA_PATH = String.raw`C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe`;
export const CREATIVE_CLOUD_EXE = String.raw`C:\Program Files\Adobe\Adobe Creative Cloud\ACC\Creative Cloud.exe`;
/** Every WhyNot Cut UXP id: the release id itself, or `ai.thewhynot.cut.<something>` (dev, spike, tools). */
const ID_FAMILY = /^ai\.thewhynot\.cut(\.[a-z0-9-]+)*$/;
const CC_PROCESS = "creative cloud.exe";
const PREMIERE_PROCESS = "adobe premiere pro.exe";
const CC_WAIT_MS = 60_000;
const CC_POLL_MS = 2_000;
const CC_SETTLE_MS = 5_000;

export const USAGE = "usage: npm run dev-install -- <path to .ccx> [--release]";

export function parseArgs(argv) {
  const out = { ccx: undefined, release: false, help: false, unknown: [] };
  for (const a of argv) {
    if (a === "--release") out.release = true;
    else if (a === "--help" || a === "-h") out.help = true;
    else if (a.startsWith("-")) out.unknown.push(a);
    else if (out.ccx === undefined) out.ccx = a;
    else out.unknown.push(a);
  }
  return out;
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
 *  " <Status>    <Extension Name>    <Version>" (columns are runs of 2+ spaces; the name may hold single spaces). */
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
    const row = /^\s*(\S+)\s{2,}(.+?)\s{2,}(\S+)$/.exec(line);
    if (row) out.push({ host, hostVersion, status: row[1], name: row[2], version: row[3] });
  }
  return out;
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
  const manifest = JSON.parse(m);
  const build = JSON.parse(b);
  for (const k of ["id", "name", "version"]) if (typeof manifest[k] !== "string") throw new Error(`its manifest.json has no ${k}`);
  for (const k of ["product", "build", "sha"]) if (typeof build[k] !== "string") throw new Error(`its build.json has no ${k}`);
  return { manifest, build };
}

/** null when the id may be installed, else the one-sentence refusal. */
export function idRefusal(id, release) {
  if (!ID_FAMILY.test(id)) return `"${id}" is not a WhyNot Cut plugin id, so dev-install will not install it.`;
  if (id === RELEASE_ID && !release) return `This .ccx has the release id ${RELEASE_ID}; add --release to install it on purpose.`;
  return null;
}

export function realDeps() {
  return {
    platform: process.platform,
    env: process.env,
    cwd: process.env.INIT_CWD || process.cwd(),
    upiaPath: UPIA_PATH,
    creativeCloudExe: CREATIVE_CLOUD_EXE,
    runUpia(args) {
      const r = spawnSync(UPIA_PATH, args, { encoding: "utf8", windowsHide: true, timeout: 180_000 });
      if (r.error) return { status: null, output: String(r.error.message) };
      return { status: r.status, output: `${r.stdout ?? ""}${r.stderr ?? ""}` };
    },
    readFile: (p) => readFileSync(p),
    exists: (p) => existsSync(p),
    processes() {
      const r = spawnSync("tasklist", ["/FO", "CSV", "/NH"], { encoding: "utf8", windowsHide: true });
      return parseTasklist(r.stdout ?? "");
    },
    startCreativeCloud() {
      if (!existsSync(CREATIVE_CLOUD_EXE)) return false;
      try {
        spawn(CREATIVE_CLOUD_EXE, [], { detached: true, stdio: "ignore", windowsHide: false }).unref();
        return true;
      } catch {
        return false;
      }
    },
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    out: (line) => console.log(line),
    err: (line) => console.error(line),
  };
}

async function ensureCreativeCloud(deps) {
  if (deps.processes().includes(CC_PROCESS)) return true;
  deps.out("Creative Cloud is not running; starting it ...");
  if (!deps.startCreativeCloud()) return false;
  for (let waited = 0; waited < CC_WAIT_MS; waited += CC_POLL_MS) {
    await deps.sleep(CC_POLL_MS);
    if (deps.processes().includes(CC_PROCESS)) {
      // UPIA talks to Creative Cloud's services; give them a moment after the window process appears
      await deps.sleep(CC_SETTLE_MS);
      return true;
    }
  }
  return false;
}

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

  const ccx = resolve(deps.cwd, args.ccx);
  let pkg;
  try {
    pkg = readCcx(deps.readFile(ccx));
  } catch (e) {
    const why = e && e.code === "ENOENT" ? "it does not exist" : e instanceof Error ? e.message : String(e);
    return fail(2, `Cannot install ${ccx}: ${why}.`);
  }
  const { manifest, build } = pkg;
  const refusal = idRefusal(manifest.id, args.release);
  if (refusal) return fail(2, refusal);
  if (!deps.exists(deps.upiaPath)) return fail(2, `Adobe's installer agent (UPIA) is not at ${deps.upiaPath}; install or repair Creative Cloud first.`);
  if (!(await ensureCreativeCloud(deps))) return fail(2, "Creative Cloud is not running and could not be started; open Creative Cloud, then run this again.");

  deps.out(`package: ${manifest.id} "${manifest.name}" ${manifest.version}, build ${build.build}, sha ${build.sha}`);
  const infoPath = pluginsInfoPath(deps.env);
  const installed = () => {
    try {
      return parsePluginsInfo(String(deps.readFile(infoPath)));
    } catch {
      return [];
    }
  };
  const entryFor = (plugins) => plugins.find((p) => p.pluginId === manifest.id);

  // 1. remove (a same-version install would otherwise keep the old files)
  const before = entryFor(installed());
  deps.out(before ? `removing ${manifest.id} (installed: "${before.name}" ${before.versionString})` : `removing ${manifest.id} (not installed)`);
  const r1 = deps.runUpia(["/remove", manifest.id]);
  deps.out(`  UPIA /remove ${manifest.id}: ${lastLine(r1.output)}`);
  let after = installed();
  let left = entryFor(after);
  if (left) {
    // UPIA's own help reads "/remove <extension-name>": when the id did not work, remove by the installed name, but
    // never when another plugin shares that name (it could be the release panel).
    const clash = after.filter((p) => p.pluginId !== manifest.id && p.name === left.name).map((p) => p.pluginId);
    if (clash.length) return fail(1, `UPIA did not remove ${manifest.id}, and its name "${left.name}" is also used by ${clash.join(", ")}; remove it in Creative Cloud, then run this again.`);
    const r2 = deps.runUpia(["/remove", left.name]);
    deps.out(`  UPIA /remove "${left.name}": ${lastLine(r2.output)}`);
    after = installed();
    left = entryFor(after);
    if (left) return fail(1, `UPIA did not remove ${manifest.id} ("${left.name}" ${left.versionString} is still installed); remove it in Creative Cloud, then run this again.`);
  }

  // 2. install
  deps.out(`installing ${ccx}`);
  const ins = deps.runUpia(["/install", ccx]);
  deps.out(`  UPIA /install: ${lastLine(ins.output)}`);
  if (!installSucceeded(ins.output)) return fail(1, `Install failed: ${upiaFailure(ins.output)} (UPIA exit code ${ins.status}).`);

  // 3a. /list all shows the name and version under Premiere Pro
  const listed = parseUpiaList(deps.runUpia(["/list", "all"]).output).filter((r) => /^Premiere Pro\b/.test(r.host));
  const row = listed.find((r) => r.name === manifest.name && r.version === manifest.version);
  if (!row) {
    const seen = listed.map((r) => `"${r.name}" ${r.version}`).join(", ") || "nothing";
    return fail(1, `Install not confirmed: UPIA /list all shows ${seen} for Premiere Pro, not "${manifest.name}" ${manifest.version}.`);
  }

  // 3b. PluginsInfo names the installed folder; its build.json must be the packaged one
  let plugins;
  try {
    plugins = parsePluginsInfo(String(deps.readFile(infoPath)));
  } catch (e) {
    return fail(1, `Install not confirmed: cannot read ${infoPath} (${e instanceof Error ? e.message : e}).`);
  }
  const entry = entryFor(plugins);
  if (!entry) return fail(1, `Install not confirmed: ${infoPath} has no entry for ${manifest.id}.`);
  if (entry.versionString !== manifest.version) return fail(1, `Install not confirmed: ${infoPath} lists ${manifest.id} ${entry.versionString}, not ${manifest.version}.`);
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

  deps.out(`installed and verified: "${manifest.name}" ${manifest.version} (${row.status}), build ${build.build}, sha ${build.sha}, in ${dir}`);
  if (deps.processes().includes(PREMIERE_PROCESS)) deps.out("Premiere Pro is open: restart it to load this build.");
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
