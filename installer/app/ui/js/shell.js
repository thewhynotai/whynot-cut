/* WhyNot Cut 3.0 installer: the window shell (I-01 to I-09) and its shared components, ported from the mockups'
   adobe/panel-ui/design/js/installer.js (Adobe track, commit 7c3011c) into a CSP-clean ES module (ET1-07).

   Window: 760 x 540, minimum 640 x 480. Shell, top to bottom: the OS title bar (macOS by default, G11; Windows with
   C.os = "win"), the header (monogram, wordmark, "Setup", the beta chip on unsigned builds, the language switch), the
   gradient hairline, then the rail (stages, version, the build line, footer) beside the content column (a natively
   scrolling area + the pinned action bar).
   Keyboard (G2): the primary carries a Return keycap, the cancel/back/close button an Esc keycap; tab order is the DOM
   order (language switch, content, then the bar from start to end). The key handling itself is ET1-13.

   SHARED components (the same row definitions as the panel, eco §3.6.4):
   - I.step: a checklist row with an end status and an optional progress block; data-kind lets a screen COUNT its rows
     (I-03 chips are counted from the rows, never typed);
   - I.act: a notice with a title, a sentence, an optional wrapping mono box and its buttons (action needed, dialogs);
   - I.fail: a failure card: what happened, why, ONE fix, then the support action (D-05: "Copy details and open
     WhatsApp" + the reply promise; with support off, copy only + ONE "coming soon" line) and "Save a report";
   - I.btn: a button with a keycap hint (Return / Esc); never on a danger or destructive button;
   - I.radio: a single-choice row with a 20 px ring;
   - I.pathField: a recessed path field with one button and a field message;
   - I.plural: a count in a sentence: key.one for 1, key.two for 2 when the table has them (the Arabic dual).
   Screens (ET1-10..12) add I.adds, I.notice, I.offlineGet and the I.TITLES table with their states; the flow state
   machine is ET1-09.

   Differences from the mockup (see the ET1-07 report): DOM nodes instead of HTML strings; no state switcher beside the
   window; the window is the viewport; the content column scrolls natively; the rail's accessible name is the string
   i00.rail.aria (Adobe 01b7afe); data (paths, names) shows bidi controls as their code. */
import { C } from "./ctx.js";
import { btn, card, chip, ico, kbd, progress, status, supportParts, soonLine } from "./components.js";
import { T, TITLE_MAX, Tos, add, data, fmt, frag, h, ltr, mono, name, path, raw, safe } from "./text.js";
import { selfCheck } from "./selfcheck.js";

export const I = {};

I.T = T;
I.Tos = Tos;
I.ico = ico;
/* the string form for a count: the CLDR category of this language (Intl.PluralRules: zero, one, two, few, many,
   other) picks key.<category> when the table has it, else the base key (review F5). A count from host JSON may be a
   string ("2"): it is read as a number. */
/* the plural convention (Adobe 01b7afe, header of the mockup strings): the BASE key always exists; AR count keys carry
   .zero .one .two .few .many .other (base == .other), EN the base plus .one where the wording changes */
const PR = {};
I.pluralKey = function (key, n) {
  let cat = "other";
  try { cat = (PR[C.lang] = PR[C.lang] || new Intl.PluralRules(C.lang)).select(Number(n)); } catch (e) { cat = "other"; }
  return C.S[key + "." + cat] !== undefined ? key + "." + cat : key;
};
I.plural = function (key, n, vars) {
  return T(I.pluralKey(key, n), Object.assign({ n: n }, vars || {}));
};
/* "2.9 GB" / «2.9 جيجا» with a no-break space; Western digits in both (plain text: used as a T() var) */
I.gb = function (n) {
  const v = typeof n === "number" ? (n >= 100 ? String(Math.round(n * 10) / 10) : n.toFixed(1)) : n;
  return fmt("i00.unit.gb", { n: v });
};
I.mb = function (n) { return fmt("i00.unit.mb", { n: n }); };
I.path = path;
I.ltr = ltr;
I.data = data;
I.name = name;
I.mono = mono;
/* "WhyNot Cut 3.0.0" as ONE isolated Latin run, the digits in Inter (.i-ver: Syne's old-style digits read "3.o.ı") */
I.app = function (ver) { return h("bdi", { dir: "ltr", class: "lat" }, raw("product.name") + " ", h("span", { class: "i-ver" }, data(ver))); };
I.ver = function (ver) { return h("bdi", { dir: "ltr", class: "lat i-ver" }, data(ver)); };
/* a file name or link the editor must read whole: mono, LTR, wraps anywhere instead of running out */
I.monoBox = function (s) { return h("span", { class: "i-monobox" }, path(s)); };

