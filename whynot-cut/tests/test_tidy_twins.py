# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, Task 15 - the Python twins of WhyNot Tidy's classify, plan and sync (whynot-cut/engine/reel/lib/tidy/).

The twins are FAITHFUL to the current port (adobe/tools/tidy/src/js/{classify,plan,sync}.js): nothing is generalised here.
The parity tests below are the safety net for the behaviour changes of later tasks, so they are broad: many brands, layouts,
names, paths and offsets, not only the cases the tools were tuned on.

Python only (always run): the FFT against numpy's, planted offsets recovered, hand-written classify / plan / layout cases,
JS key order and UTF-16 length helpers, inputs never mutated.
With node and adobe/tools (skipped with a reason otherwise, e.g. in the plugin zip), identical results from the JS port:
* TidyTwinsUpstreamCases: every call the owner's test_classify.js / test_plan.js / test_sync.js make (the test files are run
  against the port with a recorder around the module functions; each recorded call is replayed on the twin);
* TidyTwinsSources: constants (BINS, COLORS, word lists) and every regex of classify.js / plan.js compared as text with the
  twin's pattern, in both directions, with mutation proofs that the comparison can fail;
* TidyTwinsRandom: 600 random items x 4 contexts, camera numbering, 270 random scans x 2 option sets through `build`
  (brands, duplicates in other spellings, Windows and POSIX paths, backups, nests with Arabic and emoji text, podcast
  layouts), path keys, names, regexes;
* TidyTwinsSync: synthetic multi-track power arrays with planted offsets (positive and negative, a stranger, ties, one
  track), envelope / fromPower, layout on 250 random plans: same placed / skipped, identical offsets (integer ms),
  confidence within 1e-9 relative.
Run:  bash tools/test.sh -p test_tidy_twins.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
sys = _sys
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.tidy import classify as tclassify  # noqa: E402
from lib.tidy import jsutil  # noqa: E402
from lib.tidy import plan as tplan  # noqa: E402
from lib.tidy import sync as tsync  # noqa: E402

ADOBE_TOOLS = REPO / "adobe" / "tools"
RUNNER = ADOBE_TOOLS / "_harness" / "js_runner.js"
PORT = ADOBE_TOOLS / "tidy" / "src"
UPSTREAM = ADOBE_TOOLS / "tidy" / "_upstream"
NODE = shutil.which("node")
TOOLS_PRESENT = RUNNER.is_file() and (UPSTREAM / "js").is_dir() and PORT.is_dir()
NO_TOOLS = "adobe/tools is not in this checkout (the plugin zip ships the tests but not adobe/)"
LOAD_ALL = ["js/classify.js", "js/plan.js", "js/sync.js"]


# ---------------------------------------------------------------- helpers

def run_js(tc, load, calls):
    """Run `calls` through js_runner.js (the port as tool root) in ONE node process; return the results."""
    with tempfile.TemporaryDirectory() as td:
        req = Path(td) / "request.json"
        req.write_text(json.dumps({"load": load, "calls": calls}), encoding="utf-8")
        p = subprocess.run([NODE, str(RUNNER), str(PORT), str(req)], capture_output=True, text=True, encoding="utf-8", timeout=600)
    tc.assertEqual(p.returncode, 0, p.stderr)
    out = json.loads(p.stdout.rstrip("\n").split("\n")[-1])["results"]
    tc.assertEqual(len(out), len(calls))
    for r in out:
        tc.assertFalse(isinstance(r, dict) and set(r) == {"error"}, r)
    return out


def call(fn, *args, typed=None):
    c = {"fn": fn, "args": list(args)}
    if typed:
        c["typed"] = typed
    return c


def canon(x):
    """JSON-like value with integral floats as ints (JS has one number type) and numpy turned into lists."""
    if isinstance(x, np.ndarray):
        return [canon(v) for v in x.tolist()]
    if isinstance(x, np.generic):
        return canon(x.item())
    if isinstance(x, dict):
        return {k: canon(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    if isinstance(x, float) and x == x and abs(x) != math.inf and x == int(x) and abs(x) < 2 ** 53:
        return int(x)
    return x


def dumps(x):
    return json.dumps(canon(x), ensure_ascii=True)


EXACT_KEYS = {"offset", "start", "track", "nodeId", "id", "ref", "dataOffset", "dataSize", "rate", "channels"}


def same(a, b, key=None, path="$"):
    """Equal as JSON; floats within 1e-9 relative (FFT rounding) except the keys that must be identical (integer-ms offsets)."""
    a, b = canon(a), canon(b)
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), "%s: keys %s != %s" % (path, sorted(a), sorted(b))
        for k in a:
            same(a[k], b[k], k, path + "." + k)
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), "%s: lengths %s != %s" % (path, len(a), len(b) if isinstance(b, list) else b)
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, key, "%s[%d]" % (path, i))
    elif isinstance(a, float) or isinstance(b, float):
        if key in EXACT_KEYS:
            assert a == b, "%s: %r != %r" % (path, a, b)
        else:
            assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12), "%s: %r != %r" % (path, a, b)
    else:
        assert a == b, "%s: %r != %r" % (path, a, b)


# ---------------------------------------------------------------- the recorder around the owner's test files

RECORDER = r"""
'use strict';
// runs one of the owner's jsc test files against the port (cwd = the port root) with a recorder around every function of
// TidyClassify / TidyPlan / TidySync / TidyMedia: each call's arguments and result are kept as JSON and printed at the end.
var fs = require('fs'), vm = require('vm'), path = require('path');
var root = path.resolve(process.argv[2]), testFile = process.argv[3];
process.chdir(root);
var log = [];
function count(v) { return Array.isArray(v) || ArrayBuffer.isView(v) ? v.length : 0; }
function clone(v) {
    if (v === undefined) { return null; }
    if (typeof v === 'number') { return isFinite(v) ? v : String(v); }
    if (v === null || typeof v !== 'object') { return v; }
    if (ArrayBuffer.isView(v)) { return Array.prototype.map.call(v, clone); }
    if (Array.isArray(v)) { return v.map(clone); }
    var o = {};
    Object.keys(v).forEach(function (k) { if (v[k] !== undefined) { o[k] = clone(v[k]); } });
    return o;
}
function big(args) { var n = 0; args.forEach(function (a) { n += count(a); }); return n > 250000; }
function wrapAll() {
    ['TidyClassify', 'TidyPlan', 'TidySync', 'TidyMedia'].forEach(function (name) {
        var obj = globalThis[name];
        if (!obj || obj.__wrapped) { return; }
        Object.defineProperty(obj, '__wrapped', { value: true, enumerable: false });
        Object.keys(obj).forEach(function (k) {
            var orig = obj[k];
            if (typeof orig !== 'function') { return; }
            obj[k] = function () {
                var skip = big(Array.prototype.slice.call(arguments));
                var args = skip ? null : clone(Array.prototype.slice.call(arguments));
                var res = orig.apply(this, arguments);
                if (!skip) { log.push({ fn: name + '.' + k, args: args, result: clone(res) }); }
                return res;
            };
        });
    });
}
globalThis.print = function () {};
globalThis.readFile = function (p, mode) { var b = fs.readFileSync(path.resolve(root, String(p))); return mode === 'binary' ? new Uint8Array(b) : b.toString('utf8'); };
globalThis.load = function (p) {
    var f = path.resolve(root, String(p)), r = vm.runInThisContext(fs.readFileSync(f, 'utf8'), { filename: f });
    wrapAll();
    return r;
};
vm.runInThisContext(fs.readFileSync(testFile, 'utf8'), { filename: testFile });
console.log(JSON.stringify(log));
"""

_RECORDS = {}


def record(tc, name):
    """The calls the owner's tests/<name> makes against the port: [{fn, args, result}] (cached per process)."""
    if name not in _RECORDS:
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "recorder.js"
            script.write_text(RECORDER, encoding="utf-8")
            p = subprocess.run([NODE, str(script), str(PORT), str(UPSTREAM / "tests" / name)], capture_output=True, text=True,
                               encoding="utf-8", timeout=600, cwd=str(PORT))
        tc.assertEqual(p.returncode, 0, p.stderr)
        _RECORDS[name] = json.loads(p.stdout.rstrip("\n").split("\n")[-1])
    return _RECORDS[name]


def replay(fn, args):
    """The twin's answer for a recorded JS call."""
    table = {
        "TidyClassify.category": tclassify.category, "TidyClassify.binFor": tclassify.bin_for,
        "TidyClassify.cameraNumbers": tclassify.camera_numbers, "TidyClassify.ext": tclassify.ext,
        "TidyPlan.build": tplan.build, "TidyPlan.nestName": tplan.nest_name, "TidyPlan.pathKey": tplan.path_key,
        "TidyPlan.syncedName": tplan.synced_name,
        "TidySync.envelope": tsync.envelope, "TidySync.fromPower": tsync.from_power, "TidySync.offset": tsync.offset,
        "TidySync.refine": tsync.refine, "TidySync.plan": tsync.plan, "TidySync.layout": tsync.layout, "TidySync.wavInfo": tsync.wav_info,
    }
    return table[fn](*copy.deepcopy(args))


