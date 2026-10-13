// Spike 0.1.7: the "CSS lab". The 0.1.6 style guide showed, live in Premiere 26.5.2 UXP, that <button class="kit-btn">
// paints as a grey native lens (background ignored), the .kit-glow ring paints large purple artifacts, inline SVG icons
// paint black (fill="currentColor" computes to "currentcolor", the path to "black"), @font-face does not load (Syne /
// IBM Plex Sans Arabic / IBM Plex Mono measure like the fallback), and the whitespace between two flex children
// disappears ("Needs you3"). The lab renders labelled variants of each next to each other, one row per variant, and
// records computed values and boxes for every one in `results.lab`, so ONE live run (plus 2-3 screenshots of the lab
// view at ~560 css px) decides every fix:
//   buttons    A-H  x  primary / danger / secondary (glass) / disabled
//   glow       the gradient ring: wrapper r999 (kit) / r16 / border-image / a 1 px gradient layer behind
//   svg        currentColor / fill attribute / CSS path fill / CSS svg fill / <img> data: URI / <img> bundled file,
//              each in a kit chip, inside a line of text, in a flex row and in a block
//   fonts      @font-face url forms (format() or not, plugin:/, ./, .woff), a runtime <style>, the FontFace API
//              (url and bytes) and a data: URI, for Syne and IBM Plex Sans Arabic, each under a unique family name
//   whitespace "label + count" in a flex row: literal space, &nbsp;, logical / physical margins and paddings, LTR + RTL
// Computed values are not paint: every section says what only a screenshot can confirm. Markup and measurement are
// pure over the LabDom / LabEnv interfaces, so the tests drive them with fakes; spike.ts gives the real DOM.
import { icon } from "../../../panel-ui/src/kit/icons.ts";
import { SPIKE_VERSION } from "./version.ts";

// ---------------------------------------------------------------------------------------------- colours

/** "#rrggbb" (opaque) or "#rrggbbaa", lower case; null when `v` is not a plain colour (empty, var(), currentcolor...). */
export function normColor(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const s = v.trim().toLowerCase();
  if (s === "") return null;
  const named: Record<string, string> = { black: "#000000", white: "#ffffff", transparent: "#00000000" };
  if (named[s]) return named[s]!;
  const hex = /^#([0-9a-f]{3,8})$/.exec(s);
  if (hex) {
    let h = hex[1]!;
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join("");
    if (h.length === 6) return `#${h}`;
    if (h.length === 8) return h.endsWith("ff") ? `#${h.slice(0, 6)}` : `#${h}`;
    return null;
  }
  const fn = /^rgba?\(\s*([^)]*)\)$/.exec(s);
  if (!fn) return null;
  const parts = fn[1]!.split(/[\s,/]+/).filter(Boolean);
  if (parts.length !== 3 && parts.length !== 4) return null;
  const chan = (p: string) => (p.endsWith("%") ? (parseFloat(p) * 255) / 100 : parseFloat(p));
  const rgb = parts.slice(0, 3).map(chan);
  if (rgb.some((n) => !Number.isFinite(n))) return null;
  const to2 = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
  let out = `#${rgb.map(to2).join("")}`;
  if (parts.length === 4) {
    const a = parts[3]!.endsWith("%") ? parseFloat(parts[3]!) / 100 : parseFloat(parts[3]!);
    if (!Number.isFinite(a)) return null;
    if (a < 1) out += to2(a * 255);
  }
  return out;
}

/** Every plain colour inside a value (a gradient, a shadow, a background shorthand), normalised. */
export function colorsIn(v: unknown): string[] {
  if (typeof v !== "string") return [];
  return [...v.matchAll(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g)].map((m) => normColor(m[0])).filter((c): c is string => c !== null);
}

