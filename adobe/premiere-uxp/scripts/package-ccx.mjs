// Build a target and zip it into a .ccx (a zip with manifest.json at its root).
//   node scripts/package-ccx.mjs spike    -> <repo>/dist/uxp/WhyNotCut-Spike.ccx            (gitignored)
//   node scripts/package-ccx.mjs plugin   -> <repo>/whynot-cut/adobe/WhyNotCut-Premiere-<version>.ccx  (gitignored there; whynot-cut/adobe/.gitignore)
import { zipSync } from "fflate";
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { buildTarget, mockRequested, root } from "./build.mjs";

const repo = join(root, "..", "..");
// 2026-01-01: a fixed timestamp makes the zip byte-for-byte reproducible for the same inputs.
const FIXED_MTIME = new Date(2026, 0, 1, 0, 0, 0);

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

export async function packageTarget(target) {
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
  mkdirSync(join(outFile, ".."), { recursive: true });
  writeFileSync(outFile, zipSync(entries));
  return { outFile, entries: Object.keys(entries) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const target = process.argv[2] ?? "spike";
  try {
    const { outFile, entries } = await packageTarget(target);
    console.log(`packaged ${target}: ${outFile} (${entries.length} files, ${statSync(outFile).size} bytes)`);
  } catch (err) {
    console.error(String(err instanceof Error ? err.message : err));
    process.exit(1);
  }
}
