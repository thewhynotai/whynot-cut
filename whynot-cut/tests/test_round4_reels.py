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


class TestEvidenceDidYouMean(unittest.TestCase):
    """G64: the analyst wrote evidence from the machine transcript, then `transcript-correct` changed words; the
    reels-plan error must show the CURRENT words at that time so the fix is a copy-paste."""

    @classmethod
    def setUpClass(cls):
        from lib.episode import EpisodePaths
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp / "C"
        (cls.root / "assets").mkdir(parents=True)
        (cls.root / "data").mkdir()
        cls.ep = EpisodePaths(cls.root, "EP12")
        cls.words = synthetic_episode_transcript(cls.ep)           # the machine transcript (what the analyst read)
        write_json(cls.ep.p("00_inputs/episode.json"), {"episode_id": "EP12", "duration_ms": 121000, "sheet": {}})
        # the analyst's candidate: words 39..149; evidence/end_evidence copied from the machine transcript
        cls.cand = cand(cls.words, 39, 149)
        # then the transcript-editor corrects words (ids are index + 1): the 2nd evidence word, and the last-but-one
        write_json(cls.ep.p("02_transcription/transcript-corrections.json"), {"corrections": [
            {"word_id": 41, "from": "كلمه40", "to": "الشركة الكبرى", "reason": "misheard", "confidence": "high"},
            {"word_id": 149, "from": "كلمه148", "to": "٣", "reason": "digit", "confidence": "high"}]})
        from lib.transcribe import apply_corrections
        apply_corrections(cls.ep)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_plan(self, **kw):
        from lib.reels import compile_reels_plan
        write_json(self.ep.p("01_analysis/reels-plan.json"), {"episode_id": "EP12", "candidates": [dict(self.cand, **kw)]})
        return compile_reels_plan(self.ep)

    def did_you_mean(self, errors, key):
        e = next(x for x in errors if f": {key} not found" in x)
        m = re.search(r"did you mean: «(.+?)»", e)
        self.assertIsNotNone(m, e)
        return e, m.group(1)

    def test_the_fixture_really_corrected_the_words(self):
        cur = read_json(self.ep.p("02_transcription/words.json"))["words"]
        self.assertEqual(cur[40]["word"], "الشركة الكبرى")
        self.assertEqual(self.words[40]["word"], "كلمه40")            # the analyst read the old one

    def test_stale_start_evidence_shows_the_corrected_words(self):
        r = self.run_plan()
        self.assertFalse(r["ok"])
        e, maybe = self.did_you_mean(r["errors"], "evidence")
        self.assertIn("R01", e)
        self.assertIn(self.words[39]["word"] + " الشركة الكبرى", maybe)    # the corrected 2nd word, in place
        self.assertEqual(maybe.split()[0], self.words[39]["word"])         # starts where the candidate starts
        self.assertEqual(len(maybe.split()), 4)                            # 3 quoted words, one became two

    def test_stale_end_evidence_shows_the_corrected_words(self):
        r = self.run_plan()
        e, maybe = self.did_you_mean(r["errors"], "end_evidence")
        self.assertTrue(maybe.endswith(self.words[149]["word"]), maybe)    # ends where the candidate ends
        self.assertIn("٣", maybe)                                          # verbatim, not normalised

    def test_the_suggestion_is_a_mechanical_fix(self):
        r = self.run_plan()
        _, start = self.did_you_mean(r["errors"], "evidence")
        _, end = self.did_you_mean(r["errors"], "end_evidence")
        r = self.run_plan(evidence=start, end_evidence=end)
        self.assertTrue(r["ok"], r["errors"])

    def test_the_quote_is_still_listed(self):
        e, _ = self.did_you_mean(self.run_plan()["errors"], "evidence")
        self.assertIn(self.cand["evidence"], e)
        self.assertIn("not found verbatim", e)

    def test_evidence_in_the_wrong_place_also_gets_the_current_words(self):
        r = self.run_plan(evidence="كلام مش موجود خالص بالمرة")
        e, maybe = self.did_you_mean(r["errors"], "evidence")
        self.assertEqual(len(maybe.split()), 6)                            # 5 words like the quote; one became two
        self.assertIn("الشركة الكبرى", maybe)
        self.assertEqual(maybe.split()[0], self.words[39]["word"])

    def test_matching_evidence_has_no_error_and_folding_still_applies(self):
        good = "كلمه39 الشركه الكبري"                                      # corrected words, written with ta marbuta/ya
        r = self.run_plan(evidence=good, end_evidence=" ".join(
            w["word"] for w in read_json(self.ep.p("02_transcription/words.json"))["words"][147:150]).replace("٣", "3"))
        self.assertTrue(r["ok"], r["errors"])

    def test_no_words_gives_no_suggestion(self):
        from lib.reels import current_words_at
        self.assertEqual(current_words_at([], 1000, "start", 4), "")

    def test_cli_reels_plan_prints_the_suggestion(self):
        write_json(self.ep.p("01_analysis/reels-plan.json"), {"episode_id": "EP12", "candidates": [self.cand]})
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(self.root), "reels-plan",
                            "--episode", "EP12"], capture_output=True, text=True, encoding="utf-8",
                           env=dict(os.environ, PYTHONUTF8="1"))
        out = json.loads(r.stdout)
        self.assertFalse(out["ok"])
        self.assertTrue(any("did you mean: «" in e and "الشركة الكبرى" in e for e in out["errors"]), out["errors"])

    def test_the_analyst_docs_say_to_copy_the_suggestion(self):
        for rel in ("agents/episode-analyst.md", "skills/episode-craft/SKILL.md"):
            self.assertIn("did you mean", (SK / rel).read_text(encoding="utf-8"), rel)


