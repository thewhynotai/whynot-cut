/* Kalam - the user's Motion Graphics Templates as a gallery: name, folder, thumbnail and text fields of every
   .mogrt under Premiere's Local Templates folder. A .mogrt is a zip: definition.json + thumb.png are read from it
   (read only) and cached by path + modification time. */
(function (root) {
    'use strict';
    var G = {};

    function u16(b, i) { return b[i] | (b[i + 1] << 8); }
    function u32(b, i) { return (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16)) + b[i + 3] * 16777216; }
    function utf8(b, from, to) {
        var s = '', i;
        for (i = from; i < to; i++) { s += String.fromCharCode(b[i]); }
        try { return decodeURIComponent(escape(s)); } catch (e) { return s; }
    }

    /* [{name, method, compSize, size, offset}] from the zip's central directory */
    G.zipEntries = function (b) {
        var i, end = -1, out = [];
        for (i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) {
            if (b[i] === 0x50 && b[i + 1] === 0x4b && b[i + 2] === 0x05 && b[i + 3] === 0x06) { end = i; break; }
        }
        if (end < 0) { return out; }
        var count = u16(b, end + 10), p = u32(b, end + 16), k;
        for (k = 0; k < count && p + 46 <= b.length; k++) {
            if (u32(b, p) !== 0x02014b50) { break; }
            var n = u16(b, p + 28), x = u16(b, p + 30), c = u16(b, p + 32);
            out.push({ name: utf8(b, p + 46, p + 46 + n), method: u16(b, p + 10), compSize: u32(b, p + 20),
                       size: u32(b, p + 24), offset: u32(b, p + 42) });
            p += 46 + n + x + c;
        }
        return out;
    };
    /* where an entry's (compressed) bytes begin: after its local header */
    G.dataStart = function (b, e) { return e.offset + 30 + u16(b, e.offset + 26) + u16(b, e.offset + 28); };

    function localized(v) {
        var db = v && v.strDB, i;
        if (!db || !db.length) { return ''; }
        for (i = 0; i < db.length; i++) { if (db[i].localeString === 'en_US') { return db[i].str; } }
        return db[0].str;
    }
    /* {name, textFields: [names of the template's text controls]} */
    G.definitionInfo = function (d) {
        var fields = [], cs = (d && d.clientControls) || [], i;
        for (i = 0; i < cs.length; i++) { if (cs[i].type === 6) { fields.push(localized(cs[i].uiName) || ('Text ' + (fields.length + 1))); } }
        return { name: localized(d && d.capsuleNameLocalized) || (d && d.capsuleName) || '', textFields: fields };
    };

    G.folderOf = function (p, base) {
        var rel = String(p).slice(String(base).length).replace(/^[\/\\]+/, '');
        var cut = Math.max(rel.lastIndexOf('/'), rel.lastIndexOf('\\'));
        return cut > 0 ? rel.slice(0, cut).replace(/\\/g, '/') : '';
    };
    G.filter = function (list, q, top) {
        q = String(q || '').toLowerCase();
        return list.filter(function (m) {
            if (top && m.folder !== top && m.folder.indexOf(top + '/') !== 0) { return false; }
            return !q || m.name.toLowerCase().indexOf(q) >= 0;
        });
    };
    G.topFolders = function (list) {
        var seen = {}, out = [];
        list.forEach(function (m) { var t = m.folder.split('/')[0]; if (t && !seen[t]) { seen[t] = true; out.push(t); } });
        return out.sort();
    };

    /* Node side: every .mogrt under base -> [{path, name, folder, textFields, thumb}], cached in cacheDir */
    G.scan = function (base, cacheDir) {
        var req = (root.cep_node && root.cep_node.require) || root.require;
        var fs = req('fs'), path = req('path'), zlib = req('zlib'), crypto = req('crypto');
        var thumbs = path.join(cacheDir, 'mogrt-thumbs'), indexFile = path.join(cacheDir, 'mogrt-index.json'), cache = {}, out = [];
        try { fs.mkdirSync(thumbs, { recursive: true }); } catch (e) {}
        try { cache = JSON.parse(fs.readFileSync(indexFile, 'utf8')); } catch (e) { cache = {}; }
        function walk(dir) {
            var names = [];
            try { names = fs.readdirSync(dir); } catch (e) { return; }
            names.forEach(function (n) {
                var p = path.join(dir, n), st;
                if (n.charAt(0) === '.') { return; }
                try { st = fs.statSync(p); } catch (e) { return; }
                if (st.isDirectory()) { walk(p); return; }
                if (!/\.mogrt$/i.test(n)) { return; }
                var key = p + '|' + st.mtimeMs, hit = cache[key];
                if (!hit || !fs.existsSync(hit.thumb || '/nonexistent')) { hit = read(p, key); }
                if (hit) { hit.folder = G.folderOf(p, base); out.push(hit); }
            });
        }
        function read(p, key) {
            try {
                var b = fs.readFileSync(p), es = G.zipEntries(b), def = null, png = null, i;
                function data(e) { var raw = b.slice(G.dataStart(b, e), G.dataStart(b, e) + e.compSize); return e.method === 8 ? zlib.inflateRawSync(raw) : raw; }
                for (i = 0; i < es.length; i++) {
                    if (es[i].name === 'definition.json') { def = JSON.parse(data(es[i]).toString('utf8')); }
                    if (es[i].name === 'thumb.png') { png = data(es[i]); }
                }
                var info = G.definitionInfo(def || {}), thumb = '';
                if (png) { thumb = path.join(thumbs, crypto.createHash('sha1').update(p).digest('hex') + '.png'); fs.writeFileSync(thumb, png); }
                var rec = { path: p, name: info.name || path.basename(p, '.mogrt'), textFields: info.textFields, thumb: thumb };
                cache[key] = rec;
                return rec;
            } catch (e) { return { path: p, name: path.basename(p, '.mogrt'), textFields: [], thumb: '' }; }
        }
        walk(base);
        try { fs.writeFileSync(indexFile, JSON.stringify(cache)); } catch (e) {}
        out.sort(function (a, b) { return a.folder === b.folder ? (a.name < b.name ? -1 : 1) : (a.folder < b.folder ? -1 : 1); });
        return out;
    };

    root.KalamMogrt = G;
})(window);