# ---------------------------------------------------------------- random corpora

EXT_POOL = {
    "video": ["mp4", "MOV", "mkv", "mxf", "MTS", "avi", "r3d", "braw", "insv", "wmv", "webm", "m4v", "3gp", "mpg", "dv", "m2ts", "crm", "ari", "Mp4"],
    "audio": ["wav", "WAV", "mp3", "aif", "aiff", "m4a", "flac", "ogg", "bwf", "caf", "aac", "wma"],
    "image": ["png", "PNG", "jpg", "JPG", "jpeg", "tif", "tiff", "psd", "gif", "heic", "webp", "svg", "ai", "eps", "bmp", "ico", "exr", "tga", "dpx", "icns"],
    "caption": ["srt", "vtt", "scc", "stl", "SRT"], "graphic": ["mogrt", "aegraphic", "prgraphic", "aep"],
    "other": ["xyz", "txt", "pdf", "docx", "prproj", "", "zip"],
}
WORDS = ["clip", "interview", "Script 1 - 2", "C0123", "IMG_3886", "DJI_0042", "whoosh", "riser", "music", "song", "bgm", "beat", "track",
         "loop", "score", "impact", "ding", "hit", "click", "pop", "White smoke", "Architecture B-roll", "Host", "Guest Track", "ZOOM0001",
         "sfx", "fx_boom", "final", "Company Logo", "icon", "emoji 2", "\u0627\u062c\u062a\u0645\u0627\u0639", "\u062d\u0644\u0642\u0629 \u0662",
         "\u0645\u0642\u0627\u0628\u0644\u0629", "\u0645\u0648\u0633\u064a\u0642\u0649", "episode 12", "Caf\u00e9 \u00e9t\u00e9", "na\u00efve",
         "name " + chr(0x1F600), "music_loop_2", "Ambient pad", "Foley steps", "transition 3", "glitch", "beep", "ost", "instrumental",
         "melody", "Swoosh 4", "SFX", "bgm_01", "A001C002_220101", "00001", "GX010203", "MVI_1234", "Render 2", "export", "x", "a" * 70]
ROOTS = ["/Volumes/X/RAW", "/Users/me/Media", "C:\\Shoot\\Day 1", "D:\\Clients\\Ex ample\\Footage", "c:/m", "\\\\NAS\\share\\cam", "/m",
         "", "/Volumes/Brand A/\u0645\u062c\u0644\u062f", "E:\\\u00dcber\\\u0130stanbul", "/mnt/\u03a3\u0391\u03a3"]
CAMS = ["DJI OsmoPocket3 | /Volumes/X/RAW", "DJI Mavic3 | C:\\Shoot", "iPhone 16 Pro Max | /Users/me", "folder:/x/Cam B", "folder:/x/Cam A",
        "ILCE-7M4 | /sony", "1", "2", "10", "11", "Sony FX3", "GoPro HERO12 | /g", "BMPCC6K | /b", "\u0643\u0627\u0645\u064a\u0631\u0627 1"]
BIN_NAMES = ["01 Footage", "02 Renders & Stock", "03 Audio/SFX", "03 Audio/Voice", "04 Images/PNG", "Assets", "Assets/Assets", "Empty Bin",
             "Kalam Captions", "Recovered Clips", "04 Images/Other", "01 Footage/Cam 1", "06 Sequences", "X/Y/Z", ""]


def rand_path(r, kind=None):
    kind = kind or r.choices(list(EXT_POOL), weights=[34, 22, 22, 4, 4, 5])[0]
    ext = r.choice(EXT_POOL[kind])
    name = r.choice(WORDS) + (" %d" % r.randrange(1, 40) if r.random() < 0.4 else "")
    sep = r.choice(["/", "\\"])
    root = r.choice(ROOTS)
    return (root + sep if root else "") + name + ("." + ext if ext else ""), name + ("." + ext if ext else "")


def maybe(r, p, value):
    return value if r.random() < p else None


def rand_item(r, nid, paths):
    it = {"nodeId": nid}
    kind = r.random()
    if kind < 0.18:                                                   # a sequence
        base = r.choice(["Main", "Logo Nest", "Nested Sequence 01", "Old Edit", "Episode", "\u0627\u0644\u062a\u062c\u0645\u064a\u0639", "Reel A"])
        suffix = r.choice(["", "", "", " (Hush backup 10:00:00)", " (Hush cut 10:05:00)", " (WhyNot Hush backup 10:10:00)",
                           " (WhyNot Hush cut 10:11:00)", " (Tidy backup 2026-10-12 1542)", " Hush backup 10:12:00", " (hush backup 1)"])
        it.update({"name": base + suffix, "path": "", "isSequence": True, "size": 0, "bin": r.choice(["", "06 Sequences", "07 Nests", "X"])})
        return it
    if kind < 0.28:                                                   # a graphic with no file
        it.update({"name": r.choice(WORDS), "path": "", "isSequence": False})
    else:
        if paths and r.random() < 0.18:                               # the same file again, maybe spelled differently
            path = r.choice(paths)
            path = r.choice([path, path.replace("\\", "/"), path.replace("/", "\\"), path.upper(), path.lower(), path])
            name = path.replace("\\", "/").split("/")[-1]
        else:
            path, name = rand_path(r)
            paths.append(path)
        it.update({"name": name if r.random() < 0.95 else maybe(r, 0.5, name), "path": path, "isSequence": False})
        if r.random() < 0.02:
            del it["path"]
    for key, vals, p in (("duration", [0, 0.5, 2, 8, 8.0001, 9, 120, 179.999, 180, 300, 3600, 7200.5, None], 0.9),
                         ("size", [0, 1000, 5000, 123456789, 1.5, None], 0.9), ("kind", ["camera", "render", "camera", "other", None], 0.55),
                         ("camId", CAMS, 0.5), ("icon", [True, False], 0.15), ("exists", [True, False, None], 0.15),
                         ("offline", [True, False], 0.06), ("color", list(range(0, 16)) + [None], 0.5),
                         ("bin", BIN_NAMES + [None], 0.7)):
        if r.random() < p:
            it[key] = r.choice(vals)
    return it


def rand_scan(r):
    n = r.choice([0, 1, 2, 5, 12, 25, 40])
    paths, items = [], []
    for i in range(n):
        nid = r.choice(["n%d" % i, "n%d" % i, "n%d" % i, str(1000 + i), i + 5000])      # a few ids are numbers (JS keys coerce)
        items.append(rand_item(r, nid, paths))
    ids = [it["nodeId"] for it in items]
    seqs = [it["nodeId"] for it in items if it.get("isSequence")]
    usage = {}
    for sid in seqs + (["ghost"] if r.random() < 0.2 else []):
        usage[str(sid)] = [r.choice(ids + ["missing"]) for _ in range(r.randrange(0, min(8, len(ids) + 1) + 1))] if ids else []
    bins = [{"nodeId": "b%d" % i, "path": r.choice(BIN_NAMES)} for i in range(r.randrange(0, 8))]
    scan = {"items": items, "bins": bins, "usage": usage}
    if r.random() < 0.6:
        longtext = "\u0647\u064a\u0631\u0642\u064a\u0643 \u0644\u0648 " * 6 + chr(0x1F600) * 3
        scan["texts"] = {str(s): [r.choice(["  \u0647\u064a\u0631\u0642\u064a\u0643   \u0644\u0648  ", "3", "", "  ", "Title\n\nSecond line", longtext, "constructor", "toString", "__proto__", "Title", "a" * 49 + chr(0x1F600) + "bc de",
                                            "x" * 48 + chr(0x1F600) + " tail words", "word " * 20, "\u00a0\u3000padded\ufeff"]) for _ in range(r.randrange(0, 3))]
                         for s in seqs if r.random() < 0.7}
    return scan


def rand_opts(r, scan):
    ids = [str(it["nodeId"]) for it in scan["items"]]
    opts = {}
    if r.random() < 0.45:
        opts["mode"] = r.choice(["podcast", "reels", "other"])
    if r.random() < 0.5:
        opts["platform"] = r.choice(["win32", "darwin", "linux", None])
    for key in ("unchecked", "checked", "noRename"):
        if ids and r.random() < 0.25:
            opts[key] = {i: True for i in r.sample(ids, min(len(ids), r.randrange(1, 4)))}
    return opts


# ---------------------------------------------------------------- Python only

