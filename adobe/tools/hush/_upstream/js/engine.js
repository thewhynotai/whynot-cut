/* Hush - Node side: files, settings, logs, audio scan, Whisper process. */
(function (root) {
    'use strict';
    var req = (root.cep_node && root.cep_node.require) || root.require;
    var fs = req('fs'), path = req('path'), os = req('os'), cp = req('child_process');
    var E = {};

    E.HOME = path.join(os.homedir(), 'Library', 'Application Support', 'Hush');
    E.CACHE = path.join(E.HOME, 'cache');
    E.LOGS = path.join(E.HOME, 'logs');
    E.PY = path.join(E.HOME, 'venv', 'bin', 'python');
    E.HF = path.join(E.HOME, 'hf');
    [E.HOME, E.CACHE, E.LOGS].forEach(function (d) { try { fs.mkdirSync(d, { recursive: true }); } catch (e) {} });

    E.log = function (msg) {
        var line = new Date().toISOString() + '  ' + msg + '\n';
        try { fs.appendFileSync(path.join(E.LOGS, 'hush.log'), line); } catch (e) {}
    };
    E.readJSON = function (name, fallback) {
        try { return JSON.parse(fs.readFileSync(path.join(E.HOME, name), 'utf8')); } catch (e) { return fallback; }
    };
    E.writeJSON = function (name, data) {
        try { fs.writeFileSync(path.join(E.HOME, name), JSON.stringify(data, null, 1)); } catch (e) { E.log('write ' + name + ' failed: ' + e); }
    };
    E.openFolder = function (dir) { cp.spawn('open', [dir], { detached: true, stdio: 'ignore' }).unref(); };

    /* export the range from Premiere (chosen audio tracks only) and build the level envelope */
    E.scanAudio = function (range, audioTracks) {
        var out = path.join(E.CACHE, 'scan-' + Date.now() + '.wav');
        E.cleanCache();
        return root.HushCEP.call('exportAudio', {
            outPath: out, start: range.start, end: range.end, audioTracks: audioTracks, extDir: root.HushCEP.extensionPath()
        }).then(function (r) {
            var buf = fs.readFileSync(r.path);
            var bytes = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
            var e = root.HushWav.envelope(bytes, root.HushDetect.HOP);
            E.log('scan ' + r.path + ' ' + e.duration.toFixed(2) + 's @' + e.sampleRate);
            return { wav: r.path, env: e.env, duration: e.duration };
        });
    };

    /* keep the cache small: drop scans older than the last 3 */
    E.cleanCache = function () {
        try {
            var f = fs.readdirSync(E.CACHE).filter(function (n) { return /^scan-\d+\.wav$/.test(n) || /^words-\d+\.json$/.test(n); }).sort();
            f.slice(0, Math.max(0, f.length - 6)).forEach(function (n) { fs.unlinkSync(path.join(E.CACHE, n)); });
        } catch (e) {}
    };

    E.hasWhisper = function () { return fs.existsSync(E.PY); };

    /* run Whisper on the scanned wav. returns {promise, kill}; onStage gets 'loading' | 'transcribing' */
    E.transcribe = function (wav, lang, onStage) {
        var outJson = path.join(E.CACHE, 'words-' + Date.now() + '.json');
        var script = path.join(root.HushCEP.extensionPath(), 'py', 'hush_whisper.py');
        var env = Object.assign({}, process.env, { HF_HOME: E.HF, HF_HUB_OFFLINE: '1', PYTHONDONTWRITEBYTECODE: '1' });
        var child = cp.spawn(E.PY, [script, wav, outJson, lang || 'auto'], { env: env });
        var killed = false, errText = '', lastErr = null;
        var promise = new Promise(function (resolve, reject) {
            var buf = '';
            child.stdout.on('data', function (d) {
                buf += d.toString();
                var lines = buf.split('\n'); buf = lines.pop();
                lines.forEach(function (l) {
                    var m; try { m = JSON.parse(l); } catch (e) { return; }
                    if (m.stage === 'error') { lastErr = m.error; }
                    else if (onStage) { onStage(m.stage, m); }
                });
            });
            child.stderr.on('data', function (d) { errText = (errText + d.toString()).slice(-4000); });
            child.on('error', function (e) { reject(e); });
            child.on('close', function (code) {
                if (killed) { reject(new Error('cancelled')); return; }
                if (code !== 0) {
                    E.log('whisper failed (' + code + '): ' + (lastErr || errText));
                    reject(new Error('Whisper failed: ' + (lastErr || errText.split('\n').filter(Boolean).pop() || code)));
                    return;
                }
                try { resolve(JSON.parse(fs.readFileSync(outJson, 'utf8'))); } catch (e) { reject(e); }
            });
        });
        return { promise: promise, kill: function () { killed = true; try { child.kill('SIGTERM'); } catch (e) {} } };
    };

    root.HushEngine = E;
})(window);
