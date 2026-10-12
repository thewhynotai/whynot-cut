import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { AR, EN, fmt, stringsFor } from "../src/i18n.ts";
import { PANEL_UI } from "./tokens-util.ts";

const table = (lang: "en" | "ar") => JSON.parse(readFileSync(join(PANEL_UI, "i18n", `${lang}.json`), "utf8")) as Record<string, unknown>;

test("ONE string table: i18n/en.json and i18n/ar.json have identical keys, every value a non-empty string", () => {
  const en = table("en");
  const ar = table("ar");
  assert.deepEqual(Object.keys(ar).sort(), Object.keys(en).sort());
  assert.ok(Object.keys(en).length >= 96, "every string migrated from the old TS tables (96 keys)");
  for (const [lang, t] of [["en", en], ["ar", ar]] as const) {
    for (const [k, v] of Object.entries(t)) assert.ok(typeof v === "string" && v.trim().length > 0, `${lang}.${k} is empty or not a string`);
  }
});

test("i18n.ts is only the loader/typing: EN/AR are the JSON tables, and no string table is left in the TS", () => {
  assert.deepEqual({ ...EN }, table("en"));
  assert.deepEqual({ ...AR }, table("ar"));
  const src = readFileSync(join(PANEL_UI, "src", "i18n.ts"), "utf8");
  assert.match(src, /from "\.\.\/i18n\/en\.json"/);
  assert.match(src, /from "\.\.\/i18n\/ar\.json"/);
  assert.doesNotMatch(src, /[\u0600-\u06FF]/, "no Arabic copy in i18n.ts");
  assert.doesNotMatch(src, /"[a-z]+\.[a-z_.]+"\s*:\s*"/, "no key: value string entries in i18n.ts");
});

test("placeholders match between EN and AR", () => {
  const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");
  for (const k of Object.keys(EN) as (keyof typeof EN)[]) assert.equal(ph(AR[k]), ph(EN[k]), `placeholders differ in ${k}`);
});

test("commands in `backticks` are identical in EN and AR (they stay left-to-right, never translated)", () => {
  const cmds = (s: string) => (s.match(/`[^`]+`/g) ?? []).sort().join(",");
  for (const k of Object.keys(EN) as (keyof typeof EN)[]) assert.equal(cmds(AR[k]), cmds(EN[k]), k);
});

test("Arabic uses Western digits only (no Arabic-Indic or Persian digits)", () => {
  for (const [k, v] of Object.entries(AR)) assert.doesNotMatch(v, /[\u0660-\u0669\u06F0-\u06F9]/, k);
});

test("the string 'Claude Code' never appears in a string table", () => {
  for (const t of [EN, AR]) for (const v of Object.values(t)) assert.ok(!/claude\s*code/i.test(v), v);
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

// ---- no hard-coded user-visible strings in the render code ----

/** The static text of every string and template literal in a TS source (template expressions become "§"). Comments
 *  and regular expressions are skipped. Small on purpose: enough for the panel's own render code. */
export function literals(src: string): string[] {
  const out: string[] = [];
  let i = 0;
  let prev = "";
  const n = src.length;
  function template(): string {
    // at the opening backtick
    let text = "";
    i++;
    while (i < n && src[i] !== "`") {
      if (src[i] === "\\") {
        text += src.slice(i, i + 2);
        i += 2;
      } else if (src[i] === "$" && src[i + 1] === "{") {
        i += 2;
        code(true);
        text += "§";
      } else text += src[i++];
    }
    i++;
    return text;
  }
  function quoted(q: string): string {
    let text = "";
    i++;
    while (i < n && src[i] !== q) {
      if (src[i] === "\\") {
        text += src.slice(i, i + 2);
        i += 2;
      } else text += src[i++];
    }
    i++;
    return text;
  }
  /** Code until the end (or, inside a template expression, until its closing brace). */
  function code(inExpr: boolean): void {
    let depth = 0;
    while (i < n) {
      const c = src[i]!;
      if (c === "/" && src[i + 1] === "/") {
        i = src.indexOf("\n", i);
        if (i < 0) i = n;
      } else if (c === "/" && src[i + 1] === "*") {
        i = src.indexOf("*/", i) + 2;
      } else if (c === "/" && (prev === "" || "(,=:[!&|?{};+".includes(prev) || /\breturn$/.test(src.slice(0, i).trimEnd()))) {
        // a regular expression literal
        i++;
        let cls = false;
        while (i < n && (cls || src[i] !== "/")) {
          if (src[i] === "\\") i++;
          else if (src[i] === "[") cls = true;
          else if (src[i] === "]") cls = false;
          i++;
        }
        i++;
        prev = "/";
      } else if (c === "`") {
        out.push(template());
        prev = "`";
      } else if (c === '"' || c === "'") {
        out.push(quoted(c));
        prev = c;
      } else {
        if (c === "{") depth++;
        else if (c === "}") {
          if (inExpr && depth === 0) {
            i++;
            prev = "}";
            return;
          }
          depth--;
        }
        if (!/\s/.test(c)) prev = c;
        i++;
      }
    }
  }
  code(false);
  return out;
}

const LETTERS = /[A-Za-z\u0600-\u06FF]/;

/** Hard-coded words in an HTML-building literal: text between tags, and literal words in user-visible attributes. */
export function hardCoded(src: string): string[] {
  const found: string[] = [];
  for (const lit of literals(src)) {
    if (!/<[a-z/][^>]*>/i.test(lit) && !/^[^<]*>/.test(lit)) continue; // not markup
    for (const m of lit.matchAll(/\b(title|aria-label|placeholder|alt|aria-valuetext)="([^"]*)"/g)) {
      if (LETTERS.test(m[2]!.replace(/§/g, ""))) found.push(`${m[1]}="${m[2]}"`);
    }
    const text = lit.replace(/<[^>]*>/g, " ").replace(/^[^<]*>/, " ").replace(/<[^>]*$/, " ").replace(/§/g, " ");
    if (LETTERS.test(text)) found.push(text.trim());
  }
  return found;
}

test("the literal scanner sees text, attributes, templates and nested templates, and skips regexes and comments", () => {
  const sample = [
    "// <p>comment</p>",
    "const a = esc(x).replace(/</g, \"&lt;\").replace(/\"/g, '&quot;');",
    "const b = `<p>${esc(t[\"k\"])}</p><b>Hello</b>`;",
    "const c = `<i title=\"Close\">${x ? `<em>Inner</em>` : \"\"}</i>`;",
    "const d = '<span>' + esc(v) + '</span>';",
  ].join("\n");
  assert.deepEqual(hardCoded(sample).sort(), ["Hello", "Inner", 'title="Close"'].sort());
});

test("no hard-coded user-visible strings in panel-ui/src render code (render.ts, mount.ts): all copy comes from the table", () => {
  for (const f of ["render.ts", "mount.ts"]) {
    const found = hardCoded(readFileSync(join(PANEL_UI, "src", f), "utf8"));
    assert.deepEqual(found, [], `${f}: ${found.join(" | ")}`);
  }
});
