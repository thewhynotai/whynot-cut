import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "..", "..");
const manifest = JSON.parse(readFileSync(join(root, "plugin", "manifest.json"), "utf8"));
const productVersion = JSON.parse(readFileSync(join(repo, "whynot-cut", ".claude-plugin", "plugin.json"), "utf8")).version as string;

test("plugin manifest: v5, dev id, name, entry page, single premierepro host object", () => {
  assert.equal(manifest.manifestVersion, 5);
  assert.equal(manifest.id, "ai.thewhynot.cut.dev");
  assert.equal(manifest.name, "WhyNot Cut");
  assert.equal(manifest.main, "index.html");
  assert.ok(!Array.isArray(manifest.host), "host must be one object, not an array");
  assert.deepEqual(manifest.host, { app: "premierepro", minVersion: "26.5.0" });
});

test("plugin manifest: version is the product version (plugin.json), so a release cannot ship a stale .ccx", () => {
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
  assert.equal(manifest.version, productVersion);
});

test("plugin manifest: full file access + network \"all\" (127.0.0.1 entries failed live) + clipboard readAndWrite + launchProcess for file/folder open (owner decision 2026-10-12), and NOTHING else", () => {
  assert.deepEqual(manifest.requiredPermissions, {
    localFileSystem: "fullAccess",
    clipboard: "readAndWrite",
    launchProcess: { schemes: ["file"], extensions: [".mp4", ".mov", ".prproj", ""] },
    // live evidence: Premiere 26.5.2, spike 0.1.3 run results-20261012-211920 - "Permission denied to the url ws://127.0.0.1:53672/session. Manifest entry not found." (and the same for http://127.0.0.1:53672/status): the explicit ws://127.0.0.1 / http://127.0.0.1 entries do not match a URL with a port, so the spec's fallback applies (docs/adobe/evidence/2026-10-12-premiere-run4-panel-blocked.webp).
    // The code still only ever connects to 127.0.0.1 (guarded by the bundle test in plugin-package.test.ts).
    network: { domains: "all" },
  });
  assert.deepEqual(Object.keys(manifest.requiredPermissions).sort(), ["clipboard", "launchProcess", "localFileSystem", "network"]);
});

test("plugin manifest: launchProcess is as narrow as it works - only the file scheme, only the types the panel opens, and \"\" (Adobe's recipe: folders need an empty extension); never a web scheme", () => {
  const lp = manifest.requiredPermissions.launchProcess;
  assert.deepEqual(lp.schemes, ["file"]);
  assert.deepEqual([...lp.extensions].sort(), ["", ".mov", ".mp4", ".prproj"]);
  assert.equal(lp.schemes.some((s: string) => /^(https?|mailto)$/.test(s)), false);
  assert.equal(lp.extensions.includes("*"), false);
});

test("plugin manifest: one panel entrypoint, 340x640 preferred, 280x320 minimum", () => {
  const panels = manifest.entrypoints.filter((e: { type: string }) => e.type === "panel");
  assert.equal(panels.length, 1);
  assert.equal(manifest.entrypoints.length, 1);
  const [panel] = panels;
  assert.equal(panel.id, "whynotCut");
  assert.equal(panel.label.default, "WhyNot Cut");
  assert.deepEqual(panel.minimumSize, { width: 280, height: 320 });
  assert.deepEqual(panel.preferredDockedSize, { width: 340, height: 640 });
  assert.deepEqual(panel.preferredFloatingSize, { width: 340, height: 640 });
});

type Icon = { width: number; height: number; path: string; scale: number[]; theme: string[]; species: string[] };

test("plugin manifest: icons 23 (panel) and 24 (plugin list) at scale [1,2], dark + light, every file exists", () => {
  const all: Icon[] = [...manifest.entrypoints[0].icons, ...manifest.icons];
  const sizes = (species: string) => new Set(all.filter((i) => i.species.includes(species)).map((i) => i.width));
  assert.deepEqual([...sizes("chrome")], [23]);
  assert.deepEqual([...sizes("pluginList")], [24]);
  for (const icon of all) {
    assert.equal(icon.width, icon.height);
    assert.deepEqual(icon.scale, [1, 2]);
    assert.match(icon.path, /^icons\/(dark|light)\/icon-(23|24)\.png$/);
    const base = icon.path.replace(/\.png$/, "");
    const px2 = icon.path.replace(/-(23|24)\.png$/, (_m, n) => `-${Number(n) * 2}.png`);
    for (const p of [icon.path, px2, `${base}@2x.png`]) assert.ok(existsSync(join(root, p)), `missing ${p}`);
  }
  for (const theme of ["dark", "light"]) {
    assert.ok(all.some((i) => i.species.includes("chrome") && i.path.includes(`/${theme}/`)), `no chrome icon for ${theme}`);
    assert.ok(all.some((i) => i.species.includes("pluginList") && i.path.includes(`/${theme}/`)), `no list icon for ${theme}`);
  }
  const darkThemes = all.filter((i) => i.path.includes("/dark/")).flatMap((i) => i.theme);
  const lightThemes = all.filter((i) => i.path.includes("/light/")).flatMap((i) => i.theme);
  assert.ok(darkThemes.includes("darkest") && darkThemes.includes("dark"));
  assert.ok(lightThemes.includes("light") && lightThemes.includes("lightest"));
});

test("plugin page: loads the bundled fonts, the brand tokens, the panel kit css, then the shell css, one script, a #root to mount into", () => {
  const html = readFileSync(join(root, "plugin", "index.html"), "utf8");
  const hrefs = [...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(hrefs, ["fonts.css", "tokens.css", "panel.css", "index.css"]);
  assert.match(html, /<div id="root"><\/div>/);
  assert.equal([...html.matchAll(/<script/g)].length, 1);
  assert.match(html, /<script[^>]+src="index\.js"/);
  assert.doesNotMatch(html, /Claude Code/);
});
