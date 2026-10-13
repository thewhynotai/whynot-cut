// src/commands.ts: TWO detectors with two jobs (C2.2 review round 2: no sentence surgery).
//   - looksLikeCommand / commandIn: high recall, for the guard test on OUR OWN strings (i18n, literals, rendered panel).
//   - containsRuntimeCommand: high precision, for engine and host texts at runtime. A text it flags is not shown at all:
//     the panel shows its own localized sentence instead and puts the raw words in the log (runtimeText -> null).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { commandIn, commandSpans, containsRuntimeCommand, looksLikeCommand, RUNTIME_MAX, runtimeText } from "../src/commands.ts";
import { scrubToken } from "../src/diagnostics.ts";
import { AR, EN } from "../src/i18n.ts";
import { DAEMON_SOURCE_STRINGS_TO_MIGRATE_IN_B_T2 } from "./i18n-debt.ts";
import { PANEL_UI } from "./tokens-util.ts";

/** The real texts that came out of round 1's sentence surgery broken, and the commands they held. */
const EARLIER_REAL_EXAMPLES = [
  "Start it from your Claude session (reel serve --ensure).",
  "Bridge not ready. In your Claude session run `reel doctor`.",
  "Engine down: start it with reel serve --ensure, then try again.",
  "تعذّر الاتصال. في جلسة Claude شغّل الأمر: reel doctor ثم أعد المحاولة.",
  "The link failed (see whynotcut://engine/start). Press Try again.",
  "Use the reel CLI for this step for now (e.g. `reel approve` / `reel build`); the panel will do it later.",
  "Premiere is not responding. Run reel doctor and press Try again.",
  "Open your Claude session, run reel serve --ensure.",
  "Open your Claude session, reel doctor.",
  "reel serve --ensure",
  "Run: reel doctor",
  "REEL DOCTOR",
  "Reel doctor",
  "npx x",
  "claude auth login",
  "Open Claude Code and run claude auth login.",
  "`reel doctor`",
  "whynotcut://engine/start",
  "brew install ffmpeg and retry",
  "Start it with reel serve --ensure --key abc, then press Try again.",
  "claude -p --safe-mode",
  "npm run dev:build",
  "python -m reel",
  "py -m reel",
  "pip install whynot-cut",
  "git pull",
  "powershell -File setup.ps1",
  "pwsh ./setup.ps1",
  "winget install ffmpeg",
  "node dev.js",
  "reel\tdoctor",
  "reel doctor",
];

/** Round 2's leaks: path-qualified programs, more programs, case-insensitive arguments, the variants. */
const LEAKS = [
  "~/…/reel previews",
  "~/.whynot-cut/engine/bin/reel previews",
  "./reel doctor",
  "C:\\…\\reel.exe doctor",
  "C:\\Users\\Yara\\.whynot-cut\\bin\\reel.exe doctor",
  "bash setup.sh",
  "sh -c 'reel doctor'",
  "curl -fsSL https://thewhynot.ai/install.sh | bash",
  "irm https://thewhynot.ai/install.ps1 | iex",
  "cd ~/WhyNotCut",
  "chmod +x reel",
  "taskkill /F /IM node.exe",
  "setx WHYNOT_HOME D:\\WhyNotCut",
  "echo %PATH%",
  "reel previews(C0239)",
  "reel previews C0239",
  "reel previews --video-id C0239",
];

/** The broad detector's own extra leaks (it flags these; the runtime detector need not). */
const BROAD_ONLY = ["/usr/local/bin/reel", "reel-doctor", "Run reel-doctor now."];

/** Normal sentences an engine or host sends: shown as they are. */
const PRECISION = [
  "The reel plan is ready",
  "The reel plan is ready.",
  "reel previews are ready",
  "reel build failed",
  "Claude install is incomplete",
  "Claude login expired",
  "Python 3.9 is required",
  "node 18 is required",
  "reel on-screen text",
  "reel follow-up",
  "reel 5.5 s hook",
  "Press Enter: it starts",
  "Type: Podcast",
  "Your reel is ready.",
  "a 58 s reel.",
  "Claude",
  "Open your Claude session to start the engine, then wait a moment.",
  "Reel plan: 14 statement bars, 6 checklist cards.",
  "Waiting for reel build.",
  "Node.js 18 is required.",
  "Open a PowerShell window.",
  "Git 2.40 is required.",
  "PowerShell 7 is required.",
  "Your Claude session is working on the plan.",
  "A client folder holds the `assets` and `data` folders.",
  "The engine's connection file `engine.json` is incomplete.",
  "Premiere is not responding.",
  "Copy the diagnostics and send them to support.",
  "graphics placed",
  "Premiere Pro 26.5.2",
  "58 s vertical clip from Episode 1, 31:10 to 32:08. Hook: the first coffee myth.",
  "تعذّر الاتصال.",
  "The reel doctor said nothing.",
];

test("runtime detector: precision table: a normal sentence from an engine or host is never flagged", () => {
  for (const s of PRECISION) assert.equal(containsRuntimeCommand(s), false, `false alarm: ${s}`);
});

test("runtime detector: recall table: every earlier real example and every round-2 leak is flagged", () => {
  for (const s of [...EARLIER_REAL_EXAMPLES, ...LEAKS, "/usr/local/bin/reel --version", "Run reel-doctor.", "Open Claude Code"]) {
    assert.equal(containsRuntimeCommand(s), true, `not caught: ${s}`);
  }
});

