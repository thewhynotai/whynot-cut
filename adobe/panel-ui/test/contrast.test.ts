// B-T1 contrast test: every text/background pair the panel kit paints meets WCAG (Addendum B4.8): 4.5:1 for text,
// 3:1 for the focus ring and status icons. Colours are read from brand/tokens.css, never restated here; translucent
// layers (glass) are composited over what they sit on. A guard makes sure every colour/background token the CSS uses
// is covered by a pair, so a new text colour cannot skip this test; a stacking guard makes sure glass only ever sits
// on the black background (the card ruling in brand/tokens.css).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { initialUi, render } from "../src/render.ts";
import { stringsFor } from "../src/i18n.ts";
import { SCENARIOS, sampleState } from "../src/mock.ts";
import { kitGallery } from "../src/kit/gallery.ts";
import { ADOBE, PANEL_UI, TOKENS, contrast, over, parseCss, tokenMap, walk } from "./tokens-util.ts";
import type { Rgb } from "./tokens-util.ts";

const tokens = tokenMap(readFileSync(TOKENS, "utf8"));

/** A token (or "<translucent token> over <spec>", nested) as the opaque colour the eye sees. */
function colour(spec: string): Rgb {
  const m = /^(--twn-[a-z0-9-]+) over (.+)$/.exec(spec);
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

/** The card: glass over the black background (about #141414), as on thewhynot.ai (Addendum B §B2, magnific-brand
 *  §2.2). Glass never sits on #121212 (the stacking guard below enforces it), so this is the only glass composite. */
const GLASS = "--twn-glass over --twn-bg";
/** A kit control drawn in glass (secondary button, toast, dialog) inside a glass card: glass on glass over black. */
const GLASS2 = `--twn-glass over ${GLASS}`;
const TEXT = 4.5;
const NON_TEXT = 3;

/** [foreground, background, minimum, where] for every pair the kit paints. */
const PAIRS: readonly [string, string, number, string][] = [
  ["--twn-text", "--twn-bg", TEXT, "panel body, inputs, step names"],
  ["--twn-text", "--twn-surface", TEXT, "solid (non-glass) panels: banners, now box, copy box"],
  ["--twn-text", "--twn-surface-2", TEXT, "command chips, flagged statements"],
  ["--twn-text-muted", "--twn-bg", TEXT, "header who-line, pill keys, hints, footer"],
  ["--twn-text-muted", "--twn-surface", TEXT, "idle now box, banner close, log timestamps"],
  ["--twn-text-muted", "--twn-surface-2", TEXT, "pending step dot"],
  ["--twn-text-muted", "--twn-frame-bg", TEXT, "QC tile with no image; kit: frame / waveform placeholder text"],
  ["--twn-primary-text", "--twn-bg", TEXT, "violet text / links"],
  ["--twn-primary-text", "--twn-surface", TEXT, "violet text on a solid panel"],
  ["--twn-accent", "--twn-bg", TEXT, "pink eyebrow section titles"],
  ["--twn-accent", "--twn-surface", TEXT, "pink eyebrow on a solid panel"],
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
  ["--twn-focus", "--twn-surface", NON_TEXT, "focus ring on a solid panel"],
  // the glass card (glass over black): every text token reads at 4.5:1 or better on it, icons at 3:1
  ["--twn-text", GLASS, TEXT, "glass card: text"],
  ["--twn-text-muted", GLASS, TEXT, "glass card: secondary text"],
  ["--twn-primary-text", GLASS, TEXT, "glass card: violet text / links"],
  ["--twn-accent", GLASS, TEXT, "glass card: pink eyebrow"],
  ["--twn-ok", GLASS, TEXT, "glass card: ok text"],
  ["--twn-warn", GLASS, TEXT, "glass card: warn text"],
  ["--twn-error", GLASS, TEXT, "glass card: error text"],
  ["--twn-focus", GLASS, NON_TEXT, "glass card: focus ring"],
  ["--twn-ok", GLASS, NON_TEXT, "glass card: ok icon"],
  ["--twn-warn", GLASS, NON_TEXT, "glass card: warn icon"],
  ["--twn-error", GLASS, NON_TEXT, "glass card: error icon"],
  // the kit (B-T1): glass controls inside a glass card (secondary button, toast or dialog in a card)
  ["--twn-text", GLASS2, TEXT, "kit: secondary button / toast text in a card"],
  ["--twn-text-muted", GLASS2, TEXT, "kit: toast how-line, dialog labels in a card"],
  // violet and pink on two glass layers are about 4.25:1: fine for icons (3:1), NOT for text. Violet/pink TEXT (eyebrows,
  // info/accent chips, links) stays on one glass layer at most; test/kit.test.ts checks the kit never nests it deeper.
  ["--twn-primary-text", GLASS2, NON_TEXT, "kit: info toast icon in a card"],
  ["--twn-accent", GLASS2, NON_TEXT, "kit: pink icon on a glass control in a card"],
  ["--twn-ok", GLASS2, TEXT, "kit: ok toast in a card"],
  ["--twn-warn", GLASS2, TEXT, "kit: warn toast / dialog icon in a card"],
  ["--twn-error", GLASS2, TEXT, "kit: error toast in a card"],
  ["--twn-focus", GLASS2, NON_TEXT, "kit: focus ring on a glass control in a card"],
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

// ---- guard: every colour / background token the CSS uses has a pair ----

/** Tokens a pair covers: plain foregrounds and backgrounds, and the translucent layer X of an "X over Y" pair (where
 *  the layer may sit is the stacking guard's job). */
const FGS = new Set(PAIRS.map((p) => p[0]));
const BGS = new Set(PAIRS.map((p) => p[1].split(" over ")[0]!));
/** No text sits on these: the gradient (hairline, progress fill) and the progress track. */
const NO_TEXT = new Set(["--twn-gradient", "--twn-track"]);

function uncovered(cssText: string): string[] {
  const css = cssText.replace(/\/\*[\s\S]*?\*\//g, "");
  const missing: string[] = [];
  for (const m of css.matchAll(/(?:^|[;{\s])color\s*:\s*var\((--twn-[a-z0-9-]+)\)/g)) if (!FGS.has(m[1]!)) missing.push(`color ${m[1]}`);
  for (const m of css.matchAll(/background(?:-color)?\s*:\s*var\((--twn-[a-z0-9-]+)\)/g)) {
    if (!BGS.has(m[1]!) && !NO_TEXT.has(m[1]!)) missing.push(`background ${m[1]}`);
  }
  return [...new Set(missing)];
}

const KIT_CSS = () => [...walk(join(PANEL_UI, "styles"), (p) => p.endsWith(".css")), join(ADOBE, "premiere-uxp", "plugin", "index.css")];

test("guard self-check: glass (an 'X over Y' pair) counts as covered; a token with no pair does not", () => {
  assert.deepEqual(uncovered(".x { background: var(--twn-glass); color: var(--twn-text); }"), []);
  assert.deepEqual(uncovered(".x { background: var(--twn-deep); color: var(--twn-deep); }"), ["color --twn-deep", "background --twn-deep"]);
});

test("guard: every colour and background token the kit CSS uses is covered by a pair", () => {
  for (const f of KIT_CSS()) assert.deepEqual(uncovered(readFileSync(f, "utf8")), [], f);
});

// ---- stacking guard: glass sits on the black background, never on a #121212 surface ----

interface Rule {
  selector: string;
  body: string;
}
function rules(cssText: string): Rule[] {
  const css = cssText.replace(/\/\*[\s\S]*?\*\//g, "").replace(/@font-face\s*\{[^}]*\}/g, "");
  return [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)].flatMap((m) => m[1]!.split(",").map((s) => ({ selector: s.trim(), body: m[2]! })));
}
const backgroundsOf = (body: string) => [...body.matchAll(/background(?:-color)?\s*:([^;]+)/g)].map((m) => m[1]!);
const hasToken = (body: string, token: string) => backgroundsOf(body).some((b) => new RegExp(`var\\(${token}\\)`).test(b));
const classesOf = (compound: string) => [...compound.matchAll(/\.([A-Za-z0-9_-]+)/g)].map((m) => m[1]!);

/** Where glass is stacked on a surface: a rule painting both; a glass rule whose selector sits inside a surface class;
 *  and, in rendered markup, an element with a glass class inside (or on) an element with a surface class. Classes are
 *  mapped from the last compound of each selector. */
export function glassStacking(cssText: string, htmls: readonly string[]): string[] {
  const rs = rules(cssText);
  const glass = new Set<string>();
  const surface = new Set<string>();
  const found: string[] = [];
  for (const r of rs) {
    const last = classesOf(r.selector.split(/\s+|>/).filter(Boolean).pop() ?? "");
    if (hasToken(r.body, "--twn-glass")) last.forEach((c) => glass.add(c));
    if (hasToken(r.body, "--twn-surface")) last.forEach((c) => surface.add(c));
    if (hasToken(r.body, "--twn-glass") && hasToken(r.body, "--twn-surface")) found.push(`${r.selector}: glass and surface in one rule`);
  }
  for (const r of rs) {
    if (!hasToken(r.body, "--twn-glass")) continue;
    const ancestors = r.selector.split(/\s+|>/).filter(Boolean).slice(0, -1);
    for (const a of ancestors) for (const c of classesOf(a)) if (surface.has(c)) found.push(`${r.selector}: glass inside .${c} (a surface)`);
  }
  if (glass.size) {
    for (const html of htmls) {
      const stack: string[][] = [];
      for (const m of html.matchAll(/<(\/?)([a-z][a-z0-9]*)\b([^>]*)>/gi)) {
        const [, close, tag, attrs] = m;
        if (close) {
          stack.pop();
          continue;
        }
        const cls = (/\bclass="([^"]*)"/.exec(attrs!)?.[1] ?? "").split(/\s+/).filter(Boolean);
        if (cls.some((c) => glass.has(c))) {
          const under = [...stack.flat(), ...cls].filter((c) => surface.has(c));
          if (under.length) found.push(`<${tag} class="${cls.join(" ")}"> is glass on .${under.join(", .")}`);
        }
        if (!/^(img|input|br|hr|meta|link)$/i.test(tag!) && !attrs!.trimEnd().endsWith("/")) stack.push(cls);
      }
    }
  }
  return [...new Set(found)];
}

test("stacking guard self-check: it catches glass on a surface (same rule, selector nesting, rendered nesting)", () => {
  const css = ".card { background: var(--twn-surface); } .glass { background: var(--twn-glass); } .card .tip { background: var(--twn-glass); } .both { background: var(--twn-surface); background: var(--twn-glass); }";
  const found = glassStacking(css, ['<div class="card"><p><span class="glass">x</span></p></div>', '<div class="glass">ok on black</div>']);
  assert.deepEqual(found.sort(), [
    ".both: glass and surface in one rule",
    ".card .tip: glass inside .card (a surface)",
    '<span class="glass"> is glass on .card',
  ].sort());
  assert.deepEqual(glassStacking(css.replace(/\.card \.tip[^}]*\}|\.both[^}]*\}/g, ""), ['<div class="glass">on black</div>']), []);
});