class TidyTwinsPythonOnly(unittest.TestCase):
    def test_classify_cases_of_the_owners_tests(self):
        c = tclassify.category
        reels = {"nestIds": {"n1": True}, "mode": "reels"}

        def item(name, path, **kw):
            d = {"name": name, "path": path, "isSequence": False, "duration": 10, "nodeId": "x"}
            d.update(kw)
            return d
        self.assertEqual(c(item("Script 1 - 2.mp4", "/a/Script 1 - 2.mp4", kind="camera"), reels), "footage")
        self.assertEqual(c(item("BLADE WHOOSH SFX.mp4", "/a/b.mp4", kind="render", duration=2), reels), "sfx")
        self.assertEqual(c(item("White smoke.mov", "/a/w.mov", kind="render"), reels), "renders")
        self.assertEqual(c(item("Host.wav", "/a/Host.wav", duration=3600), {"mode": "podcast"}), "mics")
        self.assertEqual(c(item("song.wav", "/a/song.wav", duration=240), {"mode": "podcast"}), "music")
        self.assertEqual(c(item("interview.wav", "/a/i.wav", duration=300), reels), "voice")
        self.assertEqual(c(item("logo.png", "/a/logo.png", icon=True), reels), "icons")
        self.assertEqual((c(item("Main", "", isSequence=True, nodeId="s1"), reels), c(item("Nest", "", isSequence=True, nodeId="n1"), reels)),
                         ("sequences", "nests"))
        self.assertEqual(c(item("data.xyz", "/a/data.xyz"), reels), "other")
        self.assertEqual(c(item("Graphic", ""), reels), "graphics")
        self.assertEqual(c(item("x.wav", "/a/x.wav", duration=8), reels), "sfx")
        self.assertEqual(c(item("x.wav", "/a/x.wav", duration=8.0001), reels), "voice")

    def test_bins_and_camera_numbers(self):
        items = [{"kind": "camera", "camId": "DJI", "duration": 600}, {"kind": "camera", "camId": "iPhone", "duration": 900},
                 {"kind": "camera", "camId": "DJI", "duration": 500}, {"kind": "render", "camId": "x", "duration": 5000},
                 {"kind": "camera", "camId": "A", "duration": 100}, {"kind": "camera", "camId": "B", "duration": 100}, {"kind": "camera"}]
        cams = tclassify.camera_numbers(items)
        self.assertEqual(cams, {"DJI": 1, "iPhone": 2, "A": 3, "B": 4})
        pod = {"mode": "podcast", "camNumbers": cams}
        self.assertEqual(tclassify.bin_for("footage", {"camId": "iPhone"}, pod), "01 Footage/Cam 2")
        self.assertEqual(tclassify.bin_for("footage", {"camId": "zzz"}, pod), "01 Footage")
        self.assertEqual(tclassify.bin_for("mics", {}, pod), "03 Audio/Mics")
        self.assertEqual(tclassify.bin_for("footage", {"camId": "iPhone"}, {"mode": "reels", "camNumbers": cams}), "01 Footage")

    def test_camera_numbers_sorts_ties_by_utf16_code_units_like_js(self):
        # U+FF5E (BMP) sorts AFTER U+1F600 in code points but BEFORE it in UTF-16 (the emoji starts with 0xD83D)
        a, b = "x" + chr(0xFF5E), "x" + chr(0x1F600)
        items = [{"kind": "camera", "camId": a, "duration": 5}, {"kind": "camera", "camId": b, "duration": 5}]
        self.assertEqual(tclassify.camera_numbers(items), {b: 1, a: 2})
        self.assertLess(a, b)                                          # Python's own (code point) order is the other one

    def test_plan_like_test_plan_js(self):
        def I(nid, name, path, **kw):
            it = {"nodeId": nid, "name": name, "path": path, "isSequence": False, "duration": 10, "bin": "", "exists": True, "offline": False, "size": 1000, "color": 0}
            it.update(kw)
            return it
        scan = {"items": [I("c1", "clip.mp4", "/m/clip.mp4", size=5000, kind="camera", camId="DJI OsmoPocket3", duration=600),
                          I("c2", "clip.mp4", "/m/clip.mp4", size=5000, kind="camera", camId="DJI OsmoPocket3"),
                          I("v1", "voice.wav", "/m/voice.wav", duration=200), I("x1", "onlyInBackup.mp4", "/m/onlyInBackup.mp4"),
                          I("l1", "logo.png", "/m/logo.png"), I("t1", "subs.srt", "/m/subs.srt", bin="Kalam Captions"),
                          I("q1", "Main", "", isSequence=True, size=0), I("q2", "Logo Nest", "", isSequence=True, size=0),
                          I("q3", "Main (Hush backup 10:00:00)", "", isSequence=True, size=0), I("q4", "Main (WhyNot Hush cut 10:00:00)", "", isSequence=True, size=0)],
                "bins": [{"nodeId": "b1", "path": "Empty Bin"}, {"nodeId": "b2", "path": "Assets/Assets"}, {"nodeId": "b3", "path": "Assets"}],
                "usage": {"q1": ["c1", "q2"], "q2": ["l1"], "q3": ["c1", "x1"], "q4": ["x1"]}}
        before = copy.deepcopy(scan)
        plan = tplan.build(scan, {})
        self.assertEqual(scan, before)                                 # never mutates its input
        rem = {r["nodeId"]: r for r in plan["removals"]}
        self.assertEqual(rem["x1"]["reason"], "unused")
        self.assertEqual(rem["c2"]["reason"], "duplicate")
        self.assertEqual((rem["q3"]["reason"], rem["q4"]["reason"]), ("backup", "backup"))
        self.assertFalse(rem["t1"]["checked"])
        self.assertEqual(plan["emptyBins"][0]["path"], "Assets/Assets")           # deepest first
        self.assertEqual(plan["stats"]["removeCount"], sum(1 for r in plan["removals"] if r["checked"]))
        self.assertEqual(list(plan), ["removals", "moves", "colors", "duplicates", "offline", "emptyBins", "renames", "stats"])
        self.assertEqual(list(plan["stats"]), ["removeCount", "removeSize", "totalSize", "byType"])

    def test_missing_fields_stay_missing_like_undefined_in_json(self):
        scan = {"items": [{"nodeId": "a", "path": "/m/a.mp4"}, {"nodeId": "b", "name": "b.png", "path": "/m/b.png", "bin": None},
                          {"nodeId": "s", "name": "S", "path": "", "isSequence": True}], "usage": {"s": ["a", "b"]}}
        plan = tplan.build(scan, {})
        mv = {m["nodeId"]: m for m in plan["moves"]}
        self.assertEqual(mv["a"], {"nodeId": "a", "to": "02 Renders & Stock"})                # no name, no bin: JSON drops undefined
        self.assertEqual(mv["b"], {"nodeId": "b", "name": "b.png", "from": None, "to": "04 Images/PNG"})   # null stays null

    def test_path_key_synced_name_and_regexes(self):
        self.assertEqual(tplan.path_key("C:\\M\\Clip.MP4", "win32"), "c:/m/clip.mp4")
        self.assertEqual(tplan.path_key("C:\\M\\Clip.MP4", "darwin"), "C:\\M\\Clip.MP4")
        self.assertEqual(tplan.path_key("C:\\M\\Clip.MP4"), "C:\\M\\Clip.MP4")
        self.assertEqual(tplan.synced_name("Episode 12.prproj", ["Episode 12 - Synced"]), "Episode 12 - Synced 2")
        self.assertEqual(tplan.synced_name("", []), "Podcast - Synced")
        for n in ("A (Hush backup 1)", "A (WhyNot Hush cut 1)"):
            self.assertTrue(tplan.BACKUP.search(n))
        self.assertFalse(tplan.BACKUP.search("A Hush backup 1"))
        self.assertTrue(tplan.TEMP_SYNC.search("WhyNot Tidy sync temp"))
        self.assertFalse(tplan.TEMP_SYNC.search("WhyNot Tidy sync temp\n"))      # $ is the very end (JS), not before a newline
        self.assertTrue(tplan.TIDY_BACKUP.search("Main (WhyNot Tidy backup 2026)"))

    def test_nest_names(self):
        byid = {"i": {"name": "Corporate Success.png", "path": "/a/Corporate Success.png", "isSequence": False},
                "c": {"name": "C0001.MP4", "path": "/a/C0001.MP4", "isSequence": False}, "s": {"name": "  Inner   Seq ", "isSequence": True}}
        nn = tplan.nest_name
        self.assertEqual(nn({}, ["  \u0647\u064a\u0631\u0642\u064a\u0643   \u0644\u0648  "], [], byid), "\u0647\u064a\u0631\u0642\u064a\u0643 \u0644\u0648")
        self.assertEqual(nn({}, [], ["c", "i"], byid), "Corporate Success")
        self.assertEqual(nn({}, [], ["c"], byid), "C0001")
        self.assertEqual(nn({}, [], ["s"], byid), "Inner Seq")
        self.assertEqual(nn({}, [], [], byid), "")

    def test_names_are_cut_at_50_utf16_units_like_js(self):
        # the cut counts UTF-16 units: 49 letters + an emoji (2 units) is 51 long, so the cut lands inside the emoji (a lone
        # high surrogate stays in the string until the trailing-word rule removes it, exactly as in JS)
        text = "a" * 49 + chr(0x1F600) + "bc de"
        out = tplan.nest_name({}, [text], [], {})
        self.assertEqual(out, "a" * 49 + chr(0xD83D))
        self.assertEqual(jsutil.u16len("a" + chr(0x1F600)), 3)
        short = "w" * 20 + chr(0x1F600) * 10                         # 40 units: nothing is cut
        self.assertEqual(tplan.nest_name({}, [short], [], {}), short)
        longer = "word " * 20
        self.assertEqual(tplan.nest_name({}, [longer], [], {}), "word " * 9 + "word")

    def test_a_nest_named_like_an_inherited_object_property_is_renamed_like_js(self):
        # JS: `taken["constructor"]` is Object.prototype.constructor (truthy) before anything is stored, so the name counts as taken
        scan = {"items": [{"nodeId": "m", "name": "Main", "path": "", "isSequence": True}, {"nodeId": "n1", "name": "Nested Sequence 01", "path": "", "isSequence": True},
                          {"nodeId": "n2", "name": "Nested Sequence 02", "path": "", "isSequence": True}],
                "usage": {"m": ["n1", "n2"]}, "texts": {"n1": ["constructor"], "n2": ["Title"]}}
        plan = tplan.build(scan, {})
        self.assertEqual([(x["nodeId"], x["to"]) for x in plan["renames"]], [("n1", "constructor 2"), ("n2", "Title")])

    def test_js_key_order_helper(self):
        self.assertEqual(jsutil.js_order(["b", "10", "a", "2", "01", "4294967295", "4294967294", "-1", "1.5"]),
                         ["2", "10", "4294967294", "b", "a", "01", "4294967295", "-1", "1.5"])
        self.assertEqual(jsutil.key(5), "5")
        self.assertEqual(jsutil.key(5.0), "5")
        self.assertEqual(jsutil.key(None), "null")
        self.assertEqual(jsutil.key(True), "true")

    def test_duplicates_come_out_in_js_property_order(self):
        # an integer-like path key is enumerated first in JS, whatever came first in the scan
        scan = {"items": [{"nodeId": "a", "name": "x", "path": "zz.mp4"}, {"nodeId": "b", "name": "x", "path": "zz.mp4"},
                          {"nodeId": "c", "name": "y", "path": "7"}, {"nodeId": "d", "name": "y", "path": "7"}, {"nodeId": "s", "isSequence": True, "name": "S"}],
                "usage": {"s": ["a", "b", "c", "d"]}}
        self.assertEqual([d["path"] for d in tplan.build(scan, {})["duplicates"]], ["7", "zz.mp4"])


