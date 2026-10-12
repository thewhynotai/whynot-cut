// B-T1 component kit tests (src/kit/*, styles/kit.css): markup structure, escaping, RTL (dir and order), <bdi dir="ltr">
// on left-to-right tokens, accessibility (labels, aria-*, the focus-ring class, 32 px hit targets), UXP CSS limits
// (flexbox only, an explicit display on every element the kit emits) and no hard-coded strings (all copy from the
// i18n table; i18n.test.ts scans the kit sources too).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { AR, EN, fmt, stringsFor } from "../src/i18n.ts";
import type { Strings } from "../src/i18n.ts";
import {
  aspectPct,
  button,
  buttonRow,
  card,
  chip,
  chips,
  cmdRow,
  dialog,
  emptyState,
  esc,
  eyebrow,
  footer,
  frameGrid,
  header,
  icon,
  kitRoot,
  langSwitch,
  logDrawer,
  paragraph,
  progress,
  section,
  statusIcon,
  stepStrip,
  tabs,
  toast,
  waveformFrame,
} from "../src/kit/index.ts";
import type { Html } from "../src/kit/index.ts";
import { esc as renderEsc } from "../src/render.ts";
import { sampleState } from "../src/mock.ts";
import { kitGallery } from "../dev/kit-gallery.ts";
import { PANEL_UI } from "./tokens-util.ts";

