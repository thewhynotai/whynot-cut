// Spike 0.1.7: the CSS lab (run-request mode "css_lab", the lab view, `results.lab`) and the 0.1.6 review's probe
// fixes (resolved values, unlike font fallbacks, svg fill compared with the expected colour, a layout pass after mounting,
// lifecycle.json's folder made first) - all against hand-made fakes (no Premiere, no DOM).
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createAutoRunner, RUN_MODES, type AutoRunDeps, type GuideView, type RunMode, type RunSummary } from "../spike/src/autorun.ts";
import {
  BUTTON_FORMS,
  BUTTON_VARIANTS,
  buttonId,
  bytesToBase64,
  colorsIn,
  createLabView,
  FONT_VARIANTS,
  fontRefId,
  fontSpanId,
  GLOW_INNER,
  GLOW_VARIANTS,
  glowId,
  isResolved,
  LAB_FONTS,
  LAB_REF_FAMILY,
  LAB_SECTIONS,
  labCaption,
  labFamily,
  labHtml,
  normColor,
  okSvgFile,
  runCssLab,
  staticFontFaceCss,
  SVG_CONTEXTS,
  SVG_VARIANTS,
  svgId,
  WS_DIRS,
  WS_VARIANTS,
  wsId,
  type LabDom,
  type LabEnv,
  type Rect,
  type StepResult,
} from "../spike/src/css-lab.ts";
import { createLifecycle, lifecycleWriter, type EcoCtx } from "../spike/src/eco-probes.ts";
import { ECO_PROBE_NAMES, runPreSections, type Sections } from "../spike/src/sections.ts";
import { UI_PROBES, type StyleLike, type UiCtx, type UiStage } from "../spike/src/ui-probes.ts";
import { runProbe } from "../spike/src/runner.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(root, "..", "..");
const read = (p: string) => readFileSync(join(root, p), "utf8");
const DIR = "C:/Users/LOQ/.whynot-cut/uxp-spike";
const T0 = Date.parse("2026-10-13T12:00:00.000Z");
const iso = (ms: number) => new Date(ms).toISOString();

// ---- version + run-request mode "css_lab" -------------------------------------------------------------------------

test("spike 0.1.7: manifest and SPIKE_VERSION say the current version (0.1.9); css_lab is a run mode", () => {
  assert.equal(JSON.parse(read("spike/manifest.json")).version, "0.1.9");
  assert.match(read("spike/src/version.ts"), /SPIKE_VERSION = "0.1.9"/);
  assert.deepEqual([...RUN_MODES], ["full", "keep_open", "style_guide", "css_lab"]);
});

function memFs(initial: Record<string, string> = {}) {
  const files = new Map<string, string>(Object.entries(initial));
  const dirs = new Set<string>();
  const fs: Record<string, unknown> = {
    files,
    dirs,
    readFileSync: (p: string) => {
      const v = files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return v;
    },
    writeFileSync: (p: string, data: string) => {
      const parent = p.slice(0, p.lastIndexOf("/"));
      if (!dirs.has(parent) && !initial.__nodirs) throw new Error(`ENOENT (no folder): ${parent}`);
      files.set(p, data);
    },
    lstatSync: (p: string) => {
      if (dirs.has(p)) return { size: 0, isDirectory: () => true };
      const v = files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return { size: v.length, isDirectory: () => false };
    },
    mkdirSync: (p: string) => void dirs.add(p),
    renameSync: (from: string, to: string) => {
      const v = files.get(from);
      if (v === undefined) throw new Error(`ENOENT: ${from}`);
      files.delete(from);
      files.set(to, v);
    },
    unlinkSync: (p: string) => void files.delete(p),
  };
  return fs as Record<string, unknown> & { files: Map<string, string>; dirs: Set<string> };
}

