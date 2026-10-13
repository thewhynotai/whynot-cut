// C2.2 (Addendum C1.4): no command text on the editor's screen. Every problem is one plain sentence and one fix button
// (Start engine / Try again / Copy diagnostics); commands live only in the log drawer and the Copy diagnostics payload.
// The detector is src/commands.ts, the SAME one the panel uses at runtime; the source scan reads string literals with
// the TypeScript compiler's parser (test/no-commands-scan.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { AR, EN } from "../src/i18n.ts";
import { initialUi, render } from "../src/render.ts";
import { sampleState, SCENARIOS } from "../src/mock.ts";
import { kitGallery } from "../src/kit/gallery.ts";
import { COMMAND_FILES, LOG_TUPLE_FILE, commandIn, commandLiterals, commandsOnScreen, parseSources, pluginTexts, scannedPluginFiles, screenText, textsOf, tsFiles } from "./no-commands-scan.ts";
import { PANEL_UI } from "./tokens-util.ts";

const stripRule = (hits: string[]) => hits.map((s) => s.replace(/^[a-z-]+: /, ""));

test("the guard's rules (src/commands.ts): programs with an argument, backticked commands, whynotcut:// links, the product name with 'Code', 'run:' and Arabic lead-ins; single tokens and plain words pass", () => {
  for (const bad of [
    "reel serve --ensure",
    "Start it from your Claude session (reel serve --ensure).",
    "In your session run `reel doctor`.",
    "claude -p --safe-mode",
    "npm run dev:build",
    "python -m reel",
    "python3 -m reel doctor",
    "Use `node scripts/x.mjs` now",
    "Open Claude Code",
    "open claude code",
    "open Claude Code",
    "In your Claude session run:",
    "في جلسة Claude شغّل الأمر:",
    // C2.2 review round 1 blind spots: case, NBSP and tab, other programs, the Arabic family with or without tashkeel
    "Reel doctor",
    "REEL DOCTOR",
    "reel serve",
    "reel\tdoctor",
    "npx x",
    "py -m reel",
    "pip install whynot-cut",
    "git pull",
    "powershell -File setup.ps1",
    "pwsh ./setup.ps1",
    "winget install ffmpeg",
    "brew install ffmpeg",
    "node dev.js",
    "claude auth login",
    "شغل الأمر",
    "شغِّل الأمر",
    "نفّذ الأمر",
    "اكتب الأمر",
    "الصق الأمر",
    "whynotcut://engine/start",
    "Open WhyNotCut://engine/start now.",
    "a run of `two words` in backticks",
    "a run of `two words` with NBSP",
  ]) {
    assert.ok(commandIn(bad), `not caught: ${bad}`);
  }
  for (const ok of [
    "A client folder holds the `assets` and `data` folders.",
    "The engine's connection file `engine.json` is incomplete.",
    "Claude",
    "Open your Claude session to start the engine, then wait a moment.",
    "58 s vertical clip",
    "a 58 s reel.",
    "Your reel is ready.",
    "reel-profile",
    "Python is required.",
    "تشغيل المحرّك",
    "افتح جلسة Claude لتشغيل المحرّك، ثم انتظر قليلًا.",
    "Copy the diagnostics and send them to support.",
    "Do this step in your Claude session for now — it will work from the panel after the next update.",
    "Press Try again.",
  ]) {
    assert.equal(commandIn(ok), null, `false alarm: ${ok}`);
  }
});

test("the source scan reads literals with the compiler and folds what builds one text: + chains, joined arrays, templates (${...} = a space), escapes", () => {
  const src = [
    'const a = "reel doctor";',
    "const b = `Run \\`reel setup\\` now ${x}`;",
    'const c = "the `assets` folder";',
    "// a comment: reel serve --ensure",
    'const d = "reel" + " serve";',
    'const e = ["reel", "serve"].join(" ");',
    'const f = `reel${" "}doctor`;',
    'const g = "reel\\x20serve";',
    'const h = "reel\\u00a0doctor";',
    'const i = "Reel" + " " + "doctor";',
    'const j = ["npx", "x"].join("\\u0020");',
    "const k = `${a}py -m reel`;",
    'const l = "claude" + " auth " + "login";',
    'const m = "شغل" + " الأمر";',
    'const n = "اكتب الأمر";',
    'const o = "REEL DOCTOR";',
    // a regular expression after => or ) never desynchronises the scan: the literal after it is still read
    'const p = (x: string) => /"/.test(x) ? "a" : "b"; const q = "npm run build";',
    'if (ok) /\'/.test(s); const r = "git pull";',
    'const s2 = ["reel", flag].join(" ");',
  ].join("\n");
  const hits = stripRule(commandLiterals(src));
  for (const want of [
    "reel doctor",
    "Run `reel setup` now  ",
    "reel serve",
    "reel doctor",
    "reel doctor",
    "Reel doctor",
    "npx x",
    " py -m reel",
    "claude auth login",
    "شغل الأمر",
    "اكتب الأمر",
    "REEL DOCTOR",
    "npm run build",
    "git pull",
  ]) {
    assert.ok(hits.includes(want), `not caught: ${JSON.stringify(want)} in ${JSON.stringify(hits)}`);
  }
  assert.ok(!hits.some((h) => h.includes("assets")), "a single backticked token passes");
  assert.ok(!hits.some((h) => h.includes("comment")), "comments are not literals");
  // the joined array with a non-literal part reads it as a space: "reel  " (no argument) is not a command
  assert.ok(!hits.includes("reel  "));
});