class TidyTwinsFft(unittest.TestCase):
    def test_the_radix2_fft_is_an_fft(self):
        r = np.random.RandomState(3)
        for n in (1, 2, 4, 8, 64, 1024, 4096):
            re_, im_ = r.randn(n), r.randn(n)
            fr, fi = tsync.fft(re_.copy(), im_.copy(), False)
            want = np.fft.fft(re_ + 1j * im_)
            self.assertTrue(np.allclose(fr + 1j * fi, want, rtol=1e-9, atol=1e-9 * max(1, n)), n)
            br, bi = tsync.fft(fr, fi, True)
            self.assertTrue(np.allclose(br, re_, atol=1e-12 * n) and np.allclose(bi, im_, atol=1e-12 * n), n)

    def test_inputs_are_not_modified(self):
        re_, im_ = np.arange(8.0), np.zeros(8)
        tsync.fft(re_, im_, False)
        self.assertEqual(re_.tolist(), list(range(8)))


def world(seed, seconds):
    """A speech-like loudness curve at 1 ms: bursts of random length and level, some silences (power, not samples)."""
    r = np.random.RandomState(seed)
    n = int(seconds * 1000)
    out = np.empty(n)
    i = 0
    while i < n:
        ln = int((0.08 + abs(r.rand()) * 0.6) * 1000)
        amp = 0.0 if r.rand() < 0.15 else 0.02 + r.rand() * 0.5
        out[i:i + ln] = amp * amp * (0.5 + r.rand(min(ln, n - i)))
        i += ln
    return out


def track_from(power_world, start_s, end_s, seed, noise=0.0002):
    r = np.random.RandomState(seed)
    seg = power_world[int(round(start_s * 1000)):int(round(end_s * 1000))]
    return seg * 0.7 + noise * r.rand(len(seg))


def make_track(tid, power):
    f = tsync.from_power(power)
    return {"id": tid, "env": f["env"].tolist(), "hi": f["hi"].tolist(), "seconds": f["seconds"]}


class TidyTwinsSyncPythonOnly(unittest.TestCase):
    def test_planted_offsets_are_recovered_and_a_stranger_is_left_out(self):
        w = world(7, 45)
        tracks = [make_track("mic", track_from(w, 0, 45, 1)), make_track("camA", track_from(w, 3.217, 38, 2)),
                  make_track("camB", track_from(w, 12, 44.5, 3)), make_track("other", world(99, 20))]
        pl = tsync.plan(tracks)
        self.assertEqual(pl["ref"], "mic")
        at = {p["id"]: p["offset"] for p in pl["placed"]}
        self.assertAlmostEqual(at["camA"], 3.217, delta=0.002)
        self.assertAlmostEqual(at["camB"], 12.0, delta=0.002)
        self.assertEqual(at["mic"], 0)
        self.assertEqual(pl["skipped"], ["other"])
        self.assertEqual(list(pl), ["ref", "placed", "skipped"])
        self.assertEqual(list(pl["placed"][0]), ["id", "offset", "confidence"])

    def test_empty_and_single_plans(self):
        self.assertEqual(tsync.plan([]), {"ref": None, "placed": [], "skipped": []})
        one = tsync.plan([{"id": "a", "env": [0.0], "hi": [0.0], "seconds": 1}])
        self.assertEqual(one, {"ref": "a", "placed": [{"id": "a", "offset": 0, "confidence": 99}], "skipped": []})

    def test_layout_cases_of_the_owners_test(self):
        lay = tsync.layout({"placed": [{"id": "mic1", "offset": 0}, {"id": "a1", "offset": -2.5}, {"id": "b1", "offset": 20}, {"id": "a2", "offset": 400}], "skipped": ["x"]},
                           {"mic1": {"role": "mic"}, "a1": {"role": "cam", "cam": 1}, "a2": {"role": "cam", "cam": 1}, "b1": {"role": "cam", "cam": 2}, "x": {"role": "cam", "cam": 2}})
        st = {c["nodeId"]: c for c in lay["cams"]}
        self.assertEqual((st["a1"]["start"], st["a1"]["track"], st["a2"]["track"], st["b1"]["track"]), (0, 0, 0, 1))
        self.assertAlmostEqual(st["b1"]["start"], 22.5)
        self.assertAlmostEqual(lay["mics"][0]["start"], 2.5)
        self.assertEqual(lay["skipped"], ["x"])
        lay2 = tsync.layout({"placed": [{"id": "m", "offset": 0}, {"id": "x1", "offset": 5}, {"id": "x2", "offset": 30}, {"id": "y1", "offset": 10}, {"id": "x3", "offset": 200}], "skipped": []},
                            {"m": {"role": "mic", "seconds": 300}, "x1": {"role": "cam", "cam": 1, "seconds": 100}, "x2": {"role": "cam", "cam": 1, "seconds": 100},
                             "x3": {"role": "cam", "cam": 1, "seconds": 50}, "y1": {"role": "cam", "cam": 2, "seconds": 100}})
        self.assertEqual({c["nodeId"]: c["track"] for c in lay2["cams"]}, {"x1": 0, "y1": 1, "x2": 2, "x3": 0})
        self.assertEqual(list(lay2["cams"][0]), ["nodeId", "start", "track"])           # `end` is gone, key order as in JS

    def test_from_power_and_envelope_shapes(self):
        f = tsync.from_power(np.full(1005, 0.25))
        self.assertEqual((len(f["hi"]), len(f["env"]), f["seconds"]), (1005, 100, 1.005))
        self.assertAlmostEqual(float(np.sum(f["hi"])), 0.0, places=9)                   # mean removed
        e = tsync.envelope(np.sin(np.arange(8000) * 0.3), 8000, 100)
        self.assertEqual(len(e), 100)
        self.assertEqual(len(tsync.envelope(np.zeros(0), 8000, 100)), 0)

    def test_inputs_are_not_modified(self):
        w = world(5, 12)
        t = [make_track("a", track_from(w, 0, 12, 1)), make_track("b", track_from(w, 1, 11, 2))]
        before = copy.deepcopy(t)
        tsync.plan(t)
        self.assertEqual(t, before)


