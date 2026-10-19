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
import time
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
        (self.tmp / "assets").mkdir()                   # a client folder: output/ sits next to assets/ and data/
        (self.tmp / "data").mkdir()
        self.out = self.tmp / "output" / "intermediates"

    def cf(self, src, out, d, **kw):
        kw.setdefault("client_root", self.tmp)        # conform writes only into <client_root>/output
        return MN.conform(src, out, d, **kw)

    def conform(self, name, **kw):
        m = MN.measure(fx(name))
        with quiet():
            return m, self.cf(fx(name), self.out, MN.decide(m), **kw)

    def ls(self, folder=None, settle_s: float = 5.0):
        """The folder's entries once no scanner copy is in it. On this PC a file filter (the antivirus) briefly renames
        a just-deleted file to `<NAME IN UPPER CASE>.tmp`, holds it and deletes it within ~50 ms (reproduced with plain
        Python rename + delete, no engine code: CLOSEOUT T26-wire, section B). Only that transient form is waited
        out (up to settle_s); anything of ours that stays is still listed, so a real leftover fails the test."""
        folder = self.out if folder is None else folder
        t0 = time.monotonic()
        while True:
            items = list(folder.iterdir())
            if not any(_scanner_copy(p.name) for p in items) or time.monotonic() - t0 > settle_s:
                return items
            time.sleep(0.05)


def _scanner_copy(name: str) -> bool:
    """`TAG60_REAL30.FC772D56FE.CONFORM.HELD.JSON.tmp`: an upper-cased name of ours + `.tmp`, made by a file filter
    outside the engine (the engine's own temp files are `.<name>.<12 hex>.tmp`, lower case, with a leading dot)."""
    stem = name[:-4] if name.endswith(".tmp") else None
    return bool(stem) and stem == stem.upper() and ".CONFORM" in stem and not stem.startswith(".")


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
        self.assertFalse(self.out.exists() and any(self.ls()))

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
                r = self.cf(fx("tag60_real30"), self.out, MN.decide(m))
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
            r = self.cf(long, self.out, MN.decide(m))
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
            r = self.cf(src, self.out, d, runner=dies)
        self.assertFalse(r["ok"])
        self.assertEqual([p.name for p in self.out.glob("*.mp4")], [])          # nothing under the final name
        self.assertEqual(list(self.out.glob("*.json")), [])
        with quiet():
            r1 = self.cf(src, self.out, d)
        self.assertTrue(r1["ok"] and not r1["reused"])
        with open(src, "ab") as f:
            f.write(b"\0")                                                     # the footage changed
        with quiet():
            r2 = self.cf(src, self.out, d)
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
            r = self.cf(fx("tag60_real30"), self.out, MN.decide(m))
        self.assertEqual(r["skipped"], "no ffmpeg")
        self.assertTrue(r["lines"]["en"] and r["lines"]["ar"])

    def test_range_part_duration(self):
        m, r = self.conform("tag60_real30", ranges=[(1.0, 1.5)])
        import av
        with av.open(r["parts"][0]["path"]) as c:
            self.assertAlmostEqual(c.duration / 1e6, 3.0, delta=0.15)



# --------------------------------------------------------------------------- batch B (executor acceptance of 8bd6b60)
def _junction(link: Path, target: Path):
    """A folder link: a junction on Windows (no privilege needed), a symlink on macOS / Linux."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _unlink_dir(link: Path):
    """Remove a folder link as a name, never its target."""
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


def _can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink(os.path.join(d, "t"), os.path.join(d, "l"))
            return True
        except (OSError, NotImplementedError):
            return False


class TestBatchBNames(_Out):
    def two_cams(self, root=None):
        root = root or self.tmp
        a, b = root / "data" / "camA" / "C0001.MP4", root / "data" / "camB" / "C0001.MP4"
        for p, name in ((a, "tag60_real30"), (b, "film24")):
            p.parent.mkdir(parents=True)
            shutil.copyfile(fx(name), p)
        return a, b

    def test_p1_same_name_in_two_folders_never_overwrites(self):
        a, b = self.two_cams()
        da = MN.decide(MN.measure(a))
        db = dict(MN.decide(MN.measure(b)), actions=["cfr"], cfr_fps=24.0)
        with quiet():
            ra, rb = self.cf(a, self.out, da), self.cf(b, self.out, db)
        self.assertTrue(ra["ok"] and rb["ok"], (ra, rb))
        self.assertNotEqual(ra["path"], rb["path"])
        self.assertTrue(Path(ra["path"]).is_file() and Path(rb["path"]).is_file())
        for r, src in ((ra, a), (rb, b)):
            side = json.loads(Path(r["sidecar"]).read_text(encoding="utf-8"))
            self.assertEqual(side["source_sha256"], sha(src))
        self.assertTrue(Path(ra["path"]).name.startswith("C0001."))               # the clip name stays readable
        with quiet():
            again = self.cf(a, self.out, da)
        self.assertTrue(again["reused"])
        self.assertEqual(again["path"], ra["path"])

    def test_tag_is_stable_and_never_folds_case(self):
        """Review 19049fe #8: names differing only in case (a case-sensitive folder, WSL, a Linux share) never share
        an intermediate, on any OS; the client folder's own spelling does not matter (the tag is relative to it)."""
        a, b = self.two_cams()
        self.assertEqual(MN._source_tag(a, self.tmp), MN._source_tag(a, self.tmp))
        self.assertNotEqual(MN._source_tag(a, self.tmp), MN._source_tag(b, self.tmp))
        lower = a.with_name("c0001.mp4")
        with mock.patch.object(MN, "_REAL_CASE", False):                        # the macOS rule: the given case
            self.assertNotEqual(MN._source_tag(lower, self.tmp), MN._source_tag(a, self.tmp))
        if os.path.exists(lower):                                               # one file under two spellings
            if os.name == "nt":                                                 # review 2063755 P3-5: the on-disk
                self.assertEqual(MN._source_tag(lower, self.tmp), MN._source_tag(a, self.tmp))   # case, one tag
        else:                                                                   # a case-sensitive folder: two files
            lower.write_bytes(b"another clip")
            with mock.patch.object(MN, "_REAL_CASE", True):                     # the Windows rule keeps them apart
                self.assertNotEqual(MN._source_tag(lower, self.tmp), MN._source_tag(a, self.tmp))
        self.assertEqual(MN._source_tag(Path(str(a).replace("\\", "/")), self.tmp), MN._source_tag(a, self.tmp))
        if os.name == "nt":                                                     # the client folder spelled in upper case
            self.assertEqual(MN._source_tag(a, Path(str(self.tmp).upper())), MN._source_tag(a, self.tmp))

    def test_a_moved_client_or_a_touched_file_keeps_its_intermediate(self):
        a, _ = self.two_cams()
        moved = self.tmp / "moved client"
        a2, _ = self.two_cams(moved)
        self.assertEqual(MN._source_tag(a, self.tmp), MN._source_tag(a2, moved))  # relative to the client folder
        d = MN.decide(MN.measure(a))
        with quiet():
            r1 = self.cf(a, self.out, d)
        os.utime(a, (1_000_000_000, 1_000_000_000))                            # a sync tool rewrote the time only
        with quiet():
            r2 = self.cf(a, self.out, d)
        self.assertTrue(r2["reused"])
        self.assertEqual(r1["path"], r2["path"])
        with open(a, "ab") as f:
            f.write(b"\0")                                                     # new content: redone under its name
        with quiet():
            r3 = self.cf(a, self.out, d)
        self.assertTrue(r3["ok"] and not r3["reused"])
        self.assertEqual(r3["path"], r1["path"])
        self.assertEqual(len(list(self.out.glob("*.mp4"))), 1)                  # no orphan copy left behind

    def test_a_long_stem_is_capped(self):
        src = self.tmp / "data" / ("زووم " * 30 + ".mp4")
        shutil.copyfile(fx("tag60_real30"), src)
        with quiet():
            r = self.cf(src, self.out, MN.decide(MN.measure(src)))
        self.assertTrue(r["ok"], r)
        self.assertLessEqual(len(Path(r["path"]).name), 60 + len(".0123456789.conform.mp4"))


