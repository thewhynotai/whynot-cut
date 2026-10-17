# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 62 (Addendum K1, K-T2) — `reel removed-review`: a short MP4 of only what the edit removes (cuts,
retakes, removed pauses, trimmed head and tail), each with a 1 s slate (timecode, the words, the reason) and 0.5 s of
dimmed kept context on each side; words whose loss changes meaning are highlighted and listed first in the sheet.
Run:  bash tools/test.sh -p test_safety_removed_review.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402
from lib.safety import removed_review as RR  # noqa: E402

DUR = 12000


def words(spec, start=0, step=400):
    return [{"id": i, "segment_id": 1, "word": w, "start_ms": start + (i - 1) * step,
             "end_ms": start + (i - 1) * step + step - 40, "probability": 0.95} for i, w in enumerate(spec, 1)]


SPEECH = ["الدكتورة", "قالت", "إن", "الدوا", "ده", "لا", "تزيد", "عن", "٥٠٠", "مجم", "في", "اليوم",
          "وده", "مهم", "جدا", "للضغط", "وخلي", "بالك", "من", "نفسك", "يعني", "كده", "خلاص", "شكرا"]


class Project(unittest.TestCase):
    ROOT_NAME = "د. تجربة Dr Test"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt2_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / self.ROOT_NAME
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": "medical"})
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": words(SPEECH)})

    def spec(self, keep, dur=DUR, words_cut=None, in_ms=0):
        write_json(self.p.p("01_analysis/timeline-spec.json"), {
            "main_footage": "data/Raw/CLIP1.mov", "source_in_ms": in_ms, "fps": 25, "events": [],
            "time_map": {"keep_ms": keep, "source_duration_ms": dur, "words_cut": words_cut or []}})

    def snapshot(self):
        return {str(f.relative_to(self.root)): f.read_bytes() for f in self.root.rglob("*") if f.is_file()}