# ---------------------------------------------------------------- JS parity

@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyTwinsUpstreamCases(unittest.TestCase):
    """Every call the owner's tests make, replayed on the twin (the recorder runs the real test file against the port)."""

    def check(self, name, minimum, fns):
        calls = [c for c in record(self, name) if c["fn"] in fns]
        self.assertGreaterEqual(len(calls), minimum, "the recorder saw too few calls of %s" % name)
        for c in calls:
            try:
                same(c["result"], replay(c["fn"], c["args"]))
            except AssertionError as e:
                self.fail("%s%s -> %s" % (c["fn"], json.dumps(c["args"])[:300], e))
        return calls

    def test_test_classify_js(self):
        calls = self.check("test_classify.js", 40, {"TidyClassify.category", "TidyClassify.binFor", "TidyClassify.cameraNumbers"})
        self.assertEqual({c["fn"] for c in calls}, {"TidyClassify.category", "TidyClassify.binFor", "TidyClassify.cameraNumbers"})

    def test_test_plan_js(self):
        calls = self.check("test_plan.js", 40, {"TidyPlan.build", "TidyPlan.nestName", "TidyClassify.category", "TidyClassify.binFor", "TidyClassify.cameraNumbers"})
        builds = [c for c in calls if c["fn"] == "TidyPlan.build"]
        self.assertGreaterEqual(len(builds), 9)
        for c in builds:                                           # exact, key order included
            self.assertEqual(dumps(c["result"]), dumps(replay(c["fn"], c["args"])))

    def test_test_sync_js(self):
        calls = self.check("test_sync.js", 12, {"TidySync.offset", "TidySync.refine", "TidySync.plan", "TidySync.layout", "TidySync.fromPower", "TidySync.wavInfo"})
        self.assertGreaterEqual(len([c for c in calls if c["fn"] == "TidySync.plan"]), 1)
        self.assertGreaterEqual(len([c for c in calls if c["fn"] == "TidySync.layout"]), 2)


def js_to_py(src):
    out, i = [], 0
    while i < len(src):
        c = src[i]
        if c == "\\":
            out.append(src[i:i + 2])
            i += 2
            continue
        out.append("\\Z" if c == "$" else c)
        i += 1
    return "".join(out)


def js_regex(file, name, prefix=r"\b"):
    src = (PORT / "js" / file).read_text(encoding="utf-8")
    m = re.search(prefix + re.escape(name) + r" = /((?:\\.|[^/\\\n])+)/([a-z]*)[;,]", src)
    return (m.group(1), m.group(2)) if m else None


def js_string_list(name):
    src = (PORT / "js" / "classify.js").read_text(encoding="utf-8")
    m = re.search(r"\b%s = '([^']*)'" % name, src)
    return m.group(1) if m else None


CLASSIFY_REGEXES = {"SFX_WORDS": "SFX_WORDS", "SFX_VIDEO": "SFX_VIDEO", "MUSIC_STRICT": "MUSIC_STRICT", "MUSIC_WORDS": "MUSIC_WORDS"}
PLAN_REGEXES = {"P.BACKUP": "BACKUP", "P.TEMP_SYNC": "TEMP_SYNC", "P.TIDY_BACKUP": "TIDY_BACKUP", "P.IMAGE": "IMAGE"}


