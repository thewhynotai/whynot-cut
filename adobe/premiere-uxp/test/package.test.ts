import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { unzipSync } from "fflate";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "..", "..");
const ccx = join(repo, "dist", "uxp", "WhyNotCut-Spike.ccx");

test("package-ccx spike builds dist/uxp/WhyNotCut-Spike.ccx with manifest.json at the zip root", () => {
  execFileSync(process.execPath, [join(root, "scripts", "package-ccx.mjs"), "spike"], { cwd: root, stdio: "pipe" });
  assert.ok(existsSync(ccx), "ccx not written");
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  const names = Object.keys(files);
  for (const need of ["manifest.json", "index.html", "index.js", "index.css"]) {
    assert.ok(names.includes(need), `missing ${need} at zip root (got ${names.join(", ")})`);
  }
  assert.ok(
    names.every((n) => !n.includes("\\") && !n.startsWith("spike/") && !n.startsWith("build/")),
    "entries must be forward-slash and rooted at the plugin folder",
  );
  const manifest = JSON.parse(new TextDecoder().decode(files["manifest.json"]));
  assert.equal(manifest.id, "ai.thewhynot.cut.spike");
  const icons = names.filter((n) => n.startsWith("icons/") && n.endsWith(".png"));
  assert.ok(icons.length >= 12, `expected the icon set, got ${icons.length}`);
});

test("bundled spike script keeps UXP host modules external and loads from index.html", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  const js = new TextDecoder().decode(files["index.js"]);
  assert.match(js, /require\(\s*["']premierepro["']\s*\)/);
  assert.doesNotMatch(js, /@adobe\/premierepro/);
  const html = new TextDecoder().decode(files["index.html"]);
  assert.match(html, /<script[^>]+src="index\.js"/);
  assert.match(html, /<link[^>]+href="index\.css"/);
});

test("the spike bundle carries the brand kit for its style guide: brand tokens, fonts.css and every font file it names", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  assert.equal(new TextDecoder().decode(files["tokens.css"]), readFileSync(join(repo, "brand", "tokens.css"), "utf8"));
  const css = new TextDecoder().decode(files["fonts.css"]);
  const urls = [...css.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map((m) => m[1]!);
  assert.ok(urls.length >= 7);
  for (const u of urls) assert.ok(u in files, `${u} is not in the spike .ccx`);
  assert.ok(Object.keys(files).some((n) => n.endsWith("/OFL.txt")));
});
