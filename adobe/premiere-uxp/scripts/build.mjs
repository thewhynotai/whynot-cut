// Bundle a UXP plugin target into build/<target>/ (manifest + index.html + index.css + index.js + icons + the brand kit).
//   node scripts/build.mjs spike      -> build/spike/
//   node scripts/build.mjs plugin     -> build/plugin/   (the WhyNot Cut panel; `--mock` or WNC_MOCK=1 bundles MockSource for visual checks)
import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const root = join(dirname(fileURLToPath(import.meta.url)), "..");

/** UXP host modules: provided by Premiere at runtime, never bundled. */
const EXTERNAL = ["premierepro", "uxp", "fs", "os", "path", "process"];

/** The brand kit every bundle carries (Addendum B): the ONE token source (brand/tokens.css, copied as-is), the font
 *  faces and the bundled OFL font files (fonts.css sits next to fonts/, so its relative URLs resolve). The string table
 *  (panel-ui/i18n/{en,ar}.json) needs no copy: esbuild bundles it into index.js wherever the panel kit is imported. */
const BRAND_KIT = {
  "../../brand/tokens.css": "tokens.css",
  "../panel-ui/styles/fonts.css": "fonts.css",
  "../panel-ui/fonts": "fonts",
};

export const TARGETS = {
  spike: {
    entry: "spike/src/spike.ts",
    // 0.1.6: the style guide renders the panel kit, so the spike carries kit.css too (index.html links fonts.css,
    // tokens.css, kit.css, index.css in that order)
    files: { "spike/manifest.json": "manifest.json", "spike/index.html": "index.html", "spike/index.css": "index.css", ...BRAND_KIT, "../panel-ui/styles/kit.css": "kit.css" },
  },
  plugin: {
    entry: "src/main.ts",
    files: {
      "plugin/manifest.json": "manifest.json",
      "plugin/index.html": "index.html",
      "plugin/index.css": "index.css",
      // the brand kit, then the shared panel stylesheets, ship as-is (the page links fonts.css, tokens.css,
      // panel.css, kit.css, index.css in that order; kit.css is scoped to .kit-root, so it changes nothing until B-T2
      // screens use the kit)
      ...BRAND_KIT,
      "../panel-ui/styles/panel.css": "panel.css",
      "../panel-ui/styles/kit.css": "kit.css",
    },
  },
};

export function outDir(target) {
  return join(root, "build", target);
}

/** The build stamp shown in the panel's log drawer and copied with its diagnostics: the short git hash of HEAD (with
 *  "+dirty" when adobe/ has uncommitted changes) and the build time in UTC to the minute, e.g.
 *  "61b12aa 2026-10-12T18:40Z". It tells two builds of the same plugin version apart on a live machine. */
export function buildStamp(now = new Date()) {
  const git = (args) => {
    try {
      return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    } catch {
      return "";
    }
  };
  const hash = git(["rev-parse", "--short", "HEAD"]) || "nogit";
  const dirty = git(["status", "--porcelain", "--", ".."]) ? "+dirty" : "";
  return `${hash}${dirty} ${now.toISOString().slice(0, 16)}Z`;
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
    define: { __WNC_MOCK__: target === "plugin" && mock ? "true" : "false", __WNC_BUILD__: JSON.stringify(buildStamp()) },
    logLevel: "warning",
  });
  for (const [from, to] of Object.entries(t.files)) cpSync(join(root, from), join(out, to), { recursive: true });
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
