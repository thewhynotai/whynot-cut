// Spike 0.1.6: live UXP measurements of what the panel kit (adobe/panel-ui/styles/kit.css) relies on. Each probe mounts
// a small visible stage of kit markup, reads computed styles and boxes, and records what it saw; nothing is assumed.
// 0.1.7 (the 0.1.6 review + live run): every probe waits for layout after mounting (0.1.6 measured every box 0 x 0 right
// after the mount); "ok" needs RESOLVED values (no var( left, a real hex / rgb colour, the expected one where the kit
// fixes it); the fonts fallbacks have unlike metrics (0.1.6: monospace and serif measured the same width in UXP); svg and
// kit_code say that paint is only confirmed by a screenshot.
// Results go to the results file under `ui_probes`:
//   fonts        - does @font-face (fonts.css, bundled OFL files) load? computed font-family + the text width of a sample
//                  in Syne / Inter / IBM Plex Sans Arabic / IBM Plex Mono vs the same text in a fallback family
//   svg          - inline <svg> status icon: box > 0, computed fill / color (0.1.8: no fill attribute, the kit-ink-ok class)
//   box_shadow   - the focus ring (box-shadow: var(--twn-focus)) and a literal shadow: computed values
//   gradient     - the header hairline / progress fill (var(--twn-gradient)) and a literal gradient: computed values
//   kit_code     - the inline <bdi class="kit-code"> run inside a sentence: computed display / background / font / box
// The DOM is reached through UiStage so the tests can drive the probes with a fake; domStage() is the real one.
import { stringsFor } from "../../../panel-ui/src/i18n.ts";
import { statusIcon } from "../../../panel-ui/src/kit/icons.ts";
import { withCommands } from "../../../panel-ui/src/kit/html.ts";
import { colorsIn, isResolved, normColor } from "./css-lab.ts";
import type { ProbeDef } from "./runner.ts";

/** What the probes read from a computed style (a CSSStyleDeclaration, or a fake). */
export interface StyleLike {
  getPropertyValue(name: string): string;
  [prop: string]: unknown;
}

export interface Box {
  width: number;
  height: number;
}

/** The DOM surface the probes use. */
export interface UiStage {
  /** shows `html` in a fresh, visible stage (inside a .kit-root so kit.css applies), replacing what was there */
  mount(html: string, opts?: { rtl?: boolean }): void;
  /** the first element in the stage that matches */
  query(selector: string): unknown | null;
  style(el: unknown): StyleLike;
  box(el: unknown): Box;
  /** computed style of the document element (where tokens.css defines the --twn-* custom properties) */
  rootStyle(): StyleLike;
  /** document.fonts, when this runtime has it */
  fonts(): { present: boolean; check?: (font: string) => boolean; ready?: Promise<unknown> } ;
  unmount(): void;
  wait(ms: number): Promise<void>;
}

export interface UiCtx {
  stage: UiStage;
  /** how long to let lazily loaded fonts settle before the second measurement (ms) */
  fontSettleMs?: number;
  /** how long to let UXP lay a freshly mounted stage out before measuring boxes (ms; 0.1.6 measured 0 x 0 without) */
  layoutSettleMs?: number;
}

export const LAYOUT_SETTLE_MS = 300;

/** mount, then give UXP a layout pass before anything is measured */
async function mountAndSettle(ctx: UiCtx, html: string, opts?: { rtl?: boolean }): Promise<void> {
  ctx.stage.mount(html, opts);
  await ctx.stage.wait(ctx.layoutSettleMs ?? LAYOUT_SETTLE_MS);
}

/** Where paint is confirmed: computed values are what the runtime resolved, not what it drew. */
export const PAINT_BY_SCREENSHOT = "computed values only; paint is confirmed by a screenshot (style guide, CSS lab)";

const read = (s: StyleLike, prop: string, css: string): string => {
  const direct = s[prop];
  if (typeof direct === "string" && direct !== "") return direct;
  try {
    return s.getPropertyValue(css) ?? "";
  } catch {
    return "";
  }
};

const round = (n: number) => Math.round(n * 100) / 100;

// ---------------------------------------------------------------------------------------------- fonts

export interface FontSample {
  key: string;
  family: string;
  weight: number;
  text: string;
  rtl?: boolean;
}

