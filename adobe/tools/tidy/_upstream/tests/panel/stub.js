/* Browser stand-in for Premiere + Node - Tidy panel UI tests only. window.TIDY_CALLS records host calls. */
(function () {
    var sizes = { '/m/clip.mp4': 5e8, '/m/voice.wav': 2e7, '/m/old.mp4': 3e8, '/m/logo.png': 2e5, '/m/whoosh.wav': 1e5, '/m/subs.srt': 3e3 };
    var copies = [];
    window.TIDY_COPIES = copies;
    var fs = { mkdirSync: function () {}, appendFileSync: function (p, l) { console.log('[log]', l.trim()); }, writeFileSync: function () {},
        readFileSync: function () { throw new Error('ENOENT'); }, constants: { COPYFILE_EXCL: 1 },
        statSync: function (p) { if (!(p in sizes)) { throw new Error('ENOENT'); } return { size: sizes[p], isDirectory: function () { return false; } }; },
        copyFileSync: function (a, b) { copies.push([a, b]); } };
    var path = { join: function () { return Array.prototype.join.call(arguments, '/').replace(/\/+/g, '/'); },
        dirname: function (p) { return p.replace(/\/[^\/]*$/, ''); }, basename: function (p, ext) { var b = p.replace(/^.*\//, ''); return ext && b.slice(-ext.length) === ext ? b.slice(0, -ext.length) : b; } };
    window.require = function (m) { return { fs: fs, path: path, os: { homedir: function () { return '/Users/test'; } }, child_process: { spawn: function () { return { unref: function () {} }; } } }[m]; };
    window.TIDY_CALLS = [];
    function I(id, name, p, extra) { var it = { nodeId: id, name: name, path: p, isSequence: false, duration: 10, bin: 'Footage stuff', offline: false, color: 1 }; for (var k in (extra || {})) { it[k] = extra[k]; } return it; }
    window.__adobe_cep__ = { getSystemPath: function () { return '/ext'; }, evalScript: function (code, cb) {
        var fn = code.match(/^tidy_(\w+)\(/)[1], arg = JSON.parse(JSON.parse(code.slice(code.indexOf('(') + 1, -1)));
        window.TIDY_CALLS.push([fn, arg]);
        var r = { ok: true };
        if (fn === 'scan') {
            r.name = 'Rog 2.prproj'; r.project = '/Volumes/Work/Rog 2.prproj';
            r.items = [I('c1', 'clip.mp4', '/m/clip.mp4'), I('c2', 'clip.mp4', '/m/clip.mp4'), I('v1', 'voice.wav', '/m/voice.wav', { duration: 200 }),
                       I('o1', 'old.mp4', '/m/old.mp4'), I('l1', 'logo.png', '/m/logo.png'), I('s1', 'whoosh.wav', '/m/whoosh.wav', { duration: 0.5 }),
                       I('g1', 'gone.mp4', '/m/gone.mp4'), I('t1', 'subs.srt', '/m/subs.srt', { bin: 'Kalam Captions' }),
                       I('q1', 'Main', '', { isSequence: true }), I('q2', 'Main (Hush backup 10:00:00)', '', { isSequence: true })];
            r.bins = [{ nodeId: 'b1', path: 'Footage stuff' }, { nodeId: 'b2', path: 'Kalam Captions' }];
            r.usage = { q1: ['c1', 's1', 'g1', 'l1'], q2: ['c1', 'o1'] };
        }
        if (fn === 'save') { r.path = window.STUB_UNSAVED ? '' : '/Volumes/Work/Rog 2.prproj'; }
        if (fn === 'apply') { r.removed = arg.removals.filter(function (x) { return x.checked; }).length; r.moved = arg.moves.length; r.binsRemoved = arg.emptyBins.length; r.colored = arg.colors.length; r.skipped = 0; }
        setTimeout(function () { cb(JSON.stringify(r)); }, 30);
    } };
})();
