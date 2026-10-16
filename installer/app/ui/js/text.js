/* DOM building and text for the installer UI, CSP-clean: every node is made with createElement / createTextNode, so no
   string is ever parsed as HTML (no HTML string sink anywhere in ui/). Ported from the mockups' mockup.js (M.t, txt,
   M.path, M.ltr, M.mono) with the same bidi rules; the mockup built HTML strings and escaped them, this builds nodes.

   Data (paths, folder and file names, host names, versions) is never trusted:
   - it is only ever text (createTextNode), so "<img src=x onerror=…>" as a folder name is shown as those characters;
   - every character that can reorder or split a line is SHOWN as its code ("[U+202E]") instead of being applied, so a
     name can never reorder what is drawn around it ("evil\u202Egpj.exe" would read "evilexe.jpg"). The set (CTL):
     . the bidi controls: ALM U+061C, LRM/RLM U+200E/F, LRE..RLO U+202A-E, LRI..PDI U+2066-9;
     . every C0 control but TAB (U+0000-0008, 000A-001F) and DEL, and every C1 control (U+0080-009F): U+000A/000D/
       001C-001E/0085 are paragraph separators and U+000B/001F segment separators in the bidi algorithm, and a
       paragraph separator ends every isolate, so the rest of the data reorders with the line (review F1, measured).
       LF is coded too: no data helper here shows a line break (one value per line, always). TAB stays: it is
       collapsed to a space by white-space normal/nowrap, which every data place uses;
     . U+2028 / U+2029 (line / paragraph separator);
     . the invisible look-alike makers U+200B (ZWSP), U+2060 (WJ) and U+FEFF (BOM), so two names that look the same
       on screen do not differ by an invisible character. ZWNJ / ZWJ (U+200C/D) are LEFT ALONE: Arabic and Persian
       names and emoji need them;
     . the other invisible format characters (review round 2): U+00AD (soft hyphen), U+180E, U+2061-2064,
       U+206A-206F, U+FFF9-FFFB and the tag block U+E0000-E007F;
     . the two private-use characters this file uses as placeholders, so data can never forge one.
     A run of consecutive coded characters is ONE .m-ctl span (one pass, review round 2 N3).
   - what is SHOWN of one data value is capped at DATA_MAX characters with an ellipsis (a corrupt or hostile host
     value of a Windows long-path size must not stall the window, N3); where the whole value matters (a name, the path
     field) it is the title, neutralised and capped at TITLE_MAX.
   - a T() string var joins the sentence only when it is provably ONE safe run (safeRun below, the one definition);
     anything else is its own data isolate (name()), never part of the line (review round 2, N1). */
import { C } from "./ctx.js";

export const SVG_NS = "http://www.w3.org/2000/svg";

/* attributes h() refuses: event handlers, inline style, formaction (CSP keeps them dead anyway; this keeps them out
   of the DOM) */
const REFUSED_ATTR = /^(?:on|style$|formaction$)/i;

function setAttrs(el, attrs) {
  if (!attrs) return el;
  for (const name of Object.keys(attrs)) {
    const v = attrs[name];
    if (v === null || v === undefined || v === false) continue;
    if (REFUSED_ATTR.test(name)) throw new Error("refused attribute: " + name);
    /* the URL parser drops tabs, newlines and leading C0/space (a tab inside the scheme name still makes it), so the check does too */
    if ((name === "href" || name === "src") && /^javascript(?=:)/i.test(String(v).replace(/[\u0000-\u0020]/g, ""))) throw new Error("refused URL");
    el.setAttribute(name, v === true ? "" : String(v));
  }
  return el;
}

