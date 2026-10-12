import { test } from "node:test";
import assert from "node:assert/strict";
import { AR, EN, fmt, stringsFor } from "../src/i18n.ts";

test("EN and AR have identical keys, all non-empty", () => {
  assert.deepEqual(Object.keys(AR).sort(), Object.keys(EN).sort());
  for (const [k, v] of Object.entries(EN)) assert.ok(v.trim().length > 0, `EN.${k} is empty`);
  for (const [k, v] of Object.entries(AR)) assert.ok(v.trim().length > 0, `AR.${k} is empty`);
});

test("placeholders match between EN and AR", () => {
  const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");
  for (const k of Object.keys(EN) as (keyof typeof EN)[]) assert.equal(ph(AR[k]), ph(EN[k]), `placeholders differ in ${k}`);
});

test("the string 'Claude Code' never appears in a string table", () => {
  for (const table of [EN, AR]) for (const v of Object.values(table)) assert.ok(!/claude\s*code/i.test(v), v);
});

test("product name is WhyNot Cut in both languages and the footer says Powered by thewhynot.ai", () => {
  assert.equal(EN["product.name"], "WhyNot Cut");
  assert.equal(AR["product.name"], "WhyNot Cut");
  assert.equal(EN["footer.powered"], "Powered by thewhynot.ai");
  assert.equal(AR["footer.powered"], "Powered by thewhynot.ai");
});

test("stringsFor picks the table; fmt fills placeholders", () => {
  assert.equal(stringsFor("ar"), AR);
  assert.equal(stringsFor("en"), EN);
  assert.equal(fmt("Step {n} of {of}", { n: 2, of: 7 }), "Step 2 of 7");
  assert.equal(fmt("no placeholders", { n: 1 }), "no placeholders");
});
