/*  whynot-cut — Premiere Pro ExtendScript library (run inside Premiere via the WhyNot Cut Bridge panel).
    NHPP.run(dataFilePath) reads a JSON job (ASCII-escaped) and dispatches on data.action.
    Every action returns a JSON string with read-back evidence (what Premiere actually reports),
    never just "ok".
*/
var NHPP = NHPP || {};
NHPP.TICKS = 254016000000;

/* ---- tiny JSON (ExtendScript has no JSON object) ---- */
NHPP.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-￿]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
NHPP.str = function (v) {
    if (v === null || v === undefined) { return 'null'; }
    var t = typeof v;
    if (t === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (t === 'boolean') { return v ? 'true' : 'false'; }
    if (t === 'string') { return NHPP.q(v); }
    if (v instanceof Array) { var a = []; for (var i = 0; i < v.length; i++) { a.push(NHPP.str(v[i])); } return '[' + a.join(',') + ']'; }
    if (t === 'object') {
        var o = [];
        for (var k in v) { if (v.hasOwnProperty(k) && typeof v[k] !== 'function') { o.push(NHPP.q(k) + ':' + NHPP.str(v[k])); } }
        return '{' + o.join(',') + '}';
    }
    return NHPP.q(String(v));
};
NHPP.read = function (p) {
    var f = new File(p); f.encoding = 'UTF-8'; f.open('r'); var t = f.read(); f.close();
    return eval('(' + t + ')');  // trusted: written by the pipeline itself
};

NHPP.findSeq = function (name) {
    for (var i = 0; i < app.project.sequences.numSequences; i++) {
        var s = app.project.sequences[i];
        if (s.name === name) { return s; }
    }
    return null;
};
NHPP.findBin = function (parent, name) {
    for (var i = 0; i < parent.children.numItems; i++) {
        var c = parent.children[i];
        if (c.type === ProjectItemType.BIN && c.name === name) { return c; }
    }
    return null;
};
NHPP.bin = function (name) {
    var b = NHPP.findBin(app.project.rootItem, name);
    if (!b) { app.project.rootItem.createBin(name); b = NHPP.findBin(app.project.rootItem, name); }
    return b;
};
NHPP.findItemByPath = function (parent, path) {
    for (var i = 0; i < parent.children.numItems; i++) {
        var c = parent.children[i];
        if (c.type === ProjectItemType.BIN) { var r = NHPP.findItemByPath(c, path); if (r) { return r; } }
        else { try { if (c.getMediaPath && c.getMediaPath() === path) { return c; } } catch (e) {} }
    }
    return null;
};

NHPP.settingsDump = function (seq) {
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

NHPP.tracksDump = function (seq) {
    var v = [], a = [];
    for (var i = 0; i < seq.videoTracks.numTracks; i++) { var t = seq.videoTracks[i]; v.push({i: i + 1, name: t.name, clips: t.clips.numItems}); }
    for (var j = 0; j < seq.audioTracks.numTracks; j++) { var u = seq.audioTracks[j]; a.push({i: j + 1, name: u.name, clips: u.clips.numItems}); }
    return {video: v, audio: a};
};

/* ---------------------------------------------------------------- actions */
NHPP.actions = {};

NHPP.actions.ping = function (d) {
    return {version: app.version, build: app.build, project: app.project ? app.project.path : null,
            projects_open: app.projects ? app.projects.numProjects : null};
};

NHPP.actions.probe = function (d) {
    var r = {version: app.version, project: app.project.path, sequences: []};
    for (var i = 0; i < app.project.sequences.numSequences; i++) {
        var s = app.project.sequences[i];
        r.sequences.push({name: s.name, settings: NHPP.settingsDump(s), tracks: NHPP.tracksDump(s)});
    }
    r.caption_constants = {};
    try { r.caption_constants.SUBTITLE = Sequence.CAPTION_FORMAT_SUBTITLE; } catch (e) { r.caption_constants.err = String(e); }
    return r;
};

NHPP.actions.new_project_import = function (d) {
    var ok = app.newProject(d.project_path);
    var r = {newProject: ok, project: app.project ? app.project.path : null};
    if (d.xml_path) {
        r.importXML = app.project.importFiles([d.xml_path], true, app.project.rootItem, false);
        var seq = NHPP.findSeq(d.sequence_name);
        r.sequence_found = !!seq;
        if (seq) { r.settings = NHPP.settingsDump(seq); r.tracks = NHPP.tracksDump(seq); }
    }
    return r;
};

NHPP.waitSeq = function (name, ms) {   // XML import can register the sequence a moment later
    for (var t = 0; t < (ms || 8000); t += 250) { var s = NHPP.findSeq(name); if (s) { return s; } $.sleep(250); }
    return null;
};

NHPP.actions.import_xml_count = function (d) {
    var ok = app.project.importFiles([d.xml_path], true, app.project.rootItem, false);
    var seq = NHPP.waitSeq(d.sequence_name);
    return {imported: ok, found: !!seq, tracks: seq ? NHPP.tracksDump(seq) : null};
};

NHPP.actions.reference_export = function (d) {
    // Ask Premiere for its OWN FCP XML of a sequence made from the clip: ground truth for our generator.
    app.project.importFiles([d.media_path], true, app.project.rootItem, false);
    var item = NHPP.findItemByPath(app.project.rootItem, d.media_path);
    if (!item) { return {error: "imported item not found"}; }
    var seq = app.project.createNewSequenceFromClips(d.sequence_name, [item], app.project.rootItem);
    var ok = seq.exportAsFinalCutProXML(d.out_xml, 1);
    return {exported: ok, tracks: NHPP.tracksDump(seq), settings: NHPP.settingsDump(seq)};
};

/* ---------------------------------------------------------------- full Premiere-only build */
NHPP.comp = function (item, name) {
    for (var i = 0; i < item.components.numItems; i++) { var c = item.components[i]; if (c.displayName === name) { return c; } }
    return null;
};
NHPP.prop = function (comp, name) {
    if (!comp) { return null; }
    for (var i = 0; i < comp.properties.numItems; i++) { var p = comp.properties[i]; if (p.displayName === name) { return p; } }
    return null;
};
NHPP.keyframes = function (prop, base, pairs) {   // pairs: [[offsetSeconds, value], ...] relative to clip in-point
    if (!prop) { return false; }
    prop.setTimeVarying(true);
    for (var i = 0; i < pairs.length; i++) { var t = base + pairs[i][0]; prop.addKey(t); prop.setValueAtKey(t, pairs[i][1], true); }
    return true;
};
NHPP.itemAt = function (track, startSec) {
    var best = null, bd = 1e9;
    for (var i = 0; i < track.clips.numItems; i++) {
        var c = track.clips[i], dd = Math.abs(c.start.seconds - startSec);
        if (dd < bd) { bd = dd; best = c; }
    }
    return bd < 0.05 ? best : null;
};
NHPP.secTime = function (sec) { var t = new Time(); t.seconds = sec; return t; };

NHPP.F = 1 / 24;
NHPP.placeStill = function (seq, trackIdx, projItem, g, log) {
    var track = seq.videoTracks[trackIdx];
    track.overwriteClip(projItem, g.start_s);
    var it = NHPP.itemAt(track, g.start_s);
    if (!it) { log.push("placement not found: " + g.id); return null; }
    it.end = NHPP.secTime(g.end_s);
    var base = it.inPoint.seconds, dur = g.end_s - g.start_s, F = NHPP.F;
    var motion = NHPP.comp(it, "Motion");
    var op = NHPP.prop(NHPP.comp(it, "Opacity"), "Opacity");
    var fo = Math.min(g.fade_out_s || 0, dur / 3);
    var outKeys = fo > 0 ? [[dur - fo, 100], [dur, 0]] : [];
    var a = g.anim;
    if (a === "flash") {
        NHPP.keyframes(op, base, [[0, 0], [dur / 2, g.peak || 90], [dur, 0]]);
    } else if (a === "text_pop") {            // reference: text pops in fast
        NHPP.keyframes(op, base, [[0, 0], [2 * F, 100]].concat(outKeys));
        NHPP.keyframes(NHPP.prop(motion, "Scale"), base, [[0, 90], [4 * F, 100]]);
    } else if (a === "bar_sweep") {           // reference: teal bar sweeps in right-to-left (RTL)
        var d0 = (g.delay_f || 1) * F, sw = (g.sweep_f || 6) * F;
        NHPP.keyframes(NHPP.prop(motion, "Crop Left"), base, [[0, 100], [d0, 100], [d0 + sw, 0]]);
        if (outKeys.length) { NHPP.keyframes(op, base, [[0, 100]].concat(outKeys)); }
    } else if (a === "slide") {               // checklist item slides in from the right
        var pos = NHPP.prop(motion, "Position"), v = pos.getValue();
        var dx = (v[0] <= 2) ? 60 / 1080 : 60;   // normalised or pixel coordinates, whichever this build uses
        NHPP.keyframes(pos, base, [[0, [v[0] + dx, v[1]]], [5 * F, [v[0], v[1]]]]);
        NHPP.keyframes(op, base, [[0, 0], [4 * F, 100]].concat(outKeys));
    } else if (a === "push") {                // full-screen card: fade + slow push
        NHPP.keyframes(op, base, [[0, 0], [6 * F, 100]].concat(outKeys));
        NHPP.keyframes(NHPP.prop(motion, "Scale"), base, [[0, 100], [dur, 103]]);
    } else if (a === "card") {                // closing glass card
        var fi = Math.min(g.fade_in_s || 10 * F, dur / 3);
        NHPP.keyframes(op, base, [[0, 0], [fi, 100]].concat(outKeys));
        NHPP.keyframes(NHPP.prop(motion, "Scale"), base, [[0, 96], [fi, 100]]);
    } else {
        NHPP.keyframes(op, base, [[0, 0], [5 * F, 100]].concat(outKeys));
    }
    return {id: g.id, track: trackIdx + 1, start: it.start.seconds, end: it.end.seconds, anim: a};
};

NHPP.actions.build_project = function (d) {
    var log = [], ev = {};
    // 1. project
    if (d.overwrite_existing !== true && new File(d.project_path).exists) { return {error: "project exists (set overwrite_existing)"}; }
    ev.newProject = app.newProject(d.project_path);
    ev.project = app.project.path;
    var root = app.project.rootItem;
    var bins = {};
    var names = ["00 Sequences", "01 Footage", "02 Graphics", "03 Sound FX", "04 Captions"];
    for (var b = 0; b < names.length; b++) { bins[names[b]] = NHPP.bin(names[b]); }
    // 2. base sequence from XML (footage, punch-ins, dialogue, SFX, empty graphic tracks)
    ev.importXML = app.project.importFiles([d.xml_path], true, root, false);
    var seq = NHPP.waitSeq(d.sequence_name, 15000);
    if (!seq) { return {error: "sequence not found after XML import", log: log}; }
    app.project.openSequence(seq.sequenceID);
    // 3. sequence settings (what XML can't carry) -> set, then READ BACK
    var st = seq.getSettings();
    for (var k in d.settings) { if (d.settings.hasOwnProperty(k)) { try { st[k] = d.settings[k]; } catch (e1) { log.push("setting " + k + ": " + e1); } } }
    ev.setSettings = seq.setSettings(st);
    ev.settings_after = NHPP.settingsDump(seq);
    // 4. graphics: import stills, place with Premiere keyframes
    var gpaths = [];
    for (var i = 0; i < d.graphics.length; i++) { gpaths.push(d.graphics[i].png); }
    ev.importGraphics = app.project.importFiles(gpaths, true, bins["02 Graphics"], false);
    ev.placed = [];
    for (var j = 0; j < d.graphics.length; j++) {
        var g = d.graphics[j];
        var pi = NHPP.findItemByPath(bins["02 Graphics"], g.png);
        if (!pi) { log.push("graphic not imported: " + g.png); continue; }
        var r = NHPP.placeStill(seq, g.track_index, pi, g, log);
        if (r) { ev.placed.push(r); }
    }
    // 4b. source cutaways: blur the cover copy on V1 under each whole card (fit + blurred fill)
    ev.blurred = [];
    for (var bi = 0; d.blur_v1_clips && bi < d.blur_v1_clips.length; bi++) {
        var ci = d.blur_v1_clips[bi];
        try {
            if (NHPP.addEffect(seq, 0, ci, "Gaussian Blur")) {
                var bc = NHPP.comp(seq.videoTracks[0].clips[ci], "Gaussian Blur");
                var pb = NHPP.prop(bc, "Blurriness"), pe = NHPP.prop(bc, "Repeat Edge Pixels");
                if (pb) { pb.setValue(90, true); }
                if (pe) { pe.setValue(true, true); }
                ev.blurred.push({clip: ci, blurriness: pb ? pb.getValue() : null});
            } else { log.push("Gaussian Blur effect not found"); }
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
                if (NHPP.addEffect(seq, 0, si, "Sharpen")) {
                    var sa = NHPP.prop(NHPP.comp(v1.clips[si], "Sharpen"), "Sharpen Amount");
                    if (sa) { sa.setValue(d.sharpen_v1.amount, true); rec.ok = true; rec.amount = d.sharpen_v1.amount; }
                    else { log.push("Sharpen Amount property not found"); }
                } else { log.push("Sharpen effect not found"); ev.sharpened.push(rec); break; }
                if (d.sharpen_v1.grain && NHPP.addEffect(seq, 0, si, "Noise")) {
                    // Premiere 26 resolves "Noise" to its grain effect (ADBE_Noise_FX: Intensity, default 50 = heavy);
                    // older versions to the classic Noise ("Amount of Noise" %). Set whichever exists.
                    var nc = NHPP.comp(v1.clips[si], "Noise");
                    var na = NHPP.prop(nc, "Intensity") || NHPP.prop(nc, "Amount of Noise");
                    if (na) { na.setValue(d.sharpen_v1.grain, true); rec.grain = na.getValue(); }
                    else { log.push("Noise: no Intensity / Amount of Noise property"); rec.ok = false; }
                }
                ev.sharpened.push(rec);
            } catch (es) { log.push("sharpen clip " + si + ": " + es); }
        }
    }
    // 5. native captions from SRT
    if (d.srt_path && d.native_caption_track) {
        app.project.importFiles([d.srt_path], true, bins["04 Captions"], false);
        var cap = NHPP.findItemByPath(bins["04 Captions"], d.srt_path);
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
    ev.tracks = NHPP.tracksDump(seq);
    ev.log = log;
    return ev;
};

NHPP.outPath = function (dir, name) {
    // QE exportFramePNG on Windows accepts ONLY native backslash paths ("D:\x\frame"); any "/" throws
    // "Unknown error exception" (probed on Premiere 26.5.2). fsName gives the native form on both systems.
    var win = $.os.indexOf("Windows") >= 0;
    return new Folder(dir).fsName + (win ? "\\" : "/") + name;
};

NHPP.actions.clip_components = function (d) {
    // read-only: the effects on one clip and their property names/values (find Premiere's real names per version)
    var seq = NHPP.findSeq(d.sequence_name);
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

NHPP.activateProject = function (path) {
    // several projects can be open (one per reel): make the one at `path` the active project (opening it if needed)
    var want = String(path).replace(/\//g, "\\").toLowerCase();
    if (app.project && String(app.project.path).replace(/\//g, "\\").toLowerCase() === want) { return true; }
    for (var i = 0; i < app.projects.numProjects; i++) {
        var pp = String(app.projects[i].path);
        if (pp.replace(/\//g, "\\").toLowerCase() === want) { return app.openDocument(pp); }
    }
    return app.openDocument(String(path));
};

NHPP.actions.export_frames = function (d) {
    // Premiere renders frames of ITS OWN timeline -> visual evidence of the real result
    if (d.project_path) { NHPP.activateProject(d.project_path); }
    app.enableQE();
    var seq = NHPP.findSeq(d.sequence_name);
    if (!seq) {
        throw new Error("sequence " + d.sequence_name + " not found in the active project " +
                        (app.project ? app.project.path : "(none)"));
    }
    app.project.openSequence(seq.sequenceID);
    var qs = qe.project.getActiveSequence();
    var out = [];
    for (var i = 0; i < d.times.length; i++) {
        var ticks = String(Math.round(d.times[i] * NHPP.TICKS));
        seq.setPlayerPosition(ticks);
        var f = NHPP.outPath(d.out_dir, "frame_" + ("000000" + Math.round(d.times[i] * 1000)).slice(-6));
        var ok = false;
        // exportFramePNG needs the CTI TIMECODE string; given ticks it silently exports frame 0 (verified 26.5)
        var tc = qs.CTI.timecode;
        try { qs.exportFramePNG(tc, f); ok = true; } catch (e) { out.push({t: d.times[i], error: String(e)}); continue; }
        out.push({t: d.times[i], tc: tc, file: f + ".png", called: ok});
    }
    return {frames: out};
};

NHPP.actions.probe_frame_export = function (d) {
    app.enableQE();
    var seq = NHPP.findSeq(d.sequence_name);
    app.project.openSequence(seq.sequenceID);
    var qs = qe.project.getActiveSequence();
    seq.setPlayerPosition(String(Math.round(d.t * NHPP.TICKS)));
    var r = {player_pos_s: seq.getPlayerPosition().seconds, cti_tc: null, variants: []};
    try { r.cti_tc = qs.CTI.timecode; } catch (e) { r.cti_err = String(e); }
    var tries = [["cti_timecode", r.cti_tc], ["ticks", seq.getPlayerPosition().ticks], ["seconds_str", String(d.t)]];
    for (var i = 0; i < tries.length; i++) {
        var f = NHPP.outPath(d.out_dir, "probe_" + tries[i][0]);
        try { qs.exportFramePNG(tries[i][1], f); r.variants.push({v: tries[i][0], arg: tries[i][1], ok: true, file: f + ".png"}); }
        catch (e2) { r.variants.push({v: tries[i][0], arg: tries[i][1], err: String(e2)}); }
    }
    return r;
};

NHPP.actions.probe_frame_paths = function (d) {
    // which output-path form does QE exportFramePNG accept on this OS? (Windows: separators / spaces)
    app.enableQE();
    var seq = NHPP.findSeq(d.sequence_name);
    app.project.openSequence(seq.sequenceID);
    var qs = qe.project.getActiveSequence();
    seq.setPlayerPosition(String(Math.round(d.t * NHPP.TICKS)));
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

NHPP.addEffect = function (seq, trackIdx, clipIdx, effectName) {
    // Effects can only be ADDED via the QE DOM; their parameters are then keyframed through the normal DOM.
    app.enableQE();
    var qs = qe.project.getActiveSequence();
    var qi = qs.getVideoTrackAt(trackIdx).getItemAt(clipIdx);
    var fx = qe.project.getVideoEffectByName(effectName);
    if (!fx) { return false; }
    qi.addVideoEffect(fx);
    return true;
};

NHPP.clipIndex = function (track, item) {   // QE indexes include empty gaps; find by start time
    app.enableQE();
    return null;
};

NHPP.actions.test_crop = function (d) {
    var r = {};
    r.newProject = app.newProject(d.project_path);
    app.project.importFiles([d.png], true, app.project.rootItem, false);
    var it = NHPP.findItemByPath(app.project.rootItem, d.png);
    var seq = app.project.createNewSequenceFromClips("CROP_TEST", [it], app.project.rootItem);
    app.project.openSequence(seq.sequenceID);
    var clip = seq.videoTracks[0].clips[0];
    clip.end = NHPP.secTime(2);
    r.added = NHPP.addEffect(seq, 0, 0, "Crop");
    clip = seq.videoTracks[0].clips[0];
    var comps = [];
    for (var i = 0; i < clip.components.numItems; i++) {
        var c = clip.components[i], props = [];
        for (var j = 0; j < c.properties.numItems; j++) { props.push(c.properties[j].displayName); }
        comps.push({name: c.displayName, props: props});
    }
    r.components = comps;
    var left = NHPP.prop(NHPP.comp(clip, "Crop"), "Left");
    r.left_found = !!left;
    if (left) { r.keyed = NHPP.keyframes(left, clip.inPoint.seconds, [[0, 100], [0.5, 0]]); }
    // render two frames to SEE the sweep
    app.enableQE();
    var qs = qe.project.getActiveSequence();
    var tcs = [];
    var times = [0.04, 0.25, 1.0];
    for (var k = 0; k < times.length; k++) {
        seq.setPlayerPosition(String(Math.round(times[k] * NHPP.TICKS)));
        var tc = qs.CTI.timecode; tcs.push(tc);
        qs.exportFramePNG(tc, NHPP.outPath(d.out_dir, "crop_t" + k));
    }
    r.tcs = tcs;
    app.project.closeDocument(0, 0);
    return r;
};

NHPP.actions.close_project_path = function (d) {
    // close a specific project if it is open (saved first so nothing is lost)
    if (!app.projects) { return {closed: false, reason: "no projects collection"}; }
    for (var i = 0; i < app.projects.numProjects; i++) {
        var pr = app.projects[i];
        if (pr.path === d.path) { pr.save(); return {closed: pr.closeDocument(1, 0), path: d.path}; }
    }
    return {closed: false, reason: "not open"};
};

NHPP.actions.close_project = function (d) {
    var p = app.project.path;
    var ok = app.project.closeDocument(d.save ? 1 : 0, 0);
    return {closed: ok, path: p};
};

NHPP.run = function (dataPath) {
    var d;
    try { d = NHPP.read(dataPath); } catch (e) { return NHPP.str({ok: false, error: 'bad data file: ' + e}); }
    var fn = NHPP.actions[d.action];
    if (!fn) { return NHPP.str({ok: false, error: 'unknown action ' + d.action}); }
    try {
        var res = fn(d);
        return NHPP.str({ok: true, action: d.action, result: res});
    } catch (err) {
        return NHPP.str({ok: false, action: d.action, error: String(err), line: err.line});
    }
};