/* The keycap is the panel's own (.m-kbd, Inter): Return and Esc here. btn() refuses it on a danger or destructive
   button; a disabled button shows none. o.key = "enter" | "esc" */
I.btn = function (label, o) {
  o = Object.assign({}, o || {});
  o.kbd = o.key && !o.disabled ? (o.key === "enter" ? "↵" : "Esc") : null;
  return btn(label, o);
};

/* ---- content helpers ---- */
I.title = function (text, sub) {
  return frag(h("div", { class: "i-title" }, text), sub ? h("div", { class: "t-body tx-muted mt-1" }, sub) : null);
};
I.fact = function (icon, text, o) {
  o = o || {};
  return h("div", { class: "i-fact" }, ico(icon, 16, o.ink || "ink-muted"),
    h("div", { class: "i-fact-text" },
      h("div", { class: "t-body " + (o.muted ? "tx-muted" : "tx-text") }, text),
      o.sub ? h("div", { class: "t-meta tx-muted" }, o.sub) : null, o.under || null));
};

/* SHARED: checklist row. kind ok|warn|error|info|pending|busy|waiting; o = {detail, extra, end, prog:{pct, meta, time},
   act, cls, under} */
I.step = function (kind, name, o) {
  o = o || {};
  const detailCls = kind === "error" || kind === "warn" ? "tx-text" : "tx-muted";
  const prog = o.prog ? h("div", { class: "i-step-prog" }, progress(o.prog.pct),
    h("div", { class: "m-row mt-1" }, h("div", { class: "t-meta tx-muted m-grow" }, o.prog.meta),
      /* R3 I-6: "0:42 elapsed" / «عدّى 0:42», never a bare time that reads as time left */
      o.prog.time ? h("div", { class: "t-meta tx-muted ms-2" }, T("i04.elapsed", { time: mono(o.prog.time) })) : null)) : null;
  const cls = ["i-step", kind === "pending" ? "i-step-pend" : "", o.prog ? "i-step-run" : "", o.cls || ""].filter(Boolean).join(" ");
  return h("div", { class: cls, "data-kind": kind }, status(kind),
    h("div", { class: "i-step-text" },
      h("div", { class: "i-step-head" }, h("div", { class: "t-label i-step-name m-grow" }, name),
        o.end ? h("span", { class: "i-step-end t-meta" }, o.end) : null),
      o.detail ? h("div", { class: "t-meta " + detailCls }, o.detail) : null,
      o.extra ? h("div", { class: "t-meta tx-muted mt-1" }, o.extra) : null,
      prog,
      o.act ? h("div", { class: "m-row mt-2" }, o.act) : null,
      o.under || null));
};
I.list = function (rows, cls) { return card(rows, ("m-card-flush " + (cls || "")).trim()); };

/* SHARED: action-needed card / dialog; kind ok|warn|error|info|waiting (waiting = for the person: the pink dot on the
   info tint); o = {mono, btns (Node or Nodes), hint, icon, sub, cls, extra} */
