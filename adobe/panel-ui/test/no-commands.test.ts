// C2.2 (Addendum C1.4): no command text on the editor's screen. Every problem is one plain sentence and one fix button
// (Start engine / Try again / Copy diagnostics); commands live only in the log drawer and the Copy diagnostics payload.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { AR, EN } from "../src/i18n.ts";
import { initialUi, render } from "../src/render.ts";
import { sampleState, SCENARIOS } from "../src/mock.ts";
import { kitGallery } from "../src/kit/gallery.ts";
import { COMMAND_FILES, commandIn, commandLiterals, commandsOnScreen, tsFiles } from "./no-commands-scan.ts";
import { PANEL_UI } from "./tokens-util.ts";

test("the guard's rules: reel / claude / npm / python commands, backticked commands, 'Claude Code' and 'run:' lead-ins; single tokens and the product name pass", () => {
  for (const bad of [
    "reel serve --ensure",
    "Start it from your Claude session (reel serve --ensure).",
    "In your session run `reel doctor`.",
    "claude -p --safe-mode",
    "npm run dev:build",
    "python -m reel",
    "Use `node scripts/x.mjs` now",
    "Open Claude Code",
    "open claude code",
    "In your Claude session run:",
    "في جلسة Claude شغّل الأمر:",
  ]) {
    assert.ok(commandIn(bad), `not caught: ${bad}`);
  }
  for (const ok of [
    "A client folder holds the `assets` and `data` folders.",
    "The engine's connection file `engine.json` is incomplete.",
    "Claude",
    "Open your Claude session to start the engine, then wait a moment.",
    "58 s vertical clip",
    "reel-profile",
    "تشغيل المحرّك",
  ]) {
    assert.equal(commandIn(ok), null, `false alarm: ${ok}`);
  }
  // literals: template backticks are escaped in the source; log-line tuples ([level, text]) are log drawer data
  const src = [
    'const a = "reel doctor";',
    "const b = `Run \\`reel setup\\` now ${x}`;",
    'const log = [["info", "reel plan --root X"], ["warn", `reel build ${id}`]];',
    'const c = "the `assets` folder";',
    "// a comment: reel serve --ensure",
  ].join("\n");
  assert.deepEqual(commandLiterals(src).map((s) => s.replace(/^[^:]+: /, "")), ["reel doctor", "Run `reel setup` now §"]);
});

test("C2.2 guard: no i18n value (EN and AR) and no string literal in panel-ui/src/** shows a command; only the log drawer and diagnostics may hold one", () => {
  const files = tsFiles(join(PANEL_UI, "src"));
  assert.ok(files.includes("render.ts") && files.includes("daemon-source.ts") && files.includes("kit/gallery.ts") && files.includes("mock.ts"), "the scan is recursive");
  assert.deepEqual([...COMMAND_FILES], ["kit/log.ts", "diagnostics.ts"]);
  assert.deepEqual(commandsOnScreen(PANEL_UI), []);
  // the commands moved to diagnostics.ts (exempt), so the payload can still name them
  assert.match(readFileSync(join(PANEL_UI, "src", "diagnostics.ts"), "utf8"), /reel serve --ensure/);
});

test("the obsolete command keys are gone; the fix buttons have identical keys in EN and AR", () => {
  for (const t of [EN, AR] as Record<string, string>[]) assert.ok(!("offline.hint" in t), "offline.hint is obsolete");
  for (const k of ["action.start_engine", "action.retry", "actions.diagnostics"] as const) {
    assert.ok(EN[k].trim() && AR[k].trim(), k);
    assert.match(AR[k], /[؀-ۿ]/, `${k}: Arabic label`);
  }
  assert.equal(EN["action.start_engine"], "Start engine");
  assert.equal(AR["action.start_engine"], "تشغيل المحرّك");
});

test("rendered panel: no command and no backtick anywhere outside the log drawer, in every scenario, online and offline, EN and AR", () => {
  const codes = ["no_engine", "down", "unreachable", "bad_engine_json", "auth", "no_welcome", "lost", "refused_host", "refused_busy", "refused", "protocol", "too_large", "blocked", "connecting", "stopped", "something_new"];
  for (const lang of ["en", "ar"] as const) {
    const t = lang === "ar" ? AR : EN;
    for (const scenario of SCENARIOS) {
      for (const link of [null, ...codes.map((code) => ({ code, retry_in_s: 2 }))]) {
        const s = sampleState(lang, scenario);
        s.connection.engine = link ? "offline" : s.connection.engine;
        const ui = { ...initialUi(), confirmRebuild: true, link, notice: { kind: "error" as const, text: "x", how: "Run `reel doctor` now." } };
        const html = render(s, t, ui);
        const onScreen = html.replace(/<section class="sec sec-log">[\s\S]*?<\/section>/, "");
        assert.equal(commandIn(onScreen.replace(/<[^>]*>/g, " ")), null, `${lang}/${scenario}/${link?.code ?? "online"}`);
        assert.ok(!onScreen.includes("`"), `${lang}/${scenario}: a backtick on screen`);
      }
    }
  }
});

test("kit gallery: no command anywhere outside the log drawer (EN and AR)", () => {
  for (const lang of ["en", "ar"] as const) {
    const html = kitGallery(lang).replace(/<ul class="kit-log-lines"[\s\S]*?<\/ul>/g, "");
    assert.equal(commandIn(html.replace(/<[^>]*>/g, " ")), null, lang);
  }
});