const EVIL = `<script>alert("x")</script>`;
const KIT_CSS = readFileSync(join(PANEL_UI, "styles", "kit.css"), "utf8");
const FLAT_CSS = KIT_CSS.replace(/\/\*[\s\S]*?\*\//g, "");

const noScript = (html: string) => {
  assert.ok(!html.includes("<script"), "an injected <script> reached the HTML");
  assert.ok(!/\son[a-z]+=/.test(html.replace(/&quot;|&#39;/g, "")), "an injected event handler attribute reached the HTML");
};
/** every <tag ...> start tag of an HTML string */
const tags = (html: string, name: string) => [...html.matchAll(new RegExp(`<${name}\\b([^>]*)>`, "g"))].map((m) => m[1]!);
const attr = (attrs: string, name: string) => new RegExp(`\\s${name}="([^"]*)"`).exec(attrs)?.[1];
const classesOf = (attrs: string) => (attr(attrs, "class") ?? "").split(/\s+/).filter(Boolean);
/** the inner text of each <button> (tags stripped) */
const buttons = (html: string) => [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].map((m) => ({ attrs: m[1]!, text: m[2]!.replace(/<[^>]*>/g, "").trim() }));

/** Every interactive element carries the focus-ring class and a label (visible text or aria-label). */
function assertControlsAccessible(html: string): void {
  for (const b of buttons(html)) {
    assert.ok(classesOf(b.attrs).includes("kit-focus"), `button without the focus-ring class: ${b.attrs}`);
    assert.equal(attr(b.attrs, "type"), "button", `button without type="button": ${b.attrs}`);
    assert.ok(b.text !== "" || (attr(b.attrs, "aria-label") ?? "").trim() !== "", `button without a label: ${b.attrs}`);
  }
}

// ---- helpers ----

test("kit esc is the panel's esc (same five characters); ltr runs are <bdi dir=\"ltr\">", () => {
  for (const v of [`<&>"'`, 5, null, undefined, "plain"]) assert.equal(esc(v), renderEsc(v));
  assert.equal(cmdRow("reel doctor"), '<div class="kit-cmd-row"><span class="kit-cmd"><bdi dir="ltr">reel doctor</bdi></span></div>');
  noScript(cmdRow(EVIL));
});

// ---- icons ----

test("icons: inline SVG in currentColor, hidden from screen readers unless labelled; directional chevrons mirror in RTL", () => {
  for (const name of ["ok", "warn", "error", "info", "chevron-down", "close"] as const) {
    const svg = icon(name);
    assert.match(svg, /^<svg class="kit-icon kit-icon-[a-z-]+" data-icon="[a-z-]+" viewBox="0 0 16 16" width="16" height="16" fill="currentColor" focusable="false" aria-hidden="true"><path fill-rule="evenodd" d="[^"]+"\/><\/svg>$/);
    assert.equal(icon(name, { rtl: true }), svg, `${name} has no direction: the same in RTL`);
  }
  assert.match(icon("chevron-end"), /kit-icon-chevron-right/);
  assert.match(icon("chevron-end", { rtl: true }), /kit-icon-chevron-left/);
  assert.match(icon("chevron-start"), /kit-icon-chevron-left/);
  assert.match(icon("chevron-start", { rtl: true }), /kit-icon-chevron-right/);
  const labelled = icon("error", { label: EVIL });
  assert.match(labelled, /role="img" aria-label="&lt;script&gt;/);
  assert.doesNotMatch(labelled, /aria-hidden/);
  noScript(labelled);
  for (const kind of ["ok", "warn", "error", "info"] as const) {
    assert.match(statusIcon(kind, EN), new RegExp(`aria-label="${EN[`status.${kind}`]}"`));
    assert.match(statusIcon(kind, AR), new RegExp(`aria-label="${AR[`status.${kind}`]}"`));
  }
});

// ---- header ----

test("header: monogram + WhyNot Cut + Needs-you badge + ع/EN switch + gradient hairline", () => {
  const html = header({ t: EN, lang: "en", needsYou: 3 });
  assert.match(html, /^<header class="kit-hdr">/);
  assert.match(html, /<img class="kit-mono" src="data:image\/png;base64,[^"]+" alt="" width="24" height="24">/);
  assert.match(html, /<span class="kit-wordmark"><bdi dir="ltr">WhyNot Cut<\/bdi><\/span>/);
  assert.match(html, /<div class="kit-hairline" aria-hidden="true"><\/div><\/header>$/);
  // badge: label + count in a left-to-right run, opens NEEDS-YOU, labelled with the count
  assert.match(html, /<button type="button" class="kit-badge kit-focus" data-action="open-needs-you" aria-label="[^"]*3[^"]*">/);
  assert.match(html, /<span class="kit-badge-count"><bdi dir="ltr">3<\/bdi><\/span>/);
  assert.ok(html.includes(esc(EN["needs.label"])));
  // no badge when nothing needs the editor; a bad count is no badge either
  for (const n of [0, -2, Number.NaN, undefined]) assert.doesNotMatch(header({ t: EN, lang: "en", needsYou: n }), /kit-badge/);
  assert.match(header({ t: EN, lang: "en", needsYou: 2.7 }), /<bdi dir="ltr">2<\/bdi>/);
  assertControlsAccessible(html);
});

test("language switch: ع then EN, the current one pressed, each labelled in its own language, data-lang for the shell", () => {
  for (const lang of ["en", "ar"] as const) {
    const t = stringsFor(lang);
    const html = langSwitch(t, lang);
    assert.match(html, new RegExp(`^<div class="kit-lang" role="group" aria-label="${t["lang.group"]}">`));
    const bs = buttons(html);
    assert.deepEqual(bs.map((b) => b.text), ["ع", "EN"]);
    assert.deepEqual(bs.map((b) => attr(b.attrs, "data-lang")), ["ar", "en"]);
    assert.deepEqual(bs.map((b) => attr(b.attrs, "lang")), ["ar", "en"]);
    assert.deepEqual(bs.map((b) => attr(b.attrs, "aria-pressed")), lang === "ar" ? ["true", "false"] : ["false", "true"]);
    assert.deepEqual(bs.map((b) => attr(b.attrs, "aria-label")), [t["lang.ar"], t["lang.en"]]);
    assert.ok(bs.every((b) => attr(b.attrs, "data-action") === "set-language"));
    assert.ok(classesOf(bs[lang === "ar" ? 0 : 1]!.attrs).includes("kit-lang-on"));
    assertControlsAccessible(html);
  }
});

// ---- tabs ----

test("tabs: a tablist; the active tab is selected (pink underline class); DOM order is the same in EN and AR (CSS direction mirrors it)", () => {
  const items = [
    { id: "home", label: EN["tab.home"] },
    { id: "edit", label: EN["tab.edit"], count: 2 },
    { id: "tools", label: EN["tab.tools"] },
  ];
  const html = tabs({ t: EN, items, active: "edit" });
  assert.match(html, new RegExp(`^<div class="kit-tabs" role="tablist" aria-label="${EN["tabs.label"]}">`));
  const bs = buttons(html);
  assert.deepEqual(bs.map((b) => attr(b.attrs, "data-tab")), ["home", "edit", "tools"]);
  assert.deepEqual(bs.map((b) => attr(b.attrs, "aria-selected")), ["false", "true", "false"]);
  assert.deepEqual(bs.map((b) => attr(b.attrs, "role")), ["tab", "tab", "tab"]);
  assert.ok(classesOf(bs[1]!.attrs).includes("kit-tab-on"));
  assert.match(html, /<span class="kit-tab-count"><bdi dir="ltr">2<\/bdi><\/span>/);
  // an unknown active id selects the first tab
  assert.equal(attr(buttons(tabs({ t: EN, items, active: "nope" }))[0]!.attrs, "aria-selected"), "true");
  const ar = tabs({ t: AR, items: items.map((i) => ({ ...i, label: AR[`tab.${i.id}` as keyof Strings] })), active: "edit" });
  assert.deepEqual(buttons(ar).map((b) => attr(b.attrs, "data-tab")), ["home", "edit", "tools"], "never reversed in the DOM");
  noScript(tabs({ t: EN, items: [{ id: EVIL, label: EVIL }], active: EVIL }));
  assertControlsAccessible(html);
});

// ---- card, section, paragraph ----

test("card: glass section with an optional eyebrow, title and status tone; body is kit HTML", () => {
  const body = paragraph(EN["rebuild.warning"]);
  const html = card({ eyebrow: EN["section.approval"], title: EN["approval.summary"], body });
  assert.match(html, /^<section class="kit-card" aria-label="Plan summary"><div class="kit-eyebrow"><bdi>Approval<\/bdi><\/div><h3 class="kit-card-title"><bdi>Plan summary<\/bdi><\/h3><div class="kit-card-body"><p class="kit-text">/);
  assert.match(card({ body, tone: "warn" }), /^<section class="kit-card kit-card-warn">/);
  assert.match(card({ body, tone: "bogus" as never }), /^<section class="kit-card">/, "an unknown tone is no tone");
  noScript(card({ eyebrow: EVIL, title: EVIL, body: paragraph(EVIL) }));
  assert.match(section({ title: EN["section.qc"], body }), /^<section class="kit-section" aria-label="Frames and QC"><h2 class="kit-eyebrow"><bdi>Frames and QC<\/bdi><\/h2>/);
  assert.equal(eyebrow(EVIL), `<div class="kit-eyebrow"><bdi>${esc(EVIL)}</bdi></div>`, "titles are isolated runs");
  // a paragraph keeps `commands` left-to-right
  assert.match(paragraph("Run `reel doctor` now."), /<bdi dir="ltr">reel doctor<\/bdi>/);
});

// ---- buttons ----

test("buttons: primary / secondary-glass / danger, type=button, data-action + data-*, disabled, optional gradient glow", () => {
  assert.equal(
    button({ label: "Go", action: "go", variant: "primary", data: { t: 1.5, id: "a" } }),
    '<button type="button" class="kit-btn kit-btn-primary kit-focus" data-action="go" data-t="1.5" data-id="a"><span class="kit-btn-label">Go</span></button>',
  );
  assert.match(button({ label: "x", action: "a" }), /kit-btn kit-btn-secondary kit-focus/, "secondary is the default");
  assert.match(button({ label: "x", action: "a", variant: "danger" }), /kit-btn kit-btn-danger kit-focus/);
  assert.match(button({ label: "x", action: "a", variant: "nope" as never }), /kit-btn-secondary/);
  assert.match(button({ label: "x", action: "a", disabled: true }), /<button [^>]* disabled>/);
  assert.match(button({ label: "x", action: "a", block: true }), /class="kit-btn kit-btn-secondary kit-focus kit-btn-block"/);
  assert.match(button({ label: "x", action: "a", variant: "primary", glow: true }), /^<span class="kit-glow"><button [^>]*kit-btn-primary[^>]*>.*<\/button><\/span>$/);
  assert.match(button({ label: "x", action: "a", variant: "primary", glow: true, block: true }), /^<span class="kit-glow kit-glow-block">/);
  assert.doesNotMatch(button({ label: "x", action: "a", variant: "secondary", glow: true }), /kit-glow/, "the glow is for the main (primary) CTA only");
  assert.match(button({ label: "x", action: "a", icon: "chevron-end", rtl: true }), /kit-icon-chevron-left/);
  assert.match(button({ label: "", action: "a", icon: "close", ariaLabel: "Close" }), /aria-label="Close"/);
  assert.throws(() => button({ label: "x", action: "a", data: { "bad key": 1 } }), /kit\.data-attribute="bad key"/);
  noScript(button({ label: EVIL, action: EVIL, data: { x: EVIL }, ariaLabel: EVIL }));
  const row = buttonRow([button({ label: "a", action: "a", variant: "primary" }), button({ label: "b", action: "b" })]);
  assert.match(row, /^<div class="kit-btn-row"><button/);
  assertControlsAccessible(row);
});

// ---- chips ----

test("chips: status tones always carry their icon; LTR chips (timecodes, commands) are mono <bdi dir=ltr>", () => {
  for (const tone of ["ok", "warn", "error", "info"] as const) {
    const html = chip({ label: "x", tone });
    assert.match(html, new RegExp(`^<span class="kit-chip kit-chip-${tone}"><svg [^>]*kit-icon-${tone}[^>]*aria-hidden="true"`));
  }
  assert.equal(chip({ label: "Medical", tone: "accent" }), '<span class="kit-chip kit-chip-accent"><span class="kit-chip-text">Medical</span></span>');
  assert.equal(chip({ label: "x" }), '<span class="kit-chip kit-chip-neutral"><span class="kit-chip-text">x</span></span>');
  assert.equal(chip({ label: "00:01:02:03", ltr: true }), '<span class="kit-chip kit-chip-neutral kit-chip-mono"><span class="kit-chip-text"><bdi dir="ltr">00:01:02:03</bdi></span></span>');
  assert.match(chip({ label: "x", tone: "bogus" as never }), /kit-chip-neutral/);
  noScript(chip({ label: EVIL, tone: "error" }));
  assert.match(chips([chip({ label: "a" })]), /^<div class="kit-chips"><span class="kit-chip/);
});

// ---- step strip ----

test("step strip: the 7 pipeline steps in order, state classes, icons for done/failed, numbers as LTR runs, mirrored chevrons", () => {
  const steps = [
    { id: "transcript", state: "done" },
    { id: "plan", state: "done" },
    { id: "approve", state: "waiting" },
    { id: "build", state: `running" onclick="x` },
  ] as const;
  const html = stepStrip({ t: EN, steps: steps as never, rtl: false });
  assert.match(html, new RegExp(`^<ol class="kit-steps" aria-label="${EN["section.pipeline"]}">`));
  const lis = tags(html, "li");
  assert.deepEqual(lis.map((a) => attr(a, "data-step")), ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"]);
  assert.deepEqual(lis.map((a) => classesOf(a)[1]), ["kit-step-done", "kit-step-done", "kit-step-waiting", "kit-step-pending", "kit-step-pending", "kit-step-pending", "kit-step-pending"], "an unknown state is pending");
  assert.equal(attr(lis[2]!, "aria-current"), "step");
  assert.equal(attr(lis[2]!, "aria-label"), fmt(EN["step.aria"], { name: EN["step.approve"], state: EN["step.state.waiting"] }));
  assert.match(html, /<span class="kit-step-dot"><svg [^>]*kit-icon-ok/);
  assert.match(html, /<span class="kit-step-dot"><bdi dir="ltr">3<\/bdi><\/span>/);
  // 6 separators, pointing in the reading direction
  assert.equal((html.match(/kit-step-sep/g) ?? []).length, 6);
  assert.equal((html.match(/kit-icon-chevron-right/g) ?? []).length, 6);
  const ar = stepStrip({ t: AR, steps: [{ id: "build", state: "failed" }], rtl: true });
  assert.equal((ar.match(/kit-icon-chevron-left/g) ?? []).length, 6, "RTL chevrons point left");
  assert.deepEqual(tags(ar, "li").map((a) => attr(a, "data-step")), ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"], "same DOM order in RTL");
  assert.match(ar, /kit-step-failed[^>]*><span class="kit-step-dot"><svg [^>]*kit-icon-error/);
  noScript(html);
});

// ---- progress ----

test("progress: plain-language status, n of N as LTR runs, gradient bar with aria values, elapsed m:ss, Cancel", () => {
  const html = progress({ t: EN, status: EN["progress.building"], n: 23, of: 47, elapsedS: 65, cancel: { action: "cancel", data: { id: "r1" } } });
  assert.match(html, /^<div class="kit-progress" role="group" aria-label="Building your sequence…">/);
  assert.match(html, /<span class="kit-progress-count"><bdi dir="ltr">23<\/bdi> of <bdi dir="ltr">47<\/bdi><\/span>/);
  assert.match(html, /<div class="kit-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="49" aria-valuetext="23\/47"><div class="kit-fill" style="width:49%"><\/div><\/div>/);
  assert.match(html, /<span class="kit-meta"><span class="kit-meta-k">elapsed<\/span><span class="kit-meta-v"><bdi dir="ltr">1:05<\/bdi><\/span><\/span>/);
  const cancel = buttons(html);
  assert.equal(cancel.length, 1);
  assert.equal(cancel[0]!.text, EN["pipeline.cancel"]);
  assert.equal(attr(cancel[0]!.attrs, "data-id"), "r1");
  assert.ok(classesOf(cancel[0]!.attrs).includes("kit-btn-secondary"), "Cancel is secondary (one primary per screen)");
  // no count: an indeterminate bar without aria-valuenow; no cancel, no elapsed
  const ind = progress({ t: EN, status: "x" });
  assert.match(ind, /<div class="kit-track kit-track-indeterminate" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="kit-fill" style="width:30%"><\/div><\/div>/);
  assert.doesNotMatch(ind, /<button|kit-meta|kit-progress-count/);
  // clamped
  assert.match(progress({ t: EN, status: "x", n: 99, of: 10 }), /aria-valuenow="100"/);
  assert.match(progress({ t: EN, status: "x", n: -3, of: 10 }), /aria-valuenow="0"/);
  noScript(progress({ t: EN, status: EVIL, n: 1, of: 2, cancel: { action: EVIL, data: { id: EVIL } } }));
  assertControlsAccessible(html);
});

// ---- toast ----

test("toast: status colour + icon; errors are alerts with a fix action and Copy diagnostics; commands become chips", () => {
  const err = toast({ t: EN, kind: "error", text: EN["offline.no_engine"], how: "In your session run `reel serve --ensure`", fix: { label: EN["action.retry"], action: "retry" } });
  assert.match(err, /^<div class="kit-toast kit-toast-error" role="alert" aria-live="assertive"><span class="kit-toast-icon"><svg [^>]*kit-icon-error[^>]*role="img" aria-label="Error"/);
  assert.match(err, /<div class="kit-cmd-row"><span class="kit-cmd"><bdi dir="ltr">reel serve --ensure<\/bdi><\/span><\/div>/);
  assert.match(err, /<div class="kit-toast-how">In your session run:<\/div>/);
  const bs = buttons(err);
  assert.deepEqual(bs.map((b) => attr(b.attrs, "data-action")), ["retry", "copy-diagnostics", "dismiss-toast"]);
  assert.equal(bs[1]!.text, EN["actions.diagnostics"]);
  assert.equal(attr(bs[2]!.attrs, "aria-label"), EN["notice.dismiss"]);
  assert.ok(bs.every((b) => !classesOf(b.attrs).includes("kit-btn-primary")), "a toast never adds a primary button");
  const ok = toast({ t: EN, kind: "ok", text: EN["notice.approved"] });
  assert.match(ok, /^<div class="kit-toast kit-toast-ok" role="status" aria-live="polite">/);
  assert.doesNotMatch(ok, /copy-diagnostics/, "Copy diagnostics is for errors (unless asked)");
  assert.doesNotMatch(toast({ t: EN, kind: "warn", text: "x", dismiss: false }), /dismiss-toast/);
  assert.match(toast({ t: EN, kind: "warn", text: "Check `engine.json`." }), /<bdi dir="ltr">engine\.json<\/bdi>/);
  assert.match(toast({ t: EN, kind: "bogus" as never, text: "x" }), /kit-toast-info/);
  noScript(toast({ t: EN, kind: "error", text: EVIL, how: EVIL, fix: { label: EVIL, action: EVIL } }));
  assertControlsAccessible(err);
});

// ---- dialog ----

test("dialog: destructive confirm shows what will change and the backup name (LTR chip), danger confirm + secondary cancel", () => {
  const html = dialog({
    t: EN,
    id: "rebuild",
    title: EN["rebuild.title"],
    changes: [EN["rebuild.warning"], "Uses `reel ppro-build --force`."],
    backupName: "C0239_prev_2026-10-13-1412.prproj",
    confirm: { label: EN["rebuild.confirm"], action: "rebuild-confirm" },
    cancel: { label: EN["rebuild.cancel"], action: "rebuild-cancel" },
  });
  assert.match(html, /^<div class="kit-dialog" id="rebuild" role="alertdialog" aria-modal="true" aria-labelledby="rebuild-title" aria-describedby="rebuild-changes">/);
  assert.match(html, /<h3 class="kit-dialog-title" id="rebuild-title">Rebuild this project\?<\/h3>/);
  assert.match(html, /<div class="kit-label">What will change<\/div><ul class="kit-dialog-changes" id="rebuild-changes"><li class="kit-dialog-change">/);
  assert.equal(tags(html, "li").length, 2);
  assert.match(html, /<bdi dir="ltr">reel ppro-build --force<\/bdi>/);
  assert.match(html, /<div class="kit-label">Backup copy<\/div><div class="kit-cmd-row"><span class="kit-cmd"><bdi dir="ltr">C0239_prev_2026-10-13-1412\.prproj<\/bdi><\/span><\/div>/);
  const bs = buttons(html);
  assert.deepEqual(bs.map((b) => attr(b.attrs, "data-action")), ["rebuild-confirm", "rebuild-cancel"]);
  assert.ok(classesOf(bs[0]!.attrs).includes("kit-btn-danger"));
  assert.ok(classesOf(bs[1]!.attrs).includes("kit-btn-secondary"));
  // no backup: it says so (never silent)
  const none = dialog({ t: EN, title: "x", changes: ["y"], confirm: { label: "a", action: "a" }, cancel: { label: "b", action: "b" } });
  assert.match(none, /<p class="kit-dialog-nobackup">No backup copy is made\. This cannot be undone\.<\/p>/);
  assert.match(none, /id="kit-dialog"/, "default id");
  // not destructive: the confirm is primary
  assert.match(dialog({ t: EN, title: "x", changes: ["y"], destructive: false, confirm: { label: "a", action: "a" }, cancel: { label: "b", action: "b" } }), /kit-btn-primary/);
  const evil = dialog({ t: EN, id: EVIL, title: EVIL, changes: [EVIL], backupName: EVIL, confirm: { label: EVIL, action: EVIL }, cancel: { label: EVIL, action: EVIL } });
  noScript(evil);
  assert.match(evil, /id="-script-alert--x----script-"/, "the id is reduced to safe characters");
  assertControlsAccessible(html);
});

// ---- empty state ----

test("empty state: icon, title, teaching text, exactly ONE action (primary by default)", () => {
  const html = emptyState({ title: EN["empty.noclient.title"], text: EN["empty.noclient.text"], action: { label: EN["empty.noclient.action"], action: "choose-client" } });
  assert.match(html, /^<div class="kit-empty" role="status"><span class="kit-empty-icon"><svg [^>]*kit-icon-info/);
  assert.match(html, /<h3 class="kit-empty-title">No client folder yet<\/h3><p class="kit-empty-text">/);
  assert.match(html, /<bdi dir="ltr">assets\/<\/bdi>/);
  const bs = buttons(html);
  assert.equal(bs.length, 1);
  assert.ok(classesOf(bs[0]!.attrs).includes("kit-btn-primary"));
  assert.match(emptyState({ title: "x", text: "y", primary: false, icon: "warn", action: { label: "a", action: "a" } }), /kit-icon-warn[\s\S]*kit-btn-secondary/);
  noScript(emptyState({ title: EVIL, text: EVIL, action: { label: EVIL, action: EVIL } }));
  assertControlsAccessible(html);
});

// ---- log drawer ----

test("log drawer: toggle with aria-expanded/controls and a direction-aware chevron; lines as LTR runs with level icons; build stamp; Copy diagnostics", () => {
  const lines = [
    { ts: "14:12:03", level: "info", text: "reel build --video-id C0239" },
    { ts: "14:12:09", level: "warn", text: "font fallback" },
    { ts: "14:12:11", level: "error", text: EVIL },
    { ts: "14:12:12", level: `x" onclick="y`, text: "z" },
  ] as const;
  const closed = logDrawer({ t: EN, open: false, lines: lines as never, rtl: false });
  assert.match(closed, /^<section class="kit-log" aria-label="Log"><button type="button" class="kit-log-toggle kit-focus" data-action="toggle-log" aria-expanded="false" aria-controls="kit-log-lines"><svg [^>]*kit-icon-chevron-right/);
  assert.match(closed, /<span class="kit-log-count"><bdi dir="ltr">4<\/bdi> lines<\/span>/);
  assert.doesNotMatch(closed, /<ul class="kit-log-lines"/);
  assert.match(logDrawer({ t: EN, open: false, lines: [], rtl: true }), /kit-icon-chevron-left/);
  const open = logDrawer({ t: EN, open: true, lines: lines as never, rtl: false, build: { version: "3.0.0", build: "c0112b5" } });
  assert.match(open, /aria-expanded="true"[^>]*><svg [^>]*kit-icon-chevron-down/);
  assert.match(open, /<ul class="kit-log-lines" id="kit-log-lines">/);
  assert.match(open, /<li class="kit-log-line kit-log-info"><span class="kit-log-ts"><bdi dir="ltr">14:12:03<\/bdi><\/span><span class="kit-log-text"><bdi dir="ltr">reel build --video-id C0239<\/bdi><\/span><\/li>/);
  assert.match(open, /<li class="kit-log-line kit-log-warn"><span class="kit-log-ts"><bdi dir="ltr">14:12:09<\/bdi><\/span><span class="kit-log-icon"><svg [^>]*kit-icon-warn/);
  assert.equal((open.match(/kit-log-line kit-log-info/g) ?? []).length, 2, "an unknown level is info");
  assert.match(open, /<span class="kit-log-build"><bdi dir="ltr">WhyNot Cut 3\.0\.0 · build c0112b5<\/bdi><\/span>/);
  assert.match(open, /data-action="copy-diagnostics"/);
  noScript(open);
  assert.match(logDrawer({ t: EN, open: true, lines: [], rtl: false }), /<p class="kit-log-empty">No log lines yet\.<\/p>/);
  // only the last `max` lines
  const many = Array.from({ length: 150 }, (_, i) => ({ ts: String(i), level: "info" as const, text: `l${i}` }));
  const m = logDrawer({ t: EN, open: true, lines: many, rtl: false });
  assert.equal(tags(m, "li").length, 100);
  assert.match(m, /<bdi dir="ltr">150<\/bdi> lines/);
  assert.match(m, />l149</);
  assertControlsAccessible(open);
});

// ---- frame grid ----

test("frame grid: aspect from w/h (9:16 default, 4:5, clamped), safe thumbnails only, verdict chips with icons, seek buttons labelled", () => {
  assert.equal(aspectPct(1080, 1920), 177.78);
  assert.equal(aspectPct(1080, 1350), 125);
  assert.equal(aspectPct(1920, 1080), 56.25);
  assert.equal(aspectPct(undefined, undefined), 177.78);
  assert.equal(aspectPct(0, 100), 177.78);
  assert.equal(aspectPct(Number.NaN, 5), 177.78);
  assert.equal(aspectPct(100, 1000), 300);
  assert.equal(aspectPct(1000, 100), 40);
  const frames = sampleState("en", "qc").qc;
  const html = frameGrid({ t: EN, frames });
  assert.match(html, /^<div class="kit-frames" role="list" aria-label="Frames and QC">/);
  assert.equal(tags(html, "div").filter((a) => classesOf(a)[0] === "kit-frame-tile").length, frames.length);
  for (const f of frames) {
    assert.ok(html.includes(`aria-label="${esc(fmt(EN["frame.seek"], { tc: f.tc }))}"`));
    assert.ok(html.includes(`<span class="kit-frame-tc"><bdi dir="ltr">${esc(f.tc)}</bdi></span>`));
  }
  assert.match(html, /style="padding-top:125%"/, "the 4:5 frame");
  assert.match(html, /kit-verdict-pass[\s\S]*?kit-chip kit-chip-ok"><svg/);
  const evil = frameGrid({
    t: EN,
    frames: [
      { t_s: 1, tc: EVIL, file: EVIL, label: EVIL, verdict: "fail", thumb: `javascript:${EVIL}` },
      { t_s: 2, tc: "x", file: "y", label: "z", verdict: `pass" onclick="x` as never, thumb: "https://example.com/a.png" },
      { t_s: 3, tc: "x", file: "y", label: "z", verdict: "pass", thumb: "data:image/png;base64,AAAA" },
    ],
  });
  noScript(evil);
  assert.doesNotMatch(evil, /javascript:|https:\/\//, "no script or network thumbnail");
  assert.match(evil, /<img class="kit-frame-img" src="data:image\/png;base64,AAAA" alt="">/);
  assert.match(evil, /kit-verdict-pending/, "an unknown verdict is pending");
  assertControlsAccessible(html);
});

// ---- waveform frame ----

test("waveform frame: a labelled container with a slot, mid line and placeholder; timeline ruler stays left-to-right", () => {
  const html = waveformFrame({ t: EN, start: "00:00:00:00", end: "00:00:42:10", slot: "hush" });
  assert.match(html, /^<div class="kit-wave" role="group" aria-label="Audio waveform"><div class="kit-wave-box" data-wave-slot="hush" style="height:64px"><div class="kit-wave-mid" aria-hidden="true"><\/div><div class="kit-wave-placeholder">The waveform appears after the scan\.<\/div><\/div>/);
  assert.match(html, /<div class="kit-wave-ruler"><span class="kit-wave-tc"><bdi dir="ltr">00:00:00:00<\/bdi><\/span><span class="kit-spacer"><\/span><span class="kit-wave-tc"><bdi dir="ltr">00:00:42:10<\/bdi><\/span><\/div>/);
  assert.doesNotMatch(waveformFrame({ t: EN }), /kit-wave-ruler/);
  assert.match(waveformFrame({ t: EN, height: 5000 }), /height:240px/);
  assert.match(waveformFrame({ t: EN, height: 2 }), /height:32px/);
  noScript(waveformFrame({ t: EN, label: EVIL, start: EVIL, end: EVIL, slot: EVIL }));
  // the timeline is never mirrored: CSS keeps the box and the ruler left-to-right
  assert.match(cssRule(".kit-wave-box"), /direction: ltr/);
  assert.match(cssRule(".kit-wave-ruler"), /direction: ltr/);
});

// ---- root and footer ----

test("kit root: dir/lang/class per language (RTL via CSS direction), one scroll region; footer «Powered by thewhynot.ai» as an LTR run", () => {
  const body = paragraph("x");
  assert.equal(kitRoot({ lang: "en", body }), '<div class="kit-root kit-ltr" dir="ltr" lang="en"><div class="kit-scroll"><p class="kit-text">x</p></div></div>');
  assert.equal(kitRoot({ lang: "ar", body }), '<div class="kit-root kit-rtl" dir="rtl" lang="ar"><div class="kit-scroll"><p class="kit-text">x</p></div></div>');
  assert.equal(footer(AR), '<footer class="kit-foot"><bdi dir="ltr">Powered by thewhynot.ai</bdi></footer>');
  assert.match(cssRule(".kit-rtl"), /direction: rtl/);
  assert.match(cssRule(".kit-ltr"), /direction: ltr/);
  assert.match(cssRule(".kit-root bdi"), /display: inline(?!-)/, "UXP: bdi is set inline in CSS");
  // the height chain: root and scroll are flex columns that may shrink (min-height: 0), the scroll region scrolls
  assert.match(cssRule(".kit-root"), /height: 100%/);
  assert.match(cssRule(".kit-root"), /min-height: 0/);
  assert.match(cssRule(".kit-scroll"), /min-height: 0/);
  assert.match(cssRule(".kit-scroll"), /overflow-y: auto/);
  assert.match(cssRule(".kit-scroll"), /overflow-x: hidden/, "nothing scrolls sideways");
});

// ---- the gallery (dev harness "Kit" scenario): every component, EN and AR ----

const GALLERY = { en: kitGallery("en"), ar: kitGallery("ar") };

test("gallery renders every component in EN and AR, in the same DOM order, with no 'Claude Code' and the footer", () => {
  const parts = ["kit-hdr", "kit-lang", "kit-badge", "kit-tabs", "kit-card", "kit-btn-primary", "kit-btn-secondary", "kit-btn-danger", "kit-glow", "kit-chip-ok", "kit-chip-warn", "kit-chip-error", "kit-chip-info", "kit-steps", "kit-progress", "kit-toast-error", "kit-toast-ok", "kit-dialog", "kit-empty", "kit-log", "kit-frames", "kit-wave", "kit-foot"];
  for (const lang of ["en", "ar"] as const) {
    const html = GALLERY[lang];
    for (const p of parts) assert.ok(html.includes(`"${p}"`) || html.includes(`${p} `) || html.includes(` ${p}"`), `${lang} gallery lacks ${p}`);
    assert.doesNotMatch(html, /claude\s*code/i);
    assert.ok(html.includes("Powered by thewhynot.ai"));
  }
  assert.match(GALLERY.ar, /^<div class="kit-root kit-rtl" dir="rtl" lang="ar">/);
  const order = (h: string) => [...h.matchAll(/data-(?:step|tab|action)="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order(GALLERY.ar), order(GALLERY.en), "AR mirrors through CSS direction only: the DOM order is the same");
  assert.ok(GALLERY.ar.includes(AR["progress.building"]));
  assertControlsAccessible(GALLERY.en);
  assertControlsAccessible(GALLERY.ar);
});

// ---- CSS: UXP limits, explicit display, hit targets, focus ring, mirroring ----

function cssRules(): { selectors: string[]; body: string }[] {
  return [...FLAT_CSS.matchAll(/([^{}]+)\{([^}]*)\}/g)].map((m) => ({ selectors: m[1]!.split(",").map((s) => s.trim()), body: m[2]! }));
}
function cssRule(selector: string): string {
  const found = cssRules().filter((r) => r.selectors.includes(selector));
  assert.ok(found.length, `kit.css has no rule for ${selector}`);
  return found.map((r) => r.body).join(";");
}
/** the rules whose selector ends in a compound that names the class (e.g. ".kit-btn", ".kit-glow .kit-btn") */
const rulesFor = (cls: string) =>
  cssRules().filter((r) => r.selectors.some((s) => (s.split(/\s+|>/).filter(Boolean).pop() ?? "").split(/(?=[.:[])/).includes(`.${cls}`)));

test("kit.css: flexbox only (no grid, gap, sticky, :has), no @font-face/@import, no row-reverse (CSS direction mirrors once)", () => {
  assert.doesNotMatch(FLAT_CSS, /display\s*:\s*(inline-)?grid|grid-template|(?:^|[;{\s])(?:row-|column-)?gap\s*:|position\s*:\s*sticky|:has\(/);
  assert.doesNotMatch(FLAT_CSS, /@font-face|@import|url\(/);
  assert.doesNotMatch(FLAT_CSS, /row-reverse|column-reverse/);
  assert.doesNotMatch(FLAT_CSS, /inline-flex|inline-block/, "no inline-flex / inline-block (UXP draws them over running text)");
  assert.doesNotMatch(FLAT_CSS, /\[[a-z-]+[~|^$*]?=/, "no attribute selectors: state is a class");
});

test("kit.css: every element class the kit emits has a rule with an explicit display", () => {
  const emitted = new Set<string>();
  for (const html of Object.values(GALLERY)) {
    for (const m of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/g)) {
      if (["bdi", "path"].includes(m[1]!)) continue;
      const first = classesOf(m[2]!)[0];
      assert.ok(first, `<${m[1]}${m[2]}> has no class: every kit element is styled explicitly`);
      emitted.add(first);
    }
  }
  const missing = [...emitted].filter((c) => !rulesFor(c).some((r) => /(?:^|;)\s*display\s*:/.test(r.body)));
  assert.deepEqual(missing, []);
});

test("kit.css: every button class is a 32 px hit target; the focus ring is the #9D6BFF token", () => {
  const px = (body: string, prop: string) => Number(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*(\\d+)px`).exec(body)?.[1] ?? 0);
  const buttonClasses = new Set<string>();
  for (const html of Object.values(GALLERY)) for (const b of buttons(html)) buttonClasses.add(classesOf(b.attrs)[0]!);
  assert.ok(buttonClasses.size >= 7, [...buttonClasses].join(","));
  for (const c of buttonClasses) {
    const body = rulesFor(c).map((r) => r.body).join(";");
    assert.ok(px(body, "min-height") >= 32, `.${c} min-height < 32px`);
  }
  for (const c of ["kit-x", "kit-lang-btn", "kit-btn"]) assert.ok(px(cssRule(`.${c}`), "min-width") >= 32, `.${c} min-width < 32px`);
  assert.match(cssRule(".kit-focus:focus"), /box-shadow: var\(--twn-focus\)/);
});

test("kit.css: the card is glass + border + 16 px radius; pills 999 px; the gradient only on the hairline, progress fill and CTA glow", () => {
  const cardRule = cssRule(".kit-card");
  assert.match(cardRule, /background: var\(--twn-glass\)/);
  assert.match(cardRule, /border: 1px solid var\(--twn-border\)/);
  assert.match(cardRule, /border-radius: var\(--twn-radius-card\)/);
  assert.doesNotMatch(FLAT_CSS, /var\(--twn-surface\)/, "the kit never paints the solid #121212 surface (cards are glass over black)");
  for (const c of [".kit-chip", ".kit-btn", ".kit-badge", ".kit-lang"]) assert.match(cssRule(c), /border-radius: var\(--twn-radius-pill\)/, c);
  const gradientUsers = cssRules().filter((r) => /var\(--twn-gradient\)/.test(r.body)).flatMap((r) => r.selectors).sort();
  assert.deepEqual(gradientUsers, [".kit-fill", ".kit-glow", ".kit-hairline"]);
  assert.match(cssRule(".kit-tab-on"), /border-bottom-color: var\(--twn-accent\)/, "pink active-tab underline");
  assert.match(cssRule(".kit-btn-primary"), /background: var\(--twn-primary\)/);
  assert.match(cssRule(".kit-btn-primary"), /color: var\(--twn-on-primary\)/);
  assert.match(cssRule(".kit-eyebrow"), /text-transform: uppercase/);
  assert.match(cssRule(".kit-eyebrow"), /font-family: var\(--twn-font-display\)/);
  assert.match(cssRule(".kit-rtl .kit-eyebrow"), /font-family: var\(--twn-font-ar\)/, "Arabic eyebrows use IBM Plex Sans Arabic, no uppercase");
  assert.match(cssRule(".kit-cmd"), /font-family: var\(--twn-font-mono\)/);
});

/** Violet / pink TEXT on two glass layers is about 4.25:1 (contrast.test.ts): kit markup may put it on one glass layer
 *  (a card) at most. Glass classes and violet/pink text classes are read from kit.css (icon holders, "-icon", are
 *  non-text and need only 3:1). */
function deepGlassText(html: string): string[] {
  const glass = new Set<string>();
  const violetPink = new Set<string>();
  for (const r of cssRules()) {
    for (const s of r.selectors) {
      if (!/^\.[a-z0-9_-]+$/.test(s)) continue;
      const c = s.slice(1);
      if (/background\s*:\s*var\(--twn-glass\)/.test(r.body)) glass.add(c);
      if (/(?:^|;)\s*color\s*:\s*var\(--twn-(?:primary-text|accent)\)/.test(r.body) && !c.endsWith("-icon")) violetPink.add(c);
    }
  }
  assert.ok(glass.has("kit-card") && violetPink.has("kit-eyebrow"), "the guard reads kit.css");
  const found: string[] = [];
  const stack: number[] = [];
  for (const m of html.matchAll(/<(\/?)([a-z][a-z0-9]*)\b([^>]*)>/g)) {
    const [, close, tag, attrs] = m;
    if (close) {
      stack.pop();
      continue;
    }
    const cls = classesOf(attrs!);
    const depth = (stack.at(-1) ?? 0) + (cls.some((c) => glass.has(c)) ? 1 : 0);
    if (depth >= 2 && cls.some((c) => violetPink.has(c))) found.push(`<${tag} class="${cls.join(" ")}"> on ${depth} glass layers`);
    if (!/^(img|input|br|hr|path)$/.test(tag!) && !attrs!.trimEnd().endsWith("/")) stack.push(depth);
  }
  return found;
}

test("violet / pink text never sits on two glass layers (a chip or eyebrow inside a toast or dialog inside a card)", () => {
  // self-check: an info chip in a toast in a card is caught; an eyebrow in a card is fine
  const bad = card({ body: toast({ t: EN, kind: "info", text: "x", fix: null, dismiss: false }).replace("</div></div>", `${chip({ label: "x", tone: "info" })}</div></div>`) as Html });
  assert.equal(deepGlassText(bad).length, 1);
  assert.deepEqual(deepGlassText(card({ eyebrow: "x", body: chips([chip({ label: "y", tone: "accent" })]) })), []);
  for (const html of Object.values(GALLERY)) assert.deepEqual(deepGlassText(html), []);
});

test("kit sources: one file per component group, all re-exported from src/kit/index.ts", () => {
  const files = readdirSync(join(PANEL_UI, "src", "kit")).filter((f) => f.endsWith(".ts")).sort();
  const index = readFileSync(join(PANEL_UI, "src", "kit", "index.ts"), "utf8");
  for (const f of files) if (f !== "index.ts") assert.ok(index.includes(`./${f}"`), `index.ts does not re-export ${f}`);
});

test("Html is a branded string: kit functions return markup the next function accepts", () => {
  const h: Html = paragraph("x");
  assert.equal(typeof h, "string");
  assert.match(card({ body: h }), /<p class="kit-text">x<\/p>/);
});