I.act = function (kind, title, text, o) {
  o = o || {};
  const inks = { ok: "ink-ok", warn: "ink-warn", error: "ink-error", info: "ink-info", waiting: "ink-accent" };
  const body = h("div", { class: "m-notice-body" },
    h("div", { class: "t-label i-act-title" }, title),
    text ? h("div", { class: "t-body tx-text mt-1" }, text) : null,
    o.extra || null,
    o.mono ? h("div", { class: "m-row mt-2" }, I.monoBox(o.mono)) : null,
    o.sub ? h("div", { class: "t-meta tx-muted mt-1" }, o.sub) : null,
    o.btns ? h("div", { class: "m-row mt-3" }, o.btns) : null,
    o.hint ? h("div", { class: "t-meta tx-muted mt-2" }, o.hint) : null);
  return h("div", { class: ("m-notice m-notice-" + (kind === "waiting" ? "info" : kind) + " i-act " + (o.cls || "")).trim(),
    role: kind === "error" ? "alert" : "status" }, o.icon ? ico(o.icon, 16, inks[kind]) : status(kind), body);
};

/* SHARED: failure card (I-07 pattern): what happened (white sentence), why (meta), o.extra, ONE fix (o.btn: one button
   or a list; the row wraps), then the support action and "Save a report for support", and the privacy note (no log
   path in a card: R2 D-P1-10). o = {kind, safety, sub, extra, mono, btn, soonKey} */
I.fail = function (text, o) {
  o = o || {};
  const sp = supportParts({ kind: "ghost", flush: true });
  const btns = o.btn ? [].concat(o.btn).filter(Boolean) : [];
  const body = h("div", { class: "m-notice-body" },
    o.safety ? h("div", { class: "m-row" }, chip("error", T("i07.safety"), "shield-x")) : null,
    h("div", { class: "t-body tx-text" + (o.safety ? " mt-2" : "") }, text),
    o.sub ? h("div", { class: "t-meta tx-muted mt-1" }, o.sub) : null,
    o.extra ? h("div", { class: "t-meta tx-muted mt-1" }, o.extra) : null,
    o.mono ? h("div", { class: "m-row mt-2" }, I.monoBox(o.mono)) : null,
    btns.length ? h("div", { class: "m-row m-wrap" }, btns.map((b) => h("div", { class: "m-row me-2 mt-3" }, b))) : null,
    h("div", { class: "m-row m-wrap mt-2 i-support" }, h("div", { class: "m-row me-2" }, sp.btn)),
    /* o.soonKey (support off only): the card's own "coming soon" and support.soon fold into ONE line */
    !sp.live && o.soonKey ? soonLine(o.soonKey) : sp.under,
    h("div", { class: "m-row m-wrap i-support" }, btn(T("i00.save_report"), { kind: "ghost", icon: "download", flush: true })),
    h("div", { class: "t-meta tx-muted mt-1" }, T("i00.report_note")));
  return h("div", { class: "m-notice m-notice-" + (o.kind || "error"), role: "alert" }, status(o.kind || "error"), body);
};

/* SHARED: single-choice row; o = {on, chip, size, focus, disabled} (one tab stop per group: only the chosen row is 0) */
I.radio = function (label, o) {
  o = o || {};
  return h("div", { class: "i-radiorow" + (o.disabled ? " i-radio-disabled" : "") + (o.focus ? " m-btn-focus" : ""),
    role: "radio", tabindex: o.disabled ? "-1" : o.on ? "0" : "-1", "aria-checked": String(!!o.on),
    "aria-disabled": o.disabled ? "true" : null },
    h("span", { class: "i-radio" + (o.on ? " i-radio-on" : "") }, o.on ? h("span", { class: "i-radio-dot" }) : null),
    h("div", { class: "t-label ms-3" }, label), o.chip || null, h("span", { class: "m-spacer" }),
    h("span", { class: "i-size t-meta" }, o.size || ""));
};

