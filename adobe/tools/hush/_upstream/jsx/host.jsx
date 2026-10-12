/*  Hush - Premiere Pro ExtendScript host.
    Every public function takes a JSON string and returns a JSON string: {ok:true, ...} or {ok:false, error}.
    Times crossing the boundary are seconds on the sequence timeline. */

var HUSH = HUSH || {};
HUSH.TICKS = 254016000000;
HUSH.MARKER_PREFIX = 'Hush';

/* ---- JSON (ExtendScript has no JSON object) ---- */
HUSH.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-\uffff]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
HUSH.str = function (v) {
    var i, out, k;
    if (v === null || v === undefined) { return 'null'; }
    if (typeof v === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (typeof v === 'boolean') { return v ? 'true' : 'false'; }
    if (typeof v === 'string') { return HUSH.q(v); }
    if (v instanceof Array) {
        out = [];
        for (i = 0; i < v.length; i++) { out.push(HUSH.str(v[i])); }
        return '[' + out.join(',') + ']';
    }
    out = [];
    for (k in v) { if (v.hasOwnProperty(k)) { out.push(HUSH.q(k) + ':' + HUSH.str(v[k])); } }
    return '{' + out.join(',') + '}';
};
HUSH.parse = function (s) { return eval('(' + s + ')'); };
HUSH.wrap = function (fn, argStr) {
    try {
        var res = fn(argStr ? HUSH.parse(argStr) : {});
        res.ok = true;
        return HUSH.str(res);
    } catch (e) {
        return HUSH.str({ ok: false, error: String(e && e.message ? e.message : e), line: e && e.line });
    }
};

/* ---- helpers ---- */
HUSH.seq = function () {
    var s = app.project.activeSequence;
    if (!s) { throw new Error('No active sequence. Open a sequence in the timeline first.'); }
    return s;
};
HUSH.sec = function (t) { return Number(t.ticks) / HUSH.TICKS; };
HUSH.fps = function (seq) { return HUSH.TICKS / Number(seq.timebase); };
HUSH.ticksStr = function (sec) { return String(Math.round(sec * HUSH.TICKS)); };
HUSH.timeObj = function (sec) { var t = new Time(); t.ticks = HUSH.ticksStr(sec); return t; };
HUSH.isNest = function (item) {
    try { return !!(item.projectItem && item.projectItem.isSequence && item.projectItem.isSequence()); } catch (e) { return false; }
};
HUSH.trackInfo = function (tracks, kind) {
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
HUSH.timecode = function (seq, sec) {
    var t = HUSH.timeObj(sec);
    var st = seq.getSettings();
    return t.getFormatted(st.videoFrameRate, st.videoDisplayFormat);
};

/* ---- info: sequence, tracks, selection ---- */
HUSH.info = function () {
    var seq = HUSH.seq(), sel = [], i, it, s;
    var items = seq.getSelection();
    for (i = 0; i < items.length; i++) {
        it = items[i];
        if (it.mediaType !== 'Video' && it.mediaType !== 'Audio') { continue; }
        sel.push({ name: it.name, type: it.mediaType, start: HUSH.sec(it.start), end: HUSH.sec(it.end), nest: HUSH.isNest(it) });
    }
    var inP = HUSH.sec(seq.getInPointAsTime()), outP = HUSH.sec(seq.getOutPointAsTime());
    s = {
        name: seq.name, id: seq.sequenceID, fps: HUSH.fps(seq), end: Number(seq.end) / HUSH.TICKS,
        inPoint: inP, outPoint: outP,
        video: HUSH.trackInfo(seq.videoTracks, 'video'), audio: HUSH.trackInfo(seq.audioTracks, 'audio'),
        selection: sel
    };
    return { sequence: s, projectPath: app.project.path };
};

/* ---- export the audio of a timeline range to WAV ---- */
HUSH.findPreset = function (extDir) {
    var pkg = Folder.appPackage.fsName;
    var cands = [
        extDir + '/presets/Hush_WAV48k16.epr',
        pkg + '/Contents/Settings/EncoderPresets/Wave48mono16.epr',
        pkg + '/Contents/MediaIO/systempresets/3F3F3F3F_57415645/Waveform Audio 48kHz 16-bit.epr'
    ];
    for (var i = 0; i < cands.length; i++) { if (new File(cands[i]).exists) { return cands[i]; } }
    throw new Error('No WAV export preset found in Premiere.');
};

HUSH.exportAudio = function (a) {
    var seq = HUSH.seq(), i, tr, restoreMute = [];
    var preset = HUSH.findPreset(a.extDir);
    var oldIn = seq.getInPointAsTime().ticks, oldOut = seq.getOutPointAsTime().ticks;
    var keep = {};
    for (i = 0; i < a.audioTracks.length; i++) { keep[a.audioTracks[i]] = true; }
    var f = new File(a.outPath);
    if (f.exists) { f.remove(); }
    try {
        // analyse only the chosen audio tracks: mute the others while exporting
        for (i = 0; i < seq.audioTracks.numTracks; i++) {
            tr = seq.audioTracks[i];
            var was = tr.isMuted();
            var want = keep[i] ? false : true;
            if (was !== want) { tr.setMute(want ? 1 : 0); restoreMute.push([i, was]); }
        }
        seq.setInPoint(HUSH.ticksStr(a.start));
        seq.setOutPoint(HUSH.ticksStr(a.end));
        var ok = seq.exportAsMediaDirect(a.outPath, preset, app.encoder.ENCODE_IN_TO_OUT);
    } finally {
        for (i = 0; i < restoreMute.length; i++) { seq.audioTracks[restoreMute[i][0]].setMute(restoreMute[i][1] ? 1 : 0); }
        seq.setInPoint(oldIn);
        seq.setOutPoint(oldOut);
    }
    // the export's own extension may be appended
    var out = new File(a.outPath);
    if (!out.exists && new File(a.outPath + '.wav').exists) { out = new File(a.outPath + '.wav'); }
    if (!out.exists) { throw new Error('Premiere did not write the audio file (' + ok + ').'); }
    return { path: out.fsName, start: a.start, end: a.end, preset: preset };
};

/* ---- source-media fallback: media path + timing of each selected clip ---- */
HUSH.clipSources = function (a) {
    var seq = HUSH.seq(), out = [], i, it;
    var items = seq.getSelection();
    for (i = 0; i < items.length; i++) {
        it = items[i];
        if (it.mediaType !== 'Audio' || !it.projectItem) { continue; }
        out.push({ path: it.projectItem.getMediaPath(), start: HUSH.sec(it.start), end: HUSH.sec(it.end), inPoint: HUSH.sec(it.inPoint) });
    }
    return { clips: out };
};

/* ---- backup ---- */
HUSH.cloneSequence = function (seq) {
    var before = {}, i, p = app.project, ss;
    for (i = 0; i < p.sequences.numSequences; i++) { before[p.sequences[i].sequenceID] = true; }
    seq.clone();
    for (i = 0; i < p.sequences.numSequences; i++) {
        ss = p.sequences[i];
        if (!before[ss.sequenceID]) { return ss; }
    }
    return null;
};
HUSH.stamp = function () {
    var d = new Date();
    function z(n) { return (n < 10 ? '0' : '') + n; }
    return z(d.getHours()) + ':' + z(d.getMinutes()) + ':' + z(d.getSeconds());
};

/* ---- cut ----
   a.cuts: [[start,end],...] seconds, frame-aligned, non-overlapping
   a.video / a.audio: track indices to cut
   a.ripple: close the gaps; a.backup: clone the sequence first */
HUSH.cut = function (a) {
    var seq = HUSH.seq(), i, j, k, c, backup = null;
    var cuts = a.cuts.slice(0).sort(function (x, y) { return x[0] - y[0]; });
    if (!cuts.length) { return { removed: 0, cuts: 0 }; }
    if (a.backup) {
        var b = HUSH.cloneSequence(seq);
        if (b) { b.name = seq.name + ' (Hush backup ' + HUSH.stamp() + ')'; backup = { id: b.sequenceID, name: b.name }; }
        // cloning can make the copy the active timeline; switch back to the original
        app.project.openSequence(seq.sequenceID);
    }
    app.enableQE();
    var qs = qe.project.getActiveSequence();
    if (!app.project.activeSequence || app.project.activeSequence.sequenceID !== seq.sequenceID || qs.name !== seq.name) {
        throw new Error('Could not make "' + seq.name + '" the active timeline. Nothing was cut.');
    }
    var half = 0.5 / HUSH.fps(seq);
    var tracks = [];
    for (i = 0; i < a.video.length; i++) { tracks.push(HUSH.trackRef(seq, qs, 'video', a.video[i])); }
    for (i = 0; i < a.audio.length; i++) { tracks.push(HUSH.trackRef(seq, qs, 'audio', a.audio[i])); }
    for (k = 0; k < tracks.length; k++) {
        if (tracks[k].t().isLocked()) { throw new Error('Track ' + tracks[k].name + ' is locked. Unlock it or untick it.'); }
    }

    // 1) razor every chosen track at every boundary
    var edges = [];
    for (i = 0; i < cuts.length; i++) { edges.push(cuts[i][0]); edges.push(cuts[i][1]); }
    for (k = 0; k < tracks.length; k++) {
        for (i = 0; i < edges.length; i++) {
            if (HUSH.clipAt(tracks[k].t(), edges[i], half) === 'inside') { tracks[k].q.razor(HUSH.timecode(seq, edges[i])); }
        }
    }

    // 2) remove the pieces inside each cut
    var removed = 0;
    for (k = 0; k < tracks.length; k++) {
        var clips = tracks[k].t().clips;
        for (j = clips.numItems - 1; j >= 0; j--) {
            var it = clips[j];
            var s = HUSH.sec(it.start), e = HUSH.sec(it.end);
            for (i = 0; i < cuts.length; i++) {
                if (s >= cuts[i][0] - half && e <= cuts[i][1] + half) { it.remove(false, true); removed++; break; }
            }
        }
    }
    // 3) close the gaps: one pass, every clip moves left by the total cut time before it
    if (a.ripple) { HUSH.closeGaps(tracks, cuts, half); }
    // 4) keep every video piece linked to the audio piece(s) under it
    var linked = a.link ? HUSH.relink(seq, a.video, a.audio) : null;
    return { removed: removed, cuts: cuts.length, backup: backup, sequence: seq.name, sequenceId: seq.sequenceID, linked: linked };
};

/* track handle; .t() re-reads the DOM track because collections go stale after QE edits */
HUSH.trackRef = function (seq, qs, kind, idx) {
    return {
        name: (kind === 'video' ? seq.videoTracks : seq.audioTracks)[idx].name,
        t: function () { return (kind === 'video' ? seq.videoTracks : seq.audioTracks)[idx]; },
        q: kind === 'video' ? qs.getVideoTrackAt(idx) : qs.getAudioTrackAt(idx)
    };
};

/* is t strictly inside a clip on this track? ('inside' | 'edge' | 'none') */
HUSH.clipAt = function (track, t, tol) {
    var clips = track.clips, j, s, e;
    for (j = 0; j < clips.numItems; j++) {
        s = HUSH.sec(clips[j].start); e = HUSH.sec(clips[j].end);
        if (t > s + tol && t < e - tol) { return 'inside'; }
        if (Math.abs(t - s) <= tol || Math.abs(t - e) <= tol) { return 'edge'; }
    }
    return 'none';
};

/* move each remaining clip left by the cut time that lies before it (earliest first, so nothing overlaps) */
HUSH.closeGaps = function (tracks, cuts, tol) {
    var k, j, i, it, st, shift;
    for (k = 0; k < tracks.length; k++) {
        var clips = tracks[k].t().clips, list = [];
        for (j = 0; j < clips.numItems; j++) { list.push(clips[j]); }
        for (j = 0; j < list.length; j++) {
            it = list[j];
            st = HUSH.sec(it.start);
            shift = 0;
            for (i = 0; i < cuts.length; i++) { if (cuts[i][1] <= st + tol) { shift += cuts[i][1] - cuts[i][0]; } }
            if (shift > 0) { it.move(HUSH.timeObj(-shift)); }
        }
    }
};

/* link each video piece with the audio pieces that sit (mostly) under it on the chosen tracks.
   Pieces that are already linked are left alone. Works for camera audio and for separately recorded mic audio. */
HUSH.relink = function (seq, vIdx, aIdx) {
    if (typeof seq.linkSelection !== 'function') { return { groups: 0, note: 'linkSelection not available in this Premiere' }; }
    function collect(tracks, idx) {
        var out = [], i, j, c;
        for (i = 0; i < idx.length; i++) {
            c = tracks[idx[i]].clips;
            for (j = 0; j < c.numItems; j++) { out.push({ it: c[j], s: HUSH.sec(c[j].start), e: HUSH.sec(c[j].end) }); }
        }
        return out;
    }
    function linkedCount(it) { try { var L = it.getLinkedItems(); return L ? L.numItems : 0; } catch (e) { return -1; } }
    function clearSel() { var sel = seq.getSelection(), i; for (i = 0; i < sel.length; i++) { sel[i].setSelected(false, false); } }
    var vids = collect(seq.videoTracks, vIdx), auds = collect(seq.audioTracks, aIdx), used = {}, groups = 0, kept = 0, i, k;
    for (i = 0; i < vids.length; i++) {
        var v = vids[i], partners = [];
        for (k = 0; k < auds.length; k++) {
            if (used[k]) { continue; }
            var ov = Math.min(v.e, auds[k].e) - Math.max(v.s, auds[k].s);
            if (ov > 0.5 * (auds[k].e - auds[k].s)) { partners.push(k); }
        }
        if (!partners.length) { continue; }
        for (k = 0; k < partners.length; k++) { used[partners[k]] = true; }
        if (linkedCount(v.it) >= partners.length) { kept++; continue; }
        clearSel();
        v.it.setSelected(true, false);
        for (k = 0; k < partners.length; k++) { auds[partners[k]].it.setSelected(true, false); }
        seq.linkSelection();
        groups++;
    }
    clearSel();
    return { groups: groups, alreadyLinked: kept };
};

/* ---- markers ---- */
HUSH.markers = function (a) {
    var seq = HUSH.seq(), i, r, m, n = 0;
    for (i = 0; i < a.ranges.length; i++) {
        r = a.ranges[i];
        m = seq.markers.createMarker(r.s);
        m.end = r.e;
        m.name = HUSH.MARKER_PREFIX + ' ' + (r.kind === 'filler' ? 'filler' : 'silence');
        m.comments = r.label || '';
        try { m.setColorByIndex(r.kind === 'filler' ? 5 : 1); } catch (e) {}
        n++;
    }
    return { added: n };
};
HUSH.clearMarkers = function () {
    var seq = HUSH.seq(), ms = seq.markers, m = ms.getFirstMarker(), next, n = 0;
    while (m) {
        next = ms.getNextMarker(m);
        if (String(m.name).indexOf(HUSH.MARKER_PREFIX) === 0) { ms.deleteMarker(m); n++; }
        m = next;
    }
    return { removed: n };
};

HUSH.setPlayhead = function (a) { HUSH.seq().setPlayerPosition(HUSH.ticksStr(a.t)); return {}; };

/* ---- undo: bring the backup back as the open sequence, keep the cut version renamed ---- */
HUSH.restore = function (a) {
    var p = app.project, i, ss, backup = null, cut = null;
    for (i = 0; i < p.sequences.numSequences; i++) {
        ss = p.sequences[i];
        if (ss.sequenceID === a.backupId) { backup = ss; }
        if (ss.sequenceID === a.cutId) { cut = ss; }
    }
    if (!backup) { throw new Error('Backup sequence not found (was it deleted?).'); }
    var name = cut ? cut.name : a.originalName;
    if (cut) { cut.name = name + ' (Hush cut ' + HUSH.stamp() + ')'; }
    backup.name = name;
    p.openSequence(backup.sequenceID);
    return { restored: backup.name };
};

/* ---- public entry points (called from the panel with a JSON string) ---- */
function hush_info(s) { return HUSH.wrap(HUSH.info, s); }
function hush_exportAudio(s) { return HUSH.wrap(HUSH.exportAudio, s); }
function hush_clipSources(s) { return HUSH.wrap(HUSH.clipSources, s); }
function hush_cut(s) { return HUSH.wrap(HUSH.cut, s); }
function hush_markers(s) { return HUSH.wrap(HUSH.markers, s); }
function hush_clearMarkers(s) { return HUSH.wrap(HUSH.clearMarkers, s); }
function hush_setPlayhead(s) { return HUSH.wrap(HUSH.setPlayhead, s); }
function hush_restore(s) { return HUSH.wrap(HUSH.restore, s); }