/** One sample per bundled family, at a weight fonts.css ships. */
export const FONT_SAMPLES: readonly FontSample[] = [
  { key: "syne", family: "Syne", weight: 700, text: "WhyNot Cut Style Guide MWQ" },
  { key: "inter", family: "Inter", weight: 400, text: "Quick brown fox jumps 0123456789" },
  { key: "plex_arabic", family: "IBM Plex Sans Arabic", weight: 400, text: "مراجعة المونتاج قبل التصدير", rtl: true },
  { key: "plex_mono", family: "IBM Plex Mono", weight: 400, text: "00:00:12:04 C0239_prev.prproj" },
];

/** A family no machine has (0.1.7). */
export const NO_SUCH_FAMILY = "WncNoSuchFamily7f3a";
/** Two fallbacks with unlike metrics, so a font that loaded changes the width against both. 0.1.6 used the generic
 *  monospace and serif, and UXP measured them the SAME (both resolve to one default face): a unique nonexistent family
 *  (= the runtime default) and an installed proportional serif instead. */
export const FALLBACKS = [
  { key: "none", family: `"${NO_SUCH_FAMILY}"` },
  { key: "tnr", family: `"Times New Roman", "${NO_SUCH_FAMILY}"` },
] as const;
export type FallbackKey = (typeof FALLBACKS)[number]["key"];
const FONT_PX = 20;

export const fontId = (key: string, fallback: string, branded: boolean) => `wnc-font-${key}-${fallback}-${branded ? "brand" : "plain"}`;

export function fontStageHtml(): string {
  const rows: string[] = [];
  for (const s of FONT_SAMPLES) {
    for (const fb of FALLBACKS) {
      for (const branded of [true, false]) {
        const family = branded ? `"${s.family}", ${fb.family}` : fb.family;
        // a flex row with a non-growing child: the child's box is the text's own width
        rows.push(
          `<div style="display:flex; flex-direction:row; direction:${s.rtl ? "rtl" : "ltr"};">` +
            `<span id="${fontId(s.key, fb.key, branded)}" style="display:block; flex:0 0 auto; white-space:nowrap; font-family:${family.replace(/"/g, "&quot;")}; font-weight:${s.weight}; font-size:${FONT_PX}px;">${s.text}</span>` +
            `</div>`,
        );
      }
    }
  }
  return rows.join("");
}

interface FontMeasure {
  [fallback: string]: { brand_width: number; fallback_width: number; differs: boolean };
}

function measureFonts(stage: UiStage): Record<string, { computed_family: string; per_fallback: FontMeasure; fallbacks_differ: boolean }> {
  const out: Record<string, { computed_family: string; per_fallback: FontMeasure; fallbacks_differ: boolean }> = {};
  for (const s of FONT_SAMPLES) {
    const per: FontMeasure = {};
    let computed = "";
    for (const fb of FALLBACKS) {
      const brand = stage.query(`#${fontId(s.key, fb.key, true)}`);
      const plain = stage.query(`#${fontId(s.key, fb.key, false)}`);
      if (!brand || !plain) throw new Error(`font stage is missing the ${s.key} / ${fb.key} spans`);
      if (!computed) computed = read(stage.style(brand), "fontFamily", "font-family");
      const bw = round(stage.box(brand).width);
      const pw = round(stage.box(plain).width);
      per[fb.key] = { brand_width: bw, fallback_width: pw, differs: Math.abs(bw - pw) > 0.5 };
    }
    const widths = FALLBACKS.map((fb) => per[fb.key]!.fallback_width);
    out[s.key] = { computed_family: computed, per_fallback: per, fallbacks_differ: widths.some((w) => Math.abs(w - widths[0]!) > 0.5) };
  }
  return out;
}

/** loaded: the brand width differs from BOTH fallbacks; not loaded: from neither; anything else is inconclusive. */
export function fontVerdict(per: FontMeasure): boolean | null {
  const d = FALLBACKS.map((fb) => per[fb.key]?.differs);
  if (d.every((x) => x === true)) return true;
  if (d.every((x) => x === false)) return false;
  return null;
}

