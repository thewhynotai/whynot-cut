import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { esc, initialUi, render } from "../src/render.ts";
import { AR, EN, stringsFor } from "../src/i18n.ts";
import { sampleState } from "../src/mock.ts";
import type { PanelState } from "../src/source.ts";

const STEP_IDS = ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"];
const EVIL = `<script>alert("x")</script>`;
const SCENARIOS = ["showcase", "approval", "building", "qc", "idle"] as const;

function evilState(): PanelState {
  const s = sampleState("en", "showcase");
  s.client = EVIL;
  s.item = EVIL;
  s.editor_name = EVIL;
  s.connection.host.detail = EVIL;
  s.context = { project_path: `C:\\"><img src=x onerror=1>\\p.prproj`, sequence_name: EVIL, folder: EVIL, out_dir: EVIL, review_mp4: EVIL };
  if (s.approval) {
    s.approval.summary = EVIL;
    s.approval.preview_mp4 = EVIL;
    s.approval.fingerprint = `"${EVIL}`;
    for (const f of s.approval.flagged) {
      f.text = EVIL;
      f.tc = EVIL;
    }
  }
  for (const q of s.qc) {
    q.label = EVIL;
    q.tc = EVIL;
    q.file = EVIL;
    q.thumb = `javascript:${EVIL}`;
  }
  for (const l of s.log) {
    l.text = EVIL;
    l.ts = EVIL;
  }
  for (const st of s.pipeline) st.request_id = EVIL;
  s.pipeline[0]!.state = `done" onmouseover="x` as never;
  return s;
}

test("esc escapes the five HTML-significant characters", () => {
  assert.equal(esc(`<&>"'`), "&lt;&amp;&gt;&quot;&#39;");
  assert.equal(esc(5 as unknown as string), "5");
  assert.equal(esc(null as unknown as string), "");
});

test("every dynamic value is escaped: an injected <script> never reaches the HTML", () => {
  const ui = initialUi();
  ui.logOpen = true;
  ui.confirmRebuild = true;
  ui.notice = { kind: "error", text: EVIL };
  ui.changeText = EVIL;
  ui.editorName = EVIL;
  for (const lang of ["en", "ar"] as const) {
    const s = evilState();
    s.language = lang;
    const html = render(s, stringsFor(lang), ui);
    assert.ok(!html.includes("<script"), `${lang}: raw <script in output`);
    assert.ok(!/<img[^>]*onerror/i.test(html), `${lang}: attribute breakout`);
    assert.ok(html.includes("&lt;script&gt;"), `${lang}: escaped form missing`);
    assert.ok(!/javascript:/i.test(html), `${lang}: javascript: URL kept`);
    assert.ok(!html.includes("onmouseover"), `${lang}: step state reached a class attribute`);
  }
});

test('paths, commands and timecodes sit inside <bdi dir="ltr">', () => {
  const s = sampleState("ar", "showcase");
  s.connection.engine = "offline";
  const html = render(s, AR, { ...initialUi(), logOpen: true });
  const inBdi = (txt: string) => assert.ok(html.includes(`<bdi dir="ltr">${esc(txt)}</bdi>`), `not isolated: ${txt}`);
  inBdi(s.context.project_path as string);
  inBdi(s.approval!.flagged[0]!.tc);
  inBdi(s.qc[0]!.tc);
  inBdi("reel doctor"); // also wrapped in a .cmd chip (own test below)
  inBdi(s.log[0]!.text);
});

test("AR render carries dir=rtl lang=ar on the container; EN carries ltr/en", () => {
  const ar = render(sampleState("ar", "showcase"), AR, initialUi());
  assert.match(ar, /^<div class="twn-panel twn-rtl" dir="rtl" lang="ar"/);
  const en = render(sampleState("en", "showcase"), EN, initialUi());
  assert.match(en, /^<div class="twn-panel twn-ltr" dir="ltr" lang="en"/);
  assert.ok(!en.includes('dir="rtl"'));
  assert.ok(!/sp-theme/.test(ar), "RTL must never go through sp-theme");
});

