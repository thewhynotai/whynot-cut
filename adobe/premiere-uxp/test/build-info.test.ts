// C2.6: build.json {product, build, sha} in every .ccx, and the names the editor (and UPIA /list all) sees.
// The packaged files themselves are checked in package.test.ts (spike) and plugin-package.test.ts (plugin).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

type Manifest = { id: string; name: string; version: string; entrypoints: { id: string; label?: { default: string } }[] };
type PackageCcx = {
  RELEASE_ID: string;
  gitSha(git?: (args: string[]) => string): string;
  buildId(now?: Date): string;
  buildInfo(manifest: { version: string }, opts?: { now?: Date; sha?: string }): { product: string; build: string; sha: string };
  stampDevName(manifest: Manifest): Manifest;
};
const pc = (await import(pathToFileURL(join(root, "scripts", "package-ccx.mjs")).href)) as PackageCcx;
type BuildMjs = {
  buildId(now?: Date): string;
  buildDefines(o: { target: string; mock: boolean; now: Date; sha: string }): Record<string, string>;
  localSha(): string;
};
const bm = (await import(pathToFileURL(join(root, "scripts", "build.mjs")).href)) as BuildMjs;
const read = (p: string) => JSON.parse(readFileSync(join(root, p), "utf8")) as Manifest;
const product = read("plugin/manifest.json");
const spike = read("spike/manifest.json");

test("buildId: a UTC timestamp id, seconds precision, no separators", () => {
  assert.equal(pc.buildId(new Date(Date.UTC(2026, 9, 13, 14, 25, 30, 123))), "20261013T142530Z");
  assert.match(pc.buildId(), /^\d{8}T\d{6}Z$/);
});

test("C1.8: one id per build - the panel's __WNC_BUILD__ is build.json's `build`; the git sha rides separately as __WNC_SHA__", () => {
  assert.equal(bm.buildId, pc.buildId, "package-ccx uses build.mjs's buildId: one function, one format");
  const now = new Date(Date.UTC(2026, 9, 13, 14, 25, 30, 123));
  const d = bm.buildDefines({ target: "plugin", mock: false, now, sha: "57d3211-dirty" });
  assert.deepEqual(d, { __WNC_MOCK__: "false", __WNC_BUILD__: JSON.stringify("20261013T142530Z"), __WNC_SHA__: JSON.stringify("57d3211-dirty") });
  assert.equal(JSON.parse(d.__WNC_BUILD__!), pc.buildInfo(product, { now, sha: "x" }).build, "the same id build.json gets for the same build");
  assert.match(JSON.parse(d.__WNC_BUILD__!), /^\d{8}T\d{6}Z$/, "sortable: text order is time order (the daemon compares ids as text)");
  assert.equal(bm.buildDefines({ target: "plugin", mock: true, now, sha: "x" }).__WNC_MOCK__, "true");
  assert.equal(bm.buildDefines({ target: "spike", mock: true, now, sha: "x" }).__WNC_MOCK__, "false", "only the plugin bundles MockSource");
  assert.match(bm.localSha(), /^(?:[0-9a-f]{4,40}(?:-dirty)?|unknown)$/);
});

test("gitSha: short HEAD, \"-dirty\" when adobe/ or brand/ has changes, \"unknown\" without git", () => {
  const git = (head: string | Error, status: string | Error) => (args: string[]) => {
    const r = args[0] === "rev-parse" ? head : status;
    if (r instanceof Error) throw r;
    return r;
  };
  assert.equal(pc.gitSha(git("57d3211", "")), "57d3211");
  assert.equal(pc.gitSha(git("57d3211", " M adobe/x.ts")), "57d3211-dirty");
  assert.equal(pc.gitSha(git(new Error("not a git repository"), "")), "unknown");
  assert.equal(pc.gitSha(git("", "")), "unknown");
  assert.equal(pc.gitSha(git("fatal: bad", "")), "unknown");
  assert.equal(pc.gitSha(git("57d3211", new Error("status failed"))), "57d3211", "status failing only loses the dirty flag");
  const calls: string[][] = [];
  pc.gitSha((a) => (calls.push(a), a[0] === "rev-parse" ? "abc1234" : ""));
  assert.deepEqual(calls[0], ["rev-parse", "--short", "HEAD"]);
  assert.deepEqual(calls[1]!.slice(0, 3), ["status", "--porcelain", "--"]);
  assert.match(calls[1]![3]!, /adobe$/);
  assert.match(calls[1]![4]!, /brand$/);
  // this checkout
  assert.match(pc.gitSha(), /^(?:[0-9a-f]{4,40}(?:-dirty)?|unknown)$/);
});

test("buildInfo: {product, build, sha} - product is the manifest version", () => {
  const now = new Date(Date.UTC(2026, 9, 13, 8, 0, 5));
  assert.deepEqual(pc.buildInfo(product, { now, sha: "57d3211-dirty" }), { product: product.version, build: "20261013T080005Z", sha: "57d3211-dirty" });
  assert.deepEqual(Object.keys(pc.buildInfo(spike, { now, sha: "x" })), ["product", "build", "sha"]);
  assert.equal(pc.buildInfo(spike, { now, sha: "x" }).product, spike.version);
});

test("names: the product manifest is exactly \"WhyNot Cut\" (C4/H5 release name), panel label too", () => {
  assert.equal(product.name, "WhyNot Cut");
  assert.equal(product.entrypoints[0]!.label!.default, "WhyNot Cut");
  assert.equal(pc.RELEASE_ID, "ai.thewhynot.cut");
  // with the release id it keeps the exact product name
  const release = pc.stampDevName({ ...product, id: pc.RELEASE_ID });
  assert.equal(release.name, "WhyNot Cut");
  assert.equal(release.entrypoints[0]!.label!.default, "WhyNot Cut");
});

test("names: any dev manifest is visibly \"(dev)\" - the product manifest under its current dev id packages as \"WhyNot Cut (dev)\"", () => {
  assert.match(product.id, /\.dev$/, "the plugin still carries the dev id until release");
  const dev = pc.stampDevName(product);
  assert.equal(dev.name, "WhyNot Cut (dev)");
  assert.equal(dev.entrypoints[0]!.label!.default, "WhyNot Cut (dev)");
  assert.equal(dev.entrypoints[0]!.id, "whynotCut", "panel id unchanged");
  assert.deepEqual(pc.stampDevName(dev), dev, "stamping twice adds nothing");
  assert.equal(product.name, "WhyNot Cut", "the source manifest is not mutated");
  for (const m of [product, spike].map((x) => pc.stampDevName(x))) {
    if (/\.dev$/.test(m.id)) assert.match(m.name, /\(dev\)/, `${m.id} name "${m.name}"`);
  }
});

test("names: the spike is \"Spike\" by name and never stamped \"(dev)\"", () => {
  assert.equal(spike.id, "ai.thewhynot.cut.spike");
  assert.match(spike.name, /Spike/);
  assert.match(spike.entrypoints[0]!.label!.default, /Spike/);
  assert.equal(pc.stampDevName(spike).name, spike.name);
});
