import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifest = JSON.parse(readFileSync(join(root, "spike", "manifest.json"), "utf8"));

test("spike manifest: v5, ids, single premierepro host object", () => {
  assert.equal(manifest.manifestVersion, 5);
  assert.equal(manifest.id, "ai.thewhynot.cut.spike");
  assert.equal(manifest.name, "WhyNot Cut Spike");
  assert.equal(manifest.main, "index.html");
  assert.ok(!Array.isArray(manifest.host), "host must be one object, not an array");
  assert.deepEqual(manifest.host, { app: "premierepro", minVersion: "26.5.0" });
});

test("spike manifest: permissions are full file access + loopback network", () => {
  assert.equal(manifest.requiredPermissions.localFileSystem, "fullAccess");
  assert.deepEqual(manifest.requiredPermissions.network.domains, ["ws://127.0.0.1", "http://127.0.0.1"]);
});

test("spike manifest: one panel entrypoint, 340x640 preferred, 280x320 minimum", () => {
  const panels = manifest.entrypoints.filter((e: { type: string }) => e.type === "panel");
  assert.equal(panels.length, 1);
  const [panel] = panels;
  assert.equal(panel.id, "whynotCutSpike");
  assert.deepEqual(panel.minimumSize, { width: 280, height: 320 });
  assert.deepEqual(panel.preferredDockedSize, { width: 340, height: 640 });
  assert.deepEqual(panel.preferredFloatingSize, { width: 340, height: 640 });
  assert.equal(panel.label.default, "WhyNot Cut Spike");
});

type Icon = { width: number; height: number; path: string; scale: number[]; theme: string[]; species: string[] };

test("spike manifest: icons 23/46 (panel) and 24/48 (plugin list), dark + light, all files exist", () => {
  const panel = manifest.entrypoints[0];
  const all: Icon[] = [...panel.icons, ...manifest.icons];
  const sizes = (species: string) => new Set(all.filter((i) => i.species.includes(species)).map((i) => i.width));
  assert.deepEqual([...sizes("chrome")], [23]);
  assert.deepEqual([...sizes("pluginList")], [24]);
  for (const icon of all) {
    assert.equal(icon.width, icon.height);
    assert.deepEqual(icon.scale, [1, 2]);
    assert.match(icon.path, /^icons\/(dark|light)\/icon-(23|24)\.png$/);
    // the 1x file, the explicit 2x pixel size and the @2x sibling all ship
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

test("spike manifest: version is semver", () => {
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
});
