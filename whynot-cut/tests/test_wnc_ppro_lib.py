"""3.0 T6.3 Task 3 - the Premiere ExtendScript library's carry-overs, run in node against a fake Premiere DOM.

* slide: the checklist slide-in is 60 SEQUENCE pixels (60 / W normalised), W = Sequence.frameSizeHorizontal, else the
  settings' videoFrameWidth, else 1080 (it was the literal 60 / 1080: far too large on a 1920-wide sequence);
* frame constant: WNCPP.F is one frame of the built sequence (videoFrameRate.seconds, else 1/24); build_project sets
  it and reports it as frame_s, so text_pop at 25 fps keys at 2 and 4 frames of 25 fps;
* match names: effects are added by QE display name, then checked by match name (Premiere 26: "Gaussian Blur" is the
  new AE.Impact_Blur_FX; the classic blur is "Gaussian Blur (Legacy)", AE.ADBE Gaussian Blur 2). compByMatch finds a
  component by match name; a display name that adds another effect is reported {ok: false, got}; build_project's
  readback gains `effects`;
* close_project_path: save "always" (default) | "if_clean", projectDirty from pr.dirty / pr.isDirty (else null), and a
  readback that always carries dirty, saved and dirty_api (checked against the v4 contract schema).
Run:  bash tools/test.sh -p test_wnc_ppro_lib.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from contract import validator as V  # noqa: E402

NODE = shutil.which("node")
LIB = SK / "templates" / "premiere" / "wnc_ppro_lib.jsx"

# Premiere 26.5's effect names (docs/adobe/uxp-parity.md "Match names (verified live)"): display -> match name, params
P26_EFFECTS = {
    "Gaussian Blur": ["AE.Impact_Blur_FX", ["Blur Amount"]],
    # the third parameter (Repeat Edge Pixels) has a blank display name in Premiere 26 (uxp-parity.md row E4)
    "Gaussian Blur (Legacy)": ["AE.ADBE Gaussian Blur 2", ["Blurriness", "Blur Dimensions", " "]],
    "Sharpen": ["AE.ADBE Sharpen", ["Sharpen Amount"]],
    "Noise": ["AE.ADBE_Noise_FX", ["Intensity"]],
    "Crop": ["AE.ADBE AECrop", ["Left", "Top", "Right", "Bottom"]],
}

# A fake Premiere: the DOM parts the library touches (projects, bins, sequences, tracks, clips, components, properties,
# keyframes) and QE's effect lookup. Effects append to the end of a clip's chain, as in Premiere (parity note 8).
FAKE_JS = r"""
var fs = require('fs'), path = require('path');
function coll(a) { Object.defineProperty(a, 'numItems', {get: function () { return this.length; }}); return a; }
function File(p) {
    if (!(this instanceof File)) { return new File(p); }
    this.fsName = String(p); this.exists = fs.existsSync(this.fsName); this.encoding = 'BINARY';
}
File.prototype.open = function () { this._t = fs.readFileSync(this.fsName, 'utf8'); return true; };
File.prototype.read = function () { return this._t; };
File.prototype.close = function () { return true; };
function Folder(p) { this.fsName = String(p); }
function Time() { this.seconds = 0; }
Object.defineProperty(Time.prototype, 'ticks', {get: function () { return String(Math.round(this.seconds * 254016000000)); }});
function T(s) { var t = new Time(); t.seconds = s; return t; }
function Prop(name, value) { this.displayName = name; this.value = value; this.keys = []; this.tv = false; }
Prop.prototype.getValue = function () { return this.value; };
Prop.prototype.setValue = function (v) { this.value = v; return true; };
Prop.prototype.setTimeVarying = function (b) { this.tv = b; };
Prop.prototype.addKey = function (t) { this.keys.push([t, null]); };
Prop.prototype.setValueAtKey = function (t, v) { for (var i = 0; i < this.keys.length; i++) { if (this.keys[i][0] === t) { this.keys[i][1] = v; } } };
function Comp(display, match, props) {
    this.displayName = display; this.matchName = match;
    this.properties = coll(props.map(function (p) { return p instanceof Prop ? p : new Prop(p, 0); }));
}
function stillComps() {
    return [new Comp('Opacity', 'AE.ADBE Opacity', [new Prop('Opacity', 100)]),
            new Comp('Motion', 'AE.ADBE Motion', [new Prop('Position', globalThis.POSITION || [0.5, 0.5]), new Prop('Scale', 100),
                                                 new Prop('Crop Left', 0)])];
}
function Clip(name, start, end) {
    this.name = name; this.start = T(start); this.end = T(end); this.inPoint = T(0); this.components = coll(stillComps());
}
function Track(name) { this.name = name; this.clips = coll([]); }
Track.prototype.overwriteClip = function (item, startSec) { this.clips.push(new Clip(item.name, startSec, startSec + 5)); return true; };
var FAKE = {effects: {}, saved: 0};
function Sequence_(name, settings, fsh) {
    this.name = name; this.sequenceID = 'seq-' + name; this._st = settings;
    if (fsh !== undefined) { this.frameSizeHorizontal = fsh; }
    var v = [], a = [];
    for (var i = 0; i < 4; i++) { v.push(new Track('Video ' + (i + 1))); }
    for (var j = 0; j < 2; j++) { a.push(new Track('Audio ' + (j + 1))); }
    v[0].clips.push(new Clip('EP.mp4', 0, 4)); v[0].clips.push(new Clip('EP.mp4', 4, 8));
    a[0].clips.push(new Clip('EP.mp4', 0, 8)); a[1].clips.push(new Clip('EP.mp4', 0, 8));
    this.videoTracks = v; this.audioTracks = a;
    Object.defineProperty(v, 'numTracks', {get: function () { return this.length; }});
    Object.defineProperty(a, 'numTracks', {get: function () { return this.length; }});
    this.markers = {createMarker: function (t) { return {}; }};
}
Sequence_.prototype.getSettings = function () { return JSON.parse(JSON.stringify(this._st)); };
Sequence_.prototype.setSettings = function (st) { this._st = JSON.parse(JSON.stringify(st)); return true; };
globalThis.Sequence = {CAPTION_FORMAT_SUBTITLE: 6};
globalThis.ProjectItemType = {BIN: 2, CLIP: 1};
function Item(p) { this.type = 1; this.name = path.basename(p); this._p = p; }
Item.prototype.getMediaPath = function () { return this._p; };
Item.prototype.moveBin = function () { return true; };
function Bin(name) { this.type = 2; this.name = name; this.children = coll([]); }
Bin.prototype.createBin = function (n) { this.children.push(new Bin(n)); };
function project(p) {
    var seqs = coll([]);
    Object.defineProperty(seqs, 'numSequences', {get: function () { return this.length; }});
    return {path: p, rootItem: new Bin('root'), sequences: seqs,
            openSequence: function () { return true; }, save: function () { FAKE.saved++; return true; },
            importFiles: function (files, quiet, bin) {
                files.forEach(function (f) {
                    if (/\.xml$/i.test(f)) { seqs.push(FAKE.seq); } else { bin.children.push(new Item(f)); }
                });
                return true;
            }};
}
globalThis.app = {version: '26.5.2', build: '7', projects: coll([]),
    newProject: function (p) { app.project = project(p); return true; }, enableQE: function () {}};
