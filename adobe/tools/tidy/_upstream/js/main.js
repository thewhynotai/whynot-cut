/* Tidy - panel flow: scan -> preview (ticks, sizes) -> confirm -> save + backup -> apply -> report -> undo */
(function () {
    'use strict';
    var E = window.TidyEngine, C = window.TidyCEP, I = window.TidyI18n, P = window.TidyPlan, K = window.TidyClassify, Y = window.TidySync, t = I.t;
    var $ = function (id) { return document.getElementById(id); };
    var cfg = E.loadSettings({ lang: 'ar', remove: true, organize: true, colors: true, mode: 'reels' });
    var S = { scan: null, plan: null, unchecked: {}, checked: {}, noRename: {}, busy: false, backup: null };

    function save() { E.saveSettings(cfg); }
    function status(msg, kind) { $('status').textContent = msg || ''; $('status').className = 'tiny ' + (kind || 'muted'); }
    function fail(e) { var m = e && e.message ? e.message : String(e); E.log('ERROR ' + m); status(m, 'err'); }
    function el(tag, cls, text) { var x = document.createElement(tag); if (cls) { x.className = cls; } if (text !== undefined) { x.textContent = text; } return x; }

    function scan() {
        if (S.busy) { return; }
        S.busy = true; status(t('scanning')); $('report').hidden = true; $('confirm').hidden = true;
        C.call('scan').then(function (r) {
            S.busy = false;
            E.diskInfo(r.items);
            E.sniff(r.items);
            var tx = {}, sid, j;   // graphic text per sequence (raw "Source Text" pieces from the host)
            for (sid in r.texts || {}) {
                if (r.texts.hasOwnProperty(sid)) { tx[sid] = []; for (j = 0; j < r.texts[sid].length; j++) { tx[sid].push(window.TidyMedia.textFromValue('{' + r.texts[sid][j])); } }
            }
            r.texts = tx;
            S.scan = r; S.unchecked = {}; S.checked = {}; S.noRename = {};
            $('project-name').textContent = r.name || '-';
            replan();
            status('');
            E.log('scan ' + r.project + ': ' + r.items.length + ' items, ' + r.bins.length + ' bins');
        }).catch(function (e) { S.busy = false; fail(/No project/.test(e.message) ? new Error(t('noProject')) : e); });
    }

    function replan() {
        S.plan = P.build(S.scan, { unchecked: S.unchecked, checked: S.checked, noRename: S.noRename, mode: cfg.mode });
        render();
    }

    function render() {
        var p = S.plan, st = p.stats;
        $('summary').hidden = $('details').hidden = $('actions').hidden = false;
        $('st-items').textContent = S.scan.items.length;
        $('st-size').textContent = E.size(st.totalSize);
        $('st-remove').textContent = st.removeCount;
        $('st-free').textContent = st.totalSize ? Math.round(100 * st.removeSize / st.totalSize) + '% (' + E.size(st.removeSize) + ')' : '0';
        var parts = []; for (var k in st.byType) { if (st.byType.hasOwnProperty(k)) { parts.push(K.BINS[k].replace(/^\d+ /, '') + ': ' + st.byType[k]); } }
        $('by-type').textContent = parts.join('  \u00b7  ');

        // removals grouped by reason
        var box = $('list-remove'); box.innerHTML = '';
        var groups = [['unused', 'rUnused'], ['duplicate', 'rDuplicate'], ['backup', 'rBackup'], ['captions', 'rCaptions']];
        groups.forEach(function (g) {
            var rows = p.removals.filter(function (r) { return g[0] === 'captions' ? r.category === 'captions' : (r.reason === g[0] && r.category !== 'captions'); });
            if (!rows.length) { return; }
            box.appendChild(el('div', 'group', t(g[1]) + ' (' + rows.length + ')'));
            rows.forEach(function (r) {
                var row = el('label', 'item'), cb = el('input');
                cb.type = 'checkbox'; cb.checked = r.checked;
                cb.onchange = function () {
                    if (cb.checked) { delete S.unchecked[r.nodeId]; S.checked[r.nodeId] = true; }
                    else { S.unchecked[r.nodeId] = true; delete S.checked[r.nodeId]; }
                    replan();
                };
                row.appendChild(cb); row.appendChild(el('span', 'n', r.name)); row.appendChild(el('span', 'm', r.size ? E.size(r.size) : ''));
                row.title = r.name;
                box.appendChild(row);
            });
        });
        $('n-remove').textContent = st.removeCount + ' / ' + p.removals.length;

        // moves summarised by target bin
        var mv = {}; p.moves.forEach(function (m) { (mv[m.to] = mv[m.to] || []).push(m.name); });
        box = $('list-move'); box.innerHTML = '';
        Object.keys(mv).sort().forEach(function (to) {
            box.appendChild(el('div', 'group', to + ' (' + mv[to].length + ')'));
            mv[to].slice(0, 50).forEach(function (n) { var r = el('div', 'item plain'); r.appendChild(el('span', 'n', n)); box.appendChild(r); });
        });
        $('n-move').textContent = p.moves.length;

        box = $('list-bins'); box.innerHTML = '';
        p.emptyBins.forEach(function (b) { var r = el('div', 'item plain'); r.appendChild(el('span', 'n', b.path)); box.appendChild(r); });
        $('n-bins').textContent = p.emptyBins.length;

        box = $('list-ren'); box.innerHTML = '';
        p.renames.forEach(function (r) {
            var row = el('label', 'item'), cb = el('input');
            cb.type = 'checkbox'; cb.checked = r.checked;
            cb.onchange = function () { if (cb.checked) { delete S.noRename[r.nodeId]; } else { S.noRename[r.nodeId] = true; } replan(); };
            row.appendChild(cb); row.appendChild(el('span', 'n', r.to)); row.appendChild(el('span', 'm', r.from));
            row.title = r.from + '  \u2192  ' + r.to;
            box.appendChild(row);
        });
        $('n-ren').textContent = p.renames.filter(function (r) { return r.checked; }).length + ' / ' + p.renames.length;

        box = $('list-dup'); box.innerHTML = '';
        p.duplicates.forEach(function (d) { var r = el('div', 'item plain'); r.appendChild(el('span', 'n', d.name)); r.appendChild(el('span', 'm', t('copies', { n: d.copies }) + ' \u00b7 ' + d.used + ' ' + t('used'))); r.title = d.path; box.appendChild(r); });
        $('n-dup').textContent = p.duplicates.length;

        box = $('list-off'); box.innerHTML = '';
        p.offline.forEach(function (o) { var r = el('div', 'item plain'); r.appendChild(el('span', 'n', o.name)); r.appendChild(el('span', 'm', o.used ? t('used') : t('notUsed'))); r.title = o.path; box.appendChild(r); });
        $('n-off').textContent = p.offline.length;
    }

    /* what the host will be asked to do, after the three options */
    function job() {
        var p = S.plan, removals = cfg.remove ? p.removals.map(function (r) {
            return { nodeId: r.nodeId, name: r.name, checked: r.checked };
        }) : [];
        return { removals: removals, moves: cfg.organize ? p.moves : [], emptyBins: cfg.organize ? p.emptyBins : [], colors: cfg.colors ? p.colors : [],
                 renames: cfg.organize ? p.renames : [] };
    }

    function askApply() {
        var j = job(), r = j.removals.filter(function (x) { return x.checked; }).length;
        var rn = j.renames.filter(function (x) { return x.checked; }).length;
        if (!r && !j.moves.length && !j.emptyBins.length && !j.colors.length && !rn) { status(t('nothing'), 'ok'); return; }
        $('confirm-text').textContent = t('confirmText', { r: r, m: j.moves.length, b: j.emptyBins.length });
        $('confirm').hidden = false;
    }

    function apply() {
        $('confirm').hidden = true;
        if (S.busy) { return; }
        var j = job();
        S.busy = true; status(t('applying'));
        C.call('save').then(function (s) {
            if (!s.path) { throw new Error(t('unsaved')); }
            S.backup = E.backup(s.path);
            E.log('backup ' + S.backup);
            return C.call('apply', j);
        }).then(function (res) {
            S.busy = false;
            var msg = t('done', { r: res.removed, m: res.moved, b: res.binsRemoved, c: res.colored });
            if (res.renamed) { msg += ' ' + t('renamed', { n: res.renamed }); }
            if (res.skipped) { msg += ' ' + t('skipped', { s: res.skipped }); }
            if (res.problems && res.problems.length > res.skipped) { msg += ' ' + t('problems', { n: res.problems.length - res.skipped }); }
            $('report').hidden = false;
            $('report').textContent = msg + '  ' + t('backupAt', { p: S.backup });
            $('undo').hidden = false;
            E.log('apply ' + JSON.stringify(res));
            status('', 'ok');
            scan();
        }).catch(function (e) { S.busy = false; fail(e); });
    }

    /* podcast: export each camera clip and mic recording's sound, find where each sits, build one synced sequence */
    function syncPodcast() {
        if (S.busy || !S.scan) { return; }
        var items = S.scan.items, cams = K.cameraNumbers(items), ctx = { mode: 'podcast', camNumbers: cams, nestIds: {} };
        var roles = {}, list = [], names = {}, paths = {}, i;
        for (i = 0; i < items.length; i++) {
            var it = items[i], cat = K.category(it, ctx);
            if (it.exists === false || paths[it.path]) { continue; }    // one copy per file
            if (cat === 'footage' || cat === 'mics') { paths[it.path] = true; }
            if (cat === 'footage') { roles[it.nodeId] = { role: 'cam', cam: cams[it.camId] || 1 }; list.push(it); }
            if (cat === 'mics') { roles[it.nodeId] = { role: 'mic' }; list.push(it); }
            names[it.nodeId] = it.name;
        }
        if (list.length < 2) { status(t('syncNeedTwo'), 'err'); return; }
        S.busy = true;
        var tracks = [], k = 0, failed = [];
        function next() {
            if (k >= list.length) { return Promise.resolve(); }
            var it = list[k++], out = E.tempWav('clip-' + k);
            status(t('syncExport', { i: k, n: list.length, name: it.name }));
            return C.call('exportClipAudio', { nodeId: it.nodeId, outPath: out }).then(function (r) {
                var env = Y.fromPower(E.wavPower(r.path));
                E.removeFile(r.path);
                env.id = it.nodeId;
                roles[it.nodeId].seconds = env.seconds;
                tracks.push(env);
            }).catch(function (e) {                       // e.g. a camera clip without sound: leave it out, go on
                E.log('sync export failed ' + it.name + ': ' + (e && e.message));
                failed.push(it.nodeId);
            }).then(next);
        }
        next().then(function () {
            status(t('syncMatch'));
            var plan = Y.plan(tracks), lay = Y.layout(plan, roles);
            lay.skipped = lay.skipped.concat(failed);
            E.log('sync ' + JSON.stringify(plan));
            var first = null, best = -1;   // the new sequence takes Cam 1's settings (its longest clip)
            lay.cams.forEach(function (c) { if (c.track === 0 && (roles[c.nodeId].seconds || 0) > best) { best = roles[c.nodeId].seconds || 0; first = c.nodeId; } });
            if (!lay.cams.length && !lay.mics.length) { throw new Error(t('syncNothing')); }
            return C.call('buildSynced', { name: (S.scan.name || 'Podcast').replace(/\.prproj$/, '') + ' - Synced', cams: lay.cams, mics: lay.mics,
                                           first: first, bin: '06 Sequences' })
                .then(function (res) {
                    S.busy = false;
                    var msg = t('syncDone', { n: res.placed, seq: res.sequence });
                    if (res.problems && res.problems.length) { E.log('sync problems ' + JSON.stringify(res.problems)); msg += ' ' + t('problems', { n: res.problems.length }); }
                    if (lay.skipped.length) { msg += ' ' + t('syncSkipped', { list: lay.skipped.map(function (id) { return names[id]; }).join('، ') }); }
                    $('report').hidden = false; $('report').textContent = msg; status('', 'ok');
                });
        }).catch(function (e) { S.busy = false; fail(e); });
    }

    function undo() {
        if (!S.backup) { return; }
        C.call('open', { path: S.backup }).then(function () { status(t('opened'), 'ok'); }).catch(fail);
    }

    function wire() {
        $('lang').onclick = function () { cfg.lang = cfg.lang === 'ar' ? 'en' : 'ar'; save(); I.apply(cfg.lang); $('lang').textContent = cfg.lang === 'ar' ? 'EN' : '\u0639'; if (S.plan) { render(); } };
        $('menu-btn').onclick = function (e) { e.stopPropagation(); $('menu').hidden = !$('menu').hidden; };
        document.addEventListener('click', function () { $('menu').hidden = true; });
        $('menu').onclick = function (e) {
            var a = e.target.getAttribute('data-act');
            if (a === 'open-logs') { E.openFolder(E.LOGS); }
            if (a === 'open-folder') { E.openFolder(E.HOME); }
        };
        $('scan').onclick = scan;
        function showMode() {
            var bs = document.querySelectorAll('#mode button'), i;
            for (i = 0; i < bs.length; i++) { bs[i].className = bs[i].getAttribute('data-mode') === cfg.mode ? 'on' : ''; }
        }
        $('mode').onclick = function (e) {
            var m = e.target.getAttribute('data-mode');
            if (!m || m === cfg.mode) { return; }
            cfg.mode = m; save(); showMode();
            $('sync').hidden = cfg.mode !== 'podcast';
            if (S.scan) { replan(); }
        };
        showMode();
        $('sync').hidden = cfg.mode !== 'podcast';
        $('apply').onclick = askApply;
        $('confirm-yes').onclick = apply;
        $('confirm-no').onclick = function () { $('confirm').hidden = true; };
        $('undo').onclick = undo;
        $('sync').onclick = syncPodcast;
        [['opt-remove', 'remove'], ['opt-organize', 'organize'], ['opt-colors', 'colors']].forEach(function (o) {
            $(o[0]).checked = cfg[o[1]];
            $(o[0]).onchange = function () { cfg[o[1]] = this.checked; save(); };
        });
    }

    wire();
    I.apply(cfg.lang);
    $('lang').textContent = cfg.lang === 'ar' ? 'EN' : '\u0639';
    E.log('panel opened');
})();
