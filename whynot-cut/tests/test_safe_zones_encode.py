# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Delivery-encode check of the safe-zone profiles (Phase 4 Task 27, R-4.5): encode_findings and its probes' parsers.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.5-safe-zone-profiles.md ("Delivery-encode check").
The profile the checks run against is a TEST FIXTURE with made-up limits (the shipped file carries only what the
platforms publish: no loudness, level or GOP number). Case list: C50-C54.
Run:  tools/test.sh -p test_safe_zones_encode.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import safe_zones as SZ  # noqa: E402

FIX = SK / "tests" / "fixtures" / "safe_zones"

GOOD = {"codec": "h264", "profile": "High", "level": 4.1, "pix_fmt": "yuv420p", "gop_s": 2.0, "closed_gop": True,
        "audio_codec": "aac", "loudness_lufs": -14.0, "true_peak_dbtp": -1.5}


def fixture_profile():
    """A real profile with a test-only encode block (every key filled) written to a temp file."""
    d = json.loads((SK / "config" / "defaults" / "safe-zones.json").read_text(encoding="utf-8"))
    d["profiles"]["ig_reels_organic"]["encode"] = {
        "codec": ["h264"], "profile": "High", "level_max": 4.2, "gop_s": 3, "closed_gop": True, "pix_fmt": "yuv420p",
        "audio": "aac", "loudness_lufs": -14, "true_peak_dbtp": -1,
        "basis": "official", "source": "https://example.test/fixture", "retrieved": "2026-10-17"}
    p = Path(tempfile.mkdtemp()) / "safe-zones.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return SZ.load("ig_reels_organic", path=p)


class Findings(unittest.TestCase):
    def setUp(self):
        self.p = fixture_profile()
        self.assertFalse(self.p.fallback)

    def test_c50_correct_fixture_passes(self):
        self.assertEqual(SZ.encode_findings(dict(GOOD), self.p), [])

    def test_c50_open_gop(self):
        f = SZ.encode_findings(dict(GOOD, closed_gop=False), self.p)
        self.assertEqual(len(f), 1)
        self.assertIn("GOP", f[0]["text"])
        self.assertEqual(f[0]["check"], "closed_gop")

    def test_c50_gop_too_long(self):
        f = SZ.encode_findings(dict(GOOD, gop_s=5.0), self.p)
        self.assertEqual([x["check"] for x in f], ["gop_s"])

    def test_c50_wrong_level_codec_pixfmt_profile(self):
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, level=5.1), self.p)], ["level_max"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, level="5.1"), self.p)], ["level_max"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, level=41), self.p)], [])   # ffprobe: 41 = 4.1
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, level=51), self.p)], ["level_max"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, codec="prores"), self.p)], ["codec"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, pix_fmt="yuv444p"), self.p)], ["pix_fmt"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, profile="Main"), self.p)], [])   # lower is fine
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, profile="High 4:4:4 Predictive"), self.p)], ["profile"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(dict(GOOD, audio_codec="mp3"), self.p)], ["audio"])

    def test_c50_too_loud_in_arabic(self):
        f = SZ.encode_findings(dict(GOOD, loudness_lufs=-12.0), self.p)
        self.assertEqual([x["check"] for x in f], ["loudness_lufs"])
        self.assertIn("أعلى من المطلوب", f[0]["text"])
        self.assertIn("إنستجرام", f[0]["text"])
        self.assertIn("٢ ديسيبل", f[0]["text"])
        self.assertEqual(f[0]["delta_db"], 2.0)

    def test_c50_loudness_tolerance_and_quiet(self):
        self.assertEqual(SZ.encode_findings(dict(GOOD, loudness_lufs=-13.2), self.p), [])      # within 1 LU
        self.assertEqual(SZ.encode_findings(dict(GOOD, loudness_lufs=-20.0), self.p), [])      # quieter is never a finding

    def test_c50_true_peak(self):
        f = SZ.encode_findings(dict(GOOD, true_peak_dbtp=0.5), self.p)
        self.assertEqual([x["check"] for x in f], ["true_peak_dbtp"])
        self.assertIn("ذروة", f[0]["text"])

    def test_c51_unmeasured_values_are_not_findings(self):
        # an unmeasured value is never a mismatch; it is one "not measured" line instead (never a silent pass)
        for m in ({}, {"codec": None, "loudness_lufs": None, "closed_gop": None},
                  {"loudness_lufs": "loud", "level": "x", "gop_s": float("nan")}, None):
            self.assertEqual([x["severity"] for x in SZ.encode_findings(m, self.p)], ["not_measured"], m)

    def test_c51_unpublished_values_never_checked(self):
        shipped = SZ.load("ig_reels_organic")       # no loudness / GOP length / level in the shipped file
        bad = dict(GOOD, loudness_lufs=-3.0, true_peak_dbtp=3.0, gop_s=30.0, level=6.2)
        adv = lambda f: [x["check"] for x in f if x["severity"] == "advisory"]   # noqa: E731
        self.assertEqual(adv(SZ.encode_findings(bad, shipped)), [])
        self.assertEqual(adv(SZ.encode_findings(dict(GOOD, closed_gop=False), shipped)), ["closed_gop"])

    def test_c54_no_encode_block(self):
        self.assertEqual(SZ.encode_findings(dict(GOOD, closed_gop=False), SZ.load("yt_shorts")), [])
        self.assertEqual(SZ.encode_findings(dict(GOOD), None), [])

    def test_findings_are_plain_words(self):
        for f in SZ.encode_findings(dict(GOOD, closed_gop=False, level=5.1, loudness_lufs=-10.0), self.p):
            self.assertRegex(f["text"], r"[؀-ۿ]")
            for bad in ("None", "{", "level_max", "closed_gop"):
                self.assertNotIn(bad, f["text"])