export const fontsProbe: ProbeDef<UiCtx> = {
  op: "fonts",
  timeoutMs: 15_000,
  run: async (ctx) => {
    const { stage, fontSettleMs = 1500 } = ctx;
    await mountAndSettle(ctx, fontStageHtml());
    try {
      const first = measureFonts(stage);
      const f = stage.fonts();
      // fonts may load on first use: give them time (document.fonts.ready when present), then measure again
      if (f.ready) await Promise.race([f.ready, stage.wait(fontSettleMs)]);
      await stage.wait(fontSettleMs);
      const settled = measureFonts(stage);
      const families: Record<string, unknown> = {};
      let loaded = 0;
      let notLoaded = 0;
      for (const s of FONT_SAMPLES) {
        const m = settled[s.key]!;
        const verdict = fontVerdict(m.per_fallback);
        if (verdict === true) loaded++;
        if (verdict === false) notLoaded++;
        let check: boolean | string | null = null;
        if (typeof f.check === "function") {
          try {
            check = f.check(`${s.weight} ${FONT_PX}px "${s.family}"`);
          } catch (e) {
            check = `threw: ${e instanceof Error ? e.message : String(e)}`;
          }
        }
        families[s.key] = {
          family: s.family,
          weight: s.weight,
          sample: s.text,
          font_size_px: FONT_PX,
          computed_family: m.computed_family,
          loaded: verdict,
          widths: m.per_fallback,
          fallbacks_differ: m.fallbacks_differ,
          widths_before_settle: first[s.key]!.per_fallback,
          document_fonts_check: check,
        };
      }
      const ok = loaded === FONT_SAMPLES.length ? true : notLoaded === FONT_SAMPLES.length ? false : null;
      return {
        ok,
        detail: {
          rule: `loaded = the brand-family span's width differs from the same text in BOTH fallbacks (${FALLBACKS.map((f) => f.family).join(" | ")}); not loaded = differs from neither; else inconclusive. fallbacks_differ false = the two fallbacks measured alike (a weaker test)`,
          loaded_count: loaded,
          not_loaded_count: notLoaded,
          document_fonts: f.present,
          settle_ms: fontSettleMs,
          families,
        },
      };
    } finally {
      stage.unmount();
    }
  },
};

// ---------------------------------------------------------------------------------------------- svg

const SVG_EXPECTED = "#3DD68C";

export const svgProbe: ProbeDef<UiCtx> = {
  op: "svg",
  run: async (ctx) => {
    const { stage } = ctx;
    const t = stringsFor("en");
    // the status icon in the ok colour, the way a toast / chip draws it (0.1.8: its kit-ink-ok class sets the CSS fill;
    // 0.1.7 drew it with fill="currentColor", which UXP does not paint)
    await mountAndSettle(ctx, `<div id="wnc-svg-wrap" style="display:flex; flex-direction:row; color:var(--twn-ok);">${statusIcon("ok", t)}</div>`);
    try {
      const svg = stage.query("#wnc-svg-wrap svg");
      if (!svg) throw new Error("the status icon <svg> is not in the DOM (inline svg markup dropped?)");
      const path = stage.query("#wnc-svg-wrap svg path");
      const s = stage.style(svg);
      const box = stage.box(svg);
      const wrap = stage.query("#wnc-svg-wrap");
      const pathFill = path ? read(stage.style(path), "fill", "fill") : null;
      const svgFill = read(s, "fill", "fill");
      // what the path paints with: its own computed fill (it inherits the svg's), else the svg's
      const painted = pathFill ?? svgFill;
      const fillMatches = normColor(painted) === normColor(SVG_EXPECTED);
      const boxOk = box.width > 0 && box.height > 0;
      const detail = {
        svg_box: { width: round(box.width), height: round(box.height) },
        svg_fill: svgFill,
        svg_color: read(s, "color", "color"),
        svg_display: read(s, "display", "display"),
        wrapper_color: wrap ? read(stage.style(wrap), "color", "color") : null,
        path_present: path !== null,
        path_box: path ? (({ width, height }) => ({ width: round(width), height: round(height) }))(stage.box(path)) : null,
        path_fill: pathFill,
        expected_color: "the --twn-ok token, #3DD68C = rgb(61, 214, 140)",
        fill_resolved: isResolved(painted) && normColor(painted) !== null,
        fill_matches_expected: fillMatches,
        box_ok: boxOk,
        rule: 'ok = a box > 0 AND the path\'s computed fill is the expected colour (0.1.6: path fill "black" = not ok)',
        paint_confirmed_by: PAINT_BY_SCREENSHOT,
      };
      return { ok: boxOk && fillMatches, detail };
    } finally {
      stage.unmount();
    }
  },
};

// ---------------------------------------------------------------------------------------------- box-shadow + gradient

/** A resolved shadow / colour value: no var( left in it and at least one real hex / rgb colour. */
const resolvedColourValue = (v: string) => isResolved(v) && colorsIn(v).length > 0;
const FOCUS_COLOUR = "#9d6bff";
const GRADIENT_COLOURS = ["#d95c9b", "#5400fb"];

