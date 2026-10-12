// B-T1 font-bundle test (source side): styles/fonts.css declares the four brand families from files bundled under
// panel-ui/fonts/ (byte copies of the OFL files vendored in guide-ar/fonts/, each folder with its OFL licence). No
// network URL anywhere. The plugin package test checks the same files are inside the built .ccx.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { PANEL_UI, REPO, walk } from "./tokens-util.ts";

const FONTS_CSS = join(PANEL_UI, "styles", "fonts.css");
const VENDORED = join(REPO, "guide-ar", "fonts");

/** The @font-face rules of a stylesheet: family, weight, style and every url() in src. */
export function fontFaces(css: string): { family: string; weight: string; style: string; urls: string[] }[] {
  const flat = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...flat.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((m) => {
    const body = m[1]!;
    const prop = (p: string) => (new RegExp(`(?:^|;)\\s*${p}\\s*:\\s*([^;]+)`).exec(body)?.[1] ?? "").trim();
    return {
      family: prop("font-family").replace(/^["']|["']$/g, ""),
      weight: prop("font-weight"),
      style: prop("font-style") || "normal",
      urls: [...body.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map((u) => u[1]!),
    };
  });
}

/** What Addendum B names, mapped to the static files vendored in guide-ar/fonts (no other weights ship). */
const EXPECTED: Record<string, { dir: string; files: Record<string, string> }> = {
  Syne: { dir: "syne", files: { "700": "Syne-Bold.ttf" } },
  Inter: { dir: "inter", files: { "400": "Inter-Regular.ttf", "600": "Inter-SemiBold.ttf" } },
  "IBM Plex Sans Arabic": {
    dir: "ibmplexsansarabic",
    files: { "300": "IBMPlexSansArabic-Light.ttf", "400": "IBMPlexSansArabic-Regular.ttf", "600": "IBMPlexSansArabic-SemiBold.ttf" },
  },
  "IBM Plex Mono": { dir: "ibmplexmono", files: { "400": "IBMPlexMono-Regular.ttf" } },
};

test("fonts.css declares the four brand families with the bundled files, relative URLs only", () => {
  const css = readFileSync(FONTS_CSS, "utf8");
  assert.doesNotMatch(css, /https?:|\/\/|@import/i, "no network fonts");
  const faces = fontFaces(css);
  const got = faces.map((f) => `${f.family}|${f.weight}|${f.style}|${f.urls.join(",")}`).sort();
  const want = Object.entries(EXPECTED)
    .flatMap(([family, e]) => Object.entries(e.files).map(([w, file]) => `${family}|${w}|normal|fonts/${e.dir}/${file}`))
    .sort();
  assert.deepEqual(got, want);
  for (const f of faces) assert.match(css, new RegExp(`url\\("${f.urls[0]!.replace(/[.]/g, "\\.")}"\\) format\\("truetype"\\)`));
});

test("every @font-face url resolves to a bundled file (fonts.css sits next to fonts/ in every bundle)", () => {
  for (const f of fontFaces(readFileSync(FONTS_CSS, "utf8"))) {
    for (const u of f.urls) assert.ok(existsSync(join(PANEL_UI, u)), `${u} is not in panel-ui/`);
  }
});

test("bundled font files are byte copies of guide-ar/fonts, each family folder carries its OFL licence, nothing extra", () => {
  const bundled = walk(join(PANEL_UI, "fonts"), () => true).map((p) => p.slice(join(PANEL_UI, "fonts").length + 1).replace(/\\/g, "/")).sort();
  const want = Object.values(EXPECTED)
    .flatMap((e) => [...Object.values(e.files).map((f) => `${e.dir}/${f}`), `${e.dir}/OFL.txt`])
    .sort();
  assert.deepEqual(bundled, want);
  for (const rel of bundled) {
    const a = readFileSync(join(PANEL_UI, "fonts", rel));
    const b = readFileSync(join(VENDORED, rel));
    assert.ok(a.equals(b), `${rel} differs from guide-ar/fonts/${rel}`);
  }
  for (const e of Object.values(EXPECTED)) {
    const ofl = readFileSync(join(PANEL_UI, "fonts", e.dir, "OFL.txt"), "utf8");
    assert.match(ofl, /SIL Open Font License, Version 1\.1/, e.dir);
  }
  assert.ok(readdirSync(join(PANEL_UI, "fonts")).every((d) => Object.values(EXPECTED).some((e) => e.dir === d)));
});

test("the font stylesheet only declares faces: if a host ignores @font-face, nothing else is lost (the token stacks fall back)", () => {
  const flat = readFileSync(FONTS_CSS, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/@font-face\s*\{[^}]*\}/g, "").trim();
  assert.equal(flat, "", "fonts.css holds @font-face rules only; the families are used through the token stacks");
});
