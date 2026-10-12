// B-T1 contrast test: every text/background pair the panel kit paints meets WCAG (Addendum B4.8): 4.5:1 for text,
// 3:1 for the focus ring and status icons. Colours are read from brand/tokens.css, never restated here; translucent
// layers (glass) are composited over what they sit on. A guard makes sure every colour/background token the CSS uses
// is covered by a pair, so a new text colour cannot skip this test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ADOBE, PANEL_UI, TOKENS, contrast, over, parseCss, tokenMap, walk } from "./tokens-util.ts";
import type { Rgb } from "./tokens-util.ts";

const tokens = tokenMap(readFileSync(TOKENS, "utf8"));

/** A token (or "glass over <token>") as the opaque colour the eye sees. */
function colour(spec: string): Rgb {
  const m = /^(--twn-[a-z0-9-]+) over (--twn-[a-z0-9-]+)$/.exec(spec);
  if (m) return over(parseCss(value(m[1]!)), colour(m[2]!));
  const c = parseCss(value(spec));
  assert.equal(c.a, 1, `${spec} is translucent: say what it sits on ("${spec} over --twn-bg")`);
  return c;
}
function value(name: string): string {
  const v = tokens.get(name);
  assert.ok(v, `token ${name} is not in brand/tokens.css`);
  // the focus token is a box-shadow: its colour is the last part
  return name === "--twn-focus" ? v.split(/\s+/).pop()! : v;
}

const GLASS = "--twn-glass over --twn-bg";
const TEXT = 4.5;
const NON_TEXT = 3;

/** [foreground, background, minimum, where] for every pair the kit paints. */
const PAIRS: readonly [string, string, number, string][] = [
  ["--twn-text", "--twn-bg", TEXT, "panel body, inputs, step names"],
  ["--twn-text", "--twn-surface", TEXT, "cards, banners, now box, copy box"],
  ["--twn-text", "--twn-surface-2", TEXT, "command chips, flagged statements"],
  ["--twn-text", GLASS, TEXT, "glass card (Addendum B)"],
  ["--twn-text-muted", "--twn-bg", TEXT, "header who-line, pill keys, hints, footer"],
  ["--twn-text-muted", "--twn-surface", TEXT, "idle now box, banner close, log timestamps"],
  ["--twn-text-muted", "--twn-surface-2", TEXT, "pending step dot"],
  ["--twn-text-muted", "--twn-frame-bg", TEXT, "QC tile with no image"],
  ["--twn-text-muted", GLASS, TEXT, "glass card secondary text"],
  ["--twn-primary-text", "--twn-bg", TEXT, "violet text / links"],
  ["--twn-primary-text", "--twn-surface", TEXT, "violet text on a card"],
  ["--twn-primary-text", GLASS, TEXT, "violet text on a glass card"],
  ["--twn-accent", "--twn-bg", TEXT, "pink eyebrow section titles"],
  ["--twn-accent", "--twn-surface", TEXT, "pink eyebrow on a card"],
  ["--twn-accent", "--twn-surface-2", TEXT, "religious flag chip"],
  ["--twn-ok", "--twn-bg", TEXT, "ok pill value"],
  ["--twn-ok", "--twn-surface", TEXT, "QC pass verdict"],
  ["--twn-warn", "--twn-bg", TEXT, "warn pill value"],
  ["--twn-warn", "--twn-surface", TEXT, "rebuild confirm title, log warn line"],
  ["--twn-warn", "--twn-surface-2", TEXT, "medical flag chip"],
  ["--twn-error", "--twn-bg", TEXT, "offline pill value"],
  ["--twn-error", "--twn-surface", TEXT, "QC fail verdict, log error line"],
  ["--twn-on-primary", "--twn-primary", TEXT, "primary button, running step dot"],
  ["--twn-on-primary", "--twn-primary-hover", TEXT, "primary button hover"],
  ["--twn-on-ok", "--twn-ok", TEXT, "done step dot"],
  ["--twn-on-accent", "--twn-accent", TEXT, "waiting step dot"],
  ["--twn-on-error", "--twn-error", TEXT, "failed step dot"],
  ["--twn-focus", "--twn-bg", NON_TEXT, "focus ring"],
  ["--twn-focus", "--twn-surface", NON_TEXT, "focus ring on a card"],
  ["--twn-ok", GLASS, NON_TEXT, "ok icon on a glass card"],
  ["--twn-warn", GLASS, NON_TEXT, "warn icon on a glass card"],
  ["--twn-error", GLASS, NON_TEXT, "error icon on a glass card"],
];

test("every text/background pair meets WCAG: 4.5:1 text, 3:1 focus ring and status icons", () => {
  const fails: string[] = [];
  for (const [fg, bg, min, where] of PAIRS) {
    const r = contrast(colour(fg), colour(bg));
    if (r < min) fails.push(`${fg} on ${bg} = ${r.toFixed(2)}:1 < ${min}:1 (${where})`);
  }
  assert.deepEqual(fails, []);
});

test("Addendum B's own numbers hold: white on #5400FB is about 7.6:1; raw #5400FB as text on black fails", () => {
  const white = colour("--twn-on-primary");
  assert.ok(contrast(white, colour("--twn-primary")) > 7.4);
  assert.ok(contrast(colour("--twn-primary"), colour("--twn-bg")) < TEXT, "#5400FB must never be a text colour");
});

test("guard: every colour and solid background token the kit CSS uses is covered by a pair", () => {
  const files = [...walk(join(PANEL_UI, "styles"), (p) => p.endsWith(".css")), join(ADOBE, "premiere-uxp", "plugin", "index.css")];
  const fgs = new Set(PAIRS.map((p) => p[0]));
  const bgs = new Set(PAIRS.flatMap((p) => [p[1], ...(p[1].includes(" over ") ? [p[1].split(" over ")[1]!] : [])]));
  // no text sits on these: the gradient (hairline, progress fill) and the progress track
  const NO_TEXT = new Set(["--twn-gradient", "--twn-track"]);
  const missing: string[] = [];
  for (const f of files) {
    const css = readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    for (const m of css.matchAll(/(?:^|[;{\s])color\s*:\s*var\((--twn-[a-z0-9-]+)\)/g)) if (!fgs.has(m[1]!)) missing.push(`color ${m[1]}`);
    for (const m of css.matchAll(/background(?:-color)?\s*:\s*var\((--twn-[a-z0-9-]+)\)/g)) {
      if (!bgs.has(m[1]!) && !NO_TEXT.has(m[1]!)) missing.push(`background ${m[1]}`);
    }
  }
  assert.deepEqual([...new Set(missing)], []);
});
