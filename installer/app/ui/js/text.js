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
     . the two private-use characters this file uses as placeholders, so data can never forge one.
   - a T() string var that holds any of these is inserted as its own data isolate (name()), never into the line. */
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
const CTL = /[\u0000-\u0008\u000A-\u001F\u007F-\u009F\u061C\u200B\u200E\u200F\u2028\u2029\u202A-\u202E\u2060\u2066-\u2069\uFEFF\uE000\uE001]/g;
const hasCtl = (s) => { CTL.lastIndex = 0; const r = CTL.test(s); CTL.lastIndex = 0; return r; };
const code = (ch) => "[U+" + ch.charCodeAt(0).toString(16).toUpperCase().padStart(4, "0") + "]";
/* data as plain text: every control shown as its code */
export function safe(s) { return String(s).replace(CTL, code); }
/* data as nodes: the controls become visible .m-ctl marks */
export function data(s) {
  s = String(s);
  const out = document.createDocumentFragment();
  let last = 0;
  CTL.lastIndex = 0;
  for (let m; (m = CTL.exec(s));) {
    if (m.index > last) out.append(document.createTextNode(s.slice(last, m.index)));
    out.append(h("span", { class: "m-ctl" }, code(m[0])));
    last = m.index + 1;
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
export function name(s) { return h("bdi", { dir: "auto", class: "m-data" }, data(s)); }
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

/* T(key, vars): the string for this language as a fragment, Latin runs isolated in Arabic. A var is plain text
   (substituted BEFORE the Latin runs are isolated, so "After Effects {version}" stays one run) or a Node (inserted as
   is, through a private-use placeholder). A plain-text var that holds a neutralised character becomes its own data
   isolate (name()): its [U+XXXX] codes would otherwise split the Latin run in an Arabic line. A missing key is recorded
   and drawn as [key]. */
export function T(key, vars) {
  const s = C.S[key];
  if (s === undefined) { C.missing.push(key); return frag("[" + key + "]"); }
  const parts = s.split(/\{(\w+)\}/), marks = [];
  let str = "";
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 0) { str += parts[i]; continue; }
    let v = vars ? vars[parts[i]] : undefined;
    if (v !== undefined && !(v instanceof Node) && hasCtl(String(v))) v = name(v);
    if (v instanceof Node) { str += "\uE000" + marks.length + "\uE001"; marks.push(v); }
    else str += v === undefined ? "{" + parts[i] + "}" : safe(v);
  }
  if (parts[parts.length - 1]) str = nbLast(str);
  str = str.replace(/ \u00B7 (estimate|\u062A\u0642\u062F\u064A\u0631)/g, "\u00A0\u00B7\u00A0$1")
    .replace(/ \((estimate|\u062A\u0642\u062F\u064A\u0631)\)/g, "\u00A0($1)");
  return txt(str, marks);
}
export function Tos(key, vars) { return T(osKey(key), vars); }
