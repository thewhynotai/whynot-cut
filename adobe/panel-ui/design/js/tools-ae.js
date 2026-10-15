/* WhyNot Cut 3.0 E-D2 mockups: helpers for the "tools + After Effects" screen group (P-13 to P-20, A-01 to A-04).
   Loaded after ../mockup.js. Emits only markup the UXP kit can paint (same rules as mockup.js): <div role> controls
   with a 2 px rest border equal to the fill, <span> chips, inline SVG coloured by .ink-* classes, physical margins.
   Components marked PROMOTE are candidates for mockup.js.
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
    /* Addendum G (pattern 2e68bcf): the screen's one primary (violet, or danger in a confirm sheet) carries the shared
       Mod+Enter keycap M.kbd(M.KEY_PRIMARY); a button that mockup.js already gave one keeps it. Dialog "keep" buttons
       carry Esc (TA.dialog). The other keys are listed in each screen's <meta name="mock-keys">. */
    /* R2 (designer P0-3): never on a danger or destructive action; the primary alone carries it */
    var prim = panel.querySelectorAll(".m-btn-primary:not(.m-btn-destructive):not(.m-btn-disabled)");
    for (var i = 0; i < prim.length; i++) if (!prim[i].querySelector(".m-kbd")) prim[i].insertAdjacentHTML("beforeend", M.kbd(M.KEY_PRIMARY));
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

  /* ---- Addendum G: no-Claude (one plain sentence, one button) ---- */
  TA.noClaude = function (textKey, o) {
    o = o || {};
    return M.notice("warn", t(textKey), { sub: t("p13.claude_window"), btn: { label: t("p13.open_claude"), icon: "external-link", primary: !!o.primary }, dismiss: false });
  };
  TA.pillsNoClaude = { claude: "signed_out" };

  /* back row: a start-aligned ghost button with the backward chevron (mirrors per language) */
  TA.back = function (label) {
    return '<div class="m-row">' + M.btn(label, { kind: "ghost", icon: M.rtl ? "chevron-right" : "chevron-left", flush: true }) + "</div>";
  };
  /* tool title: icon well, plain-language label (title role), brand name small (meta) */
  TA.title = function (icon, label, brand, o) {
    o = o || {};
    return '<div class="ta-title mt-2"><div class="m-verb-well">' + M.ico(icon, 20, "ink-text") + "</div>" +
      '<div class="ta-title-text"><div class="t-title">' + label + "</div>" +
      (brand ? '<div class="t-meta tx-muted">' + brand + "</div>" : "") + "</div>" + (o.end || "") + "</div>";
  };

  /* PROMOTE: segmented control. opts = [label...]; on = index; o.focus = index; o.disabled */
  TA.seg = function (opts, on, o) {
    o = o || {};
    var segs = opts.map(function (l, i) {
      var cls = "ta-seg-opt" + (i === on ? " ta-seg-on" : "") + (o.focus === i ? " ta-seg-focus" : "");
      return '<div class="' + cls + '" role="button" tabindex="' + (o.disabled ? -1 : 0) + '" aria-pressed="' + (i === on) + '"><span class="m-block">' + l + "</span></div>";
    }).join("");
    return '<div class="ta-seg' + (o.disabled ? " ta-seg-dis" : "") + '" role="group"' + (o.disabled ? ' aria-disabled="true"' : "") + ">" + segs + "</div>";
  };

  /* PROMOTE: radio row */
  TA.radio = function (label, on, o) {
    o = o || {};
    var cls = "ta-radio" + (o.focus ? " ta-radio-focus" : "") + (o.disabled ? " ta-radio-dis" : "");
    return '<div class="' + cls + '" role="radio" tabindex="' + (o.disabled ? -1 : 0) + '" aria-checked="' + !!on + '">' +
      '<span class="ta-dot' + (on ? " ta-dot-on" : "") + '">' + (on ? '<span class="ta-dot-in"></span>' : "") + "</span>" +
      '<div class="m-col m-grow ms-2"><div class="t-label">' + label + "</div>" + (o.sub ? '<div class="t-meta tx-muted">' + o.sub + "</div>" : "") + "</div>" +
      (o.end || "") + "</div>";
  };

  /* PROMOTE: toggle button for a track. state: "on" | "off" | "locked"; o.disabled, o.focus */
  TA.tog = function (label, state, o) {
    o = o || {};
    var on = state === "on", dis = !!o.disabled;
    var cls = "ta-tog" + (dis ? " ta-tog-dis" : on ? " ta-tog-on" : "") + (o.focus ? " ta-tog-focus" : "");
    var icon = state === "locked" ? M.ico("lock", 12, dis ? "ink-disabled" : "ink-warn") : M.ico(on ? "check" : "square", 12, dis ? "ink-disabled" : on ? "ink-text" : "ink-muted");
    return '<div class="' + cls + ' ta-wi" role="checkbox" tabindex="' + (dis ? -1 : 0) + '" aria-checked="' + on + '">' + icon + M.ltr(label) + "</div>";
  };
  TA.tracks = function (list, o) {
    return '<div class="ta-wrap" style="margin-top:-8px">' + list.map(function (x) { return TA.tog(x[0], x[1], o); }).join("") + "</div>";
  };

  /* PROMOTE: select control (secondary fill, trailing chevron-down) */
  TA.select = function (label, o) {
    o = o || {};
    var cls = "m-btn " + (o.disabled ? "m-btn-disabled" : "m-btn-secondary") + " ta-select" + (o.grow ? " ta-select-grow" : "") + (o.focus ? " m-btn-focus" : "") + " " + (o.cls || "");
    return '<div class="' + cls + '" role="button" aria-haspopup="listbox" tabindex="' + (o.disabled ? -1 : 0) + '"><span class="m-block">' + label + "</span>" +
      M.ico("chevron-down", 16, o.disabled ? "ink-disabled" : "ink-muted") + "</div>";
  };

  /* PROMOTE: slider; pct 0..100 */
  TA.slider = function (pct, o) {
    o = o || {};
    return '<div class="ta-slider' + (o.disabled ? " ta-slider-dis" : "") + '"><span class="ta-slider-fill" style="width:' + pct + '%"></span>' +
      '<span class="ta-thumb' + (o.focus ? " ta-thumb-focus" : "") + '" role="slider" tabindex="0" aria-valuenow="' + pct + '"></span><span class="ta-slider-rest"></span></div>';
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

  /* stats strip: items = [[value, label], ...] */
  TA.stats = function (items, cls) {
    return '<div class="ta-stats ' + (cls || "") + '">' + items.map(function (x) {
      return '<div class="ta-stat"><div class="ta-stat-in"><span class="ta-num">' + x[0] + '</span><span class="t-meta tx-muted">' + x[1] + "</span></div></div>";
    }).join("") + "</div>";
  };

  /* PROMOTE: checkbox row whose name wraps (never cut). o: checked, name (html), sub, end, mono, disabled, focus */
  TA.checkrow = function (o) {
    var dis = !!o.disabled;
    var cls = "ta-checkrow" + (o.focus ? " ta-checkrow-focus" : "") + (dis ? " ta-checkrow-dis" : "");
    var box = '<span class="m-box' + (o.checked && !dis ? " m-box-on" : "") + '">' + (o.checked ? M.ico("check", 16, dis ? "ink-disabled" : "ink-on-light") : "") + "</span>";
    var name = o.mono ? '<div class="t-mono ta-wrapname">' + M.esc(o.name) + "</div>" : '<div class="t-label">' + o.name + "</div>";
    return '<div class="' + cls + '" role="checkbox" tabindex="' + (dis ? -1 : 0) + '" aria-checked="' + !!o.checked + '">' + box +
      '<div class="ta-rowtext">' + name + (o.sub ? '<div class="t-meta tx-muted">' + o.sub + "</div>" : "") + "</div>" +
      (o.end ? '<div class="ta-rowend">' + o.end + "</div>" : "") + "</div>";
  };

  /* PROMOTE: section header control (opens or closes) */
  TA.sechead = function (label, count, open, o) {
    o = o || {};
    return '<div class="ta-sechead" role="button" tabindex="0" aria-expanded="' + !!open + '">' + M.ico(open ? "chevron-up" : "chevron-down", 16, "ink-muted") +
      '<div class="t-label ms-2 m-grow">' + label + "</div>" + (count ? '<div class="ta-end ms-2">' + count + "</div>" : "") + "</div>";
  };

  /* PROMOTE: confirm dialog (G6). o: title, changes [html...], backupLabel, backup (name) or nobackup (text),
     confirm (label), confirmIcon, keep (label), danger, focus */
  TA.dialog = function (o) {
    var list = o.changes.map(function (c) {
      return '<div class="ta-bullet mt-2">' + M.ico("circle-dashed", 16, "ink-muted") + '<div class="t-body ms-2 m-grow">' + c + "</div></div>";
    }).join("");
    var backup = o.backup
      ? '<div class="t-meta tx-muted mt-3">' + o.backupLabel + '</div><div class="m-row mt-1"><bdi dir="ltr" class="mono ta-monowrap">' + M.esc(o.backup) + "</bdi></div>"
      : '<div class="ta-bullet mt-3">' + M.status("error") + '<div class="t-body ms-2 m-grow">' + o.nobackup + "</div></div>";
    return '<div class="ta-dialog' + (o.danger ? " ta-dialog-danger" : "") + '" role="alertdialog">' +
      '<div class="m-row-top">' + M.status(o.danger ? "error" : "warn") + '<div class="t-label ms-2 m-grow">' + o.title + "</div></div>" +
      '<div class="t-meta tx-muted mt-2">' + o.changesLabel + "</div>" + list + backup +
      '<div class="m-col mt-4">' + M.btn(o.confirm, { kind: o.danger ? "danger" : "primary", block: true, icon: o.confirmIcon, focus: o.focus }) +
      '<div class="mt-2"></div>' + M.btn(o.keep, { kind: "secondary", block: true, kbd: "Esc" }) + "</div></div>";
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

  /* PROMOTE: stage list. stages = [[kind, label (html), meta (html)], ...]; kind ok | busy | pending | error */
  TA.stages = function (stages) {
    return stages.map(function (s, i) {
      return (i ? M.divider() : "") + '<div class="ta-stage">' + M.status(s[0]) +
        '<div class="m-col m-grow ms-2"><div class="t-label' + (s[0] === "pending" ? " tx-muted" : "") + '">' + s[1] + "</div>" +
        (s[3] ? '<div class="t-meta ' + (s[0] === "error" ? "tx-text" : "tx-muted") + '">' + s[3] + "</div>" : "") + "</div>" +
        (s[2] ? '<div class="ta-end ms-2"><span class="t-meta tx-muted">' + s[2] + "</span></div>" : "") + "</div>";
    }).join("");
  };

  /* progress block (direction §12): sentence with "n of m" at the end, the bar, then elapsed + a ghost stop */
  TA.progress = function (text, pct, elapsed, stopLabel, o) {
    o = o || {};
    return '<div class="m-row">' + M.status("busy") + '<div class="t-body ms-2 m-grow">' + text + "</div></div>" +
      '<div class="mt-3">' + M.progress(pct) + "</div>" +
      '<div class="m-row mt-2"><span class="t-meta tx-muted">' + elapsed + '</span><span class="m-spacer"></span>' +
      (stopLabel ? M.btn(stopLabel, { kind: o.stopKind || "ghost", icon: "circle-stop" }) : "") + "</div>";
  };

  /* list of "label · value" rows inside a card */
  TA.kv = function (rows) {
    return rows.map(function (r, i) {
      return (i ? M.divider() : "") + '<div class="m-row-top" style="padding:8px 0"><div class="t-meta tx-muted m-grow">' + r[0] + '</div><div class="t-label ms-2">' + r[1] + "</div></div>";
    }).join("");
  };

  TA.slot = function (html) { return html + '<div class="mt-4"></div>'; };
  TA.offline = function (primary) {
    return M.notice("error", t("p13.service.off"), { sub: t("p13.service.off.hint"), btn: { label: t("p13.start_service"), icon: "power", primary: primary !== false }, dismiss: false });
  };
  TA.stale = function () { return M.notice("warn", t(TA.AE ? "a01.stale" : "p13.stale"), { btn: { label: t("p13.check_again"), icon: "refresh-cw" } }); };
  /* value line: the time a result saved (G2-r1 decision; mock values, an engine data request) */
  TA.saved = function (html) { return '<div class="ta-bullet mt-2">' + M.ico("clock", 16, "ink-ok") + '<div class="t-label ms-2 m-grow">' + html + "</div></div>"; };
  /* trust line: what is created or changed, and that the originals stay untouched */
  TA.trust = function (html) { return '<div class="ta-bullet mt-2">' + M.ico("shield-check", 16, "ink-muted") + '<div class="t-meta tx-muted ms-2 m-grow">' + html + "</div></div>"; };
  TA.pillsOff = { engine: "off", claude: "unchecked", host: "unlinked" };
  /* Hush and the Tidy undo work with Premiere alone: the app is off, Premiere is still linked */
  TA.pillsAppOff = { engine: "off", claude: "unchecked", host: "linked" };
  TA.code = function (s) { return M.html(M.ltr(s, "lat code")); };
  TA.mono = function (s) { return M.html(M.mono(s)); };
  /* an Arabic run (as said) in either UI */
  TA.ar = function (s) { return '<span class="ar-run" dir="rtl" lang="ar">' + M.esc(s) + "</span>"; };
})();
