/* WhyNot Cut panel V1 group (UI track, 2026-10-18): helpers for P-23 chat and the Phase 4 screens. Loaded after
   ../mockup.js, ../js/premiere-core.js and ../strings/panel-v1.js. Emits only markup the UXP kit can paint (div role=button
   controls, <span> chips, inline SVG coloured by .ink-* classes, physical margins).
   - V1.you / V1.bot: one chat turn. Text a person typed and the assistant's words are CONTENT: always escaped (M.esc),
     never markup from the stream; each message carries its own dir/lang, so an Arabic message reads RTL in the English UI
     and an English one LTR in the Arabic UI (spec F1, review focus 2). Latin runs inside Arabic are isolated (M.txt).
   - V1.steps: the step cards of a turn ("Transcript ready", "Building", ...): status icon, sentence, time, Open.
   - V1.ask: the approval prompt rendered as buttons (spec F1: Approve / Change / Stop). The panel never decides: each
     button only sends the editor's choice (a contract intent, C-1/C-2 in the coverage map).
   - V1.compose: the composer in the pinned bar (Send, or Stop while a turn runs). */
(function () {
  "use strict";
  var M = window.M, t = M.t, PC = window.PC;
  var V1 = (window.V1 = { D: window.V1_DATA });

  /* a message in a known language: "ar" -> RTL, "en" -> LTR; the text is escaped, Latin runs inside Arabic isolated */
  /* a long token with no space (a file name, a URL) may break after its separators, never mid-word otherwise
     (review focus 2: no sideways scroll at 300 px). Applied to escaped text only, outside tags. */
  function wbr(html) {
    return html.replace(/(^|>)([^<]+)/g, function (_, a, txt) {
      return a + txt.replace(/\S{25,}/g, function (tok) { return tok.replace(/([_\/.\-])/g, "$1<wbr>"); });
    });
  }
  function msg(text, lang, extra) {
    var dir = lang === "ar" ? "rtl" : "ltr";
    var body = wbr(lang === "ar" ? arTxt(text) : M.esc(text));
    return '<div class="v1-msg t-body" dir="' + dir + '" lang="' + lang + '">' + body + (extra || "") + "</div>";
  }
  /* Arabic content in either UI: the shell's txt() isolates Latin runs only when the UI is Arabic, so do it here too */
  function arTxt(s) {
    /* a sentence's full stop or a trailing hyphen after a Latin word stays OUTSIDE the isolate (Arabic punctuation side) */
    return M.esc(s).replace(/[A-Za-z][A-Za-z0-9._\-]*(?:[  ][A-Za-z0-9][A-Za-z0-9._\-]*)*/g, function (m) {
      var run = m.replace(/[.\-_]+$/, ""), tail = m.slice(run.length);
      return '<bdi dir="ltr" class="lat' + (run.length <= 32 ? " nb" : "") + '">' + run + "</bdi>" + tail;
    });
  }
  V1.msg = msg;
  V1.arTxt = arTxt;
  /* a counted line: "<key>.one" for 1 and "<key>.two" for 2 when the language has them (Arabic singular and dual),
     else the plural "<key>" with {n} */
  V1.tn = function (key, n, vars) {
    var k = n === 1 && M.raw(key + ".one") !== undefined ? key + ".one" : n === 2 && M.raw(key + ".two") !== undefined ? key + ".two" : key;
    var v = { n: M.html(M.ltr(String(n))) };
    for (var x in vars || {}) v[x] = vars[x];
    return t(k, v);
  };

  /* the language a demo message was typed in: the UI language (the person writes in it; the assistant answers in it) */
  V1.lang = function () { return M.lang; };

  V1.you = function (text, lang) {
    return '<div class="v1-turn v1-turn-you"><div class="v1-who"><span class="t-meta tx-muted">' + t("p23.you") + "</span></div>" +
      '<div class="v1-bubble">' + msg(text, lang || M.lang) + "</div></div>";
  };
  /* o = {lang, streaming, extra (markup after the text, inside the turn), steps, ask} */
  V1.bot = function (text, o) {
    o = o || {};
    var caret = o.streaming ? '<span class="v1-caret" aria-hidden="true"></span>' : "";
    return '<div class="v1-turn v1-turn-bot"><div class="v1-who"><img class="m-mono" src="../../../premiere-uxp/icons/dark/icon-48.png" alt="" width="16" height="16">' +
      '<span class="v1-who-name t-meta tx-muted">' + M.ltr(M.raw("p23.bot"), "lat") + "</span></div>" +
      '<div class="v1-say">' + (text ? msg(text, o.lang || M.lang, caret) : "") + (o.extra || "") + "</div>" +
      (o.steps || "") + (o.ask || "") + "</div>";
  };
  /* rows: [kind ("ok" | "busy" | "paused" | "error"), sentence html, time ("0:42") or "", open (bool)] */
  V1.steps = function (rows) {
    return '<div class="v1-steps">' + rows.map(function (r) {
      var end = (r[2] ? '<span class="t-meta tx-muted">' + M.mono(r[2]) + "</span>" : "") +
        (r[3] ? '<div class="m-row ms-1">' + M.btn(t("p23.step.open"), { kind: "ghost", flush: true }) + "</div>" : "");
      return '<div class="v1-step">' + M.status(r[0]) + '<div class="v1-step-text"><span class="t-meta tx-text">' + r[1] + "</span></div>" +
        (end ? '<div class="v1-step-end">' + end + "</div>" : "") + "</div>";
    }).join("") + "</div>";
  };
  /* the approval prompt. o = {flagged (n), quote (a flagged line as said), primary (bool: this card holds the screen's
     one primary), disabled, focus, approved ({name, time}: the prompt after the answer: no buttons, one line)} */
  V1.ask = function (o) {
    o = o || {};
    var D = M.D;
    if (o.approved) {
      return '<div class="v1-steps"><div class="v1-step">' + M.status("ok") + '<div class="v1-step-text"><span class="t-meta tx-text">' +
        t("p23.approved", { name: o.approved.name, time: M.html(M.mono(o.approved.time)) }) + "</span></div></div></div>";
    }
    var lines = o.flagged ? '<div class="t-body mt-1">' + t("p23.ask.flagged", { n: M.html(M.ltr(String(o.flagged))) }) + "</div>" +
      (o.quote ? '<div class="m-inset mt-2"><div class="m-quote m-quote-ar t-body" dir="rtl" lang="ar"><span class="ar-run">«' + arTxt(o.quote) + "»</span></div></div>" : "") : "";
    var main = o.flagged ? t("p23.ask.review") : t("approval.approve");
    var acts = '<div class="v1-acts">' +
      '<div class="m-row">' + M.btn(main, { kind: o.primary === false ? "secondary" : "primary", icon: "circle-check-big", disabled: o.disabled, focus: o.focus, kbd: o.primary !== false && !o.disabled }) + "</div>" +
      '<div class="m-row">' + M.btn(t("p23.ask.change"), { icon: "message-square", disabled: o.disabled }) + "</div>" +
      '<div class="m-row">' + M.btn(t("p23.ask.stop"), { kind: "ghost", icon: "circle-stop", disabled: o.disabled }) + "</div></div>";
    return '<div class="v1-ask" role="group">' + M.eyebrow(t("p23.ask.eyebrow")) +
      '<div class="t-label mt-1">' + t("p23.ask.title", { item: PC.code(D.item) }) + "</div>" + lines + acts +
      M.trust(t("p23.ask.trust", { seq: PC.seq() }), "mt-3") + "</div>";
  };
  /* the composer. o = {value, focus, disabled, hint, running (Stop instead of Send), primary (Send is the screen's
     primary: only when no prompt waits and text is typed)} */
  V1.compose = function (o) {
    o = o || {};
    var box = M.input(o.value ? M.esc(o.value) : t("p23.placeholder"), { textarea: true, focus: o.focus, value: o.value ? M.esc(o.value) : "" });
    var btn = o.running
      ? PC.kbtn(t("p23.stop"), "mod+.", { kind: "secondary", icon: "circle-stop", disabled: o.disabled })
      : M.btn(t("p23.send"), { kind: o.primary ? "primary" : "secondary", icon: "send-horizontal", disabled: o.disabled || !o.value, kbd: o.primary && !o.disabled && !!o.value });
    var under = o.hint ? '<div class="t-meta tx-muted mt-2">' + o.hint + "</div>" : "";
    return '<div class="v1-compose">' + (o.disabled ? box.replace('class="m-input', 'class="m-input pc-chk-dis') : box) +
      '<div class="v1-compose-row"><div class="m-grow t-meta tx-muted">' + t("p23.uses") + '</div><div class="m-row ms-2">' + btn + "</div></div>" + under + "</div>";
  };
  /* the suggestions of the empty chat: plain controls, never a primary (the screen's primary is Send) */
  V1.suggs = function (keys, o) {
    o = o || {};
    return '<div class="v1-suggs">' + keys.map(function (k) {
      return '<div class="v1-sugg" role="button" tabindex="' + (o.disabled ? "-1" : "0") + '"' + (o.disabled ? ' aria-disabled="true"' : "") + ">" +
        M.ico("message-square", 16, o.disabled ? "ink-disabled" : "ink-accent") + '<span class="m-block t-label' + (o.disabled ? " tx-disabled" : "") + '">' + t(k[0], k[1]) + "</span></div>";
    }).join("") + "</div>";
  };
})();
