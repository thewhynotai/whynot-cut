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
  assert.match(manifest.name, /Spike/);
  assert.doesNotMatch(manifest.name, /\(dev\)/);
  // C2.6: build.json {product, build, sha} next to manifest.json (dev-install compares the installed copy with it)
  const build = JSON.parse(new TextDecoder().decode(files["build.json"]));
  assert.deepEqual(Object.keys(build), ["product", "build", "sha"]);
  assert.equal(build.product, manifest.version);
  assert.match(build.build, /^\d{8}T\d{6}Z$/);
  assert.match(build.sha, /^(?:[0-9a-f]{4,40}(?:-dirty)?|unknown)$/);
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

test("spike 0.1.6+: the bundle carries kit.css (as-is), the string table (EN + AR) and the kit gallery for the style guide", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  assert.equal(new TextDecoder().decode(files["kit.css"]), readFileSync(join(root, "..", "panel-ui", "styles", "kit.css"), "utf8"));
  const html = new TextDecoder().decode(files["index.html"]);
  assert.deepEqual([...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map((m) => m[1]), ["fonts.css", "tokens.css", "kit.css", "index.css", "lab.css"]);
  // esbuild writes non-ASCII as \uXXXX escapes: read them back before looking for the Arabic strings
  const js = new TextDecoder().decode(files["index.js"]).replace(/\\u([0-9a-fA-F]{4})/g, (_m, h: string) => String.fromCharCode(parseInt(h, 16)));
  const ar = JSON.parse(readFileSync(join(root, "..", "panel-ui", "i18n", "ar.json"), "utf8")) as Record<string, string>;
  const en = JSON.parse(readFileSync(join(root, "..", "panel-ui", "i18n", "en.json"), "utf8")) as Record<string, string>;
  for (const key of ["tab.home", "approval.approve"]) {
    assert.ok(js.includes(en[key]!), `EN ${key}`);
    assert.ok(js.includes(ar[key]!), `AR ${key}`);
  }
  assert.match(js, /kit-root/);
  assert.match(js, /whynotcut:\/\/engine\/start/);
  const manifest = JSON.parse(new TextDecoder().decode(files["manifest.json"]));
  assert.equal(manifest.version, "0.1.7");
  assert.ok(Array.isArray(manifest.requiredPermissions.network.domains));
});

test("spike 0.1.7: the bundle carries the CSS lab - lab.css at the root, every font file it names, the .woff fonts with their OFL texts, the bundled test icon", () => {
  const files = unzipSync(new Uint8Array(readFileSync(ccx)));
  assert.equal(new TextDecoder().decode(files["lab.css"]), readFileSync(join(root, "spike", "lab.css"), "utf8"));
  const css = new TextDecoder().decode(files["lab.css"]).replace(/\/\*[\s\S]*?\*\//g, "");
  // plugin:/ and ./ name the same bundle-root files as the plain relative form
  const urls = [...css.matchAll(/url\("([^"]+)"\)/g)].map((m) => m[1]!.replace(/^plugin:\//, "").replace(/^\.\//, ""));
  assert.ok(urls.length >= 12);
  for (const u of urls) assert.ok(u in files, `${u} is not in the spike .ccx`);
  for (const f of ["lab/fonts/syne/Syne-Bold.woff", "lab/fonts/syne/OFL.txt", "lab/fonts/ibmplexsansarabic/IBMPlexSansArabic-Regular.woff", "lab/fonts/ibmplexsansarabic/OFL.txt", "lab/icons/ok.svg"]) {
    assert.ok(f in files, f);
  }
  const js = new TextDecoder().decode(files["index.js"]);
  assert.match(js, /lab-root/);
  assert.match(js, /css_lab/);
  assert.equal(JSON.parse(new TextDecoder().decode(files["manifest.json"])).version, "0.1.7");
});