/* add children: a Node as is, anything else as a text node; arrays are flattened; null/false/"" are skipped */
export function add(el, kids) {
  for (const k of [kids].flat(Infinity)) {
    if (k === null || k === undefined || k === false || k === "") continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

export function h(tag, attrs, ...kids) { return add(setAttrs(document.createElement(tag), attrs), kids); }
export function frag(...kids) { return add(document.createDocumentFragment(), kids); }
export function svg(tag, attrs) { return setAttrs(document.createElementNS(SVG_NS, tag), attrs); }

/* ---- untrusted data ---- */
const CTL_SET = "\\u0000-\\u0008\\u000A-\\u001F\\u007F-\\u009F\\u00AD\\u061C\\u180E\\u200B\\u200E\\u200F\\u2028\\u2029\\u202A-\\u202E" +
  "\\u2060-\\u2064\\u2066-\\u206F\\uFEFF\\uFFF9-\\uFFFB\\uE000\\uE001\\u{E0000}-\\u{E007F}";
const CTL = new RegExp("[" + CTL_SET + "]", "u");
const CTL_RUN = new RegExp("[" + CTL_SET + "]+", "gu");
const hasCtl = (s) => CTL.test(s);
const codes = (run) => Array.from(run, (ch) => "[U+" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0") + "]").join("");
export const DATA_MAX = 512;
export const TITLE_MAX = 4096;
/* the first max characters (whole code points) with an ellipsis, when the value is longer */
export function cap(s, max) {
  s = String(s);
  if (s.length <= max) return s;
  return Array.from(s.slice(0, max + 1)).slice(0, max - 1).join("") + "\u2026";
}
/* data as plain text (a title, a T() var that is a safe run): every coded character shown as its code; with max, the
   result (codes included) is at most max characters */
export function safe(s, max) {
  s = String(s);
  if (!max) return s.replace(CTL_RUN, codes);
  return cap(cap(s, max).replace(CTL_RUN, codes), max);
}
/* data as nodes, capped at DATA_MAX: one pass, each run of coded characters one visible .m-ctl mark */
export function data(s) {
  s = cap(s, DATA_MAX);
  const out = document.createDocumentFragment();
  let last = 0;
  CTL_RUN.lastIndex = 0;
  for (let m; (m = CTL_RUN.exec(s));) {
    if (m.index > last) out.append(document.createTextNode(s.slice(last, m.index)));
    out.append(h("span", { class: "m-ctl" }, codes(m[0])));
    last = m.index + m[0].length;
  }
  if (last < s.length) out.append(document.createTextNode(s.slice(last)));
  return out;
}

/* ---- isolates ---- */
/* a Latin run (a name, a version, a drive) as ONE LTR isolate */
export function ltr(s, cls) { return h("bdi", { dir: "ltr", class: cls || "lat" }, data(s)); }
/* a path or long file name: an LTR isolate that never reverses. It may wrap after a separator (a <wbr> after each
   slash, backslash, underscore, dot or hyphen), except with oneLine: a one-line field (I.pathField) gets no break
   opportunity at all, since Chrome breaks at <wbr> even under white-space: nowrap */
export function path(s, oneLine) {
  s = cap(s, DATA_MAX);
  const b = h("bdi", { dir: "ltr", class: "mono m-path" });
  if (oneLine) return add(b, [data(s)]);
  for (const piece of String(s).split(/(?<=[\\/_.\-])/)) {
    b.append(data(piece));
    if (/[\\/_.\-]$/.test(piece)) b.append(document.createElement("wbr"));
  }
  return b;
}
/* a name from data (a client folder, a file) in a text line: its own isolate whose direction comes from its first
   strong letter (dir=auto), so it never reorders the line around it, and the line never reorders it */
export function name(s) {
  s = String(s);
  return h("bdi", { dir: "auto", class: "m-data", title: s.length > DATA_MAX ? safe(s, TITLE_MAX) : null }, data(s));
}
/* a mono run; a pure time (6:40) tightens the colon, which a monospace face spaces as a full cell */
export function mono(s) {
  s = String(s);
  const b = h("bdi", { dir: "ltr", class: "mono" });
  if (/^[\d:.]+$/.test(s)) s.split(/(:)/).forEach((p) => b.append(p === ":" ? h("span", { class: "mo-c" }, ":") : p));
  else b.append(data(s));
  return b;
}
/* LRI … PDI as characters, for plain-text places (aria-label, title) */
export function lri(s) { return "\u2066" + safe(s) + "\u2069"; }

/* ---- the string table ---- */
/* the raw string (no isolation) for a plain-text place; a missing key is recorded and shown as [key] */
export function raw(key) {
  const s = C.S[key];
  if (s === undefined) { C.missing.push(key); return "[" + key + "]"; }
  return s;
}
/* the macOS copy is the default; a key with a ".win" twin uses it on Windows */
export function osKey(key) { return C.os === "win" && C.S[key + ".win"] !== undefined ? key + ".win" : key; }
/* plain-text substitution of {name} (units, aria): values are data */
export function fmt(key, vars) {
  return raw(key).replace(/\{(\w+)\}/g, (m, n) => (vars && vars[n] !== undefined ? safe(vars[n]) : m));
}

/* R2 (designer P2-9): no one-word orphan: a short last word is bound to the one before it with a no-break space */
function nbLast(s) {
  if (s.split(" ").length < 4) return s;
  return s.replace(/(\S{1,12}) (\S{1,12})$/, "$1\u00A0$2");
}

/* A Latin run inside Arabic: letters then words, digits, dots, hyphens; a path (C:\…, ~/…, /Users/…) is one run; a
   slash INSIDE a run keeps it whole ("claude.ai/download"). Same expression as the mockup's mockup.js LATIN. */
const LATIN = /(?:[A-Za-z]:[\\\/]|~\/|\/(?=[A-Za-z]))[^\s\u00AB\u00BB\u061F\u060C]*|[A-Za-z][A-Za-z0-9.'_\-]*(?:\/[A-Za-z0-9.'_\-]+)*(?:[ \u00A0][A-Za-z0-9][A-Za-z0-9.'_\-]*(?:\/[A-Za-z0-9.'_\-]+)*)*/g;
const PATHSTART = /^(?:[A-Za-z]:[\\\/]|~\/|\/)/;
const PAIRS = { '"': '"', "\u201C": "\u201D", "(": ")", "[": "]" };
const MARK = /\uE000(\d+)\uE001/;

