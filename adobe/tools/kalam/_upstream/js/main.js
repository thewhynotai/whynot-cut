/* Kalam - panel flow: mode -> target -> output -> settings -> make captions -> place in Premiere -> undo */
(function () {
    'use strict';
    var E = window.KalamEngine, C = window.KalamCEP, I = window.KalamI18n, R = window.KalamRange, t = I.t;
    var $ = function (id) { return document.getElementById(id); };
    var DEFAULTS = {
        lang: 'ar', mode: 'ar', range: 'sequence', output: 'track', mogrtPath: '', mogrtTrack: 1, mogrtField: '',
        mogrtName: '', mogrtThumb: '', mogrtFields: [],
        max_line: 32, max_lines: 2, max_dur: 4.5, min_pause: 0.22,
        correct: true, backend: 'subscription', api_key: '', rules_ar: '', rules_en: '', rules_other: '', glossary: ''
    };
    var cfg = E.loadSettings(DEFAULTS);
    var S = { info: null, chips: {}, busy: false, job: null, last: null };

    function save() { E.saveSettings(cfg); }
    function status(msg, kind) { $('status').textContent = msg || ''; $('status').className = 'tiny ' + (kind || 'muted'); }
    function fail(e) {
        var m = e && e.message ? e.message : String(e);
        E.log('ERROR ' + m);
        status(m === 'cancelled' ? t('cancelled') : m, m === 'cancelled' ? 'muted' : 'err');
    }
    function progress(text, frac) {
        $('progress').hidden = text === null;
        $('progress-text').textContent = text || '';
        $('progress-fill').style.width = Math.round((frac || 0) * 100) + '%';
    }
    function busy(on) { S.busy = on; $('go').disabled = on; $('stop').hidden = !on; }
    function fmt(sec) { var m = Math.floor(sec / 60), s = sec - m * 60; return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1); }

    /* ---------- target ---------- */
    function rangeOf(seq) {
        var r = R.rangeFor(seq, cfg.range);
        if (r.ok) { r.label = r.label === 'clips' ? t('clips', { n: r.count }) : t(r.label); }
        return r;
    }
    function refreshTarget() {
        if (S.busy) { return Promise.resolve(); }
        return C.call('info').then(function (r) {
            var seq = r.sequence;
            if (!S.chips[seq.id]) {
                S.chips[seq.id] = {};
                seq.audio.forEach(function (tr) { S.chips[seq.id][tr.index] = tr.clips > 0 && !tr.muted; });
            }
            S.info = r;
            var rg = rangeOf(seq);
            $('target').textContent = rg.ok ? rg.label + '  ' + fmt(rg.start) + '-' + fmt(rg.end) : t(rg.error);
            renderChips(); renderTracks();
        }).catch(function (e) {
            S.info = null; $('target').textContent = '-'; $('chips').innerHTML = '';
            if (/No active sequence/.test(e.message)) { status(t('noSequence')); } else { fail(e); }
        });
    }
    function renderChips() {
        var seq = S.info.sequence, st = S.chips[seq.id], box = $('chips');
        box.innerHTML = '';
        seq.audio.forEach(function (tr) {
            var b = document.createElement('button');
            b.className = 'chip' + (st[tr.index] ? ' on' : '') + (tr.clips ? '' : ' empty');
            b.textContent = 'A' + (tr.index + 1);
            b.title = tr.name;
            b.onclick = function () { st[tr.index] = !st[tr.index]; renderChips(); };
            box.appendChild(b);
        });
    }
    function renderTracks() {
        var sel = $('mogrt-track'), n = S.info ? S.info.sequence.video.length : 3, i;
        sel.innerHTML = '';
        for (i = 0; i < n; i++) { var o = document.createElement('option'); o.value = i; o.textContent = 'V' + (i + 1); sel.appendChild(o); }
        sel.value = Math.min(cfg.mogrtTrack, n - 1);
    }
    function audioChosen() {
        var st = S.chips[S.info.sequence.id], out = [];
        S.info.sequence.audio.forEach(function (tr) { if (st[tr.index]) { out.push(tr.index); } });
        return out;
    }

    /* ---------- make captions ---------- */
    var STAGE = { loading: 0.12, transcribing: 0.2, aligning: 0.55, correcting: 0.68, captions: 0.9 };
    function engineSettings() {
        var rules = cfg['rules_' + cfg.mode] || '';
        return {
            correct: !!cfg.correct, backend: cfg.backend, api_key: cfg.api_key || '', glossary: E.parseGlossary(cfg.glossary),
            rules: rules, max_line: +cfg.max_line, max_lines: +cfg.max_lines, max_dur: +cfg.max_dur, min_pause: +cfg.min_pause
        };
    }
    function srtDestination(seqName) {
        var proj = S.info.projectPath, stamp = new Date().toTimeString().slice(0, 8).replace(/:/g, '');
        var dir = proj ? E.path.join(E.path.dirname(proj), 'Kalam Captions') : E.path.join(E.HOME, 'exports');
        return E.path.join(dir, window.KalamPlatform.safeName(seqName) + ' ' + stamp + '.srt');
    }
    function go() {
        if (S.busy) { return; }
        if (!E.installed()) { status(t('setupMissing'), 'err'); return; }
        refreshTarget().then(function () {
            if (!S.info) { return; }
            var audio = audioChosen();
            if (!audio.length) { status(t('needAudio'), 'err'); return; }
            if (cfg.output === 'mogrt' && !cfg.mogrtPath) { status(t('needMogrt'), 'err'); return; }
            var seq = S.info.sequence, rg = rangeOf(seq);
            if (!rg.ok) { status(t(rg.error), 'err'); return; }
            var job = E.newJob(), wav = E.path.join(job, 'audio.wav');
            busy(true); status(''); $('result').hidden = true;
            progress(t('exporting'), 0.04);
            E.log('job ' + job + ' mode=' + cfg.mode + ' out=' + cfg.output + ' range=' + rg.start.toFixed(2) + '-' + rg.end.toFixed(2));
            setTimeout(function () {
                C.call('exportAudio', { outPath: wav, start: rg.start, end: rg.end, audioTracks: audio }).then(function (r) {
                    S.job = E.run(job, r.path, cfg.mode, engineSettings(), function (m) {
                        if (STAGE[m.stage] !== undefined) { progress(t(m.stage), STAGE[m.stage]); }
                    });
                    return S.job.promise;
                }).then(function (done) {
                    S.job = null;
                    // the saved SRT is in sequence time, so it lines up wherever it is imported at 0
                    var caps = E.readJSON(done.json), srt = E.writeText(srtDestination(seq.name), R.shiftSrt(E.readText(done.srt), rg.start));
                    progress(t('placing'), 0.95);
                    var place = Promise.resolve({});
                    if (cfg.output === 'track') { place = C.call('captionsTrack', { srtPath: srt, start: 0, name: E.path.basename(srt) }); }
                    if (cfg.output === 'mogrt') {
                        place = C.call('mogrt', { mogrtPath: cfg.mogrtPath, videoTrack: +cfg.mogrtTrack, start: rg.start, textParam: cfg.mogrtField || null,
                                                  captions: caps.map(function (c) { return { s: c.s, e: c.e, text: c.text }; }) });
                    }
                    return place.then(function () {
                        S.last = { output: cfg.output, range: rg, count: caps.length, videoTrack: +cfg.mogrtTrack, srt: srt };
                        showResult(done, caps, rg);
                        E.log('done ' + caps.length + ' captions corrected=' + done.corrected + (done.notice ? ' notice=' + done.notice : '') + ' ' + done.elapsed + 's');
                    });
                }).then(function () { progress(null); busy(false); refreshTarget(); })
                  .catch(function (e) { S.job = null; progress(null); busy(false); fail(e); });
            }, 30);
        });
    }
    function showResult(done, caps, rg) {
        $('result').hidden = false;
        $('res-count').textContent = t('done', { n: caps.length });
        var note = done.corrected ? t('corrected') : t('notCorrected');
        if (done.notice === 'no_api_key') { note = t('noKey'); } else if (done.notice === 'claude_code_missing' || /not logged in|Claude Code:/i.test(done.notice || '')) { note = t('ccMissing'); } else if (done.notice) { note = t('offline', { e: done.notice }); }
        $('res-note').textContent = '  ' + note;
        $('res-note').className = 'tiny ' + (done.corrected ? 'muted' : 'note-warn');
        var box = $('res-list'); box.innerHTML = '';
        caps.forEach(function (c) {
            var row = document.createElement('div'); row.className = 'crow';
            row.innerHTML = '<span class="t"></span><span class="x" dir="auto"></span>';
            row.firstChild.textContent = fmt(rg.start + c.s);
            row.lastChild.textContent = c.text;
            row.onclick = function () { C.call('setPlayhead', { t: rg.start + c.s }).catch(fail); };
            box.appendChild(row);
        });
    }
    function undo() {
        if (!S.last) { return; }
        if (S.last.output === 'mogrt') {
            C.call('removeClips', { videoTrack: S.last.videoTrack, from: S.last.range.start, to: S.last.range.end + 10 })
                .then(function (r) { status(t('undone', { n: r.removed }), 'ok'); S.last = null; $('result').hidden = true; }).catch(fail);
        } else if (S.last.output === 'track') {
            status(t('undoTrack'));
        }
    }

    /* ---------- controls ---------- */
    function setSeg(id, attr, value) {
        Array.prototype.forEach.call(document.querySelectorAll('#' + id + ' button'), function (b) { b.classList.toggle('active', b.getAttribute(attr) === value); });
    }
    function setMode(m) {
        cfg.mode = m; save(); setSeg('modes', 'data-mode', m);
        $('mode-model').textContent = t(m === 'ar' ? 'modelAr' : m === 'en' ? 'modelEn' : 'modelOther');
        $('rules').value = cfg['rules_' + m] || E.defaultRules(m);
    }
    function setBackend(b) {
        cfg.backend = b; save(); setSeg('backends', 'data-backend', b);
        $('key-row').hidden = b !== 'api';
        $('backend-help').textContent = t(b === 'api' ? 'backendApiHelp' : 'backendSubHelp');
    }
    function setRange(r) {
        cfg.range = R.MODES.indexOf(r) >= 0 ? r : 'sequence'; save(); setSeg('ranges', 'data-range', cfg.range);
        if (S.info) { refreshTarget(); }
    }
    function setOutput(o) { cfg.output = o; save(); setSeg('outputs', 'data-out', o); $('mogrt-opts').hidden = o !== 'mogrt'; }
    function applyLang(l) {
        cfg.lang = l; save(); I.apply(l);
        $('lang').textContent = l === 'ar' ? 'EN' : '\u0639';
        setMode(cfg.mode); setBackend(cfg.backend || 'subscription'); setSeg('ranges', 'data-range', cfg.range);
        showMogrt();
        if (S.info) { refreshTarget(); }
    }
    function wire() {
        $('lang').onclick = function () { applyLang(cfg.lang === 'ar' ? 'en' : 'ar'); };
        $('menu-btn').onclick = function (e) { e.stopPropagation(); $('menu').hidden = !$('menu').hidden; };
        document.addEventListener('click', function () { $('menu').hidden = true; });
        $('menu').onclick = function (e) {
            var act = e.target.getAttribute('data-act');
            if (act === 'open-logs') { E.openFolder(E.LOGS); }
            if (act === 'open-folder') { E.openFolder(E.HOME); }
            if (act === 'report') {
                status(t('reportSaving'));
                C.call('version').catch(function () { return {}; }).then(function (h) { return E.report(h); })
                    .then(function (p) { status(t('reportSaved', { p: p }), 'ok'); E.reveal(p); }).catch(fail);
            }
            if (act === 'reset') { var key = cfg.api_key, lang = cfg.lang; cfg = Object.assign({}, DEFAULTS, { api_key: key, lang: lang }); save(); init(); status(t('settingsReset'), 'ok'); }
        };
        Array.prototype.forEach.call(document.querySelectorAll('#modes button'), function (b) { b.onclick = function () { setMode(b.getAttribute('data-mode')); }; });
        Array.prototype.forEach.call(document.querySelectorAll('#outputs button'), function (b) { b.onclick = function () { setOutput(b.getAttribute('data-out')); }; });
        Array.prototype.forEach.call(document.querySelectorAll('#ranges button'), function (b) { b.onclick = function () { setRange(b.getAttribute('data-range')); }; });
        Array.prototype.forEach.call(document.querySelectorAll('#backends button'), function (b) { b.onclick = function () { setBackend(b.getAttribute('data-backend')); }; });
        $('mogrt-pick').onclick = openGallery;
        $('g-close').onclick = closeGallery;
        $('g-search').oninput = renderGallery;
        $('g-folder').onchange = renderGallery;
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !$('gallery').hidden) { closeGallery(); } });
        $('g-file').onclick = function () {
            var r = window.cep && window.cep.fs.showOpenDialogEx(false, false, t('gFromFile'), cfg.mogrtPath || E.TEMPLATES, ['mogrt']);
            if (!(r && r.data && r.data[0])) { return; }
            var p = r.data[0], found = window.KalamMogrt.scan(E.path.dirname(p), E.CACHE).filter(function (m) { return m.path === p; })[0];
            chooseMogrt(found || { path: p, name: E.path.basename(p, '.mogrt'), thumb: '', textFields: [] });
        };
        $('mogrt-track').onchange = function () { cfg.mogrtTrack = +this.value; save(); };
        $('mogrt-field').onchange = function () { cfg.mogrtField = this.value; save(); };
        ['max_line', 'max_lines', 'max_dur', 'min_pause'].forEach(function (k) { $(k).onchange = function () { cfg[k] = +this.value; save(); }; });
        $('correct').onchange = function () { cfg.correct = this.checked; save(); $('correct-opts').hidden = !cfg.correct; };
        $('api_key').onchange = function () { cfg.api_key = this.value.trim(); save(); };
        $('key-show').onclick = function () { $('api_key').type = $('api_key').type === 'password' ? 'text' : 'password'; };
        $('rules').onchange = function () { var v = this.value; cfg['rules_' + cfg.mode] = v.trim() === E.defaultRules(cfg.mode).trim() ? '' : v; save(); };
        $('rules-reset').onclick = function () { cfg['rules_' + cfg.mode] = ''; save(); $('rules').value = E.defaultRules(cfg.mode); };
        $('glossary').onchange = function () { cfg.glossary = this.value; save(); };
        $('go').onclick = go;
        $('stop').onclick = function () { if (S.job) { S.job.kill(); } };
        $('undo').onclick = undo;
        $('reveal').onclick = function () { if (S.last) { E.reveal(S.last.srt); } };
        var lastPoke = 0;
        function poke() { var n = Date.now(); if (n - lastPoke > 1500 && !S.busy) { lastPoke = n; refreshTarget(); } }
        document.addEventListener('mouseenter', poke);
        window.addEventListener('focus', poke);
    }
    /* ---- template gallery: every .mogrt in Premiere's Local Templates, with its thumbnail ---- */
    function fileUrl(p) { return 'file://' + encodeURI(p.replace(/\\/g, '/')).replace(/#/g, '%23').replace(/\?/g, '%3F'); }
    function openGallery() {
        $('gallery').hidden = false;
        $('g-search').value = '';
        if (S.mogrts) { renderGallery(); $('g-search').focus(); return; }
        $('g-grid').innerHTML = '';
        $('g-count').textContent = t('gLoading');
        setTimeout(function () {
            try { S.mogrts = window.KalamMogrt.scan(E.TEMPLATES, E.CACHE); } catch (e) { S.mogrts = []; E.log('templates scan failed: ' + e); }
            var sel = $('g-folder'), tops = window.KalamMogrt.topFolders(S.mogrts);
            sel.innerHTML = '';
            [''].concat(tops).forEach(function (f) { var o = document.createElement('option'); o.value = f; o.textContent = f || t('gAll'); sel.appendChild(o); });
            if (cfg.mogrtPath) { var cur = S.mogrts.filter(function (m) { return m.path === cfg.mogrtPath; })[0]; if (cur) { sel.value = cur.folder.split('/')[0]; } }
            renderGallery();
            $('g-search').focus();
        }, 30);
    }
    function closeGallery() { $('gallery').hidden = true; }
    function renderGallery() {
        var list = window.KalamMogrt.filter(S.mogrts || [], $('g-search').value, $('g-folder').value), grid = $('g-grid');
        grid.innerHTML = '';
        list.forEach(function (m) {
            var b = document.createElement('button'), img = document.createElement('img'), nm = document.createElement('span'), fd = document.createElement('span');
            b.className = 'g-card' + (m.path === cfg.mogrtPath ? ' on' : '');
            b.title = m.path;
            img.loading = 'lazy'; img.alt = '';
            if (m.thumb) { img.src = fileUrl(m.thumb); }
            nm.className = 'nm'; nm.textContent = m.name;
            fd.className = 'fd'; fd.textContent = m.folder;
            b.appendChild(img); b.appendChild(nm); b.appendChild(fd);
            b.onclick = function () { chooseMogrt(m); closeGallery(); };
            grid.appendChild(b);
        });
        $('g-count').textContent = t('gCount', { n: list.length });
    }
    function chooseMogrt(m) {
        cfg.mogrtPath = m.path; cfg.mogrtName = m.name; cfg.mogrtThumb = m.thumb || ''; cfg.mogrtFields = m.textFields || [];
        if (cfg.mogrtFields.indexOf(cfg.mogrtField) < 0) { cfg.mogrtField = ''; }
        save(); showMogrt();
    }
    function showMogrt() {
        $('mogrt-name').textContent = cfg.mogrtPath ? (cfg.mogrtName || E.path.basename(cfg.mogrtPath, '.mogrt')) : t('gNone');
        $('mogrt-thumb').hidden = !cfg.mogrtThumb;
        if (cfg.mogrtThumb) { $('mogrt-thumb').src = fileUrl(cfg.mogrtThumb); }
        var sel = $('mogrt-field');
        sel.innerHTML = '';
        [''].concat(cfg.mogrtFields || []).forEach(function (f) { var o = document.createElement('option'); o.value = f; o.textContent = f || t('gAuto'); sel.appendChild(o); });
        sel.value = cfg.mogrtField || '';
    }

    function init() {
        applyLang(cfg.lang);
        setOutput(cfg.output);
        showMogrt();
        ['max_line', 'max_lines', 'max_dur', 'min_pause'].forEach(function (k) { $(k).value = cfg[k]; });
        $('correct').checked = cfg.correct; $('correct-opts').hidden = !cfg.correct;
        $('api_key').value = cfg.api_key || '';
        $('glossary').value = cfg.glossary || '';
        progress(null); busy(false);
        refreshTarget();
    }
    wire();
    init();
    E.log('panel opened');
})();