export const boxShadowProbe: ProbeDef<UiCtx> = {
  op: "box_shadow",
  run: async (ctx) => {
    const { stage } = ctx;
    await mountAndSettle(
      ctx,
      `<div id="wnc-shadow-token" style="display:block; width:40px; height:20px; margin:4px; box-shadow:var(--twn-focus);"></div>` +
        `<div id="wnc-shadow-literal" style="display:block; width:40px; height:20px; margin:4px; box-shadow:0 0 0 2px #9D6BFF;"></div>`,
    );
    try {
      const token = stage.query("#wnc-shadow-token");
      const literal = stage.query("#wnc-shadow-literal");
      if (!token || !literal) throw new Error("box-shadow stage elements missing");
      const tv = read(stage.style(token), "boxShadow", "box-shadow");
      const lv = read(stage.style(literal), "boxShadow", "box-shadow");
      const rootVar = read(stage.rootStyle(), "--twn-focus", "--twn-focus").trim();
      // resolved AND the focus-ring colour (#9D6BFF) in it
      const good = (v: string) => resolvedColourValue(v) && colorsIn(v).includes(FOCUS_COLOUR);
      return {
        ok: good(tv) && good(lv) ? true : !good(tv) && !good(lv) ? false : null,
        detail: {
          via_token: tv,
          literal: lv,
          via_token_resolved: good(tv),
          literal_resolved: good(lv),
          rule: "ok = both computed shadows have no var( left and carry the focus colour #9D6BFF (hex or rgb)",
          root_custom_property_twn_focus: rootVar,
          kit_use: ".kit-focus:focus { box-shadow: var(--twn-focus) } (the focus ring)",
        },
      };
    } finally {
      stage.unmount();
    }
  },
};

export const gradientProbe: ProbeDef<UiCtx> = {
  op: "gradient",
  run: async (ctx) => {
    const { stage } = ctx;
    await mountAndSettle(
      ctx,
      `<div id="wnc-grad-hairline" class="kit-hairline"></div>` +
        `<div class="kit-track" style="display:flex; flex-direction:row; height:6px;"><div id="wnc-grad-fill" class="kit-fill" style="width:50%;"></div></div>` +
        `<div id="wnc-grad-literal" style="display:block; height:6px; margin-top:4px; background:linear-gradient(90deg,#D95C9B,#5400FB);"></div>`,
    );
    try {
      const out: Record<string, unknown> = {};
      let seen = 0;
      let total = 0;
      for (const [key, sel] of [["hairline (.kit-hairline)", "#wnc-grad-hairline"], ["progress fill (.kit-fill)", "#wnc-grad-fill"], ["literal", "#wnc-grad-literal"]] as const) {
        const el = stage.query(sel);
        total++;
        if (!el) {
          out[key] = { present: false };
          continue;
        }
        const s = stage.style(el);
        const image = read(s, "backgroundImage", "background-image");
        const colours = colorsIn(image);
        const resolved = isResolved(image) && /gradient/i.test(image) && colours.join(",") === GRADIENT_COLOURS.join(",");
        if (resolved) seen++;
        const b = stage.box(el);
        out[key] = {
          background_image: image,
          background: read(s, "background", "background"),
          background_color: read(s, "backgroundColor", "background-color"),
          colours,
          resolved,
          box: { width: round(b.width), height: round(b.height) },
        };
      }
      out.root_custom_property_twn_gradient = read(stage.rootStyle(), "--twn-gradient", "--twn-gradient").trim();
      out.root_custom_property_twn_bg = read(stage.rootStyle(), "--twn-bg", "--twn-bg").trim();
      out.rule = "ok = every background-image is a gradient with no var( left whose colours are #D95C9B then #5400FB (hex or rgb)";
      return { ok: seen === total ? true : seen === 0 ? false : null, detail: out };
    } finally {
      stage.unmount();
    }
  },
};

// ---------------------------------------------------------------------------------------------- kit-code bdi

export const KIT_CODE_SENTENCE = "Saved a copy as `C0239_prev_2026-10-13-1412.prproj` next to the project.";