/** A computed value the runtime actually resolved: not empty, not "none", no var( left in it. */
export const isResolved = (v: unknown): boolean => typeof v === "string" && v.trim() !== "" && v.trim() !== "none" && !/var\(/i.test(v);

// ---------------------------------------------------------------------------------------------- DOM surface

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface StyleLike {
  getPropertyValue(name: string): string;
  [prop: string]: unknown;
}

/** What the lab reads from the rendered lab view. */
export interface LabDom {
  /** the first element in the lab view that matches */
  query(selector: string): unknown | null;
  style(el: unknown): StyleLike;
  rect(el: unknown): Rect;
  /** a plain property of the element (tagName, complete, naturalWidth, textContent) */
  prop(el: unknown, name: string): unknown;
  /** the lab host's width in css px (what the screenshots show) */
  hostWidth(): number | null;
  wait(ms: number): Promise<void>;
}

export interface StepResult {
  ok: boolean;
  error?: string;
  [k: string]: unknown;
}

/** The runtime font paths and the environment facts (spike.ts: the real document / FontFace / plugin folder). */
export interface LabEnv {
  /** appends a <style> with `css` to the document */
  injectStyle(css: string): StepResult;
  /** new FontFace(family, source, descriptors) -> load() -> document.fonts.add() */
  loadFontFace(family: string, source: string | ArrayBuffer, descriptors: Record<string, string>): Promise<StepResult>;
  /** the bytes of a bundled file (fs "plugin:/<rel>", else uxp.storage getPluginFolder) */
  readPluginBytes(rel: string): Promise<{ bytes?: ArrayBuffer; via?: string; error?: string }>;
  /** typeof FontFace, document.fonts, customElements, sp-button: facts only */
  facts(): Record<string, unknown>;
}

// ---------------------------------------------------------------------------------------------- markup helpers

const escAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const escText = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const row = (id: string, tag: string, desc: string, body: string, extra = "") =>
  `<div class="lab-row${extra}" id="${id}"><span class="lab-tag">${escText(tag)}</span><span class="lab-desc">${escText(desc)}</span>${body}</div>`;
const section = (id: string, title: string, note: string) => `<div class="lab-sec" id="lab-sec-${id}"><span class="lab-sec-title">${escText(title)}</span><span class="lab-sec-note">${escText(note)}</span></div>`;

// ---------------------------------------------------------------------------------------------- 1. buttons

export type ButtonForm = "primary" | "danger" | "secondary" | "disabled";
export const BUTTON_FORMS: readonly { key: ButtonForm; bg: "primary" | "danger" | "glass"; text: string; expect: string; disabled?: boolean }[] = [
  { key: "primary", bg: "primary", text: "Approve", expect: "#5400fb" },
  { key: "danger", bg: "danger", text: "Rebuild", expect: "#ff5c5c" },
  { key: "secondary", bg: "glass", text: "Preview", expect: "#ffffff14" },
  { key: "disabled", bg: "primary", text: "Export", expect: "#5400fb", disabled: true },
];

export interface ButtonVariant {
  id: "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H";
  desc: string;
  kind: "button" | "div" | "sp-button";
  /** layout + shape classes (lab.css) */
  cls: string;
  /** the colour classes use background-color (longhand) instead of the background shorthand */
  longhand?: boolean;
}

/** A is the kit's own form (.kit-btn: <button>, display:flex, radius 999); B, C, G and H change ONE thing from A. */
export const BUTTON_VARIANTS: readonly ButtonVariant[] = [
  { id: "A", desc: "button, flex, r999 (= .kit-btn)", kind: "button", cls: "lab-b lab-flex lab-r999" },
  { id: "B", desc: "button, inline-block, r999", kind: "button", cls: "lab-b lab-ib lab-r999" },
  { id: "C", desc: "button, flex, r16 (half the height)", kind: "button", cls: "lab-b lab-flex lab-r16" },
  { id: "D", desc: "button, inline-block, r16", kind: "button", cls: "lab-b lab-ib lab-r16" },
  { id: "E", desc: "div role=button tabindex=0, flex, r16", kind: "div", cls: "lab-b lab-flex lab-r16" },
  { id: "F", desc: "sp-button (UXP Spectrum widget)", kind: "sp-button", cls: "" },
  { id: "G", desc: "A + background-color longhand", kind: "button", cls: "lab-b lab-flex lab-r999", longhand: true },
  { id: "H", desc: "A + appearance:none", kind: "button", cls: "lab-b lab-flex lab-r999 lab-noapp" },
];

export const buttonId = (v: string, form: ButtonForm) => `lab-btn-${v}-${form}`;
const SP_VARIANT: Record<ButtonForm, string> = { primary: "cta", danger: "warning", secondary: "secondary", disabled: "cta" };

function buttonHtml(v: ButtonVariant, f: (typeof BUTTON_FORMS)[number]): string {
  const id = buttonId(v.id, f.key);
  if (v.kind === "sp-button") return `<sp-button id="${id}" variant="${SP_VARIANT[f.key]}"${f.disabled ? " disabled" : ""}>${f.text}</sp-button>`;
  const color = `${v.longhand ? "lab-bgc" : "lab-bg"}-${f.bg}`;
  const cls = `${v.cls} ${color}${f.disabled ? " lab-off" : ""}`;
  if (v.kind === "div") return `<div id="${id}" class="${cls}" role="button" tabindex="0"${f.disabled ? ' aria-disabled="true"' : ""}>${f.text}</div>`;
  return `<button id="${id}" type="button" class="${cls}"${f.disabled ? " disabled" : ""}>${f.text}</button>`;
}

// ---------------------------------------------------------------------------------------------- 2. glow

export interface GlowVariant {
  id: "GA" | "GB" | "GC" | "GD";
  desc: string;
}
export const GLOW_VARIANTS: readonly GlowVariant[] = [
  { id: "GA", desc: "wrapper r999, 1 px padding, gradient background (= .kit-glow)" },
  { id: "GB", desc: "wrapper r16, 1 px padding; button r15" },
  { id: "GC", desc: "no wrapper: border-image gradient on the button" },
  { id: "GD", desc: "a 1 px gradient layer behind (position absolute), r16" },
];
export const GLOW_INNER = ["button", "div"] as const;
export type GlowInner = (typeof GLOW_INNER)[number];
export const glowId = (v: string, inner: GlowInner, part: "wrap" | "btn" | "layer") => `lab-glow-${v}-${inner}-${part}`;

function glowHtml(v: GlowVariant, inner: GlowInner): string {
  const tag = inner === "button" ? "button" : "div";
  const attrs = inner === "button" ? ' type="button"' : ' role="button" tabindex="0"';
  const btn = (cls: string) => `<${tag} id="${glowId(v.id, inner, "btn")}"${attrs} class="lab-b lab-flex ${cls} lab-bg-primary">Approve</${tag}>`;
  switch (v.id) {
    case "GA":
      return `<div id="${glowId(v.id, inner, "wrap")}" class="lab-glow lab-r999">${btn("lab-r999 lab-grow")}</div>`;
    case "GB":
      return `<div id="${glowId(v.id, inner, "wrap")}" class="lab-glow lab-r16">${btn("lab-r15 lab-grow")}</div>`;
    case "GC":
      return `<div id="${glowId(v.id, inner, "wrap")}" class="lab-glow-none">${btn("lab-r16 lab-bimg")}</div>`;
    case "GD":
      return `<div id="${glowId(v.id, inner, "wrap")}" class="lab-glow-abs lab-r16"><div id="${glowId(v.id, inner, "layer")}" class="lab-glow-layer lab-r16"></div>${btn("lab-r15 lab-grow lab-glow-top")}</div>`;
  }
}

// ---------------------------------------------------------------------------------------------- 3. svg

/** The bundled lab icon (spike/lab/icons/ok.svg, published at lab/icons/ok.svg) is this file. */
export const OK_ICON_PATH = "M8 1a7 7 0 1 0 0 14A7 7 0 1 0 8 1z M4.5 8.2l1.1-1.1 1.5 1.5 3.3-3.3 1.1 1.1-4.4 4.4z";
export const OK_HEX = "#3DD68C";
export const okSvgFile = (): string =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16" fill="${OK_HEX}"><path fill-rule="evenodd" d="${OK_ICON_PATH}"/></svg>\n`;
export const OK_IMG_FILE = "lab/icons/ok.svg";

export type SvgContext = "chip" | "inline" | "row" | "block";
export const SVG_CONTEXTS: readonly SvgContext[] = ["chip", "inline", "row", "block"];
export interface SvgVariant {
  id: "S1" | "S2" | "S3" | "S4" | "S5" | "S6";
  desc: string;
  img: boolean;
}
export const SVG_VARIANTS: readonly SvgVariant[] = [
  { id: "S1", desc: 'fill="currentColor" (= kit icon)', img: false },
  { id: "S2", desc: `fill="${OK_HEX}" attribute`, img: false },
  { id: "S3", desc: "CSS .x path { fill: var(--twn-ok) }", img: false },
  { id: "S4", desc: "CSS fill on the svg element", img: false },
  { id: "S5", desc: '<img src="data:image/svg+xml;utf8,...">', img: true },
  { id: "S6", desc: `<img src="${OK_IMG_FILE}"> (bundled)`, img: true },
];
export const svgId = (v: string, ctx: SvgContext) => `lab-svg-${v}-${ctx}`;

function svgMarkup(v: SvgVariant, ctx: SvgContext): string {
  const id = svgId(v.id, ctx);
  // inside a line of text the icon is inline; elsewhere it is the kit's block icon
  const size = ctx === "inline" ? "lab-icon-inline" : "kit-icon";
  if (v.id === "S5") return `<img id="${id}" class="lab-img ${ctx === "inline" ? "lab-img-inline" : ""}" alt="" src="data:image/svg+xml;utf8,${encodeURIComponent(okSvgFile().trim())}" />`;
  if (v.id === "S6") return `<img id="${id}" class="lab-img ${ctx === "inline" ? "lab-img-inline" : ""}" alt="" src="${OK_IMG_FILE}" />`;
  // S1 is the kit's own markup (adobe/panel-ui/src/kit/icons.ts), with the lab's id and size class
  const kit = String(icon("ok")).replace(/^<svg class="kit-icon /, `<svg id="${id}" class="${size} `);
  if (v.id === "S1") return kit;
  if (v.id === "S2") return kit.replace('fill="currentColor"', `fill="${OK_HEX}"`);
  if (v.id === "S3") return kit.replace(' fill="currentColor"', "").replace(`class="${size} `, `class="${size} lab-svg-path `);
  return kit.replace(' fill="currentColor"', "").replace(`class="${size} `, `class="${size} lab-svg-self `);
}

function svgCell(v: SvgVariant, ctx: SvgContext): string {
  const m = svgMarkup(v, ctx);
  switch (ctx) {
    case "chip":
      return `<span class="kit-chip kit-chip-ok lab-cell">${m}<span class="kit-chip-text">chip</span></span>`;
    case "inline":
      return `<p class="lab-inline lab-cell lab-ok">text ${m} text</p>`;
    case "row":
      return `<div class="lab-svgrow lab-cell lab-ok">${m}<span class="lab-svgrow-text">row</span></div>`;
    case "block":
      return `<div class="lab-svgblock lab-cell lab-ok">${m}</div>`;
  }
}

// ---------------------------------------------------------------------------------------------- 4. fonts

/** A family name no machine has: what a span falls back to when the lab family did not load (the 0.1.6 review: monospace
 *  and serif measured the SAME in UXP, so a generic fallback cannot tell fonts apart). */
export const LAB_REF_FAMILY = "WncLabNoSuchFamily7f3a";
/** An installed family with metrics unlike the default: proves the width method sees a font change at all. */
export const LAB_SANITY_FAMILY = "Times New Roman";
export const LAB_FONT_PX = 18;

export interface LabFont {
  key: "syne" | "plex";
  name: "Syne" | "Plex";
  ttf: string;
  woff: string;
  weight: number;
  text: string;
  rtl: boolean;
}
export const LAB_FONTS: readonly LabFont[] = [
  { key: "syne", name: "Syne", ttf: "fonts/syne/Syne-Bold.ttf", woff: "lab/fonts/syne/Syne-Bold.woff", weight: 700, text: "WhyNot Cut MWQ", rtl: false },
  {
    key: "plex",
    name: "Plex",
    ttf: "fonts/ibmplexsansarabic/IBMPlexSansArabic-Regular.ttf",
    woff: "lab/fonts/ibmplexsansarabic/IBMPlexSansArabic-Regular.woff",
    weight: 400,
    text: "مراجعة المونتاج",
    rtl: true,
  },
];

export type FontHow = "static" | "inject" | "fontface_url" | "fontface_bytes" | "data_uri";
export interface FontVariant {
  id: "ctrl" | "A" | "B" | "B2" | "C" | "D" | "E" | "F" | "F2" | "H";
  desc: string;
  how: FontHow;
  /** the @font-face src (static / inject) or the FontFace source (fontface_url) */
  src?: (f: LabFont) => string;
}
export const FONT_VARIANTS: readonly FontVariant[] = [
  { id: "ctrl", desc: 'lab.css url("fonts/..ttf") format("truetype") (= fonts.css)', how: "static", src: (f) => `url("${f.ttf}") format("truetype")` },
  { id: "A", desc: 'lab.css url("fonts/..ttf"), no format()', how: "static", src: (f) => `url("${f.ttf}")` },
  { id: "B", desc: 'lab.css url("plugin:/fonts/..ttf")', how: "static", src: (f) => `url("plugin:/${f.ttf}")` },
  { id: "B2", desc: 'lab.css plugin:/ + format("truetype")', how: "static", src: (f) => `url("plugin:/${f.ttf}") format("truetype")` },
  { id: "C", desc: 'lab.css url("./fonts/..ttf")', how: "static", src: (f) => `url("./${f.ttf}")` },
  { id: "D", desc: 'lab.css url("lab/fonts/..woff")', how: "static", src: (f) => `url("${f.woff}")` },
  { id: "E", desc: 'runtime <style>, url("fonts/..ttf")', how: "inject", src: (f) => `url("${f.ttf}")` },
  { id: "F", desc: 'FontFace API, url("fonts/..ttf")', how: "fontface_url", src: (f) => `url("${f.ttf}")` },
  { id: "F2", desc: "FontFace API, bytes read from the plugin folder", how: "fontface_bytes" },
  { id: "H", desc: "runtime <style>, data: URI of the bytes", how: "data_uri" },
];

export const labFamily = (f: LabFont, v: FontVariant) => `Lab${f.name}_${v.id}`;
export const fontSpanId = (v: string, f: string) => `lab-font-${v}-${f}`;
export const fontRefId = (kind: "ref" | "sanity", f: string) => `lab-font-${kind}-${f}`;

const fontFace = (family: string, weight: number, src: string) => `@font-face { font-family: "${family}"; font-weight: ${weight}; font-style: normal; src: ${src}; }`;

/** The static @font-face rules lab.css carries (test: lab.css contains exactly these lines). */
export function staticFontFaceCss(): string {
  const out: string[] = [];
  for (const v of FONT_VARIANTS.filter((x) => x.how === "static")) for (const f of LAB_FONTS) out.push(fontFace(labFamily(f, v), f.weight, v.src!(f)));
  return out.join("\n");
}

const fontStyle = (families: string, f: LabFont) =>
  `font-family:${escAttr(families)}; font-weight:${f.weight}; font-size:${LAB_FONT_PX}px; direction:${f.rtl ? "rtl" : "ltr"};`;
const fontSpan = (id: string, families: string, f: LabFont) => `<span id="${id}" class="lab-fspan" style="${fontStyle(families, f)}">${escText(f.text)}</span>`;

// ---------------------------------------------------------------------------------------------- 5. whitespace

export interface WsVariant {
  id: "W0" | "W1" | "W2" | "W3" | "W4" | "W5" | "W6" | "W7" | "W8" | "W9";
  desc: string;
  /** label, count -> the two spans (ids added by wsHtml) */
  join: "none" | "space_between" | "space_inside" | "nbsp_between" | "nbsp_inside";
  countCls?: string;
  labelCls?: string;
  control?: boolean;
}
export const WS_VARIANTS: readonly WsVariant[] = [
  { id: "W0", desc: "no space (control)", join: "none", control: true },
  { id: "W1", desc: "literal space between the spans", join: "space_between" },
  { id: "W2", desc: "space inside the label span", join: "space_inside" },
  { id: "W3", desc: "&nbsp; between the spans", join: "nbsp_between" },
  { id: "W4", desc: "&nbsp; inside the label span", join: "nbsp_inside" },
  { id: "W5", desc: "count margin-inline-start 6px", join: "none", countCls: "lab-ws-mis" },
  { id: "W6", desc: "count margin-left / -right 6px by .lab-rtl", join: "none", countCls: "lab-ws-mlr" },
  { id: "W7", desc: "count padding-inline-start 6px", join: "none", countCls: "lab-ws-pis" },
  { id: "W8", desc: "count padding-left / -right 6px by .lab-rtl", join: "none", countCls: "lab-ws-plr" },
  { id: "W9", desc: "space inside the label span + white-space:pre", join: "space_inside", labelCls: "lab-ws-pre" },
];
export const WS_DIRS = ["ltr", "rtl"] as const;
export type WsDir = (typeof WS_DIRS)[number];
const WS_TEXT: Record<WsDir, string> = { ltr: "Needs you", rtl: "مطلوب منك" };
export const wsId = (v: string, dir: WsDir, part: "row" | "label" | "count") => `lab-ws-${v}-${dir}-${part}`;

function wsHtml(v: WsVariant, dir: WsDir): string {
  const label = escText(WS_TEXT[dir]);
  const l = (inner: string) => `<span id="${wsId(v.id, dir, "label")}" class="lab-ws-label${v.labelCls ? ` ${v.labelCls}` : ""}">${inner}</span>`;
  const c = `<span id="${wsId(v.id, dir, "count")}" class="lab-ws-count${v.countCls ? ` ${v.countCls}` : ""}">3</span>`;
  const body =
    v.join === "space_between" ? `${l(label)} ${c}`
    : v.join === "space_inside" ? `${l(`${label} `)}${c}`
    : v.join === "nbsp_between" ? `${l(label)}&nbsp;${c}`
    : v.join === "nbsp_inside" ? `${l(`${label}&nbsp;`)}${c}`
    : `${l(label)}${c}`;
  return `<div id="${wsId(v.id, dir, "row")}" class="lab-ws lab-${dir}" dir="${dir}">${body}</div>`;
}

// ---------------------------------------------------------------------------------------------- the page

/** The lab view's markup: five sections, one labelled flex row per variant (compact, so 2-3 screenshots at ~560 px). */
export function labHtml(): string {
  const parts: string[] = [];
  parts.push(`<div class="kit-root kit-ltr lab-root" dir="ltr" lang="en">`);
  parts.push(section("buttons", "1 Buttons", "primary / danger / secondary / disabled; A = .kit-btn"));
  for (const v of BUTTON_VARIANTS) parts.push(row(`lab-row-btn-${v.id}`, v.id, v.desc, `<div class="lab-items">${BUTTON_FORMS.map((f) => buttonHtml(v, f)).join("")}</div>`));
  parts.push(section("glow", "2 Glow", "gradient ring round a primary; <button> then div role=button"));
  for (const v of GLOW_VARIANTS) parts.push(row(`lab-row-glow-${v.id}`, v.id, v.desc, `<div class="lab-items">${GLOW_INNER.map((i) => `<div class="lab-glowcell">${glowHtml(v, i)}</div>`).join("")}</div>`));
  parts.push(section("svg", "3 SVG", "chip / inline text / flex row / block; green = right"));
  for (const v of SVG_VARIANTS) parts.push(row(`lab-row-svg-${v.id}`, v.id, v.desc, `<div class="lab-items">${SVG_CONTEXTS.map((c) => svgCell(v, c)).join("")}</div>`));
  parts.push(section("fonts", "4 @font-face", `Syne 700 / IBM Plex Sans Arabic 400, fallback "${LAB_REF_FAMILY}"`));
  const refs = LAB_FONTS.map((f) => fontSpan(fontRefId("ref", f.key), `"${LAB_REF_FAMILY}"`, f)).join("");
  parts.push(row("lab-row-font-ref", "ref", "fallback only (what not-loaded looks like)", `<div class="lab-items">${refs}</div>`));
  const sanity = LAB_FONTS.map((f) => fontSpan(fontRefId("sanity", f.key), `"${LAB_SANITY_FAMILY}", "${LAB_REF_FAMILY}"`, f)).join("");
  parts.push(row("lab-row-font-sanity", "tnr", `${LAB_SANITY_FAMILY} (method check: must differ from ref)`, `<div class="lab-items">${sanity}</div>`));
  for (const v of FONT_VARIANTS) {
    const spans = LAB_FONTS.map((f) => fontSpan(fontSpanId(v.id, f.key), `"${labFamily(f, v)}", "${LAB_REF_FAMILY}"`, f)).join("");
    parts.push(row(`lab-row-font-${v.id}`, v.id, v.desc, `<div class="lab-items">${spans}</div>`));
  }
  parts.push(section("whitespace", "5 Flex whitespace", "label + count; LTR then RTL"));
  for (const v of WS_VARIANTS) parts.push(row(`lab-row-ws-${v.id}`, v.id, v.desc, `<div class="lab-items">${WS_DIRS.map((d) => wsHtml(v, d)).join("")}</div>`));
  parts.push(`<div class="lab-end" id="lab-end">end of lab - spike ${SPIKE_VERSION}</div>`);
  parts.push(`</div>`);
  return parts.join("");
}

// ---------------------------------------------------------------------------------------------- measuring

const r2 = (n: unknown) => (typeof n === "number" && Number.isFinite(n) ? Math.round(n * 100) / 100 : 0);

function read(s: StyleLike, css: string): string {
  const camel = css.replace(/^-webkit-/, "webkit-").replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase());
  for (const key of [camel, css]) {
    const v = s[key];
    if (typeof v === "string" && v !== "") return v;
  }
  try {
    return s.getPropertyValue(css) ?? "";
  } catch {
    return "";
  }
}

export interface LabEl {
  present: boolean;
  tag?: string | null;
  rect?: Rect;
  style?: Record<string, string>;
}

const BUTTON_PROPS = [
  "display",
  "background",
  "background-color",
  "background-image",
  "border-top-left-radius",
  "border-top-right-radius",
  "border-bottom-left-radius",
  "border-radius",
  "border-top-width",
  "border-top-style",
  "border-top-color",
  "border-image-source",
  "color",
  "opacity",
  "appearance",
  "-webkit-appearance",
  "padding-top",
  "padding-left",
  "min-height",
  "position",
] as const;
const SVG_PROPS = ["display", "fill", "color", "width", "height", "vertical-align"] as const;
const WS_PROPS = ["display", "margin-left", "margin-right", "padding-left", "padding-right", "white-space", "direction"] as const;
const FONT_PROPS = ["font-family", "font-weight", "font-size"] as const;

function measure(dom: LabDom, selector: string, props: readonly string[]): LabEl {
  const el = dom.query(selector);
  if (!el) return { present: false };
  const s = dom.style(el);
  const style: Record<string, string> = {};
  for (const p of props) style[p] = read(s, p);
  const r = dom.rect(el);
  const tag = dom.prop(el, "tagName");
  return { present: true, tag: typeof tag === "string" ? tag.toLowerCase() : null, rect: { x: r2(r.x), y: r2(r.y), width: r2(r.width), height: r2(r.height) }, style };
}

const px = (v: string | undefined) => {
  const n = parseFloat(v ?? "");
  return Number.isFinite(n) ? n : 0;
};
const hasBox = (e: LabEl) => !!e.rect && e.rect.width > 0 && e.rect.height > 0;

/** The background colour a button computed to: the longhand, else the colour inside the shorthand. */
function backgroundOf(e: LabEl): string | null {
  const st = e.style ?? {};
  const own = st["background-color"] ?? "";
  if (isResolved(own)) return normColor(own);
  const fromShorthand = colorsIn(st.background);
  return fromShorthand[0] ?? null;
}

// ---- verdict bookkeeping: true = pass, false = fail, null = only a screenshot decides

interface Tally {
  pass: number;
  fail: number;
  na: number;
}
const tally = (): Tally => ({ pass: 0, fail: 0, na: 0 });
const count = (t: Tally, v: boolean | null) => void (v === true ? t.pass++ : v === false ? t.fail++ : t.na++);

export const PAINT_NOTE = "computed values only: whether it PAINTS that way is decided by the screenshot of this lab row";

function measureButtons(dom: LabDom, t: Tally) {
  const out: Record<string, unknown> = {};
  for (const v of BUTTON_VARIANTS) {
    const forms: Record<string, unknown> = {};
    for (const f of BUTTON_FORMS) {
      const e = measure(dom, `#${buttonId(v.id, f.key)}`, BUTTON_PROPS);
      const bg = e.present ? backgroundOf(e) : null;
      const resolved = e.present && !/var\(/i.test(JSON.stringify(e.style ?? {}));
      let computed: boolean | null = null;
      if (v.kind !== "sp-button" && e.present) {
        computed = resolved && bg === f.expect && hasBox(e);
        if (computed && f.disabled) computed = Math.abs(px(e.style?.opacity) - 0.45) < 0.02;
      } else if (!e.present) computed = false;
      count(t, computed);
      forms[f.key] = { ...e, expected_background: f.expect, resolved_background: bg, no_var_left: resolved, computed_matches: computed };
    }
    out[v.id] = { desc: v.desc, kind: v.kind, classes: v.cls, longhand: v.longhand === true, forms, paint: PAINT_NOTE };
  }
  return out;
}

function measureGlow(dom: LabDom, t: Tally) {
  const out: Record<string, unknown> = {};
  for (const v of GLOW_VARIANTS) {
    const inner: Record<string, unknown> = {};
    for (const i of GLOW_INNER) {
      const wrap = measure(dom, `#${glowId(v.id, i, "wrap")}`, BUTTON_PROPS);
      const btn = measure(dom, `#${glowId(v.id, i, "btn")}`, BUTTON_PROPS);
      const layer = v.id === "GD" ? measure(dom, `#${glowId(v.id, i, "layer")}`, BUTTON_PROPS) : null;
      // where the gradient lives for this variant
      const holder = v.id === "GC" ? btn.style?.["border-image-source"] : v.id === "GD" ? layer?.style?.["background-image"] : wrap.style?.["background-image"];
      const gradient = isResolved(holder) && /gradient/i.test(holder ?? "") && colorsIn(holder).length >= 2;
      const computed = wrap.present && btn.present ? gradient && hasBox(btn) : false;
      count(t, computed);
      inner[i] = { wrapper: wrap, button: btn, ...(layer ? { layer } : {}), gradient_value: holder ?? null, computed_gradient_resolved: computed };
    }
    out[v.id] = { desc: v.desc, inner, paint: `${PAINT_NOTE} (look for the 1 px ring and NO artifacts around it)` };
  }
  return out;
}

function measureSvg(dom: LabDom, t: Tally) {
  const expected = normColor(OK_HEX)!;
  const out: Record<string, unknown> = {};
  for (const v of SVG_VARIANTS) {
    const contexts: Record<string, unknown> = {};
    for (const c of SVG_CONTEXTS) {
      const sel = `#${svgId(v.id, c)}`;
      const e = measure(dom, sel, SVG_PROPS);
      if (v.img) {
        const el = dom.query(sel);
        const complete = el ? dom.prop(el, "complete") : null;
        const natural = el ? dom.prop(el, "naturalWidth") : null;
        const loaded = typeof natural === "number" ? natural > 0 : typeof complete === "boolean" ? complete : null;
        const verdict = !e.present ? false : !hasBox(e) ? false : loaded === false ? false : null;
        count(t, verdict);
        contexts[c] = { ...e, complete: complete ?? null, natural_width: natural ?? null, box_ok: hasBox(e), verdict, paint: "an <img> paints its own colours: the screenshot decides" };
        continue;
      }
      const path = e.present ? measure(dom, `${sel} path`, ["fill"]) : { present: false };
      const pathFill = path.style?.fill ?? "";
      const svgFill = e.style?.fill ?? "";
      const fillMatches = normColor(pathFill) === expected;
      const verdict = e.present ? fillMatches && hasBox(e) : false;
      count(t, verdict);
      contexts[c] = {
        ...e,
        path,
        svg_fill: svgFill,
        path_fill: pathFill,
        fill_resolved: isResolved(pathFill) && normColor(pathFill) !== null,
        fill_matches_expected: fillMatches,
        box_ok: hasBox(e),
        verdict,
        paint: "the computed path fill says what the runtime resolved; the screenshot confirms it paints green",
      };
    }
    out[v.id] = { desc: v.desc, contexts };
  }
  return { expected_color: `${OK_HEX} (--twn-ok) = ${expected}`, variants: out };
}

function bytesToBase64(bytes: Uint8Array): string {
  const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out = "";
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const n = (bytes[i]! << 16) | (bytes[i + 1]! << 8) | bytes[i + 2]!;
    out += abc[(n >> 18) & 63]! + abc[(n >> 12) & 63]! + abc[(n >> 6) & 63]! + abc[n & 63]!;
  }
  const rest = bytes.length - i;
  if (rest === 1) {
    const n = bytes[i]! << 16;
    out += `${abc[(n >> 18) & 63]}${abc[(n >> 12) & 63]}==`;
  } else if (rest === 2) {
    const n = (bytes[i]! << 16) | (bytes[i + 1]! << 8);
    out += `${abc[(n >> 18) & 63]}${abc[(n >> 12) & 63]}${abc[(n >> 6) & 63]}=`;
  }
  return out;
}
export { bytesToBase64 };

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Runs the runtime font paths (E, F, F2, H) before anything is measured; records each step. */
async function loadRuntimeFonts(env: LabEnv): Promise<Record<string, Record<string, unknown>>> {
  const out: Record<string, Record<string, unknown>> = {};
  const bytesCache: Record<string, { bytes?: ArrayBuffer; via?: string; error?: string }> = {};
  const bytesOf = async (f: LabFont) => (bytesCache[f.key] ??= await env.readPluginBytes(f.ttf).catch((e: unknown) => ({ error: errText(e) })));
  for (const v of FONT_VARIANTS.filter((x) => x.how !== "static")) {
    const per: Record<string, unknown> = {};
    for (const f of LAB_FONTS) {
      const family = labFamily(f, v);
      try {
        if (v.how === "inject") {
          const css = fontFace(family, f.weight, v.src!(f));
          per[f.key] = { css, ...env.injectStyle(css) };
        } else if (v.how === "fontface_url") {
          per[f.key] = { source: v.src!(f), ...(await env.loadFontFace(family, v.src!(f), { weight: String(f.weight) })) };
        } else {
          const b = await bytesOf(f);
          if (!b.bytes) {
            per[f.key] = { ok: false, step: "read bytes", error: b.error ?? "no bytes" };
            continue;
          }
          const size = b.bytes.byteLength;
          if (v.how === "fontface_bytes") {
            per[f.key] = { bytes: size, bytes_via: b.via ?? null, ...(await env.loadFontFace(family, b.bytes, { weight: String(f.weight) })) };
          } else {
            const css = fontFace(family, f.weight, `url("data:font/ttf;base64,${bytesToBase64(new Uint8Array(b.bytes))}")`);
            per[f.key] = { bytes: size, bytes_via: b.via ?? null, css_chars: css.length, ...env.injectStyle(css) };
          }
        }
      } catch (e) {
        per[f.key] = { ok: false, error: errText(e) };
      }
    }
    out[v.id] = per;
  }
  return out;
}

