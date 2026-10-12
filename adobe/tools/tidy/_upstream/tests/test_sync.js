// run from tidy/: jsc tests/test_sync.js
var window = this;
load('js/sync.js');
var Y = window.TidySync, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }

var RATE = 8000, seed = 1;
function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5; }
/* speech-like signal: noise bursts with random lengths and loudness */
function speech(seconds, s0) {
    seed = s0;
    var n = Math.round(seconds * RATE), a = new Float32Array(n), i = 0;
    while (i < n) {
        var len = Math.round((0.08 + Math.abs(rnd()) * 0.6) * RATE), amp = Math.abs(rnd()) < 0.15 ? 0 : 0.1 + Math.abs(rnd());
        for (var k = 0; k < len && i < n; k++, i++) { a[i] = amp * rnd(); }
    }
    return a;
}
function slice(a, s0, s1) { return a.subarray(Math.round(s0 * RATE), Math.round(s1 * RATE)); }
function noisy(a, level, s0) { seed = s0; var b = new Float32Array(a.length); for (var i = 0; i < a.length; i++) { b[i] = a[i] * 0.7 + level * rnd(); } return b; }
function track(id, samples) { return { id: id, env: Y.envelope(samples, RATE, 100), hi: Y.envelope(samples, RATE, 1000), seconds: samples.length / RATE }; }

var full = speech(90, 7);
var mic = slice(full, 0, 90);                          // the recorder runs the whole time
var camA = noisy(slice(full, 3.217, 70), 0.05, 11);    // camera started 3.217 s after the recorder
var camB = noisy(slice(full, 20, 85.5), 0.05, 13);     // started 20 s in
var other = speech(40, 99);                            // a clip from another shoot

var env = Y.envelope(mic, RATE, 100);
ok(env.length === 9000, 'envelope has one value per 10 ms: ' + env.length);

var r = Y.offset(Y.envelope(mic, RATE, 100), Y.envelope(camA, RATE, 100), 100);
ok(Math.abs(r.offset - 3.217) < 0.02 && r.confidence >= 3, 'coarse offset of a camera that started later: ' + JSON.stringify(r));
var fine = Y.refine(Y.envelope(mic, RATE, 1000), Y.envelope(camA, RATE, 1000), 1000, r.offset, 0.5);
ok(Math.abs(fine - 3.217) <= 0.002, 'refined to within 2 ms: ' + fine);

// a clip that started before the reference: negative offset
var late = slice(full, 12.5, 90), early = slice(full, 0, 30);
var r2 = Y.offset(Y.envelope(late, RATE, 100), Y.envelope(early, RATE, 100), 100);
ok(Math.abs(r2.offset + 12.5) < 0.02, 'negative offset when the clip starts before the reference: ' + r2.offset);

var pl = Y.plan([track('camA', camA), track('mic', mic), track('camB', camB), track('other', other)]);
ok(pl.ref === 'mic', 'the longest recording is the reference: ' + pl.ref);
var at = {}; for (var i = 0; i < pl.placed.length; i++) { at[pl.placed[i].id] = pl.placed[i].offset; }
ok(Math.abs(at.mic) < 1e-9 && Math.abs(at.camA - 3.217) <= 0.002 && Math.abs(at.camB - 20) <= 0.002, 'all placed within 2 ms: ' + JSON.stringify(at));
ok(pl.skipped.length === 1 && pl.skipped[0] === 'other' && at.other === undefined, 'a clip from another shoot is left out, never placed at a guess');
// streaming path: the panel only keeps the mean power per 1 ms, never the whole recording
function powerHi(samples) { var n = Math.floor(samples.length / 8), p = new Float64Array(n); for (var i = 0; i < n; i++) { var s = 0; for (var k = 0; k < 8; k++) { s += samples[i * 8 + k] * samples[i * 8 + k]; } p[i] = s / 8; } return p; }
var e2 = Y.fromPower(powerHi(camA));
ok(e2.env.length === Math.floor(e2.hi.length / 10) && Math.abs(e2.seconds - camA.length / RATE) < 0.002, 'envelopes from 1 ms power');
var r3 = Y.offset(Y.fromPower(powerHi(mic)).env, e2.env, 100);
ok(Math.abs(r3.offset - 3.217) < 0.02 && r3.confidence >= 3, 'power envelopes sync the same: ' + JSON.stringify(r3));
var ref = Y.fromPower(powerHi(mic));
ok(Math.abs(Y.refine(ref.hi, e2.hi, 1000, r3.offset, 0.5) - 3.217) <= 0.002, 'and refine the same');
function le32(n) { return String.fromCharCode(n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >>> 24) & 255); }
function le16(n) { return String.fromCharCode(n & 255, (n >> 8) & 255); }
var hdr = 'RIFF' + le32(0) + 'WAVE' + 'fmt ' + le32(16) + le16(1) + le16(2) + le32(48000) + le32(192000) + le16(4) + le16(16) +
          'LIST' + le32(4) + 'INFO' + 'data' + le32(960000);
