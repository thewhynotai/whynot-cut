// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
// Ported from the owner's Kalam mogrt.js; G.scan (Node-only folder scan) removed, the pure functions are unchanged; see adobe/tools/kalam/src/README.md.
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

    /* The folder scan (every .mogrt under Premiere's Local Templates, thumbnails cached by path + modification time)
       needs Node fs, zlib and crypto and cannot run in a UXP panel: the engine service takes it over (Task 11) and
       returns [{path, name, folder, textFields, thumb}] built with the pure functions above. */

    root.KalamMogrt = G;
    if (typeof module === 'object' && module.exports) { module.exports = G; }
})(typeof window !== 'undefined' ? window : this);
