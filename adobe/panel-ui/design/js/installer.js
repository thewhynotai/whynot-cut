/* WhyNot Cut 3.0 E-D2: the installer window shell (I-01 to I-09). Loaded after ../mockup.js and
   ../strings/installer.js. mockup.js draws a docked panel (300/360/480); the installer is a 760 x 540 window
   (minimum 640 x 480), so this file mounts its own shell and reuses mockup.js's components (M.btn, M.chip, M.notice,
   M.card, M.checkbox, M.progress, M.status, M.ico, M.t).
   URL: screens/I-0x-*.html?lang=ar|en&w=760|640&state=<state>[&capture=1]
   Addendum G11: macOS is the primary platform. Every state draws the macOS window chrome and uses macOS paths and
   copy; the state "win" (and any state starting with "win") is the Windows variant with Windows chrome.
   Shell, top to bottom: OS chrome, header (monogram, wordmark, "Setup", the "Internal build" chip on unsigned
   builds, the language switch), the gradient hairline, then the rail (stages, version, genuine-build line, footer)
   beside the content column (scroll area + pinned action bar).
   Keyboard (G2): the primary carries a Return keycap (Enter runs it), the cancel/back/close button an Esc keycap;
   tab order is the DOM order (header language switch, content, then the bar from start to end).
   Components marked SHARED are proposed for promotion into mockup.js:
   - I.step: a checklist row with an end status and an optional progress block (panel P-01 and the installer use
     the same row definition, eco §3.6.4);
   - I.act: a notice with a title, a sentence, an optional wrapping mono box and its buttons (action-needed, dialogs);
   - I.fail: a failure card: what happened, why, ONE fix, then Contact support / Save a report for support and the log;
   - I.btn: M.btn with a keycap hint (Return / Esc);
   - I.radio: a single-choice control row with a 20 px ring;
   - I.pathField: a recessed path field with one button and a field message;
   - I.adds: "what Setup adds, and where" rows (trust, G2-r1 d).
   R3 (installer group): I.TITLES / I.titleKey (one title table), I.notice (the "↵" keycap), I.offlineGet (the gated offline
   installer), I.fail takes a list of buttons that wrap, I.step carries data-kind, M.path in the path field, rail r.none. */
