// Bundle a UXP plugin target into build/<target>/ (manifest + index.html + index.css + index.js + icons).
//   node scripts/build.mjs spike      -> build/spike/
//   node scripts/build.mjs plugin     -> build/plugin/   (the WhyNot Cut panel; `--mock` or WNC_MOCK=1 bundles MockSource for visual checks)
import { build } from "esbuild";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const root = join(dirname(fileURLToPath(import.meta.url)), "..");

/** UXP host modules: provided by Premiere at runtime, never bundled. */
const EXTERNAL = ["premierepro", "uxp", "fs", "os", "path", "process"];

export const TARGETS = {
  spike: {
    entry: "spike/src/spike.ts",
    files: { "spike/manifest.json": "manifest.json", "spike/index.html": "index.html", "spike/index.css": "index.css" },
  },
  plugin: {
    entry: "src/main.ts",
    files: {
      "plugin/manifest.json": "manifest.json",
      "plugin/index.html": "index.html",
      "plugin/index.css": "index.css",
      // the shared panel kit's stylesheets ship as-is (the page links tokens.css, panel.css, index.css in that order)
      "../panel-ui/styles/tokens.css": "tokens.css",
      "../panel-ui/styles/panel.css": "panel.css",
    },
  },
};

export function outDir(target) {
  return join(root, "build", target);
}

/** True for `WNC_MOCK=1` / `--mock`: the plugin bundles the panel kit's MockSource instead of the offline source. */
export function mockRequested(argv = process.argv, env = process.env) {
  return argv.includes("--mock") || ["1", "true"].includes(String(env.WNC_MOCK ?? "").toLowerCase());
}

export async function buildTarget(target, { mock = mockRequested() } = {}) {
  const t = TARGETS[target];
  if (!t) throw new Error(`unknown target "${target}" (expected: ${Object.keys(TARGETS).join(", ")})`);
  const missing = [t.entry, ...Object.keys(t.files)].filter((p) => !existsSync(join(root, p)));
  if (missing.length) {
    throw new Error(`target "${target}" is not buildable yet, missing: ${missing.join(", ")}`);
  }
  const out = outDir(target);
  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });
  await build({
    entryPoints: [join(root, t.entry)],
    outfile: join(out, "index.js"),
    bundle: true,
    // UXP loads index.js with a classic <script>; keep `require("premierepro")` etc. as real require calls.
    format: "cjs",
    platform: "node",
    target: "es2022",
    external: EXTERNAL,
    legalComments: "none",
    // build-time flag read by src/main.ts; false in every normal build, so esbuild drops MockSource from the bundle
    define: { __WNC_MOCK__: target === "plugin" && mock ? "true" : "false" },
    logLevel: "warning",
  });
  for (const [from, to] of Object.entries(t.files)) cpSync(join(root, from), join(out, to));
  cpSync(join(root, "icons"), join(out, "icons"), { recursive: true });
  return out;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const target = process.argv[2] ?? "spike";
  try {
    const out = await buildTarget(target);
    console.log(`built ${target} -> ${out}`);
  } catch (err) {
    console.error(String(err instanceof Error ? err.message : err));
    process.exit(1);
  }
}
