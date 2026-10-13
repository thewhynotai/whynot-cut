/* WhyNot Cut 3.0 E-D2 mockup runtime: query params, copy, icons and the shared components every screen mockup uses.
   URL: screens/<screen>.html?lang=ar|en&w=300|360|480&state=<state>[&capture=1]
   The components emit only markup the UXP kit can paint (direction §12): <div role="button"> controls, <span> chips,
   inline SVG coloured by .ink-* classes, physical margins (mockup.css swaps them under .m-rtl). The DOM order is the
   reading order; Arabic mirrors once through CSS direction on the panel root. Directional icons (chevrons) are
   swapped here, per language, never by a CSS transform. */
(function () {
  "use strict";
  var q = new URLSearchParams(location.search);
  var LANG = q.get("lang") === "ar" ? "ar" : "en";
  var WIDTHS = [300, 360, 480];
  var W = WIDTHS.indexOf(Number(q.get("w"))) >= 0 ? Number(q.get("w")) : 360;
  var CAPTURE = q.get("capture") === "1";
  var S = window.MOCK_STRINGS[LANG];
  var ICONS = window.MOCK_ICONS || {};
  var missing = [];

  var M = (window.M = { lang: LANG, w: W, rtl: LANG === "ar", D: window.MOCK_DATA, capture: CAPTURE });

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  M.esc = esc;

  /* A Latin run (letters, then words, digits, dots, hyphens) inside Arabic goes in <bdi dir="ltr" class="lat">. */
  var LATIN = /[A-Za-z][A-Za-z0-9.'_\-]*(?: [A-Za-z0-9][A-Za-z0-9.'_\-]*)*/g;
  function txt(s) {
    s = String(s);
    if (LANG !== "ar") return esc(s);
    var out = "", last = 0, m;
    LATIN.lastIndex = 0;
    while ((m = LATIN.exec(s))) {
      var run = m[0].replace(/[.\-_']+$/, "");
      out += esc(s.slice(last, m.index)) + '<bdi dir="ltr" class="lat' + (run.length <= 24 ? " nb" : "") + '">' + esc(run) + "</bdi>";
      last = m.index + run.length;
      LATIN.lastIndex = last;
    }
    return out + esc(s.slice(last));
  }
  M.txt = txt;
  M.html = function (h) { return { html: h }; };

  /* t(key, vars): the string for this language, escaped, Latin runs isolated; a var is text or M.html(markup). */
  function t(key, vars) {
    var s = S[key];
    if (s === undefined) { missing.push(key); return "[" + esc(key) + "]"; }
    var parts = s.split(/\{(\w+)\}/), out = "";
    for (var i = 0; i < parts.length; i++) {
      if (i % 2 === 0) out += txt(parts[i]);
      else {
        var v = vars ? vars[parts[i]] : undefined;
        out += v && typeof v === "object" ? v.html : txt(v === undefined ? "{" + parts[i] + "}" : v);
      }
    }
    return out;
  }
  M.t = t;
  M.raw = function (key) { return S[key]; };
  M.ltr = function (s, cls) { return '<bdi dir="ltr" class="' + (cls || "lat") + '">' + esc(s) + "</bdi>"; };
  M.mono = function (s) { return '<bdi dir="ltr" class="mono">' + esc(s) + "</bdi>"; };

  /* ---- icons ---- */
  function ico(name, size, ink, extra) {
    size = size || 16;
    var set = ICONS[name], d = set && set[String(size)];
    if (!d) { missing.push("icon:" + name + "@" + size); d = ""; }
    return '<svg class="m-ico m-ico-' + size + " " + (ink || "ink-text") + (extra ? " " + extra : "") +
      '" viewBox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="' + d + '"/></svg>';
  }
  M.ico = ico;
  /* "forward" chevron: points to the reading end (right in English, left in Arabic) */
  M.chev = function (ink, size) { return ico(LANG === "ar" ? "chevron-left" : "chevron-right", size || 16, ink || "ink-muted"); };
  var STATUS = {
    ok: ["circle-check", "ink-ok"], warn: ["triangle-alert", "ink-warn"], error: ["circle-x", "ink-error"],
    info: ["info", "ink-info"], pending: ["circle-dashed", "ink-muted"], busy: ["loader-circle", "ink-info"]
  };
  M.status = function (kind, size) {
    var s = STATUS[kind] || STATUS.info;
    return ico(s[0], size || 16, s[1], kind === "busy" ? "m-spin" : "");
  };

  /* ---- components ---- */
  M.btn = function (label, o) {
    o = o || {};
    var kind = o.disabled ? "m-btn-disabled" : "m-btn-" + (o.kind || "secondary");
    var cls = ["m-btn", kind, o.block ? "m-btn-block" : "", o.start ? "m-btn-start" : "", o.flush ? "m-btn-flush" : "", o.focus ? "m-btn-focus" : "", o.cls || ""].join(" ");
    var attrs = o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"';
    var icon = o.icon ? (o.icon === "busy" ? M.status("busy") : ico(o.icon, 16, "ink-text")) : "";
    return '<div class="' + cls + '" role="button"' + attrs + ">" + icon + '<span class="m-block">' + label + "</span></div>";
  };
  M.chip = function (tone, label, icon) {
    var ink = { ok: "ink-ok", warn: "ink-warn", error: "ink-error", info: "ink-info", neutral: "ink-muted" }[tone] || "ink-muted";
    return '<span class="m-chip m-chip-' + tone + '">' + (icon ? ico(icon, 12, ink) : "") + '<span class="m-block">' + label + "</span></span>";
  };
  M.monoChip = function (s) { return '<span class="m-chip m-chip-mono"><bdi dir="ltr" class="mono">' + esc(s) + "</bdi></span>"; };
  M.eyebrow = function (label, cls) { return '<div class="t-eyebrow ' + (cls || "") + '">' + label + "</div>"; };
  M.card = function (inner, cls) { return '<section class="m-card ' + (cls || "") + '">' + inner + "</section>"; };

  /* notice / error card (G5): icon, one white sentence (+ optional meta line), one button, dismiss */
  M.notice = function (kind, text, o) {
    o = o || {};
    var body = '<div class="t-body tx-text">' + text + "</div>";
    if (o.sub) body += '<div class="t-meta tx-muted mt-1">' + o.sub + "</div>";
    if (o.btn) body += '<div class="m-row mt-3">' + M.btn(o.btn.label, { kind: o.btn.primary ? "primary" : "secondary", icon: o.btn.icon, focus: o.btn.focus }) + "</div>";
    var x = o.dismiss === false ? "" :
      '<div class="m-x" role="button" tabindex="0" aria-label="' + esc(S["notice.dismiss"] || "Dismiss") + '">' + ico("x", 16, "ink-muted") + "</div>";
    return '<div class="m-notice m-notice-' + kind + ' ' + (o.cls || "") + '" role="' + (kind === "error" ? "alert" : "status") + '">' +
      M.status(kind) + '<div class="m-notice-body">' + body + "</div>" + x + "</div>";
  };

  M.empty = function (o) {
    return M.card(
      '<div class="m-empty">' +
        '<div class="m-well">' + ico(o.icon, 20, "ink-muted") + "</div>" +
        '<div class="t-label mt-3">' + o.title + "</div>" +
        (o.text ? '<div class="t-meta tx-muted mt-1">' + o.text + "</div>" : "") +
        (o.btn ? '<div class="m-row mt-4">' + o.btn + "</div>" : "") +
      "</div>", o.cls);
  };

  /* skeleton: bars inside line boxes of the content's own height */
  M.skel = function (pct, h) {
    return '<div class="m-skel-line' + (h ? " m-skel-line-" + h : "") + '"><span class="m-skel-bar" style="width:' + pct + '%"></span></div>';
  };

  M.verb = function (o) {
    var kind = (o.disabled ? "m-verb-disabled" : o.primary ? "m-verb-primary" : "m-verb-secondary") + (o.focus ? " m-verb-focus" : "");
    var ink = o.disabled ? "ink-disabled" : o.primary ? "ink-on-primary" : "ink-text";
    var attrs = o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"';
    return '<div class="m-verb ' + kind + ' ' + (o.cls || "") + '" role="button"' + attrs + ">" +
      '<div class="m-verb-well">' + ico(o.icon, 20, ink) + "</div>" +
      '<div class="m-verb-text"><div class="t-verb m-verb-title">' + o.title + '</div><div class="t-meta m-verb-sub">' + o.sub + "</div></div>" +
      '<div class="ms-2">' + M.chev(o.disabled ? "ink-disabled" : o.primary ? "ink-on-primary" : "ink-muted") + "</div></div>";
  };

  /* tool card (E-D3 r1): a solid #141414 control, radius 8. Plain-language label first, the brand name as the small
     line; the last result is kept even when the card is disabled (offline, error). */
  M.tool = function (o) {
    var dis = !!o.disabled;
    return '<div class="m-tool' + (dis ? " m-tool-disabled" : "") + '" role="button"' + (dis ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"') + ">" +
      ico(o.icon, 20, dis ? "ink-disabled" : "ink-text") +
      '<div class="m-col m-grow ms-3">' +
        '<div class="m-row"><div class="t-verb m-tool-title">' + o.name + '</div><span class="m-spacer"></span>' + (dis ? "" : o.chip || "") + "</div>" +
        '<div class="t-meta m-tool-brand">' + o.brand + "</div>" +
        '<div class="m-row-top mt-2"><div class="m-last-ico">' + M.status(o.lastKind || "ok", 12) + '</div><div class="t-meta tx-muted ms-1 m-grow">' + o.last + "</div></div>" +
      "</div>" +
      '<div class="m-row ms-2" style="align-self:center">' + M.chev(dis ? "ink-disabled" : "ink-muted") + "</div>" +
      "</div>";
  };

  M.divider = function () { return '<span class="m-divider"></span>'; };
  M.checkbox = function (label, checked, focus) {
    return '<div class="m-checkrow' + (focus ? " m-btn-focus" : "") + '" role="checkbox" tabindex="0" aria-checked="' + !!checked + '">' +
      '<span class="m-box' + (checked ? " m-box-on" : "") + '">' + (checked ? ico("check", 16, "ink-on-light") : "") + "</span>" +
      '<div class="t-label ms-2 m-grow">' + label + "</div></div>";
  };

  M.li = function (icon, label, end) {
    return '<div class="m-li" role="button" tabindex="0">' + ico(icon, 16, "ink-muted") + '<div class="t-label ms-2 m-grow">' + label + "</div>" + (end || "") + '<div class="ms-2">' + M.chev() + "</div></div>";
  };

  /* step strip: 7 segments + "Step n of 7 · name"; states: done / run / wait / fail / pend */
  M.steps = function (states, current, statusKind) {
    var keys = ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"];
    var segs = states.map(function (s) { return '<span class="m-stepseg' + (s === "pend" ? "" : " m-stepseg-" + s) + '"></span>'; }).join("");
    /* plain text in this release (decision 6): no role, no chevron */
    return '<div class="m-steps"><div class="m-stepbar" aria-hidden="true">' + segs + "</div>" +
      '<div class="m-row mt-2">' + M.status(statusKind || "info", 12) +
      '<div class="t-meta tx-muted ms-1 m-grow">' + t("steps.position", { n: current + 1, of: 7, name: S["step." + keys[current]] }) + "</div></div></div>";
  };

  M.progress = function (pct) {
    return '<div class="m-track"><span class="m-fill" style="width:' + pct + '%"></span></div>';
  };

  M.input = function (placeholder, o) {
    o = o || {};
    return '<div class="m-input' + (o.textarea ? " m-textarea" : "") + (o.focus ? " m-input-focus" : "") + '" role="textbox" tabindex="0">' +
      '<span class="m-block ' + (o.value ? "tx-text" : "tx-muted") + ' t-body">' + (o.value || placeholder) + "</span></div>";
  };

  /* ---- shell: header (G1-G3), hairline, tabs (G4), scroll, log row (G7), footer (G8) ---- */
  var PILL = {
    engine: { running: ["ok", "pill.engine.running"], off: ["error", "pill.engine.off"], starting: ["pending", "pill.engine.starting"], noanswer: ["warn", "pill.engine.noanswer"] },
    claude: { ready: ["ok", "pill.claude.ready"], unchecked: ["pending", "pill.claude.unchecked"], signed_out: ["warn", "pill.claude.signed_out"] },
    host: { linked: ["ok", "pill.host.linked"], unlinked: ["error", "pill.host.unlinked"], checking: ["pending", "status.pending"] }
  };
  /* E-D3 r1 #2 / editor #3: the name (key word) shows from 360 px, and at 300 px on any pill that is not ok, so a
     failing pill always says WHAT failed. Row 3 may wrap to two lines instead of dropping names. */
  function pills(p) {
    p = p || {};
    var out = "";
    ["engine", "claude", "host"].forEach(function (k) {
      var st = PILL[k][p[k] || ({ engine: "running", claude: "ready", host: "linked" })[k]];
      var showKey = W >= 360 || st[0] !== "ok";
      var key = showKey ? '<span class="m-pill-key">' + t("pill." + k) + "</span> " : "";
      out += '<div class="m-pill">' + M.status(st[0], 12) + '<span class="m-pill-txt">' + key + t(st[1]) + "</span></div>";
    });
    return '<div class="m-pills">' + out + "</div>";
  }
  /* Needs-you badge (E-D3 r1 editor #8, decision 9): ONE count, the same number as the Edit tab count; a control
     (div role=button, 2 px rest border) with a forward chevron, so it reads as "opens the list". */
  function badge(n) {
    if (!n || n <= 0) return "";
    var count = n > 99 ? "99+" : String(n);
    var chev = ico(LANG === "ar" ? "chevron-left" : "chevron-right", 12, "ink-on-accent");
    var inner = W >= 360
      ? '<span class="m-badge"><span class="m-block">' + t("needs.label") + '</span><span class="m-badge-count ms-1">' + M.ltr(count, "lat") + "</span>" + chev + "</span>"
      : '<span class="m-badge m-badge-solo"><span class="m-badge-count">' + M.ltr(count, "lat") + "</span>" + chev + "</span>";
    return '<div class="m-badge-hit me-1" role="button" tabindex="0" aria-label="' + esc((S["needs.open"] || "").replace("{n}", count)) + '">' + inner + "</div>";
  }
  function langSwitch() {
    var seg = function (l) {
      var on = l === LANG;
      return '<div class="m-seg' + (l === "ar" ? " m-seg-ar" : "") + (on ? " m-seg-on" : "") + '" role="button" tabindex="0" lang="' + l +
        '" aria-pressed="' + on + '" aria-label="' + esc(S["lang." + l]) + '">' + esc(S["lang." + l + ".short"]) + "</div>";
    };
    return '<div class="m-lang" role="group">' + seg("ar") + seg("en") + "</div>";
  }
  function header(o) {
    var D = M.D;
    var ctx = o.noclient
      ? '<span class="m-ctx t-meta tx-muted">' + t("status.novideo") + "</span>"
      : '<div class="m-ctxrow t-meta"><span class="m-ctx tx-muted">' + txt(D.client) + '</span><span class="m-ctx-sep tx-muted">·</span>' +
        '<span class="m-ctx-item tx-text">' + M.ltr(D.item) + "</span></div>";
    /* E-D3 r1: the pills sit on row 3 at every width (the longer plain names no longer fit beside client · item at 480) */
    return '<header class="m-hdr">' +
      '<div class="m-hdr-r1 m-gut"><img class="m-mono" src="../../../premiere-uxp/icons/dark/icon-48.png" alt="" width="20" height="20">' +
        '<span class="m-wordmark ms-2">' + M.ltr(S["product.name"], "wm") + '</span><span class="m-spacer"></span>' + badge(o.needs) + langSwitch() + "</div>" +
      '<div class="m-hdr-r2 m-gut">' + ctx + "</div>" +
      '<div class="m-hdr-r3 m-gut">' + pills(o.pills) + "</div>" +
      "</header>" +
      '<div class="m-hairline" aria-hidden="true"></div>';
  }
  function tabs(active, editCount) {
    var one = function (k) {
      var c = editCount > 99 ? "99+" : String(editCount);
      var count = k === "edit" && editCount ? '<span class="m-tab-count">' + M.ltr(c) + "</span>" : "";
      return '<div class="m-tab' + (k === active ? " m-tab-on" : "") + '" role="tab" tabindex="0" aria-selected="' + (k === active) + '"><span class="m-block">' + t("tab." + k) + "</span>" + count + "</div>";
    };
    return '<div class="m-tabs" role="tablist">' + one("home") + one("edit") + one("tools") + "</div>";
  }
  function logRow(n) {
    return '<span class="m-divider"></span><div class="m-logwrap m-gut"><div class="m-logrow" role="button" tabindex="0" aria-expanded="false">' + M.chev("ink-muted") +
      '<span class="t-label ms-1">' + t("log.toggle") + '</span><span class="m-spacer"></span><span class="t-meta">' + t("log.lines", { n: n }) + "</span></div></div>";
  }
  function footer() {
    return '<footer class="m-footer"><bdi dir="ltr" class="m-footer-txt">' + esc(S["footer.powered"]) + "</bdi></footer>";
  }

  /* ---- mount: one screen, one state ---- */
  M.mount = function (screen) {
    var state = q.get("state");
    var valid = screen.states.indexOf(state) >= 0;
    if (!valid) state = screen.defaultState || screen.states[0];
    if (state === "long") for (var k in M.D.long) M.D[k] = M.D.long[k];
    var view = screen.build(state);
    if (state === "long") view.needs = M.D.needs;
    /* one count: the badge and the Edit tab show the same number (decision 9) */
    view.editCount = view.needs || 0;
    var root = document.documentElement;
    root.lang = LANG;
    root.dir = M.rtl ? "rtl" : "ltr";
    if (CAPTURE) root.className += " m-capture";
    document.title = screen.id + " " + state + " · " + LANG + " · " + W;

    var panel = document.createElement("div");
    panel.className = "m-panel m-w" + W + (M.rtl ? " m-rtl" : "");
    panel.setAttribute("dir", M.rtl ? "rtl" : "ltr");
    panel.innerHTML =
      header(view) +
      (view.tab ? tabs(view.tab, view.editCount) : "") +
      '<main class="m-scroll m-gut" id="scroll">' + view.body + "</main>" +
      (view.bar ? '<div class="m-actionbar m-gut">' + view.bar + "</div>" : "") +
      logRow(view.log || M.D.log) + footer();
    document.body.innerHTML = "";
    document.body.appendChild(panel);
    if (!CAPTURE) document.body.appendChild(nav(screen, state));
    check(panel, state, valid);
  };

  /* a small state switcher beside the panel for people browsing the files (not part of the product, never captured) */
  function nav(screen, state) {
    var box = document.createElement("div");
    box.setAttribute("style", "display:flex;flex-direction:column;margin:0 0 0 24px;padding:16px;font:12px/18px Inter,Segoe UI,sans-serif;color:#ddd;direction:ltr;text-align:left");
    var link = function (k, v, label, on) {
      var p = new URLSearchParams(location.search); p.set(k, v);
      return '<a style="color:' + (on ? "#fff" : "#9D6BFF") + ";margin:0 8px 0 0;font-weight:" + (on ? 600 : 400) + '" href="?' + p.toString() + '">' + label + "</a>";
    };
    var html = "<div style='margin:0 0 8px 0;font-weight:600'>" + screen.id + " " + esc(screen.name) + "</div><div>";
    screen.states.forEach(function (s) { html += link("state", s, s, s === state); });
    html += "</div><div style='margin:8px 0 0 0'>" + link("lang", "en", "EN", LANG === "en") + link("lang", "ar", "AR", LANG === "ar") + "</div><div>";
    WIDTHS.forEach(function (w) { html += link("w", w, w, w === W); });
    box.innerHTML = html + "</div>";
    document.body.style.flexDirection = "row";
    return box;
  }

  /* self-check for _build/render_all.py (read with --dump-dom): direction, mirroring, sideways overflow, copy */
  function check(panel, state, valid) {
    var done = function () {
      var pr = panel.getBoundingClientRect(), mid = pr.left + pr.width / 2;
      var side = function (el) { if (!el) return "none"; var r = el.getBoundingClientRect(); return r.left + r.width / 2 < mid ? "left" : "right"; };
      var over = 0, worst = "";
      var clipped = function (el) {
        for (var a = el.parentElement; a && a !== panel; a = a.parentElement) if (getComputedStyle(a).overflowX === "hidden") return true;
        return false;
      };
      panel.querySelectorAll("*").forEach(function (el) {
        if (clipped(el)) return;
        var r = el.getBoundingClientRect();
        if (!r.width || !r.height) return;
        if (r.right > pr.right + 0.5 || r.left < pr.left - 0.5) { over++; if (!worst) worst = el.className && el.className.baseVal === undefined ? String(el.className) : el.tagName; }
      });
      var fontsOk = true;
      if (document.fonts && document.fonts.check) {
        fontsOk = document.fonts.check("700 15px Syne") && document.fonts.check("400 13px Inter") &&
          (LANG !== "ar" || document.fonts.check("400 14px 'IBM Plex Sans Arabic'"));
      }
      var meta = document.createElement("meta");
      meta.name = "mock-check";
      meta.content = ["state=" + (valid ? state : "invalid"), "lang=" + LANG, "w=" + Math.round(pr.width), "dir=" + getComputedStyle(panel).direction,
        "mono=" + side(panel.querySelector(".m-mono")), "tab1=" + side(panel.querySelector(".m-tab")),
        "overflow=" + over, "worst=" + worst.replace(/[;=]/g, " "), "fonts=" + (fontsOk ? "ok" : "fallback"),
        "missing=" + missing.join(",")].join(";");
      document.head.appendChild(meta);
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { setTimeout(done, 50); });
    else setTimeout(done, 300);
  }
})();
