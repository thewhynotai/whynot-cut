/* Hush - pure detection maths (no DOM, no Node). Loaded by the panel and by the tests.
   All times are seconds relative to the start of the analysed range. */
(function (root) {
    'use strict';
    var D = {};
    D.HOP = 0.01; // envelope resolution: 10 ms

    /* RMS level per hop, in dBFS (floor -100) */
    D.envelope = function (samples, sampleRate, hop) {
        hop = hop || D.HOP;
        var n = Math.max(1, Math.round(sampleRate * hop));
        var frames = Math.ceil(samples.length / n), env = new Float32Array(frames), i, j, sum, v, end;
        for (i = 0; i < frames; i++) {
            sum = 0; end = Math.min(samples.length, (i + 1) * n);
            for (j = i * n; j < end; j++) { v = samples[j]; sum += v * v; }
            v = Math.sqrt(sum / Math.max(1, end - i * n));
            env[i] = v > 1e-5 ? 20 * Math.log10(v) : -100;
        }
        return env;
    };

    D.percentile = function (env, p) {
        var a = Array.prototype.slice.call(env).sort(function (x, y) { return x - y; });
        return a.length ? a[Math.min(a.length - 1, Math.floor(p * a.length))] : -100;
    };

    /* noise floor and speech level of a clip */
    D.stats = function (env) {
        return { floor: Math.max(-70, D.percentile(env, 0.10)), speech: D.percentile(env, 0.90) };
    };

    /* Simple mode: one 0..100 intensity -> detection settings, adapted to this clip's levels */
    D.SIMPLE = { soft: 25, medium: 50, strong: 80 };
    D.fromIntensity = function (intensity, st) {
        var t = Math.max(0, Math.min(100, intensity)) / 100;
        var span = Math.max(6, st.speech - st.floor);
        var pad = 0.18 - 0.12 * t;
        return {
            threshold: Math.round((st.floor + span * (0.15 + 0.30 * t)) * 10) / 10,
            minSilence: Math.round((0.9 - 0.65 * t) * 100) / 100,
            padBefore: Math.round(pad * 100) / 100,
            padAfter: Math.round(pad * 100) / 100
        };
    };

    /* runs below threshold lasting >= minSilence; clicks shorter than 30 ms inside a silence are ignored */
    D.silences = function (env, threshold, minSilence, hop) {
        hop = hop || D.HOP;
        var out = [], i, start = -1, blip = 0, maxBlip = Math.round(0.03 / hop);
        for (i = 0; i <= env.length; i++) {
            var quiet = i < env.length && env[i] < threshold;
            if (quiet) {
                if (start < 0) { start = i; }
                blip = 0;
            } else if (start >= 0) {
                blip++;
                if (blip > maxBlip || i === env.length) {
                    var end = i - blip + 1;
                    if ((end - start) * hop >= minSilence) { out.push([start * hop, end * hop]); }
                    start = -1; blip = 0;
                }
            }
        }
        return out;
    };

    /* silence -> cut range, leaving padding next to speech. A silence touching the range edge needs no pad there. */
    D.cutsFromSilences = function (sil, o, length) {
        var out = [], i, s, e;
        for (i = 0; i < sil.length; i++) {
            s = sil[i][0] <= 0.001 ? 0 : sil[i][0] + o.padAfter;
            e = sil[i][1] >= length - 0.001 ? length : sil[i][1] - o.padBefore;
            if (e - s >= (o.minCut || 0.08)) { out.push({ s: s, e: e, kind: 'silence' }); }
        }
        return out;
    };

    /* union of ranges; filler cuts also swallow a gap up to joinGap so no sliver of padding is left beside them */
    D.combine = function (ranges, joinGap) {
        var a = ranges.slice(0).sort(function (x, y) { return x.s - y.s; }), out = [], i, r, last;
        for (i = 0; i < a.length; i++) {
            r = { s: a[i].s, e: a[i].e, kind: a[i].kind, label: a[i].label };
            last = out[out.length - 1];
            var gap = last ? r.s - last.e : Infinity;
            var join = last && (gap <= 0.0005 || (gap <= joinGap && (r.kind === 'filler' || last.kind === 'filler')));
            if (join) {
                last.e = Math.max(last.e, r.e);
                if (r.kind === 'filler') { last.kind = 'filler'; last.label = (last.label ? last.label + ' ' : '') + (r.label || ''); }
            } else { out.push(r); }
        }
        return out;
    };

    /* align to whole frames (inward), drop anything shorter than minFrames */
    D.snap = function (ranges, fps, minFrames) {
        var out = [], i, s, e;
        minFrames = minFrames || 2;
        for (i = 0; i < ranges.length; i++) {
            // round inward: the cut never reaches into speech, even by part of a frame
            s = Math.ceil(ranges[i].s * fps - 1e-6) / fps;
            e = Math.floor(ranges[i].e * fps + 1e-6) / fps;
            if ((e - s) * fps >= minFrames - 0.001) { out.push({ s: s, e: e, kind: ranges[i].kind, label: ranges[i].label }); }
        }
        return out;
    };

    D.total = function (ranges) {
        var t = 0;
        for (var i = 0; i < ranges.length; i++) { t += ranges[i].e - ranges[i].s; }
        return t;
    };

    /* the full plan: env + settings + chosen fillers -> frame-aligned cuts */
    D.plan = function (env, settings, fillers, length, fps) {
        var sil = D.silences(env, settings.threshold, settings.minSilence);
        var cuts = D.cutsFromSilences(sil, settings, length);
        var all = cuts.concat(fillers || []);
        var joined = D.combine(all, settings.padBefore + settings.padAfter + 0.05);
        var snapped = D.snap(joined, fps, 2);
        return { silences: sil, cuts: snapped, removed: D.total(snapped), before: length, after: length - D.total(snapped) };
    };

    D.fmt = function (sec) {
        sec = Math.max(0, sec);
        var m = Math.floor(sec / 60), s = sec - m * 60;
        return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1);
    };

    root.HushDetect = D;
})(typeof window !== 'undefined' ? window : this);