globalThis.$ = {os: 'Windows', sleep: function () {}};
globalThis.qe = {project: {
    getVideoEffectByName: function (n) { return FAKE.effects[n] ? {name: n} : null; },
    getActiveSequence: function () { return {getVideoTrackAt: function (t) { return {getItemAt: function (i) {
        var comps = function () { return FAKE.seq.videoTracks[t].clips[i].components; };
        var qi = {addVideoEffect: function (fx) {
            var e = FAKE.effects[fx.name];
            comps().push(new Comp(fx.name, e[0], e[1]));
        }};
        if (FAKE.qeRemove !== false) {      // QE's component remove (FAKE.qeRemove = false: a Premiere without it)
            Object.defineProperty(qi, 'numComponents', {get: function () { return comps().length; }});
            qi.getComponentAt = function (k) { return {remove: function () { comps().splice(k, 1); return true; }}; };
        }
        return qi;
    }}; }}; }}};
globalThis.File = File; globalThis.Folder = Folder; globalThis.Time = Time;
"""


def node(tc, scenario: str, effects=None, position=None) -> object:
    """Run `scenario` (JS that ends with console.log(JSON.stringify(...))) after the fake host and the library."""
    d = Path(tempfile.mkdtemp(prefix="wnc_ppro_"))
    tc.addCleanup(shutil.rmtree, d, True)
    js = (FAKE_JS + "FAKE.effects = " + json.dumps(P26_EFFECTS if effects is None else effects) + ";\n"
          + ("globalThis.POSITION = " + json.dumps(position) + ";\n" if position else "")
          + "(0, eval)(fs.readFileSync(" + json.dumps(str(LIB)) + ", 'utf8'));\n"
          + "var TMP = " + json.dumps(str(d)) + ";\n" + scenario)
    f = d / "run.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    tc.assertEqual(r.returncode, 0, r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def settings(fps: float, w: int = 1080, h: int = 1920) -> dict:
    return {"videoFrameWidth": w, "videoFrameHeight": h, "videoFrameRate": {"seconds": 1 / fps, "ticks": "x"},
            "previewCodec": "apcs", "compositeLinearColor": True, "maximumBitDepth": False,
            "maximumRenderQuality": False}


# one still placed with an animation; prints the keyframes of the clip it made on V2
PLACE = r"""
var seq = new Sequence_('S', %(settings)s, %(fsh)s);
FAKE.seq = seq;
WNCPP.F = %(F)s;
var r = WNCPP.placeStill(seq, 1, {name: 'g.png'}, {id: 'G1', start_s: 1, end_s: 3, anim: %(anim)s}, []);
var c = seq.videoTracks[1].clips[0], out = {placed: r, keys: {}};
for (var i = 0; i < c.components.length; i++) {
    var cp = c.components[i];
    for (var j = 0; j < cp.properties.length; j++) { var p = cp.properties[j]; if (p.keys.length) { out.keys[p.displayName] = p.keys; } }
}
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestSlideDistance(unittest.TestCase):
    def place(self, anim, fsh="undefined", st=None, F="1 / 24", position=None):
        js = PLACE % {"settings": json.dumps(st or settings(24)), "fsh": fsh, "F": F, "anim": json.dumps(anim)}
        return node(self, js, position=position)

    def test_slide_is_60_sequence_pixels_at_1080_and_1920(self):
        for w in (1080, 1920):
            out = self.place("slide", fsh=str(w), st=settings(24, w, 1080 if w == 1920 else 1920))
            pos = out["keys"]["Position"]
            self.assertAlmostEqual(pos[0][1][0], 0.5 + 60 / w, places=12, msg=w)
            self.assertEqual(pos[0][1][1], 0.5)
            self.assertEqual(pos[1][1], [0.5, 0.5])
            self.assertAlmostEqual(pos[1][0], 5 / 24, places=12)

    def test_1080_wide_is_unchanged(self):
        out = self.place("slide", fsh="1080")
        self.assertAlmostEqual(out["keys"]["Position"][0][1][0], 0.5 + 60 / 1080, places=15)

    def test_width_falls_back_to_the_settings_then_1080(self):
        for fsh, st, want in (("undefined", settings(24, 1920, 1080), 1920), ("0", settings(24, 1440, 1080), 1440),
                              ("undefined", {}, 1080), ("'x'", {"videoFrameWidth": -5}, 1080)):
            js = ("var s = new Sequence_('S', %s, %s); console.log(JSON.stringify(WNCPP.seqWidth(s)));"
                  % (json.dumps(st), fsh))
            self.assertEqual(node(self, js), want, (fsh, st))

    def test_pixel_coordinates_still_move_60_pixels(self):
        out = self.place("slide", fsh="1920", position=[960, 540])
        self.assertEqual(out["keys"]["Position"][0][1], [1020, 540])


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestFrameConstant(unittest.TestCase):
    def test_frame_seconds_from_the_sequence(self):
        for st, want in ((settings(25), 1 / 25), (settings(30000 / 1001), 1001 / 30000), ({}, 1 / 24),
                         ({"videoFrameRate": {"seconds": 0}}, 1 / 24), ({"videoFrameRate": {"seconds": 5}}, 1 / 24)):
            js = "console.log(JSON.stringify(WNCPP.frameSeconds(new Sequence_('S', %s))));" % json.dumps(st)
            self.assertAlmostEqual(node(self, js), want, places=12, msg=st)

    def test_text_pop_at_25_fps(self):
        js = PLACE % {"settings": json.dumps(settings(25)), "fsh": "1080",
                      "F": "WNCPP.frameSeconds(new Sequence_('x', %s))" % json.dumps(settings(25)),
                      "anim": json.dumps("text_pop")}
        out = node(self, js)
        self.assertEqual([k[0] for k in out["keys"]["Opacity"]], [0, 2 / 25])
        self.assertEqual([k[1] for k in out["keys"]["Opacity"]], [0, 100])
        self.assertEqual([k[0] for k in out["keys"]["Scale"]], [0, 4 / 25])


