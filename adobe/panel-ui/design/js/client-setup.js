/* WhyNot Cut 3.0 J-T9a: helpers for the "Set up a client" group (J-01 to J-05, Addendum J12). Loaded after ../mockup.js,
   ../strings/premiere-core.js, ../js/premiere-core.js and ../strings/client-setup.js. Emits only markup the UXP kit can
   paint (div role=button controls, <span> chips, inline SVG coloured by .ink-* classes, physical margins).
   Everything shared comes from the shell (M.*) and the Premiere core group (PC.pick, PC.kbtn, PC.indet, PC.info,
   PC.title, PC.mount). What is new here:
   - CS.flow: the four-step strip of the flow (folder, website, review, report) on the shell's segment bar;
   - CS.web / CS.quote: WEBSITE TEXT. It is data from someone else's server, so it is printed with M.esc only (a text
     node in the product, never markup) inside an auto-direction isolate (L-G38, J12); a website title is a quote
     marked "From the website", never an answer;
   - CS.dec / CS.item: an item with its ✓ confirm / ✕ reject pair, its source (page and host) and its conflict mark;
   - CS.gender / CS.hon: the two people choices, NEITHER pre-selected (J6.2, J12); only the titles that match the chosen
     gender are offered (people.py HONORIFICS), "Unknown" offers only the ungendered «د.»;
   - CS.mount: PC.mount plus the header action (J12) and the "No client open" context line (view.noclientKey). */