function autorun(request: Record<string, unknown>) {
  const fs = memFs({ __nodirs: "1", [`${DIR}/run-request.json`]: JSON.stringify({ requested_at: iso(T0 - 1000), ...request }) });
  const runs: Array<{ id: string; mode: RunMode; view?: GuideView; args: number }> = [];
  let held = false;
  const summary: RunSummary = { results_file: `${DIR}/results-x.json`, ok: true, pass: 40, fail: 12, na: 30 };
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

test("run-request mode css_lab: claimed, run with (mode, id) only (no view), the done file names the mode", async () => {
  const h = autorun({ id: "lab-1", mode: "css_lab" });
  const out = await h.runner.poll();
  assert.equal(out.kind, "ran");
  assert.deepEqual(h.runs, [{ id: "lab-1", mode: "css_lab", args: 2 }]);
  const done = JSON.parse(h.fs.files.get(`${DIR}/run-done-lab-1.json`)!);
  assert.equal(done.mode, "css_lab");
  assert.equal(done.view, undefined);
  assert.equal(done.ok, true);
  assert.equal(done.pass, 40);
});

test("css_lab with lang / width is malformed (the lab uses the panel's own width); an unknown mode names css_lab", async () => {
  for (const [i, bad] of [{ mode: "css_lab", lang: "ar" }, { mode: "css_lab", width: 340 }, { mode: "csslab" }].entries()) {
    const h = autorun({ id: `bad-lab-${i}`, ...bad });
    const out = await h.runner.poll();
    assert.equal(out.kind, "malformed", JSON.stringify(bad));
    assert.equal(h.runs.length, 0);
    if (bad.mode === "csslab") assert.match((out as { error: string }).error, /"css_lab"/);
    else assert.match((out as { error: string }).error, /belong to mode "style_guide" only/);
  }
});

// ---- colours ------------------------------------------------------------------------------------------------------

test("normColor / colorsIn / isResolved: hex, rgb(a), named; var( and currentcolor are not resolved colours", () => {
  assert.equal(normColor("#5400FB"), "#5400fb");
  assert.equal(normColor("rgb(84, 0, 251)"), "#5400fb");
  assert.equal(normColor("rgba(84, 0, 251, 1)"), "#5400fb");
  assert.equal(normColor("rgba(255,255,255,.08)"), "#ffffff14");
  assert.equal(normColor("#FFFFFF14"), "#ffffff14");
  assert.equal(normColor("#fff"), "#ffffff");
  assert.equal(normColor("black"), "#000000");
  assert.equal(normColor("currentcolor"), null);
  assert.equal(normColor("var(--twn-ok)"), null);
  assert.equal(normColor(""), null);
  assert.deepEqual(colorsIn("linear-gradient(90deg, rgb(217, 92, 155), #5400FB)"), ["#d95c9b", "#5400fb"]);
  assert.equal(isResolved("#9D6BFF 0px 0px 0px 2px"), true);
  assert.equal(isResolved("var(--twn-focus)"), false);
  assert.equal(isResolved("none"), false);
  assert.equal(isResolved(""), false);
});

test("bytesToBase64 matches Node's base64 for every tail length", () => {
  for (const n of [0, 1, 2, 3, 4, 5, 255, 1000]) {
    const bytes = new Uint8Array(n).map((_v, i) => (i * 37 + 11) & 255);
    assert.equal(bytesToBase64(bytes), Buffer.from(bytes).toString("base64"), String(n));
  }
});

// ---- the lab page -------------------------------------------------------------------------------------------------

test("lab page: buttons A-H in four forms each, the variants as specified (div role=button, sp-button, longhand, appearance:none)", () => {
  const html = labHtml();
  assert.deepEqual(BUTTON_VARIANTS.map((v) => v.id), ["A", "B", "C", "D", "E", "F", "G", "H"]);
  assert.deepEqual(BUTTON_FORMS.map((f) => f.key), ["primary", "danger", "secondary", "disabled"]);
  for (const v of BUTTON_VARIANTS) for (const f of BUTTON_FORMS) assert.ok(html.includes(`id="${buttonId(v.id, f.key)}"`), `${v.id} ${f.key}`);
  const tagOf = (id: string) => new RegExp(`<([a-z-]+) id="${id}"[^>]*>`).exec(html);
  assert.match(tagOf(buttonId("A", "primary"))![0], /^<button [^>]*class="lab-b lab-flex lab-r999 lab-bg-primary"/);
  assert.match(tagOf(buttonId("B", "primary"))![0], /class="lab-b lab-ib lab-r999 lab-bg-primary"/);
  assert.match(tagOf(buttonId("C", "danger"))![0], /class="lab-b lab-flex lab-r16 lab-bg-danger"/);
  assert.match(tagOf(buttonId("D", "secondary"))![0], /class="lab-b lab-ib lab-r16 lab-bg-glass"/);
  assert.match(tagOf(buttonId("E", "primary"))![0], /^<div [^>]*role="button" tabindex="0"/);
  assert.match(tagOf(buttonId("F", "primary"))![0], /^<sp-button id="lab-btn-F-primary" variant="cta"/);
  assert.match(tagOf(buttonId("G", "primary"))![0], /lab-bgc-primary/);
  assert.match(tagOf(buttonId("H", "primary"))![0], /lab-noapp/);
  assert.match(tagOf(buttonId("A", "disabled"))![0], /lab-off" disabled>/);
  // 0.1.7 measured the kit's old .kit-btn as A; since 0.1.8 the kit draws E (a <div role="button">, flex, 16 px radius)
  const kit = readFileSync(join(root, "..", "panel-ui", "styles", "kit.css"), "utf8");
  assert.match(kit, /\.kit-btn \{\s*display: flex;[\s\S]*?border-radius: var\(--twn-radius-control\)/);
});

test("lab page: glow, svg (6 variants x chip / inline / row / block), fonts (unique families) and whitespace (LTR + RTL) rows", () => {
  const html = labHtml();
  for (const v of GLOW_VARIANTS) for (const i of GLOW_INNER) {
    assert.ok(html.includes(`id="${glowId(v.id, i, "wrap")}"`) && html.includes(`id="${glowId(v.id, i, "btn")}"`), `${v.id} ${i}`);
  }
  assert.ok(html.includes(`id="${glowId("GD", "button", "layer")}"`));
  for (const v of SVG_VARIANTS) for (const c of SVG_CONTEXTS) assert.ok(html.includes(`id="${svgId(v.id, c)}"`), `${v.id} ${c}`);
  const svg = (id: string) => new RegExp(`<(svg|img) id="${id}"[^>]*>`).exec(html)![0];
  assert.match(svg(svgId("S1", "row")), /fill="currentColor"/);
  assert.match(svg(svgId("S2", "row")), /fill="#3DD68C"/);
  assert.doesNotMatch(svg(svgId("S3", "row")), /fill=/);
  assert.match(svg(svgId("S3", "row")), /lab-svg-path/);
  assert.match(svg(svgId("S4", "row")), /lab-svg-self/);
  assert.match(svg(svgId("S5", "chip")), /^<img [^>]*src="data:image\/svg\+xml;utf8,%3Csvg/);
  assert.match(svg(svgId("S6", "block")), /src="lab\/icons\/ok\.svg"/);
  assert.match(svg(svgId("S1", "inline")), /class="lab-icon-inline /);
  assert.match(html, /<span class="kit-chip kit-chip-ok lab-cell"><svg id="lab-svg-S1-chip"/);
  // fonts: one span per variant and font, each under its own family, falling back to the one nonexistent family
  const families = new Set<string>();
  for (const v of FONT_VARIANTS) for (const f of LAB_FONTS) {
    const fam = labFamily(f, v);
    assert.ok(!families.has(fam));
    families.add(fam);
    assert.ok(html.includes(`id="${fontSpanId(v.id, f.key)}"`));
    assert.ok(html.includes(`font-family:&quot;${fam}&quot;, &quot;${LAB_REF_FAMILY}&quot;;`), fam);
  }
  assert.deepEqual(FONT_VARIANTS.map((v) => v.id), ["ctrl", "A", "B", "B2", "C", "D", "E", "F", "F2", "H"]);
  for (const f of LAB_FONTS) assert.ok(html.includes(`id="${fontRefId("ref", f.key)}"`) && html.includes(`id="${fontRefId("sanity", f.key)}"`));
  for (const v of WS_VARIANTS) for (const d of WS_DIRS) {
    for (const part of ["row", "label", "count"] as const) assert.ok(html.includes(`id="${wsId(v.id, d, part)}"`), `${v.id} ${d} ${part}`);
  }
  assert.match(html, /id="lab-ws-W1-ltr-label" class="lab-ws-label">Needs you<\/span> <span id="lab-ws-W1-ltr-count"/);
  assert.match(html, /id="lab-ws-W3-rtl-label" class="lab-ws-label">مطلوب منك<\/span>&nbsp;<span/);
  assert.match(html, /class="lab-ws lab-rtl" dir="rtl"/);
  assert.doesNotMatch(html, /Claude Code/);
});

test("lab.css: the static @font-face rules are exactly staticFontFaceCss(); every font URL is bundled; UXP limits; tokens only from brand/tokens.css", () => {
  const css = read("spike/lab.css");
  assert.ok(css.includes(staticFontFaceCss()), "lab.css carries the generated @font-face block verbatim");
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(bare, /--twn-[a-z0-9-]+\s*:/, "no token definitions (brand/tokens.css is the one source)");
  assert.doesNotMatch(bare, /grid|(^|[\s;{])gap\s*:|position\s*:\s*sticky|:has\(|\[[a-z-]+=/, "UXP limits: no grid / gap / sticky / :has / [attr=value]");
  const defined = new Set([...readFileSync(join(repo, "brand", "tokens.css"), "utf8").matchAll(/(--twn-[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
  for (const m of bare.matchAll(/var\((--twn-[a-z0-9-]+)\)/g)) assert.ok(defined.has(m[1]), `${m[1]} is not in brand/tokens.css`);
  // every URL resolves to a file that goes into the bundle (fonts/ from panel-ui, lab/ from spike/lab)
  const urls = [...bare.matchAll(/url\("([^"]+)"\)/g)].map((m) => m[1]!.replace(/^plugin:\//, "").replace(/^\.\//, ""));
  assert.ok(urls.length >= 12);
  for (const u of urls) {
    const src = u.startsWith("lab/") ? join(root, "spike", u) : join(root, "..", "panel-ui", u);
    assert.ok(existsSync(src), `${u} -> ${src}`);
  }
  for (const f of LAB_FONTS) {
    assert.ok(existsSync(join(root, "spike", f.woff)), f.woff);
    assert.ok(existsSync(join(root, "spike", dirname(f.woff), "OFL.txt")), `OFL text next to ${f.woff}`);
    assert.equal(readFileSync(join(root, "spike", f.woff)).subarray(0, 4).toString("latin1"), "wOFF");
  }
  assert.equal(read("spike/lab/icons/ok.svg"), okSvgFile());
});

test("page + build: index.html links lab.css after index.css and has the lab view; build ships lab.css and lab/", () => {
  const html = read("spike/index.html");
  assert.deepEqual([...html.matchAll(/<link[^>]+href="([^"]+)"/g)].map((m) => m[1]), ["tokens.css", "kit.css", "index.css", "lab.css"]);
  assert.match(html, /<div id="lab-view" class="lab-view">[\s\S]*id="lab-back"[\s\S]*id="lab-caption"[\s\S]*<div id="lab-host" class="lab-host">/);
  assert.match(html, /<button id="lab-open" type="button">CSS lab<\/button>/);
  const build = read("scripts/build.mjs");
  const spikeFiles = /spike:\s*\{[\s\S]*?files:\s*\{([^}]*)\}/.exec(build)?.[1] ?? "";
  assert.match(spikeFiles, /"spike\/lab\.css": "lab\.css"/);
  assert.match(spikeFiles, /"spike\/lab": "lab"/);
});

// ---- the lab view -------------------------------------------------------------------------------------------------

function fakeEl() {
  const handlers: Record<string, Array<() => void>> = {};
  return {
    style: {} as Record<string, string>,
    innerHTML: "",
    textContent: "",
    addEventListener: (t: string, fn: () => void) => void (handlers[t] ??= []).push(fn),
    click: () => handlers.click?.forEach((f) => f()),
  };
}

test("lab view: show hides the probe view and the style guide and renders the lab; Back returns to the probe view", () => {
  const e = Object.fromEntries(["main", "guide", "lab", "host", "caption", "back"].map((k) => [k, fakeEl()])) as Record<string, ReturnType<typeof fakeEl>>;
  const v = createLabView(e as unknown as Parameters<typeof createLabView>[0]);
  assert.equal(v.isOpen(), false);
  v.show();
  assert.equal(v.isOpen(), true);
  assert.deepEqual([e.main!.style.display, e.guide!.style.display, e.lab!.style.display], ["none", "none", "flex"]);
  assert.equal(e.host!.innerHTML, labHtml());
  assert.equal(e.caption!.textContent, "CSS lab - spike 0.1.9");
  v.caption(561.4);
  assert.equal(e.caption!.textContent, labCaption(561.4));
  assert.match(e.caption!.textContent, /CSS lab - spike 0\.1\.9 - 561 px/);
  v.hide(false);
  assert.equal(e.lab!.style.display, "none");
  assert.equal(e.main!.style.display, "none", "hide(false): the style guide takes over");
  v.show();
  e.back!.click();
  assert.equal(v.isOpen(), false);
  assert.equal(e.main!.style.display, "flex");
});

// ---- runCssLab: the results shape and the verdicts ----------------------------------------------------------------

type Props = Record<string, string | undefined>;
function styleOf(props: Props): StyleLike {
  return { ...props, getPropertyValue: (n: string) => props[n] ?? "" } as StyleLike;
}

interface FakeLab {
  styles?: (sel: string) => Props | undefined;
  rect?: (sel: string) => Rect | undefined;
  props?: (sel: string, name: string) => unknown;
  missing?: RegExp;
}

function fakeDom(o: FakeLab = {}) {
  const waits: number[] = [];
  const dom: LabDom = {
    query: (sel) => (o.missing?.test(sel) ? null : sel),
    style: (el) => styleOf(o.styles?.(el as string) ?? {}),
    rect: (el) => o.rect?.(el as string) ?? { x: 0, y: 0, width: 10, height: 10 },
    prop: (el, name) => (name === "tagName" ? "BUTTON" : o.props?.(el as string, name)),
    hostWidth: () => 560,
    wait: async (ms) => void waits.push(ms),
  };
  return { dom, waits };
}

function fakeEnv(o: { facts?: () => Record<string, unknown>; noBytes?: boolean } = {}) {
  const injected: string[] = [];
  const faces: Array<{ family: string; source: string | ArrayBuffer; descriptors: Record<string, string> }> = [];
  const reads: string[] = [];
  const bytes = new Uint8Array([0, 1, 0, 0, 0, 12, 0x80, 0xff, 7]).buffer;
  const env: LabEnv = {
    injectStyle: (css): StepResult => {
      injected.push(css);
      return { ok: true, in_dom: true };
    },
    loadFontFace: async (family, source, descriptors) => {
      faces.push({ family, source, descriptors });
      return { ok: true, status: "loaded", added_to_document_fonts: true };
    },
    readPluginBytes: async (rel) => {
      reads.push(rel);
      return o.noBytes ? { error: "fs plugin:/: no" } : { bytes, via: "fake" };
    },
    facts: o.facts ?? (() => ({ typeof_FontFace: "function", sp_button_defined: false })),
  };
  return { env, injected, faces, reads, bytes };
}

const GOOD_BG: Record<string, string> = { primary: "#5400FB", danger: "#FF5C5C", secondary: "rgba(255, 255, 255, 0.08)", disabled: "#5400FB" };

test("runCssLab: results.lab carries every section and variant, settles layout + fonts first, counts verdicts", async () => {
  const { dom, waits } = fakeDom({
    styles: (sel) => {
      const btn = /^#lab-btn-([A-H])-(\w+)$/.exec(sel);
      if (btn) return { display: "flex", background: GOOD_BG[btn[2]!]!, opacity: btn[2] === "disabled" ? "0.45" : "1" };
      if (/^#lab-glow-G[ABD]-\w+-(wrap|layer)$/.test(sel)) return { "background-image": "linear-gradient(90deg,#D95C9B,#5400FB)" };
      if (/^#lab-glow-GC-\w+-btn$/.test(sel)) return { "border-image-source": "linear-gradient(90deg,#D95C9B,#5400FB)" };
      if (/^#lab-svg-S\d-\w+ path$/.test(sel)) return { fill: "#3DD68C" };
      return undefined;
    },
  });
  const { env, injected, faces, reads } = fakeEnv();
  const r = await runCssLab(dom, env, { layoutSettleMs: 7, fontSettleMs: 9 });
  assert.deepEqual(waits, [7, 9], "a layout pass, then the fonts settle, before anything is measured");
  assert.equal(r.lab, "css_lab");
  assert.equal(r.spike, "0.1.9");
  assert.equal(r.host_width_px, 560);
  assert.deepEqual(Object.keys(r.facts), ["typeof_FontFace", "sp_button_defined"]);
  for (const s of LAB_SECTIONS) assert.ok(s in r, s);
  const buttons = r.buttons as Record<string, { forms: Record<string, { computed_matches: boolean | null; resolved_background: string | null; style: Props; rect: Rect }> }>;
  assert.deepEqual(Object.keys(buttons), ["A", "B", "C", "D", "E", "F", "G", "H"]);
  for (const v of ["A", "B", "C", "D", "E", "G", "H"]) for (const f of BUTTON_FORMS) assert.equal(buttons[v]!.forms[f.key]!.computed_matches, true, `${v} ${f.key}`);
  assert.equal(buttons.F!.forms.primary!.computed_matches, null, "sp-button: Spectrum's own colours, only the screenshot decides");
  assert.equal(buttons.A!.forms.secondary!.resolved_background, "#ffffff14");
  for (const p of ["display", "background", "background-color", "border-top-left-radius", "appearance", "-webkit-appearance", "opacity"]) assert.ok(p in buttons.A!.forms.primary!.style, p);
  assert.deepEqual(buttons.A!.forms.primary!.rect, { x: 0, y: 0, width: 10, height: 10 });
  const glow = r.glow as Record<string, { inner: Record<string, { computed_gradient_resolved: boolean }>; paint: string }>;
  assert.deepEqual(Object.keys(glow), ["GA", "GB", "GC", "GD"]);
  for (const v of Object.values(glow)) for (const i of GLOW_INNER) assert.equal(v.inner[i]!.computed_gradient_resolved, true);
  const svg = r.svg.variants as Record<string, { contexts: Record<string, { verdict: boolean | null }> }>;
  assert.deepEqual(Object.keys(svg), ["S1", "S2", "S3", "S4", "S5", "S6"]);
  for (const v of ["S1", "S2", "S3", "S4"]) for (const c of SVG_CONTEXTS) assert.equal(svg[v]!.contexts[c]!.verdict, true, `${v} ${c}`);
  assert.equal(svg.S5!.contexts.chip!.verdict, null, "an <img> with a box: only the screenshot decides");
  // runtime fonts: a <style> for E and H (data: URI), FontFace for F (url) and F2 (bytes), for both fonts
  assert.equal(injected.length, 4);
  assert.match(injected[0]!, /font-family: "LabSyne_E"; font-weight: 700;[^}]*src: url\("fonts\/syne\/Syne-Bold\.ttf"\)/);
  assert.match(injected[2]!, /font-family: "LabSyne_H";[^}]*src: url\("data:font\/ttf;base64,AAEAAAAMgP8H"\)/);
  assert.deepEqual(faces.map((f) => [f.family, typeof f.source]), [["LabSyne_F", "string"], ["LabPlex_F", "string"], ["LabSyne_F2", "object"], ["LabPlex_F2", "object"]]);
  assert.deepEqual(faces[0]!.descriptors, { weight: "700" });
  assert.deepEqual(reads, ["fonts/syne/Syne-Bold.ttf", "fonts/ibmplexsansarabic/IBMPlexSansArabic-Regular.ttf"], "bytes read once per font");
  const fonts = r.fonts.variants as Record<string, { families: Record<string, { family: string; runtime?: { ok: boolean } }> }>;
  assert.deepEqual(Object.keys(fonts), FONT_VARIANTS.map((v) => v.id));
  assert.equal(fonts.F2!.families.plex!.family, "LabPlex_F2");
  assert.equal(fonts.F2!.families.plex!.runtime!.ok, true);
  assert.equal(fonts.A!.families.syne!.runtime, undefined, "static variants have no runtime step");
  const ws = r.whitespace.variants as Record<string, Record<string, unknown>>;
  assert.deepEqual(Object.keys(ws), WS_VARIANTS.map((v) => v.id));
  assert.equal(ws.W0!.control, true);
  // the summary adds up
  const total = Object.values(r.summary.by_section).reduce((n, s) => n + s.pass + s.fail + s.na, 0);
  assert.equal(r.summary.pass + r.summary.fail + r.summary.na, total);
  assert.equal(r.summary.by_section.buttons!.pass, 7 * 4);
  assert.equal(r.summary.by_section.buttons!.na, 4);
  assert.match(r.screenshots, /stays open/);
});

test("runCssLab buttons: a grey / unresolved background, var( left, a zero box or a wrong disabled opacity is not a match", async () => {
  const { dom } = fakeDom({
    styles: (sel) => {
      if (sel === "#lab-btn-A-primary") return { background: "#F0F0F0" };
      if (sel === "#lab-btn-A-danger") return { background: "var(--twn-error)" };
      if (sel === "#lab-btn-A-disabled") return { background: "#5400FB", opacity: "1" };
      if (sel === "#lab-btn-G-primary") return { "background-color": "rgb(84, 0, 251)" };
      return undefined;
    },
    rect: (sel) => (sel === "#lab-btn-B-primary" ? { x: 0, y: 0, width: 0, height: 0 } : undefined),
    missing: /lab-btn-C-primary/,
  });
  const r = await runCssLab(dom, fakeEnv().env, { layoutSettleMs: 0, fontSettleMs: 0 });
  const b = r.buttons as Record<string, { forms: Record<string, { computed_matches: boolean | null; no_var_left: boolean; present?: boolean }> }>;
  assert.equal(b.A!.forms.primary!.computed_matches, false);
  assert.equal(b.A!.forms.danger!.computed_matches, false);
  assert.equal(b.A!.forms.danger!.no_var_left, false);
  assert.equal(b.A!.forms.disabled!.computed_matches, false);
  assert.equal(b.G!.forms.primary!.computed_matches, true, "the longhand is read too");
  assert.equal(b.B!.forms.primary!.computed_matches, false, "no box");
  assert.equal(b.C!.forms.primary!.computed_matches, false);
  assert.equal((b.C!.forms.primary as { present: boolean }).present, false);
});

test("runCssLab svg: the 0.1.6 result (path fill black) fails; an <img> without a loaded image fails; a missing one fails", async () => {
  const { dom } = fakeDom({
    styles: (sel) => (/ path$/.test(sel) ? { fill: sel.includes("S1") ? "black" : "rgb(61, 214, 140)" } : sel.startsWith("#lab-svg-S1") ? { fill: "currentcolor", color: "#3DD68C" } : undefined),
    props: (sel, name) => (sel === `#${svgId("S6", "row")}` && name === "naturalWidth" ? 0 : sel.startsWith("#lab-svg-S5") && name === "naturalWidth" ? 16 : undefined),
    missing: new RegExp(svgId("S6", "block")),
  });
  const r = await runCssLab(dom, fakeEnv().env, { layoutSettleMs: 0, fontSettleMs: 0 });
  const v = r.svg.variants as Record<string, { contexts: Record<string, Record<string, unknown>> }>;
  assert.equal(v.S1!.contexts.chip!.verdict, false);
  assert.equal(v.S1!.contexts.chip!.svg_fill, "currentcolor");
  assert.equal(v.S1!.contexts.chip!.path_fill, "black");
  assert.equal(v.S1!.contexts.chip!.fill_matches_expected, false);
  assert.equal(v.S2!.contexts.row!.verdict, true);
  assert.equal(v.S6!.contexts.row!.verdict, false, "naturalWidth 0 = the bundled file did not load");
  assert.equal(v.S6!.contexts.block!.verdict, false);
  assert.equal(v.S5!.contexts.inline!.natural_width, 16);
  assert.equal(v.S5!.contexts.inline!.verdict, null);
  assert.match(r.svg.expected_color, /#3DD68C/);
});

test("runCssLab fonts: loaded = width differs from the fallback-only span; same width = not loaded; a blind method makes same-width undecided", async () => {
  const widths = (sanity: number) => (sel: string): Rect | undefined => {
    const w = sel.includes("-ref-") ? 100 : sel.includes("-sanity-") ? sanity : /lab-font-(A|D|F2)-/.test(sel) ? 131 : sel.startsWith("#lab-font-") ? 100 : undefined;
    return w === undefined ? undefined : { x: 0, y: 0, width: w, height: 20 };
  };
  const seeing = await runCssLab(fakeDom({ rect: widths(118) }).dom, fakeEnv().env, { layoutSettleMs: 0, fontSettleMs: 0 });
  const f = seeing.fonts.variants as Record<string, { families: Record<string, { loaded: boolean | null; width: number; reference_width: number }> }>;
  assert.equal(f.A!.families.syne!.loaded, true);
  assert.equal(f.D!.families.plex!.loaded, true);
  assert.equal(f.F2!.families.syne!.loaded, true);
  assert.equal(f.ctrl!.families.syne!.loaded, false);
  assert.equal(f.B!.families.plex!.loaded, false);
  assert.deepEqual([f.A!.families.syne!.width, f.A!.families.syne!.reference_width], [131, 100]);
  assert.equal(seeing.fonts.references.syne!.method_sees_change, true);
  assert.equal(seeing.fonts.reference_family, LAB_REF_FAMILY);
  const blind = await runCssLab(fakeDom({ rect: widths(100) }).dom, fakeEnv().env, { layoutSettleMs: 0, fontSettleMs: 0 });
  const g = blind.fonts.variants as typeof f;
  assert.equal(blind.fonts.references.syne!.method_sees_change, false);
  assert.equal(g.ctrl!.families.syne!.loaded, null, "same width but the method cannot see a font change: undecided");
  assert.equal(g.A!.families.syne!.loaded, true, "a different width still means it loaded");
});

test("runCssLab fonts: no bytes from the plugin folder is recorded on F2 / H (never thrown); the facts throwing is recorded", async () => {
  const { env, faces, injected } = fakeEnv({ noBytes: true, facts: () => { throw new Error("no document.fonts"); } });
  const r = await runCssLab(fakeDom().dom, env, { layoutSettleMs: 0, fontSettleMs: 0 });
  assert.deepEqual(r.facts, { error: "no document.fonts" });
  const f = r.fonts.variants as Record<string, { families: Record<string, { runtime?: Record<string, unknown> }> }>;
  assert.deepEqual(f.F2!.families.syne!.runtime, { ok: false, step: "read bytes", error: "fs plugin:/: no" });
  assert.equal(f.H!.families.plex!.runtime!.ok, false);
  assert.equal(faces.length, 2, "only F (url) reached FontFace");
  assert.equal(injected.length, 2, "only E reached a <style>");
});

test("runCssLab whitespace: the gap between label and count, in LTR and RTL; padding and a wider label count as space; W0 is the control", async () => {
  const at = (x: number, width: number): Rect => ({ x, y: 0, width, height: 16 });
  const { dom } = fakeDom({
    rect: (sel) => {
      const m = /^#lab-ws-(W\d)-(ltr|rtl)-(label|count)$/.exec(sel);
      if (!m) return undefined;
      const [, v, d, part] = m as unknown as [string, string, "ltr" | "rtl", "label" | "count"];
      // W9 keeps the space inside its label (white-space:pre): 4 px wider; W2's trailing space is dropped here
      const labelW = v === "W9" ? 64 : 60;
      const gap = v === "W1" || v === "W3" || v === "W5" || v === "W6" ? 4 : 0;
      if (d === "ltr") return part === "label" ? at(0, labelW) : at(labelW + gap, 10);
      return part === "count" ? at(0, 10) : at(10 + gap, labelW);
    },
    styles: (sel) => {
      if (/^#lab-ws-W7-ltr-count$/.test(sel)) return { "padding-left": "6px", "padding-right": "0px" };
      if (/^#lab-ws-W8-rtl-count$/.test(sel)) return { "padding-left": "0px", "padding-right": "6px" };
      return undefined;
    },
    props: (sel, name) => (name === "textContent" && sel === "#lab-ws-W1-ltr-row" ? "Needs you 3" : undefined),
  });
  const r = await runCssLab(dom, fakeEnv().env, { layoutSettleMs: 0, fontSettleMs: 0 });
  const w = r.whitespace.variants as Record<string, Record<string, Record<string, unknown>>>;
  assert.equal(w.W0!.ltr!.space_px, 0);
  assert.equal(w.W1!.ltr!.box_gap_px, 4);
  assert.equal(w.W1!.ltr!.space_visible, true);
  assert.equal(w.W1!.ltr!.row_text, '"Needs you 3"');
  assert.equal(w.W1!.rtl!.box_gap_px, 4);
  assert.equal(w.W1!.rtl!.space_visible, true);
  assert.equal(w.W2!.ltr!.space_visible, false, "the trailing space inside the span was dropped: no wider label, no gap");
  assert.equal(w.W9!.ltr!.label_extra_px_vs_control, 4);
  assert.equal(w.W9!.ltr!.space_visible, true);
  assert.equal(w.W7!.ltr!.count_padding_start_px, 6);
  assert.equal(w.W7!.ltr!.space_visible, true);
  assert.equal(w.W7!.rtl!.space_visible, false);
  assert.equal(w.W8!.rtl!.space_visible, true, "RTL: the start padding is padding-right");
  assert.equal(w.W4!.ltr!.space_visible, false);
  // W0 is not counted: 9 variants x 2 directions
  const t = r.summary.by_section.whitespace!;
  assert.equal(t.pass + t.fail + t.na, (WS_VARIANTS.length - 1) * 2);
});

// ---- sections + spike.ts wiring -----------------------------------------------------------------------------------

function goodStage(waits: number[] = []): UiStage {
  const styles: Record<string, Props> = {
    "#wnc-shadow-token": { boxShadow: "#9D6BFF 0px 0px 0px 2px" },
    "#wnc-shadow-literal": { boxShadow: "rgb(157, 107, 255) 0px 0px 0px 2px" },
    "#wnc-grad-hairline": { backgroundImage: "linear-gradient(90deg,#D95C9B,#5400FB)" },
    "#wnc-grad-fill": { backgroundImage: "linear-gradient(90deg,#D95C9B,#5400FB)" },
    "#wnc-grad-literal": { backgroundImage: "linear-gradient(90deg, rgb(217, 92, 155), rgb(84, 0, 251))" },
    "#wnc-svg-wrap svg path": { fill: "#3DD68C" },
    "#wnc-code-p bdi.kit-code": { display: "inline", backgroundColor: "#1E1E1E" },
  };
  let html = "";
  return {
    mount: (h) => void (html = h),
    query: (sel) => (html === "" ? null : sel),
    style: (el) => styleOf(styles[el as string] ?? {}),
    box: (el) => ({ width: (el as string).endsWith("-brand") ? 120 : (el as string).includes("-tnr-") ? 100 : 110, height: 16 }),
    rootStyle: () => styleOf({}),
    fonts: () => ({ present: false }),
    unmount: () => void (html = ""),
    wait: async (ms) => void waits.push(ms),
  };
}

test("css_lab sections: the UI probes run, the ecosystem probes are recorded n/a (not run)", async () => {
  const sections: Sections = { ui_probes: {}, eco_probes: {} };
  const steps: string[] = [];
  const eco = { uxp: {}, ppro: {}, fs: {}, home: null, now: () => T0, lifecycle: createLifecycle(() => T0) } as unknown as EcoCtx;
  await runPreSections(sections, { stage: goodStage(), fontSettleMs: 0, layoutSettleMs: 0 }, eco, (s) => void steps.push(s), { eco: false });
  assert.ok(Object.values(sections.ui_probes).every((r) => r.ok === true), JSON.stringify(sections.ui_probes).slice(0, 1500));
  for (const name of ["quit_restart_names", "loopback", "hide_show"]) {
    assert.equal(sections.eco_probes[name]!.ok, null);
    assert.match(String(sections.eco_probes[name]!.detail), /mode "css_lab"/);
  }
  assert.ok(ECO_PROBE_NAMES.includes("open_external"));
  assert.ok(!steps.some((s) => s.startsWith("Ecosystem probe")));
  assert.equal(steps.at(-1), "ui probes done");
});

test("spike.ts: css_lab opens the lab (stays open), measures it into `lab`, runs the UI probes only, needs no premierepro", () => {
  const spike = read("spike/src/spike.ts");
  assert.match(spike, /if \(mode === "css_lab"\) \{\s*guide\?\.hide\(\);\s*lab\?\.show\(\);/);
  assert.match(spike, /if \(mode !== "style_guide" && mode !== "css_lab"\) throw e;/);
  assert.match(spike, /labResults = await runCssLab\(realLabDom\(\$\("lab-host"\)\), realLabEnv\(document, fs, uxp\)\)/);
  assert.match(spike, /\.\.\.\(mode === "css_lab" \? \{ lab: labResults,/);
  assert.match(spike, /\{ eco: mode !== "css_lab" \}/);
  assert.match(spike, /\$\("lab-open"\)\.addEventListener\("click", \(\) => void runSpike\("css_lab"\)\)/);
  assert.match(spike, /"guide-open", "lab-open"\]\) \(\$\(id\) as HTMLButtonElement\)\.disabled = on/);
  // the lab is never closed by the run: nothing hides it after the measurement
  assert.doesNotMatch(spike.slice(spike.indexOf("labResults = await")), /lab\?\.hide\(\)/);
});

// ---- the 0.1.6 review's probe Importants --------------------------------------------------------------------------

const uiRun = (op: string, stage: UiStage, extra: Partial<UiCtx> = {}) => runProbe(UI_PROBES.find((p) => p.op === op)!, { stage, fontSettleMs: 0, ...extra } satisfies UiCtx);

test("ui probes wait for a layout pass after every mount (0.1.6 measured 0 x 0 right after mounting)", async () => {
  const waits: number[] = [];
  for (const p of UI_PROBES) await uiRun(p.op, goodStage(waits), { layoutSettleMs: 123 });
  // fonts: 1, svg: 1, box_shadow: 1, gradient: 1, kit_code: 2 (EN + AR)
  assert.equal(waits.filter((w) => w === 123).length, 6);
});

test("ui box_shadow / gradient / kit_code: ok needs resolved values (no var( left, the expected hex or rgb colour)", async () => {
  const stage = (styles: Record<string, Props>) => {
    const s = goodStage();
    return { ...s, style: (el: unknown) => styleOf(styles[el as string] ?? {}) } as UiStage;
  };
  const unresolved = stage({ "#wnc-shadow-token": { boxShadow: "var(--twn-focus)" }, "#wnc-shadow-literal": { boxShadow: "var(--twn-focus)" } });
  assert.equal((await uiRun("box_shadow", unresolved)).ok, false);
  const half = stage({ "#wnc-shadow-token": { boxShadow: "var(--twn-focus)" }, "#wnc-shadow-literal": { boxShadow: "#9D6BFF 0px 0px 0px 2px" } });
  assert.equal((await uiRun("box_shadow", half)).ok, null);
  const wrongColour = stage({ "#wnc-shadow-token": { boxShadow: "#000000 0px 0px 0px 2px" }, "#wnc-shadow-literal": { boxShadow: "#000000 0px 0px 0px 2px" } });
  assert.equal((await uiRun("box_shadow", wrongColour)).ok, false);
  const gradVar = { backgroundImage: "linear-gradient(90deg,var(--twn-accent),#5400FB)" };
  assert.equal((await uiRun("gradient", stage({ "#wnc-grad-hairline": gradVar, "#wnc-grad-fill": gradVar, "#wnc-grad-literal": gradVar }))).ok, false);
  const gradWrong = { backgroundImage: "linear-gradient(90deg,#000000,#5400FB)" };
  assert.equal((await uiRun("gradient", stage({ "#wnc-grad-hairline": gradWrong, "#wnc-grad-fill": gradWrong, "#wnc-grad-literal": gradWrong }))).ok, false);
  const codeVar = stage({ "#wnc-code-p bdi.kit-code": { display: "inline", backgroundColor: "var(--twn-surface-2)" } });
  assert.equal((await uiRun("kit_code", codeVar)).ok, false);
  const codeOther = stage({ "#wnc-code-p bdi.kit-code": { display: "inline", backgroundColor: "#333333" } });
  assert.equal((await uiRun("kit_code", codeOther)).ok, false);
  const good = await uiRun("kit_code", goodStage());
  assert.equal(good.ok, true);
  const d = good.detail as Record<string, Record<string, unknown>>;
  assert.equal(d.en!.background_matches_expected, true);
  assert.match(String(d.en!.paint_confirmed_by), /screenshot/);
});

test("ui svg: ok = a box AND the path's computed fill is #3DD68C; the 0.1.6 live values (currentcolor / black) fail", async () => {
  const live = { ...goodStage(), style: (el: unknown) => styleOf((el as string).endsWith("path") ? { fill: "black" } : { fill: "currentcolor", color: "#3DD68C" }) } as UiStage;
  const r = await uiRun("svg", live);
  assert.equal(r.ok, false);
  const d = r.detail as Record<string, unknown>;
  assert.equal(d.fill_matches_expected, false);
  assert.equal(d.box_ok, true);
  assert.match(String(d.paint_confirmed_by), /screenshot/);
  assert.equal((await uiRun("svg", goodStage())).ok, true);
});

test("ui fonts: the fallbacks are a nonexistent family and Times New Roman (0.1.6: monospace = serif in UXP); fallbacks_differ recorded", async () => {
  const r = await uiRun("fonts", goodStage());
  assert.equal(r.ok, true);
  const d = r.detail as { rule: string; families: Record<string, { fallbacks_differ: boolean; widths: Record<string, unknown> }> };
  assert.match(d.rule, /WncNoSuchFamily7f3a.*Times New Roman/);
  assert.deepEqual(Object.keys(d.families.syne!.widths), ["none", "tnr"]);
  assert.equal(d.families.syne!.fallbacks_differ, true);
});

// ---- lifecycleWriter makes its folder ------------------------------------------------------------------------------

test("lifecycleWriter: makes the spike folder before writing lifecycle.json (a fresh machine has none yet)", async () => {
  const fs = memFs();
  const write = lifecycleWriter(fs as never, DIR);
  const rec = createLifecycle(() => T0, write);
  rec.record("script.loaded");
  await new Promise((r) => setTimeout(r, 20));
  assert.ok(fs.dirs.has(DIR), "ensureDir made the folder");
  const body = JSON.parse(fs.files.get(`${DIR}/lifecycle.json`)!);
  assert.equal(body.spike, "0.1.9");
  assert.equal(body.events[0].event, "script.loaded");
});
