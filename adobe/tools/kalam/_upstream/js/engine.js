/* Kalam - Node side: settings (private), logs, jobs, running the Python engine. */
(function (root) {
    'use strict';
    var req = (root.cep_node && root.cep_node.require) || root.require;
    var fs = req('fs'), path = req('path'), os = req('os'), cp = req('child_process');
    var E = {}, P = root.KalamPlatform, plat = process.platform;
    var dirs = P.paths(plat, process.env, os.homedir(), path.sep);

    E.HOME = dirs.home;
    E.LOGS = dirs.logs;
    E.CACHE = dirs.cache;
    E.PY = dirs.py;
    E.MODELS = dirs.models;
    E.TEMPLATES = P.templatesDir(plat, process.env, os.homedir(), path.sep);
    [E.HOME, E.LOGS, E.CACHE].forEach(function (d) { try { fs.mkdirSync(d, { recursive: true }); } catch (e) {} });

    E.log = function (msg) {
        try { fs.appendFileSync(path.join(E.LOGS, 'kalam.log'), new Date().toISOString() + '  ' + msg + '\n'); } catch (e) {}
    };
    E.engineDir = function () { return path.join(root.KalamCEP.extensionPath(), 'engine'); };
    E.installed = function () { return fs.existsSync(E.PY) && fs.existsSync(path.join(E.engineDir(), 'kalam_engine.py')); };

    /* settings.json holds the API key: owner-only permissions, never logged */
    E.loadSettings = function (defaults) {
        var s = {};
        try { s = JSON.parse(fs.readFileSync(path.join(E.HOME, 'settings.json'), 'utf8')); } catch (e) {}
        return Object.assign({}, defaults, s);
    };
    E.saveSettings = function (s) {
        var p = path.join(E.HOME, 'settings.json');
        try { fs.writeFileSync(p, JSON.stringify(s, null, 1), { mode: 384 }); fs.chmodSync(p, 384); } catch (e) { E.log('settings save failed: ' + e); }
    };
    E.defaultRules = function (mode) {
        var f = mode === 'ar' ? 'default_rules.txt' : 'default_rules_en.txt';
        try { return fs.readFileSync(path.join(E.engineDir(), 'kalam', f), 'utf8'); } catch (e) { return ''; }
    };

    /* "Correct = wrong, other wrong" lines -> {Correct: [variants]} */
    E.parseGlossary = function (text) {
        var out = {};
        String(text || '').split('\n').forEach(function (line) {
            var i = line.indexOf('=');
            if (i < 0) { return; }
            var k = line.slice(0, i).trim(), vs = line.slice(i + 1).split(/[,\u060c]/).map(function (v) { return v.trim(); }).filter(Boolean);
            if (k && vs.length) { out[k] = vs; }
        });
        return out;
    };

    E.newJob = function () {
        var dir = path.join(E.CACHE, 'job-' + Date.now());
        fs.mkdirSync(dir, { recursive: true });
        E.cleanJobs();
        return dir;
    };
    E.cleanJobs = function () {   // keep the last 5 jobs
        try {
            var jobs = fs.readdirSync(E.CACHE).filter(function (n) { return /^job-\d+$/.test(n); }).sort();
            jobs.slice(0, Math.max(0, jobs.length - 5)).forEach(function (n) {
                var d = path.join(E.CACHE, n);
                fs.readdirSync(d).forEach(function (f) { try { fs.unlinkSync(path.join(d, f)); } catch (e) {} });
                try { fs.rmdirSync(d); } catch (e) {}
            });
        } catch (e) {}
    };

    /* run the engine; onStage(stageEvent). Returns {promise, kill}. The job settings file is deleted right after start. */
    E.run = function (jobDir, wav, mode, settings, onStage) {
        var sPath = path.join(jobDir, 'settings.json');
        fs.writeFileSync(sPath, JSON.stringify(settings), { mode: 384 });
        var env = Object.assign(P.childEnv(plat, process.env), {
            HF_HOME: dirs.hf, HF_HUB_OFFLINE: '1', PYTHONDONTWRITEBYTECODE: '1', TOKENIZERS_PARALLELISM: 'false'
        });
        var child = cp.spawn(E.PY, [path.join(E.engineDir(), 'kalam_engine.py'), 'run', '--wav', wav, '--mode', mode,
                                     '--out', jobDir, '--settings', sPath, '--models', E.MODELS], { env: env, windowsHide: true });
        var killed = false, last = null, errTail = '';
        var promise = new Promise(function (resolve, reject) {
            var buf = '';
            child.stdout.on('data', function (d) {
                buf += d.toString();
                var lines = buf.split('\n'); buf = lines.pop();
                lines.forEach(function (l) {
                    var m; try { m = JSON.parse(l); } catch (e) { return; }
                    if (m.stage === 'loading') { try { fs.unlinkSync(sPath); } catch (e) {} }
                    last = m;
                    if (onStage) { onStage(m); }
                });
            });
            child.stderr.on('data', function (d) { errTail = (errTail + d.toString()).slice(-3000); });
            child.on('error', reject);
            child.on('close', function (code) {
                try { fs.unlinkSync(sPath); } catch (e) {}
                if (killed) { reject(new Error('cancelled')); return; }
                if (last && last.stage === 'done') { resolve(last); return; }
                var msg = last && last.stage === 'error' ? last.error : (errTail.split('\n').filter(Boolean).pop() || ('exit ' + code));
                E.log('engine failed: ' + msg + (last && last.trace ? '\n' + last.trace : ''));
                reject(new Error(msg));
            });
        });
        return { promise: promise, kill: function () { killed = true; try { child.kill(); } catch (e) {} } };
    };

    E.readJSON = function (p) { return JSON.parse(fs.readFileSync(p, 'utf8')); };
    E.writeText = function (dst, text) { fs.mkdirSync(path.dirname(dst), { recursive: true }); fs.writeFileSync(dst, text, 'utf8'); return dst; };
    E.readText = function (p) { return fs.readFileSync(p, 'utf8'); };
    E.copy = function (src, dst) { fs.mkdirSync(path.dirname(dst), { recursive: true }); fs.copyFileSync(src, dst); return dst; };
    function launch(c) { cp.spawn(c[0], c[1], { detached: true, stdio: 'ignore' }).unref(); }
    E.reveal = function (p) { launch(P.revealCmd(plat, p)); };
    E.openFolder = function (p) { launch(P.openCmd(plat, p)); };

    /* one text file on the Desktop for the developer: system, doctor, last log lines. Never settings or keys. */
    E.report = function (host) {
        return new Promise(function (resolve) {
            var env = Object.assign(P.childEnv(plat, process.env), { HF_HOME: dirs.hf, HF_HUB_OFFLINE: '1' });
            cp.execFile(E.PY, [path.join(E.engineDir(), 'kalam_engine.py'), 'doctor', '--models', E.MODELS, '--quick'],
                        { env: env, timeout: 120000, windowsHide: true }, function (err, out, errOut) {
                var log = '';
                try { log = fs.readFileSync(path.join(E.LOGS, 'kalam.log'), 'utf8').split('\n').slice(-200).join('\n'); } catch (e) {}
                var d = new Date();
                function z(n) { return (n < 10 ? '0' : '') + n; }
                var stamp = d.getFullYear() + z(d.getMonth() + 1) + z(d.getDate()) + '-' + z(d.getHours()) + z(d.getMinutes()) + z(d.getSeconds());
                var dst = path.join(os.homedir(), 'Desktop', 'Kalam-report-' + stamp + '.txt');
                var text = ['Kalam report ' + d.toISOString(),
                            'os: ' + os.type() + ' ' + os.release() + ' ' + os.arch() + ' (' + plat + ')',
                            'premiere: ' + (host && host.version || '?') + '   panel: ' + (host && host.panel || '?'),
                            'python: ' + E.PY + (fs.existsSync(E.PY) ? '' : '  (MISSING)'),
                            '', '--- doctor ---', String(out || '').trim(), String(errOut || '').trim().slice(-3000),
                            err ? 'doctor exit: ' + (err.code || err.message) : '',
                            '', '--- last log lines ---', log].join('\n');
                try { fs.writeFileSync(dst, text, 'utf8'); } catch (e) { dst = path.join(E.HOME, path.basename(dst)); fs.writeFileSync(dst, text, 'utf8'); }
                resolve(dst);
            });
        });
    };
    E.path = path;

    root.KalamEngine = E;
})(window);