(function () {
  "use strict";
  var M = window.M, t = M.t;
  var q = new URLSearchParams(location.search);
  var CS = (window.CS = { D: window.CS_DATA, state: q.get("state") });
  if (CS.state === "long") for (var k in CS.D.long) CS.D[k] = CS.D.long[k];
  var STEPS = ["folder", "website", "review", "report"];

  /* the flow strip: step n of 4 (1-based); o = {done, kind, skipped}. view.setup feeds the header ("Setting up · n of 4") */
  CS.flow = function (step, o) {
    o = o || {};
    var done = o.done !== undefined ? o.done : step - 1;
    var label = t(o.skipped ? "cs.flow.pos_skipped" : "cs.flow.pos", { n: step, name: M.raw("cs.flow." + STEPS[step - 1]) });
    return M.segbar(4, done, label, o.kind || (done === 4 ? "ok" : "pending"));
  };
  CS.head = function (step, title, sub, o) {
    return CS.flow(step, o) + '<div class="mt-4">' + PC.title(title, sub) + "</div>";
  };
  /* a host or a site address: an LTR isolate, never a link */
  /* R1 (designer P1-4): ONE no-wrap run, middle ellipsis when long (R3 S-13), so a host never splits at a hyphen */
  CS.host = function (s, max) { return M.html(M.ltr(M.mid(String(s), max || 30), "lat cs-web cs-nw")); };
  /* the host part of a site address (a path-scoped site "sites.google.com/view/x" shows "sites.google.com") */
  CS.hostOf = function (s) { return String(s).split("/")[0]; };
  /* website text: escaped, an auto-direction isolate (Arabic or Latin as the site wrote it) */
  CS.web = function (s, cls) { return '<bdi dir="auto" class="cs-web ' + (cls || "") + '">' + M.esc(s) + "</bdi>"; };
  CS.quote = function (s) {
    return '<div class="cs-quote"><div class="t-meta tx-muted">' + t("cs.ppl.web") + '</div><div class="t-body">' + CS.web(s) + "</div></div>";
  };
  /* the source line: link icon + "From About · sahha-clinic.example" */
  CS.src = function (page, host) {
    return '<div class="cs-line">' + M.ico("link", 12, "ink-muted") + '<div class="t-meta tx-muted ms-1 m-grow">' +
      t("cs.src", { page: M.raw("cs.pg." + page), host: CS.host(CS.hostOf(host || CS.D.site)) }) + "</div></div>";
  };
  /* ✓ / ✕ pair. state: "" | "yes" | "no"; o = {focus: "yes"|"no", disabled} */
  CS.dec = function (state, o) {
    o = o || {};
    var one = function (kind, icon, label) {
      var on = state === kind, dis = !!o.disabled;
      var cls = "cs-decbtn" + (dis ? " cs-decbtn-dis" : on ? " cs-decbtn-" + kind : "") + (o.focus === kind ? " cs-decbtn-focus" : "");
      var ink = dis ? "ink-disabled" : on ? (kind === "yes" ? "ink-ok" : "ink-text") : "ink-muted";
      return '<div class="' + cls + '" role="button" tabindex="' + (dis ? -1 : 0) + '" aria-pressed="' + on + '" aria-label="' + M.esc(M.raw(label)) + '"' +
        (dis ? ' aria-disabled="true"' : "") + ">" + M.ico(icon, 16, ink) + "</div>";
    };
    return '<div class="cs-dec" role="group">' + one("yes", "check", "cs.dec.yes") + one("no", "x", "cs.dec.no") + "</div>";
  };
  /* what the choice means, in words, under a decided item */
  CS.decLine = function (state) {
    if (!state) return "";
    return '<div class="cs-line">' + M.ico(state === "yes" ? "check" : "minus", 12, state === "yes" ? "ink-ok" : "ink-muted") +
      '<div class="t-meta tx-muted ms-1 m-grow">' + t(state === "yes" ? "cs.dec.will" : "cs.dec.out") + "</div></div>";
  };
  /* the conflict mark (J12: "marked when it conflicts with the client's files") and what differs */
  CS.conflict = function (html) {
    return '<div class="cs-chiprow">' + M.chip("warn", t("cs.conf.mark"), "triangle-alert") + "</div>" +
      '<div class="t-meta tx-text">' + html + "</div>";
  };
  /* one item. o = {main (html), dec, focus, disabled, src [page, host], conflict (html), extra (html, full width)} */
  CS.item = function (o) {
    return '<div class="cs-item"><div class="cs-item-row"><div class="m-col m-grow">' + o.main + "</div>" +
      CS.dec(o.dec || "", { focus: o.focus, disabled: o.disabled }) + "</div>" + (o.extra || "") +
      (o.conflict ? CS.conflict(o.conflict) : "") + CS.decLine(o.dec) + (o.src ? CS.src(o.src[0], o.src[1]) : "") + "</div>";
  };
  CS.section = function (label, inner, first) {
    return M.eyebrow(label, first ? "mt-4" : "mt-5") + M.card(inner, "m-card-flush mt-2");
  };

  /* mock raster previews (the engine's PNG previews in the product) */
  CS.logo = function (kind) {
    return kind === "icon" ? '<span class="cs-logo-icon"><span class="cs-logo-dot"></span></span>'
      : '<span class="cs-logo"><span class="cs-logo-mark"></span><span class="cs-logo-word">Sahha</span></span>';
  };
  CS.tiles = function (kind) {
    var one = function (tone) { return '<div class="cs-tile cs-tile-' + tone + '" aria-hidden="true">' + CS.logo(kind) + "</div>"; };
    return '<div class="cs-tiles">' + one("light") + one("grey") + one("dark") + "</div>";
  };
  CS.swatch = function (hex) { return '<span class="cs-swatch" style="background:' + hex + '" aria-hidden="true"></span>'; };
  CS.photo = function (p) {
    var fig = p.face ? '<span class="pc-head"></span><span class="pc-body"></span>' : '<span class="cs-photo-desk"></span>';
    return '<div class="cs-photo cs-photo-' + p.tone + '" aria-hidden="true">' + fig + "</div>";
  };

  /* ---- people ---- */
  var HON = {
    male: [["الدكتور", "Dr."], ["الأستاذ", "Mr."], ["الشيخ", "Sheikh"], ["المهندس", "Eng."]],
    female: [["الدكتورة", "Dr."], ["الأستاذة", "Ms."], ["الشيخة", "Sheikha"], ["المهندسة", "Eng."]],
    unknown: [["د.", "Dr."]]
  };
  CS.HON = HON;
  var GI = { male: 0, female: 1, unknown: 2 };
  /* gender: three options, none on until the editor picks; o = {focus: index, disabled} */
  CS.gender = function (g, o) {
    o = o || {};
    return '<div class="cs-field"><div class="t-meta tx-muted">' + t("cs.ppl.gender") + "</div>" +
      M.segmented(["male", "female", "unknown"].map(function (k) {
        /* R1 (designer P1-2): the chosen answer carries a check mark (the neutral-plus-mark pattern, R3 S-09), so it reads
           at a glance; focus stays the border only */
        return k === g ? '<span class="cs-seglbl">' + M.ico("check", 12, "ink-text") + "<span>" + t("cs.ppl." + k) + "</span></span>" : t("cs.ppl." + k);
      }), g ? GI[g] : -1, { focus: o.focus, disabled: o.disabled }) + "</div>";
  };
  function honLabel(pair) {
    return M.rtl ? '<span class="ar-run">' + M.esc(pair[0]) + "</span>"
      : M.esc(pair[1]) + ' <bdi dir="rtl" class="ar-run">' + M.esc(pair[0]) + "</bdi>";
  }
  /* title: off until a gender is picked; then only that gender's titles (+ "No title"). value = index or "none" */
  CS.hon = function (g, value, o) {
    o = o || {};
    var sel;
    if (!g) sel = M.select(t("cs.ppl.hon.first"), { disabled: true, grow: true });
    else if (value === undefined || value === null) sel = M.select(t("cs.ppl.hon.pick"), { grow: true, focus: o.open, disabled: o.disabled });
    else sel = M.select(value === "none" ? t("cs.ppl.hon.none") : honLabel(HON[g][value]), { grow: true, disabled: o.disabled });
    var list = "";
    if (o.open && g) {
      list = '<div class="cs-list" role="listbox">' + HON[g].map(function (p, i) {
        return '<div class="cs-opt' + (i === 0 ? " cs-opt-focus" : "") + '" role="option" tabindex="-1" aria-selected="false"><span class="t-label">' + honLabel(p) + "</span></div>";
      }).join("") + '<div class="cs-opt" role="option" tabindex="-1" aria-selected="false"><span class="t-label">' + t("cs.ppl.hon.none") + "</span></div></div>";
    }
    return '<div class="cs-field"><div class="t-meta tx-muted">' + t("cs.ppl.hon") + "</div>" + sel + list + "</div>";
  };

  /* the website link field. o = {value, focus, error} */
  CS.linkField = function (o) {
    o = o || {};
    var cls = "m-input" + (o.focus ? " m-input-focus" : "") + (o.error ? " cs-input-err" : "");
    /* R1 (designer P2-13): an address is LTR in both languages, left-aligned, cut at its END, so the host stays visible */
    var val = o.value ? '<span class="m-block m-trunc m-grow tx-text t-body cs-ltrval" dir="ltr">' + M.esc(o.value) + "</span>"
      : '<span class="m-block tx-muted t-body">' + t("cs.web.ph") + "</span>";
    return '<div class="t-label cs-label">' + t("cs.web.field") + "</div>" +
      '<div class="' + cls + '" role="textbox" tabindex="0" aria-label="' + M.esc(M.raw("cs.web.field")) + '"' + (o.error ? ' aria-invalid="true"' : "") + ">" + val + "</div>";
  };
  /* a buttons row that wraps (300 px safe) */
  CS.acts = function (btns, cls) {
    return '<div class="cs-acts ' + (cls || "") + '">' + btns.map(function (b) { return '<div class="m-row">' + b + "</div>"; }).join("") + "</div>";
  };
  /* "Send diagnostics" (J12: the certificate fix's second button): copies the details and opens the support chat */
  CS.diag = function () {
    return M.btn(t("cs.diag"), { kind: "secondary", icon: "message-square" });
  };
  CS.diagUnder = function () {
    return '<div class="t-meta tx-muted mt-2">' + t("cs.diag.sub") + " " + t("support.promise") + "</div>";
  };

  /* ---- mount: PC.mount + the header action and the no-client context line ---- */
  CS.mount = function (screen) {
    var view = null, build = screen.build;
    /* the header's no-client line says "No client open" (the shell's view.noclientKey) */
    screen.build = function (s) { view = build(s); if (view.noclient && !view.noclientKey) view.noclientKey = "cs.noclient"; return view; };
    PC.mount(screen);
    var panel = document.querySelector(".m-panel");
    if (!panel || !view) return;
    if (view.hdrAct) {
      var r1 = panel.querySelector(".m-hdr-r1"), lang = panel.querySelector(".m-lang");
      var a = view.hdrAct, off = !!a.disabled;
      var html = '<div class="cs-hdr-act' + (a.focus ? " cs-hdr-act-focus" : "") + (off ? " cs-hdr-act-off" : "") + '" role="button" tabindex="' + (off ? -1 : 0) + '"' +
        (off ? ' aria-disabled="true"' : "") + ' aria-label="' + M.esc(M.raw("cs.action.setup")) + '">' + M.ico("plus", 16, off ? "ink-disabled" : "ink-muted") +
        (M.w >= 360 ? '<span class="cs-hdr-act-lbl">' + t("cs.hdr.new") + "</span>" : "") + "</div>";
      if (r1 && lang) lang.insertAdjacentHTML("beforebegin", html);
    }
  };
})();
