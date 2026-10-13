// B-T1 kit rules from the live Premiere 26.5.2 UXP CSS lab (spike 0.1.7, docs/adobe/evidence/ui-kit/uxp-lab-017/,
// docs/adobe/uxp-parity.md "Spike 0.1.7 CSS lab"):
//   1 every <button> paints as Premiere's native grey control -> the kit emits <div role="button" tabindex="0">; Enter
//     and Space activate it (src/kit/activate.ts, wired by mount.ts); disabled = aria-disabled + class + tabindex -1;
//     a control's radius is the explicit half-height 16 px, never 999 (999 stays on <span> chips);
//   2 no gradient ring is clean -> the main CTA's glow is ONE box-shadow token; the gradient is hairline + progress only;
//   3 fill="currentColor", a fill attribute and <img> paint nothing; a CSS fill does -> no fill attribute, ink classes;
//   4 no @font-face loads -> brand family first, then Windows / macOS system fonts (tokens.test.ts, this file);
//   5 whitespace between flex children is dropped and margin-inline does nothing -> a physical-margin gap class;
//   6 a Latin word inside an Arabic run shapes badly -> Latin words inside Arabic copy are <bdi dir="ltr"> runs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { AR, EN } from "../src/i18n.ts";
import { button, chip, header, icon, isolateLatin, kitDisabled, kitKeyHandler, logDrawer, prose, stepStrip, tabs, withCommands } from "../src/kit/index.ts";
import type { KitElement } from "../src/kit/index.ts";
import { kitGallery } from "../src/kit/gallery.ts";
import { mount } from "../src/mount.ts";
import type { MountRoot, PanelElement } from "../src/mount.ts";
import { MockSource } from "../src/mock.ts";
import { PANEL_UI, TOKENS, tokenMap } from "./tokens-util.ts";

