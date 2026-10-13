// src/commands.ts at runtime: neutralise() holds back only the command span of an engine or host text; the cause and
// the remedy stay. The guard test (test/no-commands.test.ts) uses the same detector.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { commandIn, commandSpans, hasCommand, neutralise } from "../src/commands.ts";
import { scrubToken } from "../src/diagnostics.ts";
import { PANEL_UI } from "./tokens-util.ts";

test("neutralise: a text with no command comes back unchanged", () => {
  for (const s of ["Premiere is busy.", "Open your Claude session to start the engine, then wait a moment.", "تعذّر الاتصال.", "A client folder holds the `assets` folder."]) {
    assert.equal(neutralise(s), s);
  }
});

test("neutralise: only the command span (and the verb that leads into it) goes; the cause and the remedy stay", () => {
  const cases: Array<[string, string]> = [
    ["Start it from your Claude session (reel serve --ensure).", "Start it from your Claude session."],
    ["Bridge not ready. In your Claude session run `reel doctor`.", "Bridge not ready. In your Claude session."],
    ["Engine down: start it with reel serve --ensure, then try again.", "Engine down: start it, then try again."],
    ["Open Claude Code and press Try again.", "Open Claude and press Try again."],
    ["Open Claude Code, then press Try again.", "Open Claude, then press Try again."],
    ["تعذّر الاتصال. في جلسة Claude شغّل الأمر: reel doctor ثم أعد المحاولة.", "تعذّر الاتصال. في جلسة Claude ثم أعد المحاولة."],
    ["The link failed (see whynotcut://engine/start). Press Try again.", "The link failed. Press Try again."],
    ["Use the reel CLI for this step for now (e.g. `reel approve` / `reel build`); the panel will do it later.", "Use the reel CLI for this step for now; the panel will do it later."],
  ];
  for (const [raw, shown] of cases) {
    assert.equal(neutralise(raw), shown, raw);
    assert.equal(hasCommand(neutralise(raw)), false, raw);
  }
});

test("neutralise: nothing meaningful left -> null (the caller shows its own localised sentence)", () => {
  for (const s of ["reel serve --ensure", "Run: reel doctor", "REEL DOCTOR", "npx x", "claude auth login", "شغّل الأمر", "`reel doctor`", "whynotcut://engine/start", "brew install ffmpeg and retry"]) {
    assert.equal(neutralise(s), null, s);
  }
  assert.equal(neutralise(undefined), null);
  assert.equal(neutralise(42), null);
});

test("commandSpans: spans are in the original text's indices, also with tashkeel, tatweel and zero-width characters", () => {
  const s = "قبل شغِّـل الأمر​: reel doctor بعد";
  const spans = commandSpans(s);
  assert.ok(spans.length >= 1);
  const span = spans[0]!;
  assert.equal(s.slice(span.start, span.end).replace(/[ً-ٟـ​]/g, ""), "شغل الأمر: reel doctor");
  assert.equal(commandIn("Your reel is ready."), null);
  assert.equal(commandIn("reel doctor"), "command");
  assert.equal(commandIn("`a b`"), "backticked-command");
  assert.equal(commandIn("Claude Code"), "claude-code");
  assert.equal(commandIn("whynotcut://x"), "launcher-link");
  assert.equal(commandIn("type: something"), "lead-in");
});

test("ONE detector: render.ts, mount.ts and kit/toast.ts use src/commands.ts and keep no command regex of their own; the guard imports the same one", () => {
  for (const f of ["render.ts", "mount.ts", "kit/toast.ts"]) {
    const src = readFileSync(join(PANEL_UI, "src", f), "utf8");
    assert.match(src, /from "\.\.?\/(?:\.\.\/)?commands\.ts"/, f);
    assert.doesNotMatch(src, /function hasCommand|claude\\s\*code/, `${f} keeps its own detector`);
  }
  assert.match(readFileSync(join(PANEL_UI, "test", "no-commands-scan.ts"), "utf8"), /from "\.\.\/src\/commands\.ts"/);
});

test("scrubToken (DaemonSource's log lines and the panel's own): the known token and any token-looking 64-hex run become [token]", () => {
  const tok = "f".repeat(64);
  assert.equal(scrubToken(`key ${tok} refused`, tok), "key [token] refused");
  const other = "0123456789ABCDEF".repeat(4);
  assert.equal(scrubToken(`saw ${other}.`), "saw [token].");
  assert.equal(scrubToken("sha256:4b7a1f03c6e9 is short"), "sha256:4b7a1f03c6e9 is short");
  assert.equal(scrubToken("a".repeat(65)), "a".repeat(65), "a longer hex run is not a token");
});