class TestPlan(Project):
    def test_lists_every_removed_span_in_order(self):
        # head 0-300 trimmed; a pause 1500-1900 (pause map); words 6-10 cut (2000-4000); tail after 11000
        write_json(self.p.p("06_audio/dialogue/pauses.json"), {"cuts_ms": [[1500, 1900]]})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"cut_words": [
            {"word_ids": [6, 7, 8, 9, 10], "reason": "TK-3 take dropped (best take: 4)"}]}})
        self.spec([[300, 1500], [1900, 2000], [4000, 11000]],
                  words_cut=[{"word_id": i, "start_ms": (i - 1) * 400, "reason": "TK-3 take dropped"} for i in range(6, 11)])
        doc = RR.plan(self.p)
        got = [(x["start_ms"], x["end_ms"], x["reason"]) for x in doc["pieces"]]
        self.assertEqual(got, [(0, 300, "head"), (1500, 1900, "pause"), (2000, 4000, "retake"),
                               (11000, DUR, "tail")])
        self.assertEqual(doc["pieces"][2]["word_ids"], [6, 7, 8, 9, 10])

    def test_meaning_words_highlighted(self):
        self.spec([[0, 2000], [4000, DUR]])          # «لا تزيد عن ٥٠٠ مجم» (words 6-10) inside the cut
        doc = RR.plan(self.p)
        piece = doc["pieces"][0]
        self.assertEqual(piece["reason"], "editor_cut")
        marked = {m["text"] for m in piece["meaning"]}
        self.assertIn("لا", marked)
        self.assertTrue(any(m.startswith("٥٠٠ مجم") for m in marked), marked)
        text = RR.sheet(doc)
        first = text.index("## كلمات بتغيّر المعنى")
        self.assertLess(first, text.index("## كل اللي اتشال"))
        self.assertIn("«لا»", text[first:text.index("## كل اللي اتشال")])

    def test_duration_formula(self):
        self.spec([[300, 1500], [1900, 11500]], dur=DUR)
        doc = RR.plan(self.p)
        pieces = doc["pieces"]
        # head (0-300): no context before (clip start), 0.5 s after; pause (1500-1900): 0.5 + 0.5;
        # tail (11500-12000): 0.5 before, none after (clip end)
        self.assertEqual([(p["context_before_ms"], p["context_after_ms"]) for p in pieces],
                         [(0, 500), (500, 500), (500, 0)])
        removed = 0.3 + 0.4 + 0.5
        self.assertAlmostEqual(RR.duration_s(pieces), removed + 3 * RR.SLATE_S + (0.5 + 1.0 + 0.5), places=3)

    def test_no_removed_parts_means_no_clip_and_a_plain_message(self):
        self.spec([[0, DUR]])
        before = self.snapshot()
        doc = RR.plan(self.p)
        self.assertEqual(doc["pieces"], [])
        res = RR.render(self.p)
        self.assertFalse(res["clip"])
        self.assertTrue(res["message"].startswith("مفيش حاجة اتشالت"))
        self.assertEqual(self.snapshot(), before)

    def test_overlapping_and_touching_removals_merge(self):
        self.spec([[0, 1000], [1000, 1000], [3000, 3000], [5000, DUR]])
        doc = RR.plan(self.p)
        self.assertEqual([(x["start_ms"], x["end_ms"]) for x in doc["pieces"]], [(1000, 5000)])

    def test_never_footage_outside_the_source(self):
        self.spec([[100, 1500], [1900, 11950]], in_ms=60000)
        for p in RR.plan(self.p)["pieces"]:
            a, b = p["file_from_ms"], p["file_to_ms"]
            self.assertGreaterEqual(a, 60000)
            self.assertLessEqual(b, 60000 + DUR)

    def test_long_clip_plans_fast(self):
        keep = [[k * 1000, k * 1000 + 700] for k in range(1000)]
        self.spec(keep, dur=1000 * 1000)
        t0 = time.monotonic()
        doc = RR.plan(self.p)
        self.assertEqual(len(doc["pieces"]), 1000)
        self.assertLess(time.monotonic() - t0, 10)

    def test_missing_or_damaged_plan_is_refused_and_nothing_written(self):
        before = self.snapshot()
        with self.assertRaises(Guidance) as cm:
            RR.plan(self.p)
        self.assertTrue(str(cm.exception).startswith("مفيش خطة"))
        self.p.p("01_analysis").mkdir(parents=True, exist_ok=True)
        self.p.p("01_analysis/timeline-spec.json").write_text("{x", encoding="utf-8")
        with self.assertRaises(Guidance):
            RR.render(self.p)
        before[str(self.p.p("01_analysis/timeline-spec.json").relative_to(self.root))] = b"{x"
        self.assertEqual(self.snapshot(), before)

    def test_missing_words_still_plans(self):
        self.p.p("02_transcription/words.json").unlink()
        self.spec([[0, 2000], [4000, DUR]])
        piece = RR.plan(self.p)["pieces"][0]
        self.assertEqual((piece["words"], piece["meaning"]), ("", []))

    def test_rerun_is_identical_and_same_on_macos(self):
        self.spec([[300, 1500], [1900, 11500]])
        a = RR.plan(self.p)
        with mock.patch.object(sys, "platform", "darwin"):
            b = RR.plan(self.p)
        self.assertEqual(a, b)
        self.assertEqual(RR.sheet(a), RR.sheet(b))

    def test_gpu_failure_reruns_on_the_cpu(self):
        self.spec([[0, 2000], [4000, DUR]])
        (self.root / "data/Raw/CLIP1.mov").write_bytes(b"not a real clip: the fake runner never reads it")
        calls = []

        def runner(cmd):
            calls.append(cmd)
            if "h264_nvenc" in cmd:
                return subprocess.CompletedProcess(cmd, 1, "", "OpenEncodeSessionEx failed: out of memory")
            return subprocess.CompletedProcess(cmd, 1, "", "stop here")
        with mock.patch.object(RR, "_lane", return_value="cuda"):
            with self.assertRaises(Guidance):
                RR.render(self.p, runner=runner)
        self.assertTrue(any("h264_nvenc" in c for c in calls))
        self.assertTrue(any("libx264" in c for c in calls))


