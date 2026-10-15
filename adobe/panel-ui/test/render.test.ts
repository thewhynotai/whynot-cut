import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { esc, initialUi, render, renderError } from "../src/render.ts";
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

test('paths, file names and timecodes sit inside <bdi dir="ltr">', () => {
  const s = sampleState("ar", "showcase");
  s.connection.engine = "offline";
  const html = render(s, AR, { ...initialUi(), logOpen: true, confirmRebuild: true });
  const inBdi = (txt: string) => assert.ok(html.includes(`<bdi dir="ltr">${esc(txt)}</bdi>`), `not isolated: ${txt}`);
  inBdi(s.context.project_path as string);
  inBdi(s.approval!.flagged[0]!.tc);
  inBdi(s.qc[0]!.tc);
  inBdi(AR["rebuild.backup_name"]); // also wrapped in a .cmd chip (own test below)
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

function runningBuild(phase: string | null | undefined, elapsed: number | null, detail = "Premiere Pro 26.5.2"): PanelState {
  const s = sampleState("en", "idle");
  s.connection.host.detail = detail;
  s.pipeline = s.pipeline.map((p) =>
    p.id === "build" ? { ...p, state: "running", progress: null, phase: phase as never, elapsed_s: elapsed, request_id: "req-1" } : { ...p, state: "done" },
  );
  return s;
}

test("H2: a running step with a phase shows the phase and the elapsed time, never a bare 'running'", () => {
  for (const [lang, t] of [["en", EN], ["ar", AR]] as const) {
    const bare = render({ ...runningBuild(null, null), language: lang }, t, initialUi());
    assert.ok(!bare.includes('class="now-phase"'), `${lang}: no phase yet, no phase line`);
    const queued = render({ ...runningBuild("queued", 0), language: lang }, t, initialUi());
    assert.ok(queued.includes(`<div class="now-phase">${t["pipeline.phase.queued"].replace("{app}", '<bdi dir="ltr">Premiere Pro</bdi>')}</div>`), `${lang}: queued`);
    assert.ok(queued.includes(`${esc(t["pipeline.elapsed"])} <bdi dir="ltr">0:00</bdi>`), `${lang}: elapsed from the first event`);
    const claimed = render({ ...runningBuild("claimed", 14), language: lang }, t, initialUi());
    assert.ok(claimed.includes(`<div class="now-phase">${t["pipeline.phase.claimed"].replace("{app}", '<bdi dir="ltr">Premiere Pro</bdi>')}</div>`), `${lang}: claimed`);
    assert.ok(claimed.includes('<bdi dir="ltr">0:14</bdi>'), `${lang}: elapsed 14 s`);
    assert.ok(claimed.includes('data-action="cancel"'), `${lang}: Cancel stays`);
    const working = render({ ...runningBuild("elapsed", 65), language: lang }, t, initialUi());
    assert.ok(working.includes(t["pipeline.phase.elapsed"].replace("{app}", '<bdi dir="ltr">Premiere Pro</bdi>')) && working.includes("1:05"), `${lang}: elapsed`);
    assert.ok(!working.includes("{app}"), `${lang}: no placeholder is left`);
  }
});

test("H2: the phase line names the app from the host detail (After Effects, else Premiere Pro, else a plain word) and a real n/of keeps the bar and drops the phase line", () => {
  const ae = render(runningBuild("queued", 0, "After Effects 26.5"), EN, initialUi());
  assert.ok(ae.includes('<bdi dir="ltr">After Effects</bdi>'));
  const other = render(runningBuild("queued", 0, "<img src=x onerror=1>"), EN, initialUi());
  assert.ok(other.includes(esc(EN["pipeline.app.generic"])) && !other.includes("<img src=x"));
  const none = runningBuild("queued", 0);
  delete none.connection.host.detail;
  assert.ok(render(none, EN, initialUi()).includes(esc(EN["pipeline.app.generic"])));
  const counted = runningBuild("running", 5);
  counted.pipeline = counted.pipeline.map((p) => (p.id === "build" ? { ...p, progress: { n: 3, of: 10, step: "graphics placed" } } : p));
  const h = render(counted, EN, initialUi());
  assert.match(h, /class="progress-fill" style="width:30%"/);
  assert.ok(!h.includes('class="now-phase"'), "a counted step shows its bar, not a phase");
});

test("H2 review: the phase line names the host of the running command (the step's host), not the panel's app", () => {
  const s = runningBuild("queued", 0, "Premiere Pro 26.5.2");
  s.pipeline = s.pipeline.map((p) => (p.id === "build" ? { ...p, host: "aftereffects" } : p));
  const ae = render(s, EN, initialUi());
  assert.ok(ae.includes('<bdi dir="ltr">After Effects</bdi>') && !ae.includes("Premiere Pro</bdi>"), "an After Effects job in a Premiere panel");
  s.pipeline = s.pipeline.map((p) => (p.id === "build" ? { ...p, host: "premiere" } : p));
  s.connection.host.detail = "After Effects 26.5";
  const pr = render(s, EN, initialUi());
  assert.ok(pr.includes('<bdi dir="ltr">Premiere Pro</bdi>') && !pr.includes("After Effects</bdi>"), "a Premiere job in an AE panel");
  s.pipeline = s.pipeline.map((p) => (p.id === "build" ? { ...p, host: "photoshop" as never } : p));
  assert.ok(render(s, EN, initialUi()).includes('<bdi dir="ltr">After Effects</bdi>'), "an unknown host falls back to the panel's app");
});

test("H2: a phase outside the contract renders no phase line (the value never reaches a key or the markup)", () => {
  for (const bad of ["busy", `queued" onmouseover="x`, "__proto__", "constructor", EVIL]) {
    const h = render(runningBuild(bad, 3), EN, initialUi());
    assert.ok(!h.includes('class="now-phase"'), bad);
    assert.ok(!h.includes("onmouseover") && !h.includes("<script>"), bad);
  }
});

test("pills: Engine / Claude / Host, with state classes", () => {
  const html = render(sampleState("en", "showcase"), EN, initialUi());
  for (const k of ["engine", "claude", "host"]) assert.ok(html.includes(`data-pill="${k}"`));
  const off = sampleState("en", "idle");
  off.connection.engine = "offline";
  assert.ok(render(off, EN, initialUi()).includes('class="pill pill-offline" data-pill="engine"'));
});

test("flexbox only: the shipped CSS has no grid, gap, sticky or :has(); @font-face lives only in fonts.css", () => {
  for (const f of ["../../../brand/tokens.css", "../styles/panel.css", "../styles/fonts.css"]) {
    const css = readFileSync(new URL(f, import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    assert.ok(!/display\s*:\s*(inline-)?grid|grid-template|(?:^|[;{\s])(?:row-|column-)?gap\s*:|position\s*:\s*sticky|:has\(/.test(css), f);
    if (!f.endsWith("fonts.css")) assert.ok(!/@font-face/.test(css), `${f}: @font-face belongs in fonts.css`);
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

test("offline banner (no diagnosis): one plain sentence and ONE fix button, Start engine; no command, no chip (EN and AR)", () => {
  const s = sampleState("ar", "idle");
  s.connection.engine = "offline";
  for (const [lang, t] of [["ar", AR], ["en", EN]] as const) {
    s.language = lang;
    const html = render(s, t, initialUi());
    const banner = /<div class="banner banner-error" role="alert">([\s\S]*?)<\/button><\/div><\/div><\/div>/.exec(html)![1]!;
    assert.ok(banner.includes(`<div class="banner-line"><strong>${esc(t["offline.title"])}</strong></div>`), lang);
    assert.ok(banner.includes(`<div class="btn-row banner-fix"><button class="btn btn-secondary" data-action="start-engine">${esc(t["action.start_engine"])}`), lang);
    assert.equal((banner.match(/<button/g) ?? []).length, 1, `${lang}: one fix button`);
    assert.ok(!banner.includes("cmd") && !banner.includes("reel"), `${lang}: no command`);
  }
  const css = panelCss();
  assert.match(rule(css, ".cmd"), /white-space: nowrap/);
  assert.match(rule(css, ".cmd"), /font-family: var\(--twn-font-mono\)/);
  assert.match(rule(css, ".banner-fix"), /margin-top: 6px/);
  assert.match(rule(css, ".btn-row"), /display: flex/);
});

test("an error notice: its sentence and ONE fix button (default Copy diagnostics); a how that holds a command is not shown at all", () => {
  const s = sampleState("en", "idle");
  const ui = initialUi();
  ui.notice = { kind: "error", text: "Failed.", how: "In your Claude session run `reel doctor`." };
  let html = render(s, EN, ui);
  // round 2: no sentence surgery. The how is held back whole (mount put it in the log); the Copy diagnostics fix then
  // says what to do with the copy
  assert.ok(html.includes(`<div class="banner-line">Failed.</div><div class="banner-line">${esc(EN["notice.send_diagnostics"])}</div><div class="btn-row banner-fix"><button class="btn btn-secondary" data-action="copy-diagnostics">Copy diagnostics</button></div>`), html);
  assert.ok(!html.includes("reel doctor") && !html.includes('class="cmd"'));
  for (const fix of ["start-engine", "retry", "copy-diagnostics"] as const) {
    ui.notice = { kind: "error", text: "Failed.", how: "Wait and retry.", fix };
    html = render(s, EN, ui);
    const banner = /<div class="banner banner-error" role="status"[\s\S]*?data-action="dismiss-notice"/.exec(html)![0];
    assert.ok(banner.includes('<div class="banner-line">Failed. Wait and retry.</div>'), fix);
    assert.deepEqual([...banner.matchAll(/data-action="([^"]+)"/g)].map((m) => m[1]), [fix, "dismiss-notice"], fix);
  }
  // an unknown fix falls back to Copy diagnostics; an ok notice has no fix button; a text that is a command is replaced
  ui.notice = { kind: "error", text: "x", fix: "bogus" as never };
  assert.ok(render(s, EN, ui).includes('data-action="copy-diagnostics">'));
  ui.notice = { kind: "ok", text: "Done." };
  assert.ok(!/banner-fix/.test(render(s, EN, ui)));
  ui.notice = { kind: "error", text: "Run reel serve --ensure" };
  html = render(s, EN, ui);
  assert.ok(html.includes(`<div class="banner-line">${esc(EN["notice.failed"])}</div>`) && !html.includes("reel serve"));
  // Copy diagnostics with no how: the notice says what to do with the copy
  assert.ok(html.includes(`<div class="banner-line">${esc(EN["notice.send_diagnostics"])}</div><div class="btn-row banner-fix"><button class="btn btn-secondary" data-action="copy-diagnostics">`), html);
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

test("U3: a notice's how keeps every backticked file name a left-to-right run (the backticks are markup), in EN and AR; a backticked command is not shown", () => {
  for (const [lang, t, how] of [
    ["en", EN, "Check `engine.json` and `assets`."],
    ["ar", AR, "افحص `engine.json` و`assets`."],
  ] as const) {
    const s = sampleState(lang, "idle");
    const ui = initialUi();
    ui.notice = { kind: "error", text: "x", how };
    const html = render(s, t, ui);
    assert.ok(html.includes('<bdi dir="ltr">engine.json</bdi>') && html.includes('<bdi dir="ltr">assets</bdi>'), lang);
    assert.ok(!html.includes("`"), `${lang}: the backticks are markup, not text`);
    ui.notice = { kind: "error", text: "x", how: "Run `reel setup` now, then retry." };
    assert.ok(!render(s, t, ui).includes("reel setup"), `${lang}: a command is not shown`);
  }
  const s = sampleState("en", "idle");
  const ui = initialUi();
  ui.notice = { kind: "error", text: "x", how: "open `<img src=x onerror=1>` now" };
  assert.ok(!render(s, EN, ui).includes("<img src=x"), "the run is escaped too");
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
const LINK_CASES: Array<[string, string, "start-engine" | "copy-diagnostics"]> = [
  // code, EN title fragment, its one fix button (C2.2: the command that fixes it is only in diagnostics and the log)
  ["no_engine", "is not running", "start-engine"],
  ["down", "does not answer", "start-engine"],
  ["unreachable", "could not reach", "start-engine"],
  ["bad_engine_json", "is incomplete or damaged", "start-engine"],
  ["auth", "key", "start-engine"],
  ["no_welcome", "did not answer", "start-engine"],
  ["lost", "was lost", "start-engine"],
  ["refused_host", "does not recognise", "copy-diagnostics"],
  ["refused_busy", "too many connections", "copy-diagnostics"],
  ["refused", "refused", "copy-diagnostics"],
  ["protocol", "different version", "copy-diagnostics"],
  ["too_large", "too large", "copy-diagnostics"],
  ["blocked", "the connection was blocked", "copy-diagnostics"],
];

test("offline banner names the link diagnosis (EN and AR): its own plain sentence, ONE fix button, 'tries again by itself'; no command", () => {
  const s = sampleState("en", "idle");
  s.connection.engine = "offline";
  for (const [code, fragment, fix] of LINK_CASES) {
    for (const [lang, t] of [["en", EN], ["ar", AR]] as const) {
      s.language = lang;
      const ui = { ...initialUi(), link: { code, retry_in_s: 4 } };
      const html = render(s, t, ui);
      const banner = /<div class="banner banner-error" role="alert" data-link="([a-z_]+)">([\s\S]*?)<\/button><\/div><\/div><\/div>/.exec(html);
      assert.ok(banner, `${code} ${lang}: no link banner`);
      assert.equal(banner![1], code);
      const key = `offline.${code}` as keyof typeof EN;
      assert.ok(t[key], `${lang}: no string for ${key}`);
      const label = fix === "start-engine" ? t["action.start_engine"] : t["actions.diagnostics"];
      assert.ok(banner![2]!.includes(`<button class="btn btn-secondary" data-action="${fix}">${esc(label)}`), `${code} ${lang}: fix button`);
      assert.equal((banner![2]!.match(/<button/g) ?? []).length, 1, `${code} ${lang}: one fix button`);
      assert.ok(!/reel|cmd-row|`/.test(banner![0]), `${code} ${lang}: no command`);
      assert.ok(html.includes(esc(t["offline.retry"])), `${code} ${lang}: retry line`);
      if (lang === "en") assert.ok(html.includes(esc(fragment)), `${code}: ${fragment}`);
      if (lang === "ar") assert.ok(!html.includes(esc(EN[key])), `${code}: the Arabic banner is not English`);
    }
  }
});

test("link banner: the sentences are plain (no file names, no Host / Origin jargon); connecting shows no fix button; stopped offers Start engine; neither has a retry line", () => {
  for (const [code] of LINK_CASES) {
    for (const t of [EN, AR]) assert.doesNotMatch(t[`offline.${code}` as keyof typeof EN], /engine\.json|Origin|`/, code);
  }
  const s = sampleState("ar", "idle");
  s.connection.engine = "offline";
  for (const code of ["connecting", "idle", "stopped"]) {
    const h = render(s, AR, { ...initialUi(), link: { code } });
    assert.ok(h.includes(esc(AR[code === "stopped" ? "offline.stopped" : "status.connecting"])), code);
    if (code === "stopped") {
      // the panel stopped its link: Start engine brings it back (C2.2 review round 1)
      const fixes = [...h.matchAll(/class="btn-row banner-fix"><button class="btn btn-secondary" data-action="([^"]+)"/g)].map((m) => m[1]);
      assert.deepEqual(fixes, ["start-engine"], code);
    } else assert.ok(!h.includes("banner-fix"), `${code}: nothing to fix while connecting`);
    assert.ok(!h.includes(esc(AR["offline.retry"])), code);
  }
});

test("link banner: an unknown code falls back to the generic offline banner (Start engine); a connected engine shows no offline banner", () => {
  const s = sampleState("en", "idle");
  s.connection.engine = "offline";
  const h = render(s, EN, { ...initialUi(), link: { code: "something_new" } });
  assert.ok(h.includes(esc(EN["offline.title"])));
  assert.ok(h.includes('data-action="start-engine"'));
  assert.ok(!h.includes("reel "));
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

// ---------------------------------------------------------------------------------- C2.2 review round 1

test("C2.2 r1: a Copy diagnostics fix says what to do with the copy (link banners and notices without a how), EN and AR", () => {
  const s = sampleState("en", "idle");
  s.connection.engine = "offline";
  for (const t of [EN, AR]) {
    for (const code of ["refused_host", "refused_busy", "refused", "protocol", "too_large", "blocked"]) {
      const h = render(s, t, { ...initialUi(), link: { code } });
      assert.ok(h.includes(`<div class="banner-line">${esc(t["notice.send_diagnostics"])}</div><div class="btn-row banner-fix"><button class="btn btn-secondary" data-action="copy-diagnostics">`), code);
    }
    // Start engine needs no such line
    assert.ok(!render(s, t, { ...initialUi(), link: { code: "no_engine" } }).includes(esc(t["notice.send_diagnostics"])));
  }
});

test("C2.2 r1: one Start engine on a screen: the offline banner carries it, a notice whose fix is the same does not repeat it; another fix still shows", () => {
  const s = sampleState("en", "approval");
  s.connection.engine = "offline";
  for (const link of [null, { code: "no_engine", retry_in_s: 2 }, { code: "stopped" }]) {
    const h = render(s, EN, { ...initialUi(), link, notice: { kind: "error", text: "The WhyNot Cut engine is not connected.", fix: "start-engine" } });
    assert.equal((h.match(/data-action="start-engine"/g) ?? []).length, 1, JSON.stringify(link));
  }
  const h = render(s, EN, { ...initialUi(), notice: { kind: "error", text: "Premiere is busy.", fix: "retry" } });
  assert.equal((h.match(/data-action="retry"/g) ?? []).length, 1);
  assert.equal((h.match(/data-action="start-engine"/g) ?? []).length, 1);
});


// ---- C2.2 review round 2: no sentence surgery. An engine or host text that holds a command is not shown at all: the
// panel's own localized sentence takes its place (mount puts the raw text in the log); "Claude Code" reads "Claude".

const noticeLine = (h: string) => /<div class="banner banner-(?:error|ok|info)" role="status"[\s\S]*?<div class="banner-line">([\s\S]*?)<\/div>/.exec(h)?.[1] ?? "";

test("C2.2 r2: a notice whose text holds a command shows the localized sentence for its code (generic when there is none); the fix button stays", () => {
  for (const [lang, t] of [["en", EN], ["ar", AR]] as const) {
    const s = sampleState(lang, "idle");
    const cases: Array<[string | undefined, string]> = [
      ["no_route", t["notice.code.no_route"]],
      ["timeout", t["notice.code.timeout"]],
      ["NOT_YET", t["notice.code.not_yet"]],
      ["no_engine", t["offline.no_engine"]],
      ["lost", t["offline.lost"]],
      ["something_new", t["notice.failed"]],
      ["../../evil", t["notice.failed"]],
      [undefined, t["notice.failed"]],
    ];
    for (const [code, want] of cases) {
      const h = render(s, t, { ...initialUi(), notice: { kind: "error", text: "Premiere is not responding. Run reel doctor and press Try again.", ...(code ? { code } : {}), fix: "retry" } });
      assert.equal(noticeLine(h), esc(want), `${lang}/${code}`);
      assert.ok(!h.includes("reel doctor") && !h.includes(". and press"), `${lang}/${code}: never a cut-up sentence`);
      assert.match(h, /data-action="retry"/, `${lang}/${code}: the fix button stays`);
    }
  }
});

test("C2.2 r2: a normal engine sentence is shown whole; 'Claude Code' becomes 'Claude' in place, in the text and the how", () => {
  const s = sampleState("en", "idle");
  for (const text of ["The reel plan is ready", "reel build failed", "Python 3.9 is required", "Claude login expired"]) {
    assert.equal(noticeLine(render(s, EN, { ...initialUi(), notice: { kind: "error", text } })), esc(text), text);
  }
  const h = render(s, EN, { ...initialUi(), notice: { kind: "error", text: "Open Claude Code.", how: "Open Claude Code, then press Try again.", fix: "retry" } });
  assert.equal(noticeLine(h), "Open Claude. Open Claude, then press Try again.");
  // a how that holds a command is not shown; the text stays
  const h2 = render(s, EN, { ...initialUi(), notice: { kind: "error", text: "Premiere is busy.", how: "Open your Claude session, run reel serve --ensure.", fix: "retry" } });
  assert.equal(noticeLine(h2), "Premiere is busy.");
  assert.ok(!h2.includes("reel serve") && !h2.includes("session,."));
});

test("C2.2 r2: every engine or host text that reaches the screen gets the same handling: step, summary, flagged text, QC label, host detail, renderError", () => {
  const CMD = "Run reel previews --video-id C0239 now";
  for (const [lang, t] of [["en", EN], ["ar", AR]] as const) {
    const s = sampleState(lang, "showcase");
    s.pipeline = s.pipeline.map((p) => (p.id === "build" ? { ...p, progress: { n: 1, of: 4, step: CMD } } : p));
    s.approval!.summary = CMD;
    s.approval!.flagged[0]!.text = CMD;
    s.qc[0]!.label = CMD;
    s.connection.host.detail = "Premiere Pro (claude -p)";
    const h = render(s, t, initialUi());
    assert.ok(!h.includes("reel previews") && !h.includes("claude -p"), lang);
    assert.ok(h.includes(`<p class="summary"><bdi>${esc(t["text.held"])}</bdi></p>`), `${lang}: summary`);
    assert.ok(h.includes(`<div class="qc-label"><bdi>${esc(t["text.held"])}</bdi></div>`), `${lang}: label`);
    assert.ok(!h.includes('class="now-step"'), `${lang}: the step line is left out`);
    assert.ok(h.includes(`<span class="pill-v">${esc(t["pill.host.uxp"])}</span>`), `${lang}: host pill falls back to its own words`);
    // normal texts are shown whole
    const ok = sampleState(lang, "showcase");
    ok.approval!.summary = "The reel plan is ready";
    ok.connection.host.detail = "Premiere Pro 26.5.2";
    const h2 = render(ok, t, initialUi());
    assert.ok(h2.includes("<bdi>The reel plan is ready</bdi>") && h2.includes("Premiere Pro 26.5.2") && h2.includes("graphics placed"), lang);
  }
  const e = renderError(EN, false, EN["error.render"], "Cannot read x: run `reel doctor`");
  assert.ok(!e.includes("reel doctor") && e.includes(esc(EN["error.render"])));
  assert.ok(renderError(EN, false, EN["error.render"], "Claude Code broke").includes("Claude broke"));
  assert.ok(renderError(EN, false, EN["error.render"], "Cannot read properties of undefined").includes("Cannot read properties of undefined"));
});

test("C2.2 r2: an info notice (the plan changed) has its own colour and no fix button", () => {
  const h = render(sampleState("en", "approval"), EN, { ...initialUi(), notice: { kind: "info", text: EN["notice.plan_changed"] } });
  assert.match(h, /<div class="banner banner-info" role="status"/);
  assert.ok(!/banner-fix/.test(h));
  assert.match(rule(panelCss(), ".banner-info"), /border-color: var\(--twn-warn\)/);
  assert.equal(EN["notice.plan_changed"], "The plan changed. Review it and approve again.");
  assert.match(AR["notice.plan_changed"], /[؀-ۿ]/);
});

test("C2.2 r2: the host pill uses editor words: Premiere / linked / linked (compat), never UXP, CEP or Host (EN and AR)", () => {
  for (const [lang, t] of [["en", EN], ["ar", AR]] as const) {
    for (const k of ["pill.host", "pill.host.uxp", "pill.host.cep", "pill.host.offline"] as const) {
      assert.doesNotMatch(t[k], /\bUXP\b|\bCEP\b|\bHost\b|المضيف/, `${lang} ${k}`);
    }
    assert.match(t["pill.host"], /Premiere/, lang);
    for (const st of ["uxp", "cep", "offline"] as const) {
      const s = sampleState(lang, "showcase");
      s.connection.host = { state: st };
      const h = render(s, t, initialUi());
      const pillHtml = /<span class="pill [^"]*" data-pill="host">[\s\S]*?<\/span><\/span>/.exec(h)![0];
      assert.doesNotMatch(pillHtml, /UXP|CEP|Host/, `${lang}/${st}`);
    }
  }
  assert.equal(EN["pill.host"], "Premiere");
  assert.equal(EN["pill.host.uxp"], "linked");
  assert.equal(EN["pill.host.cep"], "linked (compat)");
});