function measureFonts(dom: LabDom, runtime: Record<string, Record<string, unknown>>, t: Tally) {
  const width = (sel: string) => {
    const e = measure(dom, sel, FONT_PROPS);
    return { e, w: e.rect?.width ?? 0 };
  };
  const refs: Record<string, { reference_width: number; sanity_width: number; method_sees_change: boolean; reference_family_computed: string }> = {};
  for (const f of LAB_FONTS) {
    const ref = width(`#${fontRefId("ref", f.key)}`);
    const san = width(`#${fontRefId("sanity", f.key)}`);
    refs[f.key] = { reference_width: ref.w, sanity_width: san.w, method_sees_change: ref.w > 0 && Math.abs(san.w - ref.w) > 0.5, reference_family_computed: ref.e.style?.["font-family"] ?? "" };
  }
  const variants: Record<string, unknown> = {};
  for (const v of FONT_VARIANTS) {
    const families: Record<string, unknown> = {};
    for (const f of LAB_FONTS) {
      const m = width(`#${fontSpanId(v.id, f.key)}`);
      const ref = refs[f.key]!;
      const differs = Math.abs(m.w - ref.reference_width) > 0.5;
      // loaded = the span moved away from the fallback-only width; undecided when the method itself cannot see a change
      const loaded = !m.e.present || m.w <= 0 ? false : ref.method_sees_change ? differs : differs ? true : null;
      count(t, loaded);
      families[f.key] = {
        family: labFamily(f, v),
        src: v.src ? v.src(f) : v.how === "fontface_bytes" ? "ArrayBuffer (plugin folder)" : "data:font/ttf;base64,...",
        computed_family: m.e.style?.["font-family"] ?? "",
        width: m.w,
        reference_width: ref.reference_width,
        differs_from_reference: differs,
        loaded,
        ...(runtime[v.id]?.[f.key] ? { runtime: runtime[v.id]![f.key] } : {}),
      };
    }
    variants[v.id] = { desc: v.desc, how: v.how, families };
  }
  return {
    rule: `loaded = the span ("<lab family>", "${LAB_REF_FAMILY}") measures a different width from the same text in "${LAB_REF_FAMILY}" alone (> 0.5 px); the "${LAB_SANITY_FAMILY}" row must differ from the reference too, else the method is blind and a same width is undecided (null)`,
    reference_family: LAB_REF_FAMILY,
    sanity_family: LAB_SANITY_FAMILY,
    font_size_px: LAB_FONT_PX,
    references: refs,
    variants,
  };
}