class TestBatchBOutputOnly(_Out):
    def refused(self, out_dir, **kw):
        m = MN.measure(fx("tag60_real30"))
        with quiet():
            r = self.cf(fx("tag60_real30"), out_dir, MN.decide(m), **kw)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["skipped"], "not output")
        self.assertTrue(r["lines"]["en"] and r["lines"]["ar"])
        self.assertFalse(Path(out_dir).exists())                                   # refused before anything is made
        return r

    def test_outside_output_is_refused(self):
        self.refused(self.tmp / "elsewhere" / "intermediates")

    def test_a_folder_named_output_that_is_not_the_clients(self):
        self.refused(self.tmp / "data" / "Raw" / "output")
        (self.tmp / "assets" / "site" / "assets").mkdir(parents=True)          # looks like a client folder inside assets/
        self.refused(self.tmp / "assets" / "site" / "output" / "x")

    def test_no_client_folder_given_is_refused(self):
        self.refused(self.out, client_root=None)                               # a folder named output proves nothing

    def test_dot_dot_out_of_output_is_refused(self):
        self.refused(self.tmp / "output" / ".." / "assets" / "conform")

    def test_names_windows_mangles_are_refused(self):
        self.refused(self.tmp / "output" / "con" / "x")
        self.refused(self.tmp / "output" / "a:b")
        self.refused(self.tmp / "output" / "tab\there")                     # control characters (0-31)

    def test_project_folder_is_allowed(self):
        out = self.tmp / "output" / "projects" / "V1" / "00_inputs" / "intermediates"
        m = MN.measure(fx("tag60_real30"))
        with quiet():
            r = self.cf(fx("tag60_real30"), out, MN.decide(m))
        self.assertTrue(r["ok"], r)
        self.assertEqual(Path(r["path"]).parent, Path(os.path.realpath(out)))

    def test_client_root_given_refuses_another_clients_output(self):
        other = self.tmp / "other"
        (other / "assets").mkdir(parents=True)
        self.refused(other / "output" / "intermediates")

    def test_a_link_inside_output_is_never_written_through(self):
        (self.tmp / "output").mkdir()
        _junction(self.tmp / "output" / "lnk", self.tmp / "assets")
        self.addCleanup(_unlink_dir, self.tmp / "output" / "lnk")              # the link only, before the tree goes
        m = MN.measure(fx("tag60_real30"))
        with quiet():
            r = self.cf(fx("tag60_real30"), self.tmp / "output" / "lnk" / "x", MN.decide(m))
        self.assertEqual(r["skipped"], "not output")
        self.assertEqual(list((self.tmp / "assets").iterdir()), [])

    def test_an_output_folder_that_is_itself_a_link_is_allowed(self):
        drive = Path(tempfile.mkdtemp(prefix="whynot-t26-drive-"))             # outside the client folder
        self.addCleanup(shutil.rmtree, drive, True)
        elsewhere = drive / "renders" / "client output"
        elsewhere.mkdir(parents=True)
        _junction(self.tmp / "output", elsewhere)
        self.addCleanup(_unlink_dir, self.tmp / "output")
        m = MN.measure(fx("tag60_real30"))
        with quiet():
            r = self.cf(fx("tag60_real30"), self.out, MN.decide(m))
        self.assertTrue(r["ok"], r)
        self.assertTrue(Path(r["path"]).is_relative_to(Path(os.path.realpath(elsewhere))))

    def test_a_dangling_output_link_never_builds_its_target(self):
        gone = self.tmp / "unplugged drive" / "client output"
        gone.mkdir(parents=True)
        _junction(self.tmp / "output", gone)
        self.addCleanup(_unlink_dir, self.tmp / "output")
        gone.rmdir()                                                               # the drive is gone
        self.refused(self.out)
        self.assertFalse(gone.exists())

    def test_a_dangling_output_link_outside_the_client_is_refused(self):
        """Review 2063755 P3-6: the dangling check itself (a target inside the client is refused by the footage rule
        anyway)."""
        far = Path(tempfile.mkdtemp(prefix="whynot-t26-far-"))
        self.addCleanup(shutil.rmtree, far, True)
        gone = far / "client output"
        gone.mkdir()
        _junction(self.tmp / "output", gone)
        self.addCleanup(_unlink_dir, self.tmp / "output")
        gone.rmdir()
        self.assertIsNone(MN.client_output(self.out, self.tmp))
        self.refused(self.out)
        self.assertFalse(gone.exists())

    def test_footage_linked_into_output_is_never_written_into(self):
        """Review 2063755 P3-1: assets/ (or data/) linked INTO a plain output/: the write folder is the footage."""
        for x in ("assets", "data"):
            with self.subTest(x):
                own, out = self.tmp / x, self.tmp / "output"
                own.rmdir()
                out.mkdir(exist_ok=True)
                _junction(own, out)                                                # x -> output/
                try:
                    self.assertIsNone(MN.client_output(self.out, self.tmp))
                    self.assertIsNone(MN.client_output(out, self.tmp))
                    _unlink_dir(own)
                    (out / "footage").mkdir()
                    _junction(own, out / "footage")                                # x -> output/footage
                    self.assertIsNone(MN.client_output(out / "footage" / "x", self.tmp))
                    self.assertIsNotNone(MN.client_output(self.out, self.tmp))     # its sibling folder is fine
                    _unlink_dir(own)
                    _junction(own, self.tmp.parent)                                # x -> a share that holds the
                    self.assertIsNone(MN.client_output(self.out, self.tmp))        # client: output/ lies in the
                finally:                                                           # footage (client_move_paths)
                    _unlink_dir(own)
                    own.mkdir()
                    shutil.rmtree(out)

    def test_an_output_link_inside_linked_footage_is_refused(self):
        """Review r3b P2: assets/ -> E:/shoot and output/ -> E:/shoot/exports (no client layout there): the copy
        would land in the footage. Refused like every engine write (client_move_paths.protected_refusal)."""
        far = Path(tempfile.mkdtemp(prefix="whynot-t26-shoot-"))
        self.addCleanup(shutil.rmtree, far, True)
        (far / "exports").mkdir()
        (self.tmp / "assets").rmdir()
        _junction(self.tmp / "assets", far)
        self.addCleanup(_unlink_dir, self.tmp / "assets")
        _junction(self.tmp / "output", far / "exports")
        self.addCleanup(_unlink_dir, self.tmp / "output")
        self.assertIsNone(MN.client_output(self.out, self.tmp))
        self.refused(self.out)
        self.assertEqual([p.name for p in far.iterdir()], ["exports"])
        self.assertEqual(list((far / "exports").iterdir()), [])

    def test_an_output_link_into_the_clients_own_footage_is_refused(self):
        for x in ("assets", "data"):
            _junction(self.tmp / "output", self.tmp / x)
            try:
                self.refused(self.out)
            finally:
                _unlink_dir(self.tmp / "output")
            self.assertEqual(list((self.tmp / x).iterdir()), [])
        _junction(self.tmp / "output", self.tmp)                                # output/ -> the client folder itself
        try:
            self.refused(self.tmp / "output" / "assets" / "x")
            self.assertIsNone(MN.client_output(self.tmp / "output" / "x", self.tmp))
        finally:
            _unlink_dir(self.tmp / "output")
        self.assertEqual(list((self.tmp / "assets").iterdir()), [])

    def test_an_output_link_into_any_clients_folder_is_refused(self):
        """Review 19049fe #4: output/ linked to another client's assets/ (marked or not), into this client's own
        footage/, or into the configured clients folder is refused; nothing is written there."""
        other = Path(tempfile.mkdtemp(prefix="whynot-t26-other-"))
        self.addCleanup(shutil.rmtree, other, True)
        for x in ("assets", "data"):
            (other / "client B" / x).mkdir(parents=True)
        (self.tmp / "footage").mkdir()
        clients = other / "clients"
        (clients / "renders").mkdir(parents=True)
        for target in (other / "client B" / "assets", other / "client B" / "data" / "Raw", self.tmp / "footage",
                       clients / "renders"):
            target.mkdir(parents=True, exist_ok=True)
            _junction(self.tmp / "output", target)
            try:
                with mock.patch("lib.common.clients_root", return_value=clients):
                    self.refused(self.out)
            finally:
                _unlink_dir(self.tmp / "output")
            self.assertEqual(list(target.iterdir()), [], target)
        second = other / "second clients"                                      # output/ -> a folder that holds clients
        for x in ("assets", "data"):
            (second / "zeta" / x).mkdir(parents=True)
        _junction(self.tmp / "output", second)
        try:
            self.refused(self.tmp / "output" / "zeta" / "assets" / "x")
            self.refused(self.tmp / "output" / "zeta" / "x")
        finally:
            _unlink_dir(self.tmp / "output")
        self.assertEqual(list((second / "zeta" / "assets").iterdir()), [])

    def test_the_folder_is_checked_again_after_the_source_is_hashed(self):
        """Review 19049fe #3: a link put in place while the source is hashed (minutes on a big file) is never written
        through."""
        real_sha = MN._sha256

        def slow_hash(p):
            (self.tmp / "output").mkdir(exist_ok=True)
            _junction(self.out, self.tmp / "assets")                          # output/intermediates -> assets
            return real_sha(p)
        self.addCleanup(lambda: _unlink_dir(self.out) if os.path.lexists(self.out) else None)
        m = MN.measure(fx("tag60_real30"))
        with mock.patch.object(MN, "_sha256", slow_hash), quiet():
            r = self.cf(fx("tag60_real30"), self.out, MN.decide(m))
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["skipped"], "not output")
        self.assertEqual(list((self.tmp / "assets").iterdir()), [])

    def test_device_names_with_spaces_or_superscripts_are_refused(self):
        """Review 19049fe #5: names Windows 11 treats as devices."""
        for name in ("CON .txt", "nul .x", "CONIN$", "conout$", "COM\u00b9", "LPT\u00b2", "aux.tar.gz", "Com3",
                     " con"):
            self.assertIsNone(MN.client_output(self.tmp / "output" / name / "x", self.tmp), name)
        for name in ("console", "COM10", "lpt", "nullable", "CONTENT .x"):
            self.assertIsNotNone(MN.client_output(self.tmp / "output" / name / "x", self.tmp), name)

    def test_client_output_helper(self):
        self.assertEqual(MN.client_output(self.out, self.tmp),
                         Path(os.path.realpath(self.tmp / "output")) / "intermediates")
        self.assertEqual(MN.client_output(self.tmp / "output", self.tmp), Path(os.path.realpath(self.tmp / "output")))
        self.assertIsNone(MN.client_output(self.tmp / "nope", self.tmp))
        self.assertIsNone(MN.client_output(self.out, None))
        self.assertIsNone(MN.client_output(self.out, self.tmp / "no such client"))