class TestReviewRound1(Project):
    def test_i1_a_plan_that_removes_nothing_says_so(self):
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"main_footage": "data/Raw/CLIP1.mov", "fps": 25,
                                                                "events": [], "duration_ms": DUR, "time_map": None})
        self.assertEqual(RR.plan(self.p)["pieces"], [])
        self.assertTrue(RR.render(self.p)["message"].startswith("مفيش حاجة اتشالت"))

    def test_i2_context_stops_at_the_next_removed_part(self):
        self.spec([[0, 1000], [3000, 3200], [5000, DUR]])          # a 200 ms kept piece between two cuts
        a, b = RR.plan(self.p)["pieces"]
        self.assertEqual((a["context_after_ms"], b["context_before_ms"]), (200, 200))

    def test_minor_words_without_an_id_and_partial_overlap(self):
        ws = words(SPEECH)
        del ws[6]["id"]                              # word 7 (2400-2760) has no id: skipped, never a crash
        write_json(self.p.p("02_transcription/words.json"), {"words": ws})
        self.spec([[0, 2190], [4000, DUR]])          # word 6 (2000-2360) is mostly kept: not listed as removed
        piece = RR.plan(self.p)["pieces"][0]
        self.assertEqual(piece["word_ids"][0], 8)

    def test_minor_slate_text_cut_at_a_word(self):
        self.assertEqual(RR._short("كلمة " * 30, 20).endswith("…"), True)
        self.assertFalse(RR._short("كلمة " * 30, 20)[:-2].endswith("كل"))

    def test_minor_gpu_failure_part_way_redoes_every_part_on_the_cpu(self):
        self.spec([[0, 1000], [2000, 3000], [4000, DUR]])
        (self.root / "data/Raw/CLIP1.mov").write_bytes(b"x")
        made = []

        def runner(cmd):
            out = Path(cmd[-1])
            if "h264_nvenc" in cmd and "part0002" in out.name:
                return subprocess.CompletedProcess(cmd, 1, "", "OpenEncodeSessionEx failed: out of memory")
            out.write_bytes(b"part")
            made.append(("nvenc" if "h264_nvenc" in cmd else "x264" if "libx264" in cmd else "join", out.name))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(RR, "_lane", return_value="cuda"), \
                mock.patch.object(RR, "_probe", return_value=((406, 720), True)):
            res = RR.render(self.p, runner=runner)
        cpu_parts = [n for k, n in made if k == "x264"]
        self.assertIn("part0001.mp4", cpu_parts)               # part 1 was redone on the CPU too
        self.assertEqual(res["lane"], "cpu")

    def test_r2_spec_without_a_time_map_key_is_refused_and_point_words_count(self):
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"main_footage": "x", "duration_ms": DUR})
        with self.assertRaises(Guidance):
            RR.plan(self.p)
        ws = words(SPEECH)
        ws[6]["end_ms"] = ws[6]["start_ms"]                  # a zero-length «تزيد» inside the cut still counts
        write_json(self.p.p("02_transcription/words.json"), {"words": ws})
        self.spec([[0, 2000], [4000, DUR]])
        self.assertIn(7, RR.plan(self.p)["pieces"][0]["word_ids"])

    def test_minor_nothing_removed_clears_a_stale_clip(self):
        out = self.p.p(RR.OUT_DIR)
        out.mkdir(parents=True)
        (out / "C0001_removed-review.mp4").write_bytes(b"old")
        (out / "removed-review.md").write_text("old", encoding="utf-8")
        self.spec([[0, DUR]])
        RR.render(self.p)
        self.assertEqual(list(out.iterdir()), [])


class TestRender(Project):
    def test_a_source_without_sound(self):
        ff = common.ffmpeg_exe()
        src = self.root / "data/Raw/CLIP1.mov"
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=25:d=12",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
        self.spec([[0, 2000], [4000, DUR]])
        res = RR.render(self.p)
        self.assertTrue(Path(res["clip"]).is_file())

    def test_arabic_path_and_spaces(self):
        ff = common.ffmpeg_exe()
        src = self.root / "data/Raw/CLIP1.mov"
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=216x384:r=25:d=12",
                        "-f", "lavfi", "-i", "sine=f=440:r=48000:d=12", "-ac", "2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(src)], check=True)
        self.spec([[0, 2000], [4000, 11000]])
        res = RR.render(self.p)
        self.assertTrue(res["clip"])
        out = Path(res["clip"])
        self.assertTrue(out.is_file())
        self.assertIn(self.ROOT_NAME, str(out))
        from lib.media import probe
        got = probe(out)["duration_s"]
        self.assertAlmostEqual(got, RR.duration_s(RR.plan(self.p)["pieces"]), delta=0.25)
        self.assertTrue(Path(res["sheet"]).is_file())
        self.assertFalse(any(Path(res["clip"]).parent.glob("pieces*")))     # the per-piece files are gone


if __name__ == "__main__":
    unittest.main()