/* SHARED: the path shown in a path field, cut in the MIDDLE so it stays on ONE line (Adobe 01b7afe; the mockup's rule,
   copied exactly). For a path longer than the budget (characters, "…" counted as 1):
     1. keep the FIRST segment plus its separator: the drive "D:\", or the root "/" with its first folder ("/Volumes/"); on
        macOS under /Users and /Volumes the account or the volume name is the identity, so it is kept too ("/Users/sara/",
        "/Volumes/Samsung T7 Shield/") when head + "…" + separator + the last segment still fits the budget, else only
        the first folder;
     2. keep the LAST segment whole (the folder the person chose); it is never cut by this rule;
     3. fill from the END backwards with whole segments (each with its separator) while head + "…" + separator + the
        kept tail stays within the budget; the first segment that does not fit stops the fill (the tail is contiguous);
     4. put "…" plus the separator between the two parts: head + "…" + sep + tail.
   A path within the budget is shown whole. The separator is the path's own ("\" if it has one, else "/"). The budget is
   characters per width: 46 at 760 px, 38 at 640 px (below 760). If the last segment alone is longer than the budget the
   field's CSS cuts it at its end, the only case it can. (A UNC path "\\server\share\..." loses its server name under
   this rule: the mockup's behaviour, reported to the Adobe track.) */
I.PATH_BUDGET = { 760: 46, 640: 38 };
I.pathBudget = function () { return window.innerWidth >= 760 ? I.PATH_BUDGET[760] : I.PATH_BUDGET[640]; };
I.pathShort = function (p, budget) {
  if (p.length <= budget) return p;
  const sep = p.indexOf("\\") >= 0 ? "\\" : "/";
  const parts = p.replace(/[\\/]+$/, "").split(sep); /* "/Users/a/b" -> ["", "Users", "a", "b"]; "D:\x\y" -> ["D:", "x", "y"] */
  let keep = parts[0] === "" ? 2 : 1;
  const last = parts[parts.length - 1];
  if (parts[0] === "" && (parts[1] === "Users" || parts[1] === "Volumes") && parts.length > 4 &&
      parts.slice(0, 3).join(sep).length + 1 + 2 + last.length <= budget) keep = 3;
  if (parts.length - 1 <= keep) return p; /* nothing in the middle to cut */
  const head = parts.slice(0, keep).join(sep) + sep;
  let tail = last;
  for (let i = parts.length - 2; i >= keep; i--) {
    const cand = parts[i] + sep + tail;
    if (head.length + 2 + cand.length > budget) break;
    tail = cand;
  }
  return head + "…" + sep + tail;
};
/* the fields on screen, re-cut when the window crosses 760 px */
const PATH_FIELDS = [];
let pathBudgetNow = 0;
function recutPaths() {
  const b = I.pathBudget();
  if (b === pathBudgetNow) return;
  pathBudgetNow = b;
  for (const f of PATH_FIELDS) if (f.el.isConnected) f.el.replaceChildren(path(I.pathShort(f.p, b), true));
}
window.addEventListener("resize", recutPaths);
/* SHARED: path field; o = {btn (label), btnKind, kind: warn|error, msg, msgKind, focus, sub}. The path is data: one LTR
   isolate, left-aligned in both languages (R3 S-08), cut in the middle (I.pathShort); the whole path is the field's
   title (neutralised, capped at TITLE_MAX) */
I.pathField = function (label, p, o) {
  o = o || {};
  p = String(p);
  pathBudgetNow = I.pathBudget();
  const field = h("div", { class: "i-path i-clip" + (o.kind ? " i-path-" + o.kind : ""), title: safe(p, TITLE_MAX) },
    path(I.pathShort(p, pathBudgetNow), true));
  PATH_FIELDS.push({ el: field, p });
  return frag(
    h("div", { class: "t-label" }, label),
    h("div", { class: "i-pathrow mt-1" },
      field,
      btn(o.btn || T("i02.change"), { icon: "folder", focus: o.focus, kind: o.btnKind })),
    o.msg ? h("div", { class: "i-field-msg" }, status(o.msgKind || "info", 16),
      h("div", { class: "t-meta ms-2 m-grow " + (o.msgKind === "warn" || o.msgKind === "error" ? "tx-text" : "tx-muted") }, o.msg)) : null,
    o.sub ? h("div", { class: "t-meta tx-muted mt-1" }, o.sub) : null);
};

