/* Tidy - minimal bridge to Premiere's ExtendScript (replaces CSInterface for the few calls we need). */
(function (root) {
    'use strict';
    var C = {};

    /* ExtendScript source must stay ASCII: escape everything else as \\uXXXX */
    C.ascii = function (s) {
        return s.replace(/[^\x00-\x7e]/g, function (c) { return '\\' + 'u' + ('000' + c.charCodeAt(0).toString(16)).slice(-4); });
    };

    /* call hush_<fn>(jsonString) in Premiere -> Promise of the parsed {ok:true,...} reply */
    C.call = function (fn, args) {
        return new Promise(function (resolve, reject) {
            if (!root.__adobe_cep__) { reject(new Error('Not running inside Premiere Pro')); return; }
            var code = 'tidy_' + fn + '(' + JSON.stringify(C.ascii(JSON.stringify(args || {}))) + ')';
            root.__adobe_cep__.evalScript(code, function (res) {
                var o;
                if (res === 'EvalScript error.' || res === undefined || res === null || res === '') {
                    reject(new Error('Premiere could not run tidy_' + fn + '. Reopen the panel (Window > Extensions > Tidy).'));
                    return;
                }
                try { o = JSON.parse(res); } catch (e) { reject(new Error('Unexpected reply from Premiere: ' + String(res).slice(0, 200))); return; }
                if (!o.ok) { reject(new Error(o.error || 'Premiere reported an error')); return; }
                resolve(o);
            });
        });
    };

    C.extensionPath = function () {
        var p = root.__adobe_cep__ ? root.__adobe_cep__.getSystemPath('extension') : '';
        p = String(p || '').replace(/^file:\/\//, '');
        try { p = decodeURIComponent(p); } catch (e) {}
        return p;
    };

    root.TidyCEP = C;
})(window);
