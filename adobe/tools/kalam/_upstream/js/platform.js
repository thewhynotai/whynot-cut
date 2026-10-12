/* Kalam - what differs between macOS and Windows on the panel side: folders, the Python path, child env, reveal. */
(function (root) {
    'use strict';
    var P = {};

    function join(sep, parts) { return parts.join(sep); }

    /* data folders and the engine's Python for this OS */
    P.paths = function (platform, env, homedir, sep) {
        var home;
        if (platform === 'win32') {
            home = join(sep, [env.LOCALAPPDATA || join(sep, [homedir, 'AppData', 'Local']), 'Kalam']);
            return { home: home, py: join(sep, [home, 'python', 'python.exe']), logs: join(sep, [home, 'logs']),
                     cache: join(sep, [home, 'cache']), models: join(sep, [home, 'models']), hf: join(sep, [home, 'hf']) };
        }
        home = join(sep, [homedir, 'Library', 'Application Support', 'Kalam']);
        return { home: home, py: join(sep, [home, 'venv', 'bin', 'python']), logs: join(sep, [home, 'logs']),
                 cache: join(sep, [home, 'cache']), models: join(sep, [home, 'models']), hf: join(sep, [home, 'hf']) };
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

    /* a file name every OS accepts (Windows forbids \\ / : * ? " < > |) */
    P.safeName = function (s) { return String(s).replace(/[\\\/:*?"<>|]/g, '-'); };

    /* Premiere's Local Templates folder (what Essential Graphics shows under "My Templates") */
    P.templatesDir = function (platform, env, homedir, sep) {
        if (platform === 'win32') {
            return join(sep, [env.APPDATA || join(sep, [homedir, 'AppData', 'Roaming']), 'Adobe', 'Common', 'Motion Graphics Templates']);
        }
        return join(sep, [homedir, 'Library', 'Application Support', 'Adobe', 'Common', 'Motion Graphics Templates']);
    };

    root.KalamPlatform = P;
})(window);