function measureWhitespace(dom: LabDom, t: Tally) {
  const out: Record<string, unknown> = {};
  const controlLabel: Record<WsDir, number> = { ltr: 0, rtl: 0 };
  for (const v of WS_VARIANTS) {
    const dirs: Record<string, unknown> = {};
    for (const d of WS_DIRS) {
      const label = measure(dom, `#${wsId(v.id, d, "label")}`, WS_PROPS);
      const cnt = measure(dom, `#${wsId(v.id, d, "count")}`, WS_PROPS);
      const rowEl = dom.query(`#${wsId(v.id, d, "row")}`);
      const text = rowEl ? dom.prop(rowEl, "textContent") : null;
      const lr = label.rect ?? { x: 0, y: 0, width: 0, height: 0 };
      const cr = cnt.rect ?? { x: 0, y: 0, width: 0, height: 0 };
      const gap = d === "ltr" ? cr.x - (lr.x + lr.width) : lr.x - (cr.x + cr.width);
      const padStart = px(d === "ltr" ? cnt.style?.["padding-left"] : cnt.style?.["padding-right"]);
      if (v.control) controlLabel[d] = lr.width;
      const labelExtra = v.control ? 0 : lr.width - controlLabel[d];
      const space = r2(gap + padStart + labelExtra);
      const visible = label.present && cnt.present && lr.width > 0 ? space >= 2 : null;
      if (!v.control) count(t, visible);
      dirs[d] = {
        label,
        count: cnt,
        row_text: typeof text === "string" ? JSON.stringify(text) : null,
        box_gap_px: r2(gap),
        count_padding_start_px: padStart,
        label_extra_px_vs_control: r2(labelExtra),
        space_px: space,
        space_visible: visible,
      };
    }
    out[v.id] = { desc: v.desc, ...(v.control ? { control: true } : {}), ...dirs };
  }
  return { rule: "space_px = box gap between label and count + the count's start padding + how much wider the label is than in W0; visible = space_px >= 2 (W0 is the control, not counted)", variants: out };
}

