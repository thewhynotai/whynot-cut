/*  Tidy - Premiere Pro ExtendScript host. Every public function takes a JSON string and returns a JSON string.
    Safety: apply never deletes a bin that still has something in it, and refuses to remove an item that
    a remaining sequence uses, whatever the plan says. Keep this file ASCII and ES3 (no map/filter/forEach). */

var TIDY = TIDY || {};
TIDY.BACKUP = /\((Hush backup|Hush cut) /;
TIDY.TEMP_BIN = 'Tidy - removing';

/* ---- JSON (ExtendScript has no JSON object) ---- */
TIDY.q = function (s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r')
        .replace(/[\u0000-\u001f\u007f-\uffff]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
};
TIDY.str = function (v) {
    var i, out, k;
    if (v === null || v === undefined) { return 'null'; }
    if (typeof v === 'number') { return isFinite(v) ? String(v) : 'null'; }
    if (typeof v === 'boolean') { return v ? 'true' : 'false'; }
    if (typeof v === 'string') { return TIDY.q(v); }
    if (v instanceof Array) {
        out = [];
        for (i = 0; i < v.length; i++) { out.push(TIDY.str(v[i])); }
        return '[' + out.join(',') + ']';
    }
    out = [];
    for (k in v) { if (v.hasOwnProperty(k)) { out.push(TIDY.q(k) + ':' + TIDY.str(v[k])); } }
    return '{' + out.join(',') + '}';
};
TIDY.parse = function (s) { return eval('(' + s + ')'); };
TIDY.wrap = function (fn, argStr) {
    try {
        var res = fn(argStr ? TIDY.parse(argStr) : {});
        res.ok = true;
        return TIDY.str(res);
    } catch (e) {
        return TIDY.str({ ok: false, error: String(e && e.message ? e.message : e), line: e && e.line });
    }
};
TIDY.byId = function (list, name) {
    for (var i = 0; i < list.length; i++) { if (list[i].name === name) { return list[i]; } }
    return null;
};
TIDY.safe = function (f, dflt) { try { return f(); } catch (e) { return dflt; } };

/* ---- walk the project tree ---- */
TIDY.walk = function (fn) {
    function go(bin, path) {
        for (var i = 0; i < bin.children.numItems; i++) {
            var c = bin.children[i];
            if (c.type === ProjectItemType.BIN) {
                var p = path ? path + '/' + c.name : c.name;
                fn(c, path, true, p);
                go(c, p);
            } else {
                fn(c, path, false, null);
            }
        }
    }
    go(app.project.rootItem, '');
};

/* nodeIds referenced by the clips of every sequence: {sequenceItemNodeId: [nodeIds]} */
TIDY.usage = function () {
    var p = app.project, out = {}, i, j, k, m;
    for (i = 0; i < p.sequences.numSequences; i++) {
        var s = p.sequences[i], ids = [], seen = {}, lists = [s.videoTracks, s.audioTracks];
        for (k = 0; k < 2; k++) {
            for (j = 0; j < lists[k].numTracks; j++) {
                var cl = lists[k][j].clips;
                for (m = 0; m < cl.numItems; m++) {
                    var pi = cl[m].projectItem;
                    if (pi && !seen[pi.nodeId]) { seen[pi.nodeId] = true; ids.push(pi.nodeId); }
                }
            }
        }
        var key = TIDY.safe(function () { return s.projectItem.nodeId; }, s.sequenceID);
        out[key] = ids;
    }
    return out;
};

/* the "Source Text" of graphic clips per sequence, top video track first (raw JSON piece; the panel reads it) */
TIDY.texts = function () {
    var p = app.project, out = {}, i, t, c, k, q;
    for (i = 0; i < p.sequences.numSequences; i++) {
        var s = p.sequences[i], found = [];
        for (t = s.videoTracks.numTracks - 1; t >= 0 && found.length < 3; t--) {
            var cl = s.videoTracks[t].clips;
            for (c = 0; c < cl.numItems && found.length < 3; c++) {
                var clip = cl[c], path = TIDY.safe(function () { return clip.projectItem ? clip.projectItem.getMediaPath() : ''; }, '');
                if (path) { continue; }   // real media, not a graphic
                var comps = TIDY.safe(function () { return clip.components; }, null);
                for (k = 0; comps && k < comps.numItems; k++) {
                    var props = comps[k].properties;
                    for (q = 0; props && q < props.numItems; q++) {
                        var v = TIDY.safe(function () { return props[q].getValue(); }, null);
                        if (typeof v === 'string' && v.indexOf('textEditValue') >= 0) {
                            var at = v.indexOf('"textEditValue"');
                            found.push(v.slice(at, at + 4000));
                        }
                    }
                }
            }
        }
        if (found.length) { out[TIDY.safe(function () { return s.projectItem.nodeId; }, s.sequenceID)] = found; }
    }
    return out;
};

/* ---- scan: everything the plan needs (read only) ---- */
TIDY.scan = function () {
    if (!app.project || !app.project.rootItem) { throw new Error('No project is open.'); }
    var items = [], bins = [];
    TIDY.walk(function (c, parent, isBin, binPath) {
        if (isBin) { bins.push({ nodeId: c.nodeId, path: binPath, name: c.name }); return; }
        var isSeq = TIDY.safe(function () { return c.isSequence(); }, false);
        var dur = TIDY.safe(function () { return c.getOutPoint().seconds - c.getInPoint().seconds; }, 0);
        items.push({
            nodeId: c.nodeId, name: c.name, bin: parent, isSequence: isSeq,
            path: isSeq ? '' : TIDY.safe(function () { return c.getMediaPath(); }, ''),
            offline: TIDY.safe(function () { return c.isOffline(); }, false),
            color: TIDY.safe(function () { return c.getColorLabel(); }, -1),
            duration: dur > 0 ? dur : 0
        });
    });
    return { items: items, bins: bins, usage: TIDY.usage(), texts: TIDY.texts(), project: app.project.path, name: app.project.name };
};

/* ---- apply ---- */
TIDY.index = function () {
    var items = {}, bins = {};
    TIDY.walk(function (c, parent, isBin, binPath) { if (isBin) { bins[binPath] = c; } items[c.nodeId] = c; });
    return { items: items, bins: bins };
};
TIDY.ensureBin = function (path, idx) {
    if (idx.bins[path]) { return idx.bins[path]; }
    var parts = path.split('/'), parent = app.project.rootItem, cur = '', i, j, found;
    for (i = 0; i < parts.length; i++) {
        cur = cur ? cur + '/' + parts[i] : parts[i];
        if (!idx.bins[cur]) {
            found = null;
            for (j = 0; j < parent.children.numItems; j++) {
                if (parent.children[j].type === ProjectItemType.BIN && parent.children[j].name === parts[i]) { found = parent.children[j]; }
            }
            idx.bins[cur] = found || parent.createBin(parts[i]);
        }
        parent = idx.bins[cur];
    }
    return parent;
};

TIDY.apply = function (a) {
    var idx = TIDY.index(), i, it, res = { moved: 0, removed: 0, skipped: 0, binsRemoved: 0, colored: 0, renamed: 0, problems: [] };
    var removing = {}, toRemove = [];
    for (i = 0; i < (a.removals || []).length; i++) { if (a.removals[i].checked) { removing[a.removals[i].nodeId] = true; } }

    // safety: what the remaining sequences use right now
    var usage = TIDY.usage(), used = {}, sid, j;
    for (sid in usage) {
        if (!usage.hasOwnProperty(sid) || removing[sid]) { continue; }
        for (j = 0; j < usage[sid].length; j++) { used[usage[sid][j]] = true; }
    }
    for (i = 0; i < (a.removals || []).length; i++) {
        var r = a.removals[i];
        if (!r.checked) { continue; }
        it = idx.items[r.nodeId];
        if (!it) { continue; }
        var isSeq = TIDY.safe(function () { return it.isSequence(); }, false);
        if (used[r.nodeId] || (isSeq && !TIDY.BACKUP.test(it.name))) { res.skipped++; res.problems.push('kept (in use): ' + it.name); continue; }
        toRemove.push(it);
    }

    // 1) moves into type bins
    for (i = 0; i < (a.moves || []).length; i++) {
        it = idx.items[a.moves[i].nodeId];
        if (!it || removing[a.moves[i].nodeId]) { continue; }
        if (TIDY.safe(function () { return it.moveBin(TIDY.ensureBin(a.moves[i].to, idx)); }, false)) { res.moved++; } else { res.problems.push('could not move ' + it.name); }
    }
    // 2) removals: into one temporary bin, then delete that bin (the only removal the API offers)
    if (toRemove.length) {
        var tmp = app.project.rootItem.createBin(TIDY.TEMP_BIN);
        for (i = 0; i < toRemove.length; i++) { if (TIDY.safe(function () { return toRemove[i].moveBin(tmp); }, false)) { res.removed++; } }
        if (!TIDY.safe(function () { tmp.deleteBin(); return true; }, false)) { res.problems.push('could not delete the bin ' + TIDY.TEMP_BIN); }
    }
    // 3) empty old bins, deepest first - never a bin that still holds anything.
    //    Found by nodeId, not path: a project can hold two sibling bins with the same name.
    //    The index is rebuilt after every delete so no deleted bin is ever touched again.
    idx = TIDY.index();
    for (i = 0; i < (a.emptyBins || []).length; i++) {
        var b = idx.items[a.emptyBins[i].nodeId];
        if (!b || b.type !== ProjectItemType.BIN || TIDY.safe(function () { return b.children.numItems; }, 1) !== 0) { continue; }
        if (TIDY.safe(function () { b.deleteBin(); return true; }, false)) { res.binsRemoved++; idx = TIDY.index(); }
        else { res.problems.push('could not delete the bin ' + a.emptyBins[i].path); }
    }
    // 4) colours
    for (i = 0; i < (a.colors || []).length; i++) {
        it = idx.items[a.colors[i].nodeId];
        if (it && TIDY.safe(function () { it.setColorLabel(a.colors[i].color); return true; }, false)) { res.colored++; }
    }
    // 5) nest names (sequences only)
    for (i = 0; i < (a.renames || []).length; i++) {
        var rn = a.renames[i];
        it = idx.items[rn.nodeId];
        if (!rn.checked || !it || !TIDY.safe(function () { return it.isSequence(); }, false)) { continue; }
        if (TIDY.safe(function () { it.name = rn.to; return true; }, false)) { res.renamed++; } else { res.problems.push('could not rename ' + it.name); }
    }
    return res;
};

/* ---- podcast sync ---- */
TIDY.findPreset = function () {
    var pkg = Folder.appPackage.fsName;
    var cands = [pkg + '/Contents/Settings/EncoderPresets/Wave48mono16.epr',
                 pkg + '/Contents/MediaIO/systempresets/3F3F3F3F_57415645/Waveform Audio 48kHz 16-bit.epr',
                 pkg + '/Settings/EncoderPresets/Wave48mono16.epr',
                 pkg + '/MediaIO/systempresets/3F3F3F3F_57415645/Waveform Audio 48kHz 16-bit.epr'];
    for (var i = 0; i < cands.length; i++) { if (new File(cands[i]).exists) { return cands[i]; } }
    throw new Error('No WAV export preset found in Premiere.');
};
/* one clip's sound -> WAV (48 kHz mono 16-bit), through a temporary sequence that is deleted afterwards */
TIDY.exportClipAudio = function (a) {
    var idx = TIDY.index(), it = idx.items[a.nodeId], keep = app.project.activeSequence, ok, seq;
    if (!it) { throw new Error('Clip not found: ' + a.nodeId); }
    if (new File(a.outPath).exists) { new File(a.outPath).remove(); }
    if (new File(a.outPath + '.wav').exists) { new File(a.outPath + '.wav').remove(); }
    seq = app.project.createNewSequenceFromClips('Tidy sync temp', [it], app.project.rootItem);
    try {
        ok = seq.exportAsMediaDirect(a.outPath, TIDY.findPreset(), app.encoder.ENCODE_ENTIRE);
    } finally {
        TIDY.safe(function () { app.project.deleteSequence(seq); return true; }, false);
        if (keep) { TIDY.safe(function () { app.project.openSequence(keep.sequenceID); return true; }, false); }
    }
    var out = new File(a.outPath);
    if (!out.exists && new File(a.outPath + '.wav').exists) { out = new File(a.outPath + '.wav'); }
    if (!out.exists) { throw new Error('Premiere did not write the audio of ' + it.name + ' (' + ok + ')'); }
    return { path: out.fsName };
};
/* new sequence: camera n on video track n (its sound wherever Premiere puts it), the mics on the audio tracks after
   the last one the cameras use. Settings come from a.first (Cam 1's longest clip). Every placement is read back. */
TIDY.addTracks = function (seq, nV, nA) {
    var needV = Math.max(0, nV - seq.videoTracks.numTracks), needA = Math.max(0, nA - seq.audioTracks.numTracks);
    if (!needV && !needA) { return seq; }
    app.enableQE();
    qe.project.getActiveSequence().addTracks(needV, seq.videoTracks.numTracks, needA, 1, seq.audioTracks.numTracks, 0, 0, 0);
    seq = app.project.activeSequence;   // the old track lists may be stale after QE
    if (seq.videoTracks.numTracks < nV || seq.audioTracks.numTracks < nA) {
        throw new Error('Premiere did not add the tracks (' + seq.videoTracks.numTracks + ' video, ' + seq.audioTracks.numTracks + ' audio).');
    }
    return seq;
};
TIDY.buildSynced = function (a) {
    var idx = TIDY.index(), cams = a.cams || [], mics = a.mics || [], i, t, c, nV = 0;
    for (i = 0; i < cams.length; i++) { if (cams[i].track + 1 > nV) { nV = cams[i].track + 1; } }
    var first = idx.items[a.first || (cams.length ? cams[0] : mics[0]).nodeId];
    if (!first) { throw new Error('Nothing to place.'); }
    var bin = TIDY.ensureBin(a.bin || '06 Sequences', idx);
    var seq = app.project.createNewSequenceFromClips(a.name, [first], bin);
    app.project.openSequence(seq.sequenceID);
    seq = app.project.activeSequence;
    for (t = 0; t < seq.videoTracks.numTracks; t++) { for (c = seq.videoTracks[t].clips.numItems - 1; c >= 0; c--) { seq.videoTracks[t].clips[c].remove(false, false); } }
    for (t = 0; t < seq.audioTracks.numTracks; t++) { for (c = seq.audioTracks[t].clips.numItems - 1; c >= 0; c--) { seq.audioTracks[t].clips[c].remove(false, false); } }
    // room for every camera, and for the camera sound (up to 2 channels each) before the mics are placed
    seq = TIDY.addTracks(seq, nV, Math.max(nV * 2, 1));
    var placed = 0, problems = [];
    for (i = 0; i < cams.length; i++) {
        var ci = idx.items[cams[i].nodeId];
        if (!ci) { problems.push('missing ' + cams[i].nodeId); continue; }
        seq.videoTracks[cams[i].track].overwriteClip(ci, cams[i].start);
        placed++;
    }
    var used = -1;
    for (t = 0; t < seq.audioTracks.numTracks; t++) { if (seq.audioTracks[t].clips.numItems > 0) { used = t; } }
    seq = TIDY.addTracks(seq, nV, used + 1 + mics.length);
    for (i = 0; i < mics.length; i++) {
        var mi = idx.items[mics[i].nodeId];
        if (!mi) { problems.push('missing ' + mics[i].nodeId); continue; }
        seq.audioTracks[used + 1 + i].overwriteClip(mi, mics[i].start);
        placed++;
    }
    // read back: every clip must sit where it was asked to (within one frame)
    var frame = 1 / TIDY.fps(seq), want = [], k;
    for (i = 0; i < cams.length; i++) { want.push({ list: seq.videoTracks[cams[i].track].clips, id: cams[i].nodeId, start: cams[i].start }); }
    for (i = 0; i < mics.length; i++) { want.push({ list: seq.audioTracks[used + 1 + i].clips, id: mics[i].nodeId, start: mics[i].start }); }
    for (i = 0; i < want.length; i++) {
        var ok = false;
        for (k = 0; k < want[i].list.numItems; k++) {
            var cl = want[i].list[k];
            if (cl.projectItem && cl.projectItem.nodeId === want[i].id && Math.abs(cl.start.seconds - want[i].start) <= frame + 1e-6) { ok = true; }
        }
        if (!ok) { problems.push('not where expected: ' + (idx.items[want[i].id] ? idx.items[want[i].id].name : want[i].id)); }
    }
    return { placed: placed, sequence: seq.name, videoTracks: seq.videoTracks.numTracks, audioTracks: seq.audioTracks.numTracks,
             micTrack: used + 2, problems: problems };
};
TIDY.fps = function (seq) {
    var fr = TIDY.safe(function () { return seq.getSettings().videoFrameRate.seconds; }, 0);
    return fr > 0 ? 1 / fr : 30;
};

TIDY.save = function () { app.project.save(); return { path: app.project.path }; };
TIDY.open = function (a) {
    if (!new File(a.path).exists) { throw new Error('Backup not found: ' + a.path); }
    app.openDocument(a.path);
    return { opened: a.path };
};

/* ---- public entry points ---- */
function tidy_scan(s) { return TIDY.wrap(TIDY.scan, s); }
function tidy_apply(s) { return TIDY.wrap(TIDY.apply, s); }
function tidy_save(s) { return TIDY.wrap(TIDY.save, s); }
function tidy_open(s) { return TIDY.wrap(TIDY.open, s); }
function tidy_exportClipAudio(s) { return TIDY.wrap(TIDY.exportClipAudio, s); }
function tidy_buildSynced(s) { return TIDY.wrap(TIDY.buildSynced, s); }
