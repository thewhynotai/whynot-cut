# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 26, R-4.4: intake media normalisation (lib/media_normalise.py): the real motion rate, VFR -> CFR,
HDR -> SDR tone-mapped intermediates, even cadence, finals untouched.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.4-intake-normalisation.md. Case list: the lane's
work/t26/cases.md. Fixtures: tests/fixtures/media_normalise/ (FFmpeg test sources, made by make_fixtures.py). The
suite runs with WHYNOT_ACCEL=off: conforms here use the CPU lane; the GPU lane is checked by its argv and live.
Run:  bash tools/test.sh -p test_media_normalise.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import media_normalise as MN  # noqa: E402

FX = SK / "tests" / "fixtures" / "media_normalise"


def fx(name):
    return next(FX.glob(f"{name}.*"))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


# --------------------------------------------------------------------------- A. measure
class TestMeasure(unittest.TestCase):
    def test_a01_cfr30(self):
        m = MN.measure(fx("cfr30"))
        self.assertEqual((m["container_fps"], m["real_fps"], m["vfr"], m["transfer"]), (30.0, 30.0, False, "sdr"))
        self.assertFalse(m["rate_mismatch"])
        self.assertEqual(m["audio_rate"], 48000)

    def test_a02_tagged_60_really_30(self):
        m = MN.measure(fx("tag60_real30"))
        self.assertEqual((m["container_fps"], m["real_fps"]), (60.0, 30.0))
        self.assertTrue(m["rate_mismatch"])
        self.assertAlmostEqual(m["duplicate_ratio"], 0.5, delta=0.05)

    def test_a03_a04_ntsc_and_film_rates_are_kept_exact(self):
        self.assertAlmostEqual(MN.measure(fx("ntsc2997"))["real_fps"], 29.97, places=2)
        self.assertAlmostEqual(MN.measure(fx("film23976"))["real_fps"], 23.976, places=3)
        self.assertEqual(MN.measure(fx("film24"))["real_fps"], 24.0)
        self.assertEqual(MN.snap(30.0 * 1000 / 1001), 29.97)
        self.assertEqual(MN.snap(29.8), 29.97)                                  # within 1 %: the standard rate
        self.assertEqual(MN.snap(29.6), 29.6)                                   # 1.2 % off: as measured
        self.assertEqual(MN.snap(27.0), 27.0)                                   # nothing near: kept as measured

    def test_a05_vfr(self):
        m = MN.measure(fx("vfr"))
        self.assertTrue(m["vfr"])
        self.assertIn(m["cfr_fps"], MN.STANDARD_FPS)

    def test_a06_a07_high_rates(self):
        self.assertEqual(MN.measure(fx("phone120"))["real_fps"], 120.0)
        self.assertEqual(MN.measure(fx("pal50"))["real_fps"], 50.0)

    def test_a08_still_has_no_measurable_rate(self):
        m = MN.measure(fx("still"))
        self.assertIsNone(m["real_fps"])
        self.assertFalse(m["rate_mismatch"])
        self.assertIn("still", m["notes"][0])

    def test_a09_a12_transfer(self):
        self.assertEqual(MN.measure(fx("hdr_pq"))["transfer"], "pq")
        self.assertEqual(MN.measure(fx("hdr_hlg"))["transfer"], "hlg")
        self.assertEqual(MN.measure(fx("cfr30"))["transfer"], "sdr")
        self.assertEqual(MN.measure(fx("hdr_pq"))["bit_depth"], 10)

    def test_a10_tagged_hdr_but_8bit_is_sdr_with_a_warning(self):
        m = MN.measure(fx("pq_tag_8bit"))
        self.assertEqual(m["transfer"], "sdr")
        self.assertIn("tagged_hdr_8bit", m["flags"])

    def test_a11_untagged_10bit_bt2020_is_possibly_hdr(self):
        m = MN.measure(fx("untagged_10bit_bt2020"))
        self.assertEqual(m["transfer"], "sdr")
        self.assertIn("possibly_hdr_untagged", m["flags"])
        self.assertIsNone(MN.decide(m)["tonemap"])

    def test_repeats_split(self):
        self.assertEqual(MN.repeats([0.01, 1.3, 0.02, 1.4, 0.015, 1.5]), 3)             # doubled frames, regular
        self.assertEqual(MN.repeats([0.01, 0.02, 1.3, 0.01, 0.02, 1.4, 0.015, 0.01, 1.5]), 6)   # tripled
        self.assertEqual(MN.repeats([0.1] * 10 + [1.0] * 10), 0)                         # static, then motion: not regular
        self.assertEqual(MN.repeats([0.7, 0.75, 0.76, 0.8, 0.054, 0.9]), 0)              # 120 fps motion: no split
        self.assertEqual(MN.repeats([0.0, 0.01, 0.02]), 3)                               # a still
        self.assertEqual(MN.repeats([]), 0)

    def test_a14_unreadable_never_raises(self):
        d = Path(tempfile.mkdtemp())
        bad = d / "broken.mp4"
        bad.write_bytes(b"\0" * 100)
        m = MN.measure(bad)
        self.assertTrue(m["errors"])
        self.assertEqual(MN.decide(m)["actions"], [])
        self.assertTrue(MN.measure(d / "missing.mp4")["errors"])

    def test_a15_arabic_path_with_spaces(self):
        d = Path(tempfile.mkdtemp()) / "مقابلة العميل ٣"
        d.mkdir()
        shutil.copyfile(fx("tag60_real30"), d / "فيديو ١.mp4")
        self.assertEqual(MN.measure(d / "فيديو ١.mp4")["real_fps"], 30.0)


