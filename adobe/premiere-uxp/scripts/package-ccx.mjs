// Build a target and zip it into a .ccx (a zip with manifest.json at its root).
//   node scripts/package-ccx.mjs spike    -> <repo>/dist/uxp/WhyNotCut-Spike.ccx            (gitignored)
//   node scripts/package-ccx.mjs plugin   -> <repo>/whynot-cut/adobe/WhyNotCut-Premiere-<version>.ccx  (gitignored there; whynot-cut/adobe/.gitignore)
// Every .ccx carries build.json {product, build, sha} next to manifest.json: dev-install.mjs (and later the installer and
// the daemon) compare the installed copy with the packaged one, because UPIA can report success and keep old files.
import { zipSync } from "fflate";
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { buildTarget, mockRequested, root } from "./build.mjs";

const repo = join(root, "..", "..");
// 2026-01-01: a fixed timestamp makes the zip entries' dates reproducible (build.json's own `build` id still changes per run).
const FIXED_MTIME = new Date(2026, 0, 1, 0, 0, 0);

/** The id the released panel gets (Addendum C §3.3). Every other id is a dev or spike build. */
export const RELEASE_ID = "ai.thewhynot.cut";

function pluginVersion() {
  const p = join(repo, "whynot-cut", ".claude-plugin", "plugin.json");
  return JSON.parse(readFileSync(p, "utf8")).version;
}

export const OUTPUTS = {
  spike: () => join(repo, "dist", "uxp", "WhyNotCut-Spike.ccx"),
  plugin: () => join(repo, "whynot-cut", "adobe", `WhyNotCut-Premiere-${pluginVersion()}.ccx`),
};

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function defaultGit(args) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
}

/** `git rev-parse --short HEAD`, plus "-dirty" when the sources that go into a .ccx (adobe/ and brand/) have
 *  uncommitted changes; "unknown" when git is missing or this is not a checkout. `git` is injectable for tests. */
export function gitSha(git = defaultGit) {
  let hash;
  try {
    hash = git(["rev-parse", "--short", "HEAD"]);
  } catch {
    return "unknown";
  }
  if (!/^[0-9a-f]{4,40}$/.test(hash ?? "")) return "unknown";
  let dirty = "";
  try {
    dirty = git(["status", "--porcelain", "--", join(root, ".."), join(repo, "brand")]) ? "-dirty" : "";
  } catch {
    // the hash is known; a failing status check only loses the dirty flag
  }
  return `${hash}${dirty}`;
}

/** UTC timestamp id, e.g. 2026-10-13T14:25:30.123Z -> "20261013T142530Z". */
export function buildId(now = new Date()) {
  return now.toISOString().replace(/\.\d+Z$/, "Z").replace(/[-:]/g, "");
}

/** The build.json written into every .ccx: product = the manifest version, build = UTC timestamp id, sha = git. */
export function buildInfo(manifest, { now = new Date(), sha = gitSha() } = {}) {
  return { product: manifest.version, build: buildId(now), sha };
}

/** A dev id (ending in ".dev") is visibly a dev build: " (dev)" after the plugin name and every panel label, so
 *  Window > UXP Plugins and UPIA `/list all` (which lists names, not ids) tell it apart from the release "WhyNot Cut".
 *  The release id and the spike ("WhyNot Cut Spike") keep their names. */
export function stampDevName(manifest) {
  if (!/\.dev$/.test(String(manifest.id))) return manifest;
  const tag = (s) => (/\(dev\)/.test(s) ? s : `${s} (dev)`);
  return {
    ...manifest,
    name: tag(manifest.name),
    entrypoints: (manifest.entrypoints ?? []).map((e) =>
      e.label && typeof e.label.default === "string" ? { ...e, label: { ...e.label, default: tag(e.label.default) } } : e,
    ),
  };
}

export async function packageTarget(target, { now = new Date(), sha } = {}) {
  const outFile = OUTPUTS[target]?.();
  if (!outFile) throw new Error(`unknown target "${target}" (expected: ${Object.keys(OUTPUTS).join(", ")})`);
  // A .ccx is what gets installed; it must never carry the mock data source.
  if (target === "plugin" && mockRequested()) throw new Error("refusing to package the plugin from a mock build (WNC_MOCK / --mock): unset it and run again");
  const dir = await buildTarget(target, { mock: false });
  const entries = {};
  // manifest.json first, then everything else in sorted order; forward slashes, rooted at the plugin folder
  const rel = (f) => relative(dir, f).split(sep).join("/");
  const files = walk(dir).sort((a, b) => Number(rel(b) === "manifest.json") - Number(rel(a) === "manifest.json"));
  for (const f of files) {
    entries[rel(f)] = [new Uint8Array(readFileSync(f)), { mtime: FIXED_MTIME, level: 6 }];
  }
  if (!("manifest.json" in entries)) throw new Error("manifest.json missing from the build output");
  if ("build.json" in entries) throw new Error("build.json is written by package-ccx; the build output must not carry one");
  const manifest = stampDevName(JSON.parse(new TextDecoder().decode(entries["manifest.json"][0])));
  const info = buildInfo(manifest, { now, sha: sha ?? gitSha() });
  const json = (o) => new TextEncoder().encode(`${JSON.stringify(o, null, 2)}\n`);
  entries["manifest.json"] = [json(manifest), { mtime: FIXED_MTIME, level: 6 }];
  entries["build.json"] = [json(info), { mtime: FIXED_MTIME, level: 6 }];
  mkdirSync(join(outFile, ".."), { recursive: true });
  writeFileSync(outFile, zipSync(entries));
  return { outFile, entries: Object.keys(entries), manifest, build: info };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const target = process.argv[2] ?? "spike";
  try {
    const { outFile, entries, manifest, build } = await packageTarget(target);
    console.log(`packaged ${target}: ${outFile} (${entries.length} files, ${statSync(outFile).size} bytes)`);
    console.log(`  ${manifest.id} "${manifest.name}" ${build.product}, build ${build.build}, sha ${build.sha}`);
  } catch (err) {
    console.error(String(err instanceof Error ? err.message : err));
    process.exit(1);
  }
}