const KIT_CSS = readFileSync(join(PANEL_UI, "styles", "kit.css"), "utf8");
const FLAT_CSS = KIT_CSS.replace(/\/\*[\s\S]*?\*\//g, "");
const TOK = tokenMap(readFileSync(TOKENS, "utf8"));
const GALLERY = { en: kitGallery("en"), ar: kitGallery("ar") };
const ALL = GALLERY.en + GALLERY.ar;

const attr = (attrs: string, name: string) => new RegExp(`\\s${name}="([^"]*)"`).exec(attrs)?.[1];
const classesOf = (attrs: string) => (attr(attrs, "class") ?? "").split(/\s+/).filter(Boolean);
const controls = (html: string) => [...html.matchAll(/<div\b([^>]*\srole="(?:button|tab)"[^>]*)>/g)].map((m) => m[1]!);
function cssRules(): { selectors: string[]; body: string }[] {
  return [...FLAT_CSS.matchAll(/([^{}]+)\{([^}]*)\}/g)].map((m) => ({ selectors: m[1]!.split(",").map((s) => s.trim()), body: m[2]! }));
}
/** the rules whose selector's last compound names the class */
const rulesFor = (cls: string) =>
  cssRules().filter((r) => r.selectors.some((s) => (s.split(/\s+|>/).filter(Boolean).pop() ?? "").split(/(?=[.:[])/).includes(`.${cls}`)));

// ---- 1. controls: <div role="button">, never <button> ----

test("lab 1: the kit never emits <button>: not in the gallery (EN, AR), not in any kit source", () => {
  assert.doesNotMatch(ALL, /<\/?button\b/);
  for (const f of readdirSync(join(PANEL_UI, "src", "kit")).filter((x) => x.endsWith(".ts"))) {
    const src = readFileSync(join(PANEL_UI, "src", "kit", f), "utf8").replace(/\/\/.*$|\/\*[\s\S]*?\*\//gm, "");
    assert.doesNotMatch(src, /<button\b/, `${f} emits a <button>`);
  }
});

test("lab 1: every control in the gallery is a <div role=button|tab> with tabindex, the focus ring and a data-action; every component that has one uses it", () => {
  const cs = controls(ALL);
  assert.ok(cs.length >= 30, `${cs.length} controls`);
  for (const a of cs) {
    assert.ok(classesOf(a).includes("kit-focus"), a);
    assert.ok(attr(a, "data-action"), a);
    assert.match(attr(a, "tabindex") ?? "", /^(0|-1)$/, a);
  }
  // tabs, the language switch, the Needs-you badge, toast close, log toggle, frame tiles, checklist actions, buttons
  const firsts = new Set(cs.map((a) => classesOf(a)[0]));
  for (const c of ["kit-tab", "kit-lang-btn", "kit-badge", "kit-x", "kit-log-toggle", "kit-frame", "kit-btn"]) assert.ok(firsts.has(c), `no ${c} control`);
  assert.ok(controls(GALLERY.en).filter((a) => attr(a, "role") === "tab").length === 3, "tabs keep role=tab");
  assert.match(GALLERY.en, /<li class="kit-check-row[^"]*"[^>]*>[\s\S]*?<span class="kit-check-act"><div class="kit-btn /, "checklist actions are kit controls");
});

test("lab 1: disabled is aria-disabled + kit-btn-disabled + tabindex -1 (never the disabled attribute); explicit muted colours, not opacity", () => {
  const off = button({ label: "x", action: "a", variant: "primary", disabled: true, glow: true, icon: "close" });
  const a = controls(off)[0]!;
  assert.equal(attr(a, "aria-disabled"), "true");
  assert.equal(attr(a, "tabindex"), "-1");
  assert.ok(classesOf(a).includes("kit-btn-disabled"));
  assert.ok(!classesOf(a).includes("kit-btn-glow"), "a disabled CTA does not glow");
  assert.doesNotMatch(off, /\sdisabled(?!")/);
  assert.match(off, /kit-ink-muted/, "its icon is muted like its text");
  const on = controls(button({ label: "x", action: "a" }))[0]!;
  assert.equal(attr(on, "aria-disabled"), undefined);
  assert.equal(attr(on, "tabindex"), "0");
  assert.ok(controls(ALL).some((x) => attr(x, "aria-disabled") === "true"), "the gallery shows a disabled button");
  const rule = cssRules().find((r) => r.selectors.includes(".kit-btn.kit-btn-disabled"))!.body;
  assert.match(rule, /background: var\(--twn-surface-2\)/);
  assert.match(rule, /color: var\(--twn-text-muted\)/);
  assert.doesNotMatch(rule, /opacity/, "the lab's opacity on a div computed .45 but painted at full strength");
  assert.ok(cssRules().some((r) => r.selectors.includes(".kit-btn.kit-btn-disabled:hover")), "hover does not light a disabled button");
});

test("lab 1: a control's radius is the explicit 16 px token (half its 32 px height), never 999; 999 stays on <span> chips", () => {
  assert.equal(TOK.get("--twn-radius-control"), "16px");
  assert.equal(TOK.get("--twn-radius-pill"), "999px");
  const classes = new Set(controls(ALL).map((a) => classesOf(a)[0]!));
  for (const c of classes) {
    for (const r of rulesFor(c)) assert.doesNotMatch(r.body, /radius-pill|999px/, `.${c} (a control) has a 999 radius: ${r.selectors.join(", ")}`);
  }
  for (const c of ["kit-btn", "kit-badge", "kit-lang-btn", "kit-x"]) {
    assert.ok(rulesFor(c).some((r) => /border-radius: var\(--twn-radius-control\)/.test(r.body)), `.${c} radius`);
  }
  assert.ok(rulesFor("kit-chip").some((r) => /border-radius: var\(--twn-radius-pill\)/.test(r.body)), "chips keep the pill");
  assert.match(chip({ label: "x" }), /^<span class="kit-chip/, "a chip is a span");
});

// ---- 1. keyboard: Enter and Space activate a control ----

class El implements KitElement {
  attrs: Record<string, string>;
  parent: El | null;
  constructor(attrs: Record<string, string>, parent: El | null = null) {
    this.attrs = attrs;
    this.parent = parent;
  }
  getAttribute(n: string) { return Object.prototype.hasOwnProperty.call(this.attrs, n) ? this.attrs[n]! : null; }
  closest(sel: string): El | null {
    const m = /^\[([\w-]+)\]$/.exec(sel);
    if (!m) return null;
    return m[1]! in this.attrs ? this : (this.parent?.closest(sel) ?? null);
  }
}

test("kitKeyHandler: Enter, Space and Spacebar on a control call the click handler with it and stop the default; nothing else does", () => {
  const hits: (KitElement | null)[] = [];
  const onKey = kitKeyHandler((e: { target: KitElement | null }) => void hits.push(e.target));
  const ctl = new El({ "data-action": "approve", role: "button" });
  let prevented = 0;
  for (const key of ["Enter", " ", "Spacebar"]) onKey({ target: ctl, key, preventDefault: () => void prevented++ });
  assert.deepEqual(hits, [ctl, ctl, ctl]);
  assert.equal(prevented, 3, "Space would scroll the panel");
  // a tab control too; a key on a child of the control finds the control
  onKey({ target: new El({}, new El({ "data-action": "tab", role: "tab" })), key: "Enter" });
  assert.equal(hits.length, 4);
  assert.equal(hits[3]!.getAttribute("data-action"), "tab");
  // not: another key, a disabled control, an element with no data-action, a data-action with no control role (a text box)
  onKey({ target: ctl, key: "a" });
  onKey({ target: ctl, key: "Tab" });
  onKey({ target: ctl });
  onKey({ target: new El({ "data-action": "x", role: "button", "aria-disabled": "true" }), key: "Enter" });
  onKey({ target: new El({ "data-field": "changes" }), key: " " });
  onKey({ target: new El({ "data-action": "x" }), key: "Enter" });
  onKey({ target: null, key: "Enter" });
  assert.equal(hits.length, 4);
  assert.equal(kitDisabled(new El({ "aria-disabled": "true" })), true);
  assert.equal(kitDisabled(new El({ "aria-disabled": "false" })), false);
  assert.equal(kitDisabled(null), false);
});

class FakeEl implements PanelElement {
  attrs: Record<string, string>;
  constructor(attrs: Record<string, string>) {
    this.attrs = attrs;
  }
  getAttribute(n: string) { return this.attrs[n] ?? null; }
  closest(sel: string): PanelElement | null {
    const m = /^\[([\w-]+)\]$/.exec(sel);
    return m && m[1]! in this.attrs ? this : null;
  }
}
type Fn = (e: { target: PanelElement | null; key?: string; preventDefault?(): void }) => void;
class FakeRoot implements MountRoot {
  innerHTML = "";
  listeners: Record<string, Fn[]> = {};
  addEventListener(t: string, fn: Fn) { (this.listeners[t] ??= []).push(fn); }
  removeEventListener(t: string, fn: Fn) { this.listeners[t] = (this.listeners[t] ?? []).filter((f) => f !== fn); }
  fire(type: string, attrs: Record<string, string>, key?: string) { for (const fn of this.listeners[type] ?? []) fn({ target: new FakeEl(attrs), key, preventDefault: () => {} }); }
}
const host = { setPlayerPosition() {}, openInSourceMonitor() {}, revealPath() {}, copyText() {} };

test("mount: Enter / Space on a kit control does what its click does; a disabled control ignores clicks and keys; unmount drops the key listener", async () => {
  const root = new FakeRoot();
  const handle = mount(root, new MockSource({ language: "en", scenario: "approval" }), host);
  await handle.ready;
  assert.equal(handle.ui.logOpen, false);
  root.fire("keydown", { "data-action": "toggle-log", role: "button" }, "Enter");
  assert.equal(handle.ui.logOpen, true, "Enter toggled the log drawer");
  root.fire("keydown", { "data-action": "toggle-log", role: "button" }, " ");
  assert.equal(handle.ui.logOpen, false, "Space toggled it back");
  root.fire("keydown", { "data-action": "toggle-log", role: "button" }, "x");
  assert.equal(handle.ui.logOpen, false, "another key does nothing");
  const off = { "data-action": "toggle-log", role: "button", "aria-disabled": "true" };
  root.fire("click", off);
  root.fire("keydown", off, "Enter");
  assert.equal(handle.ui.logOpen, false, "a disabled control does nothing");
  root.fire("click", { "data-action": "toggle-log", role: "button" });
  assert.equal(handle.ui.logOpen, true, "a click still works");
  handle.unmount();
  assert.equal((root.listeners.keydown ?? []).length, 0);
});

// ---- 2. the CTA glow is a shadow ----

test("lab 2: the main CTA's glow is ONE box-shadow token (multi-shadow is unproven in UXP); no gradient ring anywhere", () => {
  const glow = TOK.get("--twn-cta-glow") ?? "";
  assert.equal(glow, "0 0 10px rgba(217,92,155,.6)");
  assert.doesNotMatch(glow.replace(/\([^)]*\)/g, ""), /,/, "a single shadow");
  assert.match(GALLERY.en, /class="kit-btn kit-btn-primary kit-focus[^"]*kit-btn-glow"/);
  assert.doesNotMatch(ALL + FLAT_CSS, /kit-glow\b/, "the gradient wrapper is gone");
  assert.doesNotMatch(FLAT_CSS, /border-image/);
  const users = cssRules().filter((r) => /var\(--twn-gradient\)/.test(r.body)).flatMap((r) => r.selectors).sort();
  assert.deepEqual(users, [".kit-fill", ".kit-hairline"]);
});

// ---- 3. svg fills come from CSS classes ----

test("lab 3: no emitted svg (or path) has a fill attribute or currentColor; every icon has exactly one ink class, and kit.css fills each from a token", () => {
  const svgs = [...ALL.matchAll(/<svg\b([^>]*)>/g)].map((m) => m[1]!);
  assert.ok(svgs.length > 20, `${svgs.length} icons`);
  assert.doesNotMatch(ALL, /<(?:svg|path)\b[^>]*\sfill="/, "a fill attribute paints nothing in UXP");
  assert.doesNotMatch(ALL + FLAT_CSS, /currentColor/i);
  for (const a of svgs) assert.equal(classesOf(a).filter((c) => c.startsWith("kit-ink-")).length, 1, a);
  const inks = new Set(svgs.flatMap((a) => classesOf(a).filter((c) => c.startsWith("kit-ink-"))));
  for (const ink of ["ok", "warn", "error", "info", "accent", "text", "muted", "on-primary", "on-ok", "on-error", "on-accent"]) {
    const rule = cssRules().find((r) => r.selectors.includes(`.kit-ink-${ink}`));
    assert.ok(rule, `.kit-ink-${ink} has no rule`);
    assert.match(rule!.body, /^\s*fill: var\(--twn-[a-z0-9-]+\);\s*$/, `.kit-ink-${ink}`);
  }
  for (const ink of inks) assert.ok(cssRules().some((r) => r.selectors.includes(`.${ink}`)), `${ink} is emitted but not styled`);
});

test("lab 3: an icon's ink follows where it sits: its status colour; on a button or a step dot, that fill's text colour", () => {
  assert.match(icon("ok"), /kit-ink-ok/);
  assert.match(icon("warn"), /kit-ink-warn/);
  assert.match(icon("pending"), /kit-ink-muted/);
  assert.match(icon("close"), /kit-ink-muted/);
  assert.match(icon("ok", { ink: "bogus" as never }), /kit-ink-ok/, "an unknown ink falls back");
  assert.match(button({ label: "x", action: "a", variant: "danger" }), /kit-icon-warn kit-ink-on-error/);
  assert.match(button({ label: "x", action: "a", variant: "primary", icon: "close" }), /kit-ink-on-primary/);
  assert.match(button({ label: "x", action: "a", icon: "close" }), /kit-ink-text/);
  const strip = stepStrip({ t: EN, rtl: false, steps: [{ id: "transcript", state: "done" }, { id: "plan", state: "failed" }] });
  assert.match(strip, /kit-step-done[^>]*><span class="kit-step-dot"><svg [^>]*kit-ink-on-ok/);
  assert.match(strip, /kit-step-failed[^>]*><span class="kit-step-dot"><svg [^>]*kit-ink-on-error/);
  assert.match(strip, /kit-step-sep"><svg [^>]*kit-ink-muted/);
});

// ---- 5. gaps are physical margins ----

test("lab 5: the gap class is a physical margin (left in LTR, right in RTL, left again in an LTR island); no margin-inline anywhere; last in kit.css", () => {
  const rule = (sel: string) => cssRules().find((r) => r.selectors.includes(sel))?.body ?? "";
  assert.match(rule(".kit-gap-s"), /^\s*margin-left: 6px;\s*$/);
  assert.match(rule(".kit-rtl .kit-gap-s"), /margin-left: 0;\s*margin-right: 6px;/);
  assert.match(rule(".kit-rtl .kit-stamp .kit-gap-s"), /margin-left: 6px;\s*margin-right: 0;/);
  assert.doesNotMatch(FLAT_CSS, /margin-inline|padding-inline|inset-inline/, "UXP ignores the logical properties");
  const last = cssRules().slice(-3).flatMap((r) => r.selectors);
  assert.deepEqual(last, [".kit-gap-s", ".kit-rtl .kit-gap-s", ".kit-rtl .kit-stamp .kit-gap-s"], "the gap rules come last, so they win over a component's own margin");
});

test("lab 5: every pair of side-by-side runs carries the gap class on its second run", () => {
  const gap = (html: string, cls: string) => new RegExp(`class="${cls} kit-gap-s"`).test(html);
  const hdr = header({ t: EN, lang: "en", needsYou: 3 });
  assert.ok(gap(hdr, "kit-badge-count"), "Needs-you label + count");
  const log = logDrawer({ t: EN, open: true, rtl: false, lines: [], build: { version: "3.0.0", build: "abc1234" } });
  assert.ok(gap(log, "kit-log-title"), "log chevron + label");
  assert.ok(gap(log, "kit-log-count"), "log label + count");
  assert.match(log, /<span class="kit-stamp" dir="ltr"><span class="kit-nowrap">[^<]+<\/span>(<span class="kit-nowrap kit-gap-s">[^<]+<\/span>)+<\/span>/, "build stamp tokens");
  assert.ok(gap(chip({ label: "x", tone: "ok" }), "kit-chip-text"), "chip icon + text");
  assert.ok(!/kit-gap-s/.test(chip({ label: "x" })), "a chip with no icon needs no gap");
  assert.ok(gap(button({ label: "x", action: "a", icon: "close" }), "kit-btn-label"), "button icon + label");
  assert.ok(!/kit-gap-s/.test(button({ label: "x", action: "a" })), "a label alone needs no gap");
  assert.ok(gap(stepStrip({ t: EN, rtl: false, steps: [] }), "kit-step-name"), "step dot + label");
  assert.ok(gap(tabs({ t: EN, active: "a", items: [{ id: "a", label: "A", count: 2 }] }), "kit-tab-count"), "tab label + count");
  // the gallery has no literal space between two flex runs that the gap class should carry instead
  assert.doesNotMatch(ALL, /<\/span> <span/);
});

// ---- 4. fonts: brand family first, then system fonts ----

test("lab 4: the font stacks name the brand family first, then good Windows / macOS fallbacks, then the generic family", () => {
  assert.equal(TOK.get("--twn-font-ar"), '"IBM Plex Sans Arabic","Segoe UI",Tahoma,"Geeza Pro",sans-serif');
  assert.equal(TOK.get("--twn-font-mono"), '"IBM Plex Mono",Consolas,"SF Mono",Menlo,monospace');
  for (const [k, first] of [["--twn-font-display", '"Syne"'], ["--twn-font-ui", '"Inter"']] as const) {
    const v = TOK.get(k) ?? "";
    assert.ok(v.startsWith(`${first},"Segoe UI",`), `${k}: ${v}`);
    assert.match(v, /"Helvetica Neue"/, `${k} has a macOS fallback`);
    assert.ok(v.endsWith(",sans-serif"), k);
  }
});

// ---- 6. Latin words inside Arabic copy are left-to-right runs ----

test("lab 6: isolateLatin wraps Latin words inside Arabic, leaves (parenthesised terms), entities, `backticks` and non-Arabic text alone", () => {
  assert.equal(isolateLatin("محرّك WhyNot Cut لا يعمل."), 'محرّك <bdi dir="ltr">WhyNot Cut</bdi> لا يعمل.');
  assert.equal(isolateLatin("في Premiere بعد"), 'في <bdi dir="ltr">Premiere</bdi> بعد');
  assert.equal(isolateLatin("إعادة البناء (Rebuild)"), "إعادة البناء (Rebuild)");
  assert.equal(isolateLatin("افتح `C0239.prproj` الآن &amp; &#39;x"), 'افتح `C0239.prproj` الآن &amp; &#39;<bdi dir="ltr">x</bdi>');
  assert.equal(isolateLatin("The WhyNot Cut engine is not running."), "The WhyNot Cut engine is not running.");
  assert.equal(prose("<b> محرّك"), '&lt;<bdi dir="ltr">b</bdi>&gt; محرّك', "escaped first; an entity's letters (lt, gt) are never wrapped");
  assert.equal(withCommands("شغّل `reel doctor` في Premiere"), 'شغّل <bdi dir="ltr" class="kit-code">reel doctor</bdi> في <bdi dir="ltr">Premiere</bdi>');
});

test("lab 6: the Arabic gallery has no Latin letter outside a left-to-right run, except an English term in parentheses", () => {
  const stray: string[] = [];
  const stack: boolean[] = [];
  for (const m of GALLERY.ar.matchAll(/<(\/?)([a-z][a-z0-9]*)\b([^>]*)>|([^<]+)/g)) {
    const [, close, tag, attrs, text] = m;
    if (text !== undefined) {
      if (stack.includes(true)) continue;
      const bare = text.replace(/\([^()]*\)/g, "");
      if (/[A-Za-z]/.test(bare) && /\p{Script=Arabic}/u.test(text)) stray.push(text);
      continue;
    }
    if (/^(img|path|input|br|hr)$/.test(tag!) || attrs!.trimEnd().endsWith("/")) continue;
    if (close) stack.pop();
    else stack.push(/\sdir="ltr"/.test(attrs!) || /\slang="en"/.test(attrs!));
  }
  assert.deepEqual(stray, []);
  // and the shared strings that had a bare Latin word are now isolated where the kit shows them
  assert.ok(GALLERY.ar.includes('<bdi dir="ltr">Premiere</bdi>'));
  assert.ok(GALLERY.ar.includes('<bdi dir="ltr">WhyNot Cut</bdi>'));
  assert.ok(AR["offline.no_engine"].includes("WhyNot Cut") && EN["offline.no_engine"].includes("WhyNot Cut"));
});