test("the [level, text] tuple exemption holds only in mock.ts (its sample log is log drawer data)", () => {
  const src = 'const log = [["info", "reel plan --root X"], ["warn", `reel build ${id}`]]; const shown = "reel doctor";';
  assert.deepEqual(stripRule(commandLiterals(src, LOG_TUPLE_FILE)), ["reel doctor"]);
  assert.deepEqual(stripRule(commandLiterals(src, "render.ts")).sort(), ["reel build  ", "reel doctor", "reel plan --root X"].sort());
  assert.equal(LOG_TUPLE_FILE, "mock.ts");
});

test("C2.2 guard: no i18n value (EN and AR) and no string literal in panel-ui/src/** or premiere-uxp/src/** shows a command; only the log drawer and diagnostics may hold one", () => {
  const files = tsFiles(join(PANEL_UI, "src"));
  assert.ok(files.includes("render.ts") && files.includes("daemon-source.ts") && files.includes("kit/gallery.ts") && files.includes("mock.ts") && files.includes("commands.ts"), "the scan is recursive");
  const uxp = tsFiles(join(PANEL_UI, "..", "premiere-uxp", "src"));
  assert.ok(uxp.includes("offline-source.ts") && uxp.includes("shell.ts") && uxp.includes("uxp-host.ts") && uxp.includes("ops/premiere.ts"), "the Premiere plugin's sources are scanned too (ops/* included)");
  assert.deepEqual([...COMMAND_FILES], ["kit/log.ts", "diagnostics.ts"]);
  assert.deepEqual(commandsOnScreen(PANEL_UI), []);
  // the commands moved to diagnostics.ts (exempt), so the payload can still name them
  assert.match(readFileSync(join(PANEL_UI, "src", "diagnostics.ts"), "utf8"), /reel serve --ensure/);
  // and the scan does see diagnostics.ts's commands when it is not exempt (the exemption is what lets them through)
  const diag = parseSources({ "diagnostics.ts": readFileSync(join(PANEL_UI, "src", "diagnostics.ts"), "utf8") }).get("diagnostics.ts")!;
  assert.ok(textsOf(diag, "diagnostics.ts").some((t) => commandIn(t)));
});

test("the obsolete command keys are gone; the fix buttons have identical keys in EN and AR", () => {
  for (const t of [EN, AR] as Record<string, string>[]) assert.ok(!("offline.hint" in t), "offline.hint is obsolete");
  for (const k of ["action.start_engine", "action.retry", "actions.diagnostics", "notice.send_diagnostics"] as const) {
    assert.ok(EN[k].trim() && AR[k].trim(), k);
    assert.match(AR[k], /[؀-ۿ]/, `${k}: Arabic label`);
  }
  assert.equal(EN["action.start_engine"], "Start engine");
  assert.equal(AR["action.start_engine"], "تشغيل المحرّك");
  assert.equal(AR["action.retry"], "إعادة المحاولة");
  assert.equal(AR["checklist.label"], "قائمة الإعداد");
  assert.match(EN["notice.send_diagnostics"], /send them to support/);
});

test("screenText reads the text AND the attributes a person reads or hears, outside the log drawer", () => {
  assert.ok(commandIn(screenText('<button aria-label="Run reel doctor">x</button>')), "aria-label");
  assert.ok(commandIn(screenText('<span title="reel serve --ensure">i</span>')), "title");
  assert.ok(commandIn(screenText('<input placeholder="npx whynot">')), "placeholder");
  assert.ok(commandIn(screenText("<p>Open Claude&nbsp;Code</p>")), "an entity is decoded");
  assert.equal(commandIn(screenText('<section class="sec sec-log"><li>reel doctor</li></section><p>Fine.</p>')), null, "the log drawer may hold one");
});

test("rendered panel: no command and no backtick anywhere outside the log drawer (text and attributes), in every scenario, online and offline, EN and AR", () => {
  const codes = ["no_engine", "down", "unreachable", "bad_engine_json", "auth", "no_welcome", "lost", "refused_host", "refused_busy", "refused", "protocol", "too_large", "blocked", "connecting", "stopped", "something_new"];
  const notices = [
    { kind: "error" as const, text: "x", how: "Run `reel doctor` now." },
    { kind: "error" as const, text: "Open Claude Code and run claude auth login.", how: "شغّل الأمر: reel doctor" },
    { kind: "error" as const, text: "REEL DOCTOR", how: "npx x" },
  ];
  for (const lang of ["en", "ar"] as const) {
    const t = lang === "ar" ? AR : EN;
    for (const scenario of SCENARIOS) {
      for (const link of [null, ...codes.map((code) => ({ code, retry_in_s: 2 }))]) {
        for (const notice of notices) {
          const s = sampleState(lang, scenario);
          s.connection.engine = link ? "offline" : s.connection.engine;
          const ui = { ...initialUi(), confirmRebuild: true, logOpen: true, link, notice };
          const html = render(s, t, ui);
          const where = `${lang}/${scenario}/${link?.code ?? "online"}/${notice.text}`;
          assert.equal(commandIn(screenText(html)), null, where);
          assert.ok(!screenText(html).includes("`"), `${where}: a backtick on screen`);
        }
      }
    }
  }
});