# --------------------------------------------------------------------------- B. decide
class TestDecide(unittest.TestCase):
    def test_b01_nothing_to_do(self):
        d = MN.decide(MN.measure(fx("cfr30")))
        self.assertEqual((d["actions"], d["lines"]["ar"]), ([], []))

    def test_b02_cfr_and_tonemap(self):
        d = MN.decide(MN.measure(fx("tag60_real30")))
        self.assertEqual((d["actions"], d["cfr_fps"]), (["cfr"], 30.0))
        d = MN.decide(MN.measure(fx("hdr_pq")))
        self.assertEqual((d["actions"], d["tonemap"]), (["tonemap"], "pq"))
        d = MN.decide(MN.measure(fx("vfr")))
        self.assertEqual(d["actions"], ["cfr"])

    def test_b03_even_cadence(self):
        for real, delivery, ok in ((30, 60, True), (60, 30, True), (24, 30, False), (25, 30, False),
                                   (29.97, 30, False), (23.976, 23.976, True), (120, 30, True), (50, 25, True)):
            self.assertEqual(MN.even_cadence(real, delivery)["ok"], ok, (real, delivery))
        r = MN.even_cadence(24, 30)
        self.assertIn(r["nearest"], (24.0, 48.0))
        d = MN.decide(MN.measure(fx("film24")), delivery_fps=30)
        self.assertFalse(d["cadence"]["ok"])
        self.assertTrue(any("24" in line for line in d["lines"]["en"]))

    def test_b04_plain_lines(self):
        for name in ("vfr", "tag60_real30", "hdr_hlg", "pq_tag_8bit", "untagged_10bit_bt2020"):
            d = MN.decide(MN.measure(fx(name)))
            self.assertTrue(d["lines"]["ar"] and d["lines"]["en"], name)
            for line in d["lines"]["ar"] + d["lines"]["en"]:
                self.assertNotIn("\n", line)
                for bad in ("smpte2084", "arib", "_", "None", "{"):
                    self.assertNotIn(bad, line, (name, line))

    def test_b05_build_without_zscale_skips_the_tonemap_with_a_line(self):
        with mock.patch.object(MN, "filters_available", return_value={"zscale": False, "tonemap": True}):
            d = MN.decide(MN.measure(fx("hdr_pq")))
        self.assertIsNone(d["tonemap"])
        self.assertTrue(any("Premiere" in line for line in d["lines"]["en"]))