test("runtime detector: also with NBSP, tab, tashkeel, zero-width characters and full-width letters (NFKC)", () => {
  for (const s of ["reel doctor", "reel\tdoctor", "Run\u00a0reel\u00a0doctor and retry", "ｒｅｅｌ ｄｏｃｔｏｒ", "Ｃｌａｕｄｅ Ｃｏｄｅ", "شغِّـل الأمر\u200b: reel doctor ثم أعد"]) {
    assert.equal(containsRuntimeCommand(s), true, JSON.stringify(s));
  }
});

test("runtime detector: none of the panel's own sentences (i18n EN/AR, DaemonSource's texts) is flagged", () => {
  for (const t of [EN, AR] as Record<string, string>[]) for (const [k, v] of Object.entries(t)) assert.equal(containsRuntimeCommand(v), false, `${k}: ${v}`);
  for (const s of DAEMON_SOURCE_STRINGS_TO_MIGRATE_IN_B_T2) assert.equal(containsRuntimeCommand(s.replace(/§/g, "x")), false, s);
});

test("broad detector (the guard): catches everything it caught before, every leak, the precision table's commands, and the broad-only forms", () => {
  for (const s of [...EARLIER_REAL_EXAMPLES, ...LEAKS, ...BROAD_ONLY, "شغل الأمر", "In your Claude session run:", "type: something", "ｒｅｅｌ ｄｏｃｔｏｒ", "ｒｅｅｌ　ｄｏｃｔｏｒ"]) {
    assert.ok(looksLikeCommand(s), `not caught: ${s}`);
  }
  for (const ok of ["A client folder holds the `assets` and `data` folders.", "Claude", "Your reel is ready.", "a 58 s reel.", "reel-profile", "Python is required.", "Copy the diagnostics and send them to support.", "Press Try again."]) {
    assert.equal(looksLikeCommand(ok), false, `false alarm: ${ok}`);
  }
});

test("broad detector: arguments are case-insensitive, so an id stays part of the span", () => {
  for (const s of ["reel previews C0239", "reel previews(C0239)", "Run reel plan --video-id EP01_R03 now"]) {
    const span = commandSpans(s).find((x) => x.rule === "command")!;
    assert.ok(span, s);
    assert.match(s.slice(span.start, span.end), /C0239|EP01_R03/, s);
  }
  const p = "~/.whynot-cut/bin/reel previews";
  const span = commandSpans(p)[0]!;
  assert.equal(p.slice(span.start, span.end), p, "the path is part of the span");
});

test("commandSpans: spans are in the original text's indices, also with tashkeel, tatweel and zero-width characters", () => {
  const s = "قبل شغِّـل الأمر\u200b: reel doctor بعد";
  const span = commandSpans(s)[0]!;
  assert.equal(s.slice(span.start, span.end).replace(/[\u064b-\u065f\u0640\u200b]/g, ""), "شغل الأمر: reel doctor");
  assert.equal(commandIn("Your reel is ready."), null);
  assert.equal(commandIn("reel doctor"), "command");
  assert.equal(commandIn("`a b`"), "backticked-command");
  assert.equal(commandIn("Claude Code"), "claude-code");
  assert.equal(commandIn("whynotcut://x"), "launcher-link");
  assert.equal(commandIn("type: something"), "lead-in");
});

test("runtimeText: 'Claude Code' becomes 'Claude' in place; a text with a command is held back (null); the input is capped", () => {
  assert.equal(runtimeText("Open Claude Code and press Try again."), "Open Claude and press Try again.");
  assert.equal(runtimeText("open claude\u00a0code, then wait."), "open Claude, then wait.");
  assert.equal(runtimeText("Premiere is not responding. Run reel doctor and press Try again."), null);
  assert.equal(runtimeText("Open your Claude session, run reel serve --ensure."), null);
  assert.equal(runtimeText("The reel plan is ready"), "The reel plan is ready", "a normal sentence is never cut");
  assert.equal(runtimeText("Python 3.9 is required"), "Python 3.9 is required");
  assert.equal(runtimeText(undefined), "");
  assert.equal(runtimeText(42), "");
  assert.equal(RUNTIME_MAX, 4000);
  const long = "a".repeat(RUNTIME_MAX) + " reel doctor";
  assert.equal(runtimeText(long), "a".repeat(RUNTIME_MAX), "only the capped text is checked and shown");
  assert.equal(containsRuntimeCommand(long), false);
});

test("ONE module, two detectors: render.ts, mount.ts and kit/toast.ts use src/commands.ts's runtime handling and keep no command regex of their own; neutralise() is gone; the guard imports the broad one", () => {
  for (const f of ["render.ts", "mount.ts", "kit/toast.ts"]) {
    const src = readFileSync(join(PANEL_UI, "src", f), "utf8");
    assert.match(src, /from "\.\.?\/(?:\.\.\/)?commands\.ts"/, f);
    assert.match(src, /runtimeText/, f);
    assert.doesNotMatch(src, /function hasCommand|claude\\s\*code|neutralise/, `${f} keeps its own detector or the old surgery`);
  }
  assert.doesNotMatch(readFileSync(join(PANEL_UI, "src", "commands.ts"), "utf8"), /export function neutralise|function tidy/);
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