def build_data(tmp: str, fps: float = 25, blur=(0,), grain=30) -> dict:
    return {"action": "build_project", "project_path": tmp + "/R.prproj", "overwrite_existing": True,
            "xml_path": tmp + "/R.xml", "sequence_name": "S", "settings": {"videoFrameRate": {"seconds": 1 / fps, "ticks": str(round(254016000000 / fps))}},
            "graphics": [{"id": "G1", "png": tmp + "/g1.png", "track_index": 1, "start_s": 1, "end_s": 3,
                          "anim": "text_pop"}],
            "blur_v1_clips": list(blur), "sharpen_v1": {"amount": 20, "grain": grain}, "srt_path": None,
            "native_caption_track": False, "track_names": {"video": ["V1"], "audio": ["A1"]}, "markers": []}


BUILD = r"""
FAKE.seq = new Sequence_('S', %(settings)s, %(fsh)s);
var data = %(data)s;
fs.writeFileSync(TMP + '/job.json', JSON.stringify(data));
var res = JSON.parse(WNCPP.run(TMP + '/job.json'));
var c = FAKE.seq.videoTracks[1].clips[0], keys = {};
for (var i = 0; i < c.components.length; i++) {
    var cp = c.components[i];
    for (var j = 0; j < cp.properties.length; j++) { var p = cp.properties[j]; if (p.keys.length) { keys[p.displayName] = p.keys.map(function (k) { return k[0]; }); } }
}
var v1 = FAKE.seq.videoTracks[0].clips.map(function (cl) {
    return cl.components.map(function (cp) { return [cp.matchName, cp.properties.map(function (p) { return [p.displayName, p.value]; })]; });
});
console.log(JSON.stringify({res: res, keys: keys, v1: v1}));
"""


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestBuildProject(unittest.TestCase):
    def build(self, fps=25, effects=None, **kw):
        tmp = Path(tempfile.mkdtemp(prefix="wnc_build_")).as_posix()
        self.addCleanup(shutil.rmtree, tmp, True)
        js = BUILD % {"settings": json.dumps(settings(24)), "fsh": "1080",
                      "data": json.dumps(build_data(tmp, fps, **kw))}
        return node(self, js, effects=effects)

    def test_frame_constant_is_set_and_read_back(self):
        out = self.build(fps=25)
        self.assertTrue(out["res"]["ok"], out["res"])
        rb = out["res"]["result"]
        self.assertAlmostEqual(rb["frame_s"], 1 / 25, places=12)
        self.assertEqual(out["keys"]["Opacity"], [0, 2 / 25])           # text_pop counts frames of THIS sequence
        self.assertEqual(out["keys"]["Scale"], [0, 4 / 25])
        self.assertEqual(len(rb["placed"]), 1)
        out24 = self.build(fps=24)
        self.assertAlmostEqual(out24["res"]["result"]["frame_s"], 1 / 24, places=12)
        self.assertEqual(out24["keys"]["Opacity"], [0, 2 / 24])

    def test_effects_by_match_name_pick_the_legacy_blur(self):
        out = self.build()
        rb = out["res"]["result"]
        fx = [(e["kind"], e["clip"], e["ok"], e["name"], e["got"]) for e in rb["effects"]]
        self.assertEqual(fx, [("blur", 0, True, "Gaussian Blur (Legacy)", "AE.ADBE Gaussian Blur 2"),
                              ("sharpen", 1, True, "Sharpen", "AE.ADBE Sharpen"),
                              ("noise", 1, True, "Noise", "AE.ADBE_Noise_FX")])
        self.assertEqual(rb["blurred"], [{"clip": 0, "blurriness": 90, "edge": True, "edge_by": "index"}])
        self.assertEqual(rb["sharpened"], [{"clip": 1, "ok": True, "amount": 20, "grain": 30}])
        self.assertEqual(rb["log"], [])
        clip0 = dict(out["v1"][0])
        self.assertNotIn("AE.Impact_Blur_FX", clip0)                     # the new blur was never added
        self.assertEqual(clip0["AE.ADBE Gaussian Blur 2"], [["Blurriness", 90], ["Blur Dimensions", 0], [" ", True]])

    def test_repeat_edge_pixels_by_name_when_premiere_names_it(self):
        effects = dict(P26_EFFECTS, **{"Gaussian Blur (Legacy)": ["AE.ADBE Gaussian Blur 2",
                                                                  ["Blurriness", "Blur Dimensions", "Repeat Edge Pixels"]]})
        out = self.build(effects=effects)
        self.assertEqual(out["res"]["result"]["blurred"], [{"clip": 0, "blurriness": 90, "edge": True, "edge_by": "name"}])
        self.assertIn(["Repeat Edge Pixels", True], dict(out["v1"][0])["AE.ADBE Gaussian Blur 2"])

    def test_index_2_is_used_only_when_its_name_is_blank(self):
        """A named third parameter that is not Repeat Edge Pixels is never set by index: reported, not guessed."""
        effects = dict(P26_EFFECTS, **{"Gaussian Blur (Legacy)": ["AE.ADBE Gaussian Blur 2",
                                                                  ["Blurriness", "Blur Dimensions", "Something Else"]]})
        rb = self.build(effects=effects)["res"]["result"]
        self.assertEqual(rb["blurred"], [{"clip": 0, "blurriness": 90, "edge": None, "edge_by": None}])
        self.assertIn("Gaussian Blur (Legacy): Repeat Edge Pixels not found", rb["log"])

    def test_an_impact_blur_is_reported_not_ok(self):
        """A Premiere whose only "Gaussian Blur" is the new effect: the blur is reported {ok: false, got}, not used."""
        effects = {k: v for k, v in P26_EFFECTS.items() if k != "Gaussian Blur (Legacy)"}
        out = self.build(effects=effects)
        rb = out["res"]["result"]
        blur = rb["effects"][0]
        self.assertEqual((blur["kind"], blur["ok"], blur["name"], blur["got"]),
                         ("blur", False, "Gaussian Blur", "AE.Impact_Blur_FX"))
        self.assertEqual(rb["blurred"], [])
        self.assertIn("Gaussian Blur (Legacy) effect not found", rb["log"])
        self.assertTrue(all(e["ok"] for e in rb["effects"][1:]), rb["effects"])
        self.assertIs(blur["removed"], True)                              # the wrong effect is taken off again
        self.assertNotIn("left_in_place", blur)
        self.assertNotIn("AE.Impact_Blur_FX", dict(out["v1"][0]))

    def test_a_wrong_effect_that_cannot_be_removed_is_reported_left_in_place(self):
        effects = {k: v for k, v in P26_EFFECTS.items() if k != "Gaussian Blur (Legacy)"}
        tmp = Path(tempfile.mkdtemp(prefix="wnc_build_")).as_posix()
        self.addCleanup(shutil.rmtree, tmp, True)
        js = "FAKE.qeRemove = false;\n" + BUILD % {"settings": json.dumps(settings(24)), "fsh": "1080",
                                                   "data": json.dumps(build_data(tmp))}
        out = node(self, js, effects=effects)
        blur = out["res"]["result"]["effects"][0]
        self.assertEqual((blur["ok"], blur["removed"], blur["left_in_place"]), (False, False, True))
        self.assertIn("AE.Impact_Blur_FX", blur["note"])
        self.assertIn("still on the clip", blur["note"])
        self.assertIn("AE.Impact_Blur_FX", dict(out["v1"][0]))           # honest: it is there

    def test_a_missing_effect_is_not_found(self):
        effects = {k: v for k, v in P26_EFFECTS.items() if k != "Sharpen"}
        rb = self.build(effects=effects, blur=())["res"]["result"]
        self.assertEqual(rb["effects"], [{"track": 0, "clip": 0, "kind": "sharpen", "ok": False, "error": "not found",
                                          "tried": ["Sharpen"]}])
        self.assertEqual(rb["sharpened"], [{"clip": 0, "ok": False}])
        self.assertIn("Sharpen effect not found", rb["log"])

    def test_the_readback_still_fits_the_contract(self):
        rb = self.build()["res"]["result"]
        self.assertEqual(V.validate(rb, "build_project#/$defs/readback"), [])


