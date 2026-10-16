# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N3 - WhyNot Hush pure JS port (adobe/tools/hush/src) against the owner's upstream.

* HushPortParity: every call of every Task 1 characterization test runs on BOTH roots and the JSON results must be
  identical. The single known difference is HushDetect.fmt where the upstream output is malformed ("0:010.0",
  "0:60.0"); the port rounds first (controller ruling). The characterization class itself runs on the port too (see
  test_hush_characterization.HushCharacterizationPort).
* HushPortFmt: the fmt fix on a grid of 13 000 values (independent Python expectation) and where it equals upstream.
* HushSettings*: settings.js (the panel's currentSettings / syncAdvFromSimple / readout, extracted from main.js:166-180 and :198
  without change): Tight zeroes the pads, advanced passes through, no stats falls back to the advanced settings.
* HushPortShape: the port differs from upstream only by the header, the CommonJS line and the fmt hunk (A0);
  require() returns the global object; SPDX header and provenance line; no "hoka"; README.
* JsRunnerContract: adobe/tools/_harness/js_runner.js contract (Infinity/NaN encoding, typed output, $file, an error slot
  per call, unserialisable result, exit 2 / 3).
Run:  bash tools/test.sh -p test_hush_port.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import test_hush_characterization as HC  # noqa: E402  (the module, so its TestCase classes are not collected twice)

