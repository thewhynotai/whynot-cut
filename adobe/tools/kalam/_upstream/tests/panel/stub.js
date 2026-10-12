/* Browser stand-in for Premiere (evalScript) + Node (fs/child_process) - panel UI tests only.
   Serve the kalam/ folder and open /tests/panel/index.html. window.KALAM_CALLS records host calls. */
(function () {
    function text(url) { var x = new XMLHttpRequest(); x.open('GET', url, false); x.send(); if (x.status !== 200) { throw new Error('ENOENT ' + url); } return x.responseText; }
    var store = {};
    window.KALAM_SPAWNS = [];
    var fs = {
        existsSync: function () { return true; }, mkdirSync: function () {}, chmodSync: function () {}, unlinkSync: function () {},
        rmdirSync: function () {}, readdirSync: function () { return []; }, copyFileSync: function (a, b) { store[b] = store[a] || 'srt'; },
        appendFileSync: function (p, l) { console.log('[log]', l.trim()); },
        writeFileSync: function (p, d) { store[p] = d; },
        readFileSync: function (p) {
            if (store[p] !== undefined) { return store[p]; }
            if (/settings\.json$/.test(p)) { throw new Error('ENOENT'); }
            if (p.indexOf('/ext/') === 0) { return text(p.slice(4)); }
            if (/captions\.json$/.test(p)) { return text('/tests/panel/captions.json'); }
            if (/captions\.srt$/.test(p)) { return '1\n00:00:00,500 --> 00:00:02,000\nواحد\n'; }
            throw new Error('ENOENT ' + p);
        }
    };
    var path = {
        join: function () { return Array.prototype.join.call(arguments, '/').replace(/\/+/g, '/'); },
        dirname: function (p) { return p.replace(/\/[^\/]*$/, ''); },
        basename: function (p) { return p.replace(/^.*\//, ''); }
    };
    var cp = { spawn: function (cmd, args) {
        window.KALAM_SPAWNS.push(args);
        var h = {}, o = {}, out = args[args.indexOf('--out') + 1];
        var ch = { stdout: { on: function (e, f) { o.data = f; } }, stderr: { on: function () {} }, on: function (e, f) { h[e] = f; },
                   kill: function () { setTimeout(function () { h.close && h.close(null); }, 10); }, unref: function () {} };
        var stages = ['loading', 'transcribing', 'aligning', 'correcting', 'captions'];
        stages.forEach(function (s, i) { setTimeout(function () { o.data && o.data('{"stage":"' + s + '"}\n'); }, 80 * (i + 1)); });
        setTimeout(function () {
            if (!o.data) { return; }
            o.data(JSON.stringify({ stage: 'done', captions: 26, srt: out + '/captions.srt', json: out + '/captions.json',
                                    corrected: !!window.STUB_CORRECTED, notice: window.STUB_NOTICE, elapsed: 21.5 }) + '\n');
            h.close(0);
        }, 600);
        return ch;
    } };
    window.require = function (m) { return { fs: fs, path: path, os: { homedir: function () { return '/Users/test'; } }, child_process: cp }[m]; };
    window.process = { env: {} };
    window.KALAM_CALLS = [];
    window.cep = { fs: { showOpenDialogEx: function () { return { data: ['/x/Essential Graphics/Basic Title.mogrt'] }; } } };
    window.__adobe_cep__ = { getSystemPath: function () { return '/ext'; }, evalScript: function (code, cb) {
        var fn = code.match(/^kalam_(\w+)\(/)[1], arg = JSON.parse(JSON.parse(code.slice(code.indexOf('(') + 1, -1)));
        window.KALAM_CALLS.push([fn, arg]);
        var r = { ok: true };
        if (fn === 'info') { r.projectPath = '/Volumes/Work/Clinic/clinic.prproj'; r.sequence = { name: 'Dr Sherif', id: 'seq1', fps: 25, end: 82.08,
            inPoint: 10, outPoint: 60, playhead: 25.5, selection: window.STUB_SEL || [],
            video: [{ index: 0, kind: 'video', name: 'Video 1', clips: 1 }, { index: 1, kind: 'video', name: 'Video 2', clips: 0 }, { index: 2, kind: 'video', name: 'Video 3', clips: 0 }],
            audio: [{ index: 0, kind: 'audio', name: 'Mic', clips: 1 }, { index: 1, kind: 'audio', name: 'Music', clips: 1, muted: true }] }; }
        if (fn === 'exportAudio') { r.path = arg.outPath; }
        if (fn === 'mogrt') { r.added = arg.captions.length; }
        if (fn === 'removeClips') { r.removed = 26; }
        setTimeout(function () { cb(JSON.stringify(r)); }, 30);
    } };
})();
