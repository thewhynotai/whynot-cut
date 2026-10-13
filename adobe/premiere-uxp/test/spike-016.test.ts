// Spike 0.1.6 (B-T1 Task 3 + Addendum C2.7): the "style_guide" run mode, the style guide view, the live UXP UI probes
// (ui_probes) and the ecosystem probes (eco_probes: openExternal, quit/restart names, loopback network.domains,
// hide/show) - all against hand-made fakes (no Premiere, no daemon, no DOM).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createAutoRunner, DEFAULT_VIEW, type AutoRunDeps, type GuideView, type RunMode, type RunSummary } from "../spike/src/autorun.ts";
import {
  CONSENT_SUSPECT_MS,
  createLifecycle,
  ENGINE_START_URL,
  hideShowProbe,
  LOOPBACK_DOMAINS,
  loopbackProbe,
  openExternalProbe,
  propertyNames,
  quitRestartNamesProbe,
  setupLifecycle,
  type EcoCtx,
} from "../spike/src/eco-probes.ts";
import { runProbe } from "../spike/src/runner.ts";
import { ECO_PROBE_NAMES, runPostSections, runPreSections, sectionCounts, UI_PROBE_NAMES, type Sections } from "../spike/src/sections.ts";
import { createStyleGuide, guideCaption, guideHtml } from "../spike/src/style-guide.ts";
import { FALLBACKS, FONT_SAMPLES, fontId, fontVerdict, UI_PROBES, type StyleLike, type UiCtx, type UiStage } from "../spike/src/ui-probes.ts";
import type { WsCtor, WsLike } from "../spike/src/ws-link.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "..", "..");
const read = (p: string) => readFileSync(join(root, p), "utf8");
const DIR = "C:/Users/LOQ/.whynot-cut/uxp-spike";
const HOME = "C:/Users/LOQ";
const ENGINE_JSON = `${HOME}/.whynot-cut/bridge/engine.json`;
const TOKEN = "e7".repeat(32);
const PORT = 53672;
const T0 = Date.parse("2026-10-13T12:00:00.000Z");
const iso = (ms: number) => new Date(ms).toISOString();

// ---- the run-request: mode "style_guide" -------------------------------------------------------------------------

function memFs(initial: Record<string, string> = {}) {
  const files = new Map<string, string>(Object.entries(initial));
  const fs: Record<string, unknown> = {
    files,
    readFileSync: (p: string) => {
      const v = files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return v;
    },
    writeFileSync: (p: string, data: string) => void files.set(p, data),
    lstatSync: (p: string) => {
      const v = files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return { size: v.length, isDirectory: () => false };
    },
    renameSync: (from: string, to: string) => {
      const v = files.get(from);
      if (v === undefined) throw new Error(`ENOENT: ${from}`);
      files.delete(from);
      files.set(to, v);
    },
    unlinkSync: (p: string) => void files.delete(p),
  };
  return fs as Record<string, unknown> & { files: Map<string, string> };
}

function autorun(request: Record<string, unknown>) {
  const fs = memFs({ [`${DIR}/run-request.json`]: JSON.stringify({ requested_at: iso(T0 - 1000), ...request }) });
  const runs: Array<{ id: string; mode: RunMode; view?: GuideView; args: number }> = [];
  let held = false;
  const summary: RunSummary = { results_file: `${DIR}/results-x.json`, ok: true, pass: 7, fail: 1, na: 1 };
  const deps: AutoRunDeps = {
    fs: fs as AutoRunDeps["fs"],
    dir: DIR,
    now: () => T0,
    isBusy: () => false,
    tryLock: () => (held ? false : (held = true)),
    unlock: () => void (held = false),
    run: async (...args: [RunMode, string, GuideView?]) => {
      runs.push({ mode: args[0], id: args[1], ...(args[2] ? { view: args[2] } : {}), args: args.length });
      return summary;
    },
    setStatus: () => {},
    schedule: () => () => {},
  };
  return { fs, runs, runner: createAutoRunner(deps) };
}

test("run-request mode style_guide: claimed, run with its view (lang / width), the done file names the mode and the view", async () => {
  const h = autorun({ id: "sg-ar-480", mode: "style_guide", lang: "ar", width: 480 });
  const out = await h.runner.poll();
  assert.equal(out.kind, "ran");
  assert.deepEqual(h.runs, [{ id: "sg-ar-480", mode: "style_guide", view: { lang: "ar", width: 480 }, args: 3 }]);
  const done = JSON.parse(h.fs.files.get(`${DIR}/run-done-sg-ar-480.json`)!);
  assert.equal(done.mode, "style_guide");
  assert.deepEqual(done.view, { lang: "ar", width: 480 });
  assert.equal(done.ok, true);
  assert.equal(done.pass, 7);
});

test("style_guide without lang / width opens the default view (EN, 340 px)", async () => {
  const h = autorun({ id: "sg-default", mode: "style_guide" });
  await h.runner.poll();
  assert.deepEqual(h.runs[0]?.view, DEFAULT_VIEW);
  assert.deepEqual(DEFAULT_VIEW, { lang: "en", width: 340 });
});