class Parsers(unittest.TestCase):
    def read(self, name):
        return (FIX / name).read_text(encoding="utf-8")

    def test_c52_ffprobe_streams(self):
        info = SZ.parse_ffprobe_streams(json.loads(self.read("ffprobe_streams.json")))
        self.assertEqual((info["codec"], info["profile"], info["level"], info["pix_fmt"]), ("h264", "High", 41, "yuv420p"))
        self.assertEqual((info["audio_codec"], info["sample_rate"]), ("aac", 48000))
        self.assertEqual(SZ.parse_ffprobe_streams({}), {})
        self.assertEqual(SZ.parse_ffprobe_streams({"streams": "x"}), {})
        self.assertEqual(SZ.parse_ffprobe_streams(None), {})

    def test_c52_keyframe_gap_from_packets(self):
        pk = [{"pts_time": "0.000000", "flags": "K_"}, {"pts_time": "0.033000", "flags": "__"},
              {"pts_time": "2.000000", "flags": "K_"}, {"pts_time": "5.000000", "flags": "K_"}, {"pts_time": "5.5", "flags": "__"}]
        self.assertEqual(SZ.gop_seconds_from_packets(pk), 3.0)
        self.assertIsNone(SZ.gop_seconds_from_packets([{"pts_time": "0", "flags": "K_"}]))
        self.assertIsNone(SZ.gop_seconds_from_packets([]))
        self.assertIsNone(SZ.gop_seconds_from_packets([{"flags": "K_"}, {"pts_time": "junk", "flags": "K_"}]))

    def test_c52_closed_gop_from_trace_headers(self):
        self.assertIs(SZ.closed_gop_from_trace(self.read("trace_closed.txt")), True)
        self.assertIs(SZ.closed_gop_from_trace(self.read("trace_open.txt")), False)
        self.assertIsNone(SZ.closed_gop_from_trace(""))
        self.assertIsNone(SZ.closed_gop_from_trace("garbage"))

    def test_c52_ebur128_summary(self):
        r = SZ.parse_ebur128(self.read("ebur128_summary.txt"))
        self.assertEqual((r["loudness_lufs"], r["true_peak_dbtp"]), (-12.1, -0.4))
        self.assertEqual(SZ.parse_ebur128(""), {})
        self.assertEqual(SZ.parse_ebur128("I: -inf LUFS"), {})

    def test_seeded_fixtures_end_to_end(self):
        """The three seeded bad files and one correct file, through the parsers and the fixture profile."""
        p = fixture_profile()
        base = SZ.parse_ffprobe_streams(json.loads(self.read("ffprobe_streams.json")))
        base.update(SZ.parse_ebur128(self.read("ebur128_summary.txt")))
        base["gop_s"] = 2.0
        base["closed_gop"] = SZ.closed_gop_from_trace(self.read("trace_open.txt"))
        checks = {f["check"] for f in SZ.encode_findings(base, p)}
        self.assertEqual(checks, {"closed_gop", "loudness_lufs", "true_peak_dbtp"})   # open GOP, too loud, true peak
        base["closed_gop"] = SZ.closed_gop_from_trace(self.read("trace_closed.txt"))
        base.update(loudness_lufs=-14.2, true_peak_dbtp=-1.6)
        self.assertEqual(SZ.encode_findings(base, p), [])
        base["level"] = 51
        self.assertEqual([f["check"] for f in SZ.encode_findings(base, p)], ["level_max"])


