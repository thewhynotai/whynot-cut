/*  Kalam - Premiere Pro ExtendScript host.
    Every public function takes a JSON string and returns a JSON string: {ok:true, ...} or {ok:false, error}.
    Times are seconds on the sequence timeline. Keep this file ASCII. */

var KALAM = KALAM || {};
KALAM.TICKS = 254016000000;
KALAM.BIN = 'Kalam Captions';

/* ---- JSON (ExtendScript has no JSON object) ---- */
KALAM.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-\uffff]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
KALAM.str = function (v) {
    var i, out, k;
    if (v === null || v === undefined) { return 'null'; }
    if (typeof v === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (typeof v === 'boolean') { return v ? 'true' : 'false'; }
    if (typeof v === 'string') { return KALAM.q(v); }
    if (v instanceof Array) {
        out = [];
        for (i = 0; i < v.length; i++) { out.push(KALAM.str(v[i])); }
        return '[' + out.join(',') + ']';
    }
    out = [];
    for (k in v) { if (v.hasOwnProperty(k)) { out.push(KALAM.q(k) + ':' + KALAM.str(v[k])); } }
    return '{' + out.join(',') + '}';
};
KALAM.parse = function (s) { return eval('(' + s + ')'); };
KALAM.wrap = function (fn, argStr) {
    try {
        var res = fn(argStr ? KALAM.parse(argStr) : {});
        res.ok = true;
        return KALAM.str(res);
    } catch (e) {
        return KALAM.str({ ok: false, error: String(e && e.message ? e.message : e), line: e && e.line });
    }
};

/* ---- helpers ---- */
KALAM.seq = function () {
    var s = app.project.activeSequence;
    if (!s) { throw new Error('No active sequence. Open a sequence in the timeline first.'); }
    return s;
};
KALAM.sec = function (t) { return Number(t.ticks) / KALAM.TICKS; };
KALAM.ticksStr = function (sec) { return String(Math.round(sec * KALAM.TICKS)); };
KALAM.timeObj = function (sec) { var t = new Time(); t.ticks = KALAM.ticksStr(sec); return t; };
KALAM.fps = function (seq) { return KALAM.TICKS / Number(seq.timebase); };
KALAM.trackInfo = function (tracks, kind) {
    var out = [], i, t, muted, locked;
    for (i = 0; i < tracks.numTracks; i++) {
        t = tracks[i];
        muted = false; locked = false;
        try { muted = t.isMuted(); } catch (e1) {}
        try { locked = t.isLocked(); } catch (e2) {}
        out.push({ index: i, kind: kind, name: t.name, clips: t.clips.numItems, muted: muted, locked: locked });
    }
    return out;
};

/* ---- info: sequence, tracks, selection ---- */
KALAM.info = function () {
    var seq = KALAM.seq(), sel = [], i, it, items = seq.getSelection();
    for (i = 0; i < items.length; i++) {
        it = items[i];
        if (it.mediaType !== 'Video' && it.mediaType !== 'Audio') { continue; }
        sel.push({ name: it.name, type: it.mediaType, start: KALAM.sec(it.start), end: KALAM.sec(it.end) });
    }
    return {
        sequence: {
            name: seq.name, id: seq.sequenceID, fps: KALAM.fps(seq), end: Number(seq.end) / KALAM.TICKS,
            inPoint: KALAM.sec(seq.getInPointAsTime()), outPoint: KALAM.sec(seq.getOutPointAsTime()),
            playhead: KALAM.sec(seq.getPlayerPosition()),
            video: KALAM.trackInfo(seq.videoTracks, 'video'), audio: KALAM.trackInfo(seq.audioTracks, 'audio'),
            selection: sel
        },
        projectPath: app.project.path
    };
};

/* ---- export the chosen audio tracks of a timeline range to WAV ---- */
KALAM.findPreset = function () {
    var pkg = Folder.appPackage.fsName;
    var cands = [pkg + '/Contents/Settings/EncoderPresets/Wave48mono16.epr',
                 pkg + '/Contents/MediaIO/systempresets/3F3F3F3F_57415645/Waveform Audio 48kHz 16-bit.epr',
                 pkg + '/Settings/EncoderPresets/Wave48mono16.epr',                                   // Windows
                 pkg + '/MediaIO/systempresets/3F3F3F3F_57415645/Waveform Audio 48kHz 16-bit.epr'];
    for (var i = 0; i < cands.length; i++) { if (new File(cands[i]).exists) { return cands[i]; } }
    throw new Error('No WAV export preset found in Premiere.');
};
KALAM.exportAudio = function (a) {
    var seq = KALAM.seq(), i, tr, restore = [], keep = {}, ok;
    var preset = KALAM.findPreset();
    var oldIn = seq.getInPointAsTime().ticks, oldOut = seq.getOutPointAsTime().ticks;
    for (i = 0; i < a.audioTracks.length; i++) { keep[a.audioTracks[i]] = true; }
    if (new File(a.outPath).exists) { new File(a.outPath).remove(); }
    try {
        for (i = 0; i < seq.audioTracks.numTracks; i++) {
            tr = seq.audioTracks[i];
            var was = tr.isMuted(), want = !keep[i];
            if (was !== want) { tr.setMute(want ? 1 : 0); restore.push([i, was]); }
        }
        seq.setInPoint(KALAM.ticksStr(a.start));
        seq.setOutPoint(KALAM.ticksStr(a.end));
        ok = seq.exportAsMediaDirect(a.outPath, preset, app.encoder.ENCODE_IN_TO_OUT);
    } finally {
        for (i = 0; i < restore.length; i++) { seq.audioTracks[restore[i][0]].setMute(restore[i][1] ? 1 : 0); }
        seq.setInPoint(oldIn);
        seq.setOutPoint(oldOut);
    }
    var out = new File(a.outPath);
    if (!out.exists && new File(a.outPath + '.wav').exists) { out = new File(a.outPath + '.wav'); }
    if (!out.exists) { throw new Error('Premiere did not write the audio file (' + ok + ').'); }
    return { path: out.fsName, start: a.start, end: a.end };
};

/* ---- project bin + import ---- */
KALAM.bin = function () {
    var root = app.project.rootItem, i;
    for (i = 0; i < root.children.numItems; i++) {
        if (root.children[i].name === KALAM.BIN && root.children[i].type === ProjectItemType.BIN) { return root.children[i]; }
    }
    return root.createBin(KALAM.BIN);
};
KALAM.importFile = function (path) {
    var bin = KALAM.bin(), before = bin.children.numItems, f = new File(path);
    if (!f.exists) { throw new Error('File not found: ' + path); }
    app.project.importFiles([f.fsName], true, bin, false);
    if (bin.children.numItems <= before) { throw new Error('Premiere did not import ' + f.name); }
    return bin.children[bin.children.numItems - 1];
};

/* ---- output 1: Premiere captions track from the SRT ---- */
KALAM.captionsTrack = function (a) {
    var seq = KALAM.seq();
    var item = KALAM.importFile(a.srtPath);
    if (a.name) { item.name = a.name; }
    var made = seq.createCaptionTrack(item, a.start || 0, Sequence.CAPTION_FORMAT_SUBTITLE);
    if (!made) { throw new Error('Premiere could not create the captions track.'); }
    return { item: item.name, nodeId: item.nodeId };
};

/* ---- output 2: one MOGRT clip per caption ---- */
KALAM.NO_TEXT = 'This .mogrt has no editable text field. Use a MOGRT whose text is exposed in Essential Graphics (for example one made in After Effects).';
KALAM.setText = function (trackItem, text, paramName) {
    var comp = trackItem.getMGTComponent();
    if (!comp) { throw new Error(KALAM.NO_TEXT); }
    var props = comp.properties, i, p, v, data, pick = null;
    for (i = 0; i < props.numItems && !pick; i++) {          // the named field, else the first real text field
        p = props[i];
        v = p.getValue();
        if (paramName ? p.displayName === paramName : (typeof v === 'string' && v.indexOf('textEditValue') >= 0)) { pick = p; }
    }
    if (!pick) { throw new Error(paramName ? 'No field named "' + paramName + '" in this .mogrt.' : KALAM.NO_TEXT); }
    v = pick.getValue();
    if (typeof v === 'string' && v.indexOf('textEditValue') >= 0) {
        data = KALAM.parse(v);
        data.textEditValue = text;
        pick.setValue(KALAM.str(data), true);
    } else {
        pick.setValue(text, true);
    }
    return pick.displayName;
};
KALAM.mogrt = function (a) {
    var seq = KALAM.seq(), i, c, it, field = null, added = 0;
    if (!new File(a.mogrtPath).exists) { throw new Error('MOGRT not found: ' + a.mogrtPath); }
    if (seq.videoTracks.numTracks <= a.videoTrack) {
        throw new Error('Video track V' + (a.videoTrack + 1) + ' does not exist. Add it or pick another track.');
    }
    var made = [];
    try {
        for (i = 0; i < a.captions.length; i++) {
            c = a.captions[i];
            it = seq.importMGT(a.mogrtPath, KALAM.ticksStr((a.start || 0) + c.s), a.videoTrack, 0);
            if (!it) { throw new Error('Premiere could not add the MOGRT at caption ' + (i + 1) + '.'); }
            made.push(it);
            it.end = KALAM.timeObj((a.start || 0) + c.e);
            field = KALAM.setText(it, c.text, a.textParam || null);
            it.name = 'Kalam ' + (i + 1);
            added++;
        }
    } catch (e) {
        for (i = made.length - 1; i >= 0; i--) { try { made[i].remove(false, false); } catch (e2) {} }   // all or nothing
        throw e;
    }
    return { added: added, field: field };
};

/* ---- undo for MOGRT output: remove the clips Kalam added in a range ---- */
KALAM.removeClips = function (a) {
    var seq = KALAM.seq(), clips = seq.videoTracks[a.videoTrack].clips, j, it, s, n = 0;
    for (j = clips.numItems - 1; j >= 0; j--) {
        it = clips[j];
        s = KALAM.sec(it.start);
        if (String(it.name).indexOf('Kalam ') === 0 && s >= a.from - 0.001 && s <= a.to + 0.001) { it.remove(false, false); n++; }
    }
    return { removed: n };
};

KALAM.setPlayhead = function (a) { KALAM.seq().setPlayerPosition(KALAM.ticksStr(a.t)); return {}; };

/* ---- public entry points (called from the panel with a JSON string) ---- */
KALAM.version = function () { return { version: app.version, os: $.os, panel: '1.1.0' }; };
function kalam_version(s) { return KALAM.wrap(KALAM.version, s); }
function kalam_info(s) { return KALAM.wrap(KALAM.info, s); }
function kalam_exportAudio(s) { return KALAM.wrap(KALAM.exportAudio, s); }
function kalam_captionsTrack(s) { return KALAM.wrap(KALAM.captionsTrack, s); }
function kalam_mogrt(s) { return KALAM.wrap(KALAM.mogrt, s); }
function kalam_removeClips(s) { return KALAM.wrap(KALAM.removeClips, s); }
function kalam_setPlayhead(s) { return KALAM.wrap(KALAM.setPlayhead, s); }