def _agent_tools(f: Path) -> list:
    head = f.read_text(encoding="utf-8").split("---")[1]
    line = next((ln for ln in head.splitlines() if ln.startswith("tools:")), "tools:")
    return [t.strip() for t in line.split(":", 1)[1].split(",")]


class TestEngineVenvPython(unittest.TestCase):
    """G67: `python -I` with the engine venv loses site-packages on Windows (PIL/av/numpy not found). The docs and every
    agent that can run Bash say: engine-side scripts run with the venv python WITHOUT -I."""

    MARK = "without `-I`"

    def user_site(self, *flags) -> str:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONNOUSERSITE", "PYTHONHOME", "PYTHONPATH")}
        r = subprocess.run([sys.executable, *flags, "-c", "import site; print(bool(site.ENABLE_USER_SITE))"],
                           capture_output=True, text=True, env=env)
        return r.stdout.strip()

    def test_isolation_flags_behave_as_the_docs_claim(self):
        plain = self.user_site()
        self.assertEqual(self.user_site("-E"), plain)                  # -E alone keeps the user site-packages
        self.assertEqual(self.user_site("-I"), "False")                # -I switches it off
        self.assertEqual(self.user_site("-E", "-s"), "False")          # so does -E -s (it is the -s)

    def test_platform_setup_explains_it(self):
        t = (SK / "skills/setup/references/platform-setup.md").read_text(encoding="utf-8")
        self.assertIn(self.MARK, t)
        for must in ("ModuleNotFoundError", "site-packages", "-E -s", "-E` alone", "--system-site-packages",
                     "venv\\Scripts\\python.exe"):
            self.assertIn(must, t)

    def test_troubleshooting_catalog_has_the_symptom(self):
        t = (SK / "skills/edit/references/troubleshooting.md").read_text(encoding="utf-8")
        row = next((ln for ln in t.splitlines() if "ModuleNotFoundError" in ln and "-I" in ln), "")
        self.assertIn(self.MARK, row)
        self.assertIn("PIL", row)

    def test_every_agent_with_bash_says_it(self):
        agents = [f for f in sorted((SK / "agents").glob("*.md")) if "Bash" in _agent_tools(f)]
        self.assertGreaterEqual(len(agents), 12)
        for f in agents:
            t = f.read_text(encoding="utf-8")
            self.assertIn(self.MARK, t, f.name)
            self.assertIn("platform-setup.md", t, f.name)
            self.assertLess(t.index(self.MARK), t.index("## When to invoke"), f.name)   # near the top, not buried

    def test_no_doc_tells_agents_to_use_dash_I_with_the_engine_python(self):
        bad = re.compile(r"venv[\\/](?:bin|Scripts)[\\/]python(?:\.exe)?[\"']?\s+-I\b")
        for f in list((SK / "skills").rglob("*.md")) + list((SK / "agents").glob("*.md")):
            self.assertIsNone(bad.search(f.read_text(encoding="utf-8")), f.name)


if __name__ == "__main__":
    unittest.main()