export interface LabResults {
  lab: "css_lab";
  spike: string;
  host_width_px: number | null;
  layout_settle_ms: number;
  font_settle_ms: number;
  facts: Record<string, unknown>;
  buttons: Record<string, unknown>;
  glow: Record<string, unknown>;
  svg: ReturnType<typeof measureSvg>;
  fonts: ReturnType<typeof measureFonts>;
  whitespace: ReturnType<typeof measureWhitespace>;
  summary: Tally & { by_section: Record<string, Tally> };
  screenshots: string;
}

export const LAB_SECTIONS = ["buttons", "glow", "svg", "fonts", "whitespace"] as const;

/** Measures the rendered lab view (labHtml() must already be in the DOM). Never throws for a missing element. */
export async function runCssLab(dom: LabDom, env: LabEnv, opts: { layoutSettleMs?: number; fontSettleMs?: number } = {}): Promise<LabResults> {
  const layoutSettleMs = opts.layoutSettleMs ?? 400;
  const fontSettleMs = opts.fontSettleMs ?? 1500;
  // 0.1.6 measured every box 0 x 0 right after mounting: UXP lays out on a later frame
  await dom.wait(layoutSettleMs);
  let facts: Record<string, unknown>;
  try {
    facts = env.facts();
  } catch (e) {
    facts = { error: errText(e) };
  }
  const runtime = await loadRuntimeFonts(env);
  await dom.wait(fontSettleMs);
  const by: Record<string, Tally> = Object.fromEntries(LAB_SECTIONS.map((s) => [s, tally()]));
  const buttons = measureButtons(dom, by.buttons!);
  const glow = measureGlow(dom, by.glow!);
  const svg = measureSvg(dom, by.svg!);
  const fonts = measureFonts(dom, runtime, by.fonts!);
  const whitespace = measureWhitespace(dom, by.whitespace!);
  const all = tally();
  for (const s of Object.values(by)) {
    all.pass += s.pass;
    all.fail += s.fail;
    all.na += s.na;
  }
  return {
    lab: "css_lab",
    spike: SPIKE_VERSION,
    host_width_px: dom.hostWidth(),
    layout_settle_ms: layoutSettleMs,
    font_settle_ms: fontSettleMs,
    facts,
    buttons,
    glow,
    svg,
    fonts,
    whitespace,
    summary: { ...all, by_section: by },
    screenshots: "the lab view stays open: screenshot it top to bottom (sections 1 Buttons + 2 Glow, 3 SVG + 4 @font-face, 5 Flex whitespace)",
  };
}

