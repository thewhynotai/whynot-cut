import { test } from "node:test";
import assert from "node:assert/strict";
import { applyHostTheme, backgroundVar, parseColor } from "../src/theme.ts";

test("parseColor: hex, rgb() and {r,g,b} objects; anything else is null", () => {
  assert.deepEqual(parseColor("#161616"), { r: 22, g: 22, b: 22 });
  assert.deepEqual(parseColor("161616"), { r: 22, g: 22, b: 22 });
  assert.deepEqual(parseColor("#fff"), { r: 255, g: 255, b: 255 });
  assert.deepEqual(parseColor("rgb(50, 50, 50)"), { r: 50, g: 50, b: 50 });
  assert.deepEqual(parseColor("rgba(50,60,70,1)"), { r: 50, g: 60, b: 70 });
  assert.deepEqual(parseColor({ r: 40, g: 41, b: 42 }), { r: 40, g: 41, b: 42 });
  assert.deepEqual(parseColor({ red: 40, green: 41, blue: 42, alpha: 255 }), { r: 40, g: 41, b: 42 });
  for (const bad of [{}, null, undefined, "", "blue", "#12", "#gggggg", 5, [], { r: 1 }, { r: "a", g: 1, b: 1 }, { r: 300, g: 0, b: 0 }, { r: NaN, g: 0, b: 0 }]) {
    assert.equal(parseColor(bad), null, JSON.stringify(bad));
  }
});

test("backgroundVar: a dark host colour becomes the --twn-bg value; light or unusable ones keep the brand dark default", () => {
  assert.equal(backgroundVar("#323232"), "#323232");
  assert.equal(backgroundVar({ r: 50, g: 50, b: 50 }), "#323232");
  assert.equal(backgroundVar("#f5f5f5"), null, "white text on a light background would be unreadable");
  assert.equal(backgroundVar({}), null, "Premiere 26.5.2 returned {} in the live spike");
  assert.equal(backgroundVar(undefined), null);
});

function fakeDoc() {
  const set: Record<string, string> = {};
  return { set, doc: { documentElement: { style: { setProperty: (k: string, v: string) => void (set[k] = v) } } } };
}

test("applyHostTheme sets --twn-bg from getBackgroundColor() when it gives a usable colour", () => {
  const { set, doc } = fakeDoc();
  assert.equal(applyHostTheme(doc, { getBackgroundColor: () => "#262626" }), "#262626");
  assert.deepEqual(set, { "--twn-bg": "#262626" });
});

test("applyHostTheme leaves the stylesheet default alone for {}, missing function, throwing function, light colour", () => {
  for (const host of [{ getBackgroundColor: () => ({}) }, {}, undefined, { getBackgroundColor: () => { throw new Error("nope"); } }, { getBackgroundColor: () => "#ffffff" }]) {
    const { set, doc } = fakeDoc();
    assert.equal(applyHostTheme(doc, host), null);
    assert.deepEqual(set, {});
  }
});
