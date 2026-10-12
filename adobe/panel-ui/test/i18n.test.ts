import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { AR, EN, fmt, stringsFor } from "../src/i18n.ts";
import { PANEL_UI } from "./tokens-util.ts";
import { hardCoded, sentences } from "./literal-scan.ts";
import { DAEMON_SOURCE_STRINGS_TO_MIGRATE_IN_B_T2 } from "./i18n-debt.ts";

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
  // technical left-to-right runs, identical in both languages: the build stamp and the backup file-name pattern
  assert.equal(EN["log.build"], "WhyNot Cut {version} · build {build}");
  assert.equal(AR["log.build"], EN["log.build"]);
  assert.equal(EN["rebuild.backup_name"], "name_prev_date-time.prproj");
  assert.equal(AR["rebuild.backup_name"], EN["rebuild.backup_name"]);
});

test("stringsFor picks the table; fmt fills placeholders", () => {
  assert.equal(stringsFor("ar"), AR);
  assert.equal(stringsFor("en"), EN);
  assert.equal(fmt("Step {n} of {of}", { n: 2, of: 7 }), "Step 2 of 7");
  assert.equal(fmt("no placeholders", { n: 1 }), "no placeholders");
});

// ---- Arabic copy (Addendum B3): clear MSA, the English UI term in parentheses the first time ----

/** The UI terms an Arabic editor meets in Premiere / the guide in English: each label carries it once, in parentheses. */
const AR_TERMS = ["Pipeline", "Approval", "QC", "Transcript", "Plan", "Approve", "Build", "Frames", "Handoff", "Rebuild", "Playhead", "Engine", "Host"];

test("Arabic: every key UI term carries its English name in parentheses on first use (the label), not in every sentence", () => {
  const values = Object.values(table("ar")) as string[];
  for (const term of AR_TERMS) {
    const uses = values.filter((v) => v.includes(`(${term})`)).length;
    assert.ok(uses >= 1, `no Arabic string carries "(${term})"`);
    assert.ok(uses <= 2, `"(${term})" is repeated in ${uses} strings: only the label carries it`);
  }
  const ar = table("ar");
  assert.equal(ar["section.pipeline"], "مراحل العمل (Pipeline)");
  assert.equal(ar["section.qc"], "الإطارات وفحص الجودة (QC)");
  assert.equal(ar["step.transcript"], "التفريغ النصي (Transcript)");
  assert.equal(ar["step.frames"], "الإطارات (Frames)");
  assert.equal(ar["actions.rebuild"], "إعادة البناء (Rebuild)");
  assert.equal(ar["status.noclient"], "لم يُختَر أي عنصر");
  assert.equal(ar["log.lines"], "عدد الأسطر: {n}");
  assert.match(ar["qc.hint"] as string, /مؤشر التشغيل \(Playhead\)/);
});

// ---- no hard-coded user-visible strings in the render code ----

test("the literal scanner sees text, attributes, nested templates, word literals and helper arguments; it skips regexes, comments, keys and commands", () => {
  const sample = [
    "// <p>comment</p>",
    "const a = esc(x).replace(/</g, \"&lt;\").replace(/\"/g, '&quot;');",
    "const b = `<p>${esc(t[\"k.key\"])}</p><b>Hello</b>`;",
    "const c = `<i title=\"Close\">${x ? `<em>Inner</em>` : \"\"}</i>`;",
    "const d = '<span>' + esc(v) + '</span>';",
    "const e = ltr(`WhyNot Cut ${v} · build ${b}`);",
    "const f = cmdRow(\"name_prev.prproj\") + cmdRow(\"reel doctor\") + cls(\"twn-rtl\") + t[\"pill.engine\"];",
    "const g = x ? \" disabled\" : \"\";",
  ].join("\n");
  assert.deepEqual(hardCoded(sample).sort(), ["Hello", "Inner", 'title="Close"', "WhyNot Cut § · build §", "name_prev.prproj"].sort());
});

test("no hard-coded user-visible strings in panel-ui/src render code (render.ts, mount.ts, kit/*.ts): all copy comes from the table", () => {
  const kit = readdirSync(join(PANEL_UI, "src", "kit")).filter((f) => f.endsWith(".ts")).map((f) => `kit/${f}`);
  assert.ok(kit.length >= 10, "the component kit is scanned");
  for (const f of ["render.ts", "mount.ts", ...kit]) {
    const found = hardCoded(readFileSync(join(PANEL_UI, "src", f), "utf8"));
    assert.deepEqual(found, [], `${f}: ${found.join(" | ")}`);
  }
});

test("i18n debt: DaemonSource's own user-visible strings are exactly the documented to-migrate-in-B-T2 list", () => {
  const found = [...new Set(sentences(readFileSync(join(PANEL_UI, "src", "daemon-source.ts"), "utf8")))];
  const debt = [...DAEMON_SOURCE_STRINGS_TO_MIGRATE_IN_B_T2];
  assert.deepEqual(found.filter((s) => !debt.includes(s)), [], "a new hard-coded string in daemon-source.ts: put it in the string table");
  assert.deepEqual(debt.filter((s) => !found.includes(s)), [], "a debt entry no longer exists in daemon-source.ts: remove it from test/i18n-debt.ts");
  assert.ok(readFileSync(join(PANEL_UI, "test", "i18n-debt.ts"), "utf8").includes("to migrate in B-T2"));
});