// ---------------------------------------------------------------------------------------------- the view

export interface LabViewDom {
  main: HTMLElement;
  guide: HTMLElement;
  lab: HTMLElement;
  host: HTMLElement;
  caption: HTMLElement;
  back: HTMLElement;
}

export const labCaption = (width: number | null) => `CSS lab - spike ${SPIKE_VERSION}${width ? ` - ${Math.round(width)} px` : ""}`;

export interface LabView {
  show(): void;
  /** `showMain` false: another view (the style guide) is about to take over */
  hide(showMain?: boolean): void;
  isOpen(): boolean;
  caption(width: number | null): void;
}

export function createLabView(dom: LabViewDom): LabView {
  let open = false;
  const api: LabView = {
    show() {
      open = true;
      dom.main.style.display = "none";
      dom.guide.style.display = "none";
      dom.lab.style.display = "flex";
      dom.host.innerHTML = labHtml();
      dom.caption.textContent = labCaption(null);
    },
    hide(showMain = true) {
      open = false;
      dom.lab.style.display = "none";
      if (showMain) dom.main.style.display = "flex";
    },
    isOpen: () => open,
    caption(width) {
      dom.caption.textContent = labCaption(width);
    },
  };
  dom.back.addEventListener("click", () => api.hide());
  return api;
}
