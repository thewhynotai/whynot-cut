/*  whynot-cut - After Effects bridge entry (ExtendScript, ES3).
    The WhyNot Cut Bridge panel (CEP, running inside After Effects) evaluates this file from <engine home>/ae-scripts and
    calls WNCAE.run(<data file>). Every action returns a JSON string with read-back evidence; the panel's Node side writes
    it to the queue, so this code never writes files (AE's scripting file-write preference is never needed).
*/
var WNCAE = WNCAE || {};

/* The libraries are evaluated at TOP LEVEL: inside a function their globals (WNC, WNCM) would stay local to it
   (seen live in After Effects 26.5: the motion library's namespace was "undefined"). */
var WNCAE_HERE = File($.fileName).parent.fsName;
$.evalFile(new File(WNCAE_HERE + "/wnc_ae_lib.jsx"));
$.evalFile(new File(WNCAE_HERE + "/wnc_motion_lib.jsx"));

/* ---- tiny JSON (ExtendScript has no JSON object) ---- */
WNCAE.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-\uffff]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
WNCAE.str = function (v) {
    if (v === null || v === undefined) { return 'null'; }
    var t = typeof v;
    if (t === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (t === 'boolean') { return v ? 'true' : 'false'; }
    if (t === 'string') { return WNCAE.q(v); }
    if (v instanceof Array) { var a = []; for (var i = 0; i < v.length; i++) { a.push(WNCAE.str(v[i])); } return '[' + a.join(',') + ']'; }
    if (t === 'object') {
        var o = [];
        for (var k in v) { if (v.hasOwnProperty(k) && typeof v[k] !== 'function') { o.push(WNCAE.q(k) + ':' + WNCAE.str(v[k])); } }
        return '{' + o.join(',') + '}';
    }
    return WNCAE.q(String(v));
};
WNCAE.read = function (p) {
    var f = new File(p); f.encoding = 'UTF-8'; f.open('r'); var t = f.read(); f.close();
    return eval('(' + t + ')');  // trusted: written by the pipeline itself (ASCII JSON)
};

/* the open-project rule lives in wnc_motion_lib.jsx: the fallback script (no bridge) applies the same one */
WNCAE.projectInfo = function () { return WNCM.projectInfo(); };
WNCAE.mayDiscard = function (info) { return WNCM.mayDiscard(info); };

WNCAE.fontInfo = function (ps) {
    var out = {found: false, substitute: false, family: null, style: null};
    try {
        var arr = app.fonts.getFontsByPostScriptName(ps);
        if (arr && arr.length) {
            out.found = true;
            out.substitute = !!arr[0].isSubstitute;
            out.family = arr[0].familyName;
            out.style = arr[0].styleName;
        }
    } catch (e) { out.error = String(e); }
    return out;
};

WNCAE.actions = {};

WNCAE.actions.ping = function (d) {
    var info = WNCAE.projectInfo();
    info.ae_version = app.version;
    info.fonts_api = !!(app.fonts && app.fonts.getFontsByPostScriptName);
    info.libs_loaded = (typeof WNCM !== "undefined") && (typeof WNC !== "undefined");
    info.scripts_dir = WNCAE_HERE;
    return info;
};

WNCAE.actions.fonts = function (d) {
    var names = d.postscript_names || [], fonts = {}, missing = [];
    for (var i = 0; i < names.length; i++) { fonts[names[i]] = WNCAE.fontInfo(names[i]); }
    try {
        var ms = app.fonts.missingOrSubstitutedFonts || [];
        for (var k = 0; k < ms.length; k++) { missing.push(ms[k].postScriptName); }
    } catch (e) {}
    return {fonts: fonts, missing_or_substituted: missing};
};

WNCAE.run = function (dataPath) {
    var d;
    try { d = WNCAE.read(dataPath); } catch (e) { return WNCAE.str({ok: false, error: 'bad data file: ' + e}); }
    var fn = WNCAE.actions[d.action];
    if (!fn) { return WNCAE.str({ok: false, error: 'unknown action ' + d.action}); }
    var out;
    app.beginSuppressDialogs();
    try {
        var res = fn(d);
        out = WNCAE.str({ok: !(res && res.ok === false), action: d.action, result: res});
    } catch (err) {
        out = WNCAE.str({ok: false, action: d.action, error: String(err), line: err.line});
    } finally {
        try { app.endSuppressDialogs(false); } catch (e2) {}
    }
    return out;
};

/* Arabic capability probe (spec 4.6): comps laid end to end in PROBE_ALL for one aerender run */
WNCAE.actions.probe_text = function (d) {
    var job = d.job, info = WNCAE.projectInfo();
    if (!WNCAE.mayDiscard(info)) { return {ok: false, reason: "dirty", project: info.project}; }
    app.newProject();
    var fps = job.fps, n = job.frames, out = {ae_version: app.version, comps: [], om_templates: []};
    var all = app.project.items.addComp("PROBE_ALL", job.w, job.h, 1, n * job.comps.length / fps, fps);
    for (var i = 0; i < job.comps.length; i++) {
        var s = job.comps[i], r = {name: s.name, ok: true};
        var c = app.project.items.addComp(s.name, job.w, job.h, 1, n / fps, fps);
        try {
            c.layers.addSolid([0.08, 0.1, 0.12], "BG", job.w, job.h, 1);
            if (s.word_layers) {                     // the motion library's own word-layer reveal
                WNCM.caps = {}; WNCM.report = {warnings: []};
                WNCM.plan = {recipe_motion: {ease: "smooth"}, dir: -1, brand: {controls: []}, word_reveal_s: 0.18};
                var toks = [];
                for (var m = 0; m < s.cues.length; m++) { toks.push({cue_frame: s.cues[m]}); }
                var g = WNCM.wordLayers(c, {name: "wl", text: s.text, lines: [s.text], tokens: toks, font_ps: s.font,
                    size: s.size, color: [1, 1, 1], accent: [1, 0.15, 0.1], x: job.w / 2, y: job.h / 2, rtl: true,
                    emphasis: s.emphasis || [], anchor: "center", cue_hash: ""}, 0, false);
                var gt = WNCM.readText(g);
                r.composer = gt.composer; r.font_ps = gt.font_ps; r.requested_ps = s.font; r.substitute = gt.substitute;
                r.direction_textdocument = gt.direction; r.layers = c.numLayers;
            } else if (s.shapes) {
                var sh = WNCM.shapeLayer(c, "icon", s.shapes, {stroke: s.stroke, color: [1, 1, 1]});
                sh.layer.property("ADBE Transform Group").property("ADBE Position").setValue([job.w / 2, job.h / 2]);
                sh.layer.property("ADBE Transform Group").property("ADBE Scale").setValue([300, 300]);
                var te = sh.trim.property("ADBE Vector Trim End");
                te.setValueAtTime(0, 0);
                te.setValueAtTime(30 * c.frameDuration, 100);
                r.layers = c.numLayers;
            } else {
                var L = c.layers.addText(s.text);
                L.name = "text";
                var dr = WNCM.styleText(L, {text: s.text, font: s.font, size: s.size, rtl: true, justify: "center"});
                L.property("ADBE Transform Group").property("ADBE Position").setValue([job.w / 2, job.h / 2]);
                if (s.cues) {
                    var secs = [];
                    for (var k = 0; k < s.cues.length; k++) { secs.push(s.cues[k] * c.frameDuration); }
                    WNCM.revealWords(L, secs, 3, 0.18);
                }
                if (s.emphasis) { WNCM.emphasisWords(L, s.emphasis, [1, 0.15, 0.1]); }
                if (s.fill_expr || s.opacity_expr) {          // diagnostics: a raw expression selector, Based On Words
                    var dn = L.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
                    if (s.fill_expr) { dn.property("ADBE Text Animator Properties").addProperty("ADBE Text Fill Color").setValue([1, 0.15, 0.1]); }
                    else { dn.property("ADBE Text Animator Properties").addProperty("ADBE Text Opacity").setValue(0); }
                    var ds = dn.property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
                    try { ds.property("ADBE Text Range Type2").setValue(3); } catch (eB) { r.based_on_error = String(eB); }
                    ds.property("ADBE Text Expressible Amount").expression = s.fill_expr || s.opacity_expr;
                    try { r.based_on = ds.property("ADBE Text Range Type2").value; } catch (eC) {}
                }
                var rt = WNCM.readText(L);
                r.text = rt.text; r.composer = rt.composer; r.font_ps = rt.font_ps; r.requested_ps = s.font;
                r.substitute = rt.substitute; r.direction_textdocument = dr.direction_textdocument;
                r.direction_paragraph_range = dr.direction_paragraph_range;
                if (dr.paragraph_error) { r.paragraph_error = dr.paragraph_error; }
                r.rect = WNCM.compRect(L, (n - 1) * c.frameDuration);
            }
        } catch (e) { r.ok = false; r.error = String(e); r.line = e.line; }
        var lay = all.layers.add(c);
        lay.startTime = i * n * c.frameDuration;
        out.comps.push(r);
    }
    try {
        var rq = app.project.renderQueue.items.add(all);
        out.om_templates = rq.outputModule(1).templates;
        rq.remove();
    } catch (e2) { out.om_error = String(e2); }
    app.project.save(new File(job.aep_path));
    out.saved = job.aep_path;
    return out;
};

/* motion build (spec 4.7): never discards the editor's work - refuses when AE holds unsaved changes */
WNCAE.actions.build_motion = function (d) {
    var job = d.job, info = WNCAE.projectInfo();
    var target = new File(job.aep_path).fsName;
    if (!WNCAE.mayDiscard(info)) {
        return {ok: false, reason: (info.project_path === target ? "dirty_target" : "dirty"), project: info.project,
                project_path: info.project_path};
    }
    app.newProject();
    var rep = WNCM.build(job);
    rep.ok = rep.failed.length === 0;
    return rep;
};

/* read-back of the project AE just built (spec 4.8): what AE actually holds, to compare with the plan */
WNCAE.actions.readback = function (d) {
    var job = d.job, plan = job.plan, out = {scenes: [], missing_or_substituted: [], main: null}, main = null, i;
    for (i = 1; i <= app.project.numItems; i++) {
        var it = app.project.item(i);
        if (it instanceof CompItem && it.name === "MAIN_" + plan.reel_id) { main = it; }
    }
    if (!main) { return {ok: false, reason: "MAIN_" + plan.reel_id + " not found in the open project"}; }
    out.main = {name: main.name, layers: main.numLayers, duration_frames: Math.round(main.duration / main.frameDuration)};
    for (var s = 0; s < plan.scenes.length; s++) {
        var sc = plan.scenes[s], cname = sc.id + "_" + sc.type, comp = WNC.findComp(cname);
        if (!comp) { continue; }
        var rec = {id: sc.id, comp: cname, layers: [], in_frame: null, out_frame: null};
        var ml = main.layer(cname);
        if (ml) {
            rec.in_frame = Math.round(ml.inPoint / main.frameDuration);
            rec.out_frame = Math.round(ml.outPoint / main.frameDuration);
        }
        var t = (sc.hero_frame - sc.start_frame) * comp.frameDuration;
        for (var k = 1; k <= comp.numLayers; k++) {
            var ly = comp.layer(k);
            var r = {name: ly.name, kind: (ly instanceof TextLayer) ? "text" : ((ly instanceof ShapeLayer) ? "shape" : "other"),
                     "in": Math.round(ly.inPoint / comp.frameDuration), out: Math.round(ly.outPoint / comp.frameDuration),
                     comment: ly.comment};
            if (ly instanceof TextLayer) {
                var rt = WNCM.readText(ly);
                r.text = rt.text; r.font_ps = rt.font_ps; r.substitute = rt.substitute; r.composer = rt.composer;
                r.direction = rt.direction;
                try { r.direction_pr = WNCM.dirName(ly.property("ADBE Text Properties").property("ADBE Text Document").value.paragraphRange(0).direction); } catch (e1) {}
                try { r.rect = WNCM.compRect(ly, t); } catch (e2) { r.rect_error = String(e2); }
            }
            rec.layers.push(r);
        }
        out.scenes.push(rec);
    }
    try {
        var ms = app.fonts.missingOrSubstitutedFonts || [];
        for (i = 0; i < ms.length; i++) { out.missing_or_substituted.push(ms[i].postScriptName); }
    } catch (e3) {}
    return out;
};
var NHAE = WNCAE; // 3.0 only: the legacy 3.1.1 bridge evaluates NHAE.run(...) after this file (D18 alias; removed in 3.1)