class Probe(unittest.TestCase):
    def test_c53_probe_fails_open(self):
        def boom(*a, **k):
            raise FileNotFoundError("ffprobe")

        def timeout(*a, **k):
            raise subprocess.TimeoutExpired("x", 1)

        def garbage(argv, **k):
            return subprocess.CompletedProcess(argv, 0, stdout="not json", stderr="")

        def fail(argv, **k):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="bad")

        for runner in (boom, timeout, garbage, fail):
            info = SZ.probe_media("whatever.mp4", runner=runner)
            self.assertIsInstance(info, dict)
            self.assertTrue(info.get("notes"))

    def test_c53_probe_assembles_all_four_probes(self):
        calls = []

        def runner(argv, **k):
            calls.append(argv)
            joined = " ".join(map(str, argv))
            if "-show_streams" in joined:
                out = (FIX / "ffprobe_streams.json").read_text(encoding="utf-8")
            elif "-show_packets" in joined:
                out = json.dumps({"packets": [{"pts_time": "0", "flags": "K_"}, {"pts_time": "2", "flags": "K_"}]})
            elif "trace_headers" in joined:
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr=(FIX / "trace_closed.txt").read_text(encoding="utf-8"))
            else:
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr=(FIX / "ebur128_summary.txt").read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

        tools = Path(tempfile.mkdtemp())
        info = SZ.probe_media("x.mp4", runner=runner, ffmpeg=str(tools / "ffmpeg.exe"), ffprobe=str(tools / "ffprobe.exe"))
        self.assertEqual((info["codec"], info["gop_s"], info["closed_gop"], info["loudness_lufs"]), ("h264", 2.0, True, -12.1))
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(a[0] for a in calls))


def fixture_profile_with(**enc):
    d = json.loads((SK / "config" / "defaults" / "safe-zones.json").read_text(encoding="utf-8"))
    d["profiles"]["ig_reels_organic"]["encode"] = {**enc, "basis": "official", "source": "https://example.test/fixture", "retrieved": "2026-10-17"}
    p = Path(tempfile.mkdtemp()) / "safe-zones.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return SZ.load("ig_reels_organic", path=p)