var wi = Y.wavInfo(hdr);
ok(wi && wi.rate === 48000 && wi.channels === 2 && wi.bits === 16 && wi.dataOffset === 56 && wi.dataSize === 960000, 'WAV header, skipping other chunks: ' + JSON.stringify(wi));
ok(Y.wavInfo('RIFF....WAVEfmt ') === null && Y.wavInfo('not a wav at all, not a wav at all, not a wav at all') === null, 'not a usable WAV -> null');
var lay = Y.layout({ placed: [{ id: 'mic1', offset: 0 }, { id: 'a1', offset: -2.5 }, { id: 'b1', offset: 20 }, { id: 'a2', offset: 400 }], skipped: ['x'] },
                   { mic1: { role: 'mic' }, a1: { role: 'cam', cam: 1 }, a2: { role: 'cam', cam: 1 }, b1: { role: 'cam', cam: 2 }, x: { role: 'cam', cam: 2 } });
ok(lay.cams.length === 3 && lay.mics.length === 1, 'cams and mics split');
var st = {}; for (i = 0; i < lay.cams.length; i++) { st[lay.cams[i].nodeId] = lay.cams[i]; }
ok(st.a1.start === 0 && st.a1.track === 0 && st.a2.track === 0 && st.b1.track === 1 && Math.abs(st.b1.start - 22.5) < 1e-9 && Math.abs(lay.mics[0].start - 2.5) < 1e-9,
   'everything shifted so the earliest clip starts at 0; Cam n on track n-1: ' + JSON.stringify(lay));
ok(lay.skipped.length === 1 && lay.skipped[0] === 'x', 'skipped clips are reported');
// two clips of one camera that overlap after sync (two identical cameras kept in one folder): never overwrite
var lay2 = Y.layout({ placed: [{ id: 'm', offset: 0 }, { id: 'x1', offset: 5 }, { id: 'x2', offset: 30 }, { id: 'y1', offset: 10 }, { id: 'x3', offset: 200 }], skipped: [] },
                    { m: { role: 'mic', seconds: 300 }, x1: { role: 'cam', cam: 1, seconds: 100 }, x2: { role: 'cam', cam: 1, seconds: 100 },
                      x3: { role: 'cam', cam: 1, seconds: 50 }, y1: { role: 'cam', cam: 2, seconds: 100 } });
var tr = {}; for (i = 0; i < lay2.cams.length; i++) { tr[lay2.cams[i].nodeId] = lay2.cams[i].track; }
ok(tr.x1 === 0 && tr.y1 === 1 && tr.x2 === 2 && tr.x3 === 0, 'an overlapping clip of the same camera goes to a new track, a later one stays: ' + JSON.stringify(tr));
print(fails ? fails + ' FAILED' : 'ALL PASS');