test("the kit's CSS is under the colour and stacking guards (styles/kit.css is walked with panel.css)", () => {
  assert.ok(KIT_CSS().some((f) => f.endsWith("kit.css")));
});

test("stacking guard: no panel-ui CSS rule or rendered screen (panel and kit) puts glass on a --twn-surface background", () => {
  const css = KIT_CSS().map((f) => readFileSync(f, "utf8")).join("\n");
  const htmls: string[] = [];
  for (const lang of ["en", "ar"] as const) {
    for (const scenario of SCENARIOS) {
      const s = sampleState(lang, scenario);
      const t = stringsFor(lang);
      htmls.push(render(s, t, initialUi()));
      htmls.push(render(s, t, { ...initialUi(), logOpen: true, confirmRebuild: true, notice: { kind: "error", text: "x", how: "Run `reel doctor`." } }));
    }
    // the component kit: every component (the dev harness "Kit" scenario)
    htmls.push(kitGallery(lang));
  }
  assert.deepEqual(glassStacking(css, htmls), []);
});

test("each pair is listed once, and a frame-bg pair is one the CSS paints (muted placeholder text, never --twn-text)", () => {
  const keys = PAIRS.map(([fg, bg, min]) => `${fg} on ${bg} @${min}`);
  assert.deepEqual(keys.filter((k, i) => keys.indexOf(k) !== i), [], "a redundant pair");
  const css = KIT_CSS().map((f) => readFileSync(f, "utf8")).join("\n").replace(/\/\*[\s\S]*?\*\//g, "");
  const frameBgRules = [...css.matchAll(/([^{}]+)\{([^}]*)\}/g)].filter((m) => /background\s*:\s*var\(--twn-frame-bg\)/.test(m[2]!));
  assert.ok(frameBgRules.length >= 3);
  for (const m of frameBgRules) {
    const colour = /(?:^|;)\s*color\s*:\s*var\((--twn-[a-z0-9-]+)\)/.exec(m[2]!)?.[1];
    if (colour) assert.ok(PAIRS.some(([fg, bg]) => fg === colour && bg === "--twn-frame-bg"), `${m[1]!.trim()}: ${colour} on --twn-frame-bg has no pair`);
  }
  assert.ok(!PAIRS.some(([fg, bg]) => fg === "--twn-text" && bg === "--twn-frame-bg"), "no kit element paints --twn-text on --twn-frame-bg");
});
