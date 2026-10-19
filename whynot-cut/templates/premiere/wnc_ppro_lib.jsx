/*  whynot-cut - Premiere Pro ExtendScript library (run inside Premiere via the WhyNot Cut Bridge panel).
    WNCPP.run(dataFilePath) reads a JSON job (ASCII-escaped) and dispatches on data.action.
    Every action returns a JSON string with read-back evidence (what Premiere actually reports),
    never just "ok".
*/
var WNCPP = WNCPP || {};
WNCPP.TICKS = 254016000000;

/* ---- tiny JSON (ExtendScript has no JSON object) ---- */
WNCPP.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-\uffff]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
WNCPP.str = function (v) {
    if (v === null || v === undefined) { return 'null'; }
    var t = typeof v;
    if (t === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (t === 'boolean') { return v ? 'true' : 'false'; }
    if (t === 'string') { return WNCPP.q(v); }
    if (v instanceof Array) { var a = []; for (var i = 0; i < v.length; i++) { a.push(WNCPP.str(v[i])); } return '[' + a.join(',') + ']'; }
    if (t === 'object') {
        var o = [];
        for (var k in v) { if (v.hasOwnProperty(k) && typeof v[k] !== 'function') { o.push(WNCPP.q(k) + ':' + WNCPP.str(v[k])); } }
        return '{' + o.join(',') + '}';
    }
    return WNCPP.q(String(v));
};
WNCPP.read = function (p) {
    var f = new File(p); f.encoding = 'UTF-8'; f.open('r'); var t = f.read(); f.close();
    return eval('(' + t + ')');  // trusted: written by the pipeline itself
};

WNCPP.findSeq = function (name) {
    for (var i = 0; i < app.project.sequences.numSequences; i++) {
        var s = app.project.sequences[i];
        if (s.name === name) { return s; }
    }
    return null;
};
WNCPP.findBin = function (parent, name) {
    for (var i = 0; i < parent.children.numItems; i++) {
        var c = parent.children[i];
        if (c.type === ProjectItemType.BIN && c.name === name) { return c; }
    }
    return null;
};
WNCPP.bin = function (name) {
    var b = WNCPP.findBin(app.project.rootItem, name);
    if (!b) { app.project.rootItem.createBin(name); b = WNCPP.findBin(app.project.rootItem, name); }
    return b;
};
WNCPP.findItemByPath = function (parent, path) {
    for (var i = 0; i < parent.children.numItems; i++) {
        var c = parent.children[i];
        if (c.type === ProjectItemType.BIN) { var r = WNCPP.findItemByPath(c, path); if (r) { return r; } }
        else { try { if (c.getMediaPath && c.getMediaPath() === path) { return c; } } catch (e) {} }
    }
    return null;
};

WNCPP.settingsDump = function (seq) {
    var s = seq.getSettings(), out = {};
    for (var k in s) {
        try {
            var v = s[k];
            if (v && typeof v === 'object' && v.seconds !== undefined) { out[k] = {seconds: v.seconds, ticks: v.ticks}; }
            else if (typeof v !== 'function') { out[k] = v; }
        } catch (e) { out[k] = 'ERR ' + e; }
    }
    return out;
};

WNCPP.tracksDump = function (seq) {
    var v = [], a = [];
    for (var i = 0; i < seq.videoTracks.numTracks; i++) { var t = seq.videoTracks[i]; v.push({i: i + 1, name: t.name, clips: t.clips.numItems}); }
    for (var j = 0; j < seq.audioTracks.numTracks; j++) { var u = seq.audioTracks[j]; a.push({i: j + 1, name: u.name, clips: u.clips.numItems}); }
    return {video: v, audio: a};
};

/* ---------------------------------------------------------------- actions */
WNCPP.actions = {};

WNCPP.actions.ping = function (d) {
    return {version: app.version, build: app.build, project: app.project ? app.project.path : null,
            projects_open: app.projects ? app.projects.numProjects : null};
};

WNCPP.actions.probe = function (d) {
    var r = {version: app.version, project: app.project.path, sequences: []};
    for (var i = 0; i < app.project.sequences.numSequences; i++) {
        var s = app.project.sequences[i];
        r.sequences.push({name: s.name, settings: WNCPP.settingsDump(s), tracks: WNCPP.tracksDump(s)});
    }
    r.caption_constants = {};
    try { r.caption_constants.SUBTITLE = Sequence.CAPTION_FORMAT_SUBTITLE; } catch (e) { r.caption_constants.err = String(e); }
    return r;
};

WNCPP.actions.new_project_import = function (d) {
    var ok = app.newProject(d.project_path);
    var r = {newProject: ok, project: app.project ? app.project.path : null};
    if (d.xml_path) {
        r.importXML = app.project.importFiles([d.xml_path], true, app.project.rootItem, false);
        var seq = WNCPP.findSeq(d.sequence_name);
        r.sequence_found = !!seq;
        if (seq) { r.settings = WNCPP.settingsDump(seq); r.tracks = WNCPP.tracksDump(seq); }
    }
    return r;
};

WNCPP.waitSeq = function (name, ms) {   // XML import can register the sequence a moment later
    for (var t = 0; t < (ms || 8000); t += 250) { var s = WNCPP.findSeq(name); if (s) { return s; } $.sleep(250); }
    return null;
};

WNCPP.actions.import_xml_count = function (d) {
    var ok = app.project.importFiles([d.xml_path], true, app.project.rootItem, false);
    var seq = WNCPP.waitSeq(d.sequence_name);
    return {imported: ok, found: !!seq, tracks: seq ? WNCPP.tracksDump(seq) : null};
};

WNCPP.actions.reference_export = function (d) {
    // Ask Premiere for its OWN FCP XML of a sequence made from the clip: ground truth for our generator.
    app.project.importFiles([d.media_path], true, app.project.rootItem, false);
    var item = WNCPP.findItemByPath(app.project.rootItem, d.media_path);
    if (!item) { return {error: "imported item not found"}; }
    var seq = app.project.createNewSequenceFromClips(d.sequence_name, [item], app.project.rootItem);
    var ok = seq.exportAsFinalCutProXML(d.out_xml, 1);
    return {exported: ok, tracks: WNCPP.tracksDump(seq), settings: WNCPP.settingsDump(seq)};
};

/* ---------------------------------------------------------------- full Premiere-only build */
WNCPP.comp = function (item, name) {
    for (var i = 0; i < item.components.numItems; i++) { var c = item.components[i]; if (c.displayName === name) { return c; } }
    return null;
};
/* Effects by match name: a display name can mean another effect in a newer Premiere (26.x: "Gaussian Blur" is the new
   AE.Impact_Blur_FX, the classic one is "Gaussian Blur (Legacy)"). Match names verified live: docs/adobe/uxp-parity.md. */
WNCPP.MATCH = {motion: "AE.ADBE Motion", opacity: "AE.ADBE Opacity", blur: "AE.ADBE Gaussian Blur 2",
               sharpen: "AE.ADBE Sharpen", noise: ["AE.ADBE_Noise_FX", "AE.ADBE Noise2"], crop: "AE.ADBE AECrop"};
WNCPP.FX_NAMES = {blur: ["Gaussian Blur (Legacy)", "Gaussian Blur"], sharpen: ["Sharpen"], noise: ["Noise"],
                  crop: ["Crop"]};      // the QE display names addEffect tries, in this order
WNCPP.isMatch = function (got, want) {
    if (want instanceof Array) { for (var i = 0; i < want.length; i++) { if (got === want[i]) { return true; } } return false; }
    return got === want;
};
WNCPP.compByMatch = function (item, match) {   // the LAST component with that match name (an added effect is appended)
    var found = null;
    for (var i = 0; i < item.components.numItems; i++) {
        var c = item.components[i], m = null;
        try { m = c.matchName; } catch (e) { m = null; }
        if (WNCPP.isMatch(m, match)) { found = c; }
    }
    return found;
};
WNCPP.prop = function (comp, name) {
    if (!comp) { return null; }
    for (var i = 0; i < comp.properties.numItems; i++) { var p = comp.properties[i]; if (p.displayName === name) { return p; } }
    return null;
};
// the parameter at `index` when its display name is blank: Premiere 26 shows the legacy Gaussian Blur's third parameter
// (Repeat Edge Pixels) with a blank name (docs/adobe/uxp-parity.md row E4), so it is found by index instead
WNCPP.blankPropAt = function (comp, index) {
    if (!comp || index >= comp.properties.numItems) { return null; }
    var p = comp.properties[index], n = "";
    try { n = String(p.displayName === undefined || p.displayName === null ? "" : p.displayName); } catch (e) { n = ""; }
    return n.replace(/\s+/g, "") === "" ? p : null;
};
WNCPP.keyframes = function (prop, base, pairs) {   // pairs: [[offsetSeconds, value], ...] relative to clip in-point
    if (!prop) { return false; }
    prop.setTimeVarying(true);
    for (var i = 0; i < pairs.length; i++) { var t = base + pairs[i][0]; prop.addKey(t); prop.setValueAtKey(t, pairs[i][1], true); }
    return true;
};
WNCPP.itemAt = function (track, startSec) {
    var best = null, bd = 1e9;
    for (var i = 0; i < track.clips.numItems; i++) {
        var c = track.clips[i], dd = Math.abs(c.start.seconds - startSec);
        if (dd < bd) { bd = dd; best = c; }
    }
    return bd < 0.05 ? best : null;
};
WNCPP.secTime = function (sec) { var t = new Time(); t.seconds = sec; return t; };

WNCPP.seqWidth = function (seq) {   // the sequence's frame width in pixels (pixel offsets scale with it)
    var w = 0;
    try { w = Number(seq.frameSizeHorizontal) || 0; } catch (e) { w = 0; }
    if (!(w > 0)) { try { w = Number(seq.getSettings().videoFrameWidth) || 0; } catch (e2) { w = 0; } }
    return w > 0 ? w : 1080;
};
WNCPP.frameSeconds = function (seq) {   // one frame of the sequence in seconds (the animation timings count frames)
    var s = 0;
    try { var r = seq.getSettings().videoFrameRate; s = Number(r && r.seconds) || 0; } catch (e) { s = 0; }
    return (s > 0 && s <= 1) ? s : 1 / 24;
};

WNCPP.F = 1 / 24;   // a default only: build_project sets it from the sequence (WNCPP.frameSeconds)
WNCPP.placeStill = function (seq, trackIdx, projItem, g, log) {
    var track = seq.videoTracks[trackIdx];
    track.overwriteClip(projItem, g.start_s);
    var it = WNCPP.itemAt(track, g.start_s);
    if (!it) { log.push("placement not found: " + g.id); return null; }
    it.end = WNCPP.secTime(g.end_s);
    var base = it.inPoint.seconds, dur = g.end_s - g.start_s, F = WNCPP.F;
    var motion = WNCPP.compByMatch(it, WNCPP.MATCH.motion) || WNCPP.comp(it, "Motion");
    var op = WNCPP.prop(WNCPP.compByMatch(it, WNCPP.MATCH.opacity) || WNCPP.comp(it, "Opacity"), "Opacity");
    var fo = Math.min(g.fade_out_s || 0, dur / 3);
    var outKeys = fo > 0 ? [[dur - fo, 100], [dur, 0]] : [];
    var a = g.anim;
    if (a === "flash") {
        WNCPP.keyframes(op, base, [[0, 0], [dur / 2, g.peak || 90], [dur, 0]]);
    } else if (a === "text_pop") {            // reference: text pops in fast
        WNCPP.keyframes(op, base, [[0, 0], [2 * F, 100]].concat(outKeys));
        WNCPP.keyframes(WNCPP.prop(motion, "Scale"), base, [[0, 90], [4 * F, 100]]);
    } else if (a === "bar_sweep") {           // reference: teal bar sweeps in right-to-left (RTL)
        var d0 = (g.delay_f || 1) * F, sw = (g.sweep_f || 6) * F;
        WNCPP.keyframes(WNCPP.prop(motion, "Crop Left"), base, [[0, 100], [d0, 100], [d0 + sw, 0]]);
        if (outKeys.length) { WNCPP.keyframes(op, base, [[0, 100]].concat(outKeys)); }
    } else if (a === "slide") {               // checklist item slides in from the right, 60 sequence pixels
        var pos = WNCPP.prop(motion, "Position"), v = pos.getValue();
        var dx = (v[0] <= 2) ? 60 / WNCPP.seqWidth(seq) : 60;   // normalised or pixel coordinates, whichever this build uses
        WNCPP.keyframes(pos, base, [[0, [v[0] + dx, v[1]]], [5 * F, [v[0], v[1]]]]);
        WNCPP.keyframes(op, base, [[0, 0], [4 * F, 100]].concat(outKeys));
    } else if (a === "push") {                // full-screen card: fade + slow push
        WNCPP.keyframes(op, base, [[0, 0], [6 * F, 100]].concat(outKeys));
        WNCPP.keyframes(WNCPP.prop(motion, "Scale"), base, [[0, 100], [dur, 103]]);
    } else if (a === "card") {                // closing glass card
        var fi = Math.min(g.fade_in_s || 10 * F, dur / 3);
        WNCPP.keyframes(op, base, [[0, 0], [fi, 100]].concat(outKeys));
        WNCPP.keyframes(WNCPP.prop(motion, "Scale"), base, [[0, 96], [fi, 100]]);
    } else {
        WNCPP.keyframes(op, base, [[0, 0], [5 * F, 100]].concat(outKeys));
    }
    return {id: g.id, track: trackIdx + 1, start: it.start.seconds, end: it.end.seconds, anim: a};
};

/* 3.0 T4.1 smooth zoom: a punch-in eases in and out with bezier keys on Motion Scale and Position of its V1 clips.
   The job's camera_keys are the timeline spec's runs (lib/camera_ease.py); each side carries segment values
   (scale_factor, offset_x/y in sequence pixels), applied RELATIVE to the clip's own Motion values from the XML, so
   normalised and pixel Position coordinates both work. Keys already on the property are dropped first (a re-run adds
   none twice). Each clip's own Scale / Position are read ONCE, before any key is written on it (getValue is not
   reliable on a time-varying parameter), and kept in `orig` for every run of the build. ExtendScript has no
   interpolation getter: the read-back says "bezier (set, not read back)", never verified (Gate 4 live check). */
WNCPP.KF_BEZIER = 5;                    // kfInterpMode_Bezier (0 linear, 4 hold, 5 bezier, 6 time)
WNCPP.seqHeight = function (seq) {
    var h = 0;
    try { h = Number(seq.frameSizeVertical) || 0; } catch (e) { h = 0; }
    if (!(h > 0)) { try { h = Number(seq.getSettings().videoFrameHeight) || 0; } catch (e2) { h = 0; } }
    return h > 0 ? h : 1920;
};
WNCPP.keyCount = function (prop) {
    if (!prop) { return 0; }
    var k = null;
    try { k = prop.getKeys(); } catch (e) { k = null; }
    return k ? (k.length || 0) : 0;
};
WNCPP.bezierKey = function (prop, t, value) {     // one key; true when its interpolation was set to bezier
    prop.addKey(t);
    prop.setValueAtKey(t, value, true);
    if (typeof prop.setInterpolationTypeAtKey !== "function") { return false; }
    try { prop.setInterpolationTypeAtKey(t, WNCPP.KF_BEZIER, true); return true; } catch (e) { return false; }
};
WNCPP.EASE_SET = "bezier (set, not read back)";
WNCPP.restoreClip = function (clip, o) {   // review 2 M-d: a clip whose keys failed goes back to its imported values
    var motion = WNCPP.compByMatch(clip, WNCPP.MATCH.motion) || WNCPP.comp(clip, "Motion");
    var sc = WNCPP.prop(motion, "Scale"), pos = WNCPP.prop(motion, "Position");
    try { if (sc) { sc.setTimeVarying(false); sc.setValue(o.S, true); } } catch (e1) {}
    try { if (pos) { pos.setTimeVarying(false); pos.setValue([o.P[0], o.P[1]], true); } } catch (e2) {}
};
// round 5 MIN-3: any throw in a move (the V1 lookup, a side, the key-count read-back) rolls back every clip it touched
WNCPP.easeRun = function (seq, r, orig, log) {
    var touched = [];
    try { return WNCPP.easeRunInner(seq, r, orig, log, touched); }
    catch (ex) {
        var v1r = null;
        try { v1r = seq.videoTracks[0]; } catch (ev) { v1r = null; }
        for (var k = 0; v1r && k < touched.length; k++) {
            if (orig[touched[k]]) { WNCPP.restoreClip(v1r.clips[touched[k]], orig[touched[k]]); }
        }
        log.push("smooth zoom " + r.decision_id + ": clips " + touched.join(", ") + " restored after an error: " + ex);
        return {decision_id: r.decision_id, pieces: r.pieces, scale_keys: 0, position_keys: 0, interpolation: "none",
                interpolation_verified: false, ok: false, error: "clips " + touched.join(", ") + " restored: " + ex};
    }
};
WNCPP.easeRunInner = function (seq, r, orig, log, touched) {
    var v1 = seq.videoTracks[0], W = WNCPP.seqWidth(seq), H = WNCPP.seqHeight(seq), F = WNCPP.F;
    var out = {decision_id: r.decision_id, pieces: r.pieces, scale_keys: 0, position_keys: 0,
               interpolation: WNCPP.EASE_SET, interpolation_verified: false, ok: true};
    var sides = [], want = 0, interpOk = true, clips = touched, i, c;
    if (r.ease_in) { sides.push({e: r.ease_in, other: r.ease_in.from, atStart: true}); }
    if (r.ease_out) { sides.push({e: r.ease_out, other: r.ease_out.to, atStart: false}); }
    for (i = 0; i < sides.length; i++) {
        var sd = sides[i], pi = sd.e.piece, clip = (pi >= 0 && pi < v1.clips.numItems) ? v1.clips[pi] : null;
        want += 2;
        if (!clip) { log.push("smooth zoom " + r.decision_id + ": no V1 clip " + pi); out.ok = false; continue; }
        try {                           // round 4 M-3: every host call of this side, the reads included, is guarded
            var motion = WNCPP.compByMatch(clip, WNCPP.MATCH.motion) || WNCPP.comp(clip, "Motion");
            var sc = WNCPP.prop(motion, "Scale"), pos = WNCPP.prop(motion, "Position");
            if (!sc || !pos) { log.push("smooth zoom " + r.decision_id + ": Motion Scale/Position not found"); out.ok = false; continue; }
            if (!orig[pi]) {            // first touch of this clip: its values as imported, then stale keys go
                var P0 = pos.getValue();
                orig[pi] = {S: Number(sc.getValue()), P: [Number(P0[0]), Number(P0[1])]};
                try { sc.setTimeVarying(false); pos.setTimeVarying(false); } catch (ec) { log.push("smooth zoom clear: " + ec); }
            }
            var seen = false;
            for (c = 0; c < clips.length; c++) { if (clips[c] === pi) { seen = true; } }
            if (!seen) { clips.push(pi); }
            var S = orig[pi].S, P = orig[pi].P, norm = (P[0] <= 2 && P[1] <= 2);
            var k = sd.e.value.scale_factor ? sd.other.scale_factor / sd.e.value.scale_factor : 1;
            var dx = (sd.other.offset_x || 0) - (sd.e.value.offset_x || 0), dy = (sd.other.offset_y || 0) - (sd.e.value.offset_y || 0);
            if (norm) { dx = dx / W; dy = dy / H; }
            var base = clip.inPoint.seconds, dur = clip.end.seconds - clip.start.seconds, n = sd.e.frames * F;
            var tOther = sd.atStart ? base : base + dur, tSelf = sd.atStart ? base + n : base + dur - n;
            sc.setTimeVarying(true);
            pos.setTimeVarying(true);
            interpOk = WNCPP.bezierKey(sc, tOther, S * k) && interpOk;
            interpOk = WNCPP.bezierKey(sc, tSelf, S) && interpOk;
            interpOk = WNCPP.bezierKey(pos, tOther, [P[0] + dx, P[1] + dy]) && interpOk;
            interpOk = WNCPP.bezierKey(pos, tSelf, [P[0], P[1]]) && interpOk;
        } catch (ek) {
            // review 2 M-d: never leave a half-keyed clip: every clip of this move goes back to its imported values
            for (c = 0; c < clips.length; c++) { if (orig[clips[c]]) { WNCPP.restoreClip(v1.clips[clips[c]], orig[clips[c]]); } }
            log.push("smooth zoom " + r.decision_id + ": clip " + pi + " restored after an error: " + ek);
            out.error = "clip " + pi + ": " + ek;
            out.ok = false;
            break;
        }
    }
    for (c = 0; c < clips.length; c++) {
        var m2 = WNCPP.compByMatch(v1.clips[clips[c]], WNCPP.MATCH.motion) || WNCPP.comp(v1.clips[clips[c]], "Motion");
        out.scale_keys += WNCPP.keyCount(WNCPP.prop(m2, "Scale"));
        out.position_keys += WNCPP.keyCount(WNCPP.prop(m2, "Position"));
    }
    if (!interpOk) { out.interpolation = "linear (fallback)"; out.ok = false; }
    if (out.scale_keys !== want || out.position_keys !== want) { out.ok = false; }
    return out;
};
/* 3.0 T4.1 fades. Picture (review 2 IMP-2): ONE black matte still on its own top track (job fades.matte: the engine's
   frame-size PNG and the empty lane the base XML made for it) over each fade window, Opacity 100 -> 0 at the start
   and 0 -> 100 at the end, so the whole picture fades as one (per-layer opacity would ghost where layers overlap).
   No track: reported, never a per-layer fallback. Sound: Volume Level keys on the audio items of the job's
   `audio_tracks` (dialogue, music, the muted originals; never the SFX); a key already inside the window (the music
   bed's fade-out) is multiplied by the fade, never overwritten. fd times in sequence seconds, end_s = the end. */
WNCPP.fadeGain = function (t, fd, kind) {
    var fin = fd[kind + "_in_s"] || 0, fout = fd[kind + "_out_s"] || 0, g = 1;
    if (fin > 0 && t < fin) { g = Math.min(g, Math.max(0, t / fin)); }
    if (fout > 0 && t > fd.end_s - fout) { g = Math.min(g, Math.max(0, (fd.end_s - t) / fout)); }
    return g;
};
WNCPP.fadeItem = function (prop, item, fd, kind) {   // keys written (0 = the item is outside both windows)
    var s = item.start.seconds, e = item.end.seconds, base = item.inPoint.seconds, eps = 1e-6;
    var fin = fd[kind + "_in_s"] || 0, fout = fd[kind + "_out_s"] || 0, wins = [], pts = [], vals = [], i, j;
    if (fin > 0 && s < fin - eps) { wins.push([Math.max(s, 0), Math.min(e, fin)]); }
    if (fout > 0 && e > fd.end_s - fout + eps) { wins.push([Math.max(s, fd.end_s - fout), Math.min(e, fd.end_s)]); }
    if (!wins.length || !prop) { return 0; }
    var old = null;
    try { old = prop.getKeys(); } catch (ek) { old = null; }
    for (i = 0; i < wins.length; i++) {
        pts.push(wins[i][0]);
        pts.push(wins[i][1]);
        for (j = 0; old && j < old.length; j++) {
            var ta = (typeof old[j] === "object" ? old[j].seconds : Number(old[j])) - base + s;
            if (ta > wins[i][0] + eps && ta < wins[i][1] - eps) { pts.push(ta); }
        }
    }
    var varying = false;
    try { varying = !!(old && old.length); } catch (evy) { varying = false; }
    for (i = 0; i < pts.length; i++) {   // read the curve as it is BEFORE any key is written
        var v;
        try { v = varying ? prop.getValueAtTime(base + (pts[i] - s)) : prop.getValue(); } catch (ev) { v = prop.getValue(); }
        vals.push(Number(v));
    }
    prop.setTimeVarying(true);
    for (i = 0; i < pts.length; i++) {
        var t2 = base + (pts[i] - s);
        prop.addKey(t2);
        prop.setValueAtKey(t2, vals[i] * WNCPP.fadeGain(pts[i], fd, kind), true);
    }
    return pts.length;
};
/* Volume > Level of an audio clip: by display name, else by match name ("Internal Volume ..." in Premiere's audio
   effects list: NOT measured live, Gate 4) with the level as the second parameter (after Bypass). Round 4 M-5. */
WNCPP.VOLUME_MATCH = ["Internal Volume Stereo", "Internal Volume Mono", "Internal Volume 5.1", "Internal Volume"];
WNCPP.levelParam = function (it) {
    var comp = WNCPP.comp(it, "Volume"), p = comp ? WNCPP.prop(comp, "Level") : null;
    if (p) { return p; }
    comp = comp || WNCPP.compByMatch(it, WNCPP.VOLUME_MATCH);
    if (!comp) { return null; }
    p = WNCPP.prop(comp, "Level");
    if (!p && comp.properties.numItems > 1) { p = comp.properties[1]; }
    return p;
};
WNCPP.placeMatte = function (seq, track, item, s, e, pairs, log) {   // one matte clip, or null (nothing left behind)
    track.overwriteClip(item, s);
    var it = WNCPP.itemAt(track, s);
    if (!it) { log.push("fade to black: the matte at " + s + " s was not placed"); return null; }
    try {
        it.end = WNCPP.secTime(e);
        var op = WNCPP.prop(WNCPP.compByMatch(it, WNCPP.MATCH.opacity) || WNCPP.comp(it, "Opacity"), "Opacity");
        if (!op) { throw new Error("no Opacity on the matte"); }
        WNCPP.keyframes(op, it.inPoint.seconds, pairs);
        return {start: it.start.seconds, end: it.end.seconds, keys: WNCPP.keyCount(op)};
    } catch (em) {
        // review 2 M-d: a half-placed matte is removed, and the fade reported as not applied
        try { it.remove(false, false); } catch (er) { log.push("fade to black: the matte at " + s + " s could not be removed: " + er); }
        log.push("fade to black: matte at " + s + " s removed after an error: " + em);
        return null;
    }
};
WNCPP.applyFades = function (seq, fd, log) {
    var res = {matte: [], audio: [], ok: true}, t, c, it, n, i;
    var fin = fd.video_in_s || 0, fout = fd.video_out_s || 0;
    var aOn = (fd.audio_in_s || 0) > 0 || (fd.audio_out_s || 0) > 0;
    if (fin > 0 || fout > 0) {
        var m = fd.matte || {}, ti = m.track_index, track = (ti >= 0 && ti < seq.videoTracks.numTracks) ? seq.videoTracks[ti] : null;
        if (!track || !m.png) {
            log.push("fade to black: no free top track for the black matte (track " + ti + "): the picture is not faded");
            res.ok = false;
        } else {
            var bin = WNCPP.bin("02 Graphics");
            app.project.importFiles([m.png], true, bin, false);
            var pi = WNCPP.findItemByPath(bin, m.png);
            if (!pi) { log.push("fade to black: the black matte still was not imported: " + m.png); res.ok = false; }
            var wins = [];
            if (fin > 0) { wins.push([0, fin, [[0, 100], [fin, 0]]]); }
            if (fout > 0) { wins.push([fd.end_s - fout, fd.end_s, [[0, 0], [fout, 100]]]); }
            for (i = 0; pi && i < wins.length; i++) {
                var r = WNCPP.placeMatte(seq, track, pi, wins[i][0], wins[i][1], wins[i][2], log);
                if (r) { res.matte.push(r); } else { res.ok = false; }
            }
        }
    }
    var named = {};                     // round 4 M-9: only the named tracks; none named = no audio faded (never an SFX)
    for (i = 0; fd.audio_tracks && i < fd.audio_tracks.length; i++) { named[fd.audio_tracks[i]] = true; }
    for (t = 0; aOn && t < seq.audioTracks.numTracks; t++) {
        if (!named[t + 1]) { continue; }
        for (c = 0; c < seq.audioTracks[t].clips.numItems; c++) {
            it = seq.audioTracks[t].clips[c];
            var lv = WNCPP.levelParam(it);
            n = 0;
            try { n = WNCPP.fadeItem(lv, it, fd, "audio"); }
            catch (e2) { log.push("sound fade A" + (t + 1) + " clip " + c + ": " + e2); res.ok = false; }
            if (n > 0) { res.audio.push({track: t + 1, clip: c, keys: n}); }
            else if (!lv) { log.push("sound fade: no Volume Level on A" + (t + 1) + " clip " + c); }
        }
    }
    if (aOn && !res.audio.length) { res.ok = false; }
    return res;
};

WNCPP.actions.build_project = function (d) {
    var log = [], ev = {};
    // 1. project
    if (d.overwrite_existing !== true && new File(d.project_path).exists) { return {error: "project exists (set overwrite_existing)"}; }
    ev.newProject = app.newProject(d.project_path);
    ev.project = app.project.path;
    var root = app.project.rootItem;
    var bins = {};
    var names = ["00 Sequences", "01 Footage", "02 Graphics", "03 Sound FX", "04 Captions"];
    for (var b = 0; b < names.length; b++) { bins[names[b]] = WNCPP.bin(names[b]); }
    // 2. base sequence from XML (footage, punch-ins, dialogue, SFX, empty graphic tracks)
    ev.importXML = app.project.importFiles([d.xml_path], true, root, false);
    var seq = WNCPP.waitSeq(d.sequence_name, 15000);
    if (!seq) { return {error: "sequence not found after XML import", log: log}; }
    app.project.openSequence(seq.sequenceID);
    // 3. sequence settings (what XML can't carry) -> set, then READ BACK
    var st = seq.getSettings();
    for (var k in d.settings) { if (d.settings.hasOwnProperty(k)) { try { st[k] = d.settings[k]; } catch (e1) { log.push("setting " + k + ": " + e1); } } }
    ev.setSettings = seq.setSettings(st);
    ev.settings_after = WNCPP.settingsDump(seq);
    WNCPP.F = WNCPP.frameSeconds(seq);   // the keyframe timings count frames of THIS sequence
    ev.frame_s = WNCPP.F;
    ev.effects = [];                     // every effect added, with the match name Premiere really applied
    // 4. graphics: import stills, place with Premiere keyframes
    var gpaths = [];
    for (var i = 0; i < d.graphics.length; i++) { gpaths.push(d.graphics[i].png); }
    ev.importGraphics = app.project.importFiles(gpaths, true, bins["02 Graphics"], false);
    ev.placed = [];
    for (var j = 0; j < d.graphics.length; j++) {
        var g = d.graphics[j];
        var pi = WNCPP.findItemByPath(bins["02 Graphics"], g.png);
        if (!pi) { log.push("graphic not imported: " + g.png); continue; }
        var r = WNCPP.placeStill(seq, g.track_index, pi, g, log);
        if (r) { ev.placed.push(r); }
    }
    // 4b. source cutaways: blur the cover copy on V1 under each whole card (fit + blurred fill)
    ev.blurred = [];
    for (var bi = 0; d.blur_v1_clips && bi < d.blur_v1_clips.length; bi++) {
        var ci = d.blur_v1_clips[bi];
        try {
            if (WNCPP.addEffect(seq, 0, ci, "blur", ev.effects).ok) {
                var bc = WNCPP.compByMatch(seq.videoTracks[0].clips[ci], WNCPP.MATCH.blur);
                var pb = WNCPP.prop(bc, "Blurriness"), pe = WNCPP.prop(bc, "Repeat Edge Pixels"), edgeBy = "name";
                if (!pe) { pe = WNCPP.blankPropAt(bc, 2); edgeBy = pe ? "index" : null; }   // Premiere 26: blank name
                if (pb) { pb.setValue(90, true); }
                if (pe) { pe.setValue(true, true); } else { log.push("Gaussian Blur (Legacy): Repeat Edge Pixels not found"); }
                ev.blurred.push({clip: ci, blurriness: pb ? pb.getValue() : null, edge: pe ? pe.getValue() : null,
                                 edge_by: edgeBy});
            } else { log.push("Gaussian Blur (Legacy) effect not found"); }
        } catch (eb) { log.push("blur clip " + ci + ": " + eb); }
    }
    // 4c. strong reframe upscale: light Sharpen (+ optional Noise as grain) on the speaker clips of V1, not on the
    //     blurred cover copies under source cutaways (client plan: a x1.78 crop looks soft)
    ev.sharpened = [];
    if (d.sharpen_v1 && d.sharpen_v1.amount) {
        var v1 = seq.videoTracks[0];
        for (var si = 0; si < v1.clips.numItems; si++) {
            var isBlur = false;
            for (var bj = 0; d.blur_v1_clips && bj < d.blur_v1_clips.length; bj++) { if (d.blur_v1_clips[bj] === si) { isBlur = true; } }
            if (isBlur) { continue; }
            try {
                var rec = {clip: si, ok: false};
                if (WNCPP.addEffect(seq, 0, si, "sharpen", ev.effects).ok) {
                    var sa = WNCPP.prop(WNCPP.compByMatch(v1.clips[si], WNCPP.MATCH.sharpen), "Sharpen Amount");
                    if (sa) { sa.setValue(d.sharpen_v1.amount, true); rec.ok = true; rec.amount = d.sharpen_v1.amount; }
                    else { log.push("Sharpen Amount property not found"); }
                } else { log.push("Sharpen effect not found"); ev.sharpened.push(rec); break; }
                if (d.sharpen_v1.grain && WNCPP.addEffect(seq, 0, si, "noise", ev.effects).ok) {
                    // Premiere 26 resolves "Noise" to its grain effect (ADBE_Noise_FX: Intensity, default 50 = heavy);
                    // older versions to the classic Noise ("Amount of Noise" %). Set whichever exists.
                    var nc = WNCPP.compByMatch(v1.clips[si], WNCPP.MATCH.noise);
                    var na = WNCPP.prop(nc, "Intensity") || WNCPP.prop(nc, "Amount of Noise");
                    if (na) { na.setValue(d.sharpen_v1.grain, true); rec.grain = na.getValue(); }
                    else { log.push("Noise: no Intensity / Amount of Noise property"); rec.ok = false; }
                }
                ev.sharpened.push(rec);
            } catch (es) { log.push("sharpen clip " + si + ": " + es); }
        }
    }
    // 4d. T4.1 smooth zoom: eased keys on the punch-ins' V1 clips (job camera_keys), read back per punch-in
    var orig = {};
    if (d.camera_keys && d.camera_keys.length) { ev.eased = []; }    // review 2 M-f: nothing asked, nothing reported
    for (var ri = 0; d.camera_keys && ri < d.camera_keys.length; ri++) {
        var run = d.camera_keys[ri];
        try { ev.eased.push(WNCPP.easeRun(seq, run, orig, log)); }
        catch (ee) {
            log.push("smooth zoom " + run.decision_id + ": " + ee);
            ev.eased.push({decision_id: run.decision_id, pieces: run.pieces, scale_keys: 0, position_keys: 0,
                           interpolation: "none", interpolation_verified: false, ok: false});
        }
    }
    // 4e. T4.1 fades of picture (one black matte on the top track) and sound (the named tracks) at the start / end
    if (d.fades) {
        try { ev.faded = WNCPP.applyFades(seq, d.fades, log); }
        catch (ef) { log.push("fades: " + ef); ev.faded = {matte: [], audio: [], ok: false}; }   // the schema's shape
    }
    // 5. native captions from SRT
    if (d.srt_path && d.native_caption_track) {
        app.project.importFiles([d.srt_path], true, bins["04 Captions"], false);
        var cap = WNCPP.findItemByPath(bins["04 Captions"], d.srt_path);
        try { ev.captionTrack = seq.createCaptionTrack(cap, 0, Sequence.CAPTION_FORMAT_SUBTITLE); }
        catch (e2) { log.push("caption track: " + e2); ev.captionTrack = false; }
    }
    // 6. track names (if this Premiere build allows renaming via script)
    ev.renamed = [];
    for (var t = 0; t < d.track_names.video.length && t < seq.videoTracks.numTracks; t++) {
        try { seq.videoTracks[t].name = d.track_names.video[t]; } catch (e3) {}
        ev.renamed.push(seq.videoTracks[t].name);
    }
    for (var a = 0; a < d.track_names.audio.length && a < seq.audioTracks.numTracks; a++) {
        try { seq.audioTracks[a].name = d.track_names.audio[a]; } catch (e4) {}
    }
    // 7. tidy bins: move imported footage / sfx out of the root
    for (var n = root.children.numItems - 1; n >= 0; n--) {
        var c = root.children[n];
        if (c.type === ProjectItemType.BIN) { continue; }
        try {
            if (c.isSequence && c.isSequence()) { c.moveBin(bins["00 Sequences"]); continue; }
            var mp = c.getMediaPath ? c.getMediaPath() : "";
            if (/\.wav$/i.test(mp)) { c.moveBin(bins["03 Sound FX"]); }
            else if (/\.(mp4|mov|mxf)$/i.test(mp)) { c.moveBin(bins["01 Footage"]); }
        } catch (e5) {}
    }
    // 8. markers for every decision (evidence), save
    for (var m = 0; m < d.markers.length; m++) {
        try { var mk = seq.markers.createMarker(d.markers[m].t); mk.name = d.markers[m].name; mk.comments = d.markers[m].comment; } catch (e6) {}
    }
    ev.saved = app.project.save();
    ev.tracks = WNCPP.tracksDump(seq);
    ev.log = log;
    return ev;
};

WNCPP.outPath = function (dir, name) {
    // QE exportFramePNG on Windows accepts ONLY native backslash paths ("D:\x\frame"); any "/" throws
    // "Unknown error exception" (probed on Premiere 26.5.2). fsName gives the native form on both systems.
    var win = $.os.indexOf("Windows") >= 0;
    return new Folder(dir).fsName + (win ? "\\" : "/") + name;
};

WNCPP.actions.clip_components = function (d) {
    // read-only: the effects on one clip and their property names/values (find Premiere's real names per version)
    var seq = WNCPP.findSeq(d.sequence_name);
    var tr = d.audio ? seq.audioTracks[d.track || 0] : seq.videoTracks[d.track || 0];
    var clip = tr.clips[d.clip || 0], comps = [];
    for (var i = 0; i < clip.components.numItems; i++) {
        var c = clip.components[i], props = [];
        for (var j = 0; j < c.properties.numItems; j++) {
            var p = c.properties[j], v = null;
            try { v = p.getValue(); if (v && typeof v === "object") { v = String(v); } } catch (e) { v = "?"; }
            props.push({name: p.displayName, value: v});
        }
        comps.push({name: c.displayName, match: c.matchName, props: props});
    }
    return {clip: clip.name, components: comps};
};

WNCPP.activateProject = function (path) {
    // several projects can be open (one per reel): make the one at `path` the active project (opening it if needed)
    var want = String(path).replace(/\//g, "\\").toLowerCase();
    if (app.project && String(app.project.path).replace(/\//g, "\\").toLowerCase() === want) { return true; }
    for (var i = 0; i < app.projects.numProjects; i++) {
        var pp = String(app.projects[i].path);
        if (pp.replace(/\//g, "\\").toLowerCase() === want) { return app.openDocument(pp); }
    }
    return app.openDocument(String(path));
};

WNCPP.actions.export_frames = function (d) {
    // Premiere renders frames of ITS OWN timeline -> visual evidence of the real result
    if (d.project_path) { WNCPP.activateProject(d.project_path); }
    app.enableQE();
    var seq = WNCPP.findSeq(d.sequence_name);
    if (!seq) {
        throw new Error("sequence " + d.sequence_name + " not found in the active project " +
                        (app.project ? app.project.path : "(none)"));
    }
    app.project.openSequence(seq.sequenceID);
    var qs = qe.project.getActiveSequence();
    var out = [];
    for (var i = 0; i < d.times.length; i++) {
        var ticks = String(Math.round(d.times[i] * WNCPP.TICKS));
        seq.setPlayerPosition(ticks);
        var f = WNCPP.outPath(d.out_dir, "frame_" + ("000000" + Math.round(d.times[i] * 1000)).slice(-6));
        var ok = false;
        // exportFramePNG needs the CTI TIMECODE string; given ticks it silently exports frame 0 (verified 26.5)
        var tc = qs.CTI.timecode;
        try { qs.exportFramePNG(tc, f); ok = true; } catch (e) { out.push({t: d.times[i], error: String(e)}); continue; }
        out.push({t: d.times[i], tc: tc, file: f + ".png", called: ok});
    }
    return {frames: out};
};

WNCPP.actions.probe_frame_export = function (d) {
    app.enableQE();
    var seq = WNCPP.findSeq(d.sequence_name);
    app.project.openSequence(seq.sequenceID);
    var qs = qe.project.getActiveSequence();
    seq.setPlayerPosition(String(Math.round(d.t * WNCPP.TICKS)));
    var r = {player_pos_s: seq.getPlayerPosition().seconds, cti_tc: null, variants: []};
    try { r.cti_tc = qs.CTI.timecode; } catch (e) { r.cti_err = String(e); }
    var tries = [["cti_timecode", r.cti_tc], ["ticks", seq.getPlayerPosition().ticks], ["seconds_str", String(d.t)]];
    for (var i = 0; i < tries.length; i++) {
        var f = WNCPP.outPath(d.out_dir, "probe_" + tries[i][0]);
        try { qs.exportFramePNG(tries[i][1], f); r.variants.push({v: tries[i][0], arg: tries[i][1], ok: true, file: f + ".png"}); }
        catch (e2) { r.variants.push({v: tries[i][0], arg: tries[i][1], err: String(e2)}); }
    }
    return r;
};

WNCPP.actions.probe_frame_paths = function (d) {
    // which output-path form does QE exportFramePNG accept on this OS? (Windows: separators / spaces)
    app.enableQE();
    var seq = WNCPP.findSeq(d.sequence_name);
    app.project.openSequence(seq.sequenceID);
    var qs = qe.project.getActiveSequence();
    seq.setPlayerPosition(String(Math.round(d.t * WNCPP.TICKS)));
    var tc = qs.CTI.timecode, r = {os: $.os, tc: tc, variants: []};
    var base = String(d.out_dir);
    var fw = base.replace(/\\/g, "/"), bw = base.replace(/\//g, "\\");
    var tmp = Folder.temp.fsName;
    var tries = [["mixed", base + "/p_mixed"], ["backslash", bw + "\\p_back"], ["forward", fw + "/p_fwd"],
                 ["fsName", new Folder(base).fsName + ($.os.indexOf("Windows") >= 0 ? "\\" : "/") + "p_fs"],
                 ["temp_nospace", tmp + "\\p_tmp"]];
    for (var i = 0; i < tries.length; i++) {
        var row = {v: tries[i][0], path: tries[i][1]};
        try { qs.exportFramePNG(tc, tries[i][1]); row.called = true; } catch (e) { row.err = String(e); }
        $.sleep(400);
        row.exists = new File(tries[i][1] + ".png").exists;
        r.variants.push(row);
    }
    return r;
};

WNCPP.addEffect = function (seq, trackIdx, clipIdx, kind, rec) {
    // Effects can only be ADDED via the QE DOM (by display name); their parameters are then set through the normal DOM.
    // `kind` is a WNCPP.MATCH key: its QE display names are tried in order and the first one found is added, then the
    // match name of the component it appended is checked, so a display name that means another effect in this
    // Premiere is reported {ok: false, got: <match name>} instead of being used. That wrong component is then removed
    // through QE when this Premiere allows it (removed: true, checked through the DOM); otherwise it is reported as
    // left on the clip (removed: false, left_in_place: true). The answer is pushed onto `rec`.
    app.enableQE();
    var qs = qe.project.getActiveSequence();
    var qi = qs.getVideoTrackAt(trackIdx).getItemAt(clipIdx);
    var names = WNCPP.FX_NAMES[kind] || [kind], want = WNCPP.MATCH[kind];
    var r = {track: trackIdx, clip: clipIdx, kind: kind, ok: false};
    for (var i = 0; i < names.length; i++) {
        var fx = qe.project.getVideoEffectByName(names[i]);
        if (!fx) { continue; }
        qi.addVideoEffect(fx);
        r.name = names[i];
        r.got = null;
        try {
            var item = seq.videoTracks[trackIdx].clips[clipIdx];
            r.got = item.components[item.components.numItems - 1].matchName;
        } catch (e) { r.got = null; }
        r.ok = want === undefined || WNCPP.isMatch(r.got, want);
        if (!r.ok) { WNCPP.removeAppended(seq, qi, trackIdx, clipIdx, r); }
        break;                          // one effect added: never a second one on the clip
    }
    if (!r.name) { r.error = "not found"; r.tried = names; }
    if (rec) { rec.push(r); }
    return r;
};

WNCPP.removeAppended = function (seq, qi, trackIdx, clipIdx, r) {
    // remove the component addEffect just appended (the last one) when its match name was wrong. Premiere's DOM has no
    // remove; QE's component may: try it, then trust only the DOM (one component fewer, and the last one not `got`)
    var item = seq.videoTracks[trackIdx].clips[clipIdx], before = item.components.numItems;
    r.removed = false;
    try {
        var n = typeof qi.numComponents === "number" ? qi.numComponents : before;
        var qc = typeof qi.getComponentAt === "function" ? qi.getComponentAt(n - 1) : null;
        if (qc && typeof qc.remove === "function") { qc.remove(); }
        item = seq.videoTracks[trackIdx].clips[clipIdx];
        var count = item.components.numItems, last = null;
        try { last = item.components[count - 1].matchName; } catch (e2) { last = null; }
        r.removed = count === before - 1 && last !== r.got;
    } catch (e) { r.remove_error = String(e); }
    if (!r.removed) {
        r.left_in_place = true;
        r.note = "the wrong effect (" + r.got + ") could not be removed: it is still on the clip";
    }
    return r.removed;
};

WNCPP.clipIndex = function (track, item) {   // QE indexes include empty gaps; find by start time
    app.enableQE();
    return null;
};

WNCPP.actions.test_crop = function (d) {
    var r = {};
    r.newProject = app.newProject(d.project_path);
    app.project.importFiles([d.png], true, app.project.rootItem, false);
    var it = WNCPP.findItemByPath(app.project.rootItem, d.png);
    var seq = app.project.createNewSequenceFromClips("CROP_TEST", [it], app.project.rootItem);
    app.project.openSequence(seq.sequenceID);
    var clip = seq.videoTracks[0].clips[0];
    clip.end = WNCPP.secTime(2);
    r.effect = WNCPP.addEffect(seq, 0, 0, "crop");
    r.added = r.effect.ok === true;
    clip = seq.videoTracks[0].clips[0];
    var comps = [];
    for (var i = 0; i < clip.components.numItems; i++) {
        var c = clip.components[i], props = [];
        for (var j = 0; j < c.properties.numItems; j++) { props.push(c.properties[j].displayName); }
        comps.push({name: c.displayName, props: props});
    }
    r.components = comps;
    var left = WNCPP.prop(WNCPP.compByMatch(clip, WNCPP.MATCH.crop) || WNCPP.comp(clip, "Crop"), "Left");
    r.left_found = !!left;
    if (left) { r.keyed = WNCPP.keyframes(left, clip.inPoint.seconds, [[0, 100], [0.5, 0]]); }
    // render two frames to SEE the sweep
    app.enableQE();
    var qs = qe.project.getActiveSequence();
    var tcs = [];
    var times = [0.04, 0.25, 1.0];
    for (var k = 0; k < times.length; k++) {
        seq.setPlayerPosition(String(Math.round(times[k] * WNCPP.TICKS)));
        var tc = qs.CTI.timecode; tcs.push(tc);
        qs.exportFramePNG(tc, WNCPP.outPath(d.out_dir, "crop_t" + k));
    }
    r.tcs = tcs;
    app.project.closeDocument(0, 0);
    return r;
};

WNCPP.DIRTY_API = ["dirty", "isDirty"];   // Premiere's ExtendScript documents no dirty flag: these members are probed
WNCPP.dirtyProbe = function (pr) {
    // {dirty: true|false, api: <member>} from the first member that answers a boolean, else {dirty: null, api: null}
    for (var i = 0; i < WNCPP.DIRTY_API.length; i++) {
        var k = WNCPP.DIRTY_API[i], v;
        try { v = pr[k]; if (typeof v === "function") { v = pr[k](); k = k + "()"; } } catch (e) { continue; }
        if (v === true || v === false) { return {dirty: v, api: k}; }
    }
    return {dirty: null, api: null};
};
WNCPP.projectDirty = function (pr) { return WNCPP.dirtyProbe(pr).dirty; };   // true / false / null (unknown: never clean)

WNCPP.actions.close_project_path = function (d) {
    // close a specific project if it is open. save "always" (the default): saved first so nothing is lost.
    // save "if_clean" (ppro_build, Gate 2 B2): unsaved changes (dirty true) -> nothing is saved or closed; a clean
    // project (dirty false) is closed without a save; unknown (dirty null) -> saved, then closed, as "always".
    // The readback always says dirty, saved and dirty_api (the member that answered; null = this Premiere has none).
    var mode = d.save === "if_clean" ? "if_clean" : "always";
    if (!app.projects) { return {closed: false, reason: "no projects collection", dirty: null, saved: false, dirty_api: null}; }
    for (var i = 0; i < app.projects.numProjects; i++) {
        var pr = app.projects[i];
        if (pr.path === d.path) {
            var p = WNCPP.dirtyProbe(pr), out = {path: d.path, dirty: p.dirty, saved: false, dirty_api: p.api};
            if (mode === "if_clean" && p.dirty === true) {
                out.closed = false;
                out.reason = "unsaved changes in Premiere";
                return out;
            }
            if (mode === "if_clean" && p.dirty === false) { out.closed = pr.closeDocument(0, 0); return out; }
            pr.save();
            out.saved = true;
            out.closed = pr.closeDocument(1, 0);
            return out;
        }
    }
    return {closed: false, reason: "not open", dirty: null, saved: false, dirty_api: null};
};

WNCPP.actions.close_project = function (d) {
    var p = app.project.path;
    var ok = app.project.closeDocument(d.save ? 1 : 0, 0);
    return {closed: ok, path: p};
};

/* Addendum G2 R1 (H4): development leftovers that discard the open project (close_project without save) or make a new
   project over a path with no backup (test_crop, new_project_import). They run only for a job with dev:true, which
   reel serve and the engine never set (WHYNOT_BRIDGE_DEV tooling only). */
WNCPP.DEV_ONLY = {test_crop: true, new_project_import: true};
WNCPP.devRefusal = function (d) {
    if (d.dev === true) { return null; }
    if (WNCPP.DEV_ONLY[d.action] === true || (d.action === 'close_project' && !d.save)) {
        return d.action + (d.action === 'close_project' ? ' without save' : '') +
            ' is a development action and is refused without dev:true (it can discard work): nothing was changed';
    }
    return null;
};

WNCPP.run = function (dataPath) {
    var d;
    try { d = WNCPP.read(dataPath); } catch (e) { return WNCPP.str({ok: false, error: 'bad data file: ' + e}); }
    var fn = WNCPP.actions[d.action];
    if (!fn) { return WNCPP.str({ok: false, error: 'unknown action ' + d.action}); }
    var refused = WNCPP.devRefusal(d);
    if (refused) { return WNCPP.str({ok: false, action: d.action, error: refused}); }
    try {
        var res = fn(d);
        return WNCPP.str({ok: true, action: d.action, result: res});
    } catch (err) {
        return WNCPP.str({ok: false, action: d.action, error: String(err), line: err.line});
    }
};
var NHPP = WNCPP; // 3.0 only: the legacy 3.1.1 bridge evaluates NHPP.run(...) after this file (D18 alias; removed in 3.1)
