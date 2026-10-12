/* Hush - panel UI and flow: target -> scan -> tune -> cut / markers -> undo */
(function () {
    'use strict';
    var D = window.HushDetect, F = window.HushFillers, E = window.HushEngine, C = window.HushCEP, I = window.HushI18n;
    var $ = function (id) { return document.getElementById(id); };
    var t = I.t;

    var DEFAULTS = {
        lang: 'en', tab: 'simple', intensity: 50, mode: 'cut', ripple: true, backup: true, link: true, tight: true, padLink: true,
        adv: { threshold: -45, minSilence: 0.5, padBefore: 0.12, padAfter: 0.12 },
        fillersOn: false, fillerLang: 'auto', soundsOn: false,
        listStrong: F.DEFAULT_STRONG, listSoft: F.DEFAULT_SOFT
    };
    var cfg = Object.assign({}, DEFAULTS, E.readJSON('settings.json', {}));
    cfg.adv = Object.assign({}, DEFAULTS.adv, cfg.adv || {});
    var presets = E.readJSON('presets.json', []);

    // scan state
    var S = { info: null, range: null, chips: {}, env: null, stats: null, duration: 0, wav: null,
              words: null, fillers: [], plan: null, busy: false, job: null, lastCut: null };

    function save() { E.writeJSON('settings.json', cfg); }
    function status(msg, kind) { var el = $('status'); el.textContent = msg || ''; el.className = 'tiny ' + (kind || 'muted'); }
    function fail(e) {
        var m = e && e.message ? e.message : String(e);
        E.log('ERROR ' + m);
        status(m === 'cancelled' ? t('cancelled') : m, m === 'cancelled' ? 'muted' : 'err');
    }
    function progress(text, frac) {
        $('progress').hidden = text === null;
        $('progress-text').textContent = text || '';
        var f = $('progress-fill');
        if (frac === undefined) { f.className = 'indeterminate'; f.style.width = ''; }
        else { f.className = ''; f.style.width = Math.round(frac * 100) + '%'; }
    }
    function busy(on) {
        S.busy = on;
        $('scan').disabled = on;
        $('go').disabled = on || !S.plan || !S.plan.cuts.length;
        $('stop').hidden = !on;
    }

    /* ---------- target & tracks ---------- */
    function rangeOf(seq) {
        if (seq.selection.length) {
            var s = Infinity, e = -Infinity;
            seq.selection.forEach(function (c) { s = Math.min(s, c.start); e = Math.max(e, c.end); });
            var n = {}; seq.selection.forEach(function (c) { n[c.name + c.start] = 1; });
            return { start: s, end: e, label: t('clips', { n: Object.keys(n).length }) };
        }
        if (seq.inPoint >= 0 && seq.outPoint > seq.inPoint) { return { start: seq.inPoint, end: seq.outPoint, label: t('inOut') }; }
        return { start: 0, end: seq.end, label: t('wholeSeq') };
    }
    function refreshTarget() {
        if (S.busy) { return Promise.resolve(); }
        return C.call('info').then(function (r) {
            var seq = r.sequence, key = seq.id;
            if (!S.chips[key]) {
                S.chips[key] = {};
                seq.video.concat(seq.audio).forEach(function (tr) { S.chips[key][tr.kind + tr.index] = tr.clips > 0 && !tr.locked; });
            }
            S.info = r;
            var rg = rangeOf(seq);
            $('target').textContent = rg.label + '  ' + D.fmt(rg.start) + '-' + D.fmt(rg.end);
            renderChips();
        }).catch(function (e) {
            S.info = null;
            $('target').textContent = '-';
            $('chips').innerHTML = '';
            if (/No active sequence/.test(e.message)) { status(t('noSequence')); } else { fail(e); }
        });
    }
    function chipState() { return S.info ? S.chips[S.info.sequence.id] : {}; }
    function renderChips() {
        var seq = S.info.sequence, st = chipState(), box = $('chips');
        box.innerHTML = '';
        seq.video.concat(seq.audio).forEach(function (tr) {
            var b = document.createElement('button'), id = tr.kind + tr.index;
            b.className = 'chip' + (st[id] ? ' on' : '') + (tr.clips ? '' : ' empty');
            b.textContent = (tr.kind === 'video' ? 'V' : 'A') + (tr.index + 1);
            b.title = tr.name + (tr.locked ? ' (locked)' : '');
            b.onclick = function () { st[id] = !st[id]; renderChips(); if (S.plan) { invalidateScan(); } };
            box.appendChild(b);
        });
        var off = seq.video.concat(seq.audio).filter(function (tr) { return tr.clips > 0 && !st[tr.kind + tr.index]; })
            .map(function (tr) { return (tr.kind === 'video' ? 'V' : 'A') + (tr.index + 1); });
        $('track-warn').hidden = !(cfg.ripple && cfg.mode === 'cut' && off.length);
        $('track-warn').textContent = t('trackWarn', { t: off.join(', ') });
    }
    function chosen(kind) {
        var st = chipState(), out = [];
        (S.info.sequence[kind] || []).forEach(function (tr) { if (st[kind + tr.index]) { out.push(tr.index); } });
        return out;
    }

    /* ---------- scan ---------- */
    function invalidateScan(msg) {
        S.env = null; S.plan = null; S.fillers = []; S.words = null;
        renderFillers(); draw(); summary();
        $('go').disabled = true;
        if (msg) { status(msg); }
    }
    function scan() {
        if (S.busy) { return; }
        refreshTarget().then(function () {
            if (!S.info) { return; }
            var audio = chosen('audio');
            if (!audio.length) { status(t('needAudio'), 'err'); return; }
            var rg = rangeOf(S.info.sequence);
            busy(true); status('');
            progress(t('exporting'));
            // let the progress bar paint before Premiere blocks on the export
            setTimeout(function () {
                E.scanAudio(rg, audio).then(function (r) {
                    S.range = rg; S.env = r.env; S.duration = r.duration; S.wav = r.wav;
                    S.stats = D.stats(r.env);
                    S.fillers = []; S.words = null;
                    if (cfg.tab === 'simple' || !cfg.advTouched) { syncAdvFromSimple(); }
                    progress(t('analyzing'));
                    if (!cfg.fillersOn) { return null; }
                    if (!E.hasWhisper()) { throw new Error(t('whisperMissing')); }
                    S.job = E.transcribe(r.wav, cfg.fillerLang, function (stage) {
                        progress(stage === 'loading' ? t('loadingModel') : t('transcribing'));
                    });
                    return S.job.promise.then(function (res) { S.words = res.words; E.log('whisper ' + res.words.length + ' words, ' + res.language + ', ' + res.elapsed + 's'); });
                }).then(function () {
                    S.job = null;
                    findFillers();
                    replan();
                    progress(null); busy(false);
                    status(t('ready', { n: S.plan.cuts.length }), 'ok');
                }).catch(function (e) { S.job = null; progress(null); busy(false); fail(e); replan(); });
            }, 30);
        });
    }

    function findFillers() {
        S.fillers = [];
        if (!S.words || !cfg.fillersOn) { renderFillers(); return; }
        var found = F.find(S.words, cfg.listStrong, cfg.listSoft);
        if (cfg.soundsOn) {
            found = found.concat(F.untranscribed(S.env, D.HOP, currentSettings().threshold, S.words, 0.15, 1.2));
        }
        found.sort(function (a, b) { return a.s - b.s; });
        S.fillers = found;
        renderFillers();
    }
    function renderFillers() {
        var box = $('filler-list');
        box.innerHTML = '';
        if (!cfg.fillersOn || !S.words) { return; }
        if (!S.fillers.length) { box.innerHTML = '<div class="muted tiny" style="padding:6px 2px">' + t('noFillers') + '</div>'; return; }
        S.fillers.forEach(function (f) {
            var row = document.createElement('div'); row.className = 'frow';
            var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = f.on;
            cb.onchange = function () { f.on = cb.checked; replan(); };
            var w = document.createElement('span'); w.className = 'w' + (f.source === 'sound' ? ' sound' : ''); w.textContent = f.label; w.dir = 'auto';
            var tm = document.createElement('span'); tm.className = 't'; tm.textContent = D.fmt(S.range.start + f.s);
            var pl = document.createElement('button'); pl.innerHTML = '&#9654;'; pl.title = 'Show in timeline';
            pl.onclick = function () { C.call('setPlayhead', { t: S.range.start + Math.max(0, f.s - 0.5) }).catch(fail); };
            row.appendChild(cb); row.appendChild(w); row.appendChild(tm); row.appendChild(pl);
            box.appendChild(row);
        });
    }

    /* ---------- settings -> plan ---------- */
    function currentSettings() {
        if (cfg.tab === 'simple' && S.stats) {
            var st = D.fromIntensity(cfg.intensity, S.stats);
            if (cfg.tight) { st.padBefore = 0; st.padAfter = 0; }
            return st;
        }
        return cfg.adv;
    }
    function syncAdvFromSimple() {
        if (!S.stats) { return; }
        var s = D.fromIntensity(cfg.intensity, S.stats);
        if (cfg.tight) { s.padBefore = 0; s.padAfter = 0; }
        cfg.adv = { threshold: s.threshold, minSilence: s.minSilence, padBefore: s.padBefore, padAfter: s.padAfter };
        renderAdv();
    }
    function replan() {
        if (!S.env) { S.plan = null; draw(); summary(); return; }
        var fl = S.fillers.filter(function (f) { return f.on; });
        S.plan = D.plan(S.env, currentSettings(), fl, S.duration, S.info.sequence.fps);
        draw(); summary();
        $('go').disabled = S.busy || !S.plan.cuts.length;
    }
    function summary() {
        var p = S.plan;
        $('sum-before').textContent = p ? D.fmt(p.before) : '-';
        $('sum-after').textContent = p ? D.fmt(p.after) : '-';
        $('sum-saved').textContent = p ? D.fmt(p.removed) : '-';
        if (!p) { $('recap').textContent = ''; return; }
        var f = p.cuts.filter(function (c) { return c.kind === 'filler'; }).length;
        $('recap').textContent = t('cutsN', { s: p.cuts.length - f, f: f });
        var st = currentSettings();
        $('simple-readout').textContent = st.threshold + ' dB  |  ' + Math.round(st.minSilence * 1000) + ' ms min  |  ' +
            Math.round(st.padBefore * 1000) + '/' + Math.round(st.padAfter * 1000) + ' ms pad';
    }

    /* ---------- waveform ---------- */
    var cv = $('wave'), ctx = cv.getContext('2d');
    function draw() {
        var dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
        cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, W, H);
        $('wave-ph').hidden = !!S.env;
        if (!S.env) { return; }
        var env = S.env, n = env.length, per = n / W, x, i, a, b, m, y;
        function yOf(db) { return H - Math.max(0, Math.min(1, (db + 72) / 72)) * (H - 4); }
        if (S.plan) {
            S.plan.cuts.forEach(function (c) {
                ctx.fillStyle = c.kind === 'filler' ? 'rgba(255,184,64,.40)' : 'rgba(255,92,92,.30)';
                var x0 = c.s / S.duration * W, x1 = c.e / S.duration * W;
                ctx.fillRect(x0, 0, Math.max(1, x1 - x0), H);
            });
        }
        ctx.fillStyle = '#7d7d88';
        for (x = 0; x < W; x++) {
            a = Math.floor(x * per); b = Math.max(a + 1, Math.floor((x + 1) * per)); m = -100;
            for (i = a; i < b && i < n; i++) { if (env[i] > m) { m = env[i]; } }
            y = yOf(m);
            ctx.fillRect(x, y, 1, H - y);
        }
        var th = yOf(currentSettings().threshold);
        ctx.strokeStyle = 'rgba(169,157,255,.9)'; ctx.setLineDash([3, 3]); ctx.beginPath();
        ctx.moveTo(0, th + 0.5); ctx.lineTo(W, th + 0.5); ctx.stroke(); ctx.setLineDash([]);
    }
    function waveTime(ev) { var r = cv.getBoundingClientRect(); return Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * S.duration; }
    cv.addEventListener('mousemove', function (ev) {
        if (!S.env) { return; }
        var tt = waveTime(ev), tip = $('wave-tip'), db = S.env[Math.min(S.env.length - 1, Math.floor(tt / D.HOP))];
        var inCut = S.plan && S.plan.cuts.filter(function (c) { return tt >= c.s && tt <= c.e; })[0];
        tip.hidden = false;
        tip.textContent = D.fmt(S.range.start + tt) + '  ' + db.toFixed(0) + ' dB' + (inCut ? '  ' + (inCut.kind === 'filler' ? (inCut.label || 'filler') : 'cut') : '');
        var r = cv.getBoundingClientRect();
        tip.style.left = Math.min(r.width - tip.offsetWidth - 4, Math.max(4, ev.clientX - r.left + 8)) + 'px';
    });
    cv.addEventListener('mouseleave', function () { $('wave-tip').hidden = true; });
    cv.addEventListener('click', function (ev) { if (S.env) { C.call('setPlayhead', { t: S.range.start + waveTime(ev) }).catch(fail); } });
    window.addEventListener('resize', draw);

    /* ---------- go / undo ---------- */
    function go() {
        if (!S.plan || !S.plan.cuts.length || S.busy) { status(t('noScan')); return; }
        var off = S.range.start;
        if (cfg.mode === 'markers') {
            busy(true);
            C.call('markers', { ranges: S.plan.cuts.map(function (c) { return { s: off + c.s, e: off + c.e, kind: c.kind, label: c.label || '' }; }) })
                .then(function (r) { busy(false); status(t('markersDone', { n: r.added }), 'ok'); })
                .catch(function (e) { busy(false); fail(e); });
            return;
        }
        var args = {
            cuts: S.plan.cuts.map(function (c) { return [off + c.s, off + c.e]; }),
            video: chosen('video'), audio: chosen('audio'), ripple: cfg.ripple, backup: cfg.backup, link: cfg.link
        };
        var removed = S.plan.removed;
        busy(true);
        progress(t('cutting', { n: args.cuts.length }));
        E.log('cut ' + args.cuts.length + ' ranges on V' + args.video.join(',') + ' A' + args.audio.join(',') + ' ripple=' + args.ripple + ' backup=' + args.backup);
        setTimeout(function () {
            C.call('cut', args).then(function (r) {
                E.log('cut done: removed ' + r.removed + ' items, backup ' + (r.backup ? r.backup.name : 'none') + ', link ' + JSON.stringify(r.linked));
                S.lastCut = r.backup ? { backupId: r.backup.id, cutId: r.sequenceId, originalName: r.sequence } : null;
                $('undo').disabled = false;
                progress(null); busy(false);
                invalidateScan();
                status(t('cutDone', { n: r.cuts, t: D.fmt(cfg.ripple ? removed : 0) }), 'ok');
                refreshTarget();
            }).catch(function (e) { progress(null); busy(false); fail(e); });
        }, 30);
    }
    function undo() {
        if (!S.lastCut) { status(t('noBackup')); return; }
        C.call('restore', S.lastCut).then(function (r) {
            status(t('undone', { name: r.restored }), 'ok');
            S.lastCut = null; $('undo').disabled = true;
            invalidateScan(); refreshTarget();
        }).catch(fail);
    }
    function stop() { if (S.job) { S.job.kill(); } }

    /* ---------- controls ---------- */
    function setTab(tab) {
        cfg.tab = tab; save();
        Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === tab); });
        $('pane-simple').hidden = tab !== 'simple';
        $('pane-adv').hidden = tab !== 'adv';
        if (tab === 'adv' && !cfg.advTouched) { syncAdvFromSimple(); }
        replan();
    }
    function setIntensity(v) {
        cfg.intensity = Math.max(0, Math.min(100, Math.round(v)));
        $('intensity').value = cfg.intensity; $('intensity-val').textContent = cfg.intensity;
        Array.prototype.forEach.call(document.querySelectorAll('#levels button'), function (b) {
            b.classList.toggle('active', D.SIMPLE[b.getAttribute('data-level')] === cfg.intensity);
        });
        cfg.advTouched = false;
        save(); replan();
    }
    var ADV = [['adv-db', 'threshold', 1], ['adv-min', 'minSilence', 1000], ['adv-pb', 'padBefore', 1000], ['adv-pa', 'padAfter', 1000]];
    function renderAdv() {
        ADV.forEach(function (a) { var v = Math.round(cfg.adv[a[1]] * a[2] * 10) / 10; $(a[0]).value = v; $(a[0] + '-n').value = v; });
        $('pad-link').checked = cfg.padLink;
    }
    function advInput(a, raw) {
        var v = parseFloat(raw); if (isNaN(v)) { return; }
        cfg.adv[a[1]] = v / a[2];
        if (cfg.padLink && (a[1] === 'padBefore' || a[1] === 'padAfter')) { cfg.adv.padBefore = cfg.adv.padAfter = v / a[2]; }
        cfg.advTouched = true;
        renderAdv(); save(); replan();
    }
    function setMode(m) {
        cfg.mode = m; save();
        Array.prototype.forEach.call(document.querySelectorAll('#modes button'), function (b) { b.classList.toggle('active', b.getAttribute('data-mode') === m); });
        $('go').textContent = t(m === 'cut' ? 'goCut' : 'goMarkers');
        if (S.info) { renderChips(); }
    }
    function renderPresets() {
        var sel = $('preset-select');
        sel.innerHTML = '<option value="">' + t('presetDefault') + '</option>';
        presets.forEach(function (p, i) { var o = document.createElement('option'); o.value = i; o.textContent = p.name; sel.appendChild(o); });
    }
    function applyLang(l) {
        cfg.lang = l; save(); I.apply(l);
        $('lang').textContent = l === 'ar' ? 'EN' : '\u0639';
        setMode(cfg.mode); renderPresets(); renderFillers(); summary();
        if (S.info) { refreshTarget(); }
    }

    function wire() {
        $('lang').onclick = function () { applyLang(cfg.lang === 'ar' ? 'en' : 'ar'); };
        $('menu-btn').onclick = function (e) { e.stopPropagation(); $('menu').hidden = !$('menu').hidden; };
        document.addEventListener('click', function () { $('menu').hidden = true; });
        $('menu').onclick = function (e) {
            var act = e.target.getAttribute('data-act');
            if (act === 'clear-markers') { C.call('clearMarkers').then(function (r) { status(t('markersCleared', { n: r.removed }), 'ok'); }).catch(fail); }
            if (act === 'open-logs') { E.openFolder(E.LOGS); }
            if (act === 'reset') {
                var keepLang = cfg.lang;
                cfg = JSON.parse(JSON.stringify(DEFAULTS)); cfg.lang = keepLang; save();
                init(); status(t('settingsReset'), 'ok');
            }
        };
        $('ripple').onchange = function () { cfg.ripple = this.checked; save(); if (S.info) { renderChips(); } };
        $('backup').onchange = function () { cfg.backup = this.checked; save(); };
        $('link').onchange = function () { cfg.link = this.checked; save(); };
        $('scan').onclick = scan;
        Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (b) { b.onclick = function () { setTab(b.getAttribute('data-tab')); }; });
        Array.prototype.forEach.call(document.querySelectorAll('#levels button'), function (b) { b.onclick = function () { setIntensity(D.SIMPLE[b.getAttribute('data-level')]); }; });
        $('intensity').oninput = function () { setIntensity(+this.value); };
        $('nudge-down').onclick = function () { setIntensity(cfg.intensity - 1); };
        $('nudge-up').onclick = function () { setIntensity(cfg.intensity + 1); };
        ADV.forEach(function (a) {
            $(a[0]).oninput = function () { advInput(a, this.value); };
            $(a[0] + '-n').onchange = function () { advInput(a, this.value); };
        });
        $('pad-link').onchange = function () { cfg.padLink = this.checked; save(); };
        $('tight').onchange = function () { cfg.tight = this.checked; cfg.advTouched = false; save(); replan(); };
        $('preset-add').onclick = function () {
            var name = $('preset-name').value.trim(); if (!name) { return; }
            presets = presets.filter(function (p) { return p.name !== name; });
            presets.push({ name: name, adv: Object.assign({}, cfg.adv) });
            E.writeJSON('presets.json', presets); renderPresets(); $('preset-name').value = ''; status(t('presetSaved'), 'ok');
        };
        $('preset-select').onchange = function () {
            var p = presets[+this.value]; if (!p) { return; }
            cfg.adv = Object.assign({}, p.adv); cfg.advTouched = true; renderAdv(); save(); replan();
        };
        $('preset-del').onclick = function () {
            var i = $('preset-select').value; if (i === '') { return; }
            presets.splice(+i, 1); E.writeJSON('presets.json', presets); renderPresets();
        };
        $('fillers-on').onchange = function () {
            cfg.fillersOn = this.checked; save(); $('filler-opts').hidden = !cfg.fillersOn;
            if (S.env && cfg.fillersOn && !S.words) { status(t('noScan')); }
            findFillers(); replan();
        };
        $('filler-lang').onchange = function () { cfg.fillerLang = this.value; save(); };
        $('sounds-on').onchange = function () { cfg.soundsOn = this.checked; save(); findFillers(); replan(); };
        $('list-strong').onchange = function () { cfg.listStrong = this.value; save(); findFillers(); replan(); };
        $('list-soft').onchange = function () { cfg.listSoft = this.value; save(); findFillers(); replan(); };
        Array.prototype.forEach.call(document.querySelectorAll('#modes button'), function (b) { b.onclick = function () { setMode(b.getAttribute('data-mode')); }; });
        $('go').onclick = go;
        $('undo').onclick = undo;
        $('stop').onclick = stop;
        var last = 0;
        function poke() { var now = Date.now(); if (now - last > 1500 && !S.busy) { last = now; refreshTarget(); } }
        document.addEventListener('mouseenter', poke);
        window.addEventListener('focus', poke);
    }

    function init() {
        applyLang(cfg.lang);
        $('ripple').checked = cfg.ripple; $('backup').checked = cfg.backup; $('link').checked = cfg.link; $('tight').checked = cfg.tight;
        $('fillers-on').checked = cfg.fillersOn; $('filler-opts').hidden = !cfg.fillersOn;
        $('filler-lang').value = cfg.fillerLang; $('sounds-on').checked = cfg.soundsOn;
        $('list-strong').value = cfg.listStrong; $('list-soft').value = cfg.listSoft;
        renderAdv(); setIntensity(cfg.intensity); setTab(cfg.tab); setMode(cfg.mode);
        progress(null); busy(false);
        refreshTarget();
    }

    wire();
    init();
    E.log('panel opened');
})();
