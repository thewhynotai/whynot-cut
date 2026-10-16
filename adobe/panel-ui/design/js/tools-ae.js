/* WhyNot Cut 3.0 E-D2 mockups: helpers for the "tools + After Effects" screen group (P-13 to P-20, A-01 to A-04).
   Loaded after ../mockup.js. Emits only markup the UXP kit can paint (same rules as mockup.js): <div role> controls
   with a 2 px rest border equal to the fill, <span> chips, inline SVG coloured by .ink-* classes, physical margins.
   R2 (R2-fix-list.md section 1.3): everything the shared layer now owns is NOT built here any more. The screens call
   M.back, M.slot, M.notice, M.offline, M.noClaude, M.stale, M.dialog, M.segmented, M.radio, M.toggle, M.select,
   M.slider, M.sechead, M.stages, M.tile / M.media, M.saved, M.trust, M.path directly. What stays in this file is
   specific to the group: the After Effects mount, the tool title block, track toggles, field rows, the stats strip,
   the check row, the waveform, progress and the "label · value" helpers.
   - TA.mount(screen, {ae}) wraps M.mount: for the After Effects panel it names the host "After Effects", maps the seven
     pipeline step labels to the motion stages and drops the Tools tab (Tidy, Hush and Kalam are Premiere tools);
     with ?w280=1 (and w=300, so the 300 px rules apply) it narrows the panel to 280 px, the CEP minimum width. */