test("full and keep_open still run with (mode, id) only; their done file names the mode", async () => {
  for (const mode of ["full", "keep_open"] as const) {
    const h = autorun({ id: `m-${mode}`, mode });
    await h.runner.poll();
    assert.deepEqual(h.runs, [{ id: `m-${mode}`, mode, args: 2 }]);
    assert.equal(JSON.parse(h.fs.files.get(`${DIR}/run-done-m-${mode}.json`)!).mode, mode);
  }
});

test("a bad style_guide view (or a view on another mode) is malformed: moved aside with an error file, nothing runs", async () => {
  for (const [i, bad] of [
    { mode: "style_guide", lang: "fr" },
    { mode: "style_guide", width: 300 },
    { mode: "style_guide", width: "340" },
    { mode: "full", lang: "ar" },
    { mode: "keep_open", width: 480 },
    { mode: "guide" },
  ].entries()) {
    const h = autorun({ id: `bad-${i}`, ...bad });
    const out = await h.runner.poll();
    assert.equal(out.kind, "malformed", JSON.stringify(bad));
    assert.equal(h.runs.length, 0);
    assert.ok([...h.fs.files.keys()].some((k) => k.startsWith(`${DIR}/run-error-`)));
  }
});

// ---- manifest, version, page --------------------------------------------------------------------------------------

test("spike 0.1.6 manifest: name kept, version bumped, an explicit loopback network list (= LOOPBACK_DOMAINS), whynotcut scheme; product stays \"all\"", () => {
  const m = JSON.parse(read("spike/manifest.json"));
  const product = JSON.parse(read("plugin/manifest.json"));
  assert.equal(m.name, "WhyNot Cut Spike");
  assert.equal(m.entrypoints[0].label.default, "WhyNot Cut Spike");
  assert.equal(m.version, "0.1.8");
  assert.match(read("spike/src/version.ts"), /SPIKE_VERSION = "0.1.8"/);
  assert.deepEqual(m.requiredPermissions.network.domains, [...LOOPBACK_DOMAINS]);
  // the port-wildcard forms, plus the exact port-less forms (two of which failed in round 1: parity W1/W2)
  for (const d of ["ws://127.0.0.1:*", "ws://localhost:*", "http://127.0.0.1:*", "http://localhost:*", "ws://127.0.0.1", "http://127.0.0.1"]) assert.ok(LOOPBACK_DOMAINS.includes(d), d);
  assert.ok(!LOOPBACK_DOMAINS.includes("all"));
  assert.ok(m.requiredPermissions.launchProcess.schemes.includes("whynotcut"), "openExternal(whynotcut://) needs its scheme");
  assert.equal(product.requiredPermissions.network.domains, "all", "the product manifest stays at \"all\"");
});

