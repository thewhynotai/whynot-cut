/* Tidy - turn a project scan into a clean-up plan (pure). Nothing here touches Premiere or the disk.
   scan: {items:[{nodeId,name,path,isSequence,duration,bin,exists,offline,size,color}],
          bins:[{nodeId,path}], usage:{sequenceNodeId:[nodeIds its clips reference]}}
   opts: {unchecked:{nodeId:true}, checked:{nodeId:true}, mode:'reels'|'podcast'} - removals the user unticked / ticked */
(function (root) {
    'use strict';
    var C = root.TidyClassify, P = {};
    P.BACKUP = /\((Hush backup|Hush cut) /;

    function addPath(set, path) {
        var parts = String(path).split('/'), i;
        for (i = 1; i <= parts.length; i++) { set[parts.slice(0, i).join('/')] = true; }
    }

    P.build = function (scan, opts) {
        opts = opts || {};
        var unchecked = opts.unchecked || {}, forced = opts.checked || {}, items = scan.items, usage = scan.usage || {};
        var byId = {}, i, j, it;
        for (i = 0; i < items.length; i++) { byId[items[i].nodeId] = items[i]; }

        // sequences that stay, and everything they use (Hush/Kalam backups do not count)
        var backup = {}, used = {}, nestIds = {};
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (it.isSequence && P.BACKUP.test(it.name)) { backup[it.nodeId] = true; }
        }
        for (var sid in usage) {
            if (!usage.hasOwnProperty(sid) || backup[sid]) { continue; }
            for (j = 0; j < usage[sid].length; j++) {
                used[usage[sid][j]] = true;
                if (byId[usage[sid][j]] && byId[usage[sid][j]].isSequence) { nestIds[usage[sid][j]] = true; }
            }
        }
        var ctx = { nestIds: nestIds, mode: opts.mode === 'podcast' ? 'podcast' : 'reels', camNumbers: C.cameraNumbers(items) };

        // duplicates: several clip items pointing at the same file
        var byPath = {}, dupOf = {}, duplicates = [];
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (it.isSequence || !it.path) { continue; }
            (byPath[it.path] = byPath[it.path] || []).push(it);
        }
        for (var path in byPath) {
            if (!byPath.hasOwnProperty(path) || byPath[path].length < 2) { continue; }
            var group = byPath[path], usedCopies = [];
            for (j = 0; j < group.length; j++) { if (used[group[j].nodeId]) { usedCopies.push(group[j]); } }
            if (usedCopies.length > 1) {
                duplicates.push({ path: path, name: group[0].name, copies: group.length, used: usedCopies.length });
            } else if (usedCopies.length === 1) {
                for (j = 0; j < group.length; j++) { if (!used[group[j].nodeId]) { dupOf[group[j].nodeId] = usedCopies[0].nodeId; } }
            }
        }

        var removals = [], moves = [], colors = [], offline = [], gone = {}, keep = {}, stats = { removeCount: 0, removeSize: 0, totalSize: 0, byType: {} };
        for (i = 0; i < items.length; i++) {
            it = items[i];
            var cat = C.category(it, ctx);
            stats.byType[cat] = (stats.byType[cat] || 0) + 1;
            stats.totalSize += it.size || 0;
            if (it.path && (it.offline || it.exists === false)) { offline.push({ nodeId: it.nodeId, name: it.name, path: it.path, used: !!used[it.nodeId] }); }
            var reason = null;
            if (it.isSequence) { reason = backup[it.nodeId] ? 'backup' : null; }
            else if (!used[it.nodeId]) { reason = dupOf[it.nodeId] ? 'duplicate' : 'unused'; }
            if (reason) {
                // captions: Premiere cannot say which are in use; podcast footage and mics: raw material for the sync
                var longRec = it.duration >= C.MIC_MIN && /^(footage|mics|renders|voice)$/.test(cat);
                var optIn = cat === 'captions' || (ctx.mode === 'podcast' && (cat === 'footage' || cat === 'mics' || longRec));
                var checked = !unchecked[it.nodeId] && (!optIn || !!forced[it.nodeId]);
                removals.push({ nodeId: it.nodeId, name: it.name, reason: reason, category: cat, size: it.size || 0, checked: checked });
                if (checked) { gone[it.nodeId] = true; stats.removeCount++; stats.removeSize += it.size || 0; continue; }
            }
            var to = C.binFor(cat, it, ctx);
            addPath(keep, to);
            if (it.bin !== to) { moves.push({ nodeId: it.nodeId, name: it.name, from: it.bin, to: to }); }
            if (it.color !== C.COLORS[cat]) { colors.push({ nodeId: it.nodeId, color: C.COLORS[cat] }); }
        }

        // every kept item ends up in its bin, so the old bins empty out; only bins something goes into stay
        var emptyBins = [];
        for (i = 0; i < (scan.bins || []).length; i++) {
            if (!keep[scan.bins[i].path]) { emptyBins.push({ nodeId: scan.bins[i].nodeId, path: scan.bins[i].path }); }
        }
        emptyBins.sort(function (a, b) { return b.path.split('/').length - a.path.split('/').length; });   // deepest first

        // nests are named after what they hold: their text, else an image, else the first clip
        var renames = [], taken = {}, texts = scan.texts || {}, noRename = opts.noRename || {};
        for (i = 0; i < items.length; i++) { if (items[i].isSequence && !nestIds[items[i].nodeId]) { taken[items[i].name] = true; } }
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (!it.isSequence || !nestIds[it.nodeId] || gone[it.nodeId]) { continue; }
            var to = P.nestName(it, texts[it.nodeId] || [], usage[it.nodeId] || [], byId);
            if (!to) { taken[it.name] = true; continue; }
            var base = to, n = 2;
            while (taken[to]) { to = base + ' ' + n++; }
            taken[to] = true;
            if (to !== it.name) { renames.push({ nodeId: it.nodeId, from: it.name, to: to, checked: !noRename[it.nodeId] }); }
        }

        return { removals: removals, moves: moves, colors: colors, duplicates: duplicates, offline: offline,
                 emptyBins: emptyBins, renames: renames, stats: stats };
    };

    P.NAME_MAX = 50;
    function clean(s) {
        s = String(s || '').replace(/[\s\u00a0]+/g, ' ').replace(/^ | $/g, '');
        return s.length > P.NAME_MAX ? s.slice(0, P.NAME_MAX).replace(/ \S*$/, '') : s;
    }
    function bare(name) { return clean(String(name || '').replace(/\.[A-Za-z0-9]{2,5}$/, '')); }
    P.IMAGE = /\.(png|jpe?g|gif|webp|psd|tiff?|heic|svg|ai|eps|bmp)$/i;
    /* text first, then an image, then any clip (nested sequences last) */
    P.nestName = function (nest, texts, usedIds, byId) {
        var i, t, it, firstClip = '', firstSeq = '';
        for (i = 0; i < texts.length; i++) { t = clean(texts[i]); if (t) { return t; } }
        for (i = 0; i < usedIds.length; i++) {
            it = byId[usedIds[i]];
            if (!it) { continue; }
            if (!it.isSequence && P.IMAGE.test(it.path || '')) { return bare(it.name); }
            if (!it.isSequence && !firstClip) { firstClip = bare(it.name); }
            if (it.isSequence && !firstSeq) { firstSeq = clean(it.name); }
        }
        return firstClip || firstSeq || '';
    };

    root.TidyPlan = P;
})(typeof window !== 'undefined' ? window : this);