class TestBatchBTimeout(_Out):
    def test_timeout_scales_with_the_duration_and_the_picture(self):
        self.assertEqual(MN.timeout_s(5, False), MN.TIMEOUT_MIN_S)
        self.assertGreaterEqual(MN.timeout_s(7200, True), 7200 * 10)
        self.assertGreater(MN.timeout_s(7200, True), MN.timeout_s(7200, False))
        self.assertEqual(MN.timeout_s(600, True, 3840 * 2160 * 60), 600 * MN.TIMEOUT_X_TONEMAP * 8)   # 4K60 = 8x 1080p30
        self.assertEqual(MN.timeout_s(600, True, 640 * 360 * 30), 600 * MN.TIMEOUT_X_TONEMAP)         # never under 1x
        seen = []
        real = subprocess.run

        def spy(cmd, **kw):
            seen.append(kw.get("timeout"))
            return real(cmd, **kw)
        m = MN.measure(fx("hdr_pq"))
        d = dict(MN.decide(m), duration_s=7200.0)
        self.assertTrue(d.get("tonemap"), d)
        with mock.patch.object(MN.subprocess, "run", side_effect=spy), quiet():
            self.cf(fx("hdr_pq"), self.out, d, ranges=[(0.0, 1000.0)])
        self.assertEqual(seen[-1], 1002.0 * MN.TIMEOUT_X_TONEMAP)                 # the span: 0 .. 1000 s + the 2 s handle
        with mock.patch.object(MN.subprocess, "run", side_effect=spy), quiet():
            self.cf(fx("hdr_pq"), self.out, dict(d, duration_s=None, tonemap=None, actions=["cfr"], cfr_fps=24.0))
        self.assertEqual(seen[-1], MN.TIMEOUT_MIN_S)

    def test_a_timeout_leaves_no_partial_file(self):
        def slow(cmd):
            Path(cmd[-1]).write_bytes(b"half")
            raise subprocess.TimeoutExpired(cmd, 1)
        m, r = self.conform("tag60_real30", runner=slow)
        self.assertFalse(r["ok"])
        self.assertEqual(r["skipped"], "timeout")
        self.assertTrue(r["lines"]["en"] and r["lines"]["ar"])
        self.assertEqual(list(self.ls()), [])                            # no .partial.mp4, no sidecar

    def test_a_locked_partial_is_retried_and_still_reported_as_a_timeout(self):
        def slow(cmd):
            Path(cmd[-1]).write_bytes(b"half")
            raise subprocess.TimeoutExpired(cmd, 1)
        real_remove = MN.linksafe.remove

        def held_for(n):                     # the .partial.mp4 is held for the first n tries (a scanner, a dying child)
            calls = []                       # (removed only through linksafe: review 0cd67d7 P2-1)

            def remove(path, root, within=None):
                if str(path).endswith(".partial.mp4") and os.path.lexists(path):
                    calls.append(path)
                    if len(calls) <= n:
                        raise MN.linksafe.RemoveIncomplete(0, [(str(path), "held by a scanner")])
                return real_remove(path, root, within)
            return remove, calls
        unlink, calls = held_for(2)
        with mock.patch.object(MN.linksafe, "remove", unlink), mock.patch.object(MN.time, "sleep"):
            m, r = self.conform("tag60_real30", runner=slow)
        self.assertEqual(r["skipped"], "timeout")
        self.assertEqual(len(calls), 3)
        self.assertEqual(list(self.ls()), [])
        unlink, calls = held_for(99)
        with mock.patch.object(MN.linksafe, "remove", unlink), mock.patch.object(MN.time, "sleep"):
            m, r = self.conform("tag60_real30", runner=slow)
        self.assertEqual(r["skipped"], "timeout")                                 # still a timeout, never "failed"
        self.assertIn("could not be removed", r["reason"])
        self.assertEqual(len(calls), 5)

    def test_an_open_old_copy_is_reported_and_kept_consistent(self):
        m, r1 = self.conform("tag60_real30")
        self.assertTrue(r1["ok"], r1)
        side_before = Path(r1["sidecar"]).read_text(encoding="utf-8")
        real_replace = Path.replace

        def held(self_, target):
            if str(target) == r1["path"]:
                raise PermissionError("open in Premiere")
            return real_replace(self_, target)
        with mock.patch.object(Path, "replace", held):
            m, r2 = self.conform("tag60_real30", crf=18)                            # a new copy is needed
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["skipped"], "in use")
        self.assertTrue(r2["lines"]["en"] and r2["lines"]["ar"])
        self.assertEqual(sorted(p.name for p in self.ls()),
                         sorted([Path(r1["path"]).name, Path(r1["sidecar"]).name]))  # no partial left
        self.assertEqual(Path(r1["sidecar"]).read_text(encoding="utf-8"), side_before)
        m, r3 = self.conform("tag60_real30")                                       # the old copy is still reused
        self.assertTrue(r3["reused"])

    def test_a_failed_record_write_never_lets_a_wrong_copy_be_reused(self):
        """Review 19049fe #1: the crf18 copy replaced the crf16 one but its sidecar could not be written (read-only):
        the next crf16 run must not reuse the crf18 file."""
        m, r1 = self.conform("tag60_real30")
        self.assertTrue(r1["ok"], r1)
        side, h16 = Path(r1["sidecar"]), sha(r1["path"])
        os.chmod(side, 0o444)
        self.addCleanup(lambda: [os.chmod(x, 0o666) for x in self.out.glob("*.json")])
        m, r2 = self.conform("tag60_real30", crf=18)
        m, r3 = self.conform("tag60_real30")
        self.assertTrue(r3["ok"], r3)
        if r3["reused"]:
            self.assertEqual(sha(r3["path"]), h16, (r2, r3))                     # reused = really the crf16 copy
        else:
            self.assertEqual(json.loads(Path(r3["sidecar"]).read_text(encoding="utf-8"))["crf"], 16)
        self.assertEqual(sorted(p.name for p in self.ls()),
                         sorted([Path(r1["path"]).name, side.name]))              # no partial, no record aside

    def test_a_record_that_cannot_be_set_aside_keeps_the_old_pair(self):
        m, r1 = self.conform("tag60_real30")
        before = (sha(r1["path"]), Path(r1["sidecar"]).read_text(encoding="utf-8"))
        real = os.replace

        def held(a, b):
            if str(a) == r1["sidecar"]:
                raise PermissionError("the record is open")
            return real(a, b)
        with mock.patch.object(MN.os, "replace", held):
            m, r2 = self.conform("tag60_real30", crf=18)
        self.assertEqual(r2["skipped"], "in use")
        self.assertEqual((sha(r1["path"]), Path(r1["sidecar"]).read_text(encoding="utf-8")), before)
        self.assertEqual(len(list(self.ls())), 2)
        m, r3 = self.conform("tag60_real30")
        self.assertTrue(r3["reused"])

    def test_a_source_named_like_a_windows_device_is_conformed(self):
        """Review r2 #1: `Con.Edison promo.mp4` (made freely on a Mac, and on Windows 11) gets a copy that every OS
        can write."""
        self.assertEqual(MN._safe_stem("CON"), "_CON")
        self.assertEqual(MN._safe_stem("aux.final"), "_aux.final")
        self.assertEqual(MN._safe_stem("nul .2024"), "_nul .2024")
        self.assertEqual(MN._safe_stem("a:b\x07c|d"), "a_b_c_d")
        self.assertEqual(MN._safe_stem("a\\b"), "a_b")                            # a Mac / Linux name, read on a PC
        self.assertEqual(MN._safe_stem("console"), "console")
        self.assertEqual(MN._safe_stem("زووم " * 30), ("زووم " * 30)[:60])
        src = self.tmp / "data" / "Con.Edison promo.mp4"
        shutil.copyfile(fx("tag60_real30"), src)
        with quiet():
            r = self.cf(src, self.out, MN.decide(MN.measure(src)))
        self.assertTrue(r["ok"], r)
        self.assertTrue(Path(r["path"]).name.startswith("_Con.Edison promo."))

    def test_a_stuck_held_record_is_found_before_the_encode(self):
        """Review r2 #2: a leftover `.held.json` that can't be removed is reported before hours of encoding."""
        m, r1 = self.conform("tag60_real30")
        real = MN.linksafe.remove
        ran = []

        def stuck(path, root, within=None):
            if str(path).endswith(".held.json"):
                raise MN.Guidance("held by a sync tool", "close it")
            return real(path, root, within)

        def runner(cmd):
            ran.append(cmd)
            raise AssertionError("never encoded")
        with mock.patch.object(MN.linksafe, "remove", stuck):
            m, r2 = self.conform("tag60_real30", crf=18, runner=runner)
        self.assertEqual(ran, [])
        self.assertEqual(r2["skipped"], "in use")
        self.assertIn(".held.json", r2["reason"])
        m, r3 = self.conform("tag60_real30")
        self.assertTrue(r3["reused"])                                              # the old pair is untouched

    def test_a_record_that_is_not_an_object_is_redone(self):
        """Review r2 #3: a sidecar of valid JSON that is not an object never blocks the source."""
        m, r1 = self.conform("tag60_real30")
        for junk in ("[1, 2]", "3", "null", '"x"'):
            Path(r1["sidecar"]).write_text(junk, encoding="utf-8")
            m, r = self.conform("tag60_real30")
            self.assertTrue(r["ok"] and not r["reused"], (junk, r))
            self.assertEqual(json.loads(Path(r["sidecar"]).read_text(encoding="utf-8"))["crf"], 16)

    def no_wrong_reuse(self, r16_sha):
        """The next crf16 run reuses only the crf16 copy (else it re-encodes); nothing is left aside."""
        m, r = self.conform("tag60_real30")
        self.assertTrue(r["ok"], r)
        if r["reused"]:
            self.assertEqual(sha(r["path"]), r16_sha)
        self.assertEqual(json.loads(Path(r["sidecar"]).read_text(encoding="utf-8"))["crf"], 16)
        self.assertEqual(len(list(self.ls())), 2, list(self.ls()))

    def test_the_new_record_cannot_be_written(self):
        """Review r2 #5: the crf18 copy took the name but its record failed: no record is left that describes
        another copy."""
        for err in (MN.Guidance("access denied", "close it"), PermissionError("locked by a virus scan")):
            with self.subTest(type(err).__name__):
                m, r1 = self.conform("tag60_real30")
                h16 = sha(r1["path"])
                with mock.patch.object(MN.linksafe, "replace_atomic", side_effect=err):
                    m, r2 = self.conform("tag60_real30", crf=18)
                # Review 2063755 P2-1 / owner pre-mortem (a): a line of its own, never a stopped run; the copy is
                # right and used now, it only has no record (made again next time). Not a skip: skipped means unused.
                self.assertTrue(r2["ok"], r2)
                self.assertIsNone(r2["skipped"])
                self.assertIsNone(r2["sidecar"])
                self.assertIsNone(r2["parts"][0]["sidecar"])
                self.assertIn("could not be saved", r2["reason"])
                self.assertIn(str(err), r2["reason"])
                self.assertEqual(r2["lines"], {"en": [MN.LINES["no_record"][0]], "ar": [MN.LINES["no_record"][1]]})
                self.assertTrue(MN._plain_file(Path(r2["path"])))
                self.assertFalse(Path(r1["sidecar"]).exists())                    # the crf16 record went aside
                self.assertFalse([p for p in self.ls() if p.name.endswith(".held.json")])
                self.no_wrong_reuse(h16)

    def test_the_old_record_cannot_be_put_back(self):
        """Review r2 #5: the old copy is open AND its record can't return: it is redone next time, never misread."""
        m, r1 = self.conform("tag60_real30")
        h16 = sha(r1["path"])
        real_path_replace, real_replace = Path.replace, os.replace

        def open_copy(self_, target):
            if str(target) == r1["path"]:
                raise PermissionError("open in Premiere")
            return real_path_replace(self_, target)

        def no_return(a, b):
            if str(a).endswith(".held.json"):
                raise PermissionError("held")
            return real_replace(a, b)
        with mock.patch.object(Path, "replace", open_copy), mock.patch.object(MN.os, "replace", no_return):
            m, r2 = self.conform("tag60_real30", crf=18)
        self.assertEqual(r2["skipped"], "in use")
        self.assertIn("aside", r2["reason"])
        self.assertFalse(Path(r1["sidecar"]).exists())
        self.assertEqual(sha(r1["path"]), h16)                                     # the old copy is untouched
        self.no_wrong_reuse(h16)

    def test_the_old_record_cannot_be_removed_after_success(self):
        m, r1 = self.conform("tag60_real30")
        real = MN.linksafe.remove
        calls = []

        def late(path, root, within=None):
            if str(path).endswith(".held.json") and os.path.lexists(path):
                calls.append(path)
                raise MN.Guidance("read-only", "clear it")
            return real(path, root, within)
        with mock.patch.object(MN.linksafe, "remove", late):
            m, r2 = self.conform("tag60_real30", crf=18)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(len(calls), 1)
        self.assertIn(".held.json", r2["reason"])
        name = Path(calls[0]).name                                                 # review 2063755 P3-3: a line
        self.assertEqual(r2["lines"], {"en": [MN.LINES["held_left"][0].format(name=name)],
                                       "ar": [MN.LINES["held_left"][1].format(name=name)]})
        self.assertEqual(json.loads(Path(r2["sidecar"]).read_text(encoding="utf-8"))["crf"], 18)
        m, r3 = self.conform("tag60_real30", crf=18)
        self.assertTrue(r3["reused"])
        self.assertFalse(os.path.lexists(calls[0]))                                # cleared on reuse (P3-2)
        m, r4 = self.conform("tag60_real30")
        self.assertTrue(r4["ok"] and not r4["reused"], r4)
        self.assertEqual(len(list(self.ls())), 2)

    def test_a_linked_copy_with_a_matching_record_is_never_reused(self):
        """Review r2 #5: a hard-linked .mp4 or .json with a VALID matching record is still not ours."""
        m, r1 = self.conform("tag60_real30")
        out, side = Path(r1["path"]), Path(r1["sidecar"])
        victim = self.tmp / "assets" / "victim.mp4"
        shutil.copyfile(out, victim)
        before = sha(victim)
        out.unlink()
        os.link(victim, out)                                                       # the copy is someone's footage
        m, r2 = self.conform("tag60_real30")
        self.assertTrue(r2["ok"] and not r2["reused"], r2)
        self.assertEqual(sha(victim), before)
        record = self.tmp / "assets" / "record.json"
        shutil.copyfile(side, record)
        rec_before = sha(record)
        side.unlink()
        os.link(record, side)                                                      # the record is someone else's file
        m, r3 = self.conform("tag60_real30")
        self.assertTrue(r3["ok"] and not r3["reused"], r3)
        self.assertEqual(sha(record), rec_before)
        self.assertEqual(os.stat(side).st_nlink, 1)

    def names(self, name="tag60_real30"):
        src = fx(name)
        stem = f"{src.stem[:60]}.{MN._source_tag(src, self.tmp)}.conform"
        return self.out / f"{stem}.partial.mp4", self.out / f"{stem}.json", self.out / f"{stem}.mp4"

    def planted(self, link):
        """Hard links named like our partial, sidecar and copy, pointing at the client's footage."""
        self.out.mkdir(parents=True)
        victims = []
        for i, p in enumerate(self.names()):
            v = self.tmp / "assets" / f"victim{i}.bin"
            v.write_bytes(b"FOOTAGE %d" % i)
            link(v, p)
            victims.append(v)
        m, r = self.conform("tag60_real30")
        self.assertTrue(r["ok"], r)
        for i, v in enumerate(victims):
            self.assertEqual(v.read_bytes(), b"FOOTAGE %d" % i, v)              # never written through
        self.assertFalse(r["reused"])                                             # a link is never taken as our copy
        for p in self.names()[1:]:
            self.assertFalse(os.path.islink(p))
            self.assertEqual(os.stat(p).st_nlink, 1)
        return r

    def test_hard_links_under_our_names_are_never_written_through(self):
        """Review 19049fe #2 (hard links work on NTFS and every POSIX file system without privileges)."""
        self.planted(os.link)

    @unittest.skipUnless(_can_symlink(), "this account may not create symlinks (Windows without developer mode)")
    def test_symlinks_under_our_names_are_never_written_through(self):
        """Review 19049fe #2 and #6: the symlink branch, on macOS / Linux (and Windows with developer mode)."""
        self.planted(lambda v, p: os.symlink(v, p))

    def test_the_symlink_branch_of_the_link_test(self):
        """Review 19049fe #6: the POSIX branch of the link test, on every OS (os.lstat mocked)."""
        st = os.stat_result((0o120777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        with mock.patch("lib.linksafe.os.lstat", return_value=st):
            self.assertTrue(MN._is_link(self.tmp / "x"))

    def test_any_runner_error_leaves_no_partial_file(self):
        def boom(cmd):
            Path(cmd[-1]).write_bytes(b"half")
            raise OSError("disk gone")
        m, r = self.conform("tag60_real30", runner=boom)
        self.assertFalse(r["ok"])
        self.assertEqual(list(self.ls()), [])


class TestReview2063755(_Out):
    """Review 2063755 (owner pre-mortem item b): nothing planted while the encode runs is handed back as our copy, and
    a record set aside by a stopped run is cleared."""
    names = TestBatchBTimeout.names                                                 # our partial, record, copy

    def encode_then(self, plant):
        def runner(cmd):
            r = subprocess.run(cmd, capture_output=True, timeout=600)
            plant(Path(cmd[-1]))                                                   # right after FFmpeg finished
            return r
        return runner

    def victim(self, name="victim.bin"):
        v = self.tmp / "assets" / name
        v.write_bytes(b"CLIENT FOOTAGE")
        return v

    def assert_changed(self, r):
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["skipped"], "changed")
        self.assertIsNone(r["path"])
        self.assertEqual(r["lines"], {"en": [MN.LINES["changed"][0]], "ar": [MN.LINES["changed"][1]]})

    def planted_partial(self, link):
        m, r1 = self.conform("tag60_real30")                                       # an earlier crf16 pair
        pair = sorted([Path(r1["path"]).name, Path(r1["sidecar"]).name])
        before = (sha(r1["path"]), Path(r1["sidecar"]).read_text(encoding="utf-8"))
        v = self.victim()

        def plant(tmp):
            tmp.unlink()
            link(v, tmp)
        m, r2 = self.conform("tag60_real30", crf=18, runner=self.encode_then(plant))
        self.assert_changed(r2)
        self.assertEqual(v.read_bytes(), b"CLIENT FOOTAGE")
        self.assertEqual(os.stat(v).st_nlink, 1)                                   # the planted name was removed
        self.assertEqual(sorted(p.name for p in self.ls()), pair)
        self.assertEqual((sha(r1["path"]), Path(r1["sidecar"]).read_text(encoding="utf-8")), before)
        m, r3 = self.conform("tag60_real30")
        self.assertTrue(r3["reused"])                                              # the old pair was never touched

    def test_a_hard_link_planted_at_the_partial_during_the_encode_is_not_handed_back(self):
        self.planted_partial(os.link)

    @unittest.skipUnless(_can_symlink(), "this account may not create symlinks (Windows without developer mode)")
    def test_a_symlink_planted_at_the_partial_during_the_encode_is_not_handed_back(self):
        self.planted_partial(lambda v, p: os.symlink(v, p))

    def test_the_folder_swapped_for_a_link_during_the_encode_is_never_written_through(self):
        """output/intermediates renamed and replaced by a link into assets/ while FFmpeg runs (macOS allows the rename
        with the file open; on Windows once FFmpeg has closed it)."""
        moved = self.tmp / "output" / "moved"
        decoy = []

        def plant(tmp):
            os.replace(self.out, moved)
            _junction(self.out, self.tmp / "assets")
            decoy.append(self.victim(tmp.name))                                    # the partial's name, in assets/
        self.addCleanup(lambda: _unlink_dir(self.out) if os.path.lexists(self.out) else None)
        m, r = self.conform("tag60_real30", runner=self.encode_then(plant))
        self.assert_changed(r)
        self.assertEqual(sorted(p.name for p in (self.tmp / "assets").iterdir()), [decoy[0].name])
        self.assertEqual(decoy[0].read_bytes(), b"CLIENT FOOTAGE")                 # never removed or renamed through it
        self.assertEqual([p.name.endswith(".partial.mp4") for p in moved.iterdir()], [True])

    def test_a_folder_planted_at_the_partial_is_left_as_it_is(self):
        def plant(tmp):
            tmp.unlink()
            tmp.mkdir()
            (tmp / "keep.txt").write_text("someone's", encoding="utf-8")
        m, r = self.conform("tag60_real30", runner=self.encode_then(plant))
        self.assert_changed(r)
        self.assertIn("is a folder now", r["reason"])
        keep = next(self.out.glob("*.partial.mp4/keep.txt"))
        m, r2 = self.conform("tag60_real30")                                       # review r3 P3-1: and on the next
        self.assert_changed(r2)                                                    # run too, before any encode
        self.assertIn("is a folder", r2["reason"])
        self.assertEqual(keep.read_text(encoding="utf-8"), "someone's")

    def test_a_folder_under_a_record_name_is_never_moved_or_removed(self):
        partial, side, out = self.names()
        held = side.with_name(side.stem + ".held.json")
        for name in (held, side, out):
            with self.subTest(name.name):
                (name / "sub").mkdir(parents=True)
                (name / "sub" / "keep.txt").write_text("someone's", encoding="utf-8")
                ran = []
                m, r = self.conform("tag60_real30", runner=lambda cmd: ran.append(cmd))
                self.assert_changed(r)
                self.assertEqual(ran, [])                                          # found before the encode
                self.assertEqual((name / "sub" / "keep.txt").read_text(encoding="utf-8"), "someone's")
                shutil.rmtree(name)
        m, r1 = self.conform("tag60_real30")                                       # a folder at the held name, on
        (held / "sub").mkdir(parents=True)                                         # the reuse path
        (held / "sub" / "keep.txt").write_text("someone's", encoding="utf-8")
        m, r2 = self.conform("tag60_real30")
        self.assertTrue(r2["ok"] and r2["reused"], r2)
        self.assertIn("is a folder", r2["reason"])
        self.assertEqual((held / "sub" / "keep.txt").read_text(encoding="utf-8"), "someone's")

    def fake(self, cmd):
        Path(cmd[-1]).write_bytes(b"a finished encode")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def two_parts(self, **kw):
        d = MN.decide(MN.measure(fx("tag60_real30")))
        d["duration_s"] = 20.0
        with quiet():
            return self.cf(fx("tag60_real30"), self.out, d, ranges=[(1.0, 2.0), (10.0, 11.0)], **kw)

    def test_a_later_part_without_a_record_keeps_the_first_parts_record(self):
        """Review r3 P3-2: the parts are the truth for which copy has a record."""
        real, calls = MN.linksafe.replace_atomic, []

        def second_fails(path, root, data, within=None):
            calls.append(path)
            if len(calls) == 2:
                raise MN.Guidance("access denied", "close it")
            return real(path, root, data, within)
        with mock.patch.object(MN.linksafe, "replace_atomic", second_fails):
            r = self.two_parts(runner=self.fake)
        self.assertTrue(r["ok"], r)
        self.assertIsNone(r["skipped"])
        self.assertEqual([p["sidecar"] is not None for p in r["parts"]], [True, False])
        self.assertEqual(r["sidecar"], r["parts"][0]["sidecar"])
        self.assertTrue(Path(r["parts"][0]["sidecar"]).is_file())
        self.assertEqual(r["lines"], {"en": [MN.LINES["no_record"][0]], "ar": [MN.LINES["no_record"][1]]})

    def test_a_later_failure_drops_the_used_note_and_keeps_the_junk_note(self):
        """Review r3 P3-3: part 1 has no record and an old record it can't remove, then part 2 fails: the original
        is used, so 'it is used now' goes; the junk file to delete is still named."""
        r0 = self.two_parts(runner=self.fake)
        first_side = Path(r0["parts"][0]["sidecar"])
        held = first_side.with_name(first_side.stem + ".held.json")
        real_remove, n = MN.linksafe.remove, []

        def stuck(path, root, within=None):
            if str(path) == str(held) and os.path.lexists(path):
                raise MN.Guidance("read-only", "clear it")
            return real_remove(path, root, within)

        def runner(cmd):
            n.append(cmd)
            if len(n) == 2:                                                        # part 2: a link planted
                Path(cmd[-1]).write_bytes(b"x")
                Path(cmd[-1]).unlink()
                os.link(self.tmp / "assets" / "victim.bin", cmd[-1])
            else:
                self.fake(cmd)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        (self.tmp / "assets" / "victim.bin").write_bytes(b"CLIENT FOOTAGE")
        with mock.patch.object(MN.linksafe, "replace_atomic", side_effect=MN.Guidance("access denied", "x")), \
                mock.patch.object(MN.linksafe, "remove", stuck):
            r = self.two_parts(runner=runner, crf=18)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["skipped"], "changed")
        self.assertEqual(r["lines"]["en"], [MN.LINES["changed"][0], MN.LINES["held_left"][0].format(name=held.name)])
        self.assertEqual(r["lines"]["ar"], [MN.LINES["changed"][1], MN.LINES["held_left"][1].format(name=held.name)])
        self.assertNotIn("is used", r["reason"])
        self.assertEqual((self.tmp / "assets" / "victim.bin").read_bytes(), b"CLIENT FOOTAGE")

    def test_a_held_record_left_by_a_stopped_run_is_cleared_on_reuse(self):
        """Review 2063755 P3-2: a run that stopped after its new record left `.held.json` behind."""
        m, r1 = self.conform("tag60_real30")
        held = Path(r1["sidecar"]).with_name(Path(r1["sidecar"]).stem + ".held.json")
        held.write_text("{}", encoding="utf-8")
        m, r2 = self.conform("tag60_real30")
        self.assertTrue(r2["ok"] and r2["reused"], r2)
        self.assertFalse(os.path.lexists(held))
        self.assertEqual(r2["lines"], {"en": [], "ar": []})
        held.write_text("{}", encoding="utf-8")
        real = MN.linksafe.remove

        def stuck(path, root, within=None):
            if str(path).endswith(".held.json"):
                raise MN.Guidance("read-only", "clear it")
            return real(path, root, within)
        with mock.patch.object(MN.linksafe, "remove", stuck):
            m, r3 = self.conform("tag60_real30")
        self.assertTrue(r3["ok"] and r3["reused"], r3)                             # still used, and said plainly
        self.assertIn(held.name, r3["reason"])
        self.assertEqual(r3["lines"]["en"], [MN.LINES["held_left"][0].format(name=held.name)])
        self.assertEqual(r3["lines"]["ar"], [MN.LINES["held_left"][1].format(name=held.name)])