COMP_JS = r"""
var it = {components: coll([
    new Comp('Opacity', 'AE.ADBE Opacity', ['Opacity']), new Comp('Motion', 'AE.ADBE Motion', ['Position']),
    new Comp('Gaussian Blur', 'AE.Impact_Blur_FX', ['Blur Amount']),
    new Comp('Gaussian Blur (Legacy)', 'AE.ADBE Gaussian Blur 2', ['Blurriness']),
    new Comp('Noise', 'AE.ADBE Noise2', ['Amount of Noise'])])};
var odd = {components: coll([{displayName: 'X', get matchName() { throw new Error('no'); }, properties: coll([])}])};
function n(c) { return c ? c.displayName : null; }
console.log(JSON.stringify({
    blur: n(WNCPP.compByMatch(it, WNCPP.MATCH.blur)), by_display: n(WNCPP.comp(it, 'Gaussian Blur')),
    motion: n(WNCPP.compByMatch(it, WNCPP.MATCH.motion)), noise: n(WNCPP.compByMatch(it, WNCPP.MATCH.noise)),
    crop: n(WNCPP.compByMatch(it, WNCPP.MATCH.crop)), odd: n(WNCPP.compByMatch(odd, WNCPP.MATCH.blur)),
    match: WNCPP.MATCH}));
"""


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestMatchNames(unittest.TestCase):
    def test_comp_by_match_finds_the_legacy_blur(self):
        out = node(self, COMP_JS)
        self.assertEqual(out["blur"], "Gaussian Blur (Legacy)")
        self.assertEqual(out["by_display"], "Gaussian Blur")             # what the display name alone would have used
        self.assertEqual(out["motion"], "Motion")
        self.assertEqual(out["noise"], "Noise")                          # the legacy noise match name counts too
        self.assertIsNone(out["crop"])
        self.assertIsNone(out["odd"])                                    # a component whose matchName throws is skipped
        self.assertEqual(out["match"], {"motion": "AE.ADBE Motion", "opacity": "AE.ADBE Opacity",
                                        "blur": "AE.ADBE Gaussian Blur 2", "sharpen": "AE.ADBE Sharpen",
                                        "noise": ["AE.ADBE_Noise_FX", "AE.ADBE Noise2"], "crop": "AE.ADBE AECrop"})


