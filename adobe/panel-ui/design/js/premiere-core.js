/* WhyNot Cut 3.0 E-D2, round 2: helpers for the Premiere core group (P-02, P-04 to P-12, P-21, P-22). Loaded after
   ../mockup.js and ../strings/premiere-core.js. Emits only markup the UXP kit can paint (div role=button controls,
   <span> chips, inline SVG coloured by .ink-* classes, physical margins).
   R2: everything the shell now owns is used from M (notice, slot, offline / noClaude / stale / noNet, dialog, radio,
   tile / media, listrow, stages, bullet, back, trust / saved, logline, path / mid). What is left here is group-only:
   - PC.code / PC.title / PC.acts: an item code in a sentence, title + sub, a wrapping row of buttons (280 px safe);
   - PC.pick: the selectable list row of the client and clip pickers (a control, not a plain row);
   - PC.key / PC.kbtn / PC.k: keycaps through the shell's M.kbd (never on a danger button: M.btn refuses it);
   - PC.info / PC.iconrow: an info line and an icon + sentence row built on the shell's .m-saved row;
   - PC.checkbox: a checkbox row that can be disabled; PC.scene: the mock video frame drawn inside M.media;
   - PC.indet: the indeterminate progress bar (G9);
   - PC.mount: the pill values the shell's map lacks (view.pillx). */
(function () {
  "use strict";
  var M = window.M, t = M.t;
  var q = new URLSearchParams(location.search);
  var PC = (window.PC = { state: q.get("state"), D: window.PC_DATA });
  if (PC.state === "long") for (var k in PC.D.long) PC.D[k] = PC.D.long[k];

  /* a long file name breaks only at "_" (R2 designer P2-9); a short code never breaks. In a sentence only. */
  function soft(s) { return M.esc(s).replace(/(_)/g, "$1<wbr>"); }
  PC.code = function (s) {
    return String(s).length <= 12 ? M.html(M.ltr(s, "lat code pc-nb")) : M.html('<bdi dir="ltr" class="lat code pc-cw">' + soft(s) + "</bdi>");
  };
  /* a name in a row that must stay on one line: middle ellipsis keeps the start and the end */
  PC.name = function (s, max) { return M.html(M.ltr(M.mid(String(s), max || 22), "lat code pc-nb")); };
  PC.title = function (title, sub) {
    return '<div class="t-title">' + title + "</div>" + (sub ? '<div class="t-body tx-muted mt-1">' + sub + "</div>" : "");
  };
  /* buttons that wrap to a second line instead of overflowing (280 px safe) */
  PC.acts = function (btns, cls) {
    return '<div class="pc-model-acts ' + (cls || "") + '">' + btns.map(function (b) { return '<div class="m-row me-2 mt-2">' + b + "</div>"; }).join("") + "</div>";
  };
  /* selectable row (control): o = {icon, title, sub, sub2, on, disabled, focus, end} */
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
  /* an info line (12 px info icon + meta), and an icon + sentence row (the shell's .m-saved row) */
  PC.info = function (html, cls) {
    return '<div class="m-saved ' + (cls || "") + '">' + M.status("info") + '<div class="t-meta tx-muted ms-2 m-grow">' + html + "</div></div>";
  };
  PC.iconrow = function (iconHtml, html, cls) {
    return '<div class="m-saved ' + (cls || "") + '">' + iconHtml + '<div class="t-body ms-2 m-grow">' + html + "</div></div>";
  };
  /* checkbox row; the shell's M.checkbox has no disabled form */
  PC.checkbox = function (label, checked, o) {
    o = o || {};
    return '<div class="m-checkrow' + (o.focus ? " m-btn-focus" : "") + (o.disabled ? " pc-chk-dis" : "") + '" role="checkbox"' +
      (o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"') + ' aria-checked="' + !!checked + '">' +
      '<span class="m-box' + (checked ? " m-box-on" : "") + '">' + (checked ? M.ico("check", 16, o.disabled ? "ink-disabled" : "ink-on-light") : "") + "</span>" +
      '<div class="t-label ms-2 m-grow' + (o.disabled ? " tx-disabled" : "") + '">' + label + "</div></div>";
  };
  /* indeterminate progress (G9) */
  PC.indet = function () { return '<span class="pc-indet"></span>'; };

  /* ---- keyboard hints (Addendum G2) use the shell's keycap (M.kbd) and its OS switch (?os=win shows Ctrl).
     PC.k maps a short spec to the OS form: "enter" = the primary (M.KEY_PRIMARY), "mod+X" = Cmd/Ctrl + X, else as is. */
  PC.k = function (spec) {
    if (spec === "enter") return M.KEY_PRIMARY;
    if (spec.indexOf("mod+") === 0) return (M.OS === "win" ? "Ctrl " : "⌘ ") + spec.slice(4);
    return spec;
  };
  PC.key = function (spec) { return M.kbd(PC.k(spec)); };
  /* a button with a keycap; never on a disabled or busy button (M.btn itself refuses a keycap on a danger button) */
  PC.kbtn = function (label, spec, o) {
    o = o || {};
    if (!o.disabled && !o.busy) o.kbd = PC.k(spec);
    return M.btn(label, o);
  };

  /* P-08: a mock video frame (9:16) drawn inside M.media. tone 0..3 picks the scene colours; the person is a plain
     head and shoulders shape; caption bars sit in the lower third. o.safe draws the safe-area outline round the
     captions; o.bad draws the offending caption box running past that outline. */
  PC.scene = function (tone, w, o) {
    o = o || {};
    var cap1 = Math.round(w * 0.62), cap2 = Math.round(w * 0.42), hd = Math.round(w * 0.3), bw = Math.round(w * 0.6), bh = Math.round(w * 0.24);
    var caps = o.bad
      ? '<span class="m-media-bad pc-bad-wide"></span><span class="pc-cap pc-cap-2" style="width:' + cap2 + 'px"></span>'
      : '<span class="pc-cap" style="width:' + cap1 + 'px"></span><span class="pc-cap pc-cap-2" style="width:' + cap2 + 'px"></span>';
    var safe = o.safe ? '<div class="m-media-safe">' + caps + "</div>" : '<div class="pc-scene-caps">' + caps + "</div>";
    return '<div class="pc-scene pc-scene-' + (tone % 4) + '"><div class="pc-scene-fig"><span class="pc-head" style="width:'+hd+'px;height:'+hd+'px"></span><span class="pc-body" style="width:'+bw+'px;height:'+bh+'px"></span></div>' + safe + "</div>";
  };

  /* ---- after-mount patch: pill values the shell's map lacks (view.pillx; the shell then keeps the three pills). ---- */
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