class Review1(unittest.TestCase):
    """Independent review round 1."""

    def checks(self, info, **enc):
        return [f["check"] for f in SZ.encode_findings(info, fixture_profile_with(**enc))]

    def test_the_numeric_and_container_checks_all_fire(self):
        self.assertEqual(self.checks({"container": "matroska,webm"}, container=["mp4", "mov"]), ["container"])
        self.assertEqual(self.checks({"container": "mov,mp4,m4a,3gp,3g2,mj2"}, container=["mp4", "mov"]), [])
        self.assertEqual(self.checks({"fps": 24.0}, fps_min=30), ["fps_min"])
        self.assertEqual(self.checks({"fps": 29.97}, fps_min=30), [])          # NTSC 29.97 vs 30: 0.1 fps tolerance
        self.assertEqual(self.checks({"fps": 59.94}, fps_max=60, fps_min=60), [])
        self.assertEqual(self.checks({"fps": 120.0}, fps_max=60), ["fps_max"])
        self.assertEqual(self.checks({"sample_rate": 96000}, audio_sample_rate_max=48000), ["audio_sample_rate_max"])
        self.assertEqual(self.checks({"sample_rate": 48000}, audio_sample_rate_max=48000), [])
        self.assertEqual(self.checks({"channels": 6}, audio_channels_max=2), ["audio_channels_max"])
        self.assertEqual(self.checks({"audio_bitrate_kbps": 64.0}, audio_bitrate_kbps_min=128), ["audio_bitrate_kbps_min"])
        self.assertEqual(self.checks({"bitrate_kbps": 1500.0}, bitrate_kbps_min=2500), ["bitrate_kbps_min"])
        self.assertEqual(self.checks({"bitrate_kbps": 9000.0}, bitrate_kbps_min=2500), [])

    def test_hevc_levels_are_not_read_as_h264(self):
        self.assertEqual(self.checks({"codec": "hevc", "level": 123}, codec=["h264", "hevc"], level_max=4.2), [])
        self.assertEqual(self.checks({"codec": "h264", "level": 52}, codec=["h264", "hevc"], level_max=4.2), ["level_max"])

    def test_ffprobe_format_bitrates_and_vfr(self):
        info = SZ.parse_ffprobe_streams(json.loads((FIX / "ffprobe_streams.json").read_text(encoding="utf-8")))
        self.assertEqual((info["container"], info["bitrate_kbps"], info["audio_bitrate_kbps"], info["fps"]),
                         ("mov,mp4,m4a,3gp,3g2,mj2", 9000.0, 128.0, 30.0))
        vfr = {"streams": [{"codec_type": "video", "codec_name": "h264", "r_frame_rate": "90000/1", "avg_frame_rate": "2997/100"}]}
        self.assertAlmostEqual(SZ.parse_ffprobe_streams(vfr)["fps"], 29.97)
        zero = {"streams": [{"codec_type": "video", "r_frame_rate": "0/0", "avg_frame_rate": "0/0"}]}
        self.assertNotIn("fps", SZ.parse_ffprobe_streams(zero))
        nofmt = {"streams": [{"codec_type": "video"}], "format": {"bit_rate": "4000000"}}
        self.assertEqual(SZ.parse_ffprobe_streams(nofmt)["bitrate_kbps"], 4000.0)

    def test_ebur128_without_a_summary_is_not_a_measurement(self):
        running = "[Parsed_ebur128_0 @ 0x1] t: 3.1  TARGET:-23 LUFS    M: -9.0 S: -9.5     I:  -9.7 LUFS     LRA:   0.0 LU\n"
        self.assertEqual(SZ.parse_ebur128(running), {})

    def test_probe_never_runs_a_planted_ffprobe_from_the_current_folder(self):
        import os
        calls = []

        def runner(argv, **k):
            calls.append(argv[0])
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

        d = Path(tempfile.mkdtemp())
        (d / "ffprobe").write_text("x")
        (d / "ffprobe.exe").write_text("x")
        old = os.getcwd()
        os.chdir(d)
        try:
            SZ.probe_media("x.mp4", runner=runner)
        finally:
            os.chdir(old)
        self.assertTrue(calls)
        self.assertNotIn(str(d / "ffprobe"), calls)
        self.assertFalse(any(Path(c).parent == d for c in calls if Path(c).parent != Path(".")))
        self.assertNotIn("ffprobe.exe", [Path(c).name for c in calls if Path(c).parent == Path(".") and Path(c).is_file()])


class RealFfmpeg(unittest.TestCase):
    """The parsers against FFmpeg's real output (the engine's pinned ffmpeg; ffprobe is not shipped, so the stream and
    keyframe-time probes are not run here and probe_media notes them)."""

    @classmethod
    def setUpClass(cls):
        from lib.common import ffmpeg_exe
        cls.ff = ffmpeg_exe()
        if not cls.ff or not Path(cls.ff).is_file():
            raise unittest.SkipTest("no ffmpeg in the engine home")
        cls.tmp = Path(tempfile.mkdtemp())
        for name, og in (("open", 1), ("closed", 0)):
            r = subprocess.run([cls.ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x568:rate=30", "-f", "lavfi", "-i",
                                "sine=frequency=440:sample_rate=48000", "-t", "4", "-c:v", "libx264", "-g", "30", "-bf", "3",
                                "-x264-params", f"open-gop={og}:scenecut=0:keyint=30:min-keyint=30", "-pix_fmt", "yuv420p",
                                "-c:a", "aac", "-b:a", "128k", str(cls.tmp / f"{name}.mp4")], capture_output=True, text=True, timeout=120)
            if r.returncode:
                raise unittest.SkipTest("this ffmpeg has no libx264: " + r.stderr[-200:])

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_open_and_closed_gop_and_loudness(self):
        o = SZ.probe_media(self.tmp / "open.mp4", ffmpeg=self.ff)
        c = SZ.probe_media(self.tmp / "closed.mp4", ffmpeg=self.ff)
        self.assertIs(o["closed_gop"], False)
        self.assertIs(c["closed_gop"], True)
        for i in (o, c):
            self.assertTrue(-30 < i["loudness_lufs"] < -15, i)
            self.assertLess(i["true_peak_dbtp"], 0)
        f = SZ.encode_findings(o, fixture_profile())
        self.assertEqual([x["check"] for x in f if x["severity"] == "advisory"], ["closed_gop"])
        self.assertEqual([x["check"] for x in SZ.encode_findings(c, fixture_profile()) if x["severity"] == "advisory"], [])