# --------------------------------------------------------------------------- C. conform
class _Out(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t26-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = self.tmp / "output" / "intermediates"

    def conform(self, name, **kw):
        m = MN.measure(fx(name))
        with quiet():
            return m, MN.conform(fx(name), self.out, MN.decide(m), **kw)


class TestConform(_Out):
    def frames(self, path):
        import av
        with av.open(str(path)) as c:
            s = c.streams.video[0]
            ts = [float(p.pts * s.time_base) for p in c.demux(s) if p.pts is not None]
        return sorted(ts)

    def test_c01_cfr_intermediate(self):
        before = sha(fx("tag60_real30"))
        m, r = self.conform("tag60_real30")
        self.assertTrue(r["ok"], r)
        out = Path(r["path"])
        self.assertTrue(out.is_relative_to(self.out))
        ts = self.frames(out)
        gaps = np.diff(ts)
        self.assertLess(gaps.max() - gaps.min(), 1e-3)                          # constant frame times
        self.assertAlmostEqual(1 / float(np.median(gaps)), 30.0, places=2)
        self.assertLessEqual(abs(len(ts) - 3 * 30), 1)
        side = json.loads(Path(r["sidecar"]).read_text(encoding="utf-8"))
        self.assertEqual(side["source_sha256"], before)
        self.assertIn("fps=30", " ".join(side["filters"]))
        self.assertEqual(sha(fx("tag60_real30")), before)                       # the source is never touched

    def test_c01_av_sync_within_one_frame(self):
        m, r = self.conform("vfr")
        self.assertTrue(r["ok"], r)
        import av
        with av.open(r["path"]) as c:
            v, a = c.streams.video[0], c.streams.audio[0]
            vd = float(v.duration * v.time_base) if v.duration else None
            ad = float(a.duration * a.time_base) if a.duration else None
        self.assertIsNotNone(vd)
        self.assertLessEqual(abs(vd - ad), 1 / r["fps"] + 0.025)

    def test_c02_hdr_tonemapped_to_bt709(self):
        for name in ("hdr_pq", "hdr_hlg"):
            m, r = self.conform(name)
            self.assertTrue(r["ok"], (name, r))
            import av
            with av.open(r["path"]) as c:
                cc = c.streams.video[0].codec_context
                self.assertEqual((cc.color_trc, cc.color_primaries, cc.pix_fmt), (1, 1, "yuv420p"), name)
            q = MN.tonemap_quality(fx(name), r["path"], m["transfer"])
            self.assertLessEqual(q["clipped_white"], 0.005, (name, q))
            self.assertLessEqual(abs(q["mean_luma_delta"]), 0.10, (name, q))

    def test_c03_gpu_lane_argv_and_fallback(self):
        cmds = []

        def runner(cmd):
            cmds.append(cmd)
            if "-hwaccel" in cmd:
                return subprocess.CompletedProcess(cmd, 1, b"", "Cannot load nvcuda.dll")
            return subprocess.run(cmd, capture_output=True)
        m, r = self.conform("tag60_real30", lane="cuda", runner=runner)
        self.assertTrue(r["ok"], r)
        self.assertEqual(cmds[0][cmds[0].index("-hwaccel") + 1], "cuda")
        self.assertNotIn("-hwaccel", cmds[1])                                    # the GPU failed: the CPU once
        self.assertEqual(r["lane"], "cpu")

    def test_c05_disk_check(self):
        Usage = type("U", (), {})
        u = Usage()
        u.free = 1024 ** 3                                                         # 1 GB free
        m, r = self.conform("tag60_real30", disk=lambda p: u)
        self.assertFalse(r["ok"])
        self.assertEqual(r["skipped"], "disk")
        self.assertTrue(r["lines"]["en"])
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_c06_ranges_only_with_handles(self):
        m, r = self.conform("tag60_real30", ranges=[(1.0, 1.5)])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["parts"]), 1)
        p = r["parts"][0]
        self.assertEqual((p["from_s"], p["to_s"]), (0.0, 3.0))                   # 2 s handles, clamped to the file
        self.assertTrue(Path(p["path"]).is_file())

    def test_c07_reuse_and_redo(self):
        m, r1 = self.conform("tag60_real30")
        mtime = Path(r1["path"]).stat().st_mtime_ns
        m, r2 = self.conform("tag60_real30")
        self.assertTrue(r2["reused"])
        self.assertEqual(Path(r2["path"]).stat().st_mtime_ns, mtime)

    def test_c08_failing_ffmpeg_never_raises(self):
        def runner(cmd):
            return subprocess.CompletedProcess(cmd, 1, b"", "Invalid data found when processing input")
        m, r = self.conform("tag60_real30", runner=runner)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"])

    def test_nothing_to_do_writes_nothing(self):
        m, r = self.conform("cfr30")
        self.assertEqual((r["ok"], r.get("path")), (True, None))
        self.assertFalse(self.out.exists())