test('"Claude Code" never appears in any rendered state; "Powered by thewhynot.ai" does', () => {
  for (const lang of ["en", "ar"] as const) {
    for (const scenario of SCENARIOS) {
      const html = render(sampleState(lang, scenario), stringsFor(lang), { ...initialUi(), logOpen: true, confirmRebuild: true });
      assert.ok(!/claude\s*code/i.test(html), `${lang}/${scenario}`);
      assert.ok(html.includes("Powered by thewhynot.ai"), `${lang}/${scenario}`);
      assert.ok(html.includes("WhyNot Cut"));
    }
  }
});

test("the pipeline has exactly the 7 steps in order", () => {
  const html = render(sampleState("en", "showcase"), EN, initialUi());
  const ids = [...html.matchAll(/data-step="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, STEP_IDS);
});

test("render does not trust a short pipeline: always the 7 steps", () => {
  const s = sampleState("en", "idle");
  s.pipeline = [];
  const ids = [...render(s, EN, initialUi()).matchAll(/data-step="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, STEP_IDS);
});

test("QC tiles carry data-t and a verdict class; Re-export only on pending / media_pending", () => {
  const s = sampleState("en", "showcase");
  const html = render(s, EN, initialUi());
  const tiles = [...html.matchAll(/<div class="qc-tile qc-(\w+)" data-t="([\d.]+)"/g)];
  assert.equal(tiles.length, s.qc.length);
  assert.deepEqual(new Set(tiles.map((m) => m[1])), new Set(["pass", "fail", "pending", "media_pending"]));
  const reexports = [...html.matchAll(/data-action="reexport" data-t="([\d.]+)"/g)].map((m) => Number(m[1]));
  const expected = s.qc.filter((q) => q.verdict === "pending" || q.verdict === "media_pending").map((q) => q.t_s);
  assert.deepEqual(reexports, expected);
  assert.ok(/data-action="seek" data-t="[\d.]+"/.test(html));
});

test("approval inbox: Approve carries the fingerprint, both flagged items show, Request changes is disabled until text", () => {
  const s = sampleState("en", "approval");
  assert.equal(s.approval!.flagged.length, 2);
  let html = render(s, EN, initialUi());
  assert.ok(html.includes(`data-action="approve"`));
  assert.ok(html.includes(`data-fingerprint="${s.approval!.fingerprint}"`));
  assert.equal((html.match(/class="flag flag-/g) ?? []).length, 2);
  assert.match(html, /data-action="request-changes"[^>]*disabled/);
  html = render(s, EN, { ...initialUi(), changeText: "Shorten the intro" });
  assert.ok(!/data-action="request-changes"[^>]*disabled/.test(html));
  html = render(s, EN, { ...initialUi(), changeText: "   " });
  assert.match(html, /data-action="request-changes"[^>]*disabled/);
});

test("no approval pending: the inbox says so and shows no Approve button", () => {
  const html = render(sampleState("en", "idle"), EN, initialUi());
  assert.ok(!html.includes('data-action="approve"'));
  assert.ok(html.includes(EN["approval.empty"]));
});

test("without an editor name Approve is disabled and a name field is shown", () => {
  const s = sampleState("en", "approval");
  s.editor_name = "";
  const html = render(s, EN, initialUi());
  assert.match(html, /data-action="approve"[^>]*disabled/);
  assert.ok(html.includes('data-field="editor_name"'));
  const named = render(s, EN, { ...initialUi(), editorName: "Layla" });
  assert.ok(!/data-action="approve"[^>]*disabled/.test(named));
});

test("log drawer is collapsed by default and opens from ui state", () => {
  const s = sampleState("en", "showcase");
  const closed = render(s, EN, initialUi());
  assert.ok(closed.includes('data-action="toggle-log"'));
  assert.ok(!closed.includes('class="log-lines"'));
  const open = render(s, EN, { ...initialUi(), logOpen: true });
  assert.ok(open.includes('class="log-lines"'));
});

test("Rebuild shows the in-panel confirm with the edited-project warning and backup note (no browser confirm)", () => {
  const s = sampleState("en", "qc");
  const before = render(s, EN, initialUi());
  assert.ok(before.includes('data-action="rebuild"'));
  assert.ok(!before.includes('data-action="rebuild-confirm"'));
  const html = render(s, EN, { ...initialUi(), confirmRebuild: true });
  assert.ok(html.includes('data-action="rebuild-confirm"'));
  assert.ok(html.includes('data-action="rebuild-cancel"'));
  assert.ok(html.includes(esc(EN["rebuild.warning"])));
  assert.ok(html.includes(esc(EN["rebuild.backup"])));
});

test("the build step shows progress, elapsed and Cancel; idle has no Cancel", () => {
  const html = render(sampleState("en", "building"), EN, initialUi());
  assert.match(html, /class="progress-fill" style="width:\d+%"/);
  assert.ok(html.includes('data-action="cancel"'));
  const idle = render(sampleState("en", "idle"), EN, initialUi());
  assert.ok(!idle.includes('data-action="cancel"'));
});

test("pills: Engine / Claude / Host, with state classes", () => {
  const html = render(sampleState("en", "showcase"), EN, initialUi());
  for (const k of ["engine", "claude", "host"]) assert.ok(html.includes(`data-pill="${k}"`));
  const off = sampleState("en", "idle");
  off.connection.engine = "offline";
  assert.ok(render(off, EN, initialUi()).includes('class="pill pill-offline" data-pill="engine"'));
});

test("flexbox only: the shipped CSS has no grid, sticky, :has() or @font-face", () => {
  for (const f of ["../styles/tokens.css", "../styles/panel.css"]) {
    const css = readFileSync(new URL(f, import.meta.url), "utf8");
    assert.ok(!/display\s*:\s*(inline-)?grid|grid-template|position\s*:\s*sticky|:has\(|@font-face/.test(css), f);
  }
});

test("tokens.css carries Appendix D verbatim plus --twn-focus", () => {
  const css = readFileSync(new URL("../styles/tokens.css", import.meta.url), "utf8").replace(/\s+/g, "");
  for (const t of [
    "--twn-bg:#161616", "--twn-surface:#1F1F1F", "--twn-surface-2:#2A2A2A", "--twn-border:rgba(255,255,255,.14)",
    "--twn-text:#FFF", "--twn-text-muted:#B3B3B3", "--twn-primary:#5400FB", "--twn-primary-hover:#6A1FFF",
    "--twn-primary-text:#9D6BFF", "--twn-accent:#D95C9B", "--twn-deep:#390796",
    "--twn-gradient:linear-gradient(90deg,#D95C9B0%,#5400FB100%)", "--twn-ok:#3DD68C", "--twn-warn:#FFB020", "--twn-error:#FF5C5C",
    '--twn-font-display:"Syne","Inter",sans-serif', '--twn-font-ui:"Inter",system-ui,sans-serif',
    '--twn-font-ar:"IBMPlexSansArabic","NotoSansArabic",sans-serif', "--twn-radius:8px", "--twn-focus:0002px#9D6BFF",
  ]) {
    assert.ok(css.includes(t), `missing ${t}`);
  }
});

test("every selector class the renderer emits for QC verdicts and pills exists in panel.css", () => {
  const css = readFileSync(new URL("../styles/panel.css", import.meta.url), "utf8");
  for (const c of ["qc-pass", "qc-fail", "qc-pending", "qc-media_pending", "pill-ok", "pill-offline", "pill-warn", "progress-fill", "twn-rtl"]) {
    assert.ok(css.includes(`.${c}`), `panel.css lacks .${c}`);
  }
});

test("QC tiles follow the frame's aspect: default 9:16, 4:5 from w/h, bad w/h fall back to 9:16", () => {
  const s = sampleState("en", "qc");
  const ratioOf = (q: Partial<PanelState["qc"][number]>) => {
    const st = sampleState("en", "qc");
    st.qc = [{ ...st.qc[0]!, ...q }];
    const m = /class="qc-frame" style="padding-top:([\d.]+)%"/.exec(render(st, EN, initialUi()));
    assert.ok(m, "no .qc-frame with an aspect");
    return Number(m[1]);
  };
  assert.equal(ratioOf({}), 177.78);
  assert.equal(ratioOf({ w: 1080, h: 1920 }), 177.78);
  assert.equal(ratioOf({ w: 1080, h: 1350 }), 125);
  for (const bad of [{ w: 0, h: 10 }, { w: -1, h: 5 }, { w: Number.NaN, h: 1 }, { w: 10 }, { h: 10 }, { w: "x", h: "y" }]) {
    assert.equal(ratioOf(bad as never), 177.78, JSON.stringify(bad));
  }
  assert.equal(ratioOf({ w: 1, h: 100000 }), 300, "extreme ratios are clamped");
  assert.ok(s.qc.length > 0);
});

test("the showcase mock includes a 4:5 tile next to 9:16 ones", () => {
  const s = sampleState("en", "showcase");
  assert.ok(s.qc.some((q) => q.w === 1080 && q.h === 1350));
  assert.ok(s.qc.some((q) => !q.w && !q.h));
  const css = readFileSync(new URL("../styles/panel.css", import.meta.url), "utf8");
  assert.ok(css.includes(".qc-frame"));
});

// ---- narrow docks (live render in Premiere 26.5.2 UXP at ~350 px) ----

const panelCss = () => readFileSync(new URL("../styles/panel.css", import.meta.url), "utf8");
/** The declarations of the first rule whose selector is exactly `selector` (whitespace-insensitive). */
function rule(css: string, selector: string): string {
  const flat = css.replace(/\/\*[\s\S]*?\*\//g, "");
  let from = 0;
  for (;;) {
    const at = flat.indexOf(selector, from);
    assert.ok(at >= 0, `no rule for ${selector}`);
    const before = flat.slice(0, at).trimEnd();
    const open = flat.indexOf("{", at);
    const between = flat.slice(at + selector.length, open).trim();
    // exact selector: starts a rule (after a closing brace or the file start) and is followed straight by the brace
    if ((before === "" || before.endsWith("}")) && between === "") {
      return flat.slice(open + 1, flat.indexOf("}", open)).replace(/\s+/g, " ");
    }
    from = at + 1;
  }
}

test("header is three stacked rows: brand / client-item / pills (pills never inside the brand row)", () => {
  for (const lang of ["en", "ar"] as const) {
    for (const scenario of ["showcase", "idle"] as const) {
      const html = render(sampleState(lang, scenario), stringsFor(lang), initialUi());
      const hdr = /<header class="hdr">([\s\S]*?)<\/header>/.exec(html)![1]!;
      const order = [...hdr.matchAll(/<div class="(hdr-title|hairline|who|pills)"/g)].map((m) => m[1]);
      assert.deepEqual(order, ["hdr-title", "hairline", "who", "pills"]);
      const title = /<div class="hdr-title">([\s\S]*?)<\/div>/.exec(hdr)![1]!;
      assert.ok(!title.includes("pill") && !title.includes("who"), "brand row holds only monogram + wordmark");
      assert.equal((hdr.match(/data-pill="/g) ?? []).length, 3);
    }
  }
  const s = sampleState("en", "idle");
  s.client = "";
  assert.ok(render(s, EN, initialUi()).includes(`<div class="who">${EN["status.noclient"]}</div>`));
});

test("CSS: brand line never wraps; header and pills are explicit flex; pills wrap and are never clipped or ellipsized", () => {
  const css = panelCss();
  assert.match(rule(css, ".wordmark"), /white-space: nowrap/);
  assert.match(rule(css, ".wordmark"), /flex: 0 0 auto/);
  assert.match(rule(css, ".hdr-title"), /flex-wrap: nowrap/);
  assert.match(rule(css, ".hdr"), /display: flex/);
  assert.match(rule(css, ".hdr"), /flex-direction: column/);
  assert.match(rule(css, ".who"), /width: 100%/);
  assert.match(rule(css, ".pills"), /display: flex/);
  assert.match(rule(css, ".pills"), /flex-wrap: wrap/);
  assert.match(rule(css, ".pills"), /width: 100%/);
  assert.match(rule(css, ".pill"), /flex: 0 0 auto/);
  assert.match(rule(css, ".pill"), /max-width: 100%/);
  assert.ok(!/text-overflow|overflow: hidden/.test(rule(css, ".pill")), "pill must not clip");
  assert.ok(!/text-overflow\s*:\s*ellipsis/.test(css), "no ellipsis anywhere");
  assert.match(rule(css, ".twn-rtl .pill"), /margin: 0 0 4px 6px/);
});

test("offline banner: the sentence is one block, then reel doctor as a chip on its own row (EN and AR)", () => {
  const s = sampleState("ar", "idle");
  s.connection.engine = "offline";
  for (const [lang, t] of [["ar", AR], ["en", EN]] as const) {
    s.language = lang;
    const html = render(s, t, initialUi());
    assert.ok(html.includes('<div class="cmd-row"><span class="cmd"><bdi dir="ltr">reel doctor</bdi></span></div>'), lang);
    const line = /<div class="banner-line">([\s\S]*?)<\/div>/.exec(html)![1]!;
    assert.ok(!line.includes("reel doctor") && !line.includes("cmd"), "the sentence holds no chip");
    assert.ok(line.trimEnd().endsWith(":"), `${lang}: the sentence leads into the command`);
  }
  const css = panelCss();
  assert.match(rule(css, ".cmd"), /white-space: nowrap/);
  assert.match(rule(css, ".cmd"), /font-family: Consolas/);
});

test("a notice's how ending in a command: sentence block + chip row; a command mid-sentence stays a plain ltr run", () => {
  const s = sampleState("en", "idle");
  const ui = initialUi();
  ui.notice = { kind: "error", text: "Failed.", how: "In your Claude session run `reel doctor`." };
  let html = render(s, EN, ui);
  assert.ok(html.includes('<div class="banner-line">Failed. In your Claude session run:</div><div class="cmd-row"><span class="cmd"><bdi dir="ltr">reel doctor</bdi></span></div>'));
  ui.notice = { kind: "error", text: "Failed.", how: "Run `reel setup` now, then retry." };
  html = render(s, EN, ui);
  assert.ok(html.includes('Run <bdi dir="ltr">reel setup</bdi> now, then retry.'));
  assert.ok(!html.includes('class="cmd"'), "no chip inside running text");
});

test("every .cmd chip sits directly in a .cmd-row (a flex container), never in inline text", () => {
  const ui = { ...initialUi(), confirmRebuild: true, logOpen: true };
  ui.notice = { kind: "error", text: "x", how: "run `reel doctor`" };
  let chips = 0;
  for (const lang of ["en", "ar"] as const) {
    for (const scenario of SCENARIOS) {
      const st = sampleState(lang, scenario);
      st.connection.engine = scenario === "idle" ? "offline" : "connected";
      const html = render(st, stringsFor(lang), ui);
      const all = (html.match(/class="cmd"/g) ?? []).length;
      const inRow = (html.match(/<div class="cmd-row"><span class="cmd">/g) ?? []).length;
      assert.equal(inRow, all, `${lang}/${scenario}: a chip outside a cmd-row`);
      chips += all;
    }
  }
  assert.ok(chips >= 6);
  const css = panelCss();
  const row = rule(css, ".cmd-row");
  assert.match(row, /display: flex/);
  assert.match(row, /flex-direction: row/);
  assert.match(row, /flex-wrap: wrap/);
  assert.match(rule(css, ".banner-text"), /display: flex/);
  assert.match(rule(css, ".banner-text"), /flex-direction: column/);
});

test("CSS: bdi is inline inside the panel; rows with bdi children are explicit flex rows", () => {
  const css = panelCss();
  assert.match(rule(css, ".twn-panel bdi"), /display: inline(?!-)/);
  for (const sel of [".who", ".now-meta", ".log-line"]) {
    const r = rule(css, sel);
    assert.match(r, /display: flex/, sel);
    assert.match(r, /flex-direction: row/, sel);
    assert.match(r, /align-items: baseline/, sel);
  }
  for (const sel of [".who", ".now-meta"]) assert.match(rule(css, sel), /flex-wrap: wrap/, sel);
  assert.match(rule(css, ".cmd"), /display: flex/, "a flex item of .cmd-row");
  assert.match(rule(css, ".cmd"), /max-width: 100%/);
  assert.match(rule(css, ".sep"), /margin: 0 3px/, "symmetric, so it is right in RTL too");
});

test("markup: client/item, progress/elapsed and log rows put their parts in separate elements", () => {
  const s = sampleState("en", "building");
  s.log = [{ ts: "10:00:00", level: "info", text: "reel plan --root X" }];
  const html = render(s, EN, { ...initialUi(), logOpen: true });
  assert.match(html, /<div class="who"><bdi>PODCAST-TEST<\/bdi> <span class="sep">\u00b7<\/span> <bdi dir="ltr">EP01_R03<\/bdi><\/div>/);
  assert.match(html, /<div class="now-meta"><span class="meta-item">[^]*?<\/span><span class="sep">\u00b7<\/span><span class="meta-item">[^]*?<\/span><\/div>/);
  assert.match(html, /<li class="log-line log-info"><span class="log-ts">10:00:00<\/span><bdi dir="ltr">reel plan --root X<\/bdi><\/li>/);
  const ar = render(sampleState("ar", "building"), AR, initialUi());
  assert.match(ar, /<span class="meta-item">[^<]*<bdi dir="ltr">31<\/bdi>[^<]*<bdi dir="ltr">47<\/bdi><\/span>/);
});

// ---- final review: how wording, thumbnails, the host-only button ----

test("U3: a notice's how puts every backticked command in a left-to-right run, in EN and AR; the backticks are not shown", () => {
  for (const [lang, t, how] of [
    ["en", EN, "In your Claude session run `reel doctor`."],
    ["ar", AR, "في جلسة Claude الخاصة بك، شغّل `reel doctor`."],
  ] as const) {
    const s = sampleState(lang, "idle");
    const ui = initialUi();
    ui.notice = { kind: "error", text: "x", how };
    const html = render(s, t, ui);
    assert.ok(html.includes('<bdi dir="ltr">reel doctor</bdi>'), lang);
    assert.ok(!html.includes("`"), `${lang}: the backticks are markup, not text`);
  }
  const s = sampleState("en", "idle");
  const ui = initialUi();
  ui.notice = { kind: "error", text: "x", how: `run \`<img src=x onerror=1>\` now` };
  assert.ok(!render(s, EN, ui).includes("<img src=x"), "the command is escaped too");
  ui.notice = { kind: "error", text: "x", how: "no command here, a stray ` backtick" };
  assert.ok(render(s, EN, ui).includes("no command here, a stray ` backtick"));
});

test("U5: a thumbnail is only drawn for data:image, file:, plugin: and relative URLs, never http(s):", () => {
  const draw = (thumb: string | null) => {
    const s = sampleState("en", "qc");
    s.qc = [{ ...s.qc[0]!, thumb }];
    return render(s, EN, initialUi());
  };
  for (const ok of ["data:image/png;base64,AAAA", "file:///C:/x/f.png", "plugin:/frames/a.png", "frames/a.png", "./a.png"]) {
    assert.ok(draw(ok).includes('class="qc-img"'), ok);
  }
  for (const bad of ["http://evil.example/a.png", "https://evil.example/a.png", "HTTPS://evil.example/a.png", "//evil.example/a.png",
    "javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://x/a.png", " https://evil.example/a.png"]) {
    assert.ok(!draw(bad).includes('class="qc-img"'), bad);
  }
});

test("the panel offers 'Reveal folder' and 'Copy diagnostics' (the permissions are granted again); the folder button is host-only, so it works while the engine is offline", () => {
  assert.equal(EN["actions.reveal"], "Reveal folder");
  assert.equal(EN["actions.diagnostics"], "Copy diagnostics");
  assert.equal(AR["actions.reveal"], "إظهار المجلد");
  assert.equal(AR["actions.diagnostics"], "نسخ التشخيص");
  const s = sampleState("en", "qc");
  s.connection.engine = "offline";
  assert.ok(s.context.folder);
  const html = render(s, EN, initialUi());
  assert.ok(/data-action="reveal"(?! disabled)/.test(html), "reveal stays enabled offline");
  assert.ok(/data-action="open-project" disabled/.test(html), "engine actions are disabled offline");
  const none = sampleState("en", "qc");
  none.context.folder = null;
  assert.ok(/data-action="reveal" disabled/.test(render(none, EN, initialUi())), "no folder, nothing to show");
});

// ---- scrolling in UXP: explicit height chain, one inner scroll region, no reliance on the document scrolling ----

test("CSS: html/body fixed to the viewport, panel root is a full-height flex column, ONE inner scroll region with min-height 0", () => {
  const css = panelCss();
  const hb = rule(css, "html, body");
  assert.match(hb, /height: 100%/);
  assert.match(hb, /margin: 0/);
  assert.match(hb, /overflow: hidden/);
  const root = rule(css, ".twn-panel");
  assert.match(root, /height: 100%/);
  assert.match(root, /display: flex/);
  assert.match(root, /flex-direction: column/);
  assert.match(root, /overflow: hidden/);
  assert.ok(!/min-height: 100%/.test(root), "min-height:100% lets the root grow with its content, so nothing scrolls");
  const sc = rule(css, ".twn-scroll");
  assert.match(sc, /flex: 1 1 auto/);
  assert.match(sc, /min-height: 0/);
  assert.match(sc, /overflow-y: auto/);
  assert.match(rule(css, ".twn-scroll > *"), /flex: 0 0 auto/);
});

test("markup: header, body and footer all sit inside the single .twn-scroll region (footer reachable by scrolling)", () => {
  for (const lang of ["en", "ar"] as const) {
    const html = render(sampleState(lang, "showcase"), stringsFor(lang), initialUi());
    assert.equal((html.match(/class="twn-scroll"/g) ?? []).length, 1);
    const inner = /<div class="twn-scroll">([\s\S]*)<\/div><\/div>$/.exec(html)![1]!;
    assert.ok(inner.startsWith("<header") && inner.includes("<main") && inner.endsWith("</footer>"));
  }
});

// ---- owner decision 2026-10-12: footer "Powered by thewhynot.ai" ----

test('footer: plain text "Powered by thewhynot.ai", domain isolated LTR, identical in EN and AR, no link, never "Claude Code"', () => {
  for (const lang of ["en", "ar"] as const) {
    const html = render(sampleState(lang, "showcase"), stringsFor(lang), initialUi());
    const foot = /<footer class="foot">([\s\S]*?)<\/footer>/.exec(html)![1]!;
    assert.equal(foot, '<bdi dir="ltr">Powered by thewhynot.ai</bdi>', lang);
    assert.ok(!/<a[\s>]/.test(foot) && !/href/.test(foot));
    assert.ok(!html.includes("Powered by Claude"), "the old footer is gone");
  }
});

// ---- UXP drops whitespace between inline children: the log summary is an explicit flex row ----

test("log summary: caret, title and count are separate flex items inside .log-row, separated by margins", () => {
  const s = sampleState("en", "showcase");
  for (const open of [false, true]) {
    const html = render(s, EN, { ...initialUi(), logOpen: open });
    assert.match(html, /<button class="log-toggle"[^>]*><span class="log-row"><span class="caret">[^<]+<\/span><span class="log-title">Log<\/span><span class="log-count">4 lines<\/span><\/span><\/button>/);
  }
  const css = panelCss();
  const row = rule(css, ".log-row");
  assert.match(row, /display: flex/);
  assert.match(row, /flex-direction: row/);
  assert.match(row, /align-items: baseline/);
  for (const sel of [".caret", ".log-title", ".log-count"]) {
    assert.match(rule(css, sel), /margin: 0 [1-9]/, `${sel} needs a horizontal margin (no whitespace survives in UXP)`);
  }
});

// ------------------------------------------------------------------------------------- Task 4: the link diagnosis
const LINK_CASES: Array<[string, string, string]> = [
  // code, EN title fragment, command
  ["no_engine", "is not running", "reel serve --ensure"],
  ["down", "does not answer", "reel serve --ensure"],
  ["unreachable", "could not reach", "reel serve --ensure"],
  ["bad_engine_json", "is incomplete or damaged", "reel serve --ensure"],
  ["auth", "key", "reel serve --ensure"],
  ["no_welcome", "did not answer", "reel serve --ensure"],
  ["lost", "was lost", "reel serve --ensure"],
  ["refused_host", "Host / Origin", "reel doctor"],
  ["refused_busy", "too many connections", "reel doctor"],
  ["refused", "refused", "reel doctor"],
  ["protocol", "different version", "reel doctor"],
  ["too_large", "too large", "reel doctor"],
  ["blocked", "could not reach the engine on its port", "reel serve --status"],
];

test("offline banner names the link diagnosis (EN and AR): its own sentence, its command as a chip, 'tries again by itself'", () => {
  const s = sampleState("en", "idle");
  s.connection.engine = "offline";
  for (const [code, fragment, cmd] of LINK_CASES) {
    for (const [lang, t] of [["en", EN], ["ar", AR]] as const) {
      s.language = lang;
      const ui = { ...initialUi(), link: { code, retry_in_s: 4 } };
      const html = render(s, t, ui);
      const banner = /<div class="banner banner-error" role="alert" data-link="([a-z_]+)">([\s\S]*?)<\/div><\/div>/.exec(html);
      assert.ok(banner, `${code} ${lang}: no link banner`);
      assert.equal(banner![1], code);
      const key = `offline.${code}` as keyof typeof EN;
      assert.ok(t[key], `${lang}: no string for ${key}`);
      assert.ok(html.includes(`<div class="cmd-row"><span class="cmd"><bdi dir="ltr">${cmd}</bdi></span></div>`), `${code} ${lang}: command chip`);
      assert.ok(html.includes(esc(t["offline.retry"])), `${code} ${lang}: retry line`);
      if (lang === "en") assert.ok(html.includes(fragment), `${code}: ${fragment}`);
      if (lang === "ar") assert.ok(!html.includes(EN[key].replace(/`/g, "")), `${code}: the Arabic banner is not English`);
    }
  }
});

test("link banner: engine.json stays a left-to-right run inside the Arabic sentence; connecting shows no command", () => {
  const s = sampleState("ar", "idle");
  s.connection.engine = "offline";
  const html = render(s, AR, { ...initialUi(), link: { code: "bad_engine_json", retry_in_s: 1 } });
  assert.ok(html.includes('<bdi dir="ltr">engine.json</bdi>'));
  for (const code of ["connecting", "idle"]) {
    const h = render(s, AR, { ...initialUi(), link: { code } });
    assert.ok(h.includes(esc(AR["status.connecting"])), code);
    assert.ok(!h.includes("cmd-row"), `${code}: no command while connecting`);
    assert.ok(!h.includes(esc(AR["offline.retry"])), code);
  }
});

test("link banner: an unknown code falls back to the generic offline banner; a connected engine shows no offline banner", () => {
  const s = sampleState("en", "idle");
  s.connection.engine = "offline";
  const h = render(s, EN, { ...initialUi(), link: { code: "something_new" } });
  assert.ok(h.includes(esc(EN["offline.title"])));
  assert.ok(h.includes('<bdi dir="ltr">reel doctor</bdi>'));
  s.connection.engine = "connected";
  const on = render(s, EN, { ...initialUi(), link: { code: "lost", retry_in_s: 2 } });
  assert.ok(!on.includes("data-link="));
  assert.ok(!on.includes(esc(EN["offline.lost"])));
});

test("M8: the open log drawer shows the plugin version and build stamp as one left-to-right run; closed, it is not rendered", () => {
  const s = sampleState("ar", "idle");
  const build = { version: "3.0.0", build: "61b12aa 2026-10-12T18:40Z" };
  const open = render(s, AR, { ...initialUi(), logOpen: true, build });
  assert.ok(open.includes('<p class="muted hint log-build"><bdi dir="ltr">WhyNot Cut 3.0.0 · build 61b12aa 2026-10-12T18:40Z</bdi></p>'), open.slice(-600));
  const closed = render(s, AR, { ...initialUi(), logOpen: false, build });
  assert.ok(!closed.includes("log-build"));
  assert.ok(!render(s, AR, { ...initialUi(), logOpen: true }).includes("log-build"));
});
