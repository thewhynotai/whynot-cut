/* The page self-check, kept from the mockups (js/installer.js check(), mockup.js M.selfCheckExtras): once the fonts have
   settled, one <meta name="mock-check" content="k=v;…"> is added to <head>. The UI tests read it (headless Chrome
   --dump-dom), and the macOS WKWebView selftest (ET1-22) reads the same fields. Fields:
   state, lang, w and h (the window's size, title bar included; h is new), dir, mono (the side of the monogram: right in Arabic), tab1 (none: no tabs here),
   overflow (elements running out sideways: measured against the window, and inside the content column, the rail and
   the bar against their own boxes, skipping boxes that cut on purpose: .i-clip, .i-log, .m-ctx), worst (the first one),
   fonts (ok | fallback), missing (string keys and icons asked for and not found), dangerkbd, violet, confirmkbd
   (the mockup's keycap and one-violet rules), and two more for production: csp (violations the CSP blocked, counted
   by guard.js from the first parsed byte) and jserr (uncaught errors).
   Fonts: ok only when each brand face the page needs has a FontFace that actually LOADED (document.fonts.check alone
   says "ok" when a face was never declared or its file failed). Not copied: the mockup's "meta:mock-keys/mock-motion"
   entries (design metadata of the mockup pages) and stalerun/spinoff (panel-only rules: restart notices, service pill). */
import { C } from "./ctx.js";

const VIOLET = { "rgb(84, 0, 251)": 1, "rgb(72, 0, 216)": 1, "rgb(106, 31, 255)": 1, "rgb(57, 7, 150)": 1 };

function fontLoaded(family) {
  let ok = false;
  document.fonts.forEach((f) => { if (f.family.replace(/["']/g, "") === family && f.status === "loaded") ok = true; });
  return ok;
}

function extras(win) {
  const dk = win.querySelectorAll(".m-btn-danger .m-kbd, .m-btn-destructive .m-kbd").length;
  const ck = win.querySelectorAll(".m-dialog .m-btn-primary .m-kbd").length;
  let violet = 0;
  const fills = [];
  win.querySelectorAll("*").forEach((el) => {
    if (!VIOLET[getComputedStyle(el).backgroundColor]) return;
    if (fills.some((f) => f.contains(el))) return;
    fills.push(el);
    violet++;
  });
  return ["dangerkbd=" + dk, "violet=" + violet, "confirmkbd=" + ck];
}

export function selfCheck(win, state, beforeMeasure) {
  const done = () => {
    if (beforeMeasure) beforeMeasure();
    const wr = win.getBoundingClientRect(), mid = wr.left + wr.width / 2;
    const side = (el) => { if (!el) return "none"; const r = el.getBoundingClientRect(); return r.left + r.width / 2 < mid ? "left" : "right"; };
    let over = 0, worst = "";
    win.querySelectorAll("*").forEach((el) => {
      let box = wr;
      for (let a = el.parentElement; a && a !== win; a = a.parentElement) {
        const c = a.classList;
        if (c.contains("i-clip") || c.contains("i-log") || c.contains("m-ctx")) return;
        if (box === wr && (c.contains("i-scroll") || c.contains("i-rail") || c.contains("i-bar"))) box = a.getBoundingClientRect();
      }
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
        over++;
        if (!worst) worst = (typeof el.className === "string" ? el.className : el.tagName) + " " + (el.textContent || "").slice(0, 30);
      }
    });
    const need = ["Syne", "Inter"].concat(C.lang === "ar" ? ["IBM Plex Sans Arabic"] : []);
    const fontsOk = !!document.fonts && need.every(fontLoaded);
    const guard = window.__wncGuard || { csp: ["no guard"], errors: ["no guard"] };
    const meta = document.createElement("meta");
    meta.name = "mock-check";
    meta.content = ["state=" + state, "lang=" + C.lang, "w=" + Math.round(wr.width), "h=" + Math.round(wr.height), "dir=" + getComputedStyle(win).direction,
      "mono=" + side(win.querySelector(".m-mono")), "tab1=none",
      "overflow=" + over, "worst=" + worst.replace(/[;=]/g, " "), "fonts=" + (fontsOk ? "ok" : "fallback"),
      "missing=" + C.missing.join(",")].concat(extras(win), ["csp=" + guard.csp.length, "jserr=" + guard.errors.length]).join(";");
    document.head.appendChild(meta);
  };
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => setTimeout(done, 50));
  else setTimeout(done, 300);
}