def _onsets(t, x, thr, gap=5.0):
    """Times where x rises above thr after at least `gap` seconds below it (numpy arrays)."""
    idx = np.flatnonzero(x > thr)
    if not idx.size:
        return np.array([])
    return t[idx][np.concatenate(([True], np.diff(t[idx]) > gap))]


class TestBatchBLongSync(_Out):
    """P2: A/V sync after VFR -> CFR over 10 minutes, measured event by event (equal stream lengths would also pass a
    constant offset). A flash (3 white frames) and a 1 kHz beep start together every 10 s; the video is dense around
    each flash and every third frame elsewhere (VFR)."""

    def make(self, name, af=None):
        from lib.common import ffmpeg_exe
        src = self.tmp / "data" / name
        cmd = [ffmpeg_exe(), "-v", "error", "-y",
               "-f", "lavfi", "-i", "color=black:size=64x36:rate=30:duration=600",
               "-f", "lavfi", "-i", r"aevalsrc='if(lt(mod(t\,10)\,0.05)\,0.8*sin(2*PI*1000*t)\,0)':s=48000:d=600",
               "-vf", r"drawbox=color=white:t=fill:enable='lt(mod(t\,10)\,0.1)',"
                      r"select='not(mod(n\,3))+between(mod(n\,300)\,0\,40)'"]
        cmd += ["-af", af] if af else []
        subprocess.run(cmd + ["-fps_mode", "vfr", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                              "-c:a", "aac", "-b:a", "96k", str(src)], check=True, capture_output=True)
        return src

    def offsets(self, src):
        import av
        m = MN.measure(src)
        self.assertTrue(m["vfr"], m)
        d = MN.decide(m)
        self.assertIn("cfr", d["actions"])
        with quiet():
            r = self.cf(src, self.out, d)
        self.assertTrue(r["ok"], r)
        with av.open(r["path"]) as c:
            vt, vl = [], []
            for f in c.decode(c.streams.video[0]):
                vt.append(float(f.time))
                vl.append(float(f.to_ndarray(format="gray").mean()))
        with av.open(r["path"]) as c:
            at, al = [], []
            for f in c.decode(c.streams.audio[0]):
                x = np.abs(f.to_ndarray()).max(axis=0)
                at.append(float(f.time) + np.arange(len(x)) / f.sample_rate)
                al.append(x)
        with av.open(r["path"]) as c:                    # review 19049fe #7: an editor reads samples back to back
            fr = [(float(f.time), f.samples / f.sample_rate) for f in c.decode(c.streams.audio[0])]
        self.assertLessEqual(abs(fr[0][0]), 1 / float(r["fps"]), fr[0])          # the audio starts with the picture
        holes = [(t1, t1 - t0 - n) for (t0, n), (t1, _) in zip(fr, fr[1:]) if abs(t1 - t0 - n) > 0.001]
        self.assertEqual(holes, [])                                                # gaps filled, never left as holes
        v_on = _onsets(np.array(vt), np.array(vl), 128)
        a_on = _onsets(np.concatenate(at), np.concatenate(al), 0.3)
        self.assertGreaterEqual(len(v_on), 59, v_on[:5])
        pairs = {round(float(v)): float(v - a_on[np.argmin(np.abs(a_on - v))]) for v in v_on}   # nearest beep
        return float(r["fps"]), pairs

    def test_av_offset_within_one_frame_over_ten_minutes(self):
        fps, pairs = self.offsets(self.make("long sync وقت.mp4"))
        self.assertEqual(len(pairs), 60)
        for t in (0, 10, 590):                                                     # the start and the end
            self.assertLessEqual(abs(pairs[t]), 1 / fps, (t, pairs[t], fps))
        self.assertLessEqual(max(map(abs, pairs.values())), 1 / fps, pairs)       # and nothing drifts in between

    def test_av_offset_with_a_late_audio_start_and_a_gap(self):
        """Zoom / phone files: the audio starts 0.5 s after the picture and loses 0.2 s mid-clip (timestamps kept,
        MKV), so the conform must place the audio by its timestamps, not end to end."""
        fps, pairs = self.offsets(self.make("gap.mkv", r"atrim=start=0.5,aselect='not(between(t\,305\,305.2))'"))
        for t in (10, 300, 310, 590):                                              # before and after the gap, the end
            self.assertLessEqual(abs(pairs[t]), 1 / fps, (t, pairs[t], fps))
        self.assertLessEqual(max(abs(v) for t, v in pairs.items() if t), 1 / fps, pairs)   # t=0: no audio yet