(function () {
  "use strict";
  var M = window.M;
  var q = new URLSearchParams(location.search);
  var WIDTHS = [760, 640];
  var W = WIDTHS.indexOf(Number(q.get("w"))) >= 0 ? Number(q.get("w")) : 760;
  var H = W === 760 ? 540 : 480;
  var S = window.MOCK_STRINGS[M.lang];
  var missing = [];
  var state0 = q.get("state") || ""; /* may end in "-live" (the support and data pages live, H24) or "-nosupport" (support.url absent): mockup.js strips it for the build */
  var OS = /^win/.test(state0) ? "win" : "mac";
  var D = {}, base = window.I_DATA, k;
  for (k in base) if (k !== "mac" && k !== "win") D[k] = base[k];
  for (k in base[OS]) if (k !== "long") D[k] = base[OS][k];
  var I = (window.I = { w: W, h: H, D: D, state: state0, os: OS, mac: OS === "mac" });

  /* T: M.t with the missing-key record this self-check needs (mockup.js keeps its own list private) */
  function T(key, vars) { if (S[key] === undefined) missing.push(key); return M.t(key, vars); }
  I.T = T;
  /* the macOS copy is the default; a key with a ".win" twin uses it on Windows */
  I.Tos = function (key, vars) { return T(OS === "win" && S[key + ".win"] !== undefined ? key + ".win" : key, vars); };
  /* a count in a sentence (convention: header of ../strings/installer.js). The category is new Intl.PluralRules(lang).select(n):
     AR zero | one | two | few (3-10) | many (11-99) | other (100+); EN one | other. The line is key + "." + category when the
     table has it, else the BASE key (EN: covers 0 and every count but 1; AR: the base equals .other). {n} is the count. */
  var PR = {};
  I.pluralKey = function (key, n) {
    var lang = M.lang;
    var cat = (PR[lang] = PR[lang] || new Intl.PluralRules(lang)).select(n);
    return S[key + "." + cat] !== undefined ? key + "." + cat : key;
  };
  I.plural = function (key, n, vars) {
    var v = { n: n }, k;
    for (k in (vars || {})) v[k] = vars[k];
    return T(I.pluralKey(key, n), v);
  };
  I.ico = function (name, size, ink) {
    var set = (window.MOCK_ICONS || {})[name];
    if (!set || !set[String(size || 16)]) missing.push("icon:" + name + "@" + (size || 16));
    return M.ico(name, size, ink);
  };
  /* "2.9 GB" / «2.9 جيجا» with a no-break space; Western digits in both */
  I.gb = function (n) { return window.I_GB(typeof n === "number" ? (n >= 100 ? String(Math.round(n * 10) / 10) : n.toFixed(1)) : n, M.lang === "ar"); };
  I.mb = function (n) { return window.I_MB(n, M.lang === "ar"); };
  I.path = function (p) { return M.html(M.path(p)); }; /* thin wrapper: the isolate and the wrap points are M.path (R2 §1.3) */
  I.ltr = function (s) { return M.html(M.ltr(s)); };
  /* "WhyNot Cut 2.2.1" as ONE isolated Latin run, so the number stays after the name in Arabic too; the digits are set in
     Inter (.i-ver) because Syne's old-style digits read "3.o.ı" in a display line (R2 designer P2-10) */
  I.app = function (ver) { return M.html('<bdi dir="ltr" class="lat">WhyNot Cut <span class="i-ver">' + M.esc(ver) + "</span></bdi>"); };
  I.ver = function (ver) { return M.html('<bdi dir="ltr" class="lat i-ver">' + M.esc(ver) + "</bdi>"); };
  /* a file name or link the editor must read whole: mono, LTR, wraps anywhere instead of running out */
  I.monoBox = function (s) { return '<span class="i-monobox">' + M.path(s) + "</span>"; };
  I.useLong = function () { var L = base[OS].long || {}; for (var x in L) D[x] = L[x]; };

  /* The keycap is the panel's own (.m-kbd, Inter): Return and Esc here, not the panel's Cmd+Return. M.btn refuses a keycap on a
     danger or destructive button (R2 designer P0-3), and a disabled button shows none. The label stays a plain inline run
     inside M.btn's own span, so the space before a Latin name is kept («سطّب Claude», not «Claudeسطّب»: a flex row dropped it). */
  I.btn = function (label, o) {
    o = o || {};
    var b = {}, k;
    for (k in o) b[k] = o[k];
    b.kbd = o.key && !o.disabled ? (o.key === "enter" ? "↵" : "Esc") : null;
    return M.btn(label, b);
  };

  /* ---- content helpers ---- */
  I.title = function (text, sub) {
    return '<div class="i-title">' + text + "</div>" + (sub ? '<div class="t-body tx-muted mt-1">' + sub + "</div>" : "");
  };
  I.fact = function (icon, text, o) {
    o = o || {};
    return '<div class="i-fact">' + I.ico(icon, 16, o.ink || "ink-muted") + '<div class="i-fact-text"><div class="t-body ' + (o.muted ? "tx-muted" : "tx-text") + '">' + text + "</div>" +
      (o.sub ? '<div class="t-meta tx-muted">' + o.sub + "</div>" : "") + (o.under || "") + "</div></div>";
  };

  /* SHARED: checklist row. kind ok|warn|error|info|pending|busy|waiting; o = {detail, extra, end, prog:{pct, meta, time}, act, cls, under}; data-kind lets a screen count its rows (I-03 chips) */
  I.step = function (kind, name, o) {
    o = o || {};
    var pend = kind === "pending";
    var detailCls = kind === "error" || kind === "warn" ? "tx-text" : "tx-muted";
    var end = o.end ? '<span class="i-step-end t-meta">' + o.end + "</span>" : "";
    var prog = o.prog ? '<div class="i-step-prog">' + M.progress(o.prog.pct) +
      '<div class="m-row mt-1"><div class="t-meta tx-muted m-grow">' + o.prog.meta + '</div>' +
      /* R3 I-6: "0:42 elapsed" / «عدّى 0:42», never a bare time that reads as time left */
      (o.prog.time ? '<div class="t-meta tx-muted ms-2">' + T("i04.elapsed", { time: M.html(M.mono(o.prog.time)) }) + "</div>" : "") + "</div></div>" : "";
    return '<div class="i-step' + (pend ? " i-step-pend" : "") + (o.prog ? " i-step-run" : "") + " " + (o.cls || "") + '" data-kind="' + kind + '">' + M.status(kind) +
      '<div class="i-step-text"><div class="i-step-head"><div class="t-label i-step-name m-grow">' + name + "</div>" + end + "</div>" +
      (o.detail ? '<div class="t-meta ' + detailCls + '">' + o.detail + "</div>" : "") + (o.extra ? '<div class="t-meta tx-muted mt-1">' + o.extra + "</div>" : "") + prog +
      (o.act ? '<div class="m-row mt-2">' + o.act + "</div>" : "") + (o.under || "") + "</div></div>";
  };
  I.list = function (rows, cls) { return M.card(rows.join(""), "m-card-flush " + (cls || "")); };

  /* SHARED: action-needed card / dialog; kind ok|warn|error|info|waiting (waiting = for the person: pink dot on the info tint);
     o = {mono, btns (html), hint, icon, sub, cls, extra} */
  I.act = function (kind, title, text, o) {
    o = o || {};
    var body = '<div class="t-label i-act-title">' + title + "</div>" + (text ? '<div class="t-body tx-text mt-1">' + text + "</div>" : "") +
      (o.extra || "") +
      (o.mono ? '<div class="m-row mt-2">' + I.monoBox(o.mono) + "</div>" : "") +
      (o.sub ? '<div class="t-meta tx-muted mt-1">' + o.sub + "</div>" : "") +
      (o.btns ? '<div class="m-row mt-3">' + o.btns + "</div>" : "") +
      (o.hint ? '<div class="t-meta tx-muted mt-2">' + o.hint + "</div>" : "");
    return '<div class="m-notice m-notice-' + (kind === "waiting" ? "info" : kind) + ' i-act ' + (o.cls || "") + '" role="' + (kind === "error" ? "alert" : "status") + '">' +
      (o.icon ? I.ico(o.icon, 16, { ok: "ink-ok", warn: "ink-warn", error: "ink-error", info: "ink-info", waiting: "ink-accent" }[kind]) : M.status(kind)) +
      '<div class="m-notice-body">' + body + "</div></div>";
  };
  /* SHARED: failure card (I-07 pattern): what happened (white sentence), why (meta), o.extra (one more meta line), ONE fix (primary), then
     one-click support + Save a report for support (ghost, G2-r1 e) and the privacy note (no log path: R2 D-P1-10) */
  I.fail = function (text, o) {
    o = o || {};
    var chip = o.safety ? '<div class="m-row">' + M.chip("error", T("i07.safety"), "shield-x") + "</div>" : "";
    /* D-05 update (2026-10-16): the support chat is WhatsApp and live: "Copy details and open WhatsApp" (one action) and
       the reply promise under it; ?support=off = "Copy details for support" (copies only) with the ONE "coming soon" line
       under it (M.supportParts, the same block as the panel, R3 designer F-03). Save a report is its own button either way. */
    var sp = M.supportParts({ kind: "ghost", flush: true });
    /* o.soonKey (?support=off only): the card's own "coming soon" (the download page) and support.soon fold into ONE line */
    var support = '<div class="m-row m-wrap mt-2 i-support"><div class="m-row me-2">' + sp.btn + "</div></div>" + (!M.supportLive && o.soonKey ? M.soonLine(o.soonKey) : sp.under) +
      '<div class="m-row m-wrap i-support">' + M.btn(T("i00.save_report"), { kind: "ghost", icon: "download", flush: true }) + "</div>"; /* both flush: a wrapped second line stays aligned */
    /* R3 I-3 (designer F-18): o.btn is one button or a list; the row wraps, each button keeps its own top margin */
    var btns = o.btn ? (Array.isArray(o.btn) ? o.btn : [o.btn]).filter(Boolean) : [];
    var btnRow = btns.length ? '<div class="m-row m-wrap">' + btns.map(function (b) { return '<div class="m-row me-2 mt-3">' + b + "</div>"; }).join("") + "</div>" : "";
    var body = chip + '<div class="t-body tx-text' + (o.safety ? " mt-2" : "") + '">' + text + "</div>" +
      (o.sub ? '<div class="t-meta tx-muted mt-1">' + o.sub + "</div>" : "") +
      (o.extra ? '<div class="t-meta tx-muted mt-1">' + o.extra + "</div>" : "") +
      (o.mono ? '<div class="m-row mt-2">' + I.monoBox(o.mono) + "</div>" : "") +
      btnRow + support +
      '<div class="t-meta tx-muted mt-1">' + T("i00.report_note") + "</div>"; /* R2 D-P1-10: no log path in a card; "Save a report" covers it */
    return '<div class="m-notice m-notice-' + (o.kind || "error") + '" role="alert">' + M.status(o.kind || "error") + '<div class="m-notice-body">' + body + "</div></div>";
  };

  /* The notice keycap is the installer's own "↵" (Return), like every other installer primary, not the panel's "⌘ ↵" (R3 designer
     F-25). M.notice draws the panel keycap for a primary button, so the text is swapped here (a shared change would let
     M.notice take b.kbd as a string). */
  I.notice = function (kind, text, o) {
    return M.notice(kind, text, o).replace(/(<span class="m-kbd [^"]*" aria-hidden="true">)[^<]*(<\/span>)/g, "$1\u21B5$2");
  };
  /* H24 + D-05 (R3 S-01): "Get the offline installer" opens thewhynot.ai/download, which is NOT published. Live = the button;
     not live = no button: the next step is WhatsApp support (live), or the ONE "coming soon" line under ?support=off.
     Returns {btn, line}: btn = the button (live only), line = the sentence that stands in for it. */
  I.offlineGet = function (key) {
    if (M.live) return { btn: M.btn(T("i00.offline_get"), { icon: "external-link" }), line: "" };
    return { btn: "", line: M.supportLive ? T(key || "i00.offline_ask") : T("download.soon") };
  };
  /* ONE title table (R3 designer F-05, same rule as the panel header): the headline says what the screen's STATE is, never
     what the happy path would be. Keyed by screen, then by the resolved state; "default" is everything else. Screens call
     t(I.titleKey("I-06", I.state)); a state that is busy, blocked or half done never reads "ready" or "Installing" over it. */
  I.TITLES = {
    "I-01": { "default": "i01.title", upgrade: "i01.title.update", "long": "i01.title.update" },
    /* a finished check with notes is "Ready, with a few things to know"; only a clean pass is "ready"; a red row is "Can't install yet" */
    "I-03": { "default": "i03.title.notes", loading: "i03.title", success: "i03.title.ready", error: "i03.title.blocked", offline: "i03.title.blocked" },
    /* the Adobe panel file card is a red problem that needs the person ("panel_not_installed"): not "Installing" */
    "I-04": { "default": "i04.title", error: "i04.title.stopped", cancelled: "i04.title.stopped", success: "i04.title.done", panelfile: "i06.title.error", "long": "i06.title.error" },
    "I-05": { "default": "i05.title", loading: "i05.title.installing", checking: "i05.title.installing", waiting: "i05.title.signin", timeout: "i05.title.signin", success: "i05.title.ready" },
    "I-06": { "default": "i06.title", loading: "i06.checking", amber: "i06.title.almost", "long": "i06.title.almost", nosignin: "i06.title.almost", error: "i06.title.error" },
    "I-07": { "default": "i07.title" },
    "I-08": { "default": "i08.title", loading: "i08.title.busy", checking: "i08.title.busy", error: "i08.title.error", "long": "i08.title.error", offline: "i08.title.offline", success: "i08.current", repair: "i08.repair.run" },
    "I-09": { "default": "i09.title", loading: "i09.removing", error: "i09.title.error", success: "i09.done", empty: "i09.empty.title" }
  };
  I.titleKey = function (id, state) { var m = I.TITLES[id] || {}; return m[state] || m["default"]; };

  /* SHARED: single-choice row; o = {on, chip, size, focus, disabled} */
  I.radio = function (label, o) {
    o = o || {};
    return '<div class="i-radiorow' + (o.disabled ? " i-radio-disabled" : "") + (o.focus ? " m-btn-focus" : "") + '" role="radio" tabindex="' + (o.disabled ? "-1" : o.on ? "0" : "-1") + '" aria-checked="' + !!o.on + '">' +
      '<span class="i-radio' + (o.on ? " i-radio-on" : "") + '">' + (o.on ? '<span class="i-radio-dot"></span>' : "") + "</span>" +
      '<div class="t-label ms-3">' + label + "</div>" + (o.chip || "") + '<span class="m-spacer"></span>' +
      '<span class="i-size t-meta">' + (o.size || "") + "</span></div>";
  };
  /* SHARED: the path shown in a path field, cut in the MIDDLE so it stays on ONE line (E-T1; the field is 32 px tall, never wraps).
     RULE (production copies this exactly), for a path longer than the budget (characters, "…" counted as 1):
       1. keep the FIRST segment plus its separator: the drive "D:\", or the root "/" with its first folder ("/Volumes/"); on macOS
          under /Users and /Volumes the account or the volume name is the identity, so it is kept too ("/Users/sara/",
          "/Volumes/Samsung T7 Shield/") when head + "…" + separator + the last segment still fits the budget, else only the first folder;
       2. keep the LAST segment whole (the folder the person chose); it is never cut by this rule;
       3. fill from the END backwards with whole segments (each with its separator) while head + "…" + separator + the kept tail
          stays within the budget; the first segment that does not fit stops the fill (no gaps: the kept tail is contiguous);
       4. put "…" plus the separator between the two parts: head + "…" + sep + tail.
     A path within the budget is shown whole. The separator is the path's own ("\\" if it has one, else "/"). The full path is
     the field's title attribute (tooltip). The text is one LTR isolate in Arabic too (<bdi dir="ltr">); no <wbr> here (M.path is for
     text that wraps; a field clips). The budget is characters per width: 760 px -> 46, 640 px -> 38. Measured: the value is mono 12 px
     (7.09 px a character); the text box is the column minus the Change button and the field's padding, 339 px at 760 and 275 px at
     640 in the narrower language (EN), so 46 and 38 characters keep a little spare. Arabic letters are narrower than a mono cell.
     If the last segment alone is longer than the budget the field's CSS cuts it at its end (text-overflow), the only case it can. */
  I.PATH_BUDGET = { 760: 46, 640: 38 };
  I.pathShort = function (path, budget) {
    if (path.length <= budget) return path;
    var sep = path.indexOf("\\") >= 0 ? "\\" : "/";
    var parts = path.replace(/[\\/]+$/, "").split(sep); /* "/Users/a/b" -> ["", "Users", "a", "b"]; "D:\x\y" -> ["D:", "x", "y"] */
    var keep = parts[0] === "" ? 2 : 1, last = parts[parts.length - 1];
    if (parts[0] === "" && (parts[1] === "Users" || parts[1] === "Volumes") && parts.length > 4 &&
        parts.slice(0, 3).join(sep).length + 1 + 2 + last.length <= budget) keep = 3;
    if (parts.length - 1 <= keep) return path; /* nothing in the middle to cut */
    var head = parts.slice(0, keep).join(sep) + sep, tail = last, i, cand;
    for (i = parts.length - 2; i >= keep; i--) {
      cand = parts[i] + sep + tail;
      if (head.length + 2 + cand.length > budget) break;
      tail = cand;
    }
    return head + "…" + sep + tail;
  };
  /* SHARED: path field; o = {btn, btnKind, kind: warn|error, msg, msgKind, focus, sub} */
  I.pathField = function (label, path, o) {
    o = o || {};
    var cls = o.kind ? " i-path-" + o.kind : "";
    var shown = I.pathShort(path, I.PATH_BUDGET[W]);
    return '<div class="t-label">' + label + "</div>" +
      '<div class="i-pathrow mt-1"><div class="i-path i-clip' + cls + '" title="' + M.esc(path) + '"><bdi dir="ltr" class="mono m-path">' + M.esc(shown) + "</bdi></div>" + /* R3 S-08: one LTR isolate, drive colon inside; .i-path is left-aligned in both languages. E-T1: middle ellipsis (I.pathShort), full path in title */
      M.btn(o.btn || T("i02.change"), { icon: "folder", focus: o.focus, kind: o.btnKind }) + "</div>" +
      (o.msg ? '<div class="i-field-msg">' + M.status(o.msgKind || "info", 16) + '<div class="t-meta ms-2 m-grow ' + (o.msgKind === "warn" || o.msgKind === "error" ? "tx-text" : "tx-muted") + '">' + o.msg + "</div></div>" : "") +
      (o.sub ? '<div class="t-meta tx-muted mt-1">' + o.sub + "</div>" : "");
  };
  I.sub = function (text) { return '<div class="t-meta tx-muted i-checksub">' + text + "</div>"; };

  /* SHARED: what Setup adds, and where (trust; E2.1#1 and #5). R2 D-P1-10: plain locations only ("In Login Items"); the raw
     folder, plist and log paths are not primary text (they stay behind Show details / Save a report). */
  I.adds = function (cls, o) {
    o = o || {};
    var rows = [
      ["app-window", "add.service", "add.service.sub"],
      ["puzzle", "add.claude", "add.claude.sub"],
      o.git ? ["package", "i09.r.git", "i09.r.git.sub"] : null, /* uninstall on Windows: the Git Setup installed for Claude */
      ["layers", "add.panels", "add.panels.sub"],
      ["type", "add.fonts", "add.fonts.sub"],
      ["power", "add.login", "add.login.sub"],
      o.uninstall ? ["link", "i09.r.link", null] : ["audio-lines", "add.model", "add.model.sub"]
    ];
    return I.list(rows.filter(Boolean).map(function (r) {
      return '<div class="i-step">' + I.ico(r[0], 16, "ink-muted") + '<div class="i-step-text"><div class="t-label">' + T(r[1]) + "</div>" +
        (r[2] ? '<div class="t-meta tx-muted">' + I.Tos(r[2]) + "</div>" : "") + "</div></div>";
    }), cls || "mt-3");
  };

  /* ---- shell ---- */
  var FLOWS = {
    install: ["welcome", "custom", "check", "claude", "install", "finish"],
    update: ["update", "install", "finish"],
    uninstall: ["choose", "remove", "done"]
  };
  function rail(r) {
    r = r || { flow: "install", at: "welcome" };
    var stages = [];
    FLOWS[r.flow].forEach(function (s) { if ((s !== "custom" || r.custom) && (s !== "claude" || r.claude)) stages.push(s); });
    var at = stages.indexOf(r.at), out = "";
    stages.forEach(function (s, i) {
      var kind = r.none ? "pending" : i < at || r.all ? "ok" : i === at ? (r.mark || "current") : "pending"; /* r.none: nothing ran (I-09 empty), so no green and no active step */
      var icon = kind === "current" ? I.ico("circle-dot", 16, "ink-text") : M.status(kind);
      var sub = s === "custom" || s === "claude";
      out += '<div class="i-rstep' + (i === at && !r.all && !r.none ? " i-rstep-on" : "") + (sub ? " i-rstep-sub" : "") + '">' + icon +
        '<span class="t-label ms-2">' + T("i00.stage." + s) + "</span></div>";
    });
    return out;
  }
  function langSwitch() {
    var seg = function (l) {
      var on = l === M.lang;
      return '<div class="m-seg' + (l === "ar" ? " m-seg-ar" : "") + (on ? " m-seg-on" : "") + '" role="button" tabindex="0" lang="' + l +
        '" aria-pressed="' + on + '" aria-label="' + M.esc(S["lang." + l]) + '">' + M.esc(S["lang." + l + ".short"]) + "</div>";
    };
    return '<div class="m-lang" role="group">' + seg("ar") + seg("en") + "</div>";
  }
  function osChrome(kind) {
    var title = '<span class="i-os-title' + (M.lang === "ar" ? " i-os-ar" : "") + '" dir="' + (M.rtl ? "rtl" : "ltr") + '">' + M.esc(S["i00.wintitle"]) + "</span>";
    if (kind === "win") {
      return '<div class="i-os i-os-win i-clip" aria-hidden="true"><img src="../../../premiere-uxp/icons/dark/icon-24.png" alt="" width="16" height="16" class="m-block me-2">' + title +
        '<span class="m-spacer"></span><span class="i-os-btn">' + I.ico("minus", 16, "ink-text") + '</span><span class="i-os-btn">' + I.ico("square", 12, "ink-text") +
        '</span><span class="i-os-btn">' + I.ico("x", 16, "ink-text") + "</span></div>";
    }
    return '<div class="i-os i-os-mac i-clip" aria-hidden="true"><span class="i-os-light i-os-red"></span><span class="i-os-light i-os-yellow"></span><span class="i-os-light i-os-green"></span>' +
      '<div class="i-os-mid">' + title + "</div></div>";
  }

  I.mount = function (screen) {
    var r = M.resolve(screen, state0), full = r.full, valid = r.valid, state = r.state;
    I.state = state;
    if (state === "long") I.useLong();
    var v = screen.build(state);
    var root = document.documentElement;
    root.lang = M.lang;
    root.dir = M.rtl ? "rtl" : "ltr";
    if (M.capture) root.className += " m-capture";
    document.title = screen.id + " " + full + " · " + M.lang + " · " + W;

    var internal = !!v.internal;
    var chrome = v.chrome || OS;
    var win = document.createElement("div");
    win.className = "m-panel i-win i-w" + W + (M.rtl ? " m-rtl" : "");
    win.setAttribute("dir", M.rtl ? "rtl" : "ltr");
    win.style.height = (H + (chrome === "win" ? 32 : 28)) + "px";
    var trust = internal
      ? '<div class="i-rail-trust">' + I.ico("flask-conical", 12, "ink-warn") + '<div class="t-meta tx-muted ms-2 m-grow">' + T("i00.unsigned") + "</div></div>"
      : '<div class="i-rail-trust">' + I.ico("shield-check", 12, "ink-ok") + '<div class="t-meta tx-muted ms-2 m-grow">' + T("i00.signed") + "</div></div>";
    var bar = v.bar ? '<div class="i-bar">' + (v.bar.meta ? '<div class="i-bar-meta">' + v.bar.meta + "</div>" : "") +
      (v.bar.start || "") + '<span class="m-spacer"></span>' + (v.bar.end || "") + "</div>" : "";
    win.innerHTML = osChrome(chrome) +
      '<div class="i-app"><header class="i-hdr"><span class="m-lockup" dir="ltr"><img class="m-mono" src="../../../premiere-uxp/icons/dark/icon-48.png" alt="" width="20" height="20">' +
      '<span class="m-wordmark m-lockup-wm">' + M.ltr(S["product.name"], "wm") + '</span></span><span class="i-setup ms-2">' + T("i00.setup") + "</span>" +
      '<span class="m-spacer"></span>' + (internal ? M.chip("warn", T("i00.internal"), "flask-conical") : "") + langSwitch() + "</header>" +
      '<div class="m-hairline" aria-hidden="true"></div>' +
      '<div class="i-body"><nav class="i-rail" aria-label="' + M.esc(T("i00.rail.aria")) + '">' + rail(v.rail) + '<span class="m-spacer"></span>' +
        '<div class="i-rail-end"><div class="t-meta tx-muted">' + T("i00.version", { app: I.app(D.version) }) + '</div><div class="mt-1">' + trust + "</div></div>" +
        '<footer class="m-footer"><bdi dir="' + (M.rtl ? "rtl" : "ltr") + '" class="m-footer-txt">' + M.t("footer.powered") + "</bdi></footer></nav>" +
      '<div class="i-main"><div class="i-scrollrow"><main class="i-scroll" id="scroll"><div class="i-scroll-in">' + v.body + "</div></main>" +
        '<div class="i-sbar" aria-hidden="true"><span class="i-sbar-gap"></span><span class="i-sbar-thumb"></span></div></div>' + bar + "</div></div></div>";
    document.body.innerHTML = "";
    document.body.appendChild(win);
    if (!M.capture) document.body.appendChild(nav(screen, full));
    check(win, full, valid, v.scroll);
  };

  function nav(screen, state) {
    var box = document.createElement("div");
    box.setAttribute("style", "display:flex;flex-direction:column;margin:0 0 0 24px;padding:16px;font:12px/18px Inter,Segoe UI,sans-serif;color:#ddd;direction:ltr;text-align:left;max-width:320px");
    var link = function (key, val, label, on) {
      var p = new URLSearchParams(location.search); p.set(key, val);
      return '<a style="color:' + (on ? "#fff" : "#9D6BFF") + ";margin:0 8px 0 0;font-weight:" + (on ? 600 : 400) + '" href="?' + p.toString() + '">' + label + "</a>";
    };
    var html = "<div style='margin:0 0 8px 0;font-weight:600'>" + screen.id + " " + M.esc(screen.name) + "</div><div>";
    screen.states.forEach(function (s) { html += link("state", s, s, s === state); });
    html += "</div><div style='margin:8px 0 0 0'>" + link("lang", "en", "EN", M.lang === "en") + link("lang", "ar", "AR", M.lang === "ar") + "</div><div>";
    WIDTHS.forEach(function (w) { html += link("w", w, w, w === W); });
    var keys = document.querySelector('meta[name="mock-keys"]'), motion = document.querySelector('meta[name="mock-motion"]');
    if (keys) html += "</div><div style='margin:8px 0 0 0;color:#aaa'><b>Keys</b> " + M.esc(keys.content);
    if (motion) html += "</div><div style='margin:8px 0 0 0;color:#aaa'><b>Motion</b> " + M.esc(motion.content);
    box.innerHTML = html + "</div>";
    document.body.style.flexDirection = "row";
    return box;
  }

  /* scroll position for the capture, then the scroll indicator (the product scrolls the column natively) */
  function scrollSetup(win, how) {
    var sc = win.querySelector("#scroll");
    if (how === "end") sc.scrollTop = sc.scrollHeight;
    else if (how) {
      var el = win.querySelector(how);
      if (el) sc.scrollTop = Math.max(0, el.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - 24);
    }
    var bar = win.querySelector(".i-sbar"), gap = bar.querySelector(".i-sbar-gap"), th = bar.querySelector(".i-sbar-thumb");
    var track = bar.getBoundingClientRect().height;
    if (sc.scrollHeight > sc.clientHeight + 1) {
      th.style.height = Math.max(24, Math.round(track * sc.clientHeight / sc.scrollHeight)) + "px";
      gap.style.height = Math.round(track * sc.scrollTop / sc.scrollHeight) + "px";
    } else { th.style.height = "0px"; gap.style.height = "0px"; }
  }

  /* self-check for _build/render_all.py: the same <meta name="mock-check"> fields as mockup.js. Sideways overflow is
     measured against the window, and inside the content column, the rail and the bar against their own boxes,
     skipping only the boxes that cut on purpose (.i-clip: path fields, OS chrome; the log). */
  function check(win, state, valid, how) {
    var done = function () {
      scrollSetup(win, how);
      var wr = win.getBoundingClientRect(), mid = wr.left + wr.width / 2;
      var side = function (el) { if (!el) return "none"; var r = el.getBoundingClientRect(); return r.left + r.width / 2 < mid ? "left" : "right"; };
      var over = 0, worst = "";
      win.querySelectorAll("*").forEach(function (el) {
        var box = wr;
        for (var a = el.parentElement; a && a !== win; a = a.parentElement) {
          var c = a.classList;
          if (c.contains("i-clip") || c.contains("i-log") || c.contains("m-ctx")) return;
          if (box === wr && (c.contains("i-scroll") || c.contains("i-rail") || c.contains("i-bar"))) box = a.getBoundingClientRect();
        }
        var r = el.getBoundingClientRect();
        if (!r.width || !r.height) return;
        if (r.right > box.right + 0.5 || r.left < box.left - 0.5) {
          over++;
          if (!worst) worst = (el.className && el.className.baseVal === undefined ? String(el.className) : el.tagName) + " " + (el.textContent || "").slice(0, 30);
        }
      });
      var fontsOk = true;
      if (document.fonts && document.fonts.check) {
        fontsOk = document.fonts.check("700 15px Syne") && document.fonts.check("400 13px Inter") &&
          (M.lang !== "ar" || document.fonts.check("400 14px 'IBM Plex Sans Arabic'"));
      }
      if (!document.querySelector('meta[name="mock-keys"]')) missing.push("meta:mock-keys");
      if (!document.querySelector('meta[name="mock-motion"]')) missing.push("meta:mock-motion");
      var meta = document.createElement("meta");
      meta.name = "mock-check";
      meta.content = ["state=" + (valid ? state : "invalid"), "lang=" + M.lang, "w=" + Math.round(wr.width), "dir=" + getComputedStyle(win).direction,
        "mono=" + side(win.querySelector(".m-mono")), "tab1=none",
        "overflow=" + over, "worst=" + worst.replace(/[;=]/g, " "), "fonts=" + (fontsOk ? "ok" : "fallback"),
        "missing=" + missing.join(",")].concat(M.selfCheckExtras(win).slice(1)).join(";");
      document.head.appendChild(meta);
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { setTimeout(done, 50); });
    else setTimeout(done, 300);
  }
})();
