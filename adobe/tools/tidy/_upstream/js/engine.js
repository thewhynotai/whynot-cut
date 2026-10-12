/* Tidy - Node side: what is on disk (exists / size), the backup copy of the project file, logs. */
(function (root) {
    'use strict';
    var req = (root.cep_node && root.cep_node.require) || root.require;
    var fs = req('fs'), path = req('path'), os = req('os'), cp = req('child_process');
    var E = {};
    E.HOME = path.join(os.homedir(), 'Library', 'Application Support', 'Tidy');
    E.LOGS = path.join(E.HOME, 'logs');
    [E.HOME, E.LOGS].forEach(function (d) { try { fs.mkdirSync(d, { recursive: true }); } catch (e) {} });

    E.log = function (msg) {
        try { fs.appendFileSync(path.join(E.LOGS, 'tidy.log'), new Date().toISOString() + '  ' + msg + '\n'); } catch (e) {}
    };
    E.loadSettings = function (d) {
        try { return Object.assign({}, d, JSON.parse(fs.readFileSync(path.join(E.HOME, 'settings.json'), 'utf8'))); } catch (e) { return Object.assign({}, d); }
    };
    E.saveSettings = function (s) { try { fs.writeFileSync(path.join(E.HOME, 'settings.json'), JSON.stringify(s)); } catch (e) {} };

    /* fill exists/size for every item that points at a file (files are only read, never changed) */
    E.diskInfo = function (items) {
        var seen = {};
        items.forEach(function (it) {
            if (!it.path) { it.exists = true; it.size = 0; return; }
            if (!seen[it.path]) {
                try { var st = fs.statSync(it.path); seen[it.path] = { exists: true, size: st.isDirectory() ? 0 : st.size }; }
                catch (e) { seen[it.path] = { exists: false, size: 0 }; }
            }
            it.exists = seen[it.path].exists;
            it.size = seen[it.path].size;
        });
        return items;
    };

    /* read each video's first and last 2 MB and each image's first 64 KB (read only) and let TidyMedia
       decide camera/render, which camera, icon or not. Files that cannot be read fall back to their names. */
    E.HEAD = 2097152;
    E.sniff = function (items) {
        var M = root.TidyMedia, seen = {}, FIELDS = ['kind', 'camId', 'icon', 'imgW', 'imgH'];
        items.forEach(function (it) {
            var need = M.needsBytes(it);
            if (!need && !/\.(r3d|braw|crm|ari|insv)$/i.test(it.path || '')) { return; }
            if (seen.hasOwnProperty(it.path)) {          // keep the description, never the bytes (4 MB per video)
                FIELDS.forEach(function (f) { if (seen[it.path][f] !== undefined) { it[f] = seen[it.path][f]; } });
                return;
            }
            {
                var text = null, fd = null;
                try {
                    fd = fs.openSync(it.path, 'r');
                    var size = fs.fstatSync(fd).size, n = need === 'video' ? E.HEAD : 65536;
                    var head = Buffer.alloc(Math.min(n, size));
                    fs.readSync(fd, head, 0, head.length, 0);
                    text = head.toString('latin1');
                    if (need === 'video' && size > n) {
                        var tail = Buffer.alloc(Math.min(n, size - n));
                        fs.readSync(fd, tail, 0, tail.length, size - tail.length);
                        text += tail.toString('latin1');
                    }
                } catch (e) { text = null; }
                if (fd !== null) { try { fs.closeSync(fd); } catch (e) {} }
                M.describe(it, need ? text : null);
                text = null;
                seen[it.path] = {};
                FIELDS.forEach(function (f) { seen[it.path][f] = it[f]; });
            }
        });
        return items;
    };

    /* mean power per 1 ms of a 16-bit PCM WAV, read in 4 MB pieces (a 1 h recording never sits in memory) */
    E.wavPower = function (file) {
        var Y = root.TidySync, fd = fs.openSync(file, 'r');
        try {
            var head = Buffer.alloc(65536), got = fs.readSync(fd, head, 0, head.length, 0);
            var info = Y.wavInfo(head.slice(0, got).toString('latin1'));
            if (!info) { throw new Error('Not a 16-bit WAV: ' + file); }
            var frame = Math.round(info.rate / 1000) * info.channels, total = Math.floor(info.dataSize / 2 / frame);
            var out = new Float64Array(total), buf = Buffer.alloc(4194304 - (4194304 % (frame * 2))), pos = info.dataOffset;
            var idx = 0, acc = 0, cnt = 0, end = info.dataOffset + info.dataSize;
            while (pos < end && idx < total) {
                var n = fs.readSync(fd, buf, 0, Math.min(buf.length, end - pos), pos);
                if (n <= 0) { break; }
                for (var i = 0; i + 1 < n; i += 2) {
                    var v = buf.readInt16LE(i) / 32768;
                    acc += v * v;
                    if (++cnt === frame) { out[idx++] = acc / frame; acc = 0; cnt = 0; if (idx === total) { break; } }
                }
                pos += n;
            }
            return out.subarray(0, idx);
        } finally { fs.closeSync(fd); }
    };
    E.tempWav = function (tag) { var d = path.join(E.HOME, 'sync'); fs.mkdirSync(d, { recursive: true }); return path.join(d, tag + '.wav'); };
    E.removeFile = function (p) { try { fs.unlinkSync(p); } catch (e) {} };

    /* copy the (saved) project file next to itself: "<name> (Tidy backup 2026-10-12 1542).prproj" */
    E.backup = function (projectPath) {
        var d = new Date();
        function z(n) { return (n < 10 ? '0' : '') + n; }
        var stamp = d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()) + ' ' + z(d.getHours()) + z(d.getMinutes()) + z(d.getSeconds());
        var dst = path.join(path.dirname(projectPath), path.basename(projectPath, '.prproj') + ' (Tidy backup ' + stamp + ').prproj');
        fs.copyFileSync(projectPath, dst, fs.constants.COPYFILE_EXCL);
        return dst;
    };
    E.size = function (n) {
        if (n >= 1073741824) { return (n / 1073741824).toFixed(1) + ' GB'; }
        if (n >= 1048576) { return (n / 1048576).toFixed(0) + ' MB'; }
        if (n >= 1024) { return (n / 1024).toFixed(0) + ' KB'; }
        return n + ' B';
    };
    E.openFolder = function (p) { cp.spawn('open', [p], { detached: true, stdio: 'ignore' }).unref(); };
    root.TidyEngine = E;
})(window);