@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyTwinsSources(unittest.TestCase):
    """The twin's constants and regexes are the same text as the JS's (both directions), so a token added or dropped on one
    side only fails here and not by luck of a seeded test (the lesson of the media twin's `Mimo`)."""

    @classmethod
    def problems(cls):
        out = []
        for jsname, pyname in CLASSIFY_REGEXES.items():
            lit = js_regex("classify.js", jsname)
            rx = getattr(tclassify, pyname)
            if lit is None:
                out.append("classify.js has no %s literal" % jsname)
                continue
            if rx.pattern != js_to_py(lit[0]):
                out.append("%s: classify.py has %r, classify.js has %r" % (jsname, rx.pattern, js_to_py(lit[0])))
            if rx.flags & (re.I | re.A | re.U) != re.ASCII | (re.I if "i" in lit[1] else 0):
                out.append("%s: flags differ" % jsname)
        for jsname, pyname in PLAN_REGEXES.items():
            lit = js_regex("plan.js", jsname, prefix=r"")
            rx = getattr(tplan, pyname)
            if lit is None:
                out.append("plan.js has no %s literal" % jsname)
                continue
            if rx.pattern != js_to_py(lit[0]):
                out.append("%s: plan.py has %r, plan.js has %r" % (jsname, rx.pattern, js_to_py(lit[0])))
            if rx.flags & (re.I | re.A | re.U) != re.ASCII | (re.I if "i" in lit[1] else 0):
                out.append("%s: flags differ" % jsname)
        for name in ("VIDEO", "AUDIO", "IMAGE", "CAPTION", "GRAPHIC", "RECORDER"):
            if js_string_list(name) != getattr(tclassify, name):
                out.append("%s list differs: %r vs %r" % (name, getattr(tclassify, name), js_string_list(name)))
        return out

    def test_every_regex_and_word_list_is_the_same_text(self):
        self.assertEqual(self.problems(), [])

    def mutated(self, mod, name, old, new):
        rx = getattr(mod, name)
        self.assertIn(old, rx.pattern)
        return mock.patch.object(mod, name, re.compile(rx.pattern.replace(old, new, 1), rx.flags))

    def test_the_comparison_can_fail(self):
        for mod, name, old, new in ((tclassify, "SFX_WORDS", "ding", "ding|dong"), (tclassify, "SFX_VIDEO", "click", "click|clack"),
                                    (tclassify, "MUSIC_STRICT", "bgm", "bgm|bg"), (tclassify, "MUSIC_WORDS", "melody", "melody|tune"),
                                    (tplan, "BACKUP", "Hush", "Hush|Kalam"), (tplan, "TEMP_SYNC", "sync", "sync|syn"),
                                    (tplan, "TIDY_BACKUP", "Tidy", "Tidy|Tidi"), (tplan, "IMAGE", "bmp", "bmp|dng")):
            with self.mutated(mod, name, old, new):
                self.assertTrue(self.problems(), (name, old))
        with mock.patch.object(tclassify, "VIDEO", tclassify.VIDEO.replace(" mkv", "")):
            self.assertTrue([p for p in self.problems() if p.startswith("VIDEO")])
        with mock.patch.object(tclassify, "AUDIO", tclassify.AUDIO + " opus"):
            self.assertTrue([p for p in self.problems() if p.startswith("AUDIO")])
        rx = tclassify.SFX_WORDS
        with mock.patch.object(tclassify, "SFX_WORDS", re.compile(rx.pattern, re.ASCII)):                 # lost /i
            self.assertTrue([p for p in self.problems() if "flags" in p])

    @unittest.skipUnless(NODE, "node is not installed")
    def test_tables_and_constants_equal_the_js(self):
        bins, colors, mic, nm = run_js(self, LOAD_ALL, [call("TidyClassify.BINS"), call("TidyClassify.COLORS"), call("TidyClassify.MIC_MIN"), call("TidyPlan.NAME_MAX")])
        self.assertEqual((bins, list(bins)), (tclassify.BINS, list(tclassify.BINS)))
        self.assertEqual((colors, list(colors)), (tclassify.COLORS, list(tclassify.COLORS)))
        self.assertEqual((mic, nm), (tclassify.MIC_MIN, tplan.NAME_MAX))
        sync_consts = run_js(self, LOAD_ALL, [call("TidySync.MIN_CONFIDENCE"), call("TidySync.REFINE_SPAN")])
        self.assertEqual(sync_consts, [tsync.MIN_CONFIDENCE, tsync.REFINE_SPAN])


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyTwinsRandom(unittest.TestCase):
    def test_category_and_bin_on_600_random_items_in_four_contexts(self):
        r = random.Random(21)
        paths = []
        items = []
        for i in range(600):
            it = rand_item(r, "n%d" % i, paths)
            if r.random() < 0.3:
                it["name"] = r.choice(WORDS) + r.choice(["", " 2", "_01", "-v2", ".final"])
            items.append(it)
        cams = tclassify.camera_numbers(items)
        items[1].update(isSequence=True, name="Nest", path="")                 # nodeIds n1 / n3 are nests in the contexts below
        items[3].update(isSequence=True, name="Nest 3", path="")
        ctxs = [{"nestIds": {"n1": True, "n2": True}, "mode": "reels"}, {"mode": "podcast", "camNumbers": cams}, {"mode": "podcast"},
                {"nestIds": {"n3": True}, "mode": "reels", "camNumbers": cams}, None, {}]
        calls = [call("TidyClassify.category", it, ctx) for it in items for ctx in ctxs]
        calls += [call("TidyClassify.cameraNumbers", items), call("TidyClassify.cameraNumbers", items[:50]), call("TidyClassify.cameraNumbers", [])]
        js = run_js(self, ["js/classify.js"], calls)
        want = [tclassify.category(it, ctx) for it in items for ctx in ctxs]
        self.assertEqual(js[:len(want)], want)
        self.assertEqual(js[len(want):], [tclassify.camera_numbers(items), tclassify.camera_numbers(items[:50]), {}])
        seen = set(want)
        self.assertEqual(seen, {"footage", "renders", "sfx", "voice", "music", "mics", "png", "jpg", "icons", "images", "graphics", "captions", "other", "sequences", "nests"})
        bcalls, bwant = [], []
        for it in items[:300]:
            for ctx in ctxs[:4]:
                cat = tclassify.category(it, ctx)
                bcalls.append(call("TidyClassify.binFor", cat, it, ctx))
                bwant.append(tclassify.bin_for(cat, it, ctx))
        self.assertEqual(run_js(self, ["js/classify.js"], bcalls), bwant)
        self.assertGreater(len({w for w in bwant if w and "/Cam " in w}), 2)

    def test_ext_and_regex_edges(self):
        paths = ["a.MP4", "a.mp4\n", "a.", ".mp4", "a.b.c", "a.\u00e9x", "a.tar.GZ", "noext", "", None, "dir.d/file", "C:\\x\\y.JPG", "a. mp4", "a.mp4 ", "A.\u212a"]
        names = ["whoosh", "WHOOSH", "who\u00f6sh", "a_sfx_", "sfx\n", "a-click-b", "clicker", "Music", "MUSIC!", "\u00e9music\u00e9", "song2", "my song", "ost", "most",
                 "hit", "white", "Architecture", "fx_1", "fx1", "x" * 5, "bgm", "BGM_loop", "\u017fong", "m\u00fasic", "beat\n", "t\u212arack", "tr\u00e4ck"]
        calls = [call("TidyClassify.ext", p) for p in paths]
        for n in names:
            for e in ("wav", "mp4"):
                calls.append(call("TidyClassify.category", {"name": n, "path": "/a/" + n + "." + e, "isSequence": False, "duration": 20}, {"mode": "reels"}))
                calls.append(call("TidyClassify.category", {"name": n, "path": "/a/x." + e, "isSequence": False, "duration": 4000, "kind": "render"}, {"mode": "podcast"}))
        js = run_js(self, ["js/classify.js"], calls)
        want = [tclassify.ext(p) for p in paths]
        for n in names:
            for e in ("wav", "mp4"):
                want.append(tclassify.category({"name": n, "path": "/a/" + n + "." + e, "isSequence": False, "duration": 20}, {"mode": "reels"}))
                want.append(tclassify.category({"name": n, "path": "/a/x." + e, "isSequence": False, "duration": 4000, "kind": "render"}, {"mode": "podcast"}))
        self.assertEqual(js, want)

    def test_build_on_270_random_scans_with_two_option_sets_each(self):
        r = random.Random(31)
        scans = [rand_scan(r) for _ in range(270)]
        jobs = [(s, rand_opts(r, s)) for s in scans] + [(s, rand_opts(r, s)) for s in scans]
        calls = [call("TidyPlan.build", s, o) for s, o in jobs]
        js = run_js(self, ["js/classify.js", "js/plan.js"], calls)
        stats = {"removals": 0, "moves": 0, "colors": 0, "duplicates": 0, "offline": 0, "emptyBins": 0, "renames": 0, "backup": 0, "dup_reason": 0,
                 "podcast_cam": 0, "win32": 0}
        for (s, o), want in zip(jobs, js):
            got = tplan.build(copy.deepcopy(s), copy.deepcopy(o))
            if dumps(want) != dumps(got):
                self.fail("build differs\nopts=%s\nscan=%s\njs =%s\npy =%s" % (json.dumps(o), json.dumps(s)[:3000], dumps(want)[:3000], dumps(got)[:3000]))
            for k in ("removals", "moves", "colors", "duplicates", "offline", "emptyBins", "renames"):
                stats[k] += len(want[k])
            stats["backup"] += sum(1 for x in want["removals"] if x["reason"] == "backup")
            stats["dup_reason"] += sum(1 for x in want["removals"] if x["reason"] == "duplicate")
            stats["podcast_cam"] += sum(1 for m in want["moves"] if "/Cam " in m["to"])
            stats["win32"] += 1 if o.get("platform") == "win32" and want["duplicates"] else 0
        for k, minimum in (("removals", 500), ("moves", 800), ("colors", 800), ("duplicates", 40), ("offline", 60), ("emptyBins", 200),
                           ("renames", 80), ("backup", 20), ("dup_reason", 20), ("podcast_cam", 20), ("win32", 5)):
            self.assertGreaterEqual(stats[k], minimum, (k, stats))

    def test_duplicates_are_listed_in_js_property_order(self):
        """for (path in byPath): integer-like keys first (ascending), the others in insertion order."""
        scans = []
        for order in (["zz.mp4", "7", "12", "abc", "3"], ["3", "12", "7"], ["b", "a"], ["10", "9", "x", "100", "1"]):
            items = []
            for p in order:
                items += [{"nodeId": "a" + p, "name": "n" + p, "path": p}, {"nodeId": "b" + p, "name": "n" + p, "path": p}]
            items.append({"nodeId": "s", "name": "S", "path": "", "isSequence": True})
            scans.append({"items": items, "usage": {"s": [i["nodeId"] for i in items[:-1]]}})
        js = run_js(self, ["js/classify.js", "js/plan.js"], [call("TidyPlan.build", sc, {}) for sc in scans])
        for sc, j in zip(scans, js):
            self.assertEqual(dumps(j["duplicates"]), dumps(tplan.build(sc, {})["duplicates"]))
        self.assertEqual([d["path"] for d in js[0]["duplicates"]], ["3", "7", "12", "zz.mp4", "abc"])
        self.assertEqual([d["path"] for d in js[3]["duplicates"]], ["1", "9", "10", "100", "x"])

    def test_path_keys_names_and_regexes(self):
        r = random.Random(41)
        paths = [rand_path(r)[0] for _ in range(120)] + ["C:\\M\\Clip.MP4", "c:/m/clip.mp4", "\u0130stanbul\\\u03a3\u0391\u03a3.mp4", "A\\B/c\\D", "", "x" * 100]
        calls = [call("TidyPlan.pathKey", p, plat) for p in paths for plat in ("win32", "darwin", None, "linux")]
        names = ["Episode 12.prproj", "Episode 12", "", None, "a.PRPROJ", "My.prproj.prproj", ".prproj", "Cut v1.2.prproj", "\u062d\u0644\u0642\u0629.prproj", "x " + chr(0x1F600)]
        existing = [[], ["Episode 12 - Synced"], ["Episode 12 - Synced", "Episode 12 - Synced 2", "Episode 12 - Synced 3"], None, ["Podcast - Synced"], ["a.PRPROJ - Synced"]]
        calls += [call("TidyPlan.syncedName", n, ex) for n in names for ex in existing]
        js = run_js(self, ["js/classify.js", "js/plan.js"], calls)
        want = [tplan.path_key(p, plat) for p in paths for plat in ("win32", "darwin", None, "linux")]
        want += [tplan.synced_name(n, copy.deepcopy(ex)) for n in names for ex in existing]
        mismatch = [(c["args"], j, w) for c, j, w in zip(calls, js, want) if j != w]
        self.assertEqual(mismatch, [])

    def test_nest_names_and_the_utf16_cut(self):
        r = random.Random(51)
        texts = ["  \u0647\u064a\u0631\u0642\u064a\u0643   \u0644\u0648  ", "3", "", "  ", "a" * 49 + chr(0x1F600) + "bc de", "x" * 48 + chr(0x1F600) + " tail words", "word " * 20,
                 "\u00a0\u3000padded\ufeff", "a" * 50, "a" * 51, "a" * 49 + " b", "ab " * 17, chr(0x1F600) * 30, "\u0627" * 60, "Title\n\nSecond line", None, 5]
        calls = []
        byid = {"i": {"name": "Corporate Success.png", "path": "/a/Corporate Success.png", "isSequence": False},
                "c": {"name": "C0001.MP4", "path": "/a/C0001.MP4", "isSequence": False}, "s": {"name": "  Inner   Seq ", "isSequence": True},
                "j": {"name": "x" * 47 + chr(0x1F600) + ".png", "path": "/a/x.JPEG", "isSequence": False},
                "k": {"name": "clip.mkv.final", "path": "/a/k", "isSequence": False}, "l": {"name": "." + "a" * 60 + ".abcdef", "path": "/a/l.mp4"}}
        for t in texts:
            calls.append(call("TidyPlan.nestName", {}, [t], [], byid))
            calls.append(call("TidyPlan.nestName", {}, [None, "", t], ["c"], byid))
        for ids in (["c", "i"], ["i"], ["s"], ["s", "c"], ["j"], ["k"], ["l"], ["zzz", "c"], [], ["c", "c"]):
            calls.append(call("TidyPlan.nestName", {}, [], ids, byid))
        js = run_js(self, ["js/classify.js", "js/plan.js"], calls)
        want = []
        for t in texts:
            want.append(tplan.nest_name({}, [t], [], byid))
            want.append(tplan.nest_name({}, [None, "", t], ["c"], byid))
        for ids in (["c", "i"], ["i"], ["s"], ["s", "c"], ["j"], ["k"], ["l"], ["zzz", "c"], [], ["c", "c"]):
            want.append(tplan.nest_name({}, [], ids, byid))
        self.assertEqual(js, want)

    def test_backup_and_name_regexes_on_many_names(self):
        r = random.Random(61)
        names = ["Main (Hush backup 10:00:00)", "Main (WhyNot Hush cut 1)", "Main Hush backup", "(Hush backup ", "(hush backup 1)", "(Hush  backup 1)", "Main (Tidy backup 2026-10-12 1542)",
                 "WhyNot Tidy sync temp", "Tidy sync temp", "Tidy sync temp\n", "xTidy sync temp", "(WhyNot Tidy backup 1).prproj"] + [rand_item(r, "q", [])["name"] or "" for _ in range(100)]
        calls = []
        for n in names:
            calls += [call("TidyPlan.BACKUP.test", n), call("TidyPlan.TEMP_SYNC.test", n), call("TidyPlan.TIDY_BACKUP.test", n), call("TidyPlan.IMAGE.test", n)]
        js = run_js(self, ["js/classify.js", "js/plan.js"], calls)
        want = []
        for n in names:
            want += [bool(tplan.BACKUP.search(n)), bool(tplan.TEMP_SYNC.search(n)), bool(tplan.TIDY_BACKUP.search(n)), bool(tplan.IMAGE.search(n))]
        self.assertEqual(js, want)


