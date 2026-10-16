// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
// Ported from the owner's Kalam platform.js; A6b paths under the engine home, reserved-name safeName and fileUrl added, see adobe/tools/kalam/src/README.md.
/* Kalam - what differs between macOS and Windows on the panel side: folders, the Python path, child env, reveal. */
(function (root) {
    'use strict';
    var P = {};

    function join(sep, parts) { return parts.join(sep); }

    /* data folders under the engine home (~/.whynot-cut): <engineHome>/tools/kalam. No Python path: the engine
       runtime runs Kalam, a UXP panel cannot spawn it. */
    P.paths = function (platform, engineHome, sep) {
        var home = join(sep, [engineHome, 'tools', 'kalam']);
        return { home: home, logs: join(sep, [home, 'logs']), cache: join(sep, [home, 'cache']),
                 models: join(sep, [home, 'models']), hf: join(sep, [home, 'hf']) };
    };

    /* environment for the engine: Arabic must cross the pipe as UTF-8 on every OS */
    P.childEnv = function (platform, base) {
        var e = {}, k;
        for (k in base) { if (Object.prototype.hasOwnProperty.call(base, k)) { e[k] = base[k]; } }
        e.PYTHONUTF8 = '1';
        e.PYTHONIOENCODING = 'utf-8';
        return e;
    };

    P.revealCmd = function (platform, p) {
        return platform === 'win32' ? ['explorer', ['/select,' + p]] : ['open', ['-R', p]];
    };
    P.openCmd = function (platform, p) {
        return platform === 'win32' ? ['explorer', [p]] : ['open', [p]];
    };

    /* a file name every OS accepts: Windows forbids \ / : * ? " < > |, trailing dots and spaces and the device names
       (CON, PRN, AUX, NUL, COM1-9, LPT1-9, also with an extension: nul.srt); an empty result is "_" */
    P.safeName = function (s) {
        var n = String(s).replace(/[\\\/:*?"<>|]/g, '-').replace(/[. ]+$/, ''), dot = n.indexOf('.');
        var base = dot < 0 ? n : n.slice(0, dot);
        if (/^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(base.replace(/ +$/, ''))) { n = base + '_' + n.slice(base.length); }
        return n || '_';
    };

    /* a file:// URL for a local path: file:///C:/... for a drive path, file:///... for POSIX, file://server/... for UNC */
    P.fileUrl = function (p) {
        var s = String(p).replace(/\\/g, '/'), enc = encodeURI(s).replace(/#/g, '%23').replace(/\?/g, '%3F');
        if (/^[A-Za-z]:\//.test(s)) { return 'file:///' + enc; }
        if (s.slice(0, 2) === '//') { return 'file:' + enc; }
        return 'file://' + enc;
    };

    /* Premiere's Local Templates folder (what Essential Graphics shows under "My Templates") */
    P.templatesDir = function (platform, env, homedir, sep) {
        if (platform === 'win32') {
            return join(sep, [env.APPDATA || join(sep, [homedir, 'AppData', 'Roaming']), 'Adobe', 'Common', 'Motion Graphics Templates']);
        }
        return join(sep, [homedir, 'Library', 'Application Support', 'Adobe', 'Common', 'Motion Graphics Templates']);
    };

    root.KalamPlatform = P;
    if (typeof module === 'object' && module.exports) { module.exports = P; }
})(typeof window !== 'undefined' ? window : this);