class TestT26Final(_Out):
    """Review 0cd67d7, executor rulings 2026-10-18 (2): our partial is never removed through a swapped folder or as
    someone's folder on any failure path (P2-1); a link refusal after the rename is "changed", never ok (P3-1); a
    folder link at one of our names is removed as a link, never kept as a folder (P3-2). Case list: the lane's
    work/t26-final/cases.md."""
    names = TestBatchBTimeout.names                                                 # our partial, record, copy

    def fresh(self):
        """A new client folder per sub-case (the swap moves output/intermediates away)."""
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t26f-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "assets").mkdir()
        (self.tmp / "data").mkdir()
        self.out = self.tmp / "output" / "intermediates"
        out = self.out                                                             # the link only, before the tree
        self.addCleanup(lambda: _unlink_dir(out) if MN.linksafe.is_link(out) else None)

    def swap(self, tmp):
        """output/intermediates moved away and replaced by a link into assets/, where a client file carries our
        partial's name: what the folder path now shows."""
        os.replace(self.out, self.tmp / "output" / "moved")
        _junction(self.out, self.tmp / "assets")
        decoy = self.tmp / "assets" / tmp.name
        decoy.write_bytes(b"CLIENT FOOTAGE")
        return decoy

    def folder(self, tmp):
        """Someone's real folder under our partial's name."""
        tmp.unlink()
        tmp.mkdir()
        keep = tmp / "keep.txt"
        keep.write_bytes(b"CLIENT FOOTAGE")
        return keep

    def failing(self, plant, finish):
        """A runner that writes the partial, plants (swap / folder), then ends as `finish` says."""
        seen = {}

        def runner(cmd):
            Path(cmd[-1]).write_bytes(b"half")
            seen["kept"] = plant(Path(cmd[-1]))
            return finish(cmd)
        return runner, seen

    def each_plant(self, finish, check):
        for kind in ("swap", "folder"):
            with self.subTest(kind):
                self.fresh()
                runner, seen = self.failing(getattr(self, kind), finish)
                with mock.patch.object(MN.time, "sleep"):
                    m, r = self.conform("tag60_real30", runner=runner)
                self.assertFalse(r["ok"], r)
                check(r)
                self.assertEqual(seen["kept"].read_bytes(), b"CLIENT FOOTAGE")       # never deleted
                if kind == "swap":
                    self.assertEqual(sorted(p.name for p in (self.tmp / "assets").iterdir()), [seen["kept"].name])
                    self.assertIn("left in place", r["reason"])
                    self.assertIn("link", r["reason"])
                else:
                    self.assertIn("is a folder", r["reason"])

    def test_p2_1_ffmpeg_failed_never_deletes_through_a_swapped_folder(self):
        def check(r):
            self.assertIsNone(r["skipped"])
            self.assertIn("ffmpeg failed", r["reason"])
            self.assertEqual(r["lines"]["en"], [MN.LINES["failed"][0]])
        self.each_plant(lambda cmd: subprocess.CompletedProcess(cmd, 1, b"", b"boom"), check)
        with self.subTest("swap, nothing written"):                                # nothing to remove: nothing is
            self.fresh()                                                           # said to be left behind

            def runner(cmd):
                os.replace(self.out, self.tmp / "output" / "moved")
                _junction(self.out, self.tmp / "assets")
                return subprocess.CompletedProcess(cmd, 1, b"", b"boom")
            m, r = self.conform("tag60_real30", runner=runner)
            self.assertFalse(r["ok"], r)
            self.assertEqual(r["reason"], "ffmpeg failed: boom")
            self.assertEqual(list((self.tmp / "assets").iterdir()), [])

    def test_p2_1_a_timeout_never_deletes_through_a_swapped_folder(self):
        def finish(cmd):
            raise subprocess.TimeoutExpired(cmd, 1)

        def check(r):
            self.assertEqual(r["skipped"], "timeout")
            self.assertEqual(r["lines"]["en"], [MN.LINES["timeout"][0]])
        self.each_plant(finish, check)

    def test_p2_1_a_runner_error_never_deletes_through_a_swapped_folder(self):
        def finish(cmd):
            raise OSError("disk gone")

        def check(r):
            self.assertIn("OSError: disk gone", r["reason"])
            self.assertEqual(r["lines"]["en"], [MN.LINES["failed"][0]])
        self.each_plant(finish, check)
        for kind in ("swap", "folder"):                                            # a real BaseException: raised on,
            with self.subTest("interrupt " + kind):                               # and still nothing deleted
                self.fresh()

                def stop(cmd):
                    raise KeyboardInterrupt
                runner, seen = self.failing(getattr(self, kind), stop)
                with self.assertRaises(KeyboardInterrupt), mock.patch.object(MN.time, "sleep"):
                    self.conform("tag60_real30", runner=runner)
                self.assertEqual(seen["kept"].read_bytes(), b"CLIENT FOOTAGE")

    def gap_swap(self):
        """_plain_file wrapped: right after the post-encode check passed on the partial, the folder is swapped for a
        link into assets/ that shows a copy of the partial under its name (the documented gap)."""
        real, decoys = MN._plain_file, []

        def pf(p):
            v = real(p)
            if str(p).endswith(".partial.mp4") and v and not decoys:
                moved = self.tmp / "output" / "moved"
                os.replace(self.out, moved)
                _junction(self.out, self.tmp / "assets")
                decoys.append(self.tmp / "assets" / Path(p).name)
                shutil.copyfile(moved / Path(p).name, decoys[0])
            return v
        return mock.patch.object(MN, "_plain_file", pf), decoys

    def fake(self, cmd):
        Path(cmd[-1]).write_bytes(b"a finished encode")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    def test_an_open_copy_after_a_swap_never_deletes_through_it(self):
        """The P2-1 class on the in_use path: the folder swapped in the gap, then the rename to the final name fails
        (the old copy open in Premiere): the partial is not removed through the link."""
        self.fresh()
        patch, decoys = self.gap_swap()
        real_replace = Path.replace

        def replace(self_, target):
            if self_.name.endswith(".partial.mp4"):
                raise PermissionError(13, "in use by Premiere", str(target))
            return real_replace(self_, target)
        with patch, mock.patch.object(Path, "replace", replace), mock.patch.object(MN.time, "sleep"):
            m, r = self.conform("tag60_real30", runner=self.fake)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["skipped"], "in use")
        self.assertEqual(decoys[0].read_bytes(), b"a finished encode")              # what the link showed: kept
        self.assertIn("left in place", r["reason"])
        self.assertEqual(sorted(p.name for p in (self.tmp / "assets").iterdir()), [decoys[0].name])

    def test_p3_1_a_link_refusal_after_the_rename_is_changed_never_ok(self):
        self.fresh()
        patch, decoys = self.gap_swap()
        with patch:
            m, r = self.conform("tag60_real30", runner=self.fake)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["skipped"], "changed")
        self.assertIsNone(r["path"])
        self.assertEqual(r["parts"], [])
        self.assertEqual(r["lines"], {"en": [MN.LINES["changed"][0]], "ar": [MN.LINES["changed"][1]]})
        copy = self.names()[2].name
        self.assertIn(copy, r["reason"])                                           # named, so it can be found
        self.assertEqual(sorted(p.name for p in (self.tmp / "assets").iterdir()), [copy])   # nothing else written
        self.assertEqual([p.name for p in (self.tmp / "output" / "moved").iterdir()],      # and nothing removed
                         [self.names()[0].name])                                           # on the real side
        m, r2 = self.conform("tag60_real30", runner=self.fake)                     # still swapped: refused, never
        self.assertFalse(r2["ok"])                                                 # written through
        self.assertEqual(r2["skipped"], "not output")

    def test_p3_1_clear_held_runs_only_when_a_held_record_exists(self):
        self.fresh()
        real, ran = MN.linksafe.remove, []

        def remove(path, root, within=None):
            if ran and str(path).endswith(".held.json"):
                raise MN.Guidance("a link (junction or symlink) is on that path", "x")   # if it were ever tried
            return real(path, root, within)

        def runner(cmd):
            ran.append(cmd)
            return self.fake(cmd)
        with mock.patch.object(MN.linksafe, "remove", remove):
            m, r = self.conform("tag60_real30", runner=runner)
        self.assertTrue(r["ok"], r)
        self.assertIsNone(r["reason"])
        self.assertEqual(r["lines"], {"en": [], "ar": []})                         # no false "could not be removed"

    def test_p3_2_a_folder_link_at_each_of_our_names_is_removed_as_a_link(self):
        """Kills mutant N15 (`_real_dir` following the link): a link to a folder is a name, never someone's folder."""
        kinds = [("junction", _junction)]
        if _can_symlink():
            kinds.append(("dir symlink", lambda link, target: os.symlink(target, link, target_is_directory=True)))
        for kind, make in kinds:
            for which in ("partial", "held", "record", "copy"):
                with self.subTest(kind=kind, name=which):
                    self.fresh()
                    partial, side, out = self.names()
                    held = side.with_name(side.stem + ".held.json")
                    at = {"partial": partial, "held": held, "record": side, "copy": out}[which]
                    target = self.tmp / "assets" / "linked"
                    target.mkdir()
                    (target / "keep.txt").write_bytes(b"CLIENT FOOTAGE")
                    self.out.mkdir(parents=True)
                    make(at, target)
                    names = (partial, held, side, out)
                    self.addCleanup(lambda ns=names: [_unlink_dir(p) for p in ns if MN.linksafe.is_link(p)])
                    m, r = self.conform("tag60_real30", runner=self.fake)
                    self.assertEqual([p.name for p in target.iterdir()], ["keep.txt"])
                    self.assertEqual((target / "keep.txt").read_bytes(), b"CLIENT FOOTAGE")
                    self.assertNotIn("is a folder", r["reason"] or "")
                    if which != "copy":
                        self.assertTrue(r["ok"], r)
                        self.assertFalse(MN.linksafe.is_link(at))                  # removed (or replaced) as a name
                        self.assertTrue(MN._plain_file(out))
                    elif os.name == "nt":                                          # Windows: a file can't be renamed
                        self.assertFalse(r["ok"], r)                               # over a link to a folder: the
                        self.assertEqual(r["skipped"], "in use")                   # link and its target stay
                        self.assertTrue(MN.linksafe.is_link(out))
                    else:                                                          # POSIX: rename replaces the link
                        self.assertTrue(r["ok"], r)                                # itself, never its target
                        self.assertTrue(MN._plain_file(out))