def rand_roles(r, ids):
    roles = {}
    for i in ids:
        kind = r.random()
        if kind < 0.2:
            roles[i] = {"role": "mic", "seconds": r.choice([0, 30, 300, 3600])}
        elif kind < 0.95:
            roles[i] = {"role": "cam", "cam": r.choice([1, 1, 2, 3, 0, None]), "seconds": r.choice([0, 5, 10, 60.5, 120, 300, None])}
            if roles[i]["cam"] is None:
                del roles[i]["cam"]
            if roles[i]["seconds"] is None:
                del roles[i]["seconds"]
        elif kind < 0.98:
            roles[i] = {}
    return roles


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyTwinsSync(unittest.TestCase):
    SCENARIOS = [
        # name, seed, world seconds, [(id, start, end)], stranger seconds
        ("camera_later_and_earlier", 7, 45, [("mic", 0, 45), ("camA", 3.217, 38), ("camB", 12, 44.5)], 20),
        ("negative_offsets_ref_is_the_late_one", 8, 60, [("long", 8, 58), ("early", 0, 30), ("pre", 3, 27), ("tail", 40, 59)], None),
        ("three_cameras_two_mics", 9, 60, [("micH", 0, 60), ("micG", 1.5, 58), ("c1", 5, 40), ("c2", 20.25, 59), ("c3", 33.1, 55)], 25),
        ("two_strangers", 10, 40, [("mic", 0, 40), ("cam", 6.5, 33)], 15),
        ("one_track", 11, 20, [("only", 0, 20)], None),
        ("two_tracks_same_length_tie", 12, 30, [("a", 0, 30), ("b", 0, 30)], None),
        ("tiny_overlap", 13, 40, [("a", 0, 40), ("b", 35, 40)], None),
        ("1ms_offsets", 14, 35, [("ref", 0, 35), ("x", 0.001, 30), ("y", 0.002, 34), ("z", 4.999, 33)], None),
        ("quiet_and_loud", 15, 45, [("ref", 0, 45), ("quiet", 2, 40)], None),
        ("many", 16, 55, [("t%d" % i, i * 2.7, 55 - i * 1.3) for i in range(7)], 30),
    ]

    def tracks(self, seed, seconds, spec, stranger):
        w = world(seed, seconds)
        tracks = [make_track(tid, track_from(w, s, e, seed * 10 + i, noise=0.0002 if tid != "quiet" else 0.00005)) for i, (tid, s, e) in enumerate(spec)]
        if stranger:
            tracks.insert(1 if len(tracks) > 1 else 0, make_track("stranger", world(seed + 1000, stranger)))
        return tracks

    def test_plans_match_and_find_the_planted_offsets(self):
        results = []
        for name, seed, seconds, spec, stranger in self.SCENARIOS:
            tracks = self.tracks(seed, seconds, spec, stranger)
            js = run_js(self, ["js/sync.js"], [call("TidySync.plan", tracks)])[0]
            py = tsync.plan(copy.deepcopy(tracks))
            try:
                same(js, py)
            except AssertionError as e:
                self.fail("%s: %s\njs=%s\npy=%s" % (name, e, json.dumps(js)[:600], json.dumps(canon(py))[:600]))
            self.assertEqual([p["id"] for p in js["placed"]], [p["id"] for p in canon(py)["placed"]], name)
            results.append((name, js))
            # the planted truth (so the scenario really tests something): within 3 ms for every track that is not a stranger
            starts = dict((tid, st) for tid, st, _ in spec)
            if js["ref"] in starts and name != "tiny_overlap":
                for p in js["placed"]:
                    if p["id"] in starts:
                        self.assertAlmostEqual(p["offset"], starts[p["id"]] - starts[js["ref"]], delta=0.003, msg="%s %s" % (name, p["id"]))
        by = dict(results)
        self.assertIn("stranger", by["camera_later_and_earlier"]["skipped"])
        self.assertEqual(by["one_track"]["placed"][0]["offset"], 0)
        self.assertGreaterEqual(len(by["many"]["placed"]), 5)
        self.assertTrue(any(p["offset"] < 0 for _, r in results for p in r["placed"]))
        self.assertTrue(any(r["skipped"] for _, r in results))

    def test_a_two_hour_scale_overlap_uses_the_120_second_window(self):
        """REFINE_SPAN: the dot product runs over at most 120 s of overlap (60000 samples each side of the middle); a 140 s
        overlap is the shortest test that reaches the cap."""
        w = world(31, 150)
        tracks = [make_track("ref", track_from(w, 0, 150, 1)), make_track("x", track_from(w, 6.789, 146, 2))]
        js = run_js(self, ["js/sync.js"], [call("TidySync.plan", tracks)])[0]
        py = tsync.plan(copy.deepcopy(tracks))
        same(js, py)
        self.assertAlmostEqual(js["placed"][1]["offset"], 6.789, delta=0.003)

    def test_the_refine_window_is_capped_at_120_seconds(self):
        """Built so that the answer depends on the cap: x agrees with ref at lag 5000 in a 40 000-sample stretch around the
        middle and at lag 5001 everywhere else. A 120 000-sample window (the cap) sees more of the second, so JS says 5.001;
        a window half as wide would say 5.000."""
        rng = np.random.RandomState(5)
        ref = rng.randn(220000)
        x = np.empty(200000)
        idx = np.arange(len(x))
        in_a = (idx >= 80000) & (idx < 120000)
        x[in_a] = ref[idx[in_a] + 5000]
        x[~in_a] = ref[idx[~in_a] + 5001]
        js = run_js(self, ["js/sync.js"], [call("TidySync.refine", ref.tolist(), x.tolist(), 1000, 5.0, 0.5)])[0]
        self.assertEqual(js, 5.001)
        self.assertEqual(tsync.refine(ref, x, 1000, 5.0, 0.5), 5.001)
        orig = tsync.REFINE_SPAN
        with mock.patch.object(tsync, "REFINE_SPAN", orig // 2):
            self.assertEqual(tsync.refine(ref, x, 1000, 5.0, 0.5), 5.0)

    def test_twelve_random_shoots(self):
        """Random layouts: 2 to 5 recordings of a 25-40 s world with random starts and ends (half or more of each clip overlaps
        the longest one), sometimes a stranger, sometimes a recorder that does not start at 0; plans must agree."""
        r = random.Random(81)
        placed_total = skipped_total = 0
        for k in range(12):
            seconds = r.choice([25, 30, 35, 40])
            spec = []
            for i in range(r.randrange(2, 6)):
                start = r.choice([0, 0, r.uniform(0, seconds * 0.3)])
                end = r.uniform(start + seconds * 0.45, seconds)
                spec.append(("t%d" % i, round(start, 3), round(end, 3)))
            tracks = self.tracks(200 + k, seconds, spec, r.choice([None, 12, 20]))
            js = run_js(self, ["js/sync.js"], [call("TidySync.plan", tracks)])[0]
            py = tsync.plan(copy.deepcopy(tracks))
            try:
                same(js, py)
            except AssertionError as e:
                self.fail("shoot %d %s: %s" % (k, spec, e))
            self.assertEqual([p["id"] for p in js["placed"]], [p["id"] for p in canon(py)["placed"]])
            placed_total += len(js["placed"])
            skipped_total += len(js["skipped"])
        self.assertGreater(placed_total, 20)
        self.assertGreater(skipped_total, 2)

    def test_offset_refine_envelope_and_from_power_parity(self):
        w = world(21, 40)
        ref = tsync.from_power(track_from(w, 0, 40, 1))
        x = tsync.from_power(track_from(w, 4.321, 35, 2))
        other = tsync.from_power(world(22, 30))
        short = tsync.from_power(track_from(w, 20, 24, 3))
        calls = [call("TidySync.offset", ref["env"].tolist(), c["env"].tolist(), 100) for c in (x, other, short, ref)]
        calls += [call("TidySync.offset", x["env"].tolist(), ref["env"].tolist(), 100), call("TidySync.offset", [], [], 100), call("TidySync.offset", [1.0], [1.0], 100),
                  call("TidySync.offset", [0.0] * 50, [0.0] * 40, 100)]
        for coarse in (4.32, 4.3, 4.0, 0.0, -1.0):
            calls.append(call("TidySync.refine", ref["hi"].tolist(), x["hi"].tolist(), 1000, coarse, 0.5))
        calls += [call("TidySync.refine", ref["hi"].tolist(), x["hi"].tolist(), 1000, 4.32, None), call("TidySync.refine", ref["hi"][:500].tolist(), x["hi"][:900].tolist(), 1000, 0.1, 0.5)]
        power = [track_from(w, 0, 40, 1), np.zeros(0), np.full(7, 0.5), np.full(10, 0.0), np.array([0.25] * 999)]
        calls += [call("TidySync.fromPower", p.tolist()) for p in power]
        samples = [np.sin(np.arange(24000) * 0.3) * 0.5, np.random.RandomState(1).randn(44100) * 0.1, np.random.RandomState(2).randn(48000) * 0.2, np.zeros(1000)]
        env_args = [(0, 8000, 100), (1, 44100, 1000), (1, 44100, 100), (2, 48000, 100), (2, 48000, 1000), (0, 8000, 1000), (3, 8000, 100), (0, 22050, 100)]
        calls += [call("TidySync.envelope", samples[i].tolist(), rate, out, typed={"0": "Float64Array"}) for i, rate, out in env_args]
        js = run_js(self, ["js/sync.js"], calls)
        want = [tsync.offset(ref["env"], c["env"], 100) for c in (x, other, short, ref)]
        want += [tsync.offset(x["env"], ref["env"], 100), tsync.offset([], [], 100), tsync.offset([1.0], [1.0], 100), tsync.offset([0.0] * 50, [0.0] * 40, 100)]
        for coarse in (4.32, 4.3, 4.0, 0.0, -1.0):
            want.append(tsync.refine(ref["hi"], x["hi"], 1000, coarse, 0.5))
        want += [tsync.refine(ref["hi"], x["hi"], 1000, 4.32, None), tsync.refine(ref["hi"][:500], x["hi"][:900], 1000, 0.1, 0.5)]
        want += [tsync.from_power(p) for p in power]
        want += [tsync.envelope(samples[i], rate, out) for i, rate, out in env_args]
        for i, (j, p) in enumerate(zip(js, want)):
            try:
                same(j, p)
            except AssertionError as e:
                self.fail("call %d (%s): %s" % (i, calls[i]["fn"], e))
        self.assertAlmostEqual(js[0]["offset"], 4.32, delta=0.02)
        self.assertGreater(js[0]["confidence"], 3)

    def test_layout_on_250_random_plans(self):
        r = random.Random(71)
        cases = []
        for _ in range(250):
            n = r.choice([0, 1, 2, 3, 5, 8, 12])
            ids = ["id%d" % i for i in range(n)]
            placed = [{"id": i, "offset": r.choice([0, 0.5, -2.5, 20, 400, -30.75, 5, 5, 10.000001, r.uniform(-50, 500)]), "confidence": r.choice([99, 4.2, 10])} for i in ids]
            cases.append(({"placed": placed, "skipped": [i for i in ("x", "y") if r.random() < 0.3]}, rand_roles(r, ids + ["x", "y"])))
        js = run_js(self, ["js/sync.js"], [call("TidySync.layout", p, ro) for p, ro in cases])
        want = [tsync.layout(copy.deepcopy(p), copy.deepcopy(ro)) for p, ro in cases]
        for (p, ro), j, w in zip(cases, js, want):
            self.assertEqual(dumps(j), dumps(w), json.dumps([p, ro]))
        self.assertTrue(any(len({c["track"] for c in j["cams"]}) > 2 for j in js))
        self.assertGreater(sum(len(j["mics"]) for j in js), 40)

    def test_wav_info_is_shared_with_the_engine_module(self):
        from lib.tidy import wavpower
        self.assertIs(tsync.wav_info, wavpower.wav_info)


# ---------------------------------------------------------------- the mutation proof for the parity harness itself

@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyTwinsHarnessCanFail(unittest.TestCase):
    """The parity tests would be worthless if they could not fail: break the twin in memory and require the failure."""

    def test_a_wrong_twin_is_caught_by_the_recorded_upstream_cases(self):
        # break a word the owner's cases use ("music") in the twin: some recorded category call must now differ
        with mock.patch.object(tclassify, "MUSIC_WORDS", re.compile(tclassify.MUSIC_WORDS.pattern.replace("music|", ""), re.I | re.A)):
            bad = []
            for c in record(self, "test_classify.js") + record(self, "test_plan.js"):
                if c["fn"] == "TidyClassify.category":
                    try:
                        same(c["result"], replay(c["fn"], c["args"]))
                    except AssertionError:
                        bad.append(c["args"][0].get("name"))
        self.assertTrue(bad)

    def test_a_wrong_plan_twin_is_caught_by_the_random_scans(self):
        r = random.Random(31)
        scans = [rand_scan(r) for _ in range(120)]
        opts = [dict(rand_opts(r, s), platform="win32") for s in scans]
        js = run_js(self, ["js/classify.js", "js/plan.js"], [call("TidyPlan.build", s, o) for s, o in zip(scans, opts)])
        self.assertEqual([i for i, (s, o, j) in enumerate(zip(scans, opts, js)) if dumps(tplan.build(copy.deepcopy(s), copy.deepcopy(o))) != dumps(j)], [])
        # a path key that forgets to lower-case on Windows: some plan of the corpus groups the files differently
        with mock.patch.object(tplan, "path_key", lambda p, plat=None: str(p).replace("\\", "/") if plat == "win32" else p):
            diffs = [i for i, (s, o, j) in enumerate(zip(scans, opts, js)) if dumps(tplan.build(copy.deepcopy(s), copy.deepcopy(o))) != dumps(j)]
        self.assertTrue(diffs)
        # a wrong flag in one removal reason
        orig = tplan.build

        def broken(scan, o=None):
            out = orig(scan, o)
            for rm in out["removals"]:
                if rm["reason"] == "duplicate":
                    rm["checked"] = not rm["checked"]
            return out
        self.assertTrue([i for i, (s, o, j) in enumerate(zip(scans, opts, js)) if dumps(broken(copy.deepcopy(s), copy.deepcopy(o))) != dumps(j)])


    def test_a_wrong_sync_twin_is_caught_by_the_planted_scenarios(self):
        scen = TidyTwinsSync.SCENARIOS[:3]
        tracks = [TidyTwinsSync().tracks(seed, seconds, spec, stranger) for _, seed, seconds, spec, stranger in scen]
        js = run_js(self, ["js/sync.js"], [call("TidySync.plan", t) for t in tracks])

        def caught(patch_name, replacement):
            with mock.patch.object(tsync, patch_name, replacement):
                for t, j in zip(tracks, js):
                    try:
                        same(j, tsync.plan(copy.deepcopy(t)))
                    except AssertionError:
                        return True
            return False
        orig_refine = tsync.refine
        self.assertTrue(caught("MIN_CONFIDENCE", 6))                                    # a wrong threshold places fewer clips
        self.assertTrue(caught("refine", lambda *a, **k: orig_refine(*a, **k) + 0.001))  # one millisecond off is a failure
        orig_fft = tsync.fft

        def noisy(re_, im_, inverse=False):
            r, i = orig_fft(re_, im_, inverse)
            return r + 1e-3 * np.sin(np.arange(len(r)) * 7.0), i                        # an FFT that is not quite one
        self.assertTrue(caught("fft", noisy))
        self.assertFalse(caught("MIN_CONFIDENCE", 3))                                   # and the untouched twin passes


if __name__ == "__main__":
    unittest.main()