CROP_JS = r"""
FAKE.seq = new Sequence_('CROP_TEST', {}, 1080);
var newProject = app.newProject;
app.newProject = function (p) {
    newProject(p);
    app.project.createNewSequenceFromClips = function () { return FAKE.seq; };
    app.project.closeDocument = function () { return true; };
    return true;
};
FAKE.seq.setPlayerPosition = function () {};
var qeSeq = qe.project.getActiveSequence;
qe.project.getActiveSequence = function () {
    var q = qeSeq(); q.CTI = {timecode: '00:00:00:00'}; q.exportFramePNG = function () { return true; }; return q;
};
fs.writeFileSync(TMP + '/png.png', 'x');
fs.writeFileSync(TMP + '/crop.json', JSON.stringify({action: 'test_crop', project_path: TMP + '/C.prproj',
                                                     png: TMP + '/png.png', out_dir: TMP, dev: true}));
console.log(JSON.stringify(JSON.parse(WNCPP.run(TMP + '/crop.json')).result));
"""


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestCropProbe(unittest.TestCase):
    def test_added_is_a_boolean(self):
        r = node(self, CROP_JS)
        self.assertIs(r["added"], True)
        self.assertEqual((r["effect"]["kind"], r["effect"]["got"]), ("crop", "AE.ADBE AECrop"))
        self.assertTrue(r["left_found"])
        r = node(self, CROP_JS, effects={k: v for k, v in P26_EFFECTS.items() if k != "Crop"})
        self.assertIs(r["added"], False)
        self.assertEqual(r["effect"]["error"], "not found")


