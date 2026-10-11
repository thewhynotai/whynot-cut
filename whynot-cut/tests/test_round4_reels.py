"""Round-4 field-test gaps in podcast reels (2.2.x): G63 explicit --adjust snaps to WORD boundaries, G64 reels-plan
evidence errors show the corrected transcript words, G67 engine-side Python must not run with `-I`. Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_round4_reels.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import common  # noqa: E402
from lib.common import Paths, write_json, read_json  # noqa: E402
from test_podcast import (cand, make_episode_client, synthetic_episode_transcript,  # noqa: E402
                          validated_plan)

SNAP = {"snap": {"search_ms": 1500, "lead_in_ms": 120, "tail_ms": 250, "gap_ms": 300}}
GAPS = {10: 600, 20: 1500, 31: 600}      # extra silence before word i, on top of the 400 ms stride (words are 250 ms long)


def adjust_words(n: int = 40) -> list:
    """Words of 250 ms every 400 ms. Silences before word 10 («طيب», a sentence-like start), word 20 (1.5 s) and word 31
    (so word 30 ends a sentence-like stretch). Word k starts at k*400 + the gaps up to k."""
    out = []
    for i in range(n):
        s = i * 400 + sum(g for k, g in GAPS.items() if i >= k)
        out.append({"id": i + 1, "segment_id": 1, "word": "طيب" if i == 10 else f"كلمه{i}", "start_ms": s,
                    "end_ms": s + 250, "probability": 0.9})
    return out


class TestExplicitAdjustSnapsToWords(unittest.TestCase):
    """G63: `reels-select --adjust Rxx:in=<t>` is the editor's own choice; it snaps to the nearest WORD start (lead-in
    kept), not to a sentence-like start up to 1.5 s away. The sentence preference stays for automatic windows."""

    def setUp(self):
        from lib.episode import EpisodePaths, prep
        from lib.transcribe import extract_audio, finalize
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_episode_client(self.tmp)
        write_json(self.root / common.CLIENT_PROFILE_REL / "podcast.json", {"reel_duration_s": {"min": 1, "hard_min": 1}})
        common.set_context(self.root)
        self.ep = EpisodePaths(self.root, "EP12")
        prep(self.ep)
        extract_audio(self.root / "data/Episodes/EP12.mp4", self.ep.p("02_transcription/dialogue_16k_mono.wav"))
        self.words = ws = adjust_words()
        segs = [{"id": 1, "start_ms": ws[0]["start_ms"], "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
                 "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}]
        finalize(self.ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                           "language_probability": 1.0, "duration_ms": 20000}, segs, ws)
        validated_plan(self.ep, [
            {"id": "R01", "in_ms": 2000, "out_ms": 18000, "duration_ms": 16000, "type": "drama", "secondary_type": None,
             "title": "t", "total": 8.0, "score": {}, "avoid_hits": []}])

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def select(self, *adjust):
        from lib.reels import select
        return select(self.ep, ["R01"], list(adjust), "editor")["reels"][0]

    # -- the engine primitive
    def test_words_fixture_has_the_sentence_start_the_bug_snaps_to(self):
        from lib.reels import boundary_words
        starts, ends = boundary_words(self.words, 300)
        self.assertIn(10, starts)                    # «طيب»: after a pause
        self.assertNotIn(13, starts)                 # the word the editor wants
        self.assertIn(30, ends)
        self.assertNotIn(28, ends)

    def test_automatic_in_still_prefers_the_sentence_start(self):
        from lib.reels import snap_in
        w = self.words
        self.assertEqual(snap_in(w, w[13]["start_ms"] + 40, SNAP), w[10]["start_ms"] - 120)

    def test_explicit_in_snaps_to_the_nearest_word_start(self):
        from lib.reels import snap_in
        w = self.words
        self.assertEqual(snap_in(w, w[13]["start_ms"] + 40, SNAP, explicit=True), w[13]["start_ms"] - 120)
        self.assertEqual(snap_in(w, w[13]["start_ms"] - 40, SNAP, explicit=True), w[13]["start_ms"] - 120)
        self.assertEqual(snap_in(w, w[10]["start_ms"], SNAP, explicit=True), w[10]["start_ms"] - 120)

    def test_explicit_in_never_reaches_into_the_previous_word(self):
        from lib.reels import snap_in
        w = self.words
        for k in (5, 13, 25):
            got = snap_in(w, w[k]["start_ms"], SNAP, explicit=True)
            self.assertGreater(got, w[k - 1]["end_ms"])
            self.assertLessEqual(got, w[k]["start_ms"])

    def test_explicit_in_does_not_go_back_to_a_word_that_ended_before_it(self):
        from lib.reels import snap_in
        w = self.words
        t = w[19]["end_ms"] + 100                    # in the 1.5 s silence after word 19: that word is skipped
        self.assertEqual(snap_in(w, t, SNAP, explicit=True), w[20]["start_ms"] - 120)

    def test_explicit_in_inside_a_word_keeps_that_word(self):
        from lib.reels import snap_in
        w = self.words
        self.assertEqual(snap_in(w, w[13]["start_ms"] + 60, SNAP, explicit=True), w[13]["start_ms"] - 120)

    def test_explicit_in_past_the_last_word_uses_the_last_word(self):
        from lib.reels import snap_in
        w = self.words
        self.assertEqual(snap_in(w, w[-1]["end_ms"] + 5000, SNAP, explicit=True), w[-1]["start_ms"] - 120)

    def test_explicit_out_snaps_to_the_nearest_word_end(self):
        from lib.reels import snap_out
        w = self.words
        t = w[28]["end_ms"] + 30
        auto = snap_out(w, t, SNAP, 20000)
        self.assertGreater(auto, w[30]["end_ms"] - 1)              # the automatic window runs on to the sentence end
        got = snap_out(w, t, SNAP, 20000, explicit=True)
        self.assertEqual(got, min(w[28]["end_ms"] + 250, w[29]["start_ms"] - 20))
        self.assertLessEqual(got, w[29]["start_ms"])               # never into the next word

    def test_explicit_out_does_not_run_on_to_a_word_that_starts_after_it(self):
        from lib.reels import snap_out
        w = self.words
        t = w[20]["start_ms"] - 100                  # in the silence before word 20: that word is skipped
        self.assertEqual(snap_out(w, t, SNAP, 20000, explicit=True), w[19]["end_ms"] + 250)

    def test_explicit_out_before_the_first_word_uses_the_first_word(self):
        from lib.reels import snap_out
        self.assertEqual(snap_out(self.words, 0, SNAP, 20000, explicit=True),
                         min(self.words[0]["end_ms"] + 250, self.words[1]["start_ms"] - 20))

    # -- through `reels-select --adjust`
    def test_select_adjust_in_skips_the_word(self):
        w = self.words
        r = self.select(f"R01:in={w[13]['start_ms'] / 1000:.3f}")           # «طيب» (word 10) sits 1.2 s earlier
        self.assertEqual(r["in_ms"], w[13]["start_ms"] - 120)
        reel = Paths(self.root, "EP12_R01")
        self.assertEqual(read_json(reel.p("00_inputs/source.json"))["in_ms"], w[13]["start_ms"] - 120)
        first = read_json(reel.p("02_transcription/words.json"))["words"][0]
        self.assertEqual(first["word"], "كلمه13")                           # the reel opens on the chosen word

    def test_select_adjust_out_ends_on_the_chosen_word(self):
        w = self.words
        r = self.select(f"R01:out={(w[28]['end_ms'] + 30) / 1000:.3f}")
        self.assertEqual(r["out_ms"], min(w[28]["end_ms"] + 250, w[29]["start_ms"] - 20))
        last = read_json(Paths(self.root, "EP12_R01").p("02_transcription/words.json"))["words"][-1]
        self.assertEqual(last["word"], "كلمه28")

    def test_select_without_adjust_keeps_the_plan_window(self):
        r = self.select()
        self.assertEqual((r["in_ms"], r["out_ms"]), (2000, 18000))          # untouched plan windows are not re-snapped

    def test_adjust_still_checks_the_duration_limits(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "podcast.json", {"reel_duration_s": {"min": 1, "hard_min": 20}})
        with self.assertRaises(SystemExit) as cm:
            self.select("R01:in=12.0")
        self.assertIn("adjusted duration", str(cm.exception))

    def test_podcast_skill_tells_the_lead_adjust_is_word_exact(self):
        pod = (SK / "skills/podcast/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("nearest WORD", pod)
        self.assertIn("never", pod.split("nearest WORD", 1)[1][:400])


if __name__ == "__main__":
    unittest.main()