NODE = HC.NODE
PORT = HC.ADOBE_TOOLS / "hush" / "src"
UPSTREAM = HC.ADOBE_TOOLS / "hush" / "_upstream"
LOAD = HC.LOAD
SETTINGS_LOAD = ["js/detect.js", "js/settings.js"]
call = HC.call
FILE = HC.FILE
WELL_FORMED = re.compile(r"^\d+:[0-5]\d\.\d$")


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(HC.TOOLS_PRESENT, HC.NO_TOOLS)
class HushPortParity(HC.HushCharacterizationPort):
    """Re-runs the whole characterization class; each js() call is also run on upstream and compared."""

    compared = 0
    fmt_differences = set()

    def js(self, calls, load=LOAD):
        up = HC.run_js(self, UPSTREAM, load, calls)
        port = HC.run_js(self, PORT, load, calls)
        for c, a, b in zip(calls, up, port):
            if c["fn"] == "HushDetect.fmt" and a != b:
                # the only known difference: upstream printed a malformed time, the port a well-formed one
                self.assertNotRegex(a, WELL_FORMED, c)
                self.assertRegex(b, WELL_FORMED, c)
                type(self).fmt_differences.add(c["args"][0])
            else:
                self.assertEqual(a, b, "upstream and port differ for %s" % json.dumps(c)[:200])
            type(self).compared += 1
        return port

    @classmethod
    def tearDownClass(cls):
        # only the values the tests feed that round up across 10 s / 60 s may differ (each is checked to be malformed upstream)
        if not cls.fmt_differences <= {9.96, 59.96, 119.96, 599.96, 3599.96}:
            raise AssertionError("unexpected fmt differences: %r" % sorted(cls.fmt_differences))
        super().tearDownClass()


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(HC.TOOLS_PRESENT, HC.NO_TOOLS)
class HushPortFmt(unittest.TestCase):
    def fmt(self, root, values):
        return HC.run_js(self, root, ["js/detect.js"], [call("HushDetect.fmt", v) for v in values])

    def test_fmt_on_a_grid_matches_python_and_upstream_where_upstream_is_well_formed(self):
        hundredths = list(range(0, 13000))  # 0.00 .. 129.99 s
        values = [i / 100 for i in hundredths] + [599.96, 3599.96, 3725.04, 86399.96]
        port = self.fmt(PORT, values)
        up = self.fmt(UPSTREAM, values)
        differ = 0
        for v, p, u in zip(values, port, up):
            self.assertRegex(p, WELL_FORMED, v)  # never "0:60.0" or "0:010.0"
            if WELL_FORMED.match(u):
                self.assertEqual(p, u, v)
            else:
                differ += 1
        self.assertGreater(differ, 0)  # the grid does reach the upstream bug (9.95..9.99, 59.95..59.99, ...)
        for i in hundredths:
            if i % 10 == 5:
                continue  # exact ties in the hundredths are decided by binary representation: skipped here
            tenths = (i + 5) // 10  # round half up to 0.1 s on exact integers
            m, s10 = divmod(tenths, 600)
            self.assertEqual(port[i], "%d:%02d.%d" % (m, s10 // 10, s10 % 10), i / 100)

    def test_fmt_edges(self):
        cases = [(0, "0:00.0"), (-5, "0:00.0"), (9.96, "0:10.0"), (59.96, "1:00.0"), (119.96, "2:00.0"),
                 (599.96, "10:00.0"), (3599.96, "60:00.0"), (9.94, "0:09.9"), (59.94, "0:59.9"), (65.5, "1:05.5")]
        self.assertEqual(self.fmt(PORT, [v for v, _ in cases]), [w for _, w in cases])
        self.assertEqual(self.fmt(UPSTREAM, [9.96, 59.96]), ["0:010.0", "0:60.0"])  # what the port fixed


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(HC.TOOLS_PRESENT, HC.NO_TOOLS)
class HushSettingsTest(unittest.TestCase):
    STATS = {"floor": -60, "speech": -20}  # span 40
    ADV = {"threshold": -33.5, "minSilence": 0.4, "padBefore": 0.07, "padAfter": 0.05}

    def one(self, fn, *args):
        return HC.run_js(self, PORT, SETTINGS_LOAD, [call(fn, *args)])[0]

    def cfg(self, **kw):
        c = {"tab": "simple", "intensity": 50, "tight": False, "adv": dict(self.ADV)}
        c.update(kw)
        return c

    def prd(self, intensity, floor=-60, speech=-20):
        return HC.HushCharacterizationMixin.from_intensity_prd(intensity, floor, speech)

    def test_current_simple_uses_the_intensity_and_keeps_the_pads_when_not_tight(self):
        for i in (0, 25, 50, 80, 100):
            got = self.one("HushSettings.current", self.cfg(intensity=i), self.STATS)
            self.assertEqual(got, self.prd(i), i)
        # hand check at 80 (t = 0.8): threshold -60 + 40 * 0.39 = -44.4, minSilence 0.9 - 0.52 = 0.38, pad 0.084 -> 0.08
        self.assertEqual(self.one("HushSettings.current", self.cfg(intensity=80), self.STATS),
                         {"threshold": -44.4, "minSilence": 0.38, "padBefore": 0.08, "padAfter": 0.08})

    def test_current_tight_zeroes_both_pads_and_nothing_else(self):
        for i in (0, 25, 50, 80, 100):
            got = self.one("HushSettings.current", self.cfg(intensity=i, tight=True), self.STATS)
            want = self.prd(i)
            want["padBefore"] = 0
            want["padAfter"] = 0
            self.assertEqual(got, want, i)
        got = self.one("HushSettings.current", self.cfg(intensity=50, tight=True), self.STATS)
        self.assertEqual(got, {"threshold": -48.0, "minSilence": 0.57, "padBefore": 0, "padAfter": 0})

    def test_current_advanced_tab_passes_the_advanced_settings_through(self):
        # even with stats, and even with Tight on: only the simple tab is affected by Tight
        for tight in (False, True):
            got = self.one("HushSettings.current", self.cfg(tab="adv", tight=tight), self.STATS)
            self.assertEqual(got, self.ADV)

    def test_current_without_stats_falls_back_to_the_advanced_settings(self):
        for stats in (None,):
            for tight in (False, True):
                self.assertEqual(self.one("HushSettings.current", self.cfg(tight=tight), stats), self.ADV)

    def test_adv_from_simple(self):
        got = self.one("HushSettings.advFromSimple", self.cfg(intensity=80), self.STATS)
        self.assertEqual(got, {"threshold": -44.4, "minSilence": 0.38, "padBefore": 0.08, "padAfter": 0.08})
        got = self.one("HushSettings.advFromSimple", self.cfg(intensity=80, tight=True), self.STATS)
        self.assertEqual(got, {"threshold": -44.4, "minSilence": 0.38, "padBefore": 0, "padAfter": 0})
        self.assertEqual(sorted(got), ["minSilence", "padAfter", "padBefore", "threshold"])
        self.assertIsNone(self.one("HushSettings.advFromSimple", self.cfg(), None))  # no stats: nothing to sync

    def test_readout_string_is_exact(self):
        # main.js:198: threshold + ' dB  |  ' + round(minSilence*1000) + ' ms min  |  ' + round(padBefore*1000) + '/' +
        #              round(padAfter*1000) + ' ms pad'   (two spaces around the bars)
        cases = [
            ({"threshold": -44.4, "minSilence": 0.38, "padBefore": 0.08, "padAfter": 0.08},
             "-44.4 dB  |  380 ms min  |  80/80 ms pad"),
            ({"threshold": -48, "minSilence": 0.57, "padBefore": 0, "padAfter": 0},
             "-48 dB  |  570 ms min  |  0/0 ms pad"),
            ({"threshold": -33.5, "minSilence": 0.4, "padBefore": 0.07, "padAfter": 0.05},
             "-33.5 dB  |  400 ms min  |  70/50 ms pad"),
            ({"threshold": -42, "minSilence": 0.25, "padBefore": 0.06, "padAfter": 0.12},
             "-42 dB  |  250 ms min  |  60/120 ms pad"),
        ]
        got = HC.run_js(self, PORT, SETTINGS_LOAD, [call("HushSettings.readout", st) for st, _ in cases])
        self.assertEqual(got, [w for _, w in cases])

    def test_readout_matches_the_panel_source(self):
        src = (UPSTREAM / "js" / "main.js").read_text(encoding="utf-8")
        for piece in ("st.threshold + ' dB  |  '", "Math.round(st.minSilence * 1000) + ' ms min  |  '",
                      "Math.round(st.padBefore * 1000) + '/' + Math.round(st.padAfter * 1000) + ' ms pad'"):
            self.assertIn(piece, src)

    def test_settings_feed_the_plan_so_tight_cuts_right_up_to_speech(self):
        # end to end through the port: stats of an envelope, Tight settings, plan. Speech 1.0 s, silence 1.0 s, speech 1.0 s
        env = [-20.0] * 100 + [-60.0] * 100 + [-20.0] * 100
        calls = [call("HushDetect.stats", env)]
        stats = HC.run_js(self, PORT, SETTINGS_LOAD, calls)[0]
        self.assertEqual(stats, {"floor": -60, "speech": -20})
        tight = self.one("HushSettings.current", self.cfg(intensity=50, tight=True), stats)
        loose = self.one("HushSettings.current", self.cfg(intensity=50, tight=False), stats)
        t = HC.run_js(self, PORT, SETTINGS_LOAD, [call("HushDetect.plan", env, tight, [], 3.0, 25),
                                                  call("HushDetect.plan", env, loose, [], 3.0, 25)])
        # silence 1.0-2.0: Tight removes exactly 25..50 frames = 1.0 s; pads 0.12 leave 1.12-1.88 -> frames 28..47
        self.assertAlmostEqual(t[0]["removed"], 1.0, places=9)
        self.assertAlmostEqual(t[1]["removed"], 0.76, places=9)  # (47 - 28) / 25 = 0.76


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(HC.TOOLS_PRESENT, HC.NO_TOOLS)
class HushPortShape(unittest.TestCase):
    FILES = ["wav", "detect", "fillers", "settings"]
    GLOBALS = {"wav": "HushWav", "detect": "HushDetect", "fillers": "HushFillers", "settings": "HushSettings"}
    SPDX = ["// SPDX-License-Identifier: GPL-3.0-or-later", "// © 2026 The Why Not AI (thewhynot.ai)"]
    UMD = "    if (typeof module === 'object' && module.exports) { module.exports = %s; }"
    # the one logic change (controller ruling): round the seconds to 0.1 before the minutes are split
    FMT_OLD = """    D.fmt = function (sec) {
        sec = Math.max(0, sec);
        var m = Math.floor(sec / 60), s = sec - m * 60;
        return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1);
    };
"""

    def text(self, path):
        data = path.read_bytes()
        self.assertNotIn(b"\r", data, path)
        return data.decode("utf-8")

    def test_files_and_readme_exist(self):
        for f in self.FILES:
            self.assertTrue((PORT / "js" / (f + ".js")).is_file(), f)
        readme = self.text(PORT / "README.md")
        for needle in ("_upstream", "settings.js", "fmt", "module.exports"):
            self.assertIn(needle, readme)

    def test_spdx_header_provenance_line_and_no_hoka(self):
        for f in self.FILES:
            path = PORT / "js" / (f + ".js")
            lines = self.text(path).split("\n")
            self.assertEqual(lines[:2], self.SPDX, f)
            self.assertTrue(lines[2].startswith("// "), f)
            self.assertIn("owner's Hush", lines[2], f)
            self.assertIn("adobe/tools/hush/src/README.md", lines[2], f)
            self.assertNotIn("hoka", self.text(path).lower(), f)
        self.assertNotIn("hoka", self.text(PORT / "README.md").lower())

    def test_wav_detect_fillers_differ_from_upstream_only_by_header_umd_line_and_fmt(self):
        for f in ("wav", "detect", "fillers"):
            up = self.text(UPSTREAM / "js" / (f + ".js"))
            port_lines = self.text(PORT / "js" / (f + ".js")).split("\n")
            letter = {"wav": "W", "detect": "D", "fillers": "F"}[f]
            umd = self.UMD % letter
            self.assertEqual(port_lines.count(umd), 1, f)
            self.assertEqual(port_lines[port_lines.index(umd) - 1], "    root.%s = %s;" % (self.GLOBALS[f], letter), f)
            body = "\n".join(l for l in port_lines[3:] if l != umd)
            if f == "detect":
                self.assertIn(self.FMT_OLD, up)
                body_up = up.replace(self.FMT_OLD, "@@FMT@@")
                self.assertEqual(body.count("D.fmt = function (sec) {"), 1)
                start = body.index("    D.fmt = function (sec) {")
                end = body.index("    };\n", start) + len("    };\n")
                body = body[:start] + "@@FMT@@" + body[end:]
                self.assertEqual(body, body_up, f)
            else:
                self.assertEqual(body, up, f)

    def test_require_returns_the_global_object(self):
        script = (
            "globalThis.window = globalThis;\n"
            "var out = {};\n"
            "[%s].forEach(function (p) {\n"
            "  var name = p[0], file = p[1], m = require(file);\n"
            "  out[name] = (m === globalThis[name]) && typeof m === 'object';\n"
            "});\n"
            "console.log(JSON.stringify(out));\n"
        ) % ", ".join("[%s, %s]" % (json.dumps(self.GLOBALS[f]), json.dumps(str(PORT / "js" / (f + ".js"))))
                      for f in self.FILES)
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]), {v: True for v in self.GLOBALS.values()})

    def test_require_works_without_window_and_settings_finds_detect(self):
        script = (
            "var D = require(%s), S = require(%s);\n"
            "var st = S.current({tab: 'simple', intensity: 50, tight: true, adv: {}}, {floor: -60, speech: -20});\n"
            "console.log(JSON.stringify({d: typeof D.plan, f: typeof require(%s).find, w: typeof require(%s).envelope, st: st,"
            " win: typeof window}));\n"
        ) % (json.dumps(str(PORT / "js" / "detect.js")), json.dumps(str(PORT / "js" / "settings.js")),
             json.dumps(str(PORT / "js" / "fillers.js")), json.dumps(str(PORT / "js" / "wav.js")))
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual((out["d"], out["f"], out["w"], out["win"]), ("function", "function", "function", "undefined"))
        self.assertEqual(out["st"], {"threshold": -48.0, "minSilence": 0.57, "padBefore": 0, "padAfter": 0})


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(HC.TOOLS_PRESENT, HC.NO_TOOLS)
class JsRunnerContract(unittest.TestCase):
    """adobe/tools/_harness/js_runner.js, used by the Hush, Tidy and Kalam tests."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        (self.tmp / "root" / "js").mkdir(parents=True)

    def tearDown(self):
        self._td.cleanup()

    def run_raw(self, root, req):
        rp = self.tmp / "req.json"
        rp.write_text(json.dumps(req) if not isinstance(req, str) else req, encoding="utf-8")
        return subprocess.run([NODE, str(HC.RUNNER), str(root), str(rp)], capture_output=True, text=True,
                              encoding="utf-8", timeout=120)

    def results(self, calls, load=()):
        p = self.run_raw(self.tmp / "root", {"load": list(load), "calls": calls})
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)  # ONE json line
        return json.loads(lines[0])["results"]

    def test_infinity_and_nan_are_strings(self):
        got = self.results([call("Math.log", 0), call("Math.exp", 1000), call("Number.parseFloat", "x"),
                            call("Math.sqrt", 4)])
        self.assertEqual(got, ["-Infinity", "Infinity", "NaN", 2])

    def test_nested_values_are_converted(self):
        (self.tmp / "root" / "js" / "o.js").write_text(
            "window.Obj = {make: function () { return {a: [Infinity, 1, {b: NaN}], c: new Float32Array([0.5, 2]),"
            " d: undefined, e: null}; }, K: 7};", encoding="utf-8")
        got = self.results([call("Obj.make"), call("Obj.K")], load=["js/o.js"])
        self.assertEqual(got, [{"a": ["Infinity", 1, {"b": "NaN"}], "c": [0.5, 2], "e": None}, 7])

    def test_typed_arguments_and_typed_array_results(self):
        got = self.results([call("Array.from", [1.5, 2.5], typed={0: "Float32Array"}),
                            call("Float32Array.from", [1, 2, 3]),
                            call("Array.from", [1, 2], typed={0: "Nope"})])
        self.assertEqual(got[:2], [[1.5, 2.5], [1, 2, 3]])
        self.assertIn("error", got[2])

    def test_file_argument_becomes_bytes(self):
        f = self.tmp / "b.bin"
        f.write_bytes(b"hi\x00\xff")
        got = self.results([call("Array.from", FILE(f)), call("Array.from", None, bytes_file=f)])
        self.assertEqual(got, [[104, 105, 0, 255], [104, 105, 0, 255]])

    def test_a_throwing_call_gives_an_error_slot_and_the_run_continues(self):
        got = self.results([call("JSON.parse", "{"), call("Math.max", 1, 9), call("No.such.fn"), call("Math.min", 3, 2)])
        self.assertIn("error", got[0])
        self.assertEqual(got[1], 9)
        self.assertEqual(got[2], {"error": "not found: No.such.fn"})
        self.assertEqual(got[3], 2)

    def test_an_unserialisable_result_is_that_slots_error_not_a_crash(self):
        got = self.results([call("BigInt", 5), call("Math.max", 1, 2)])
        self.assertIn("error", got[0])
        self.assertEqual(got[1], 2)

    def test_files_load_in_order_with_window_as_the_global_object(self):
        (self.tmp / "root" / "js" / "a.js").write_text("window.X = 1; var local = 5;", encoding="utf-8")
        (self.tmp / "root" / "js" / "b.js").write_text("window.Y = X + 1; globalThis.Z = (window === globalThis);",
                                                       encoding="utf-8")
        self.assertEqual(self.results([call("Y"), call("Z")], load=["js/a.js", "js/b.js"]), [2, True])

    def test_exit_codes(self):
        # 2: unreadable request, 2: missing tool root, 3: a file named in "load" that cannot be loaded
        p = self.run_raw(self.tmp / "root", "{not json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("cannot read", p.stderr)
        p = self.run_raw(self.tmp / "no-such-root", {"load": [], "calls": []})
        self.assertEqual(p.returncode, 2)
        self.assertIn("cannot read", p.stderr)
        p = subprocess.run([NODE, str(HC.RUNNER), str(self.tmp / "root"), str(self.tmp / "missing.json")],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 2)
        p = self.run_raw(self.tmp / "root", {"load": ["js/missing.js"], "calls": []})
        self.assertEqual(p.returncode, 3)
        self.assertIn("cannot load", p.stderr)
        self.assertEqual(p.stdout, "")
        (self.tmp / "root" / "js" / "bad.js").write_text("this is not javascript (", encoding="utf-8")
        p = self.run_raw(self.tmp / "root", {"load": ["js/bad.js"], "calls": []})
        self.assertEqual(p.returncode, 3)


if __name__ == "__main__":
    unittest.main()