class TestTools(_Out):
    def test_a16_ffmpeg_only_by_absolute_path(self):
        d = Path(tempfile.mkdtemp())
        (d / "ffmpeg.exe").write_text("x")
        (d / "ffmpeg").write_text("x")
        old = os.getcwd()
        os.chdir(d)
        try:
            self.assertIsNone(MN._abs_ffmpeg("ffmpeg"))
            self.assertIsNone(MN._abs_ffmpeg("ffmpeg.exe"))
            self.assertIsNone(MN._abs_ffmpeg(None))
            m = MN.measure(fx("tag60_real30"))
            with mock.patch("lib.common.ffmpeg_exe", return_value="ffmpeg.exe"):
                r = MN.conform(fx("tag60_real30"), self.out, MN.decide(m))
        finally:
            os.chdir(old)
        self.assertFalse(r["ok"])
        self.assertEqual(r["skipped"], "no ffmpeg")

    def test_filters_probe_is_cached_per_build(self):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, " .SC zscale  V->V  x\n .S. tonemap  V->V  y\n", "")
        MN._FILTER_CACHE.clear()
        ff = str(Path(_sys.executable))
        self.assertEqual(MN.filters_available(ff, runner=runner), {"zscale": True, "tonemap": True})
        MN.filters_available(ff, runner=runner)
        self.assertEqual(len(calls), 1)

    def test_intake_lines_producer(self):
        m = MN.measure(fx("vfr"))
        lines = MN.intake_lines(m, MN.decide(m), "ar")
        self.assertTrue(lines and all(isinstance(x, str) for x in lines))
        self.assertEqual(MN.intake_lines(MN.measure(fx("cfr30")), MN.decide(MN.measure(fx("cfr30"))), "en"), [])


# --------------------------------------------------------------------------- independent review round 1
class TestReview1Measure(unittest.TestCase):
    def test_p1_low_motion_never_becomes_a_tiny_rate(self):
        rnd = np.random.default_rng(1)
        low = list(rnd.uniform(0.001, 0.013, 600))
        for k in range(0, 600, 240):
            low[k] = 0.3                                                      # one rare "motion" frame per 240
        self.assertEqual(MN.repeats(low), 0)
        self.assertEqual(MN.repeats(([0.02] * 19 + [0.8]) * 30), 0)          # a slideshow: k = 20, not a frame rate
        self.assertEqual(MN.repeats(([0.02] * 4 + [0.8]) * 30), 0)           # k = 5: outside 2 / 2.5 / 3 / 4
        m = MN.measure(fx("slow60"))
        self.assertTrue(m["real_fps"] is None or m["real_fps"] >= MN.MIN_REAL_FPS, m["real_fps"])
        self.assertFalse(m["rate_mismatch"])

    def test_p1_regular_runs_only(self):
        self.assertEqual(MN.repeats([0.01, 1.3] * 20), 20)                     # k = 2
        uneven = [0.01, 1.3] * 10 + [0.01, 0.01, 0.01, 1.3] * 5               # half the time doubled, half quadrupled
        self.assertEqual(MN.repeats(uneven), 0)

    def test_pulldown_24_in_60(self):
        pattern = ([0.01, 1.2] + [0.01, 0.01, 1.3]) * 24                       # 2:3 pulldown
        self.assertEqual(MN.repeats(pattern), 72)
        m = MN.measure(fx("pulldown24_in60"))
        self.assertEqual((m["container_fps"], m["real_fps"], m["rate_mismatch"]), (60.0, 24.0, True))

    def test_rotation_from_the_display_matrix(self):
        self.assertIn(MN.measure(fx("rot90"))["rotation"], (90, -90, 270))
        self.assertEqual(MN.measure(fx("cfr30"))["rotation"], 0)

    def test_vfr_cfr_rate_is_always_standard(self):
        m = MN.measure(fx("vfr"))
        self.assertIn(m["cfr_fps"], MN.STANDARD_FPS)
        self.assertEqual(m["cfr_fps"], 30.0)                                   # the stream's own base rate

    def test_10bit_bt2020_with_a_named_sdr_curve_is_not_maybe_hdr(self):
        m = {"errors": [], "flags": [], "transfer": "sdr", "duration_s": 2}
        self.assertEqual(MN._curve_flags(trc=1, prim=9, depth=10), (None, []))
        self.assertEqual(MN._curve_flags(trc=2, prim=9, depth=10), (None, ["possibly_hdr_untagged"]))
        self.assertEqual(MN._curve_flags(trc=16, prim=9, depth=8), (None, ["tagged_hdr_8bit"]))
        self.assertEqual(MN._curve_flags(trc=18, prim=9, depth=10), ("hlg", []))
        del m