class TestRecordTempFiles(_Out):
    """T26-wire item B (coordinator, suite 8bb853a): no temp file of a record write ever stays in the output folder.
    linksafe.replace_atomic writes `.<record>.<12 hex>.tmp` and, when the write fails, removes it with one plain
    unlink, which a virus scanner holding the fresh file defeats; conform now removes it through linksafe."""

    def stuck_write(self, err):
        """replace_atomic whose temp file stays behind (its own clean-up defeated), then the error."""
        def write(path, root, data, within=None):
            tmp = Path(path).with_name(f".{Path(path).name}.{'ab12' * 3}.tmp")
            MN.linksafe.create_new(tmp, root, data, within)
            raise err
        return write

    def tmps(self):
        return [p.name for p in self.ls() if p.name.endswith(".tmp")]

    def test_a_failed_record_write_leaves_no_temp_file(self):
        for err in (MN.Guidance("access denied", "close it"), PermissionError("locked by a virus scan")):
            with self.subTest(type(err).__name__):
                m, r1 = self.conform("tag60_real30")
                with mock.patch.object(MN.linksafe, "replace_atomic", side_effect=self.stuck_write(err)):
                    m, r2 = self.conform("tag60_real30", crf=18)
                self.assertTrue(r2["ok"], r2)
                self.assertIn("could not be saved", r2["reason"])
                self.assertEqual(self.tmps(), [])
                self.assertEqual(sorted(p.name for p in self.ls()), [Path(r2["path"]).name])   # the copy only

    def test_a_temp_file_still_held_is_named_in_the_reason(self):
        real_remove = MN.linksafe.remove

        def held(path, root, within=None):
            if str(path).endswith(".tmp"):
                raise MN.linksafe.RemoveIncomplete(0, [(str(path), "held by a scanner")])
            return real_remove(path, root, within)
        m, r1 = self.conform("tag60_real30")
        with mock.patch.object(MN.linksafe, "replace_atomic", side_effect=self.stuck_write(PermissionError("x"))), \
                mock.patch.object(MN.linksafe, "remove", held), mock.patch.object(MN.time, "sleep"):
            m, r2 = self.conform("tag60_real30", crf=18)
        self.assertTrue(r2["ok"], r2)
        self.assertIn("could not be removed yet", r2["reason"])
        m, r3 = self.conform("tag60_real30")                                       # the next encode clears it
        self.assertEqual(self.tmps(), [])

    def test_an_earlier_runs_temp_file_is_removed_before_the_encode_and_nothing_else_is(self):
        m, r1 = self.conform("tag60_real30")
        side = Path(r1["sidecar"])
        ours = side.with_name(f".{side.name}.0123456789ab.tmp")
        ours.write_bytes(b"{}")
        other = side.with_name(".someone-elses.json.0123456789ab.tmp")            # not this record's name
        other.write_bytes(b"keep")
        folder = side.with_name(f".{side.name}.ffffffffffff.tmp")                 # a folder under that name
        folder.mkdir()
        (folder / "keep.txt").write_bytes(b"keep")
        m, r2 = self.conform("tag60_real30", crf=18)                               # a new copy: an encode
        self.assertTrue(r2["ok"], r2)
        self.assertFalse(os.path.lexists(ours))
        self.assertEqual(other.read_bytes(), b"keep")
        self.assertEqual((folder / "keep.txt").read_bytes(), b"keep")              # never someone's folder

    def test_a_temp_file_link_is_removed_as_a_name_only(self):
        m, r1 = self.conform("tag60_real30")
        side = Path(r1["sidecar"])
        target = self.tmp / "assets" / "linked"
        target.mkdir()
        (target / "keep.txt").write_bytes(b"CLIENT FOOTAGE")
        lnk = side.with_name(f".{side.name}.0123456789ab.tmp")
        _junction(lnk, target)
        self.addCleanup(lambda: _unlink_dir(lnk) if MN.linksafe.is_link(lnk) else None)
        m, r2 = self.conform("tag60_real30", crf=18)
        self.assertTrue(r2["ok"], r2)
        self.assertEqual((target / "keep.txt").read_bytes(), b"CLIENT FOOTAGE")
        self.assertFalse(os.path.lexists(lnk))

    def test_the_scanner_copy_pattern_names_only_the_outside_form(self):
        self.assertTrue(_scanner_copy("TAG60_REAL30.FC772D56FE.CONFORM.HELD.JSON.tmp"))
        for ours in ("tag60_real30.fc772d56fe.conform.held.json", ".tag60_real30.fc772d56fe.conform.json.ab12ab12ab12.tmp",
                     "tag60_real30.fc772d56fe.conform.partial.mp4", "C0001.E523330249.conform.mp4"):
            self.assertFalse(_scanner_copy(ours), ours)


if __name__ == "__main__":
    unittest.main()