test("spike page: links tokens.css, kit.css, index.css; has the style guide view and its toggles; no Claude Code", () => {
  const html = read("spike/index.html");
  // 0.1.7 adds lab.css (the CSS lab) last; 0.1.8 drops fonts.css (UXP loads no @font-face)
  assert.deepEqual([...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map((m) => m[1]), ["tokens.css", "kit.css", "index.css", "lab.css"]);
  for (const id of ["main-view", "guide-view", "guide-frame", "guide-host", "guide-caption", "guide-open", "guide-back", "guide-en", "guide-ar", "guide-w280", "guide-w340", "guide-w480", "run", "run-keep", "copy", "status", "out", "lab-open", "lab-view", "lab-host", "lab-caption", "lab-back"]) {
    assert.match(html, new RegExp(`id="${id}"`), id);
  }
  assert.doesNotMatch(html, /Claude Code/);
  assert.match(html, /Powered by thewhynot\.ai/);
});

test("spike index.css: the drift block is gone (no --twn-* definitions), every colour is a token, rules are scoped away from the kit", () => {
  const css = read("spike/index.css").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(css, /--twn-[a-z0-9-]+\s*:/, "tokens come from brand/tokens.css only");
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/, "no colour literals");
  assert.doesNotMatch(css, /:\s*(?:white|black)\s*[;}]/);
  const defined = new Set([...readFileSync(join(repo, "brand", "tokens.css"), "utf8").matchAll(/(--twn-[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
  for (const m of css.matchAll(/var\((--twn-[a-z0-9-]+)\)/g)) assert.ok(defined.has(m[1]), `${m[1]} is not in brand/tokens.css`);
  // a bare `button {` rule would leak margins / colours into the kit's buttons in the gallery
  const selectors = [...css.matchAll(/([^{}]+)\{/g)].flatMap((m) => m[1]!.split(",").map((x) => x.trim()));
  for (const sel of selectors.filter((x) => /button/.test(x))) assert.match(sel, /^\.(main-view|guide-bar) button/, sel);
  assert.doesNotMatch(css, /grid|(^|[\s;{])gap\s*:|position\s*:\s*sticky|:has\(/, "UXP CSS limits");
});

test("build: the spike bundle carries kit.css with the brand kit; the plugin links kit.css too", () => {
  const build = read("scripts/build.mjs");
  const spikeFiles = /spike:\s*\{[\s\S]*?files:\s*\{([^}]*)\}/.exec(build)?.[1] ?? "";
  assert.match(spikeFiles, /\.\.\.BRAND_KIT/);
  assert.match(spikeFiles, /"\.\.\/panel-ui\/styles\/kit\.css": "kit\.css"/);
  const pluginFiles = /plugin:\s*\{[\s\S]*?files:\s*\{([\s\S]*?)\n\s*\},/.exec(build)?.[1] ?? "";
  assert.match(pluginFiles, /"\.\.\/panel-ui\/styles\/kit\.css": "kit\.css"/);
  assert.match(read("plugin/index.html"), /href="kit\.css"/);
});

// ---- the style guide view -----------------------------------------------------------------------------------------

function fakeEl() {
  const handlers: Record<string, Array<() => void>> = {};
  return {
    style: {} as Record<string, string>,
    className: "",
    innerHTML: "",
    textContent: "",
    addEventListener: (t: string, fn: () => void) => void (handlers[t] ??= []).push(fn),
    click: () => handlers.click?.forEach((f) => f()),
  };
}

test("style guide view: shows the kit gallery for the chosen language in a 280 / 340 / 480 px column; the toggles and Back work", () => {
  const els = Object.fromEntries(["main", "guide", "frame", "host", "caption", "en", "ar", "w280", "w340", "w480", "back"].map((k) => [k, fakeEl()]));
  const e = els as Record<string, ReturnType<typeof fakeEl>>;
  const g = createStyleGuide({
    main: e.main as unknown as HTMLElement,
    guide: e.guide as unknown as HTMLElement,
    frame: e.frame as unknown as HTMLElement,
    host: e.host as unknown as HTMLElement,
    caption: e.caption as unknown as HTMLElement,
    buttons: {
      lang: { en: e.en as unknown as HTMLElement, ar: e.ar as unknown as HTMLElement },
      width: { 280: e.w280 as unknown as HTMLElement, 340: e.w340 as unknown as HTMLElement, 480: e.w480 as unknown as HTMLElement },
      back: e.back as unknown as HTMLElement,
    },
  });
  assert.equal(g.isOpen(), false);
  assert.deepEqual(g.show({ lang: "ar", width: 480 }), { lang: "ar", width: 480 });
  assert.equal(e.guide!.style.display, "flex");
  assert.equal(e.main!.style.display, "none");
  assert.equal(e.frame!.style.width, "480px");
  assert.match(e.host!.innerHTML, /class="kit-root kit-rtl" dir="rtl" lang="ar"/);
  assert.equal(e.caption!.textContent, guideCaption({ lang: "ar", width: 480 }));
  assert.match(e.caption!.textContent, /AR - 480 px - spike 0\.1\.8/);
  assert.equal(e.ar!.className, "seg on");
  assert.equal(e.w480!.className, "seg on");
  e.en!.click();
  assert.deepEqual(g.view(), { lang: "en", width: 480 });
  assert.match(e.host!.innerHTML, /class="kit-root kit-ltr" dir="ltr" lang="en"/);
  e.w280!.click();
  assert.equal(e.frame!.style.width, "280px");
  e.back!.click();
  assert.equal(g.isOpen(), false);
  assert.equal(e.guide!.style.display, "none");
  assert.equal(e.main!.style.display, "flex");
});

test("style guide content is the kit gallery: every component section, in both languages", () => {
  for (const lang of ["en", "ar"] as const) {
    const html = guideHtml({ lang, width: 340 });
    assert.match(html, /class="kit-hdr"/);
    for (const name of ["card()", "button()", "chip()", "stepStrip()", "progress()", "toast()", "dialog()", "emptyState()", "logDrawer()", "frameGrid()", "waveformFrame()"]) {
      assert.ok(html.includes(name), `${lang}: ${name}`);
    }
    assert.match(html, /<svg class="kit-icon/);
  }
});

// ---- ui_probes ----------------------------------------------------------------------------------------------------

type FakeStyle = Record<string, string>;
function style(props: FakeStyle): StyleLike {
  return { ...props, getPropertyValue: (n: string) => props[n] ?? "" };
}

/** A fake stage: elements are their selectors; widths / styles come from the tables the test gives. */
function fakeStage(o: { width?: (sel: string) => number; styles?: Record<string, FakeStyle>; root?: FakeStyle; missing?: RegExp; fonts?: ReturnType<UiStage["fonts"]> }) {
  const mounted: string[] = [];
  let html = "";
  const stage: UiStage = {
    mount: (h) => {
      html = h;
      mounted.push(h);
    },
    query: (sel) => (o.missing?.test(sel) ? null : html === "" ? null : sel),
    style: (el) => style(o.styles?.[el as string] ?? {}),
    box: (el) => ({ width: o.width?.(el as string) ?? 10, height: 16 }),
    rootStyle: () => style(o.root ?? {}),
    fonts: () => o.fonts ?? { present: false },
    unmount: () => void (html = ""),
    wait: async () => {},
  };
  return { stage, mounted };
}

const uiRun = (op: string, stage: UiStage) => runProbe(UI_PROBES.find((p) => p.op === op)!, { stage, fontSettleMs: 0 } satisfies UiCtx);

test("ui fonts: loaded when each brand span differs from BOTH fallbacks; computed family + widths recorded per family", async () => {
  const { stage, mounted } = fakeStage({
    width: (sel) => (sel.endsWith("-brand") ? 123.456 : sel.includes("-tnr-") ? 100 : 110),
    styles: Object.fromEntries(FONT_SAMPLES.flatMap((s) => FALLBACKS.map((fb) => [`#${fontId(s.key, fb.key, true)}`, { fontFamily: `"${s.family}", ${fb.family}` }]))),
    fonts: { present: true, check: () => true },
  });
  const r = await uiRun("fonts", stage);
  assert.equal(r.ok, true, JSON.stringify(r));
  const d = r.detail as { families: Record<string, { computed_family: string; loaded: boolean; widths: Record<string, { brand_width: number; fallback_width: number }>; document_fonts_check: unknown }> };
  assert.deepEqual(Object.keys(d.families), ["syne", "inter", "plex_arabic", "plex_mono"]);
  assert.equal(d.families.syne!.computed_family, '"Syne", "WncNoSuchFamily7f3a"');
  assert.deepEqual(d.families.plex_mono!.widths.tnr, { brand_width: 123.46, fallback_width: 100, differs: true });
  assert.equal(d.families.inter!.document_fonts_check, true);
  // the stage was mounted once, with every sample in both fallbacks, then removed
  assert.equal(mounted.length, 1);
  for (const s of FONT_SAMPLES) for (const fb of FALLBACKS) assert.ok(mounted[0]!.includes(fontId(s.key, fb.key, true)) && mounted[0]!.includes(fontId(s.key, fb.key, false)));
  assert.match(mounted[0]!, /font-family:&quot;IBM Plex Sans Arabic&quot;, &quot;Times New Roman&quot;, &quot;WncNoSuchFamily7f3a&quot;/);
});

test("ui fonts: not loaded when the brand spans measure like the fallback; inconclusive when only one fallback differs", async () => {
  const same = await uiRun("fonts", fakeStage({ width: () => 100 }).stage);
  assert.equal(same.ok, false);
  assert.equal(fontVerdict({ none: { brand_width: 1, fallback_width: 2, differs: true }, tnr: { brand_width: 1, fallback_width: 1, differs: false } }), null);
});

test("ui svg: the status icon's box > 0 passes and its computed fill / colour are recorded; a zero box fails", async () => {
  const styles = { "#wnc-svg-wrap svg": { fill: "rgb(61, 214, 140)", color: "rgb(61, 214, 140)", display: "block" }, "#wnc-svg-wrap svg path": { fill: "rgb(61, 214, 140)" } };
  const { stage, mounted } = fakeStage({ width: () => 16, styles });
  const r = await uiRun("svg", stage);
  assert.equal(r.ok, true);
  const d = r.detail as Record<string, unknown>;
  assert.deepEqual(d.svg_box, { width: 16, height: 16 });
  assert.equal(d.svg_fill, "rgb(61, 214, 140)");
  assert.equal(d.path_fill, "rgb(61, 214, 140)");
  // 0.1.8: the kit's icon has no fill attribute; its ink class sets the CSS fill (fill="currentColor" painted nothing)
  assert.match(mounted[0]!, /<svg class="kit-icon kit-icon-ok kit-ink-ok"/);
  assert.doesNotMatch(mounted[0]!, /<svg[^>]*\sfill=/);
  assert.equal((await uiRun("svg", fakeStage({ width: () => 0 }).stage)).ok, false);
  const gone = await uiRun("svg", fakeStage({ missing: /svg/ }).stage);
  assert.equal(gone.ok, false);
  assert.match(gone.error ?? "", /not in the DOM/);
});

test("ui box_shadow / gradient: computed values recorded (token and literal forms, root custom properties)", async () => {
  const { stage } = fakeStage({
    styles: {
      "#wnc-shadow-token": { boxShadow: "rgb(157, 107, 255) 0px 0px 0px 2px" },
      "#wnc-shadow-literal": { boxShadow: "rgb(157, 107, 255) 0px 0px 0px 2px" },
      "#wnc-grad-hairline": { backgroundImage: "linear-gradient(90deg, rgb(217, 92, 155), rgb(84, 0, 251))" },
      "#wnc-grad-fill": { backgroundImage: "linear-gradient(90deg, rgb(217, 92, 155), rgb(84, 0, 251))" },
      "#wnc-grad-literal": { backgroundImage: "linear-gradient(90deg, rgb(217, 92, 155), rgb(84, 0, 251))" },
    },
    root: { "--twn-focus": " 0 0 0 2px #9D6BFF", "--twn-gradient": "linear-gradient(90deg,#D95C9B,#5400FB)", "--twn-bg": "#000000" },
  });
  const shadow = await uiRun("box_shadow", stage);
  assert.equal(shadow.ok, true);
  assert.equal((shadow.detail as Record<string, unknown>).root_custom_property_twn_focus, "0 0 0 2px #9D6BFF");
  const grad = await uiRun("gradient", stage);
  assert.equal(grad.ok, true);
  assert.equal((grad.detail as Record<string, unknown>).root_custom_property_twn_gradient, "linear-gradient(90deg,#D95C9B,#5400FB)");
  const none = fakeStage({ styles: { "#wnc-shadow-token": { boxShadow: "none" }, "#wnc-shadow-literal": { boxShadow: "none" } } }).stage;
  assert.equal((await uiRun("box_shadow", none)).ok, false);
  assert.equal((await uiRun("gradient", none)).ok, false);
});

test("ui kit_code: the inline bdi.kit-code run in an EN and an AR sentence; display + background recorded", async () => {
  const sel = "#wnc-code-p bdi.kit-code";
  const ok = fakeStage({ styles: { [sel]: { display: "inline", backgroundColor: "rgb(30, 30, 30)", fontFamily: '"IBM Plex Mono", Consolas, monospace' } } });
  const r = await uiRun("kit_code", ok.stage);
  assert.equal(r.ok, true);
  const d = r.detail as Record<string, Record<string, unknown>>;
  assert.equal(d.en!.display, "inline");
  assert.equal(d.ar!.background_color, "rgb(30, 30, 30)");
  assert.equal(ok.mounted.length, 2);
  assert.match(ok.mounted[0]!, /<bdi dir="ltr" class="kit-code">C0239_prev_2026-10-13-1412\.prproj<\/bdi>/);
  const block = fakeStage({ styles: { [sel]: { display: "block", backgroundColor: "rgba(0, 0, 0, 0)" } } });
  assert.equal((await uiRun("kit_code", block.stage)).ok, false);
});

// ---- eco_probes: quit / restart names (never called) --------------------------------------------------------------

function quitSpies() {
  const calls: string[] = [];
  const spy = (name: string) => () => void calls.push(name);
  class Application {
    static quit = spy("Application.quit");
    static restart = spy("Application.restart");
    static get version() {
      return "26.5.2";
    }
    static get closeAllProjects() {
      calls.push("Application.closeAllProjects getter");
      return () => calls.push("Application.closeAllProjects()");
    }
    relaunch() {
      calls.push("app.relaunch");
    }
  }
  const ppro = { Application, Project: {}, quit: spy("ppro.quit"), exitApp: spy("ppro.exitApp") };
  const hostProto = { closeWindow: spy("host.closeWindow") };
  const host = Object.create(hostProto) as Record<string, unknown>;
  host.name = "premierepro";
  host.version = "26.5.2";
  Object.defineProperty(host, "restartRequired", {
    get() {
      calls.push("host.restartRequired getter");
      return false;
    },
    enumerable: true,
  });
  const uxp = { host, shell: { openExternal: spy("shell.openExternal") }, entrypoints: {} };
  return { calls, ppro, uxp };
}

test("quit / restart names: matching names on premierepro, Application (static + prototype) and uxp.host are recorded; nothing is called or read", async () => {
  const { calls, ppro, uxp } = quitSpies();
  const ctx: EcoCtx = { uxp, ppro, fs: {}, home: HOME, now: () => T0 };
  const r = await runProbe(quitRestartNamesProbe, ctx);
  assert.equal(r.ok, true);
  assert.deepEqual(calls, [], "no quit / restart / close member was called, and no matching getter ran");
  const d = r.detail as { called: boolean; matches_total: number; scanned: Array<{ path: string; matches?: Array<{ name: string; kind: string }> }> };
  assert.equal(d.called, false);
  const at = (path: string) => d.scanned.find((s) => s.path === path)?.matches?.map((m) => `${m.name}:${m.kind}`).sort();
  assert.deepEqual(at("premierepro"), ["exitApp:function", "quit:function"]);
  assert.deepEqual(at("premierepro.Application"), ["closeAllProjects:accessor get", "quit:function", "restart:function"]);
  assert.deepEqual(at("premierepro.Application.prototype"), ["relaunch:function"]);
  assert.deepEqual(at("uxp.host"), ["closeWindow:function", "restartRequired:accessor get"]);
  assert.equal(d.matches_total, 8);
  assert.ok(propertyNames(ppro.Application).includes("version"));
});

// ---- eco_probes: loopback (the token is never sent, recorded or logged) -------------------------------------------

function loopbackWorld() {
  const fs = memFs({ [ENGINE_JSON]: JSON.stringify({ port: PORT, token: TOKEN, pid: 1, version: "3.0.0", protocol: 4 }) });
  const sockets: Array<{ url: string; sent: string[]; closed: boolean }> = [];
  class FakeWs implements WsLike {
    readyState = 0;
    onopen: ((ev: unknown) => void) | null = null;
    onmessage: ((ev: { data: unknown }) => void) | null = null;
    onerror: ((ev: unknown) => void) | null = null;
    onclose: ((ev: { code?: number; reason?: string; wasClean?: boolean }) => void) | null = null;
    rec: { url: string; sent: string[]; closed: boolean };
    constructor(url: string) {
      if (url.includes("localhost")) throw new Error(`Permission denied to the url ${url}. Manifest entry not found.`);
      this.rec = { url, sent: [], closed: false };
      sockets.push(this.rec);
      setTimeout(() => {
        this.readyState = 1;
        this.onopen?.({});
      }, 1);
    }
    send(data: string) {
      this.rec.sent.push(data);
    }
    close() {
      this.rec.closed = true;
    }
  }
  const fetches: Array<{ url: string; init: unknown }> = [];
  const fetch = async (url: string, init?: unknown) => {
    fetches.push({ url, init });
    // a hostile error text that quotes the token: it must be redacted
    if (url.includes("localhost")) throw new TypeError(`Permission denied to the url ${url}. Manifest entry not found. (${TOKEN})`);
    return { status: 401, statusText: `Unauthorized ${TOKEN}` };
  };
  const ctx: EcoCtx = { uxp: {}, ppro: {}, fs: fs as EcoCtx["fs"], home: HOME, WebSocket: FakeWs as unknown as WsCtor, fetch, now: () => Date.now(), timing: { wsWaitMs: 200, fetchTimeoutMs: 200 } };
  return { ctx, sockets, fetches };
}

/** Captures console output while `fn` runs. */
async function captureConsole<T>(fn: () => Promise<T>): Promise<{ value: T; logged: string }> {
  const out: string[] = [];
  const saved = { log: console.log, info: console.info, warn: console.warn, error: console.error, debug: console.debug };
  for (const k of Object.keys(saved) as Array<keyof typeof saved>) console[k] = (...a: unknown[]) => void out.push(a.map(String).join(" "));
  try {
    return { value: await fn(), logged: out.join("\n") };
  } finally {
    Object.assign(console, saved);
  }
}

test("loopback: per form allowed / denied with the error text; the port comes from engine.json; no token is sent, recorded or logged", async () => {
  const w = loopbackWorld();
  const { value: r, logged } = await captureConsole(() => runProbe(loopbackProbe, w.ctx));
  assert.equal(r.ok, true, JSON.stringify(r));
  const d = r.detail as { port: number; manifest_domains: string[]; token_sent: boolean; forms: Array<Record<string, unknown>> };
  assert.equal(d.port, PORT);
  assert.deepEqual(d.manifest_domains, [...LOOPBACK_DOMAINS]);
  const by = Object.fromEntries(d.forms.map((f) => [f.form as string, f]));
  assert.equal(by["ws://127.0.0.1:<port>/session"]!.allowed, true);
  assert.equal(by["ws://127.0.0.1:<port>/session"]!.url, `ws://127.0.0.1:${PORT}/session`);
  assert.equal(by["ws://localhost:<port>/session"]!.allowed, false);
  assert.match(String(by["ws://localhost:<port>/session"]!.error), /Manifest entry not found/);
  assert.equal(by["http://127.0.0.1:<port>/status"]!.allowed, true);
  assert.equal(by["http://127.0.0.1:<port>/status"]!.status, 401);
  assert.equal(by["http://localhost:<port>/status"]!.allowed, false);
  // nothing carries the token: no hello on the socket, no Authorization header, every text redacted
  assert.deepEqual(w.sockets.map((s) => s.sent), [[]]);
  assert.ok(w.sockets.every((s) => s.closed), "the probe socket is closed");
  assert.ok(w.fetches.every((f) => f.init === undefined), "fetch without headers");
  assert.equal(d.token_sent, false);
  assert.ok(!JSON.stringify(r).includes(TOKEN), "the token is not in the result");
  assert.ok(!logged.includes(TOKEN), "the token is not logged");
  assert.match(JSON.stringify(r), /\[redacted\]/);
});

test("loopback: no engine.json is n/a with the reason (not a failure); a denied 127.0.0.1 form is a failure", async () => {
  const none = await runProbe(loopbackProbe, { uxp: {}, ppro: {}, fs: memFs() as EcoCtx["fs"], home: HOME, now: () => T0 });
  assert.equal(none.ok, null);
  assert.match(String((none.detail as { error: string }).error), /engine\.json not usable.*reel serve --ensure/);
  const w = loopbackWorld();
  const denyAll = (url: string) => {
    throw new Error(`Permission denied to the url ${url}. Manifest entry not found.`);
  };
  const r = await runProbe(loopbackProbe, { ...w.ctx, WebSocket: function (url: string) { denyAll(url); } as unknown as WsCtor });
  assert.equal(r.ok, false);
});

// ---- eco_probes: openExternal --------------------------------------------------------------------------------------

test("openExternal: called once with whynotcut://engine/start; resolved value, elapsed ms and the consent suspicion recorded", async () => {
  const calls: Array<{ url: string; why: unknown }> = [];
  let t = T0;
  const uxp = {
    shell: {
      openExternal: async (url: string, why?: string) => {
        calls.push({ url, why });
        t += 4200; // a person clicking through a consent dialog
        return "";
      },
    },
  };
  const r = await runProbe(openExternalProbe, { uxp, ppro: {}, fs: {}, home: HOME, now: () => t });
  assert.deepEqual(calls.map((c) => c.url), [ENGINE_START_URL]);
  assert.equal(ENGINE_START_URL, "whynotcut://engine/start");
  assert.match(String(calls[0]!.why), /WhyNot Cut spike 0\.1\.8/);
  assert.equal(r.ok, true);
  const d = r.detail as Record<string, unknown>;
  assert.equal(d.settled, "resolved");
  assert.deepEqual(d.value, { type: "string", value: "" });
  assert.equal(d.elapsed_ms, 4200);
  assert.equal(d.consent_dialog_suspected, 4200 >= CONSENT_SUSPECT_MS);
});

test("openExternal: a rejection keeps the error text; a call that never settles is n/a after the timeout; no shell is a failure", async () => {
  const rejected = await runProbe(openExternalProbe, { uxp: { shell: { openExternal: () => Promise.reject(new Error("No application is associated with whynotcut")) } }, ppro: {}, fs: {}, home: HOME, now: () => T0 });
  assert.equal(rejected.ok, false);
  assert.equal((rejected.detail as Record<string, unknown>).settled, "rejected");
  assert.match(String((rejected.detail as Record<string, unknown>).error), /No application is associated/);
  const hang = await runProbe(openExternalProbe, { uxp: { shell: { openExternal: () => new Promise(() => {}) } }, ppro: {}, fs: {}, home: HOME, now: () => Date.now(), timing: { openExternalTimeoutMs: 20 } });
  assert.equal(hang.ok, null);
  assert.equal((hang.detail as Record<string, unknown>).settled, "timeout");
  const none = await runProbe(openExternalProbe, { uxp: {}, ppro: {}, fs: {}, home: HOME, now: () => T0 });
  assert.equal(none.ok, false);
});

// ---- eco_probes: hide / show --------------------------------------------------------------------------------------

test("hide/show: entrypoints.setup registers the panel's create / show / hide / destroy; events are recorded in order with timestamps and persisted", async () => {
  let cfg: { panels: Record<string, Record<string, (...a: unknown[]) => void>> } | undefined;
  const uxp = { entrypoints: { setup: (c: typeof cfg) => void (cfg = c) } };
  const docListeners: Record<string, () => void> = {};
  const doc = { visibilityState: "visible", addEventListener: (t: string, l: () => void) => void (docListeners[t] = l) };
  let t = T0;
  const persisted: number[] = [];
  const rec = createLifecycle(() => (t += 10), (events) => void persisted.push(events.length));
  const setup = setupLifecycle(uxp, "whynotCutSpike", rec, doc);
  assert.equal(setup.entrypoints_setup, "called");
  assert.deepEqual(Object.keys(cfg!.panels), ["whynotCutSpike"]);
  assert.deepEqual(Object.keys(cfg!.panels.whynotCutSpike!), ["create", "show", "hide", "destroy"]);
  cfg!.panels.whynotCutSpike!.show!({ node: { tagName: "BODY" } });
  cfg!.panels.whynotCutSpike!.hide!();
  doc.visibilityState = "hidden";
  docListeners.visibilitychange!();
  cfg!.panels.whynotCutSpike!.show!();
  const r = await runProbe(hideShowProbe, { uxp, ppro: {}, fs: {}, home: HOME, now: () => t, lifecycle: rec, lifecycleSetup: setup });
  assert.equal(r.ok, true);
  const d = r.detail as { order: string[]; events: Array<{ seq: number; at: string; t_ms: number; detail?: unknown }> };
  assert.deepEqual(d.order, ["script.loaded", "panel.show", "panel.hide", "document.visibilitychange", "panel.show"]);
  assert.deepEqual(d.events.map((e) => e.seq), [1, 2, 3, 4, 5]);
  assert.ok(d.events.every((e, i) => i === 0 || e.t_ms > d.events[i - 1]!.t_ms));
  assert.match(d.events[1]!.at, /^2026-10-13T12:00:00\.\d{3}Z$/);
  assert.deepEqual(d.events[3]!.detail, { visibilityState: "hidden" });
  assert.deepEqual(persisted, [1, 2, 3, 4, 5], "lifecycle.json is rewritten on every event");
});

test("hide/show: a throwing entrypoints.setup is recorded (not thrown); no entrypoints is n/a", async () => {
  const rec = createLifecycle(() => T0);
  const bad = setupLifecycle({ entrypoints: { setup: () => { throw new Error("setup already called"); } } }, "whynotCutSpike", rec);
  assert.equal(bad.entrypoints_setup, "threw");
  assert.equal(bad.error, "setup already called");
  assert.equal((await runProbe(hideShowProbe, { uxp: {}, ppro: {}, fs: {}, home: HOME, now: () => T0, lifecycle: rec, lifecycleSetup: bad })).ok, false);
  const none = setupLifecycle({}, "whynotCutSpike", createLifecycle(() => T0));
  assert.equal(none.entrypoints_setup, "unavailable");
});

// ---- the results shape per mode ----------------------------------------------------------------------------------

function fullStage(): UiStage {
  return fakeStage({
    width: (sel) => (sel.endsWith("-brand") ? 120 : sel.includes("-serif-") ? 100 : 110),
    styles: {
      "#wnc-shadow-token": { boxShadow: "#9D6BFF 0px 0px 0px 2px" },
      "#wnc-shadow-literal": { boxShadow: "#9D6BFF 0px 0px 0px 2px" },
      "#wnc-grad-hairline": { backgroundImage: "linear-gradient(90deg,#D95C9B,#5400FB)" },
      "#wnc-grad-fill": { backgroundImage: "linear-gradient(90deg,#D95C9B,#5400FB)" },
      "#wnc-grad-literal": { backgroundImage: "linear-gradient(90deg,#D95C9B,#5400FB)" },
      "#wnc-svg-wrap svg path": { fill: "#3DD68C" },
      "#wnc-code-p bdi.kit-code": { display: "inline", backgroundColor: "#1E1E1E" },
    },
  }).stage;
}

for (const mode of ["full", "keep_open", "style_guide"] as const) {
  test(`results shape (${mode}): ui_probes and eco_probes carry every probe; openExternal only in full; quit never called; token never in the results`, async () => {
    const w = loopbackWorld();
    const spies = quitSpies();
    const opened: string[] = [];
    let t = T0;
    const uxp = { ...spies.uxp, shell: { openExternal: async (u: string) => void opened.push(u) } };
    const eco: EcoCtx = { ...w.ctx, uxp, ppro: spies.ppro, now: () => (t += 5), lifecycle: createLifecycle(() => T0), lifecycleSetup: { entrypoints_setup: "called", panel_id: "whynotCutSpike", listeners: [] } };
    const sections: Sections = { ui_probes: {}, eco_probes: {} };
    const steps: string[] = [];
    const { logged } = await captureConsole(async () => {
      await runPreSections(sections, { stage: fullStage(), fontSettleMs: 0 }, eco, (s) => void steps.push(s));
      await runPostSections(mode, sections, eco);
    });
    assert.deepEqual(Object.keys(sections.ui_probes), [...UI_PROBE_NAMES]);
    assert.deepEqual(Object.keys(sections.eco_probes).sort(), [...ECO_PROBE_NAMES].sort());
    for (const r of [...Object.values(sections.ui_probes), ...Object.values(sections.eco_probes)]) {
      assert.deepEqual(Object.keys(r).filter((k) => k !== "stack").sort(), ["detail", "error", "ms", "ok", "op"]);
    }
    assert.ok(Object.values(sections.ui_probes).every((r) => r.ok === true), JSON.stringify(sections.ui_probes, null, 1).slice(0, 2000));
    if (mode === "full") {
      assert.deepEqual(opened, [ENGINE_START_URL]);
      assert.equal(sections.eco_probes.open_external!.ok, true);
    } else {
      assert.deepEqual(opened, [], `${mode} never calls openExternal`);
      assert.equal(sections.eco_probes.open_external!.ok, null);
      assert.match(String(sections.eco_probes.open_external!.detail), /mode "full" only/);
    }
    assert.deepEqual(spies.calls, [], "quit / restart / close never called");
    const text = JSON.stringify(sections);
    assert.ok(!text.includes(TOKEN));
    assert.ok(!logged.includes(TOKEN));
    const c = sectionCounts(sections);
    assert.equal(c.pass + c.fail + c.na, UI_PROBE_NAMES.length + ECO_PROBE_NAMES.length);
    assert.ok(steps.includes("UI probe fonts") && steps.includes("Ecosystem probe loopback"));
  });
}

test("spike.ts: the three modes are wired (style guide opened for style_guide, sections written into the results, lifecycle at boot)", () => {
  const spike = read("spike/src/spike.ts");
  assert.match(spike, /run: \(mode: RunMode, id: string, view\?: GuideView\) => runSpike\(mode, id, view\)/);
  assert.match(spike, /if \(mode === "style_guide"\) \{\s*lab\?\.hide\(false\);\s*guide\?\.show\(view \?\? \{\}\);/);
  assert.match(spike, /const noPremiere = mode === "style_guide" \|\| mode === "css_lab";\s*const probes = noPremiere \? \[\] : buildProbes/);
  assert.match(spike, /ui_probes: sections\.ui_probes,\s*eco_probes: sections\.eco_probes/);
  assert.match(spike, /runPreSections\(/);
  assert.match(spike, /runPostSections\(mode,/);
  assert.match(spike, /function boot\(\): void \{\s*\/\/[^\n]*\n\s*startLifecycle\(\);/);
  // never a call to a quit / restart API anywhere in the spike sources
  for (const f of ["spike.ts", "eco-probes.ts", "sections.ts", "ui-probes.ts", "style-guide.ts", "probes.ts", "css-lab.ts", "lab-dom.ts"]) {
    assert.doesNotMatch(read(`spike/src/${f}`).replace(/\/\/.*$/gm, ""), /\.(quit|exit|restart|relaunch)\s*\(/, f);
  }
});