/* ---- shell ---- */
/* the stages of each flow (the state machine that moves through them is ET1-09) */
export const FLOWS = {
  install: ["welcome", "custom", "check", "claude", "install", "finish"],
  update: ["update", "install", "finish"],
  uninstall: ["choose", "remove", "done"]
};
/* r = {flow, at, custom, claude, all, none, mark}; r.none: nothing ran (I-09 empty), so no green and no active step */
function rail(r) {
  if (!r) return [];
  const stages = FLOWS[r.flow].filter((s) => (s !== "custom" || r.custom) && (s !== "claude" || r.claude));
  const at = stages.indexOf(r.at);
  return stages.map((s, i) => {
    const kind = r.none ? "pending" : i < at || r.all ? "ok" : i === at ? (r.mark || "current") : "pending";
    const on = i === at && !r.all && !r.none;
    return h("div", { class: "i-rstep" + (on ? " i-rstep-on" : "") + (s === "custom" || s === "claude" ? " i-rstep-sub" : ""),
      "aria-current": on ? "step" : null },
      kind === "current" ? ico("circle-dot", 16, "ink-text") : status(kind),
      h("span", { class: "t-label ms-2" }, T("i00.stage." + s)));
  });
}
function langSwitch() {
  const seg = (l) => {
    const on = l === C.lang;
    return h("div", { class: "m-seg" + (l === "ar" ? " m-seg-ar" : "") + (on ? " m-seg-on" : ""), role: "button", tabindex: "0",
      lang: l, "aria-pressed": String(on), "aria-label": raw("lang." + l) }, raw("lang." + l + ".short"));
  };
  return h("div", { class: "m-lang", role: "group" }, seg("ar"), seg("en"));
}
function osChrome() {
  const title = h("span", { class: "i-os-title" + (C.lang === "ar" ? " i-os-ar" : ""), dir: C.rtl ? "rtl" : "ltr" }, raw("i00.wintitle"));
  if (C.os === "win") {
    return h("div", { class: "i-os i-os-win i-clip", "aria-hidden": "true" },
      h("img", { src: "vendor/brand/icon-24.png", alt: "", width: "16", height: "16", class: "i-os-icon" }), title,
      h("span", { class: "m-spacer" }),
      h("span", { class: "i-os-btn" }, ico("minus", 16, "ink-text")), h("span", { class: "i-os-btn" }, ico("square", 12, "ink-text")),
      h("span", { class: "i-os-btn" }, ico("x", 16, "ink-text")));
  }
  return h("div", { class: "i-os i-os-mac i-clip", "aria-hidden": "true" },
    h("span", { class: "i-os-light i-os-red" }), h("span", { class: "i-os-light i-os-yellow" }), h("span", { class: "i-os-light i-os-green" }),
    h("div", { class: "i-os-mid" }, title));
}

/* the scroll indicator follows the natively scrolling column (the WebView's own scrollbar is hidden) */
function scrollIndicator(win, how) {
  const sc = win.querySelector(".i-scroll"), bar = win.querySelector(".i-sbar");
  const gap = bar.querySelector(".i-sbar-gap"), th = bar.querySelector(".i-sbar-thumb");
  const update = () => {
    const track = bar.getBoundingClientRect().height;
    if (sc.scrollHeight > sc.clientHeight + 1) {
      th.style.height = Math.max(24, Math.round(track * sc.clientHeight / sc.scrollHeight)) + "px";
      gap.style.height = Math.round(track * sc.scrollTop / sc.scrollHeight) + "px";
    } else { th.style.height = "0px"; gap.style.height = "0px"; }
  };
  if (how === "end") sc.scrollTop = sc.scrollHeight;
  else if (how) {
    const el = win.querySelector(how);
    if (el) sc.scrollTop = Math.max(0, el.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - 24);
  }
  sc.addEventListener("scroll", update, { passive: true });
  if (window.ResizeObserver) new ResizeObserver(update).observe(sc);
  update();
  return update;
}