# each job runs on a fresh project; prints what WNCPP.run answered and what touched the project
DEV_JS = r"""
var out = [], jobs = %(jobs)s;
for (var i = 0; i < jobs.length; i++) {
    var touched = [];
    app.newProject('D:\\p\\Open_EDIT.prproj');
    app.project.closeDocument = function (s) { touched.push('closeDocument ' + s); return true; };
    var newProject = app.newProject;
    app.newProject = function (p) { touched.push('newProject'); return newProject(p); };
    fs.writeFileSync(TMP + '/j.json', JSON.stringify(jobs[i]));
    var r = JSON.parse(WNCPP.run(TMP + '/j.json'));
    app.newProject = newProject;
    out.push({ok: r.ok, error: r.error || null, touched: touched});
}
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestDevOnlyActions(unittest.TestCase):
    """Addendum G2 R1 (H4): close_project without save (discards the open project), test_crop and new_project_import
    (a new project over the path, no backup) are development leftovers. The library refuses them unless the job
    carries dev:true, which reel serve and the engine never set; nothing is touched when it refuses."""

    def run_jobs(self, jobs):
        return node(self, DEV_JS % {"jobs": json.dumps(jobs)})

    def test_they_are_refused_without_dev_true(self):
        jobs = [{"action": "close_project"}, {"action": "close_project", "save": False},
                {"action": "test_crop", "project_path": "D:\\p\\C.prproj", "png": "x.png"},
                {"action": "new_project_import", "project_path": "D:\\p\\Open_EDIT.prproj"},
                {"action": "close_project", "save": False, "dev": "true"}]          # only the boolean counts
        for job, r in zip(jobs, self.run_jobs(jobs)):
            self.assertIs(r["ok"], False, job)
            self.assertIn("development action", r["error"], job)
            self.assertIn("nothing was changed", r["error"], job)
            self.assertEqual(r["touched"], [], job)

    def test_close_with_save_and_dev_jobs_still_run(self):
        out = self.run_jobs([{"action": "close_project", "save": True},
                             {"action": "close_project", "save": False, "dev": True}])
        self.assertEqual([(r["ok"], r["touched"]) for r in out],
                         [(True, ["closeDocument 1"]), (True, ["closeDocument 0"])])


CLOSE_JS = r"""
var PATH = 'D:\\p\\R_EDIT.prproj', calls = [];
function proj(p, extra) {
    var pr = {path: p, save: function () { calls.push('save'); return 0; },
              closeDocument: function (s, q) { calls.push('close ' + s + ' ' + q); return true; }};
    for (var k in extra) { Object.defineProperty(pr, k, Object.getOwnPropertyDescriptor(extra, k)); }
    return pr;
}
var out = [];
var cases = %(cases)s;
for (var i = 0; i < cases.length; i++) {
    calls = [];
    var c = cases[i], extra = {};
    if (c.dirty !== undefined) { extra.dirty = c.dirty; }
    if (c.fn !== undefined) { (function (v) { extra.isDirty = function () { return v; }; })(c.fn); }
    if (c.throws) { Object.defineProperty(extra, 'dirty', {get: function () { throw new Error('no'); }, enumerable: true, configurable: true}); }
    app.projects = c.none ? undefined : coll([proj('D:\\p\\other.prproj', {}), proj(c.open === false ? 'D:\\p\\x.prproj' : PATH, extra)]);
    if (app.projects) { Object.defineProperty(app.projects, 'numProjects', {get: function () { return this.length; }}); }
    var d = {action: 'close_project_path', path: PATH};
    if (c.save) { d.save = c.save; }
    fs.writeFileSync(TMP + '/c.json', JSON.stringify(d));
    out.push({rb: JSON.parse(WNCPP.run(TMP + '/c.json')).result, calls: calls});
}
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "needs node to run the ExtendScript library with a fake Premiere")
class TestCloseProjectPath(unittest.TestCase):
    P = "D:\\p\\R_EDIT.prproj"

    def run_cases(self, cases):
        out = node(self, CLOSE_JS % {"cases": json.dumps(cases)})
        for o in out:
            self.assertEqual(V.validate(o["rb"], "close_project_path#/$defs/readback"), [], o)
            for k in ("dirty", "saved", "dirty_api", "closed"):
                self.assertIn(k, o["rb"], o)                             # always carried
        return out

    def test_the_matrix(self):
        saved_closed = ["save", "close 1 0"]
        rows = [  # (case, readback subset, calls)
            ({}, {"closed": True, "dirty": None, "saved": True, "dirty_api": None}, saved_closed),
            ({"save": "always"}, {"closed": True, "dirty": None, "saved": True, "dirty_api": None}, saved_closed),
            ({"save": "always", "dirty": True}, {"closed": True, "dirty": True, "saved": True, "dirty_api": "dirty"},
             saved_closed),
            ({"save": "always", "dirty": False}, {"closed": True, "dirty": False, "saved": True}, saved_closed),
            ({"save": "if_clean", "dirty": True},
             {"closed": False, "dirty": True, "saved": False, "dirty_api": "dirty"}, []),
            ({"save": "if_clean", "fn": True},
             {"closed": False, "dirty": True, "saved": False, "dirty_api": "isDirty()"}, []),
            ({"save": "if_clean", "dirty": False}, {"closed": True, "dirty": False, "saved": False, "dirty_api": "dirty"},
             ["close 0 0"]),
            ({"save": "if_clean", "fn": False},
             {"closed": True, "dirty": False, "saved": False, "dirty_api": "isDirty()"}, ["close 0 0"]),
            ({"save": "if_clean"}, {"closed": True, "dirty": None, "saved": True, "dirty_api": None}, saved_closed),
            ({"save": "if_clean", "dirty": 1}, {"closed": True, "dirty": None, "saved": True, "dirty_api": None},
             saved_closed),                                              # not a boolean: unknown, never clean
            ({"save": "if_clean", "dirty": "no", "fn": True}, {"closed": False, "dirty": True, "dirty_api": "isDirty()"},
             []),
            ({"save": "if_clean", "throws": True}, {"closed": True, "dirty": None, "saved": True}, saved_closed),
            ({"save": "bogus", "dirty": True}, {"closed": True, "dirty": True, "saved": True}, saved_closed),
            ({"save": "if_clean", "open": False},
             {"closed": False, "reason": "not open", "dirty": None, "saved": False, "dirty_api": None}, []),
            ({"save": "if_clean", "none": True},
             {"closed": False, "reason": "no projects collection", "dirty": None, "saved": False}, []),
        ]
        out = self.run_cases([c for c, _, _ in rows])
        for (case, want, calls), got in zip(rows, out):
            self.assertEqual({k: got["rb"].get(k, "<absent>") for k in want}, want, case)
            self.assertEqual(got["calls"], calls, case)
            if got["rb"].get("reason") not in ("not open", "no projects collection"):
                self.assertEqual(got["rb"]["path"], self.P, case)

    def test_a_refusal_says_why(self):
        out = self.run_cases([{"save": "if_clean", "dirty": True}])
        self.assertEqual(out[0]["rb"]["reason"], "unsaved changes in Premiere")

    def test_project_dirty_is_true_false_or_null(self):
        js = ("console.log(JSON.stringify([WNCPP.projectDirty({dirty: true}), WNCPP.projectDirty({isDirty: function () "
              "{ return false; }}), WNCPP.projectDirty({}), WNCPP.projectDirty({dirty: 'yes'})]));")
        self.assertEqual(node(self, js), [True, False, None, None])


if __name__ == "__main__":
    unittest.main()