test("kit gallery: no command anywhere outside the log drawer, text and attributes (EN and AR)", () => {
  for (const lang of ["en", "ar"] as const) assert.equal(commandIn(screenText(kitGallery(lang))), null, lang);
});

// ---------------------------------------------------------------------------------- C2.2 review round 2: the guard folds more

test("C2.2 r2 guard: + chains with parentheses, .concat(), += on a declared literal and ${\"literal\"} inside a template fold into one text", () => {
  const src = [
    'const a = ("reel" + " ") + "doctor";',
    'const b = "re" + ("el" + " serve --ensure");',
    'const c = "reel".concat(" previews");',
    'const d = "reel ".concat("serve", " --ensure");',
    'const e = ["npx"].concat(["x"]).join(" ");',
    'let f = "reel"; f += " transcribe";',
    'const g = "claude"; g += " auth login";',
    'const h = `${"reel"} doctor`;',
    'const i = `${"re" + "el"} setup`;',
    'const j = `${("reel")} build`;',
    'const k = "safe".concat(flag);',
  ].join("\n");
  const hits = stripRule(commandLiterals(src));
  for (const want of ["reel doctor", "reel serve --ensure", "reel previews", "reel transcribe", "claude auth login", "reel setup", "reel build"]) {
    assert.ok(hits.some((h) => h.replace(/\s+/g, " ").trim() === want), `not caught: ${want} in ${JSON.stringify(hits)}`);
  }
  assert.ok(hits.some((h) => h.replace(/\s+/g, " ").trim() === "npx x"), `not caught: npx x in ${JSON.stringify(hits)}`);
  assert.ok(!hits.some((h) => h.startsWith("safe")), "a non-literal part reads as a space");
});

test("C2.2 r2 guard: full-width text is caught (NFKC before matching), in literals and in the string table check", () => {
  assert.ok(stripRule(commandLiterals('const a = "ｒｅｅｌ ｄｏｃｔｏｒ";')).length === 1);
  assert.ok(commandIn("Ｒｕｎ ｒｅｅｌ　ｓｅｒｖｅ －－ｅｎｓｕｒｅ"));
});

test("C2.2 r2 guard: the mock.ts exemption covers only its log-lines array (a `log` array of [level, text] tuples)", () => {
  const src = [
    'const flavor = { log: [["info", "reel plan --root X"]], qc: [["info", "reel doctor"]] };',
    'const log = [["warn", "reel build C0239"]];',
    'const other = [["error", "npx whynot"]];',
  ].join("\n");
  assert.deepEqual(stripRule(commandLiterals(src, LOG_TUPLE_FILE)).sort(), ["npx whynot", "reel doctor"]);
  assert.equal(stripRule(commandLiterals(src, "render.ts")).length, 4, "no exemption outside mock.ts");
});

test("C2.2 r2 guard: screenText also reads value, aria-description and single-quoted attributes", () => {
  assert.ok(commandIn(screenText('<input value="reel doctor">')), "value");
  assert.ok(commandIn(screenText('<div aria-description="Run reel serve --ensure">x</div>')), "aria-description");
  assert.ok(commandIn(screenText("<span title='reel serve --ensure'>i</span>")), "single-quoted");
  assert.ok(commandIn(screenText("<input placeholder='npx whynot'>")), "single-quoted placeholder");
  assert.equal(commandIn(screenText('<div data-value="reel doctor">ok</div>')), null, "a data-* attribute is not read");
});

test("C2.2 r2 guard: the Premiere plugin's index.html and manifest.json are scanned (labels, text and attributes)", () => {
  assert.deepEqual(pluginTexts('{"name":"WhyNot Cut","entrypoints":[{"label":{"default":"Run reel doctor"}}],"main":"index.html"}', "manifest.json").filter((t) => commandIn(t)), ["Run reel doctor"]);
  assert.ok(pluginTexts('<!doctype html><body><p title="x">Type: reel doctor</p></body>', "index.html").some((t) => commandIn(t)));
  assert.ok(pluginTexts('<script>var a = "reel doctor";</script><style>.x{}</style><p>Fine.</p>', "index.html").every((t) => !commandIn(t)), "script and style bodies are not screen text");
  const files = scannedPluginFiles(PANEL_UI);
  assert.deepEqual(files.map((f) => f.replace(/\\/g, "/").replace(/^.*premiere-uxp\//, "")).sort(), ["plugin/index.html", "plugin/manifest.json"]);
});
