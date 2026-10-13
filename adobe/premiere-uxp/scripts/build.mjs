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
 *  faces and the bundled OFL font files (fonts.css sits next to fonts/, so its relative URLs resolve). Premiere UXP
 *  loads no @font-face (spike 0.1.7), so no UXP page links fonts.css (0.1.8): it ships for CEP / Chromium and for the
 *  font-bundle test; in Premiere the token stacks use the installed brand fonts or the system fallbacks. The string table
 *  (panel-ui/i18n/{en,ar}.json) needs no copy: esbuild bundles it into index.js wherever the panel kit is imported. */
const BRAND_KIT = {
  "../../brand/tokens.css": "tokens.css",
  "../panel-ui/styles/fonts.css": "fonts.css",
  "../panel-ui/fonts": "fonts",
};

export const TARGETS = {
  spike: {
    entry: "spike/src/spike.ts",
    // 0.1.6: the style guide renders the panel kit, so the spike carries kit.css too (index.html links tokens.css,
    // kit.css, index.css in that order; 0.1.8 dropped fonts.css, which UXP never loads). 0.1.7: the CSS lab's lab.css (at the root, next to fonts.css, so
    // its relative font URLs resolve alike) and lab/ (the .woff test fonts with their OFL texts, the bundled test icon)
    files: {
      "spike/manifest.json": "manifest.json",
      "spike/index.html": "index.html",
      "spike/index.css": "index.css",
      ...BRAND_KIT,
      "../panel-ui/styles/kit.css": "kit.css",
      "spike/lab.css": "lab.css",
      "spike/lab": "lab",
    },
  },
  plugin: {
    entry: "src/main.ts",
    files: {
      "plugin/manifest.json": "manifest.json",
      "plugin/index.html": "index.html",
      "plugin/index.css": "index.css",
      // the brand kit, then the shared panel stylesheets, ship as-is (the page links tokens.css, panel.css,
      // kit.css, index.css in that order - no fonts.css, UXP loads no @font-face; kit.css is scoped to .kit-root, so it changes nothing until B-T2
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

/** The build id (C1.8): UTC time to the second, YYYYMMDDTHHMMSSZ, e.g. 2026-10-13T14:25:30.123Z -> "20261013T142530Z".
 *  ONE id per build: the panel bundle's `__WNC_BUILD__` (sent as hello client.build) and the .ccx's build.json `build`
 *  (package-ccx.mjs passes the same `now` to both), and release.py writes the shipped ccx's id into expected.json. The
 *  daemon compares two ids as text, which is time order (serve/messages.py compare_builds), so an older panel is
 *  "stale" (restart Premiere). */
export function buildId(now = new Date()) {
  return now.toISOString().replace(/\.\d+Z$/, "Z").replace(/[-:]/g, "");
}

/** The git short hash of HEAD with "-dirty" when adobe/ has uncommitted changes, "unknown" without git: info only (the
 *  log drawer and diagnostics show it next to the build id). A packaged build gets package-ccx's gitSha instead. */
export function localSha() {
  const git = (args) => {
    try {
      return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    } catch {
      return "";
    }
  };
  const hash = git(["rev-parse", "--short", "HEAD"]);
  if (!/^[0-9a-f]{4,40}$/.test(hash)) return "unknown";
  return `${hash}${git(["status", "--porcelain", "--", ".."]) ? "-dirty" : ""}`;
}

/** esbuild `define`s read by src/main.ts: __WNC_MOCK__ (true only for a mock plugin build), __WNC_BUILD__ (the build id)
 *  and __WNC_SHA__ (the git sha, info only). */
export function buildDefines({ target, mock, now, sha }) {
  return {
    __WNC_MOCK__: target === "plugin" && mock ? "true" : "false",
    __WNC_BUILD__: JSON.stringify(buildId(now)),
    __WNC_SHA__: JSON.stringify(sha),
  };
}

/** True for `WNC_MOCK=1` / `--mock`: the plugin bundles the panel kit's MockSource instead of the offline source. */
export function mockRequested(argv = process.argv, env = process.env) {
  return argv.includes("--mock") || ["1", "true"].includes(String(env.WNC_MOCK ?? "").toLowerCase());
}

/** `now` / `sha`: package-ccx passes the ones it writes into build.json, so the bundle carries the same id. */
export async function buildTarget(target, { mock = mockRequested(), now = new Date(), sha } = {}) {
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
    // build-time constants read by src/main.ts; __WNC_MOCK__ is false in every normal build, so esbuild drops MockSource
    define: buildDefines({ target, mock, now, sha: sha ?? localSha() }),
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