class AcceptanceEncode(unittest.TestCase):
    """The executor's acceptance review of 4451e94: ffprobe/ffmpeg never from the current folder (SEC-1 class), an
    unmeasured value is shown as "not measured" (never a silent pass), -v info for the trace."""

    def planted_cwd(self):
        import os
        d = Path(tempfile.mkdtemp())
        for n in ("ffprobe", "ffprobe.exe", "ffmpeg", "ffmpeg.exe"):
            (d / n).write_text("x")
        return d, os.getcwd()

    def test_planted_tools_in_the_current_folder_are_never_run(self):
        import os
        calls = []

        def runner(argv, **k):
            calls.append(str(argv[0]))
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

        d, old = self.planted_cwd()
        path0 = os.environ.get("PATH", "")
        os.chdir(d)
        os.environ["PATH"] = os.pathsep.join([".", "", "relative" + os.sep + "bin", path0])   # relative PATH entries too
        try:
            info = SZ.probe_media("x.mp4", runner=runner)
        finally:
            os.chdir(old)
            os.environ["PATH"] = path0
        for c in calls:
            self.assertTrue(Path(c).is_absolute(), c)                  # never a bare name the OS resolves from the cwd
            self.assertNotEqual(Path(c).resolve().parent, d.resolve(), c)
        self.assertIsInstance(info, dict)

    def test_resolver_order_and_refusals(self):
        import os
        fake = Path(tempfile.mkdtemp())
        (fake / ("ffprobe.exe" if os.name == "nt" else "ffprobe")).write_text("x")
        ff = fake / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ff.write_text("x")
        self.assertEqual(Path(SZ._probe_tool("ffprobe", str(ff))).parent, fake)        # beside the engine's ffmpeg
        self.assertIsNone(SZ._probe_tool("ffprobe", "ffmpeg", path_env=""))              # a bare ffmpeg is no anchor
        self.assertIsNone(SZ._probe_tool("ffprobe", None, path_env="." + os.pathsep + "rel"))   # relative PATH entries skipped
        self.assertEqual(Path(SZ._probe_tool("ffprobe", None, path_env=str(fake))).parent, fake)  # absolute PATH entry ok

    def test_unavailable_probe_is_not_measured_never_a_silent_pass(self):
        def runner(argv, **k):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        info = SZ.probe_media("x.mp4", runner=runner, ffmpeg=None, ffprobe=None, path_env="")
        self.assertTrue(info.get("notes"))
        f = SZ.encode_findings(info, fixture_profile())
        nm = [x for x in f if x["severity"] == "not_measured"]
        self.assertEqual(len(nm), 1)
        self.assertIn("لم", nm[0]["text"])
        self.assertIn("codec", nm[0]["keys"])
        self.assertIn("closed_gop", nm[0]["keys"])
        for bad in ("None", "{", "closed_gop", "_"):
            self.assertNotIn(bad, nm[0]["text"])
        self.assertEqual(SZ.encode_findings(dict(GOOD), fixture_profile()), [])        # everything measured: no such line

    def test_relative_explicit_tools_are_refused(self):
        calls = []

        def runner(argv, **k):
            calls.append(str(argv[0]))
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        SZ.probe_media("x.mp4", runner=runner, ffmpeg="ffmpeg", ffprobe="ffprobe", path_env="")
        self.assertEqual(calls, [])

    def test_trace_runs_at_info_level(self):
        calls = []

        def runner(argv, **k):
            calls.append([str(a) for a in argv])
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        fake = Path(tempfile.mkdtemp())
        SZ.probe_media("x.mp4", runner=runner, ffmpeg=str(fake / "ffmpeg.exe"), ffprobe=str(fake / "ffprobe.exe"))
        tr = next(c for c in calls if "trace_headers" in c)
        self.assertEqual(tr[tr.index("-v") + 1], "info")
        self.assertNotIn("trace", [tr[tr.index("-v") + 1]])


if __name__ == "__main__":
    unittest.main()