/* append text with node placeholders resolved */
function addMarked(parent, s, marks) {
  const parts = s.split(MARK);
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { if (parts[i]) parent.append(document.createTextNode(parts[i])); }
    else parent.append(marks[Number(parts[i])]);
  }
}

/* Round 3 bidi rules of the mockup, unchanged: (1) a quote or bracket PAIR around exactly one Latin run goes inside its
   isolate; (2) a Latin run of 32 characters or fewer never breaks (class nb); (3) «لـ» (tatweel) before a Latin word, and
   «ما» / a joined «و», are bound to the next word with a no-break space. English text is never split. */
function txt(s, marks) {
  const out = document.createDocumentFragment();
  if (C.lang !== "ar") { addMarked(out, s, marks); return out; }
  s = s.replace(/(\u0640) (?=[A-Za-z])/g, "$1\u00A0");
  s = s.replace(/(^|[\s(\u00AB])(\u0645\u0627|\u0648) (?=\S)/g, "$1$2\u00A0");
  let last = 0;
  LATIN.lastIndex = 0;
  for (let m; (m = LATIN.exec(s));) {
    const run = m[0].replace(/[.\-_']+$/, "");
    if (!run) { LATIN.lastIndex = m.index + 1; continue; }
    let from = m.index, to = from + run.length;
    const isPath = PATHSTART.test(run), o = from - 1 >= last ? s.charAt(from - 1) : "", c = s.charAt(to);
    const paired = !!o && !isPath && PAIRS[o] === c, shown = paired ? o + run + c : run;
    const cls = isPath ? " m-path" : shown.length <= 32 ? " nb" : "";
    if (paired) { from--; to++; }
    addMarked(out, s.slice(last, from), marks);
    const b = h("bdi", { dir: "ltr", class: "lat" + cls });
    addMarked(b, shown, marks);
    out.append(b);
    last = to;
    LATIN.lastIndex = last;
  }
  addMarked(out, s.slice(last), marks);
  return out;
}

/* The ONE definition of a T() string var that may join the sentence as is (review round 2, N1): at most DATA_MAX
   characters, and either a plain number (digits with . , or : between them: "25.1", "0:42", "1,234") or exactly ONE
   Latin run as LATIN keeps it whole (ASCII letters and digits with ' _ - . inside, single spaces or NBSPs between
   words, a slash inside a word; no trailing . - _ ', not a path). In an Arabic line such a value stays one LTR run
   and joins the words around it ("After Effects {version}"). Anything else (other punctuation, brackets, accented or
   non-Latin letters, symbols, a TAB, a coded character) would be cut into several runs that the line reorders, so it
   becomes its own isolate (name()). */
function safeRun(s) {
  if (s.length > DATA_MAX) return false;
  if (s === "" || /^[0-9]+(?:[.,:][0-9]+)*$/.test(s)) return true;
  LATIN.lastIndex = 0;
  const m = LATIN.exec(s);
  LATIN.lastIndex = 0;
  return !!m && m.index === 0 && m[0] === s && !/[.\-_']$/.test(s) && !PATHSTART.test(s);
}

/* T(key, vars): the string for this language as a fragment, Latin runs isolated in Arabic. A var is plain text
   (substituted BEFORE the Latin runs are isolated) when safeRun() allows it, a data isolate (name()) otherwise, or a
   Node (inserted as is, through a private-use placeholder). A missing key is recorded and drawn as [key]. */
export function T(key, vars) {
  const s = C.S[key];
  if (s === undefined) { C.missing.push(key); return frag("[" + key + "]"); }
  const parts = s.split(/\{(\w+)\}/), marks = [];
  let str = "";
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { str += parts[i]; continue; }
    let v = vars ? vars[parts[i]] : undefined;
    if (v !== undefined && !(v instanceof Node) && (hasCtl(String(v)) || !safeRun(String(v)))) v = name(v);
    if (v instanceof Node) { str += "\uE000" + marks.length + "\uE001"; marks.push(v); }
    else str += v === undefined ? "{" + parts[i] + "}" : safe(v);
  }
  if (parts[parts.length - 1]) str = nbLast(str);
  str = str.replace(/ \u00B7 (estimate|\u062A\u0642\u062F\u064A\u0631)/g, "\u00A0\u00B7\u00A0$1")
    .replace(/ \((estimate|\u062A\u0642\u062F\u064A\u0631)\)/g, "\u00A0($1)");
  return txt(str, marks);
}
export function Tos(key, vars) { return T(osKey(key), vars); }
