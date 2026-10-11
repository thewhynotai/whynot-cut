/*  whynot-cut — After Effects bridge entry (ExtendScript, ES3).
    The WhyNot Cut Bridge panel (CEP, running inside After Effects) evaluates this file from <engine home>/ae-scripts and
    calls NHAE.run(<data file>). Every action returns a JSON string with read-back evidence; the panel's Node side writes
    it to the queue, so this code never writes files (AE's scripting file-write preference is never needed).
*/
var NHAE = NHAE || {};

(function () {
    var here = File($.fileName).parent.fsName;
    var libs = ["nh_ae_lib.jsx", "nh_motion_lib.jsx"];
    for (var i = 0; i < libs.length; i++) {
        var f = new File(here + "/" + libs[i]);
        if (f.exists) { $.evalFile(f); }
    }
})();

/* ---- tiny JSON (ExtendScript has no JSON object) ---- */
NHAE.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-￿]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
NHAE.str = function (v) {
    if (v === null || v === undefined) { return 'null'; }
    var t = typeof v;
    if (t === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (t === 'boolean') { return v ? 'true' : 'false'; }
    if (t === 'string') { return NHAE.q(v); }
    if (v instanceof Array) { var a = []; for (var i = 0; i < v.length; i++) { a.push(NHAE.str(v[i])); } return '[' + a.join(',') + ']'; }
    if (t === 'object') {
        var o = [];
        for (var k in v) { if (v.hasOwnProperty(k) && typeof v[k] !== 'function') { o.push(NHAE.q(k) + ':' + NHAE.str(v[k])); } }
        return '{' + o.join(',') + '}';
    }
    return NHAE.q(String(v));
};
NHAE.read = function (p) {
    var f = new File(p); f.encoding = 'UTF-8'; f.open('r'); var t = f.read(); f.close();
    return eval('(' + t + ')');  // trusted: written by the pipeline itself (ASCII JSON)
};

NHAE.projectInfo = function () {
    var p = app.project, dirty = null;
    try { dirty = p.dirty; } catch (e) { dirty = null; }       // undocumented, present since AE 17.5
    return {project: p && p.file ? p.file.name : null, project_path: p && p.file ? p.file.fsName : null, dirty: dirty};
};

NHAE.fontInfo = function (ps) {
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

NHAE.actions = {};

NHAE.actions.ping = function (d) {
    var info = NHAE.projectInfo();
    info.ae_version = app.version;
    info.fonts_api = !!(app.fonts && app.fonts.getFontsByPostScriptName);
    return info;
};

NHAE.actions.fonts = function (d) {
    var names = d.postscript_names || [], fonts = {}, missing = [];
    for (var i = 0; i < names.length; i++) { fonts[names[i]] = NHAE.fontInfo(names[i]); }
    try {
        var ms = app.fonts.missingOrSubstitutedFonts || [];
        for (var k = 0; k < ms.length; k++) { missing.push(ms[k].postScriptName); }
    } catch (e) {}
    return {fonts: fonts, missing_or_substituted: missing};
};

NHAE.run = function (dataPath) {
    var d;
    try { d = NHAE.read(dataPath); } catch (e) { return NHAE.str({ok: false, error: 'bad data file: ' + e}); }
    var fn = NHAE.actions[d.action];
    if (!fn) { return NHAE.str({ok: false, error: 'unknown action ' + d.action}); }
    var out;
    app.beginSuppressDialogs();
    try {
        var res = fn(d);
        out = NHAE.str({ok: !(res && res.ok === false), action: d.action, result: res});
    } catch (err) {
        out = NHAE.str({ok: false, action: d.action, error: String(err), line: err.line});
    } finally {
        try { app.endSuppressDialogs(false); } catch (e2) {}
    }
    return out;
};
