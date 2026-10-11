"""Podcast mode (2.1): episode intake, chunked transcription, reels plan, Gate 0, source window, per-shot reframe,
recipes, publish package. Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_podcast.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json, read_json  # noqa: E402

SHEET = """---
show: بودكاست التجربة
episode: 12
host: "Ahmed"
guest: "Sara — CEO"
links:
  - https://www.instagram.com/sara.ceo/
avoid: [السياسة, دين]
language: ar
---
Notes about the episode.
"""


def ff(*args):
    subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", *args], check=True)


def make_episode_client(tmp: Path, dur_s: float = 20, fps: int = 25, size: str = "1280x720", name: str = "EP12.mp4",
                        with_clip: bool = True) -> Path:
    """Client folder with data/Episodes/<name> (16:9 testsrc2 + sine), its sheet and (optionally) a Raw clip."""
    root = tmp / "PODCLIENT"
    for d in ("assets/Brand", "assets/Logo", "data/Episodes", "data/Raw"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "assets/Brand/brief.md").write_text("# Brand\nPrimary #20ACAF and #FFFFFF\n", encoding="utf-8")
    ff("-f", "lavfi", "-i", f"testsrc2=s={size}:r={fps}:d={dur_s}", "-f", "lavfi", "-i", f"sine=f=440:r=48000:d={dur_s}",
       "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(root / "data/Episodes" / name))
    (root / "data/Episodes" / (Path(name).stem + ".md")).write_text(SHEET, encoding="utf-8")
    if with_clip:
        ff("-f", "lavfi", "-i", "testsrc2=s=216x384:r=25:d=3", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=3",
           "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest",
           str(root / "data/Raw/CLIP1.mov"))
    return root


class TestEpisodeIntake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = make_episode_client(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_parse_sheet(self):
        from lib.episode import parse_sheet
        s = parse_sheet("---\nguest: \"Sara — CEO\"\nlinks:\n  - https://a.com/x\navoid: [السياسة, دين]\n---\nnotes")
        self.assertEqual(s["guest"], "Sara — CEO")
        self.assertEqual(s["links"], ["https://a.com/x"])
        self.assertEqual(s["avoid"], ["السياسة", "دين"])
        self.assertIn("notes", s["_notes"])
        self.assertIn("https://a.com/x", s["_text"])

    def test_discover_roles(self):
        from lib.discover import run_discovery
        inv = run_discovery(Paths(self.root))["inventory"]
        roles = {f["rel"]: f["role"] for f in inv["files"]}
        self.assertEqual(roles["data/Episodes/EP12.mp4"], "episode")
        self.assertEqual(roles["data/Episodes/EP12.md"], "episode_sheet")
        self.assertEqual(roles["data/Raw/CLIP1.mov"], "source_footage")

    def test_episode_ids_unique_for_arabic_names(self):
        from lib.episode import episode_id_for
        a, b = episode_id_for(Path("حلقة 12.mp4")), episode_id_for(Path("الحلقة.mov"))
        self.assertNotEqual(a, b)
        self.assertEqual(a, episode_id_for(Path("حلقة 12.mp4")))
        for x in (a, b):
            self.assertRegex(x, r"^[A-Z0-9_]+$")
        self.assertEqual(episode_id_for(Path("EP12.mp4")), "EP12")

    def test_list_and_prep(self):
        from lib.episode import EpisodePaths, list_episodes, prep
        eps = list_episodes(self.root)
        self.assertEqual([e["episode_id"] for e in eps], ["EP12"])
        self.assertEqual(eps[0]["state"], "new")
        self.assertEqual(eps[0]["sheet"], "data/Episodes/EP12.md")
        ep = EpisodePaths(self.root, "EP12")
        r = prep(ep)
        info = read_json(ep.p("00_inputs/episode.json"))
        self.assertAlmostEqual(info["duration_ms"], 20000, delta=100)
        self.assertEqual(info["sheet"]["guest"], "Sara — CEO")
        frames = sorted(ep.p("00_inputs/intake").glob("frame_0*.jpg"))
        self.assertEqual(len(frames), 6)
        self.assertTrue(ep.p("00_inputs/intake/_intake_sheet.jpg").exists())
        self.assertGreater(r["estimate_minutes"]["cpu"], r["estimate_minutes"]["gpu"])
        self.assertEqual(list_episodes(self.root)[0]["state"], "prepared")

    def test_cli_episode_commands(self):
        cli = SK / "engine/reel/cli.py"
        own = make_episode_client(Path(tempfile.mkdtemp(dir=self.tmp)), dur_s=6, with_clip=False)   # isolated state
        r = subprocess.run([sys.executable, "-B", str(cli), "--root", str(own), "episode-prep"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual(json.loads(r.stdout)["episode_id"], "EP12")      # the only episode is picked automatically
        r = subprocess.run([sys.executable, "-B", str(cli), "episodes", "--root", str(own)],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(r.stdout)["episodes"][0]["state"], "prepared")

    def test_inbox_lists_episodes(self):
        from lib.onboard import inbox
        r = inbox(self.root)
        self.assertEqual(r["episodes"][0]["episode_id"], "EP12")
        self.assertEqual([c["video_id"] for c in r["clips"]], ["CLIP1"])


class TestChunkedTranscription(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = make_episode_client(cls.tmp, with_clip=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_plan_chunks_cuts_in_silence(self):
        from lib.episode import plan_chunks
        hop = 50
        db = [-20.0] * (1_500_000 // hop)
        for i in range(590_000 // hop, 592_000 // hop):
            db[i] = -80.0
        db[1_210_000 // hop] = -80.0
        ch = plan_chunks(db, hop, 1_500_000, 600_000)
        self.assertEqual(len(ch), 3)
        self.assertLessEqual(abs(ch[0][1] - 591_000), 1000)
        self.assertLessEqual(abs(ch[1][1] - 1_210_000), 1000)
        self.assertEqual(ch[0][0], 0)
        self.assertEqual(ch[-1][1], 1_500_000)
        for a, b in zip(ch, ch[1:]):
            self.assertEqual(a[1], b[0])

    def test_plan_chunks_short_audio(self):
        from lib.episode import plan_chunks
        self.assertEqual(plan_chunks([-20.0] * 6000, 50, 300_000, 600_000), [(0, 300_000)])

    def test_stitch_renumbers(self):
        from lib.episode import stitch
        def chunk(a, words):
            ws = [{"id": i + 1, "segment_id": 1, "word": w, "start_ms": a + i * 500, "end_ms": a + i * 500 + 400,
                   "probability": 0.9} for i, w in enumerate(words)]
            return {"start_ms": a, "end_ms": a + 2000, "language": "ar",
                    "segments": [{"id": 1, "start_ms": a, "end_ms": a + 900, "text": " ".join(words), "avg_logprob": -0.2,
                                  "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1, 2]}], "words": ws}
        segs, words = stitch([chunk(0, ["أهلا", "بيك"]), chunk(2000, ["في", "الحلقة"])])
        self.assertEqual([w["id"] for w in words], [1, 2, 3, 4])
        self.assertEqual([s["id"] for s in segs], [1, 2])
        self.assertEqual([w["segment_id"] for w in words], [1, 1, 2, 2])
        self.assertEqual(segs[1]["words"], [3, 4])
        self.assertEqual(words[2]["start_ms"], 2000)

    def test_resume_skips_done_chunks(self):
        from lib.episode import EpisodePaths, transcribe_episode
        calls = []

        def fake(audio, start_ms, language, prompt):
            calls.append({"start_ms": start_ms, "language": language, "samples": len(audio)})
            return {"language": "ar", "language_probability": 0.97,
                    "segments": [{"id": 1, "start_ms": 100, "end_ms": 900, "text": "كلام تجربة", "avg_logprob": -0.2,
                                  "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1, 2]}],
                    "words": [{"id": 1, "segment_id": 1, "word": "كلام", "start_ms": 100, "end_ms": 500, "probability": 0.9},
                              {"id": 2, "segment_id": 1, "word": "تجربة", "start_ms": 600, "end_ms": 900, "probability": 0.9}]}
        ep = EpisodePaths(self.root, "EP12")
        r = transcribe_episode(ep, "small", run_chunk=fake, chunk_ms=8000)
        self.assertEqual(len(calls), 3)
        self.assertIsNone(calls[0]["language"])
        self.assertEqual(calls[1]["language"], "ar")                    # detected once, reused
        tj = read_json(ep.p("02_transcription/transcript.json"))
        self.assertEqual(tj["meta"]["chunks"], 3)
        self.assertTrue(tj["meta"]["vad"])
        self.assertEqual(len(tj["segments"]), 3)
        self.assertEqual(tj["segments"][1]["start_ms"], calls[1]["start_ms"] + 100)   # times made absolute
        self.assertTrue(ep.p("02_transcription/words.machine.json").exists())
        self.assertEqual(r["chunks_run"], 3)
        ep.p("02_transcription/chunks/chunk_001.json").unlink()
        calls.clear()
        r = transcribe_episode(ep, "small", run_chunk=fake, chunk_ms=8000)
        self.assertEqual([c["start_ms"] for c in calls], [read_json(ep.p("02_transcription/chunks/chunk_001.json"))["start_ms"]])
        self.assertEqual(r["chunks_run"], 1)
        calls.clear()
        transcribe_episode(ep, "small", run_chunk=fake, chunk_ms=8000, force=True)
        self.assertEqual(len(calls), 3)
        # the clip transcript commands work on the episode project with --episode
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(self.root), "--episode",
                            "EP12", "transcript-verify", "--by", "editor"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-600:])
        self.assertTrue(read_json(ep.p("02_transcription/verification.json"))["verified"])


def synthetic_episode_transcript(ep, n=300, gap_at=39, total_ms=121000):
    """Words every 400 ms (360 ms long); +600 ms gap before word index gap_at; word gap_at-1 ends with '؟';
    segments: [0, gap_at-1], [gap_at, 149], [150, n-1]. A known phrase at 50-53 and 'السياسة' at 80."""
    from lib.transcribe import finalize
    special = {50: "انا", 51: "قلت", 52: "ان", 53: "الشركه", 80: "السياسة"}
    words = []
    for i in range(n):
        s = i * 400 + (600 if i >= gap_at else 0)
        w = special.get(i, f"كلمه{i}") + ("؟" if i == gap_at - 1 else "")
        words.append({"id": i + 1, "segment_id": 1 if i < gap_at else (2 if i < 150 else 3), "word": w,
                      "start_ms": s, "end_ms": s + 360, "probability": 0.95})
    segs = []
    for sid, (a, b) in enumerate(((0, gap_at - 1), (gap_at, 149), (150, n - 1)), 1):
        ws = words[a:b + 1]
        segs.append({"id": sid, "start_ms": ws[0]["start_ms"], "end_ms": ws[-1]["end_ms"],
                     "text": " ".join(w["word"] for w in ws), "avg_logprob": -0.2, "no_speech_prob": 0.0,
                     "compression_ratio": 1.2, "words": [w["id"] for w in ws]})
    ep.ensure_project()
    finalize(ep, {"source_video": "x.mp4", "backend": "test", "model": "none", "language": "ar",
                  "language_probability": 1.0, "duration_ms": total_ms}, segs, words)
    return words


def cand(words, i0, i1, cid="R01", **kw):
    from lib.common import fmt_ts
    c = {"id": cid, "start": fmt_ts(words[i0]["start_ms"] - 50, "."), "end": fmt_ts(words[i1]["end_ms"] + 40, "."),
         "type": "success_story", "title": "t", "hook_quote": words[i0]["word"], "hook_text": "h",
         "evidence": " ".join(w["word"] for w in words[i0:i0 + 3]),
         "end_evidence": " ".join(w["word"] for w in words[i1 - 2:i1 + 1]),
         "why": "w", "score": {"hook": 8, "standalone": 7, "payoff": 9, "ending": 8},
         "needs_context": False, "context_line": "", "speakers": [], "risks": []}
    c.update(kw)
    return c


class TestReelsPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from lib.episode import EpisodePaths
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp / "C"
        (cls.root / "assets").mkdir(parents=True)
        (cls.root / "data").mkdir()
        cls.ep = EpisodePaths(cls.root, "EP12")
        cls.words = synthetic_episode_transcript(cls.ep)
        write_json(cls.ep.p("00_inputs/episode.json"), {"episode_id": "EP12", "duration_ms": 121000,
                                                         "sheet": {"avoid": ["السياسه"]}})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_plan(self, cands):
        from lib.reels import compile_reels_plan
        write_json(self.ep.p("01_analysis/reels-plan.json"), {"episode_id": "EP12", "candidates": cands})
        return compile_reels_plan(self.ep)

    def test_valid_candidate_snaps_to_sentence(self):
        w = self.words
        c = cand(w, 39, 149, start=None, end=None)
        from lib.common import fmt_ts
        c["start"] = fmt_ts(w[39]["start_ms"] - 1100, ".")            # 1.1 s early, inside the previous sentence
        c["end"] = fmt_ts(w[149]["end_ms"] + 140, ".")
        r = self.run_plan([c])
        self.assertTrue(r["ok"], r["errors"])
        got = r["candidates"][0]
        self.assertEqual(got["in_ms"], w[39]["start_ms"] - 120)
        self.assertEqual(got["out_ms"], min(w[149]["end_ms"] + 250, w[150]["start_ms"] - 20))
        self.assertEqual(got["duration_ms"], got["out_ms"] - got["in_ms"])
        self.assertTrue(self.ep.p("01_analysis/reels-plan-validated.json").exists())

    def test_evidence_variants_match(self):
        from lib.reels import find_evidence
        self.assertTrue(find_evidence(self.words, "أنا قلت إن الشركة", self.words[50]["start_ms"], 3000))
        self.assertFalse(find_evidence(self.words, "أنا قلت إن الشركة", self.words[50]["start_ms"] + 20000, 3000))

    def test_evidence_missing_is_error(self):
        r = self.run_plan([cand(self.words, 39, 149, evidence="كلام مش موجود خالص")])
        self.assertFalse(r["ok"])
        self.assertTrue(any("evidence" in e for e in r["errors"]))

    def test_edges_clamped(self):
        w = self.words
        c = cand(w, 0, 299, start="00:00:00.000")
        c["end"] = "00:02:00.900"
        r = self.run_plan([c])
        self.assertTrue(r["ok"], r["errors"])
        got = r["candidates"][0]
        self.assertEqual(got["in_ms"], 0)
        self.assertLessEqual(got["out_ms"], 121000)
        self.assertLess(got["in_ms"], got["out_ms"])

    def test_duration_limits(self):
        r = self.run_plan([cand(self.words, 39, 88)])                    # ~20 s
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("R01" in x and "duration" in x for x in r["warnings"]))
        r = self.run_plan([cand(self.words, 39, 62)])                    # ~10 s
        self.assertFalse(r["ok"])
        self.assertTrue(any("duration" in e for e in r["errors"]))

    def test_unknown_type_error(self):
        r = self.run_plan([cand(self.words, 39, 149, type="documentary")])
        self.assertTrue(any("type" in e for e in r["errors"]))

    def test_overlap_warning(self):
        r = self.run_plan([cand(self.words, 39, 149), cand(self.words, 45, 149, cid="R02")])
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("overlap" in x and "R01" in x and "R02" in x for x in r["warnings"]))

    def test_avoid_hit_flagged(self):
        r = self.run_plan([cand(self.words, 39, 149)])
        self.assertEqual(r["candidates"][0]["avoid_hits"], ["السياسه"])

    def test_total_and_sort(self):
        lo = cand(self.words, 150, 260, cid="R02", score={"hook": 5, "standalone": 5, "payoff": 6, "ending": 6})
        r = self.run_plan([lo, cand(self.words, 39, 149)])
        self.assertEqual([c["id"] for c in r["candidates"]], ["R01", "R02"])
        self.assertEqual(r["candidates"][0]["total"], 8.0)
        md = self.ep.p("01_analysis/reels-plan.md").read_text(encoding="utf-8")
        self.assertLess(md.index("| R01 |"), md.index("| R02 |"))

    def test_fingerprint_changes_with_words(self):
        from lib.reels import reels_plan_fingerprint
        self.run_plan([cand(self.words, 39, 149)])
        a = reels_plan_fingerprint(self.ep)
        wj = self.ep.p("02_transcription/words.json")
        original = wj.read_bytes()
        try:
            wj.write_bytes(original + b"\n")
            self.assertNotEqual(a, reels_plan_fingerprint(self.ep))
        finally:
            wj.write_bytes(original)


def validated_plan(ep, cands: list):
    """Write a reels-plan.json + a matching (fresh) reels-plan-validated.json without running the validator."""
    from lib.reels import reels_plan_fingerprint
    write_json(ep.p("01_analysis/reels-plan.json"), {"episode_id": ep.episode_id, "candidates": cands})
    write_json(ep.p("01_analysis/reels-plan-validated.json"), {
        "episode_id": ep.episode_id, "ok": True, "errors": [], "warnings": [], "duration_ms": 20000,
        "fingerprint": reels_plan_fingerprint(ep), "candidates": cands})


class TestReelsPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from lib.episode import EpisodePaths, prep
        from lib.transcribe import finalize
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = make_episode_client(cls.tmp, with_clip=False)
        cls.ep = EpisodePaths(cls.root, "EP12")
        prep(cls.ep)
        ws = [{"id": i + 1, "segment_id": 1, "word": f"كلمه{i}", "start_ms": i * 500, "end_ms": i * 500 + 400,
               "probability": 0.9} for i in range(38)]
        finalize(cls.ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                          "language_probability": 1.0, "duration_ms": 20000},
                 [{"id": 1, "start_ms": 0, "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
                   "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}], ws)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_previews_rendered(self):
        from lib.reels import render_candidates
        from lib.media import probe
        validated_plan(self.ep, [{"id": "R01", "in_ms": 2000, "out_ms": 6000, "duration_ms": 4000, "type": "advice",
                                  "type_label": "نصيحة", "total": 7.5, "title": "t", "score": {}}])
        r = render_candidates(self.ep)
        self.assertTrue(r["ok"], r)
        mp4 = self.ep.p("03_candidates/R01.mp4")
        pr = probe(mp4)
        self.assertEqual((pr["video"]["display_width"], pr["video"]["display_height"]), (540, 960))
        self.assertTrue(4.0 <= pr["duration_s"] <= 4.6, pr["duration_s"])
        self.assertTrue(pr["audio"])
        self.assertTrue(self.ep.p("03_candidates/R01.jpg").exists())
        self.assertTrue(self.ep.p("03_candidates/_sheet.jpg").exists())
        self.assertIn("R01.mp4", self.ep.p("01_analysis/reels-plan.md").read_text(encoding="utf-8"))

    def test_stale_plan_refused(self):
        from lib.reels import render_candidates
        validated_plan(self.ep, [{"id": "R01", "in_ms": 2000, "out_ms": 6000, "duration_ms": 4000, "type": "advice",
                                  "total": 7.5, "score": {}}])
        write_json(self.ep.p("01_analysis/reels-plan.json"), {"episode_id": "EP12", "candidates": [{"id": "R09"}]})
        with self.assertRaises(SystemExit):
            render_candidates(self.ep)


GUARD = SK / "hooks" / "guard.py"


def run_guard(command: str, agent: str | None = None, cwd: str = ".") -> int:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    if agent:
        payload["agent_type"] = agent
    return subprocess.run([sys.executable, "-B", str(GUARD)], input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8").returncode


class TestReelsSelect(unittest.TestCase):
    def setUp(self):
        from lib.episode import EpisodePaths, prep
        from lib.transcribe import extract_audio, finalize
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_episode_client(self.tmp)
        # a 20 s fixture episode: the client's profile override allows short reels (exercises the override path too)
        write_json(self.root / common.CLIENT_PROFILE_REL / "podcast.json", {"reel_duration_s": {"min": 1, "hard_min": 1}})
        common.set_context(self.root)
        self.ep = EpisodePaths(self.root, "EP12")
        prep(self.ep)
        extract_audio(self.root / "data/Episodes/EP12.mp4", self.ep.p("02_transcription/dialogue_16k_mono.wav"))
        ws = []
        for i in range(48):
            s = i * 400 + (300 if i >= 25 else 0)
            ws.append({"id": i + 1, "segment_id": 1 if i < 25 else 2, "word": "السياسة" if i == 40 else f"كلمه{i}",
                       "start_ms": s, "end_ms": s + 360, "probability": 0.9})
        ws[7]["flagged"] = {"note": "unclear", "suggest": None}
        segs = [{"id": k + 1, "start_ms": g[0]["start_ms"], "end_ms": g[-1]["end_ms"], "text": " ".join(w["word"] for w in g),
                 "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in g]}
                for k, g in enumerate((ws[:25], ws[25:]))]
        finalize(self.ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                           "language_probability": 1.0, "duration_ms": 20000}, segs, ws)
        self.words = ws
        write_json(self.ep.p("01_analysis/speakers.json"), {
            "method": "inferred", "people": {"host": {"name": "Ahmed", "position": "left"},
                                             "guest": {"name": "Sara", "position": "right"}},
            "turns": [{"start": "00:00:00.000", "end": "00:00:05.000", "speaker": "host"},
                      {"start": "00:00:05.000", "end": "00:00:20.000", "speaker": "guest"}]})
        write_json(self.ep.p("00_inputs/intake.json"), {"burned_subtitles": False, "layout": {"host": "left", "guest": "right"}})
        validated_plan(self.ep, [
            {"id": "R01", "in_ms": 2000, "out_ms": 9000, "duration_ms": 7000, "type": "drama", "secondary_type": None,
             "title": "Sara's first loss", "total": 8.0, "score": {}, "avoid_hits": [], "needs_context": True,
             "context_line": "she lost her first company"},
            {"id": "R02", "in_ms": 12000, "out_ms": 19000, "duration_ms": 7000, "type": "advice", "title": "x",
             "total": 6.0, "score": {}, "avoid_hits": ["السياسه"]}])

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def select(self, *picks, **kw):
        from lib.reels import select
        return select(self.ep, list(picks), kw.pop("adjust", []), kw.pop("by", "editor"), **kw)

    def test_select_creates_reel_project(self):
        import wave
        r = self.select("R01")
        self.assertEqual(r["reels"][0]["reel_id"], "EP12_R01")
        self.assertEqual(r["reels"][0]["status"], "created")
        reel = Paths(self.root, "EP12_R01")
        src = read_json(reel.p("00_inputs/source.json"))
        self.assertEqual((src["in_ms"], src["out_ms"], src["duration_ms"]), (2000, 9000, 7000))
        self.assertEqual(src["footage"], "data/Episodes/EP12.mp4")
        self.assertEqual((src["kind"], src["episode_id"], src["reel_id"], src["content_type"]),
                         ("episode_reel", "EP12", "R01", "drama"))
        self.assertEqual(src["recipe"]["pacing"]["min_pause_ms"], 600)
        self.assertEqual(src["intake"]["layout"]["guest"], "right")
        self.assertEqual(common.source_range(reel)["in_ms"], 2000)            # the shared range mechanism reads it
        w = read_json(reel.p("02_transcription/words.json"))["words"]
        self.assertEqual(w[0]["id"], 1)
        self.assertEqual(w[0]["start_ms"], 0)                                  # word at 2000 ms -> 0 on the reel clock
        self.assertEqual(w[0]["episode_word_id"], 6)
        tj = read_json(reel.p("02_transcription/transcript.json"))
        self.assertEqual(tj["meta"]["duration_ms"], 7000)
        self.assertEqual(len(tj["segments"]), 1)
        with wave.open(str(reel.p("02_transcription/dialogue_16k_mono.wav"))) as wf:
            self.assertLessEqual(abs(wf.getnframes() - 7000 * 16), 1)
        sp = read_json(reel.p("00_inputs/speakers.json"))
        self.assertEqual(sp["turns"][0], {"start_ms": 0, "end_ms": 3000, "speaker": "host"})
        self.assertEqual(sp["turns"][1]["speaker"], "guest")
        self.assertEqual(common.load_status(reel)["status"], "TRANSCRIBED")
        sel = read_json(self.ep.p("01_analysis/selection.json"))
        self.assertEqual(sel["history"][-1]["picked"], ["R01"])
        self.assertEqual(sel["history"][-1]["by"], "editor")

    def test_flags_and_verification_carry(self):
        from lib.transcribe import words_fingerprint
        self.select("R01")
        reel = Paths(self.root, "EP12_R01")
        w = read_json(reel.p("02_transcription/words.json"))["words"]
        self.assertTrue(any(x.get("flagged") for x in w))
        write_json(self.ep.p("02_transcription/verification.json"),
                   {"verified": True, "by": "editor", "words_sha1": words_fingerprint(self.ep)})
        self.select(resync=True)
        v = read_json(reel.p("02_transcription/verification.json"))
        self.assertTrue(v["verified"])
        self.assertEqual(v["words_sha1"], words_fingerprint(reel))

    def test_reselect_noop_and_force(self):
        self.select("R01")
        self.assertEqual(self.select("R01")["reels"][0]["status"], "unchanged")
        with self.assertRaises(SystemExit):
            self.select("R01", adjust=["R01:in=00:00:03.000"])
        r = self.select("R01", adjust=["R01:in=00:00:03.000"], force=True)
        self.assertEqual(r["reels"][0]["status"], "re-sliced")
        self.assertLessEqual(abs(r["reels"][0]["in_ms"] - 3000), 400)

    def test_avoid_requires_confirm(self):
        with self.assertRaises(SystemExit):
            self.select("R02")
        self.assertEqual(self.select("R02", confirm_avoid=["R02"])["reels"][0]["status"], "created")

    def test_stale_plan_refused(self):
        write_json(self.ep.p("01_analysis/reels-plan.json"), {"episode_id": "EP12", "candidates": []})
        with self.assertRaises(SystemExit):
            self.select("R01")

    def test_window_plain_clip(self):
        self.assertEqual(common.source_range(Paths(self.root, "CLIP1")), {})

    def test_changed_episode_refused(self):
        from lib.reels import window_stale
        self.select("R01")
        reel = Paths(self.root, "EP12_R01")
        self.assertIsNone(window_stale(reel))
        src = read_json(reel.p("00_inputs/source.json"))
        src["fingerprint"] = "0" * 40
        write_json(reel.p("00_inputs/source.json"), src)
        self.assertIn("reels-select", window_stale(reel))
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(self.root),
                            "--video-id", "EP12_R01", "preflight"], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("reels-select", r.stdout + r.stderr)

    def test_guard_blocks_subagent_select(self):
        cmd = "reel reels-select --episode EP12 --pick R01 --by editor"
        self.assertEqual(run_guard(cmd, "whynot-cut:episode-analyst"), 2)
        self.assertEqual(run_guard(cmd), 0)
        self.assertEqual(run_guard('reel --root "X" --episode EP12 reels-select --pick R01 --by editor',
                                   "whynot-cut:story-editor"), 2)


if __name__ == "__main__":
    unittest.main()