class TestReview1Conform(_Out):
    def test_tonemap_against_an_independent_reference(self):
        # the PQ / HLG fixtures are the SDR test picture placed on the HDR curve: tone-mapped back they must look like
        # the SDR picture itself (a reference that does not use the conform's own filter chain)
        for name in ("hdr_pq", "hdr_hlg"):
            m, r = self.conform(name)
            q = MN.tonemap_quality(fx(name), r["path"], m["transfer"], reference=fx("sdr_ref"))
            self.assertLessEqual(q["clipped_white"], 0.005, (name, q))
            self.assertLessEqual(abs(q["mean_luma_delta"]), 0.10, (name, q))

    def test_highlights_are_not_clipped(self):
        m, r = self.conform("hdr_pq1000")
        self.assertTrue(r["ok"], r)
        q = MN.tonemap_quality(fx("hdr_pq1000"), r["path"], "pq")
        self.assertLessEqual(q["clipped_white"], 0.005, q)

    def test_hdr_needing_cfr_without_a_tonemap_makes_no_mislabelled_copy(self):
        m = dict(MN.measure(fx("hdr_pq")), rate_mismatch=True, real_fps=15.0, cfr_fps=15.0)
        with mock.patch.object(MN, "filters_available", return_value={"zscale": False, "tonemap": False}):
            d = MN.decide(m)
        self.assertEqual(d["actions"], [])
        self.assertTrue(any("HDR" in x for x in d["lines"]["en"]))

    def test_av_sync_over_two_minutes(self):
        long = self.tmp / "long_vfr.mp4"
        from lib.common import ffmpeg_exe
        subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30:duration=120",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=120",
                        "-vf", r"select='not(mod(n\,3))+between(mod(n\,300)\,100\,180)'", "-fps_mode", "vfr",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", "-c:a", "aac", "-shortest", str(long)],
                       check=True, capture_output=True)
        m = MN.measure(long)
        self.assertTrue(m["vfr"])
        with quiet():
            r = MN.conform(long, self.out, MN.decide(m))
        self.assertTrue(r["ok"], r)
        import av
        with av.open(r["path"]) as c:
            v, a = c.streams.video[0], c.streams.audio[0]
            vd, ad = float(v.duration * v.time_base), float(a.duration * a.time_base)
        self.assertLessEqual(abs(vd - ad), 1 / r["fps"], (vd, ad))

    def test_partial_output_is_never_reused_and_a_changed_source_is_redone(self):
        src = self.tmp / "clip.mp4"
        shutil.copyfile(fx("tag60_real30"), src)
        m = MN.measure(src)
        d = MN.decide(m)

        def dies(cmd):                       # writes half a file, then fails (a killed encode)
            Path(cmd[-1]).write_bytes(b"partial")
            return subprocess.CompletedProcess(cmd, 1, b"", "killed")
        with quiet():
            r = MN.conform(src, self.out, d, runner=dies)
        self.assertFalse(r["ok"])
        self.assertEqual([p.name for p in self.out.glob("*.mp4")], [])          # nothing under the final name
        self.assertEqual(list(self.out.glob("*.json")), [])
        with quiet():
            r1 = MN.conform(src, self.out, d)
        self.assertTrue(r1["ok"] and not r1["reused"])
        with open(src, "ab") as f:
            f.write(b"\0")                                                     # the footage changed
        with quiet():
            r2 = MN.conform(src, self.out, d)
        self.assertFalse(r2["reused"])

    def test_overlapping_windows_are_merged(self):
        m, r = self.conform("tag60_real30", ranges=[(0.5, 0.8), (0.9, 1.2)])
        self.assertEqual(len(r["parts"]), 1)

    def test_skips_and_failures_have_plain_lines(self):
        def fails(cmd):
            return subprocess.CompletedProcess(cmd, 1, b"", "boom")
        m, r = self.conform("tag60_real30", runner=fails)
        self.assertTrue(r["lines"]["en"] and r["lines"]["ar"])
        m = MN.measure(fx("tag60_real30"))
        with mock.patch.object(MN, "_engine_ffmpeg", return_value=None):
            r = MN.conform(fx("tag60_real30"), self.out, MN.decide(m))
        self.assertEqual(r["skipped"], "no ffmpeg")
        self.assertTrue(r["lines"]["en"] and r["lines"]["ar"])

    def test_range_part_duration(self):
        m, r = self.conform("tag60_real30", ranges=[(1.0, 1.5)])
        import av
        with av.open(r["parts"][0]["path"]) as c:
            self.assertAlmostEqual(c.duration / 1e6, 3.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()