(function () {
  "use strict";
  var M = window.M, t = M.t;
  var TA = (window.TA = {});
  var q = new URLSearchParams(location.search);
  var W280 = q.get("w280") === "1";

  TA.mount = function (screen, o) {
    o = o || {};
    var S = window.MOCK_STRINGS[M.lang];
    TA.AE = !!o.ae;
    if (o.ae) {
      S["pill.host"] = S["a01.pill.host"];
      ["transcript", "plan", "build", "frames"].forEach(function (k) { S["step." + k] = S["a01.step." + k]; });
      /* header row 2 names the motion project (client · <EP>_<ID>_MO) */
      M.D.item = M.D.ta.motion;
      M.D.long.item = M.D.ta.long.motion;
    }
    M.mount(screen);
    var panel = document.querySelector(".m-panel");
    if (o.ae) {
      var tabs = panel.querySelectorAll(".m-tab");
      if (tabs.length === 3) tabs[2].parentNode.removeChild(tabs[2]);
    }
    if (W280) {
      panel.className += " m-w280";
      document.title = document.title.replace(/· 300$/, "· 280");
    }
    /* Addendum G (pattern 2e68bcf): the screen's one primary (violet) carries the shared Mod+Enter keycap
       M.kbd(M.KEY_PRIMARY); a button that mockup.js already gave one keeps it. R2 (designer P0-3): never on a danger or
       destructive action, never on a disabled one. M.dialog already decides its own keycaps. The other keys are listed in
       each screen's <meta name="mock-keys">. */
    var prim = panel.querySelectorAll(".m-btn-primary:not(.m-btn-destructive):not(.m-btn-disabled)");
    /* R3 (designer F-21): never on the confirm button of a confirm card (M.dialog gives the keycap to the safe button) */
    var inDialog = function (el) { for (var a = el; a && a !== panel; a = a.parentNode) if (/\b(m|ta|pc)-dialog\b/.test(a.className || "")) return true; return false; };
    for (var i = 0; i < prim.length; i++) if (!prim[i].querySelector(".m-kbd") && !inDialog(prim[i])) prim[i].insertAdjacentHTML("beforeend", M.kbd(M.KEY_PRIMARY));
    /* height probe for the group's own checks (render_all captures 2600 CSS px at most) */
    var probe = function () {
      var meta = document.createElement("meta");
      meta.name = "ta-height";
      meta.content = String(Math.round(panel.getBoundingClientRect().height));
      document.head.appendChild(meta);
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { setTimeout(probe, 60); });
    else setTimeout(probe, 300);
  };

  /* header pills for the states every tool screen shares (the pill, the notice and the button all name one condition) */
  TA.pillsNoClaude = { claude: "signed_out" };
  TA.pillsOff = { engine: "off", claude: "unchecked", host: "unlinked" };
  /* Hush and the Tidy undo work with Premiere alone: the app is off, Premiere is still linked */
  TA.pillsAppOff = { engine: "off", claude: "unchecked", host: "linked" };

  /* the no-Claude card of a tool screen: M.noClaude (one sentence, one button, one "What Claude sees" link).
     solo = the tool does not use Claude at all (Tidy, Hush, the gallery): no link, no hint, the button is secondary */
  TA.noClaude = function (textKey, o) {
    o = o || {};
    return M.slot(M.noClaude("signed_out", { text: t(textKey), sub: o.solo ? "" : undefined, noLink: !!o.solo, primary: !!o.primary }));
  };
  /* the service is off but the tool still works (Hush cuts pauses, Tidy undoes, Undo): Start is secondary, no support button */
  TA.partialOffline = function (hintKey) {
    return M.slot(M.offline({ hintKey: hintKey, primary: false, support: false }));
  };

  /* tool title: icon well, plain-language label (title role), brand name small (meta) */
  TA.title = function (icon, label, brand, o) {
    o = o || {};
    return '<div class="ta-title mt-2"><div class="m-verb-well">' + M.ico(icon, 20, "ink-text") + "</div>" +
      '<div class="ta-title-text"><div class="t-title">' + label + "</div>" +
      (brand ? '<div class="t-meta tx-muted">' + brand + "</div>" : "") + "</div>" + (o.end || "") + "</div>";
  };

  /* a row of track toggles (V1, A1 ...) */
  TA.tracks = function (list, o) {
    return '<div class="ta-wrap" style="margin-top:-8px">' + list.map(function (x) { return M.toggle(x[0], x[1], o).replace(/^<div class="/, '<div class="ta-wi '); }).join("") + "</div>";
  };

  /* field row: label (+ meta) and a value control at the end */
  TA.field = function (label, control, sub) {
    return '<div class="m-row mt-2"><div class="m-col m-grow"><div class="t-label">' + label + "</div>" +
      (sub ? '<div class="t-meta tx-muted">' + sub + "</div>" : "") + '</div><div class="ta-end ms-2">' + control + "</div></div>";
  };
  /* a small value box (an input showing a number + unit) */
  TA.value = function (v, o) {
    o = o || {};
    return '<div class="m-input' + (o.focus ? " m-input-focus" : "") + '" role="textbox" tabindex="0" style="width:' + (o.w || 88) + 'px"><span class="m-block t-body ' + (o.disabled ? "tx-disabled" : "tx-text") + '">' + M.ltr(v) + "</span></div>";
  };

  /* stats strip: items = [[value, label], ...]; the number is the shared stat role (Inter 600 20/28, AR 20/32) */
  TA.stats = function (items, cls) {
    return '<div class="ta-stats ' + (cls || "") + '">' + items.map(function (x) {
      return '<div class="ta-stat"><div class="ta-stat-in"><span class="t-stat">' + x[0] + '</span><span class="t-meta tx-muted">' + x[1] + "</span></div></div>";
    }).join("") + "</div>";
  };

  /* a backup, copy or file name read in full: an LTR isolate that wraps after a separator (M.path), on the inset well */
  TA.name = function (s) { return '<div class="m-inset">' + M.path(s) + "</div>"; };

  /* checkbox row whose name wraps (never cut). o: checked, name (html), sub, end, mono (name is a file name), disabled, focus */
  TA.checkrow = function (o) {
    var dis = !!o.disabled;
    var cls = "ta-checkrow" + (o.focus ? " ta-checkrow-focus" : "") + (dis ? " ta-checkrow-dis" : "");
    var box = '<span class="m-box' + (o.checked && !dis ? " m-box-on" : "") + '">' + (o.checked ? M.ico("check", 16, dis ? "ink-disabled" : "ink-on-light") : "") + "</span>";
    var name = o.mono ? '<div class="t-mono ta-wrapname">' + M.path(o.name) + "</div>" : '<div class="t-label">' + o.name + "</div>";
    return '<div class="' + cls + '" role="checkbox" tabindex="' + (dis ? -1 : 0) + '" aria-checked="' + !!o.checked + '">' + box +
      '<div class="ta-rowtext">' + name + (o.sub ? '<div class="t-meta tx-muted">' + o.sub + "</div>" : "") + "</div>" +
      (o.end ? '<div class="ta-rowend">' + o.end + "</div>" : "") + "</div>";
  };

  /* waveform: n columns; regions [[from, to, "sil"|"fil"], ...] in column indices; head = playhead column */
  TA.wave = function (o) {
    o = o || {};
    var n = o.n || 72, cols = "";
    for (var i = 0; i < n; i++) {
      var kind = "";
      (o.regions || []).forEach(function (r) { if (i >= r[0] && i <= r[1]) kind = r[2]; });
      var h = Math.round(10 + 40 * Math.abs(Math.sin(i * 0.61) * Math.cos(i * 0.23 + 1.3)) + 6 * Math.abs(Math.sin(i * 2.7)));
      if (kind === "sil") h = 2 + (i % 3);
      if (kind === "fil") h = 14 + (i % 4) * 3;
      if (i === o.head) cols += '<span class="ta-col ta-col-head"></span>';
      cols += '<span class="ta-col' + (kind ? " ta-col-" + kind : "") + '"><span class="ta-bar" style="height:' + h + 'px"></span></span>';
    }
    return '<div class="ta-wave' + (o.disabled ? " ta-wave-dis" : "") + '" aria-hidden="true">' + cols + "</div>";
  };
  TA.wavePlaceholder = function (text) {
    return '<div class="ta-wave ta-wave-empty"><span class="t-meta tx-muted tx-center" dir="' + (M.rtl ? "rtl" : "ltr") + '">' + text + "</span></div>";
  };
  TA.ruler = function (a, b, c) {
    return '<div class="ta-ruler mt-1"><span class="t-mono tx-muted">' + M.esc(a) + '</span><span class="m-spacer"></span><span class="t-mono tx-muted">' + M.esc(b) +
      '</span><span class="m-spacer"></span><span class="t-mono tx-muted">' + M.esc(c) + "</span></div>";
  };

  /* progress block (direction §12): sentence with "n of m" at the end, the bar, then elapsed + a ghost stop.
     o.paused = work stopped by a problem: amber pause icon, solid amber bar, no spinner (R2 designer P1-2) */
  TA.progress = function (text, pct, elapsed, stopLabel, o) {
    o = o || {};
    return '<div class="m-row">' + M.status(o.paused ? "paused" : "busy") + '<div class="t-body ms-2 m-grow">' + text + "</div></div>" +
      '<div class="mt-3">' + M.progress(pct, { paused: !!o.paused }) + "</div>" +
      '<div class="m-row mt-2"><span class="t-meta tx-muted">' + elapsed + '</span><span class="m-spacer"></span>' +
      (stopLabel ? M.btn(stopLabel, { kind: o.stopKind || "ghost", icon: "circle-stop" }) : "") + "</div>";
  };

  /* an Arabic run (as said) in either UI */
  TA.ar = function (s) { return '<span class="ar-run" dir="rtl" lang="ar">' + M.esc(s) + "</span>"; };
  /* status row: an icon and one meta line (what a check says, what is left out, where a file came from) */
  TA.row = function (iconHtml, html, cls) {
    return '<div class="ta-srow ' + (cls || "mt-2") + '">' + iconHtml + '<div class="t-meta ms-2 m-grow">' + html + "</div></div>";
  };
  TA.code = function (s) { return M.html(M.ltr(s, "lat code")); };
  TA.mono = function (s) { return M.html(M.mono(s)); };
})();
