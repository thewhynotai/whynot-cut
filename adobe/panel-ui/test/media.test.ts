// The shared media helpers (src/media.ts): ONE local-thumbnail check and ONE frame-aspect function, used by both the
// panel (render.ts) and the component kit (kit/frames.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SAFE_IMG, aspectPct, isSafeImg } from "../src/media.ts";
import { PANEL_UI } from "./tokens-util.ts";

test("isSafeImg: data:image, file:/// (empty host), plugin: and local paths only; never the network or a UNC share", () => {
  for (const ok of [
    "data:image/png;base64,AAAA",
    "data:image/svg+xml;utf8,%3Csvg%3E",
    "file:///C:/x.png",
    "FILE:///C:/x/f.png",
    "file:///Users/ed/frames/a.png",
    "plugin:/frames/a.png",
    "frames/a.png",
    "./a.png",
    "../out/a.png",
    "/Users/ed/a.png",
    "my frames/a b.png",
  ]) {
    assert.ok(isSafeImg(ok), `refused a local thumbnail: ${ok}`);
  }
  for (const bad of [
    "http://evil.example/a.png",
    "https://evil.example/a.png",
    "HTTPS://evil.example/a.png",
    "//evil.example/a.png",
    "\\\\evil.com\\a.png",
    "\\evil.com\\a.png",
    "/\\evil.com/a.png",
    "\\/evil.com/a.png",
    "file://evil.com/share/a.png",
    "file://localhost/C:/x.png",
    "file:////evil.com/share/a.png",
    "file:///\\\\evil.com\\a.png",
    "file:/C:/x.png",
    "file:C:/x.png",
    "javascript:alert(1)",
    "data:text/html,<b>x</b>",
    "ftp://x/a.png",
    "C:\\x.png",
    " https://evil.example/a.png",
    " //evil.example/a.png",
    "\u0001//evil.example/a.png",
    "/\t/evil.example/a.png",
    "/\n/evil.example/a.png",
    "",
  ]) {
    assert.ok(!isSafeImg(bad), `drew a thumbnail from ${JSON.stringify(bad)}`);
  }
  for (const notString of [null, undefined, 5, {}, ["frames/a.png"]]) assert.equal(isSafeImg(notString), false);
  assert.ok(SAFE_IMG instanceof RegExp);
});

test("aspectPct: height as % of width; 9:16 when w/h are absent or invalid; clamped to 40..300", () => {
  assert.equal(aspectPct(1080, 1920), 177.78);
  assert.equal(aspectPct(1080, 1350), 125);
  assert.equal(aspectPct(1920, 1080), 56.25);
  assert.equal(aspectPct(undefined, undefined), 177.78);
  assert.equal(aspectPct(0, 100), 177.78);
  assert.equal(aspectPct(Number.NaN, 5), 177.78);
  assert.equal(aspectPct("1080", "1350"), 177.78);
  assert.equal(aspectPct(100, 1000), 300);
  assert.equal(aspectPct(1000, 100), 40);
});

test("ONE SAFE_IMG and ONE aspectPct: render.ts and kit/frames.ts import them from src/media.ts and define neither", () => {
  for (const f of ["render.ts", "kit/frames.ts"]) {
    const src = readFileSync(join(PANEL_UI, "src", f), "utf8");
    assert.match(src, /from "\.\.?\/(?:\.\.\/)?media\.ts"/, `${f} does not import src/media.ts`);
    assert.doesNotMatch(src, /const SAFE_IMG\b|function aspectPct\b/, `${f} keeps its own copy`);
  }
});