/* mount(view): view = {state, body (Node), bar: {meta, start: [Node], end: [Node]}, rail: {flow, at, …}, version,
   scroll ("end" | a selector)}. Returns the window element. */
export function mount(view) {
  const root = document.documentElement;
  root.lang = C.lang;
  root.dir = C.rtl ? "rtl" : "ltr";
  document.title = raw("i00.wintitle");

  const internal = !C.cfg.signed;
  const trust = internal
    ? h("div", { class: "i-rail-trust" }, ico("flask-conical", 12, "ink-warn"), h("div", { class: "t-meta tx-muted ms-2 m-grow" }, T("i00.unsigned")))
    : h("div", { class: "i-rail-trust" }, ico("shield-check", 12, "ink-ok"), h("div", { class: "t-meta tx-muted ms-2 m-grow" }, T("i00.signed")));
  const b = view.bar;
  const bar = b ? h("div", { class: "i-bar" }, b.meta ? h("div", { class: "i-bar-meta" }, b.meta) : null,
    b.start || null, h("span", { class: "m-spacer" }), b.end || null) : null;

  const win = h("div", { class: "m-panel i-win" + (C.rtl ? " m-rtl" : ""), dir: C.rtl ? "rtl" : "ltr" },
    C.chrome ? osChrome() : null,
    h("div", { class: "i-app" },
      h("header", { class: "i-hdr" },
        h("span", { class: "m-lockup", dir: "ltr" },
          h("img", { class: "m-mono", src: "vendor/brand/icon-48.png", alt: "", width: "20", height: "20" }),
          h("span", { class: "m-wordmark m-lockup-wm" }, ltr(raw("product.name"), "wm"))),
        h("span", { class: "i-setup ms-2" }, T("i00.setup")),
        h("span", { class: "m-spacer" }),
        internal ? chip("warn", T("i00.internal"), "flask-conical") : null,
        langSwitch()),
      h("div", { class: "m-hairline", "aria-hidden": "true" }),
      h("div", { class: "i-body" },
        h("nav", { class: "i-rail", "aria-label": raw("i00.rail.aria") }, rail(view.rail), h("span", { class: "m-spacer" }),
          h("div", { class: "i-rail-end" },
            view.version ? h("div", { class: "t-meta tx-muted" }, T("i00.version", { app: I.app(view.version) })) : null,
            h("div", { class: "mt-1" }, trust)),
          h("footer", { class: "m-footer" }, h("bdi", { dir: C.rtl ? "rtl" : "ltr", class: "m-footer-txt" }, T("footer.powered")))),
        h("div", { class: "i-main" },
          h("div", { class: "i-scrollrow" },
            h("main", { class: "i-scroll", id: "scroll" }, h("div", { class: "i-scroll-in" }, view.body || null)),
            h("div", { class: "i-sbar", "aria-hidden": "true" }, h("span", { class: "i-sbar-gap" }), h("span", { class: "i-sbar-thumb" }))),
          bar))));
  document.body.replaceChildren(win);
  const update = scrollIndicator(win, view.scroll);
  /* review F3: the keys and icons missing from THIS view (recorded while it was built and drawn), then a fresh list
     for the next one; the self-check of an earlier mount never writes after a newer mount */
  selfCheck(win, view.state || "idle", update, C.missing.splice(0));
  return win;
}

/* re-exported for screens and fixtures */
export { add, btn, card, chip, data, frag, h, ico, kbd, ltr, mono, name, path, progress, raw, safe, soonLine, status, supportParts, T, Tos };
