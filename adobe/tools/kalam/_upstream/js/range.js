/* Kalam - what part of the sequence to caption, and SRT times in sequence time (pure, no DOM/Node). */
(function (root) {
    'use strict';
    var R = {};
    R.MODES = ['inout', 'sequence', 'playhead', 'selection'];

    /* seq: {end, inPoint, outPoint, playhead, selection:[{start,end,name}]} -> {ok, start, end, label} or {ok:false, error} */
    R.rangeFor = function (seq, mode) {
        if (mode === 'inout') {
            if (!(seq.inPoint >= 0 && seq.outPoint > seq.inPoint)) { return { ok: false, error: 'noInOut' }; }
            return { ok: true, start: seq.inPoint, end: seq.outPoint, label: 'inOut' };
        }
        if (mode === 'playhead') {
            var p = Math.max(0, seq.playhead || 0);
            if (seq.end - p < 0.5) { return { ok: false, error: 'playheadAtEnd' }; }
            return { ok: true, start: p, end: seq.end, label: 'fromPlayhead' };
        }
        if (mode === 'selection') {
            if (!seq.selection || !seq.selection.length) { return { ok: false, error: 'noSelection' }; }
            var s = Infinity, e = -Infinity, names = {};
            seq.selection.forEach(function (c) { s = Math.min(s, c.start); e = Math.max(e, c.end); names[c.name + c.start] = 1; });
            return { ok: true, start: s, end: e, label: 'clips', count: Object.keys(names).length };
        }
        return { ok: true, start: 0, end: seq.end, label: 'wholeSeq' };
    };

    function ms(tc) {
        var m = /(\d+):(\d\d):(\d\d),(\d\d\d)/.exec(tc);
        return ((+m[1] * 60 + +m[2]) * 60 + +m[3]) * 1000 + +m[4];
    }
    function tc(t) {
        function z(n, w) { n = String(n); while (n.length < w) { n = '0' + n; } return n; }
        return z(Math.floor(t / 3600000), 2) + ':' + z(Math.floor(t / 60000) % 60, 2) + ':' + z(Math.floor(t / 1000) % 60, 2) + ',' + z(t % 1000, 3);
    }

    /* move every timecode of an SRT by offsetSec (captions made for a range -> sequence time) */
    R.shiftSrt = function (text, offsetSec) {
        var off = Math.round(offsetSec * 1000);
        if (!off) { return text; }
        return text.replace(/(\d+:\d\d:\d\d,\d\d\d) --> (\d+:\d\d:\d\d,\d\d\d)/g, function (all, a, b) {
            return tc(ms(a) + off) + ' --> ' + tc(ms(b) + off);
        });
    };

    root.KalamRange = R;
})(typeof window !== 'undefined' ? window : this);
