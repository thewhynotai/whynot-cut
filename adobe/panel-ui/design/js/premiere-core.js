/* WhyNot Cut 3.0 E-D2: helpers for the Premiere core group (P-02, P-04 to P-12, P-21, P-22). Loaded after
   ../mockup.js and ../strings/premiere-core.js. Emits only markup the UXP kit can paint (div role=button controls,
   <span> chips, inline SVG coloured by .ink-* classes, physical margins). Components marked SHARED are proposed for
   promotion into mockup.js:
   - PC.notice: M.notice plus a disabled / busy fix button (P-11 "working") and a primary/secondary choice;
   - PC.dialog: the confirm dialog (G6) with or without backup;
   - PC.logBody: the open log drawer (G7), shown only in Settings > Details for support (G2-r1 owner decision e);
   - PC.mount after-mount patch: pill values the shell's map lacks;
   - PC.key / PC.kbtn: keycaps through the shell's M.kbd; PC.trust / PC.saved: trust and time-saved lines; PC.noClaude;
   - PC.pill: header pill values the shell's PILL map does not carry yet (Claude not installed / update / working /
     waiting), patched after M.mount;
   - PC.back, PC.row, PC.pick, PC.radio, PC.monobox, PC.acts, PC.indet. */
(function () {
  "use strict";
  var M = window.M, t = M.t;
  var q = new URLSearchParams(location.search);
  var PC = (window.PC = { state: q.get("state"), D: window.PC_DATA });
  if (PC.state === "long") for (var k in PC.D.long) PC.D[k] = PC.D.long[k];

  /* back link: a ghost button with the arrow that points to the start of the reading direction */
  PC.back = function (label) {
    return '<div class="pc-back">' + M.btn(label, { kind: "ghost", icon: M.rtl ? "arrow-right" : "arrow-left", flush: true }) + "</div>";
  };
  /* an item code inside a sentence: the UI face (Syne's zero reads as "o"); short codes never break */
  /* long names get soft breaks after _ - . so they wrap at a separator, not mid-word */
  function soft(s) { return M.esc(s).replace(/([_.\-])/g, "$1<wbr>"); }
  PC.code = function (s) {
    return String(s).length <= 12 ? M.html(M.ltr(s, "lat code pc-nb")) : M.html('<bdi dir="ltr" class="lat code pc-cw">' + soft(s) + "</bdi>");
  };
  /* a mono name inside a sentence that may be long (sequence, file): wraps at a separator, mid-word only when one part is wider than the line */
  PC.monoWrap = function (s) { return M.html('<bdi dir="ltr" class="mono pc-wrap">' + soft(s) + "</bdi>"); };
  PC.title = function (title, sub) {
    return '<div class="t-title">' + title + "</div>" + (sub ? '<div class="t-body tx-muted mt-1">' + sub + "</div>" : "");
  };
  /* a path or file name the editor reads: mono, LTR, wraps anywhere, never cut */
  PC.monobox = function (s, cls) {
    return '<div class="m-inset ' + (cls || "") + '"><bdi dir="ltr" class="mono pc-wrap">' + soft(s) + "</bdi></div>";
  };
  /* buttons that wrap to a second line instead of overflowing (280 px safe) */
  PC.acts = function (btns, cls) {
    return '<div class="pc-model-acts ' + (cls || "") + '">' + btns.map(function (b) { return '<div class="m-row me-2 mt-2">' + b + "</div>"; }).join("") + "</div>";
  };
  /* static info row: icon html, title, sub, end html */
  PC.row = function (ico, title, sub, end, cls) {
    return '<div class="pc-row ' + (cls || "") + '">' + ico + '<div class="pc-row-text"><div class="t-label">' + title + "</div>" +
      (sub ? '<div class="t-meta tx-muted">' + sub + "</div>" : "") + "</div>" + (end ? '<div class="pc-row-end">' + end + "</div>" : "") + "</div>";
  };
  /* selectable row (control): o = {icon, title, sub, sub2, on, disabled, focus, end, chev} */
  PC.pick = function (o) {
    var cls = "pc-pick" + (o.disabled ? " pc-pick-disabled" : o.on ? " pc-pick-on" : "") + (o.focus ? " pc-pick-focus" : "");
    var ink = o.disabled ? "ink-disabled" : o.on ? "ink-text" : "ink-muted";
    var attrs = o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"';
    var end = o.end !== undefined ? o.end : M.chev(ink);
    return '<div class="' + cls + '" role="button"' + attrs + (o.on ? ' aria-current="true"' : "") + ">" + M.ico(o.icon, 16, ink) +
      '<div class="pc-row-text"><div class="t-label">' + o.title + "</div>" +
      (o.sub ? '<div class="t-meta tx-muted">' + o.sub + "</div>" : "") + (o.sub2 ? '<div class="t-meta tx-muted">' + o.sub2 + "</div>" : "") + "</div>" +
      (end ? '<div class="pc-pick-chev">' + end + "</div>" : "") + "</div>";
  };
  PC.radio = function (label, sub, on, o) {
    o = o || {};
    var cls = "pc-radio" + (o.disabled ? " pc-radio-disabled" : "") + (o.focus ? " pc-radio-focus" : "");
    return '<div class="' + cls + '" role="radio" aria-checked="' + !!on + '"' + (o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"') + ">" +
      '<span class="pc-dot' + (on ? " pc-dot-on" : "") + '">' + (on ? '<span class="pc-dot-in"></span>' : "") + "</span>" +
      '<div class="pc-row-text"><div class="t-label">' + label + "</div>" + (sub ? '<div class="t-meta tx-muted">' + sub + "</div>" : "") + "</div></div>";
  };
  /* a trust line ("what this creates or changes; what stays untouched") or a time-saved line: 12 px icon + meta */
  PC.trust = function (html, icon, ink, cls) {
    return '<div class="pc-trust ' + (cls || "") + '"><div class="m-last-ico">' + M.ico(icon || "circle-check", 12, ink || "ink-ok") + '</div>' +
      '<div class="t-meta tx-muted ms-1 m-grow">' + html + "</div></div>";
  };
  PC.saved = function (html, cls) { return PC.trust(html, "clock", "ink-info", cls); };
  /* the no-Claude card (Addendum G2 state): one plain sentence, whose account / what it costs / what it reads, one
     button. o = {signedOut, primary, sub} */
  PC.noClaude = function (o) {
    o = o || {};
    return PC.notice("warn", t(o.signedOut ? "p02.claude.signed_out" : "p02.claude.closed"), {
      sub: o.sub || t("p02.claude.why"),
      btn: { label: t("action.open_claude"), icon: o.signedOut ? "log-in" : "external-link", primary: o.primary !== false }, dismiss: false });
  };
  /* indeterminate progress (G9) */
  PC.indet = function () { return '<span class="pc-indet"></span>'; };

  /* notice / error card (G5) with a disabled or busy button. o = {sub, btn: {label, icon, primary, disabled, busy, focus}, dismiss} */
  PC.notice = function (kind, text, o) {
    o = o || {};
    var body = '<div class="t-body tx-text">' + text + "</div>";
    if (o.sub) body += '<div class="t-meta tx-muted mt-1">' + o.sub + "</div>";
    if (o.extra) body += o.extra;
    if (o.btn) {
      var b = o.btn;
      var kk = b.key === undefined ? (b.primary ? "enter" : "") : b.key;
      var bo = { kind: b.primary ? "primary" : "secondary", icon: b.busy ? "busy" : b.icon, disabled: b.disabled || b.busy, focus: b.focus };
      body += '<div class="m-row mt-3">' + (kk ? PC.kbtn(b.label, kk, bo) : M.btn(b.label, bo)) + "</div>";
    }
    var x = o.dismiss === false ? "" :
      '<div class="m-x" role="button" tabindex="0" aria-label="' + M.esc(M.raw("notice.dismiss")) + '">' + M.ico("x", 16, "ink-muted") + "</div>";
    return '<div class="m-notice m-notice-' + kind + " " + (o.cls || "") + '" role="' + (kind === "error" ? "alert" : "status") + '">' +
      M.status(kind) + '<div class="m-notice-body">' + body + "</div>" + x + "</div>";
  };

  /* confirm dialog (G6). o = {title, text, changes: [html], backup: name | null, nobackup: html, confirm: {label, icon,
     danger, disabled, busy, focus}, keep, hint} */
  PC.dialog = function (o) {
    var c = o.confirm;
    var list = (o.changes || []).map(function (h) {
      return '<div class="pc-bullet">' + M.ico("check", 16, "ink-muted") + '<div class="t-body ms-2 m-grow">' + h + "</div></div>";
    }).join("");
    /* o.reversible: the action can be undone another way (e.g. download a model again): warn tone, no red */
    var safe = !!(o.backup || o.reversible);
    var backup = o.reversible && !o.backup
      ? '<div class="mt-4">' + PC.trust(o.reversible, "download", "ink-info") + "</div>"
      : o.backup
      ? '<div class="t-label mt-4">' + t("p09.dlg.backup") + '</div><div class="t-meta tx-muted mt-1">' + t("p09.dlg.backup_text") + "</div>" +
        '<div class="mt-2">' + PC.monobox(o.backup) + "</div>"
      : '<div class="m-row-top mt-4">' + M.status("error") + '<div class="t-body ms-2 m-grow">' + o.nobackup + "</div></div>";
    if (o.untouched) backup += '<div class="mt-3">' + PC.trust(o.untouched, "circle-check", "ink-ok") + "</div>";
    var confirm = PC.kbtn(c.label, "enter", { kind: c.danger ? "danger" : "primary", block: true, icon: c.busy ? "busy" : c.icon, disabled: c.disabled || c.busy, focus: c.focus });
    return '<div class="pc-dialog' + (safe ? "" : " pc-dialog-danger") + '" role="alertdialog">' +
      '<div class="m-row-top">' + M.status(safe ? "warn" : "error") + '<div class="t-label ms-2 m-grow">' + o.title + "</div></div>" +
      (o.text ? '<div class="t-body mt-2">' + o.text + "</div>" : "") +
      '<div class="t-label mt-4">' + t("p09.dlg.changes") + "</div>" + list + backup +
      '<div class="pc-stack mt-4">' + confirm + '<div class="mt-2"></div>' + PC.kbtn(o.keep, "Esc", { kind: "secondary", block: true }) + "</div>" +
      (o.hint ? '<div class="t-meta tx-muted mt-2">' + o.hint + "</div>" : "") + "</div>";
  };

  /* ---- keyboard hints (Addendum G2) use the shell's keycap (M.kbd, .m-kbd) and its OS switch (?os=win shows Ctrl).
     PC.k maps a short spec to the OS form: "enter" = the primary (M.KEY_PRIMARY), "mod+X" = Cmd/Ctrl + X, else as is. */
  PC.k = function (spec) {
    if (spec === "enter") return M.KEY_PRIMARY;
    if (spec.indexOf("mod+") === 0) return (M.OS === "win" ? "Ctrl " : "⌘ ") + spec.slice(4);
    return spec;
  };
  PC.key = function (spec) { return M.kbd(PC.k(spec)); };
  /* a button with a keycap; never on a disabled or busy button */
  PC.kbtn = function (label, spec, o) {
    o = o || {};
    if (!o.disabled && !o.busy) o.kbd = PC.k(spec);
    return M.btn(label, o);
  };

  /* the log, shown only in Settings > Details for support (G2-r1 owner decision e) */
  PC.logBody = function (lines) {
    var n = lines ? lines.length : 0;
    var body = n
      ? lines.map(function (l) {
          return '<div class="pc-logline t-mono"><span class="pc-logtime">' + M.esc(l[0]) + '</span><span class="pc-logtext' +
            (l[2] ? " pc-logtext-" + l[2] : "") + '">' + M.esc(l[1]) + "</span></div>";
        }).join("")
      : '<div class="t-meta tx-muted">' + t("p11.log.empty") + "</div>";
    return '<div class="pc-logbody" role="log">' + body + "</div>";
  };

  /* ---- after-mount patch: pill values the shell's map lacks (view.pillx; the shell then keeps the three pills).
     The shell itself now drops the log row and collapses a healthy status to "All set" (Addendum G). ---- */
  function pills(panel, p) {
    var els = panel.querySelectorAll(".m-pill"), order = ["engine", "claude", "host"];
    order.forEach(function (k, i) {
      if (!p[k] || !els[i]) return;
      var kind = p[k][0];
      var key = M.w >= 360 || kind !== "ok" ? '<span class="m-pill-key">' + t("pill." + k) + "</span> " : "";
      els[i].innerHTML = M.status(kind, 12) + '<span class="m-pill-txt">' + key + p[k][1] + "</span>";
    });
  }

  PC.mount = function (screen) {
    var view = null, build = screen.build;
    screen.build = function (s) { view = build(s); return view; };
    M.mount(screen);
    var panel = document.querySelector(".m-panel");
    if (!panel || !view) return;
    if (view.pillx) pills(panel, view.pillx);
    /* manual 280 px check (not part of render_all): ?w=300&pc280=1 draws the 300 layout at 280 */
    if (q.get("pc280") === "1") panel.style.width = "280px";
  };
})();
