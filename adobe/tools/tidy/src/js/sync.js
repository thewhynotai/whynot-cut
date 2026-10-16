// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
// Ported from the owner's Tidy sync.js; logic unchanged; see adobe/tools/tidy/src/README.md.
/* Tidy - sync recordings of one shoot by their sound (pure). Loudness envelopes are cross-correlated (FFT) for
   the coarse offset at 100 Hz, then refined at 1 kHz. A clip whose best match is not clearly better than the rest
   is left out: it is never placed at a guess. Offsets are seconds from the reference's start (negative = earlier). */
(function (root) {
    'use strict';
    var Y = {};
    Y.MIN_CONFIDENCE = 3;
    Y.REFINE_SPAN = 120;   // seconds of overlap used for the fine search

    /* log RMS per output frame, mean removed */
    Y.envelope = function (samples, rate, outRate) {
        var frame = rate / outRate, n = Math.floor(samples.length / frame), out = new Float64Array(n), i, k, s, a, b, sum = 0;
        for (i = 0; i < n; i++) {
            a = Math.round(i * frame); b = Math.round((i + 1) * frame); s = 0;
            for (k = a; k < b; k++) { s += samples[k] * samples[k]; }
            out[i] = Math.log(Math.sqrt(s / Math.max(1, b - a)) + 1e-4);
            sum += out[i];
        }
        var mean = n ? sum / n : 0;
        for (i = 0; i < n; i++) { out[i] -= mean; }
        return out;
    };

    function logMeanRemoved(power) {
        var n = power.length, out = new Float64Array(n), i, sum = 0;
        for (i = 0; i < n; i++) { out[i] = Math.log(Math.sqrt(power[i]) + 1e-4); sum += out[i]; }
        var mean = n ? sum / n : 0;
        for (i = 0; i < n; i++) { out[i] -= mean; }
        return out;
    }

    /* mean power per 1 ms (streamed from a WAV) -> {env (100 Hz), hi (1 kHz), seconds} */
    Y.fromPower = function (powerHi) {
        var n = Math.floor(powerHi.length / 10), p100 = new Float64Array(n), i, k, s;
        for (i = 0; i < n; i++) { s = 0; for (k = 0; k < 10; k++) { s += powerHi[i * 10 + k]; } p100[i] = s / 10; }
        return { env: logMeanRemoved(p100), hi: logMeanRemoved(powerHi), seconds: powerHi.length / 1000 };
    };

    function u32(s, i) { return (s.charCodeAt(i) | (s.charCodeAt(i + 1) << 8) | (s.charCodeAt(i + 2) << 16)) + s.charCodeAt(i + 3) * 16777216; }
    function u16(s, i) { return s.charCodeAt(i) | (s.charCodeAt(i + 1) << 8); }
    /* RIFF/WAVE header (latin1 text of the first KBs) -> {rate, channels, bits, dataOffset, dataSize} or null */
    Y.wavInfo = function (s) {
        if (!s || s.length < 20 || s.slice(0, 4) !== 'RIFF' || s.slice(8, 12) !== 'WAVE') { return null; }
        var i = 12, fmt = null;
        while (i + 8 <= s.length) {
            var id = s.slice(i, i + 4), size = u32(s, i + 4);
            if (id === 'fmt ' && i + 24 <= s.length) {
                fmt = { format: u16(s, i + 8), channels: u16(s, i + 10), rate: u32(s, i + 12), bits: u16(s, i + 22) };
            } else if (id === 'data') {
                if (!fmt || (fmt.format !== 1 && fmt.format !== 65534) || fmt.bits !== 16) { return null; }
                return { rate: fmt.rate, channels: fmt.channels, bits: 16, dataOffset: i + 8, dataSize: size };
            }
            i += 8 + size + (size & 1);
        }
        return null;
    };

    function fft(re, im, inverse) {
        var n = re.length, i, j, k, len, half, tr, ti, ang, wr, wi, cr, ci, t;
        for (i = 1, j = 0; i < n; i++) {
            var bit = n >> 1;
            for (; j & bit; bit >>= 1) { j ^= bit; }
            j ^= bit;
            if (i < j) { t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
        }
        for (len = 2; len <= n; len <<= 1) {
            half = len >> 1; ang = (inverse ? 2 : -2) * Math.PI / len; wr = Math.cos(ang); wi = Math.sin(ang);
            for (i = 0; i < n; i += len) {
                cr = 1; ci = 0;
                for (k = 0; k < half; k++) {
                    var a = i + k, b = a + half;
                    tr = re[b] * cr - im[b] * ci; ti = re[b] * ci + im[b] * cr;
                    re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
                    t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
                }
            }
        }
        if (inverse) { for (i = 0; i < n; i++) { re[i] /= n; im[i] /= n; } }
    }

    /* where x starts on ref's clock: {offset (s), confidence (best peak / best peak elsewhere)} */
    Y.offset = function (ref, x, rate) {
        var n = 1, i;
        while (n < ref.length + x.length) { n <<= 1; }
        var ar = new Float64Array(n), ai = new Float64Array(n), br = new Float64Array(n), bi = new Float64Array(n);
        for (i = 0; i < ref.length; i++) { ar[i] = ref[i]; }
        for (i = 0; i < x.length; i++) { br[i] = x[i]; }
        fft(ar, ai, false); fft(br, bi, false);
        for (i = 0; i < n; i++) {   // ref * conj(x)
            var r = ar[i] * br[i] + ai[i] * bi[i], im = ai[i] * br[i] - ar[i] * bi[i];
            ar[i] = r; ai[i] = im;
        }
        fft(ar, ai, true);
        var minOverlap = Math.min(ref.length, x.length) * 0.25, best = -Infinity, bestLag = 0, lag, ov;
        function overlap(L) { return Math.min(ref.length, L + x.length) - Math.max(0, L); }
        function lagAt(k) { return k < n - x.length + 1 ? k : k - n; }
        for (i = 0; i < n; i++) {
            lag = lagAt(i); ov = overlap(lag);
            if (ov < minOverlap || lag >= ref.length || lag <= -x.length) { continue; }
            if (ar[i] > best) { best = ar[i]; bestLag = lag; }
        }
        var guard = Math.round(0.5 * rate), second = 0;
        for (i = 0; i < n; i++) {
            lag = lagAt(i); ov = overlap(lag);
            if (ov < minOverlap || Math.abs(lag - bestLag) <= guard || lag >= ref.length || lag <= -x.length) { continue; }
            if (Math.abs(ar[i]) > second) { second = Math.abs(ar[i]); }
        }
        return { offset: bestLag / rate, confidence: second > 0 ? best / second : (best > 0 ? 99 : 0) };
    };

    /* best offset within +-span s of the coarse one, on a high-rate envelope (normalized dot product) */
    Y.refine = function (refHi, xHi, rate, coarse, span) {
        var c = Math.round(coarse * rate), w = Math.round((span || 0.5) * rate), best = -Infinity, bestL = c, L, i;
        for (L = c - w; L <= c + w; L++) {
            var a = Math.max(0, L), b = Math.min(refHi.length, L + xHi.length);   // overlap on ref's clock
            if (b - a < rate) { continue; }
            var mid = (a + b) >> 1, half = Math.min((b - a) >> 1, Math.round(Y.REFINE_SPAN * rate / 2));
            var s = 0, from = mid - half, to = mid + half;
            for (i = from; i < to; i++) { s += refHi[i] * xHi[i - L]; }
            s /= (to - from);
            if (s > best) { best = s; bestL = L; }
        }
        return bestL / rate;
    };

    /* tracks: [{id, env (100 Hz), hi (1 kHz), seconds}] -> {ref, placed: [{id, offset, confidence}], skipped: [id]} */
    Y.plan = function (tracks) {
        var ref = null, i, t, placed = [], skipped = [];
        for (i = 0; i < tracks.length; i++) { if (!ref || tracks[i].seconds > ref.seconds) { ref = tracks[i]; } }
        if (!ref) { return { ref: null, placed: [], skipped: [] }; }
        for (i = 0; i < tracks.length; i++) {
            t = tracks[i];
            if (t === ref) { placed.push({ id: t.id, offset: 0, confidence: 99 }); continue; }
            var r = Y.offset(ref.env, t.env, 100);
            if (r.confidence < Y.MIN_CONFIDENCE) { skipped.push(t.id); continue; }
            placed.push({ id: t.id, offset: Y.refine(ref.hi, t.hi, 1000, r.offset, 0.5), confidence: r.confidence });
        }
        return { ref: ref.id, placed: placed, skipped: skipped };
    };

    /* sync plan + roles {id: {role:'cam'|'mic', cam:n}} -> {cams:[{nodeId,start,track}], mics:[{nodeId,start}], skipped}
       shifted so the earliest clip starts at 0; Cam n goes on video track n-1 */
    Y.layout = function (plan, roles) {
        var i, p, min = 0, cams = [], mics = [];
        for (i = 0; i < plan.placed.length; i++) { if (plan.placed[i].offset < min) { min = plan.placed[i].offset; } }
        for (i = 0; i < plan.placed.length; i++) {
            p = plan.placed[i];
            var r = roles[p.id] || {}, start = p.offset - min;
            if (r.role === 'mic') { mics.push({ nodeId: p.id, start: start }); }
            else { cams.push({ nodeId: p.id, start: start, end: start + (r.seconds || 0), track: Math.max(0, (r.cam || 1) - 1) }); }
        }
        // a clip that would overlap another on its camera's track (two identical cameras in one folder) gets a new
        // track after all camera tracks: overwriting would silently drop one angle
        cams.sort(function (a, b) { return a.start - b.start; });
        var top = -1, busyUntil = {}, j;
        for (i = 0; i < cams.length; i++) { if (cams[i].track > top) { top = cams[i].track; } }
        for (i = 0; i < cams.length; i++) {
            var c = cams[i];
            if (busyUntil.hasOwnProperty(c.track) && busyUntil[c.track] > c.start + 1e-6) {
                for (j = top + 1; busyUntil.hasOwnProperty(j) && busyUntil[j] > c.start + 1e-6; j++) { }
                c.track = j;
                if (j > top) { top = j; }
            }
            busyUntil[c.track] = Math.max(busyUntil[c.track] || 0, c.end);
            delete c.end;
        }
        return { cams: cams, mics: mics, skipped: plan.skipped.slice(0) };
    };

    root.TidySync = Y;
    if (typeof module === 'object' && module.exports) { module.exports = Y; }
})(typeof window !== 'undefined' ? window : this);
