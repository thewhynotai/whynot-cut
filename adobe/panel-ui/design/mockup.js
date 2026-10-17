/* WhyNot Cut 3.0 E-D2 mockup runtime: query params, copy, icons and the shared components every screen mockup uses.
   URL: screens/<screen>.html?lang=ar|en&w=300|360|480&state=<state>[&capture=1]
   The components emit only markup the UXP kit can paint (direction §12): <div role="button"> controls, <span> chips,
   inline SVG coloured by .ink-* classes, physical margins (mockup.css swaps them under .m-rtl). The DOM order is the
   reading order; Arabic mirrors once through CSS direction on the panel root. Directional icons (chevrons) are
   swapped here, per language, never by a CSS transform.
   Round 2 (docs/design/reviews/R2-fix-list.md, SHARED bucket): the header status is derived from the live body
   (never "All set" over a problem); a danger or destructive action never carries the primary keycap; the shared
   components the group files each re-built (dialog, radio, segmented, toggle, select, slider, tile, media, list row,
   stage list, bullet, trust / saved lines, back row, no-Claude / offline / stale notices) live here. */
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
  /* H24 (executor rule, owner decisions D-02 / D-05): the panel never links to a page that isn't live. Two mock states
     for the PAGES (thewhynot.ai/data, /download, /help):
     LIVE = the engine sends support.data_url / download_url / guide_url (state name ends in "-live", or ?support=live);
     NOT LIVE (the default, none is published yet) = no link: "Cost and data" is hidden and the data line stands alone;
     the download page and the guide show ONE "coming soon" line in place of their button (M.soonLine). */
  M.live = q.get("support") === "live";
  /* Round 3 (D-05 update 2026-10-16, R3-fix-list S-01): support is the WhyNot Cut WhatsApp chat, which IS live, so the
     support action is shown by default: "Copy details and open WhatsApp" (one action: copy, then open the chat; the
     details are never in the link) with the reply promise. ?support=off draws the alternate state (support.url absent:
     copy only + "The support chat is coming soon."). M.live above now only gates the PAGES that are not published yet
     (thewhynot.ai/data, /download, /help). */
  M.supportLive = q.get("support") !== "off" && !/-nosupport$/.test(q.get("state") || ""); /* "<state>-nosupport" draws the same alternate (support.url absent) */
  /* "<state>-live" and "<state>-nosupport" are twins of "<state>" when both are in the screen's list ("success-live" of P-07 is its own state) */
  M.resolve = function (screen, raw) {
    var valid = screen.states.indexOf(raw) >= 0;
    var full = valid ? raw : (screen.defaultState || screen.states[0]);
    var m = /^(.*)-(live|nosupport)$/.exec(full);
    var twin = !!(m && screen.states.indexOf(m[1]) >= 0);
    if (twin && m[2] === "live") M.live = true;
    return { full: full, valid: valid, state: twin ? m[1] : full };
  };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  M.esc = esc;

  /* A Latin run (letters, then words, digits, dots, hyphens) inside Arabic goes in <bdi dir="ltr" class="lat">.
     R2: a path (C:\Users\..., ~/x, /Users/x) is one isolated run too, so drive letters and separators never reverse. */
  /* R3 (designer F-04, F-09): a slash INSIDE a run keeps it whole, so a URL ("claude.ai/download") or a unit ("mg/dL")
     is one isolate and never reorders into two. */
  var LATIN = /(?:[A-Za-z]:[\\\/]|~\/|\/(?=[A-Za-z]))[^\s«»؟،]*|[A-Za-z][A-Za-z0-9.'_\-]*(?:\/[A-Za-z0-9.'_\-]+)*(?:[ \u00A0][A-Za-z0-9][A-Za-z0-9.'_\-]*(?:\/[A-Za-z0-9.'_\-]+)*)*/g;
  var PATHSTART = /^(?:[A-Za-z]:[\\\/]|~\/|\/)/;
  /* Round 3 bidi (the locked D-01 / D-02 lines; the strings themselves are never changed). Three render-time rules:
     1. a quote or bracket PAIR that encloses exactly one Latin run ("Help improve our AI models", (Cam 1)) goes INSIDE
        that run's LTR isolate, so the pair never splits across two lines and never lands on the wrong side of the words;
     2. a Latin run of 32 characters or fewer (pair included) never breaks across lines (class nb); a longer one may wrap;
     3. an Arabic prefix joined with a tatweel («لـ» before «Anthropic») is bound to the Latin word after it with a
        no-break space, so «لـ» never ends a line alone.
     A lone bracket (D-01 "(Pro ... )": the closing one sits in Arabic text) stays outside the run: the Unicode bidi
     algorithm then draws the pair mirrored and matched, "(" at the left end and ")" at the right, which is how Arabic
     is set; moving only one of the two into the LTR run would draw two openers. */
  var PAIRS = { '"': '"', "“": "”", "(": ")", "[": "]" };
  function txt(s) {
    s = String(s);
    if (LANG !== "ar") return esc(s);
    s = s.replace(/(ـ) (?=[A-Za-z])/g, "$1 ");
    /* R3 (designer F-17): «ما» and a joined «و» never end a line alone: bound to the next word with a no-break space */
    s = s.replace(/(^|[\s(«])(ما|و) (?=\S)/g, "$1$2\u00A0");
    var out = "", last = 0, m;
    LATIN.lastIndex = 0;
    while ((m = LATIN.exec(s))) {
      var run = m[0].replace(/[.\-_']+$/, ""), from = m.index, to = from + run.length;
      var isPath = PATHSTART.test(run), o = from - 1 >= last ? s.charAt(from - 1) : "", c = s.charAt(to);
      var paired = !!o && !isPath && PAIRS[o] === c, shown = paired ? o + run + c : run;
      var cls = isPath ? " m-path" : shown.length <= 32 ? " nb" : "";
      if (paired) { from--; to++; }
      out += esc(s.slice(last, from)) + '<bdi dir="ltr" class="lat' + cls + '">' + esc(shown) + "</bdi>";
      last = to;
      LATIN.lastIndex = last;
    }
    return out + esc(s.slice(last));
  }
  M.txt = txt;
  M.html = function (h) { return { html: h }; };
  /* R2 (designer P2-9): no one-word orphan. A short last word is bound to the word before it with a no-break space
     (CSS text-wrap is not proven in UXP). Only the plain last literal of a string, only when both words are short. */
  function nbLast(s) {
    if (s.split(" ").length < 4) return s;
    return s.replace(/(\S{1,12}) (\S{1,12})$/, "$1\u00A0$2");
  }

  /* t(key, vars): the string for this language, escaped, Latin runs isolated; a var is text or M.html(markup).
     R3 (designer F-09): a plain-text var is substituted BEFORE the Latin runs are isolated, so "After Effects {version}"
     is one LTR run ("After Effects 25.4") and never splits; markup vars go in through private-use placeholders.
     R3 (designer F-17): "· estimate" / "(estimate)" never sits alone on a line (no-break space before it). */
  function t(key, vars) {
    var s = S[key];
    if (s === undefined) { missing.push(key); return "[" + esc(key) + "]"; }
    var parts = s.split(/\{(\w+)\}/), str = "", marks = [];
    for (var i = 0; i < parts.length; i++) {
      if (i % 2 === 0) str += parts[i];
      else {
        var v = vars ? vars[parts[i]] : undefined;
        if (v && typeof v === "object") { str += "\uE000" + marks.length + "\uE001"; marks.push(v.html); }
        else str += v === undefined ? "{" + parts[i] + "}" : String(v);
      }
    }
    if (parts[parts.length - 1]) str = nbLast(str);
    str = str.replace(/ \u00B7 (estimate|تقدير)/g, "\u00A0\u00B7\u00A0$1").replace(/ \((estimate|تقدير)\)/g, "\u00A0($1)");
    return txt(str).replace(/\uE000(\d+)\uE001/g, function (_, n) { return marks[Number(n)]; });
  }
  M.t = t;
  M.raw = function (key) { return S[key]; };
  M.ltr = function (s, cls) { return '<bdi dir="ltr" class="' + (cls || "lat") + '">' + esc(s) + "</bdi>"; };
  /* mono run; a pure time (6:40, 00:00:14:08) tightens the colon, which a monospace face spaces as a full cell ("6 :40") */
  M.mono = function (s) {
    var h = esc(s);
    if (/^[\d:.]+$/.test(s)) h = h.replace(/:/g, '<span class="mo-c">:</span>');
    return '<bdi dir="ltr" class="mono">' + h + "</bdi>";
  };
  /* R2 bidi: LRI ... PDI as characters (aria-label, title, plain text) and the same isolate as markup */
  M.lri = function (s) { return "\u2066" + s + "\u2069"; };
  /* a path or long file name: LTR isolate; wraps after a separator, mid-word only when one part is wider than a line */
  M.path = function (s) { return '<bdi dir="ltr" class="mono m-path">' + esc(s).replace(/([\\\/_.\-])/g, "$1<wbr>") + "</bdi>"; };
  /* middle ellipsis for a no-wrap run: keeps the start and the end (the part an editor recognises) */
  M.mid = function (s, max) {
    max = max || 28;
    return s.length <= max ? s : s.slice(0, Math.ceil(max * 0.45)) + "…" + s.slice(s.length - Math.floor(max * 0.45));
  };

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
  /* a menu path (Window > UXP Plugins > WhyNot Cut) as ONE LTR chip; the separators never mirror */
  M.menuPath = function (parts) {
    return '<span class="m-menupath" dir="ltr">' + parts.map(function (p, i) {
      return (i ? ico("chevron-right", 12, "ink-muted") : "") + '<bdi dir="ltr" class="mono">' + esc(p) + "</bdi>";
    }).join("") + "</span>";
  };

  /* ---- ONE status model (R2 designer P1-3). A condition has one kind, one icon and one name; the header pill, the
     notice and the checklist row all read it. Kinds: ok, warn, error, info, pending, busy, waiting (the pink Needs-you
     dot: waiting FOR THE PERSON, never a problem), paused (work stopped by a problem, amber). ---- */
  var STATUS = {
    ok: ["circle-check", "ink-ok"], warn: ["triangle-alert", "ink-warn"], error: ["circle-x", "ink-error"],
    info: ["info", "ink-info"], pending: ["circle-dashed", "ink-muted"], busy: ["loader-circle", "ink-info"],
    waiting: ["circle-dot", "ink-accent"], paused: ["circle-pause", "ink-warn"]
  };
  M.status = function (kind, size) {
    var s = STATUS[kind] || STATUS.info;
    return ico(s[0], size || 16, s[1], kind === "busy" ? "m-spin" : "");
  };
  M.COND = {
    service_running: "ok", service_starting: "pending", service_off: "error", service_noanswer: "error",
    claude_ready: "ok", claude_unchecked: "pending", claude_signed_out: "warn", claude_missing: "error", claude_offline: "warn", claude_limited: "warn",
    premiere_linked: "ok", premiere_checking: "pending", premiere_unlinked: "error", host_restart: "warn",
    /* R3 (designer F-08): one kind each for three conditions that were drawn in several kinds. restart_needed = the one
       Premiere / After Effects restart (P-02, P-11: one card, one Check again); panel_not_installed = Adobe did not install
       the panel (I-04, I-06, I-07: one red card); frame_missing = a QC frame that could not be exported (P-08: one amber
       tile + one amber chip, no violet info icon). */
    restart_needed: "warn", panel_not_installed: "error", frame_missing: "warn"
  };

  /* ---- components ---- */
  /* A danger or destructive (no backup, not undoable) action NEVER binds Mod+Enter and never shows the primary keycap
     (R2 designer P0-3). o.kind "danger", or o.destructive on a violet button (Uninstall), refuses o.kbd here; the page
     self-check flags any keycap that reaches such a button some other way. */
  M.btn = function (label, o) {
    o = o || {};
    var refuse = o.kind === "danger" || !!o.destructive;
    var kbd = refuse ? null : o.kbd;
    var kind = o.disabled ? "m-btn-disabled" : "m-btn-" + (o.kind || "secondary");
    /* R3 (designer F-01): a disabled MAIN action (a primary, or a keycapped button) is marked m-main-off: the header
       never says "All set" over it, and the self-check counts it */
    var mainOff = o.disabled && (o.kind === "primary" || !!kbd) ? "m-main-off" : "";
    var cls = ["m-btn", kind, mainOff, o.destructive ? "m-btn-destructive" : "", o.block ? "m-btn-block" : "", o.start ? "m-btn-start" : "", o.flush ? "m-btn-flush" : "", o.focus ? "m-btn-focus" : "", o.cls || ""].join(" ");
    var attrs = o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"';
    var icon = o.icon ? (o.icon === "busy" ? M.status("busy") : ico(o.icon, 16, "ink-text")) : "";
    return '<div class="' + cls + '" role="button"' + attrs + ">" + icon + '<span class="m-block">' + label + "</span>" +
      (kbd ? M.kbd(kbd === true ? M.KEY_PRIMARY : kbd) : "") + "</div>";
  };
  /* Addendum G shortcut keycap (.m-kbd): Cmd/Ctrl+Enter runs the screen's primary; ?os=win shows Ctrl, the default is
     macOS (G11). UXP keydown capture is not proven yet (lab). One keycap for panel and installer. */
  M.OS = q.get("os") === "win" ? "win" : "mac";
  M.KEY_PRIMARY = M.OS === "win" ? "Ctrl ↵" : "⌘ ↵";
  M.kbd = function (k, cls) { return '<span class="m-kbd ' + (cls || "") + '" aria-hidden="true">' + esc(k) + "</span>"; };
  M.chip = function (tone, label, icon) {
    var ink = { ok: "ink-ok", warn: "ink-warn", error: "ink-error", info: "ink-info", neutral: "ink-muted" }[tone] || "ink-muted";
    return '<span class="m-chip m-chip-' + tone + '">' + (icon ? ico(icon, 12, ink) : "") + '<span class="m-block">' + label + "</span></span>";
  };
  M.monoChip = function (s) { return '<span class="m-chip m-chip-mono"><bdi dir="ltr" class="mono">' + esc(s) + "</bdi></span>"; };
  M.eyebrow = function (label, cls) { return '<div class="t-eyebrow ' + (cls || "") + '">' + label + "</div>"; };
  M.card = function (inner, cls) { return '<section class="m-card ' + (cls || "") + '">' + inner + "</section>"; };

  /* notice / error card (G5): icon, one white sentence (+ optional meta line), one button, dismiss.
     o = {sub, extra, btn: {label, icon, primary, kbd, disabled, busy, focus}, support, dismiss, cls, pill}
     - the button may be disabled or busy (a working fix); a primary carries the keycap, a disabled one shows it greyed;
     - R2 (designer P2-14): an error notice, and any notice the caller marks dismiss:false, has NO close button: the
       close button would hide the only fix. Warn, info and ok notices keep it unless dismiss:false.
     - o.pill: the short header text for this notice (else the shell derives one from the kind). */
  M.notice = function (kind, text, o) {
    o = o || {};
    var body = '<div class="t-body tx-text">' + text + "</div>";
    if (o.sub) body += '<div class="t-meta tx-muted mt-1">' + o.sub + "</div>";
    if (o.extra) body += o.extra;
    if (o.btn || o.support) {
      var b = o.btn;
      var bo = b ? { kind: b.primary ? "primary" : "secondary", icon: b.busy ? "busy" : b.icon, focus: b.focus, disabled: b.disabled || b.busy,
        kbd: b.primary && b.kbd !== false && !b.busy ? true : false } : null;
      /* the support action (D-05): when it is the card's only action it is the secondary button, else a ghost beside the
         fix; the promise (live) or the "coming soon" line (?support=off) sits UNDER the buttons, one placement (R3 F-03) */
      var sp = o.support ? M.supportParts({ kind: b ? "ghost" : "secondary" }) : null;
      body += '<div class="m-row m-wrap">' +
        (b ? '<div class="m-row me-2 mt-3">' + M.btn(b.label, bo) + "</div>" : "") +
        (sp ? '<div class="m-row me-2 mt-3">' + sp.btn + "</div>" : "") + "</div>" + (sp ? sp.under : "");
    }
    /* R3 (designer F-19): a notice whose button is the screen's fix (primary) is blocking too: no close button */
    var dismissible = o.dismiss === undefined ? kind !== "error" && !(o.btn && o.btn.primary) : !!o.dismiss;
    var x = !dismissible ? "" :
      '<div class="m-x" role="button" tabindex="0" aria-label="' + esc(S["notice.dismiss"] || "Dismiss") + '">' + ico("x", 16, "ink-muted") + "</div>";
    return '<div class="m-notice m-notice-' + kind + " " + (o.cls || "") + '"' + (o.pill ? ' data-pill="' + esc(o.pill) + '"' : "") +
      ' role="' + (kind === "error" ? "alert" : "status") + '">' +
      M.status(kind) + '<div class="m-notice-body">' + body + "</div>" + x + "</div>";
  };
  /* a notice followed by the standard 16 px space: the reserved slot every screen gives its notice */
  M.slot = function (html) { return html + '<div class="mt-4"></div>'; };

  /* ---- support and data links (D-01, D-02, D-05; H24). One place decides what is shown in which state. ----
     R3 (D-05 update 2026-10-16; R3-fix-list S-01): support is the WhyNot Cut WhatsApp chat (MOCK_DATA.support.url, a
     wa.me link with a fixed "WhyNot Cut support" text). It is live, so by default the button is "Copy details and open
     WhatsApp": ONE action that copies the details, then opens the chat (the details are never put in the link), and the
     D-05 reply promise is ALWAYS shown with it. ?support=off (support.url absent) is the alternate state: "Copy details
     for support" only copies, and the one "coming soon" line sits under it.
     supportParts(o): {btn, under, promise, soon}; `under` is the line block that goes under the button row. */
  M.supportParts = function (o) {
    o = o || {};
    var kind = o.kind || "ghost", live = M.supportLive;
    var btn = M.btn(t(live ? "support.copy_open" : "support.copy"), { kind: kind, icon: live ? "message-square" : "copy", cls: "m-btn-wrap" + (o.cls ? " " + o.cls : ""), flush: !!o.flush });
    var promise = live ? t("support.promise") : "";
    var soon = live ? "" : M.soonLine("support.soon");
    return { btn: btn, promise: promise, soon: soon,
      under: live ? '<div class="t-meta tx-muted mt-2 m-support-promise">' + promise + "</div>" : soon };
  };
  /* the same as one standalone block: the button, then the promise (or the "coming soon" line) under it */
  M.supportRow = function (o) {
    var sp = M.supportParts(o);
    return '<div class="m-row m-wrap"><div class="m-row me-2">' + sp.btn + "</div></div>" + sp.under;
  };
  /* D-01: "See plans" opens support.claude.com (a live page, so it is always shown) */
  M.plansLink = function () { return '<div class="m-row mt-1">' + M.linkbtn(t("plans.link"), "external-link") + "</div>"; };
  /* D-02: "Cost and data" opens thewhynot.ai/data. Not live: nothing is drawn and the D-02 line stands alone. */
  M.dataLink = function () { return M.live ? '<div class="m-row mt-1">' + M.linkbtn(t("data.link"), "external-link") + "</div>" : ""; };
  /* H24 for the pages that are NOT published yet (the download page, the guide; the support chat under ?support=off):
     live = the link the caller draws; not live = this ONE "coming soon" line, never a button. One layout everywhere
     (R3 designer F-03): under the button row, mt-2, a 12 px info icon, meta text. key = a "<page>.soon" string. */
  M.soonLine = function (key, cls) {
    return '<div class="m-row-top m-soonline ' + (cls || "mt-2") + '"><div class="m-last-ico">' + ico("info", 12, "ink-muted") + "</div>" +
      '<div class="t-meta tx-muted ms-1 m-grow">' + t(key) + "</div></div>";
  };
  /* the three recurring blocking notices, one wording and one button each (R2 designer §4) */
  M.offline = function (o) {
    o = o || {};
    return M.notice("error", t("engine.off"), { sub: t(o.hintKey || "engine.off.hint_short"),
      btn: { label: t("action.start_app"), icon: "power", primary: o.primary !== false }, dismiss: false, support: o.support !== false });
  };
  /* kind "signed_out" (amber) or "missing" (red). One sentence, one button, one "What Claude sees" link; the account,
     cost and privacy lines live behind that link, never in the card (R2 designer P1-12). o = {text, sub, primary, noLink} */
  M.noClaude = function (kind, o) {
    o = o || {};
    var missingK = kind === "missing";
    return M.notice(missingK ? M.COND.claude_missing : M.COND.claude_signed_out, o.text || t(missingK ? "claude.missing" : "claude.signed_out"), {
      sub: o.sub === undefined ? t(missingK ? "claude.missing.hint" : "claude.signed_out.hint") : o.sub,
      btn: { label: t(missingK ? "action.install_guide" : "action.sign_in"), icon: missingK ? "external-link" : "log-in", primary: o.primary !== false },
      extra: o.noLink ? "" : '<div class="m-row mt-2">' + M.linkbtn(t("privacy.link"), "info") + "</div>", dismiss: false });
  };
  /* no internet (R2 editor P1-03): Claude cannot be reached, the local work carries on, and editing resumes by itself.
     No button: there is nothing to press. Pair it with view.pills = { claude: "offline" }. */
  M.noNet = function (o) {
    o = o || {};
    return M.notice(M.COND.claude_offline, o.text || t("net.off"), { sub: o.sub === undefined ? t("net.off.sub") : o.sub, dismiss: false });
  };
  /* "Premiere (or After Effects) was updated: restart it". The notice's own button takes the violet; every other
     primary on the screen is switched off with the reason (the shell does that, see stalePass) (R2 designer P1-1). */
  M.stale = function (key) {
    key = key || (S["a01.stale"] !== undefined && S["pill.host"] === S["a01.pill.host"] ? "a01.stale" : "update.stale");
    return M.notice("warn", t(key), { btn: { label: t("action.check_again"), icon: "refresh-cw", primary: true }, cls: "m-notice-stale", dismiss: false });
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
    var kind = (o.disabled ? "m-verb-disabled" + (o.primary || o.main ? " m-main-off" : "") : o.primary ? "m-verb-primary" : "m-verb-secondary") + (o.focus ? " m-verb-focus" : "");
    var ink = o.disabled ? "ink-disabled" : o.primary ? "ink-on-primary" : "ink-text";
    var attrs = o.disabled ? ' aria-disabled="true" tabindex="-1"' : ' tabindex="0"';
    return '<div class="m-verb ' + kind + ' ' + (o.cls || "") + '" role="button"' + attrs + ">" +
      '<div class="m-verb-well">' + ico(o.icon, 20, ink) + "</div>" +
      '<div class="m-verb-text"><div class="t-verb m-verb-title">' + o.title + "</div>" +
        (o.done
          ? '<div class="m-row-top"><div class="m-last-ico">' + M.status(o.disabled ? "pending" : "ok", 12) + '</div><div class="t-meta m-verb-sub ms-1 m-grow">' + o.done + "</div></div>"
          : '<div class="t-meta m-verb-sub">' + o.sub + "</div>") + "</div>" +
      (o.primary && o.kbd !== false && !o.disabled ? M.kbd(M.KEY_PRIMARY, "m-kbd-verb") : "") +
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

  /* step strip: 7 segments + "Step n of 7 · name"; states: done / run / wait / fail / pend.
     R2 (designer P2-4): "wait" means waiting FOR THE PERSON, so its status icon is the pink Needs-you dot, not the amber
     warning triangle (amber is for problems). A caller that passes "warn" with a wait segment gets "waiting". */
  M.steps = function (states, current, statusKind) {
    var keys = ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"];
    if (statusKind === "warn" && states.indexOf("wait") >= 0) statusKind = "waiting";
    var segs = states.map(function (s) { return '<span class="m-stepseg' + (s === "pend" ? "" : " m-stepseg-" + s) + '"></span>'; }).join("");
    /* plain text in this release (decision 6): no role, no chevron */
    return '<div class="m-steps"><div class="m-stepbar" aria-hidden="true">' + segs + "</div>" +
      '<div class="m-row mt-2">' + M.status(statusKind || "info", 12) +
      '<div class="t-meta tx-muted ms-1 m-grow">' + t("steps.position", { n: current + 1, of: 7, name: S["step." + keys[current]] }) + "</div></div></div>";
  };

  /* ---- Addendum G components (additive) ---- */
  /* n-segment bar + "3 of 4 ready" line (P-01 setup progress) */
  M.segbar = function (n, done, label, kind) {
    var segs = "";
    for (var i = 0; i < n; i++) segs += '<span class="m-stepseg' + (i < done ? " m-stepseg-done" : "") + '"></span>';
    return '<div class="m-steps' + (done < n ? " m-steps-open" : "") + '"><div class="m-stepbar" aria-hidden="true">' + segs + "</div>" +
      '<div class="m-row mt-2">' + M.status(kind || (done === n ? "ok" : "pending"), 12) + '<div class="t-meta tx-muted ms-1 m-grow">' + label + "</div></div></div>";
  };
  /* a timecode that seeks the Premiere playhead: a 32 px ghost control with a 12 px play icon (never mirrors);
     ships only if the UXP lab proves the playhead API, else it falls back to plain meta */
  M.seek = function (tc) {
    return '<div class="m-seek" role="button" tabindex="0" aria-label="' + esc((S["seek.aria"] || "Play from {tc}").replace("{tc}", M.lri(tc))) + '">' +
      ico("play", 12, "ink-muted") + '<span class="t-mono tx-muted ms-1">' + M.mono(tc) + "</span></div>";
  };
  /* media well (R2 designer P1-7): the ONE tile for a poster, a frame or a thumbnail. 9:16, a #0D0D0D well, a clapperboard
     fallback glyph (never a person), 36 x 64 (48 x 84 at 480) for a poster. o = {kind: "poster"|"frame", w, h, disabled,
     inner (html drawn in the well), safe (draws the safe-area outline round inner), gone, wait, cls} */
  M.media = function (o) {
    o = o || {};
    var kind = o.kind || "poster";
    var style = (o.w ? "width:" + o.w + "px;flex-basis:" + o.w + "px;" : "") + (o.h ? "height:" + o.h + "px;" : "");
    var glyph = o.gone ? ico("image-off", 20, "ink-muted") : o.wait ? ico("loader-circle", 20, "ink-muted", "m-spin") : ico("clapperboard", 20, o.disabled ? "ink-disabled" : "ink-muted");
    var inner = o.inner ? (o.safe ? '<div class="m-media-safe">' + o.inner + "</div>" : o.inner) : glyph;
    return '<div class="m-media m-media-' + kind + (o.disabled ? " m-media-off" : "") + " " + (o.cls || "") + '"' + (style ? ' style="' + style + '"' : "") + ' aria-hidden="true">' + inner + "</div>";
  };
  M.poster = function (o) { return M.media({ kind: "poster", disabled: !!(o && o.disabled) }); };
  /* a text link that is a control (wraps, violet text on the page or a card; 2 px rest border, radius 8, 32 px high) */
  M.linkbtn = function (label, icon) {
    return '<div class="m-linkbtn" role="button" tabindex="0">' + (icon ? ico(icon, 16, "ink-info") : "") + '<span class="m-block' + (icon ? " ms-1" : "") + '">' + label + "</span></div>";
  };
  /* edit map: a 24 px #0D0D0D strip with three lanes laid out by flex percentages (no absolute positioning):
     cuts as 1 px ticks, statements as 4 px bars (flagged ones in the warn colour), B-roll as 4 px grey bars.
     m = {dur, cuts:[s], statements:[[a,b,flagged]], broll:[[a,b]]} */
  M.editMap = function (m) {
    /* the contract shape (eng-data-contract §2.2 plan.edit_map {duration_s, spans[]}) is converted here */
    if (m && m.spans) {
      var c = { dur: m.duration_s, cuts: [], statements: [], broll: [] };
      m.spans.forEach(function (sp) {
        if (sp.kind === "cut") c.cuts.push(sp.start_s);
        else if (sp.kind === "statement") c.statements.push([sp.start_s, sp.end_s]);
        else if (sp.kind === "flagged") c.statements.push([sp.start_s, sp.end_s, true]);
        else if (sp.kind === "broll") c.broll.push([sp.start_s, sp.end_s]);
      });
      m = c;
    }
    var pct = function (x) { return (100 * x / m.dur).toFixed(2) + "%"; };
    var lane = function (spans, cls) {
      var out = "", at = 0;
      spans.forEach(function (sp) {
        if (sp[0] > at) out += '<span class="m-map-gapx" style="width:' + pct(sp[0] - at) + '"></span>';
        out += '<span class="' + cls + (sp[2] ? " m-map-flag" : "") + '" style="width:' + pct(sp[1] - sp[0]) + '"></span>';
        at = sp[1];
      });
      return '<div class="m-map-lane ' + cls + '-lane">' + out + "</div>";
    };
    var ticks = "", at = 0;
    m.cuts.forEach(function (c) { ticks += '<span class="m-map-gapx" style="width:' + pct(c - at) + '"></span><span class="m-map-cut"></span>'; at = c; });
    var fmt = function (sec) { return Math.floor(sec / 60) + ":" + ("0" + Math.round(sec % 60)).slice(-2); };
    return '<div class="m-map" role="img" aria-label="' + esc(S["map.aria"] || "Edit map") + '">' +
      '<div class="m-map-strip"><div class="m-map-lane m-map-cut-lane">' + ticks + "</div>" + lane(m.statements, "m-map-stmt") + lane(m.broll, "m-map-broll") + "</div>" +
      '<div class="m-map-ends"><span class="t-mono tx-muted">' + M.mono("0:00") + '</span><span class="m-spacer"></span><span class="t-mono tx-muted">' + M.mono(fmt(m.dur)) + "</span></div>" +
      '<div class="m-map-legend">' +
        '<span class="m-map-key"><span class="m-map-sw m-map-sw-cut"></span><span class="t-meta tx-muted ms-1">' + t("map.cut") + "</span></span>" +
        '<span class="m-map-key"><span class="m-map-sw m-map-sw-stmt"></span><span class="t-meta tx-muted ms-1">' + t("map.statement") + "</span></span>" +
        '<span class="m-map-key"><span class="m-map-sw m-map-sw-broll"></span><span class="t-meta tx-muted ms-1">' + t("map.broll") + "</span></span>" +
        '<span class="m-map-key"><span class="m-map-sw m-map-sw-flag"></span><span class="t-meta tx-muted ms-1">' + t("map.flagged") + "</span></span>" +
      "</div></div>";
  };
  /* solid tappable row (Settings on Home): #141414, radius 8, 2 px matching border */
  M.rowbtn = function (icon, label) {
    return '<div class="m-rowbtn" role="button" tabindex="0">' + ico(icon, 16, "ink-muted") + '<div class="t-label ms-2 m-grow">' + label + "</div>" + M.chev() + "</div>";
  };

  /* progress bar; o.paused draws the fill solid amber (work stopped by a problem, never the running gradient) */
  M.progress = function (pct, o) {
    return '<div class="m-track"><span class="m-fill' + (o && o.paused ? " m-fill-paused" : "") + '" style="width:' + pct + '%"></span></div>';
  };

  M.input = function (placeholder, o) {
    o = o || {};
    return '<div class="m-input' + (o.textarea ? " m-textarea" : "") + (o.focus ? " m-input-focus" : "") + '" role="textbox" tabindex="0">' +
      '<span class="m-block ' + (o.value ? "tx-text" : "tx-muted") + ' t-body">' + (o.value || placeholder) + "</span></div>";
  };

  /* ==== R2 promoted components (were re-built in css/js of each group; the group copies stay until the group worker
     moves each screen over, see R2-fix-list.md section 1) ==== */
  /* back row: a start-aligned ghost button with the chevron that points to the start of the reading direction */
  M.back = function (label) {
    return '<div class="m-row m-back">' + M.btn(label, { kind: "ghost", icon: M.rtl ? "chevron-right" : "chevron-left", flush: true }) + "</div>";
  };
  /* a trust line (what is created or changed, what stays untouched) and a time-saved line: one icon colour rule,
     ok-green icon, meta text */
  M.trust = function (html, cls) {
    return '<div class="m-saved ' + (cls || "") + '">' + ico("shield-check", 16, "ink-ok") + '<div class="t-meta tx-muted ms-2 m-grow">' + html + "</div></div>";
  };
  M.saved = function (html, cls) {
    return '<div class="m-saved ' + (cls || "") + '">' + ico("timer", 16, "ink-ok") + '<div class="t-meta tx-muted ms-2 m-grow">' + html + "</div></div>";
  };
  /* neutral 4 px dot bullet (confirm lists, "what will change") */
  M.bullet = function (html, cls) {
    return '<div class="m-bullet ' + (cls || "") + '"><span class="m-bullet-dot"><span class="m-dot"></span></span><div class="t-body ms-2 m-grow">' + html + "</div></div>";
  };
  /* static info row: icon name, title, sub, end html; o.dense = 8 px rows. Paddings count the 1 px divider (11 + 1 = 12). */
  M.listrow = function (icon, title, sub, end, o) {
    o = o || {};
    return '<div class="m-lrow' + (o.dense ? " m-lrow-dense" : "") + " " + (o.cls || "") + '">' + (icon ? ico(icon, 16, o.ink || "ink-muted") : "") +
      '<div class="m-lrow-text"><div class="t-label">' + title + "</div>" + (sub ? '<div class="t-meta tx-muted">' + sub + "</div>" : "") + "</div>" +
      (end ? '<div class="m-lrow-end">' + end + "</div>" : "") + "</div>";
  };
  /* stage list. stages = [[kind, label, end meta, sub], ...]; kind ok | busy | pending | error | waiting | paused */
  M.stages = function (stages) {
    return stages.map(function (s) {
      return '<div class="m-lrow m-lrow-dense m-stage">' + M.status(s[0]) +
        '<div class="m-lrow-text"><div class="t-label' + (s[0] === "pending" ? " tx-muted" : "") + '">' + s[1] + "</div>" +
        (s[3] ? '<div class="t-meta ' + (s[0] === "error" ? "tx-text" : "tx-muted") + '">' + s[3] + "</div>" : "") + "</div>" +
        (s[2] ? '<div class="m-lrow-end"><span class="t-meta tx-muted">' + s[2] + "</span></div>" : "") + "</div>";
    }).join("");
  };
  /* radio row: a 32 px control row with a 20 px ring; the dot is a <span>. o = {sub, on?, focus, disabled, end} */
  M.radio = function (label, on, o) {
    o = o || {};
    return '<div class="m-radio' + (o.focus ? " m-radio-focus" : "") + (o.disabled ? " m-radio-dis" : "") + '" role="radio" tabindex="' + (o.disabled ? -1 : 0) + '" aria-checked="' + !!on + '">' +
      '<span class="m-ring' + (on ? " m-ring-on" : "") + '">' + (on ? '<span class="m-ring-dot"></span>' : "") + "</span>" +
      '<div class="m-col m-grow ms-2"><div class="t-label">' + label + "</div>" + (o.sub ? '<div class="t-meta tx-muted">' + o.sub + "</div>" : "") + "</div>" + (o.end || "") + "</div>";
  };
  /* segmented control (Reels / Podcast, Simple / Advanced). opts = [label]; on = index; o.focus = index; o.disabled */
  M.segmented = function (opts, on, o) {
    o = o || {};
    var segs = opts.map(function (l, i) {
      var cls = "m-segopt" + (i === on ? " m-segopt-on" : "") + (o.focus === i ? " m-segopt-focus" : "");
      return '<div class="' + cls + '" role="button" tabindex="' + (o.disabled ? -1 : 0) + '" aria-pressed="' + (i === on) + '"><span class="m-block">' + l + "</span></div>";
    }).join("");
    return '<div class="m-segctl' + (o.disabled ? " m-segctl-dis" : "") + '" role="group"' + (o.disabled ? ' aria-disabled="true"' : "") + ">" + segs + "</div>";
  };
  /* toggle button (a track V1 / A1): state "on" | "off" | "locked" */
  M.toggle = function (label, state, o) {
    o = o || {};
    var on = state === "on", dis = !!o.disabled;
    var cls = "m-tog" + (dis ? " m-tog-dis" : on ? " m-tog-on" : "") + (o.focus ? " m-tog-focus" : "");
    var icon = state === "locked" ? ico("lock", 12, dis ? "ink-disabled" : "ink-warn") : ico(on ? "check" : "square", 12, dis ? "ink-disabled" : on ? "ink-text" : "ink-muted");
    return '<div class="' + cls + '" role="checkbox" tabindex="' + (dis ? -1 : 0) + '" aria-checked="' + on + '">' + icon + M.ltr(label) + "</div>";
  };
  /* select control: secondary fill, trailing chevron-down */
  M.select = function (label, o) {
    o = o || {};
    var cls = "m-btn " + (o.disabled ? "m-btn-disabled" : "m-btn-secondary") + " m-select" + (o.grow ? " m-select-grow" : "") + (o.focus ? " m-btn-focus" : "") + " " + (o.cls || "");
    return '<div class="' + cls + '" role="button" aria-haspopup="listbox" tabindex="' + (o.disabled ? -1 : 0) + '"><span class="m-block">' + label + "</span>" +
      ico("chevron-down", 16, o.disabled ? "ink-disabled" : "ink-muted") + "</div>";
  };
  /* slider; pct 0..100; fills from the reading start */
  M.slider = function (pct, o) {
    o = o || {};
    return '<div class="m-slider' + (o.disabled ? " m-slider-dis" : "") + '"><span class="m-slider-fill" style="width:' + pct + '%"></span>' +
      '<span class="m-thumb' + (o.focus ? " m-thumb-focus" : "") + '" role="slider" tabindex="0" aria-valuenow="' + pct + '"></span><span class="m-slider-rest"></span></div>';
  };
  /* section header control (opens or closes a section) */
  M.sechead = function (label, count, open) {
    return '<div class="m-sechead" role="button" tabindex="0" aria-expanded="' + !!open + '">' + ico(open ? "chevron-up" : "chevron-down", 16, "ink-muted") +
      '<div class="t-label ms-2 m-grow">' + label + "</div>" + (count ? '<div class="m-end ms-2">' + count + "</div>" : "") + "</div>";
  };
  /* tile (frame, template, thumbnail): a control. o = {media (html), label, meta, reason, on, fail, focus, disabled, plain}.
     A failing tile gets the error border and says why (R2 designer P1-2); selected = the deep fill. */
  M.tile = function (o) {
    var cls = "m-tile" + (o.on ? " m-tile-on" : "") + (o.fail ? " m-tile-fail" : "") + (o.focus ? " m-tile-focus" : "") + (o.disabled ? " m-tile-off" : "") + (o.plain ? " m-tile-plain" : "");
    var attrs = o.plain ? "" : ' role="button" tabindex="' + (o.disabled ? -1 : 0) + '"' + (o.disabled ? ' aria-disabled="true"' : "");
    return '<div class="' + cls + '"' + attrs + ">" + (o.media || "") +
      (o.label ? '<div class="t-label mt-2">' + o.label + "</div>" : "") + (o.meta ? '<div class="t-meta">' + o.meta + "</div>" : "") +
      (o.reason ? '<div class="t-meta tx-text mt-1">' + o.reason + "</div>" : "") + "</div>";
  };
  /* the open log: mono lines, LTR, wrap anywhere so a line is read in full. lines = [[time, text, "err"|"warn"|undefined]] */
  M.logline = function (lines) {
    var n = lines ? lines.length : 0;
    return '<div class="m-logbody" role="log">' + (n ? lines.map(function (l) {
      return '<div class="m-logline t-mono"><span class="m-logtime">' + esc(l[0]) + '</span><span class="m-logtext' + (l[2] ? " m-logtext-" + l[2] : "") + '">' + esc(l[1]) + "</span></div>";
    }).join("") : '<div class="t-meta tx-muted">' + (S["p11.log.empty"] || "") + "</div>") + "</div>";
  };
  /* confirm dialog (G6): an in-panel sheet card, warn tint (red when nothing can bring the work back), no overlay.
     Keycap policy (R2 designer P0-3): a safe confirm carries the primary keycap; a DANGER confirm carries none and the
     SAFE button ("Keep my project") is focused by default and takes Esc, so Return can never trigger the danger.
     o = {title, text, changesLabel, changes [html], backupLabel, backupText, backup (file name) | nobackup (html) |
     reversible (html), untouched (html), danger (default: no backup and not reversible), confirm {label, icon, disabled,
     busy, focus}, keep, hint} */
  M.dialog = function (o) {
    var c = o.confirm;
    var safe = !!(o.backup || o.reversible);
    var danger = o.danger !== undefined ? !!o.danger : !safe;
    var list = (o.changes || []).map(function (h, i) { return M.bullet(h, i ? "" : "m-bullet-first"); }).join("");
    var backup = o.reversible && !o.backup ? '<div class="mt-4">' + M.trust(o.reversible) + "</div>"
      : o.backup ? '<div class="t-label mt-4">' + o.backupLabel + '</div>' + (o.backupText ? '<div class="t-meta tx-muted mt-1">' + o.backupText + "</div>" : "") +
        '<div class="mt-2"><div class="m-inset">' + M.path(o.backup) + "</div></div>"
      : '<div class="m-row-top mt-4">' + M.status("error") + '<div class="t-body ms-2 m-grow">' + o.nobackup + "</div></div>";
    if (o.untouched) backup += '<div class="mt-3">' + M.trust(o.untouched) + "</div>";
    /* R3 (designer F-21): in ANY confirm the keycap goes on the SAFE button; the confirm (Rebuild replaces the editor's
       own timeline changes even with a backup) needs a click. Mod+Enter in a confirm lands on the safe button (keys()). */
    var confirm = M.btn(c.label, { kind: danger ? "danger" : "primary", block: true, icon: c.busy ? "busy" : c.icon, disabled: c.disabled || c.busy, focus: c.focus && !danger });
    var keep = M.btn(o.keep, { kind: "secondary", block: true, kbd: "Esc", focus: danger || !c.focus });
    return '<div class="m-dialog' + (danger ? " m-dialog-danger" : "") + '" role="alertdialog">' +
      '<div class="m-row-top">' + M.status(danger ? "error" : "warn") + '<div class="t-label ms-2 m-grow">' + o.title + "</div></div>" +
      (o.text ? '<div class="t-body mt-2">' + o.text + "</div>" : "") +
      '<div class="t-label mt-4">' + o.changesLabel + "</div>" + list + backup +
      '<div class="m-col mt-4">' + (danger ? keep + '<div class="mt-2"></div>' + confirm : confirm + '<div class="mt-2"></div>' + keep) + "</div>" +
      (o.hint ? '<div class="t-meta tx-muted mt-2">' + o.hint + "</div>" : "") + "</div>";
  };

  /* ---- shell: header (G1-G3), hairline, tabs (G4), scroll, log row (G7), footer (G8) ---- */
  var PILL = {
    engine: { running: ["ok", "pill.engine.running"], off: ["error", "pill.engine.off"], starting: ["pending", "pill.engine.starting"], noanswer: ["error", "pill.engine.noanswer"] },
    claude: { ready: ["ok", "pill.claude.ready"], unchecked: ["pending", "pill.claude.unchecked"], signed_out: ["warn", "pill.claude.signed_out"], missing: ["error", "pill.claude.missing"], offline: ["warn", "pill.claude.offline"], limited: ["warn", "pill.claude.limited"] },
    host: { linked: ["ok", "pill.host.linked"], unlinked: ["error", "pill.host.unlinked"], checking: ["pending", "status.pending"] }
  };
  var PILL_OK = { engine: "running", claude: "ready", host: "linked" };
  /* E-D3 r1 #2 / editor #3: the name (key word) shows from 360 px, and at 300 px on any pill that is not ok, so a
     failing pill always says WHAT failed. Row 3 may wrap to two lines instead of dropping names. */
  function pills3(p) {
    var out = "";
    ["engine", "claude", "host"].forEach(function (k) {
      var st = PILL[k][p[k] || PILL_OK[k]];
      var showKey = W >= 360 || st[0] !== "ok";
      var key = showKey ? '<span class="m-pill-key">' + t("pill." + k) + "</span> " : "";
      /* R3: a stopped service (off / not responding) is marked, so the self-check can catch a spinner under it (F-07) */
      var stop = k === "engine" && (st[0] === "error") ? " m-pill-stop" : "";
      out += '<div class="m-pill' + stop + '">' + M.status(st[0], 12) + '<span class="m-pill-txt">' + key + t(st[1]) + "</span></div>";
    });
    return '<div class="m-pills">' + out + "</div>";
  }
  function pill1(kind, text, cls) {
    return '<div class="m-pills"><div class="m-pill ' + (cls || "") + '">' + M.status(kind, 12) + '<span class="m-pill-txt">' + text + "</span></div></div>";
  }
  /* ---- the live state of the screen's own body (R2 designer P0-1, owner F-06; R3 designer F-01, owner N-13, editor
     P2-01). The header status is derived from what is on screen, never from the pill values alone, and it never says
     "All set" over ANY open problem. One list of body signals (SIG) feeds both the header (liveState) and the page
     self-check (M.selfCheckExtras), and the self-check judges the RENDERED header against the rendered body, so a screen's
     own view.status, a group after-mount patch or a new component cannot hide a problem under a green pill.
     Precedence (first match wins):
       a confirm card (any .m-dialog / .pc-dialog / .ta-dialog) -> no pill: the card is the state;
       an error (error card, danger confirm, error chip, failed tile, red status icon) -> red, "Needs attention";
       a restart notice -> amber "{host} needs a restart" (while work runs: "restart after this job", see stalePass);
       a warn card or paused work (amber pause bar) -> amber, the notice's own data-pill or "Needs a look";
       a warn chip or amber status icon (a partial result, "Left out", a flagged line) -> amber "Needs a look", unless
         the Needs-you badge already says it (a problem outranks progress);
       running work (spinner, indeterminate bar) -> busy "Working…";
       first-run setup with steps open -> waiting "Setting up · 3 of 4";
       a Needs-you item -> no pill (the badge says it);
       a disabled main action (m-main-off) -> amber "Waiting" (the screen names the reason with view.status or data-pill);
       nothing open -> "All set".
     A screen may set view.status = {kind, text} to name its own state; view.pillx / view.noCollapse keep the three pills. ---- */
  var SIG = {
    confirm: ".m-dialog, .pc-dialog, .ta-dialog",
    err: ".m-notice-error, .m-dialog-danger, .pc-dialog-danger, .ta-dialog-danger, .m-chip-error, .m-tile-fail, .ink-error",
    warn: ".m-notice-warn, .m-fill-paused",
    busy: ".m-spin, .pc-indet",
    soft: ".m-chip-warn, .ink-warn",
    open: ".m-steps-open",
    off: ".m-main-off"
  };
  M.SIG = SIG;
  var STALE_KEYS = ["update.stale", "p13.stale", "a01.stale"];
  function plain(html) { var d = document.createElement("div"); d.innerHTML = html; return (d.textContent || "").replace(/\s+/g, " ").trim(); }
  function staleNotices(root) {
    var texts = STALE_KEYS.filter(function (k) { return S[k] !== undefined; }).map(function (k) { return plain(t(k)); });
    var out = [];
    var ns = root.querySelectorAll(".m-notice");
    for (var i = 0; i < ns.length; i++) {
      var tx = (ns[i].textContent || "").replace(/\s+/g, " ").trim();
      if (ns[i].className.indexOf("m-notice-stale") >= 0 || texts.some(function (x) { return x && tx.indexOf(x) >= 0; })) out.push(ns[i]);
    }
    return out;
  }
  /* running work in the body (outside the restart notices themselves): a spinner, an indeterminate bar, a running fill */
  var RUNNING = ".m-spin, .pc-indet, .m-track .m-fill:not(.m-fill-paused)";
  function runningIn(root, notices) {
    var els = root.querySelectorAll(RUNNING), n = 0;
    for (var i = 0; i < els.length; i++) {
      var inNotice = false;
      for (var j = 0; j < notices.length; j++) if (notices[j].contains(els[i])) inNotice = true;
      if (!inNotice) n++;
    }
    return n;
  }
  /* counts of every signal in a root (the probe of view.body + view.bar, or the rendered .m-scroll + .m-actionbar) */
  function signals(roots) {
    var c = { confirm: 0, err: 0, warn: 0, busy: 0, soft: 0, open: 0, off: 0, stale: 0, running: 0 };
    roots.forEach(function (r) {
      if (!r) return;
      for (var k in SIG) c[k] += r.querySelectorAll(SIG[k]).length;
      var st = staleNotices(r);
      c.stale += st.length;
      c.running += runningIn(r, st);
    });
    return c;
  }
  function liveState(view) {
    var probe = document.createElement("div");
    probe.innerHTML = (view.body || "") + (view.bar || "");
    var st = signals([probe]);
    var tagged = probe.querySelector("[data-pill]");
    st.pillText = tagged ? tagged.getAttribute("data-pill") : "";
    return st;
  }
  function statusRow(view) {
    var p = view.pills || {};
    if (view.pillx || view.noCollapse) return pills3(p);
    var allOk = true;
    for (var k in p) if (p[k] !== PILL_OK[k]) allOk = false;
    if (!allOk) return pills3(p);
    if (view.status) return pill1(view.status.kind, view.status.text);
    var st = liveState(view), tagged = esc(st.pillText);
    if (st.confirm) return "";
    if (st.err) return pill1("error", tagged || t("pill.attention"));
    if (st.stale) return pill1("warn", t(st.running ? "pill.restart_after" : "pill.restart", { host: S["pill.host"] }));
    if (st.warn) return pill1("warn", tagged || t("pill.check"));
    if (st.soft && !(view.needs > 0)) return pill1("warn", tagged || t("pill.check"));
    if (st.busy) return pill1("busy", tagged || t("pill.working"));
    var su = view.setup && typeof view.setup === "object" ? view.setup : null;
    if (st.open || (su && su.done < su.of)) return pill1("waiting", t("pill.setup", { n: su ? su.done : 0, of: su ? su.of : 4 }));
    if (view.needs > 0) return "";
    if (st.off) return pill1("warn", tagged || t("pill.waiting"));
    return pill1("ok", t("pill.all_set"), "m-pill-allset");
  }
  /* Needs-you badge (E-D3 r1 editor #8, decision 9): ONE count, the same number as the Edit tab count; a control
     (div role=button, 2 px rest border) with a forward chevron, so it reads as "opens the list". The label stays at 300. */
  function badge(n) {
    if (!n || n <= 0) return "";
    var count = n > 99 ? "99+" : String(n);
    var chev = ico(LANG === "ar" ? "chevron-left" : "chevron-right", 12, "ink-on-accent");
    var inner = '<span class="m-badge' + (n > 99 ? " m-badge-99" : "") + '"><span class="m-block">' + t("needs.label") + '</span><span class="m-badge-count ms-1">' + M.ltr(count, "lat") + "</span>" + chev + "</span>";
    return '<div class="m-badge-hit me-1" role="button" tabindex="0" aria-label="' + esc((S["needs.open"] || "").replace("{n}", count)) + '">' + inner + "</div>";
  }
  /* the language switch: both glyphs from 360 px; at 300 px one 32 px control showing the language you would switch TO */
  function langSwitch() {
    var seg = function (l) {
      var on = l === LANG;
      return '<div class="m-seg' + (l === "ar" ? " m-seg-ar" : "") + (on ? " m-seg-on" : "") + '" role="button" tabindex="0" lang="' + l +
        '" aria-pressed="' + on + '" aria-label="' + esc(S["lang." + l]) + '">' + esc(S["lang." + l + ".short"]) + "</div>";
    };
    if (W < 360) return '<div class="m-lang m-lang-solo" role="group">' + seg(LANG === "ar" ? "en" : "ar") + "</div>";
    return '<div class="m-lang" role="group">' + seg("ar") + seg("en") + "</div>";
  }
  /* row 2: client · item as ONE control (opens the client / video picker). The client name is an LTR run that truncates
     at its END with an ellipsis, in both languages; the item code never drops (R2 designer P1-4, editor P1-01). */
  function ctxRow(o) {
    var D = M.D;
    /* J-T9a: view.noclientKey names the line ("cs.noclient" = "No client open" on the Home empty state, J12) */
    if (o.noclient) return '<span class="m-ctx t-meta tx-muted">' + t(o.noclientKey || "status.novideo") + "</span>";
    var chevd = ico("chevron-down", 12, "ink-muted");
    var inner = o.ctxClientOnly
      ? '<span class="m-ctx-name tx-muted">' + M.ltr(D.client, "lat") + "</span>"
      : '<span class="m-ctx-name tx-muted">' + M.ltr(D.client, "lat") + '</span><span class="m-ctx-sep tx-muted">·</span><span class="m-ctx-item tx-text">' + M.ltr(D.item) + "</span>";
    return '<div class="m-ctxbtn t-meta" role="button" tabindex="0" aria-label="' + esc(S["hdr.ctx.aria"] || "Change client or video") + '">' + inner + '<span class="m-ctx-chev ms-1">' + chevd + "</span></div>";
  }
  function header(o) {
    var status = statusRow(o);
    /* E-D3 r1: the pills sit on row 3 at every width (the longer plain names no longer fit beside client · item at 480).
       The logo lockup (monogram + 8 px + wordmark) is ONE fixed LTR unit that never mirrors: in Arabic it moves as a
       whole to the right edge (direction §9, R2 designer P1-5). */
    return '<header class="m-hdr">' +
      '<div class="m-hdr-r1 m-gut"><span class="m-lockup" dir="ltr"><img class="m-mono" src="../../../premiere-uxp/icons/dark/icon-48.png" alt="" width="20" height="20">' +
        '<span class="m-wordmark m-lockup-wm">' + M.ltr(S["product.name"], "wm") + '</span></span><span class="m-spacer"></span>' + badge(o.needs) + langSwitch() + "</div>" +
      '<div class="m-hdr-r2 m-gut">' + ctxRow(o) + "</div>" +
      (status ? '<div class="m-hdr-r3 m-gut">' + status + "</div>" : "") +
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
    /* R3 (editor P2-17): the Arabic footer is an Arabic line («من thewhynot.ai»), so it is set RTL with the domain isolated */
    return '<footer class="m-footer"><bdi dir="' + (M.rtl ? "rtl" : "ltr") + '" class="m-footer-txt">' + t("footer.powered") + "</bdi></footer>";
  }

  /* ---- stale pass (R2 designer P1-1): under a restart notice the screen's main action is OFF, with the reason, and the
     notice's own "Check again" takes the violet. Runs on every screen, so a group screen needs no change of its own. ---- */
  function disableBtn(el) {
    el.className = el.className.replace("m-btn-primary", "m-btn-disabled m-main-off").replace("m-btn-secondary", "m-btn-disabled").replace(/\bm-btn-focus\b/, "");
    el.setAttribute("aria-disabled", "true"); el.setAttribute("tabindex", "-1");
    var k = el.querySelector(".m-kbd"); if (k) k.parentNode.removeChild(k);
  }
  function disableVerb(el, reason) {
    el.className = el.className.replace("m-verb-primary", "m-verb-disabled m-main-off").replace(/\bm-verb-focus\b/, "");
    el.setAttribute("aria-disabled", "true"); el.setAttribute("tabindex", "-1");
    var k = el.querySelector(".m-kbd"); if (k) k.parentNode.removeChild(k);
    var svgs = el.querySelectorAll("svg");
    for (var i = 0; i < svgs.length; i++) svgs[i].setAttribute("class", String(svgs[i].getAttribute("class")).replace(/ink-[a-z-]+/, "ink-disabled"));
    var sub = el.querySelector(".m-verb-sub"); if (sub && reason) sub.innerHTML = reason;
  }
  /* R3 (designer F-02, decision 7): while work is RUNNING (a build, a render, a download) the restart notice never tells
     the editor to restart now: it says to let the job finish or stop it first, and its Check again stays grey until the
     job ends. The rest of the screen's main actions are still off with the reason. Buttons that need the host but are
     not primaries carry .m-needs-host and are switched off too (F-20: P-01 "Try the sample clip"). */
  function bodyRoots(panel) { return [panel.querySelector(".m-scroll"), panel.querySelector(".m-actionbar")]; }
  function stalePass(panel) {
    var notices = staleNotices(panel);
    if (!notices.length) return;
    var reason = t("stale.reason", { host: S["pill.host"] });
    var inside = function (el) { for (var i = 0; i < notices.length; i++) if (notices[i].contains(el)) return true; return false; };
    var running = 0;
    bodyRoots(panel).forEach(function (r) { if (r) running += runningIn(r, notices); });
    notices.forEach(function (n) {
      if (n.className.indexOf("m-notice-stale") < 0) n.className += " m-notice-stale";
      var b = n.querySelector(".m-btn-secondary, .m-btn-primary");
      if (running) {
        var body = n.querySelector(".m-notice-body > .t-body");
        if (body) body.innerHTML = t("update.stale_running", { host: S["pill.host"] });
        if (b) { disableBtn(b); b.className = b.className.replace(" m-main-off", ""); }
        n.setAttribute("data-running", "1");
      } else if (b) {
        b.className = b.className.replace("m-btn-secondary", "m-btn-primary");
        if (!b.querySelector(".m-kbd")) b.insertAdjacentHTML("beforeend", M.kbd(M.KEY_PRIMARY));
      }
    });
    var told = false;
    var prim = panel.querySelectorAll(".m-btn-primary, .m-needs-host");
    for (var i = 0; i < prim.length; i++) {
      if (inside(prim[i]) || prim[i].className.indexOf("m-btn-disabled") >= 0) continue;
      var wasPrimary = prim[i].className.indexOf("m-btn-primary") >= 0;
      disableBtn(prim[i]);
      if (!wasPrimary) { prim[i].className = prim[i].className.replace(" m-main-off", ""); continue; }
      if (!told) {
        var host = prim[i].parentNode && prim[i].parentNode.className.indexOf("m-row") >= 0 ? prim[i].parentNode : prim[i];
        host.insertAdjacentHTML("afterend", '<div class="t-meta tx-muted mt-2 m-stale-reason">' + reason + "</div>");
        told = true;
      }
    }
    var verbs = panel.querySelectorAll(".m-verb-primary");
    for (var j = 0; j < verbs.length; j++) disableVerb(verbs[j], reason);
  }
  /* R3 (designer F-19): a warn notice keeps no close button while the screen's main action is off: it is the only way on */
  function dismissPass(panel) {
    var off = 0;
    bodyRoots(panel).forEach(function (r) { if (r) off += r.querySelectorAll(".m-main-off").length; });
    if (!off) return;
    var xs = panel.querySelectorAll(".m-notice-warn > .m-x");
    for (var i = 0; i < xs.length; i++) xs[i].parentNode.removeChild(xs[i]);
  }

  /* ---- J-T9a: the Premiere host theme around the docked panel (Addendum B2: the panel stays dark on Premiere's Dark
     AND Light themes; J-T9a and B-T6 review both). ?theme=dark|light draws Premiere's panel frame round the panel: the
     host's panel tab strip above it ("WhyNot Cut" + the panel menu) and the frame gap below it, in that theme's colours
     (approximate Spectrum values). It is mockup context only, never part of the product, always LTR, and exactly as wide
     as the panel, so the render crop and every self-check are unchanged. No theme param = the panel alone, as before. ---- */
  M.theme = q.get("theme") === "light" ? "light" : q.get("theme") === "dark" ? "dark" : "";
  function host(panel) {
    var box = document.createElement("div");
    box.className = "m-host m-host-" + M.theme + " m-host-w" + W;
    box.setAttribute("dir", "ltr");
    box.innerHTML = '<div class="m-host-tabs" aria-hidden="true"><span class="m-host-tab">' + esc(S["product.name"]) + '</span>' +
      '<span class="m-spacer"></span><span class="m-host-menu"><span class="m-host-bar"></span><span class="m-host-bar"></span><span class="m-host-bar"></span></span></div>';
    box.appendChild(panel);
    box.insertAdjacentHTML("beforeend", '<div class="m-host-foot" aria-hidden="true"></div>');
    return box;
  }

  /* ---- mount: one screen, one state ---- */
  M.mount = function (screen) {
    var r = M.resolve(screen, q.get("state")); /* "<state>-live" = the same screen with the support and data pages live (H24) */
    var full = r.full, valid = r.valid, state = r.state;
    if (state === "long") for (var k in M.D.long) M.D[k] = M.D.long[k];
    var view = screen.build(state);
    if (state === "long") view.needs = M.D.needs;
    /* Addendum G (owner #9): the Needs-you badge is hidden while setup runs */
    if (view.setup) view.needs = 0;
    /* one count: the badge and the Edit tab show the same number (decision 9) */
    view.editCount = view.needs || 0;
    var root = document.documentElement;
    root.lang = LANG;
    root.dir = M.rtl ? "rtl" : "ltr";
    if (CAPTURE) root.className += " m-capture";
    document.title = screen.id + " " + full + " · " + LANG + " · " + W + (M.theme ? " · " + M.theme : "");

    var panel = document.createElement("div");
    panel.className = "m-panel m-w" + W + (M.rtl ? " m-rtl" : "");
    panel.setAttribute("dir", M.rtl ? "rtl" : "ltr");
    panel.innerHTML =
      header(view) +
      (view.tab ? tabs(view.tab, view.editCount) : "") +
      '<main class="m-scroll m-gut" id="scroll">' + view.body + "</main>" +
      (view.bar ? '<div class="m-actionbar m-gut">' + view.bar + "</div>" : "") +
      /* Addendum G (owner #6, designer #15): no "Log · N lines" row in the shell any more; the log lives in
         Settings > Details for support. logRow() stays for a screen that draws it on purpose. */
      (view.log === true ? logRow(M.D.log) : "") + footer();
    document.body.innerHTML = "";
    document.body.appendChild(M.theme ? host(panel) : panel);
    stalePass(panel);
    dismissPass(panel);
    if (!CAPTURE) document.body.appendChild(nav(screen, full));
    keys(panel);
    check(panel, full, valid);
  };

  /* Addendum G shortcuts (demo in the browser; UXP keydown capture is a lab item): Cmd/Ctrl+Enter runs the primary,
     Esc closes the first notice, Alt+1/2/3 switches tabs. No single-key shortcuts (Premiere owns them).
     A danger confirm is the exception (R2 P0-3): Return lands on the SAFE button, never on the danger. */
  function keys(panel) {
    document.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        var danger = panel.querySelector(".m-dialog, .pc-dialog, .ta-dialog"); /* R3 F-21: any confirm, not only danger */
        var p = danger ? danger.querySelector(".m-btn-secondary") : panel.querySelector(".m-btn-primary:not(.m-btn-disabled):not(.m-btn-destructive), .m-verb-primary:not(.m-verb-disabled)");
        if (p) { p.className += " m-btn-focus m-verb-focus"; p.focus && p.focus(); }
      } else if (e.key === "Escape") {
        var n = panel.querySelector(".m-notice .m-x");
        if (n) { var card = n.parentNode; card.parentNode.removeChild(card); }
      } else if (e.altKey && /^[123]$/.test(e.key)) {
        var tabsEl = panel.querySelectorAll(".m-tab");
        for (var i = 0; i < tabsEl.length; i++) tabsEl[i].className = "m-tab" + (i === Number(e.key) - 1 ? " m-tab-on" : "");
      }
    });
  }

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
    html += "</div><div style='margin:8px 0 0 0'>" + link("theme", "dark", "Dark", M.theme === "dark") + link("theme", "light", "Light", M.theme === "light");
    box.innerHTML = html + "</div>";
    document.body.style.flexDirection = "row";
    return box;
  }

  /* self-check for _build/render_all.py (read with --dump-dom): direction, mirroring, sideways overflow, copy, and the
     R2 / R3 rules (render_all.py and render_280.py fail on any of them):
     - statuslie: a green header pill ("All set", or a screen's own view.status of kind ok) over ANY body signal of SIG
       (confirm, error, warn card, paused bar, running work, warn chip or amber icon, open setup, a disabled main action,
       a restart notice) or a Needs-you badge. It reads the RENDERED header and body (after stalePass and any group
       after-mount patch), so it shares no blind spot with liveState's own decision (R3 designer F-01);
     - dangerkbd: a keycap on a danger or destructive button;
     - confirmkbd: a keycap on the confirm button of ANY confirm card (R3 F-21: the keycap goes on the safe button);
     - violet: more than one live violet-family fill (#5400FB, #4800D8 pressed, #6A1FFF hover, #390796 deep), outermost
       fills only, read from the computed style (R3 F-10: the P-19 deep tile was not counted);
     - stalerun: a restart notice whose button is live while work is running (R3 F-02: never "restart now" mid-build);
     - spinoff: a spinner while the header says the WhyNot Cut service is off or not responding (R3 F-07);
     - objtext: "[object Object]" in the panel's text (J-T9a: a markup value pasted into a string). */
  var VIOLET = { "rgb(84, 0, 251)": 1, "rgb(72, 0, 216)": 1, "rgb(106, 31, 255)": 1, "rgb(57, 7, 150)": 1 };
  M.selfCheckExtras = function (panel) {
    var roots = bodyRoots(panel);
    var c = signals(roots);
    var pills = panel.querySelectorAll(".m-hdr .m-pill");
    var okPill = pills.length === 1 && !!pills[0].querySelector(".ink-ok");
    var problem = c.confirm + c.err + c.warn + c.busy + c.soft + c.open + c.off + c.stale + (panel.querySelector(".m-badge") ? 1 : 0);
    var lie = okPill && problem ? 1 : 0;
    var dk = panel.querySelectorAll(".m-btn-danger .m-kbd, .m-btn-destructive .m-kbd, .m-btn-danger .i-kbd, .m-btn-destructive .i-kbd").length;
    var ck = panel.querySelectorAll(".m-dialog .m-btn-primary .m-kbd, .pc-dialog .m-btn-primary .m-kbd, .ta-dialog .m-btn-primary .m-kbd, " +
      ".m-dialog .m-btn-primary .i-kbd, .pc-dialog .m-btn-primary .i-kbd, .ta-dialog .m-btn-primary .i-kbd").length;
    var violet = 0, fills = [];
    var all = panel.querySelectorAll("*");
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (!VIOLET[getComputedStyle(el).backgroundColor]) continue;
      var nested = false;
      for (var j = 0; j < fills.length; j++) if (fills[j].contains(el)) { nested = true; break; }
      if (!nested) { fills.push(el); violet++; }
    }
    var stalerun = 0;
    roots.forEach(function (r) {
      if (!r) return;
      var st = staleNotices(r);
      if (!runningIn(r, st)) return;
      st.forEach(function (n) { if (n.querySelector(".m-btn-primary:not(.m-btn-disabled), .m-btn-secondary")) stalerun++; });
    });
    var spinoff = 0;
    if (panel.querySelector(".m-hdr .m-pill-stop")) roots.forEach(function (r) { if (r) spinoff += r.querySelectorAll(".m-spin").length; });
    /* J-T9a (editor R2 P1-1): a markup object pasted into a string shows as "[object Object]"; never on screen */
    var txt = panel.textContent || "";
    var objtext = (txt.match(/\[object Object\]/g) || []).length;
    return ["statuslie=" + lie, "dangerkbd=" + dk, "violet=" + violet, "confirmkbd=" + ck, "stalerun=" + stalerun, "spinoff=" + spinoff, "objtext=" + objtext];
  };
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
        "missing=" + missing.join(",")].concat(M.selfCheckExtras(panel)).join(";");
      document.head.appendChild(meta);
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { setTimeout(done, 50); });
    else setTimeout(done, 300);
  }
})();
