"""3.0 T4.1 smooth zoom and fades in the Premiere ExtendScript library, run in node against the fake Premiere DOM of
test_wnc_ppro_lib (the mocked bridge: no live Adobe).

build_project gets `camera_keys` (the spec's ease runs; pieces = V1 clip indexes) and `fades` (seconds). Per ease side
it puts 2 Scale + 2 Position keys on the V1 clip, relative to the clip's own value (scale x from/value, position + the
pixel offset difference, normalised or pixel coordinates), each key set to bezier (5). Fades: Opacity keys on every
video item that touches the window, Volume Level keys on every audio item, multiplied into keys already there.
Read-back: `eased` per punch-in run and `faded`. Cases C17-C20, C22-C26, C33 of T41-CASES.md.
Run:  bash tools/test.sh -p test_t41_jsx.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import test_wnc_ppro_lib as W  # noqa: E402  (module import: its TestCases are not collected again here)
from contract import validator as V  # noqa: E402

BEZIER = 5
FPS = 25
F = 1 / FPS

# Premiere's keyframe behaviour the library relies on: setTimeVarying(false) drops the keys, a key added at an existing
# time is the same key, getKeys / getValueAtTime / setInterpolationTypeAtKey; audio clips carry Volume > Level.
FAKE_T41 = r"""
function _s(t) { return (t && typeof t === 'object') ? t.seconds : Number(t); }
Prop.prototype.setTimeVarying = function (b) { if (!b) { this.keys = []; this.interp = {}; } this.tv = b; };
Prop.prototype.isTimeVarying = function () { return this.tv; };
Prop.prototype.addKey = function (t) {
    var s = _s(t);
    for (var i = 0; i < this.keys.length; i++) { if (Math.abs(this.keys[i][0] - s) < 1e-9) { return; } }
    this.keys.push([s, null]); this.keys.sort(function (a, b) { return a[0] - b[0]; });
};
Prop.prototype.setValueAtKey = function (t, v) {
    var s = _s(t);
    for (var i = 0; i < this.keys.length; i++) { if (Math.abs(this.keys[i][0] - s) < 1e-9) { this.keys[i][1] = v; } }
};
Prop.prototype.getKeys = function () { return this.keys.length ? this.keys.map(function (k) { return T(k[0]); }) : null; };
Prop.prototype.getValueAtKey = function (t) {
    var s = _s(t);
    for (var i = 0; i < this.keys.length; i++) { if (Math.abs(this.keys[i][0] - s) < 1e-9) { return this.keys[i][1]; } }
    return null;
};
Prop.prototype.getValueAtTime = function (t) {
    var s = _s(t), k = this.keys;
    if (!k.length) { return this.value; }
    if (s <= k[0][0]) { return k[0][1]; }
    for (var i = 1; i < k.length; i++) {
        if (s <= k[i][0]) {
            var u = (s - k[i - 1][0]) / (k[i][0] - k[i - 1][0]), a = k[i - 1][1], b = k[i][1];
            if (a instanceof Array) { return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]; }
            return a + (b - a) * u;
        }
    }
    return k[k.length - 1][1];
};
// Review C1: Premiere's getValue is only meaningful on a parameter that is not time-varying; on a keyed one it is
// modelled as the value of its first key (what the reviewer's repro showed), so the library must read values first
Prop.prototype.getValue = function () { return (this.tv && this.keys.length) ? this.keys[0][1] : this.value; };
Prop.prototype.setInterpolationTypeAtKey = function (t, m) { (this.interp = this.interp || {})[_s(t).toFixed(6)] = m; return true; };
var _owc = Track.prototype.overwriteClip;
Track.prototype.overwriteClip = function (item, startSec) {
    var r = _owc.call(this, item, startSec); this.clips[this.clips.length - 1]._track = this; return r;
};
Clip.prototype.remove = function () {
    var t = this._track, i = t ? t.clips.indexOf(this) : -1;
    if (i >= 0) { t.clips.splice(i, 1); } return true;
};
function volumeComps(level) { return [new Comp('Volume', 'Internal Volume Stereo', [new Prop('Bypass', false), new Prop('Level', level)])]; }
"""

BUILD = r"""
FAKE.seq = new Sequence_('S', %(settings)s, 1080);
FAKE.seq.audioTracks.forEach(function (tr) { tr.clips.forEach(function (c) { c.components = coll(volumeComps(0.1778)); }); });
%(pre)s
var data = %(data)s;
function dump() {
    function props(c) {
        var o = {};
        c.components.forEach(function (cp) { cp.properties.forEach(function (p) {
            if (p.keys.length) { o[cp.displayName + '/' + p.displayName] = {keys: p.keys, interp: p.interp || {}}; }
        }); });
        return o;
    }
    return {v: FAKE.seq.videoTracks.map(function (tr) { return tr.clips.map(props); }),
            a: FAKE.seq.audioTracks.map(function (tr) { return tr.clips.map(props); })};
}
fs.writeFileSync(TMP + '/job.json', JSON.stringify(data));
var res = JSON.parse(WNCPP.run(TMP + '/job.json'));
var first = dump(), res2 = null;
if (%(twice)s) { res2 = JSON.parse(WNCPP.run(TMP + '/job.json')); }
console.log(JSON.stringify({res: res, res2: res2, first: first, after: dump()}));
"""


def run_build(tc, camera_keys=None, fades=None, graphics=None, pre="", twice=False, project="R.prproj", position=None):
    tmp = Path(tempfile.mkdtemp(prefix="wnc_t41_")).as_posix()
    tc.addCleanup(shutil.rmtree, tmp, True)
    d = W.build_data(tmp, FPS, blur=(), grain=0)
    d["sharpen_v1"] = None
    d["project_path"] = tmp + "/" + project
    d["graphics"] = graphics if graphics is not None else []
    if camera_keys is not None:
        d["camera_keys"] = camera_keys
    if fades is not None:
        d["fades"] = fades
    js = FAKE_T41 + BUILD % {"settings": json.dumps(W.settings(FPS)), "data": json.dumps(d, ensure_ascii=False),
                             "pre": pre, "twice": "true" if twice else "false"}
    return W.node(tc, js, position=position)


def val(sf=1.0, ox=0.0, oy=0.0):
    return {"scale_factor": sf, "offset_x": ox, "offset_y": oy}


def run_both(piece=1, did="EDIT_001", e=6):
    """A punch-in on V1 clip `piece` (the fake has two: 0-4 s and 4-8 s), eased in and out."""
    return {"decision_id": did, "camera": "punch_in", "pieces": [piece, piece],
            "ease_in": {"piece": piece, "frames": e, "from": val(), "value": val(1.1, 0, -40)},
            "ease_out": {"piece": piece, "frames": e, "value": val(1.1, 0, -40), "to": val()},
            "interpolation": "bezier"}


def key_times(p):
    return [round(k[0], 6) for k in p["keys"]]


@unittest.skipUnless(W.NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestEaseKeys(unittest.TestCase):
    def test_c22_two_scale_and_two_position_keys_per_side(self):
        out = run_build(self, camera_keys=[run_both()])
        self.assertTrue(out["res"]["ok"], out["res"])
        c1 = out["after"]["v"][0][1]
        sc, pos = c1["Motion/Scale"], c1["Motion/Position"]
        self.assertEqual(key_times(sc), [0.0, round(6 * F, 6), round(4 - 6 * F, 6), 4.0])
        vals = [k[1] for k in sc["keys"]]
        self.assertAlmostEqual(vals[0], 100 / 1.1, places=4)
        self.assertAlmostEqual(vals[1], 100.0, places=4)
        self.assertAlmostEqual(vals[2], 100.0, places=4)
        self.assertAlmostEqual(vals[3], 100 / 1.1, places=4)
        self.assertEqual(len(pos["keys"]), 4)
        self.assertAlmostEqual(pos["keys"][0][1][1], 0.5 + 40 / 1920, places=6)   # normalised: +40 px of 1920
        self.assertAlmostEqual(pos["keys"][1][1][1], 0.5, places=6)
        self.assertEqual(sorted(set(sc["interp"].values())), [BEZIER])
        self.assertEqual(len(sc["interp"]), 4)
        self.assertEqual(sorted(set(pos["interp"].values())), [BEZIER])
        self.assertNotIn("Motion/Scale", out["after"]["v"][0][0])                 # the other clip is untouched

    def test_c22_pixel_position_coordinates(self):
        out = run_build(self, camera_keys=[run_both()], position=[540, 960])
        pos = out["after"]["v"][0][1]["Motion/Position"]
        self.assertAlmostEqual(pos["keys"][0][1][1], 1000.0, places=4)           # 960 + 40 px

    def test_readback_per_punch_in(self):
        out = run_build(self, camera_keys=[run_both()])
        eased = out["res"]["result"]["eased"]
        self.assertEqual(len(eased), 1)
        e = eased[0]
        self.assertEqual((e["decision_id"], e["pieces"]), ("EDIT_001", [1, 1]))
        self.assertEqual((e["scale_keys"], e["position_keys"], e["ok"]), (4, 4, True))
        # review I2: ExtendScript cannot read the interpolation back, so it is never reported as verified
        self.assertEqual(e["interpolation"], "bezier (set, not read back)")
        self.assertIs(e["interpolation_verified"], False)

    def test_c1_values_are_read_before_any_key_is_written(self):
        """Review C1: both eases on one clip: the ease out's values come from the clip as imported, not from a
        parameter that already holds the ease-in keys."""
        out = run_build(self, camera_keys=[run_both()])
        vals = [k[1] for k in out["after"]["v"][0][1]["Motion/Scale"]["keys"]]
        self.assertAlmostEqual(vals[2], 100.0, places=4)
        self.assertAlmostEqual(vals[3], 100 / 1.1, places=4)
        pos = out["after"]["v"][0][1]["Motion/Position"]["keys"]
        self.assertAlmostEqual(pos[2][1][1], 0.5, places=6)
        self.assertAlmostEqual(pos[3][1][1], 0.5 + 40 / 1920, places=6)

    def test_c1_two_runs_on_neighbouring_clips_read_each_clip_once(self):
        a = run_both(piece=0, did="A")
        a["ease_in"] = None
        b = run_both(piece=1, did="B")
        out = run_build(self, camera_keys=[a, b])
        self.assertEqual([e["ok"] for e in out["res"]["result"]["eased"]], [True, True])
        self.assertAlmostEqual(out["after"]["v"][0][1]["Motion/Scale"]["keys"][3][1], 100 / 1.1, places=4)

    def test_i1_long_eases_on_one_clip_keep_four_keys(self):
        """A 100-frame clip (4 s at 25 fps) with a 50-frame ease in and a 49-frame ease out (the engine never lets
        them meet): four distinct keys, ok."""
        r = run_both(e=50)
        r["ease_out"]["frames"] = 49
        out = run_build(self, camera_keys=[r])
        e = out["res"]["result"]["eased"][0]
        self.assertEqual((e["scale_keys"], e["position_keys"], e["ok"]), (4, 4, True))

    def test_i1_eases_that_meet_are_reported_not_hidden(self):
        out = run_build(self, camera_keys=[run_both(e=50)])         # 50 + 50 on a 100-frame clip: keys merge
        e = out["res"]["result"]["eased"][0]
        self.assertEqual(e["scale_keys"], 3)
        self.assertFalse(e["ok"])

    def test_an_ease_on_one_side_only(self):
        r = run_both()
        r["ease_in"] = None
        out = run_build(self, camera_keys=[r])
        e = out["res"]["result"]["eased"][0]
        self.assertEqual((e["scale_keys"], e["position_keys"]), (2, 2))

    def test_a_run_over_two_clips(self):
        r = run_both()
        r["pieces"] = [0, 1]
        r["ease_in"]["piece"] = 0
        out = run_build(self, camera_keys=[r])
        self.assertEqual(len(out["after"]["v"][0][0]["Motion/Scale"]["keys"]), 2)
        self.assertEqual(len(out["after"]["v"][0][1]["Motion/Scale"]["keys"]), 2)
        self.assertEqual(out["res"]["result"]["eased"][0]["scale_keys"], 4)

    def test_c23_stale_keys_are_cleared_and_a_rerun_adds_no_duplicates(self):
        pre = ("var _m = FAKE.seq.videoTracks[0].clips[1].components[1];"
               "_m.properties[1].setTimeVarying(true); _m.properties[1].addKey(1.234); _m.properties[1].setValueAtKey(1.234, 50);")
        out = run_build(self, camera_keys=[run_both()], pre=pre, twice=True)
        sc = out["after"]["v"][0][1]["Motion/Scale"]
        self.assertNotIn(1.234, key_times(sc))
        self.assertEqual(len(sc["keys"]), 4)
        self.assertEqual(out["res2"]["result"]["eased"], out["res"]["result"]["eased"])

    def test_c24_a_missing_clip_is_reported_not_fatal(self):
        out = run_build(self, camera_keys=[run_both(piece=5)])
        self.assertTrue(out["res"]["ok"], out["res"])
        e = out["res"]["result"]["eased"][0]
        self.assertFalse(e["ok"])
        self.assertTrue(any("5" in x for x in out["res"]["result"]["log"]), out["res"]["result"]["log"])

    def test_c25_without_interpolation_api_the_keys_stay_and_it_is_not_ok(self):
        out = run_build(self, camera_keys=[run_both()], pre="delete Prop.prototype.setInterpolationTypeAtKey;")
        e = out["res"]["result"]["eased"][0]
        self.assertEqual(e["scale_keys"], 4)
        self.assertEqual(e["interpolation"], "linear (fallback)")
        self.assertFalse(e["ok"])

    def test_c26_arabic_path_and_ids_round_trip(self):
        out = run_build(self, camera_keys=[run_both(did="قص_١")], project="مشروع تجربة.prproj")
        self.assertTrue(out["res"]["ok"], out["res"])
        self.assertEqual(out["res"]["result"]["eased"][0]["decision_id"], "قص_١")

    def test_c14_no_camera_keys_is_todays_build(self):
        out = run_build(self)
        self.assertNotIn("Motion/Scale", out["after"]["v"][0][1])
        self.assertNotIn("eased", out["res"]["result"])                   # review 2 M-f: nothing asked, nothing reported
        self.assertNotIn("faded", out["res"]["result"])

    def test_r4_m3_a_throw_on_the_second_clip_restores_the_first(self):
        r = run_both()
        r["pieces"] = [0, 1]
        r["ease_in"]["piece"] = 0
        pre = ("FAKE.seq.videoTracks[0].clips[1].components[1].properties[0].getValue = function () {"
               " throw new Error('host refused'); };")
        out = run_build(self, camera_keys=[r], pre=pre)
        self.assertTrue(out["res"]["ok"], out["res"])
        e = out["res"]["result"]["eased"][0]
        self.assertFalse(e["ok"])
        self.assertIn("clip 1", e.get("error", ""))
        self.assertNotIn("Motion/Scale", out["after"]["v"][0][0])          # clip 0 had its keys: put back
        self.assertNotIn("Motion/Position", out["after"]["v"][0][0])

    def test_r5_min3_a_throw_in_the_read_back_restores_the_clips(self):
        """Round 5 MIN-3: a throw outside the per-side guard (here the key count read-back) rolls the clips back too."""
        out = run_build(self, camera_keys=[run_both()], pre="WNCPP.keyCount = function () { throw new Error('read'); };")
        self.assertTrue(out["res"]["ok"], out["res"])
        e = out["res"]["result"]["eased"][0]
        self.assertFalse(e["ok"])
        self.assertIn("read", e.get("error", ""))
        self.assertNotIn("Motion/Scale", out["after"]["v"][0][1])
        self.assertNotIn("Motion/Position", out["after"]["v"][0][1])

    def test_md_an_error_restores_the_clip(self):
        """Review 2 M-d: a key that throws half way: the clip goes back to its imported values, no keys left."""
        pre = ("var _sv = Prop.prototype.setValueAtKey; Prop.prototype.setValueAtKey = function (t, v) {"
               " if (this.displayName === 'Position') { throw new Error('host refused'); } return _sv.call(this, t, v); };")
        out = run_build(self, camera_keys=[run_both()], pre=pre)
        self.assertTrue(out["res"]["ok"], out["res"])
        e = out["res"]["result"]["eased"][0]
        self.assertFalse(e["ok"])
        self.assertIn("clip 1", e.get("error", ""))
        c1 = out["after"]["v"][0][1]
        self.assertNotIn("Motion/Scale", c1)
        self.assertNotIn("Motion/Position", c1)

    def test_readback_fits_the_contract(self):
        out = run_build(self, camera_keys=[run_both()], fades={"video_in_s": 1, "video_out_s": 0, "audio_in_s": 0,
                                                                "audio_out_s": 1, "end_s": 8})
        self.assertEqual(V.validate(out["res"]["result"], "build_project#/$defs/readback"), [])


@unittest.skipUnless(W.NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestFades(unittest.TestCase):
    """Review 2 IMP-2: the picture fade is ONE black matte on the top track over the fade windows (never Opacity keys on
    each layer: overlapping layers fading separately ghost); sound fades key Volume > Level on the named tracks."""
    FADES = {"video_in_s": 1.0, "video_out_s": 1.0, "audio_in_s": 0.5, "audio_out_s": 2.0, "end_s": 8.0}

    def fades(self, **kw):
        tmp = Path(tempfile.mkdtemp(prefix="wnc_t41m_")).as_posix()
        self.addCleanup(shutil.rmtree, tmp, True)
        return dict(dict(self.FADES, matte={"png": tmp + "/black.png", "track_index": 3}, audio_tracks=[1, 2]), **kw)

    def test_r4_m9_no_named_tracks_fades_no_audio(self):
        """An SFX can never be faded: with no audio_tracks (or an empty list) the sound fade keys nothing."""
        for at in (None, []):
            with self.subTest(audio_tracks=at):
                fd = self.fades()
                if at is None:
                    fd.pop("audio_tracks")
                else:
                    fd["audio_tracks"] = at
                out = run_build(self, fades=fd)
                for tr in out["after"]["a"]:
                    self.assertNotIn("Volume/Level", tr[0])
                self.assertEqual(out["res"]["result"]["faded"]["audio"], [])

    def test_r4_m4_a_crash_in_the_fades_reads_back_in_the_schema_shape(self):
        out = run_build(self, fades=self.fades(), pre="WNCPP.placeMatte = function () { throw new Error('boom'); };")
        self.assertEqual(out["res"]["result"]["faded"], {"matte": [], "audio": [], "ok": False})
        self.assertEqual(V.validate(out["res"]["result"], "build_project#/$defs/readback"), [])

    def test_r4_m5_level_found_by_match_name_in_another_language(self):
        pre = ("FAKE.seq.audioTracks.forEach(function (tr) { tr.clips.forEach(function (c) {"
               " c.components = coll([new Comp('Lautstaerke', 'Internal Volume Stereo', [new Prop('Umgehen', false),"
               " new Prop('Pegel', 0.1778)])]); }); });")
        out = run_build(self, fades=self.fades(), pre=pre)
        self.assertIn("Lautstaerke/Pegel", out["after"]["a"][0][0])
        self.assertEqual(len(out["res"]["result"]["faded"]["audio"]), 2)

    def test_imp2_the_matte_covers_both_windows(self):
        out = run_build(self, fades=self.fades())
        top = out["after"]["v"][3]
        self.assertEqual(len(top), 2)
        a, b = top[0]["Opacity/Opacity"]["keys"], top[1]["Opacity/Opacity"]["keys"]
        self.assertEqual([(round(t, 6), v) for t, v in a], [(0.0, 100), (1.0, 0)])
        self.assertEqual([(round(t, 6), v) for t, v in b], [(0.0, 0), (1.0, 100)])     # in-point based, 7-8 s
        fd = out["res"]["result"]["faded"]
        self.assertEqual([(round(m["start"], 6), round(m["end"], 6), m["keys"]) for m in fd["matte"]],
                         [(0.0, 1.0, 2), (7.0, 8.0, 2)])
        self.assertTrue(fd["ok"])
        for clip in out["after"]["v"][0]:                       # no layer of its own gets an opacity key
            self.assertNotIn("Opacity/Opacity", clip)

    def test_imp2_a_graphic_keeps_its_own_animation(self):
        g = [{"id": "HOOK", "png": "x/hook.png", "track_index": 1, "start_s": 0, "end_s": 3, "anim": "text_pop"}]
        out = run_build(self, fades=dict(self.fades(), video_out_s=0), graphics=g)
        op = {round(k[0], 6): k[1] for k in out["after"]["v"][1][0]["Opacity/Opacity"]["keys"]}
        self.assertEqual(op[round(2 * F, 6)], 100)              # the pop as placed: the matte does the fading

    def test_imp2_no_matte_track_is_reported_never_a_per_layer_fade(self):
        out = run_build(self, fades=dict(self.fades(), matte={"png": "x/black.png", "track_index": 9}))
        fd = out["res"]["result"]["faded"]
        self.assertFalse(fd["ok"])
        self.assertEqual(fd["matte"], [])
        self.assertTrue(any("fade" in x.lower() for x in out["res"]["result"]["log"]))
        for clip in out["after"]["v"][0]:
            self.assertNotIn("Opacity/Opacity", clip)

    def test_md_a_failed_matte_is_removed(self):
        pre = ("var _sv2 = Prop.prototype.setValueAtKey; Prop.prototype.setValueAtKey = function (t, v) {"
               " if (this.displayName === 'Opacity') { throw new Error('host refused'); } return _sv2.call(this, t, v); };")
        out = run_build(self, fades=self.fades(), pre=pre)
        self.assertEqual(out["after"]["v"][3], [])              # nothing half-placed stays on the top track
        self.assertFalse(out["res"]["result"]["faded"]["ok"])
        self.assertTrue(any("matte" in x for x in out["res"]["result"]["log"]))

    def test_c20_audio_fade_on_the_named_tracks(self):
        out = run_build(self, fades=self.fades())
        for tr in out["after"]["a"]:
            lv = tr[0]["Volume/Level"]
            self.assertAlmostEqual(lv["keys"][0][1], 0.0)
            self.assertAlmostEqual(lv["keys"][-1][1], 0.0)
            self.assertIn(0.5, [round(k[0], 6) for k in lv["keys"]])
            self.assertIn(6.0, [round(k[0], 6) for k in lv["keys"]])
        self.assertEqual(len(out["res"]["result"]["faded"]["audio"]), 2)

    def test_r3_only_the_named_audio_tracks_fade(self):
        """Round 3, item 3: the job names the dialogue / music tracks; an SFX track (here A2) is never faded."""
        out = run_build(self, fades=self.fades(audio_tracks=[1]))
        self.assertIn("Volume/Level", out["after"]["a"][0][0])
        self.assertNotIn("Volume/Level", out["after"]["a"][1][0])
        self.assertEqual([x["track"] for x in out["res"]["result"]["faded"]["audio"]], [1])

    def test_c19_the_music_fade_out_is_kept(self):
        pre = ("var _l = FAKE.seq.audioTracks[1].clips[0].components[0].properties[1];"
               "_l.setTimeVarying(true); _l.addKey(7); _l.setValueAtKey(7, 0.1778); _l.addKey(8); _l.setValueAtKey(8, 0);")
        out = run_build(self, fades=self.fades(), pre=pre)
        at = {round(k[0], 6): k[1] for k in out["after"]["a"][1][0]["Volume/Level"]["keys"]}
        self.assertAlmostEqual(at[8.0], 0.0)
        self.assertIn(7.0, at)
        self.assertLessEqual(at[7.0], 0.1778 * 0.5 + 1e-6)
        self.assertAlmostEqual(at[6.0], 0.1778, places=4)

    def test_c17_fade_and_a_punch_at_frame_0_both_land(self):
        r = run_both(piece=0)
        r["ease_in"] = None
        out = run_build(self, camera_keys=[r], fades=self.fades())
        self.assertEqual(len(out["after"]["v"][0][0]["Motion/Scale"]["keys"]), 2)
        self.assertEqual(len(out["after"]["v"][3]), 2)

    def test_c15_no_fades_nothing_keyed(self):
        out = run_build(self)
        self.assertEqual(out["after"]["v"][3], [])
        self.assertNotIn("Volume/Level", out["after"]["a"][0][0])

    def test_r3_slow_push_keys_span_the_clip(self):
        r = {"decision_id": "S", "camera": "slow_push", "pieces": [1, 1],
             "ease_in": {"piece": 1, "frames": 99, "from": val(), "value": val(1.2)}, "ease_out": None,
             "interpolation": "bezier"}
        out = run_build(self, camera_keys=[r])
        sc = out["after"]["v"][0][1]["Motion/Scale"]
        self.assertEqual(key_times(sc), [0.0, round(99 * F, 6)])
        self.assertAlmostEqual(sc["keys"][0][1], 100 / 1.2, places=4)
        self.assertTrue(out["res"]["result"]["eased"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