export const kitCodeProbe: ProbeDef<UiCtx> = {
  op: "kit_code",
  run: async (ctx) => {
    const { stage } = ctx;
    const sentences = [
      { key: "en", rtl: false, text: KIT_CODE_SENTENCE },
      { key: "ar", rtl: true, text: "حُفظت نسخة باسم `C0239_prev_2026-10-13-1412.prproj` بجوار المشروع." },
    ];
    const out: Record<string, unknown> = {};
    let good = 0;
    for (const s of sentences) {
      await mountAndSettle(ctx, `<p id="wnc-code-p" class="kit-text">${withCommands(s.text)}</p>`, { rtl: s.rtl });
      try {
        const el = stage.query("#wnc-code-p bdi.kit-code");
        if (!el) {
          out[s.key] = { present: false };
          continue;
        }
        const st = stage.style(el);
        const b = stage.box(el);
        const p = stage.query("#wnc-code-p");
        const pb = p ? stage.box(p) : null;
        const display = read(st, "display", "display");
        const bg = read(st, "backgroundColor", "background-color");
        const rects = (el as { getClientRects?: () => { length: number } }).getClientRects?.().length ?? null;
        const bgMatches = isResolved(bg) && normColor(bg) === "#1e1e1e";
        if (display === "inline" && bgMatches) good++;
        out[s.key] = {
          present: true,
          display,
          background_color: bg,
          font_family: read(st, "fontFamily", "font-family"),
          font_size: read(st, "fontSize", "font-size"),
          padding_left: read(st, "paddingLeft", "padding-left"),
          border_radius: read(st, "borderTopLeftRadius", "border-top-left-radius") || read(st, "borderRadius", "border-radius"),
          direction: read(st, "direction", "direction"),
          unicode_bidi: read(st, "unicodeBidi", "unicode-bidi"),
          box: { width: round(b.width), height: round(b.height) },
          paragraph_box: pb ? { width: round(pb.width), height: round(pb.height) } : null,
          client_rects: rects,
          expected: "display inline; background the --twn-surface-2 token #1E1E1E = rgb(30, 30, 30); font IBM Plex Mono",
          background_matches_expected: bgMatches,
          paint_confirmed_by: PAINT_BY_SCREENSHOT,
        };
      } finally {
        stage.unmount();
      }
    }
    return { ok: good === sentences.length ? true : good === 0 ? false : null, detail: out };
  },
};

export const UI_PROBES: readonly ProbeDef<UiCtx>[] = [fontsProbe, svgProbe, boxShadowProbe, gradientProbe, kitCodeProbe];

// ---------------------------------------------------------------------------------------------- the real DOM

/** The real stage: a fixed-size .kit-root box appended to <body> (or `parent`), visible while a probe runs. */
export function domStage(doc: Document, getStyle: (el: Element) => CSSStyleDeclaration, parent?: HTMLElement): UiStage {
  let host: HTMLElement | null = null;
  return {
    mount(html, opts = {}) {
      this.unmount();
      host = doc.createElement("div");
      host.id = "wnc-ui-probe-stage";
      host.setAttribute("style", "display:flex; flex-direction:column; width:340px; height:auto; min-height:40px; margin:8px 0;");
      const rtl = opts.rtl === true;
      host.innerHTML = `<div class="kit-root ${rtl ? "kit-rtl" : "kit-ltr"}" dir="${rtl ? "rtl" : "ltr"}" lang="${rtl ? "ar" : "en"}" style="height:auto; min-width:0;"><div class="kit-scroll" style="height:auto;">${html}</div></div>`;
      (parent ?? doc.body).appendChild(host);
    },
    query(selector) {
      return host?.querySelector(selector) ?? null;
    },
    style(el) {
      return getStyle(el as Element) as unknown as StyleLike;
    },
    box(el) {
      const e = el as Element & { offsetWidth?: number; offsetHeight?: number };
      try {
        const r = e.getBoundingClientRect();
        if (r && (r.width || r.height)) return { width: r.width, height: r.height };
      } catch {
        // fall through to offset*
      }
      return { width: e.offsetWidth ?? 0, height: e.offsetHeight ?? 0 };
    },
    rootStyle() {
      return getStyle(doc.documentElement) as unknown as StyleLike;
    },
    fonts() {
      const f = (doc as unknown as { fonts?: { check?: (font: string) => boolean; ready?: Promise<unknown> } }).fonts;
      if (!f) return { present: false };
      return { present: true, ...(typeof f.check === "function" ? { check: (font: string) => f.check!.call(f, font) } : {}), ...(f.ready ? { ready: f.ready } : {}) };
    },
    unmount() {
      if (host?.parentNode) host.parentNode.removeChild(host);
      host = null;
    },
    wait: (ms) => new Promise((r) => setTimeout(r, ms)),
  };
}
