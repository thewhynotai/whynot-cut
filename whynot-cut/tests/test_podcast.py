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


def onset_s(wav: Path, thr: float = 0.3) -> float:
    from lib.audio_clean import _read_stereo
    import numpy as np
    x = _read_stereo(wav)
    x = x[:, 0] if x.ndim == 2 else x
    idx = int(np.argmax(np.abs(x) > thr))
    return idx / 48000


class TestWindowMedia(unittest.TestCase):
    """A reel = a window of a longer episode file (shared range mechanism): audio, XML, QC sync and preview read only
    the window, frame/sample exact, at a non-24 fps source."""

    @classmethod
    def setUpClass(cls):
        from lib.transcribe import finalize
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = root = cls.tmp / "WCLIENT"
        for d in ("assets/Brand", "data/Episodes"):
            (root / d).mkdir(parents=True)
        cls.src = root / "data/Episodes/EPW.mp4"
        ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30000/1001:d=120", "-f", "lavfi",
           "-i", "aevalsrc=exprs='if(between(t,61,61.01),0.8*sin(2*PI*1000*t),0)':s=48000:d=120",
           "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-shortest", str(cls.src))
        common.set_context(root)
        cls.reel = reel = Paths(root, "EPW_R01")
        reel.ensure_project()
        write_json(reel.p("00_inputs/source.json"), {"footage": "data/Episodes/EPW.mp4", "in_ms": 60000, "out_ms": 70000,
                                                      "duration_ms": 10000, "kind": "episode_reel"})
        ws = [{"id": i + 1, "segment_id": 1, "word": f"كلمه{i}", "start_ms": i * 500, "end_ms": i * 500 + 400,
               "probability": 0.9} for i in range(20)]
        finalize(reel, {"source_video": str(cls.src), "backend": "test", "model": "none", "language": "ar",
                        "language_probability": 1.0, "duration_ms": 10000},
                 [{"id": 1, "start_ms": 0, "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
                   "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}], ws)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _plan(self):
        from lib.media import preflight
        from lib.plan import compile_plan
        common.set_context(self.root)
        preflight(self.reel, [self.src])
        for f in ("main-topic.md", "medical-content-review.md"):
            (self.reel.p("01_analysis") / f).write_text("# stub\n", encoding="utf-8")
        for f in ("narrative-segments.json", "transcript-semantic-analysis.json", "editing-style.json"):
            write_json(self.reel.p("01_analysis") / f, {"stub": True})
        write_json(self.reel.p("01_analysis/edit-decisions.json"), {
            "video_id": "EPW_R01", "global": {"main_footage": "data/Episodes/EPW.mp4"},
            "decisions": [{"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "كلمه0 كلمه1",
                           "start": "00:00:00.000", "end": "00:00:04.000", "semantic_intent": "hook",
                           "visual_treatment": "punch", "confidence": "high",
                           "camera": {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000", "scale_factor": 1.1}}]})
        r = compile_plan(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        return r

    def test_audio_extract_sample_exact(self):
        from lib.audio_clean import clean
        common.set_context(self.root)
        clean(self.reel, self.src)
        reel_onset = onset_s(self.reel.p("06_audio/dialogue/dialogue_raw_48k.wav"))
        full = self.tmp / "full.wav"
        ff("-i", str(self.src), "-map", "0:a:0", "-ar", "48000", "-c:a", "pcm_s16le", str(full))
        self.assertLessEqual(abs((reel_onset + 60.0) - onset_s(full)), 0.001)   # same click, same instant
        self.assertLessEqual(abs(reel_onset - 1.0), 0.03)

    def test_xml_inpoints_offset(self):
        import xml.etree.ElementTree as ET
        from lib.audio_clean import clean
        from lib.premiere_xml import build_xml, TPS
        common.set_context(self.root)
        clean(self.reel, self.src)
        self._plan()
        tm = build_xml(self.reel, prefer_ae_renders=False)
        root = ET.parse(tm["xml"]).getroot()
        v1 = root.find("./sequence/media/video/track")
        clips = list(v1.iter("clipitem"))
        fps = common.seq_fps()
        self.assertEqual(int(clips[0].findtext("pproTicksIn")), round(60000 * TPS / 1000))
        self.assertEqual(int(clips[0].findtext("in")), round(60000 * fps / 1000))
        for c in clips:   # every V1 piece points inside the window of the original file
            t = int(c.findtext("pproTicksIn")) / TPS
            self.assertTrue(60.0 - 1e-6 <= t < 70.0, t)
        a1 = root.find("./sequence/media/audio/track")
        self.assertEqual(int(next(a1.iter("clipitem")).findtext("pproTicksIn")), 0)   # clean dialogue: reel clock
        fdur = max(int(f.findtext("duration")) for f in root.iter("file") if f.findtext("duration")
                   and "EPW.mp4" in (f.findtext("pathurl") or ""))
        self.assertGreaterEqual(fdur, round(119 * 29.97))                    # the whole episode stays linked (handles)

    def test_qc_sync_offset_aware(self):
        from lib.audio_clean import clean
        from lib.premiere_xml import build_xml
        from lib.qc import run_qc
        common.set_context(self.root)
        clean(self.reel, self.src)
        self._plan()
        build_xml(self.reel, prefer_ae_renders=False)
        r = run_qc(self.reel)
        sync = next(c for c in r["checks"] if c["check"].startswith("Dialogue sync preserved"))
        self.assertEqual(sync["result"], "PASS", sync)

    def test_qc_reel_checks(self):
        from lib.audio_clean import clean
        from lib.premiere_xml import build_xml
        from lib.qc import run_qc
        common.set_context(self.root)
        clean(self.reel, self.src)
        self._plan()
        tm = build_xml(self.reel, prefer_ae_renders=False)
        checks = {c["check"]: c for c in run_qc(self.reel)["checks"]}
        self.assertEqual(checks["Reel starts at its episode in-point"]["result"], "PASS")
        self.assertEqual(checks["Reel window inside the episode"]["result"], "PASS")
        x = Path(tm["xml"])
        txt = x.read_text(encoding="utf-8")
        from lib.premiere_xml import TPS
        x.write_text(txt.replace(f"<pproTicksIn>{round(60000 * TPS / 1000)}</pproTicksIn>", "<pproTicksIn>0</pproTicksIn>", 1),
                     encoding="utf-8")
        checks = {c["check"]: c for c in run_qc(self.reel)["checks"]}
        self.assertEqual(checks["Reel starts at its episode in-point"]["result"], "FAIL")

    def test_vfr_flagged(self):
        from lib.media import preflight, probe
        v = self.tmp / "vfr.mp4"
        ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=15:d=2",
           "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-fps_mode", "vfr", "-c:v", "libx264",
           "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(v))
        self.assertTrue(probe(v)["video"]["vfr"])
        self.assertFalse(probe(self.src)["video"]["vfr"])
        p = Paths(self.root, "VFRTEST")
        p.ensure_project()
        rep = preflight(p, [v])
        self.assertTrue(any("variable frame rate" in i["msg"] for i in rep["issues"]), rep["issues"])

    def test_preview_video_seeks(self):
        from lib.preview_video import render
        from lib.previews import render_all
        common.set_context(self.root)
        self._plan()
        render_all(self.reel, composite_preview=False)
        t0 = __import__("time").time()
        r = render(self.reel, width=270, label=False)
        self.assertTrue(r["ok"], r)
        self.assertLess(__import__("time").time() - t0, 60)
        from PIL import Image, ImageChops, ImageStat

        def grab(video, t, out):
            ff("-ss", f"{t}", "-i", str(video), "-frames:v", "1", "-vf", "scale=64:36", str(out))
            return Image.open(out).convert("L")
        p = grab(r["video"], 4.0, self.tmp / "p.png").resize((64, 36))
        near = grab(self.src, 64.0, self.tmp / "near.png")
        far = grab(self.src, 4.0, self.tmp / "far.png")
        d_near = ImageStat.Stat(ImageChops.difference(p, near)).mean[0]
        d_far = ImageStat.Stat(ImageChops.difference(p, far)).mean[0]
        self.assertLess(d_near, d_far)                                        # the preview shows 01:04, not 00:04


COVER = 1920 / 1080                     # 16:9 1920x1080 source filling a 1080x1920 frame
LIM = (1920 * COVER - 1080) / 2


def shot(a, b, *cxs, w=0.05):
    return {"start_ms": a, "end_ms": b, "faces": [[cx, 0.4, w, w * 1.6] for cx in cxs], "n_faces": len(cxs)}


SPEAKERS = {"people": {"host": {"name": "A", "position": "left"}, "guest": {"name": "S", "position": "right"}},
            "turns": [{"start_ms": 0, "end_ms": 4000, "speaker": "host"}, {"start_ms": 4000, "end_ms": 9000, "speaker": "guest"}]}


class TestShots(unittest.TestCase):
    def frame(self, shots, speakers=None):
        from lib.shots import frame_shots
        return frame_shots(shots, speakers, 1920, 1080)

    def test_single_face_centred(self):
        e = self.frame([shot(0, 5000, 0.70)])
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["decision_id"], "AUTO_SHOT")
        self.assertAlmostEqual(e[0]["offset_x"], max(-LIM, -(0.70 - 0.5) * 1920 * COVER), delta=0.5)
        self.assertEqual((e[0]["at_ms"], e[0]["until_ms"], e[0]["scale_factor"]), (0, 5000, 1.0))

    def test_face_at_edge_clamped(self):
        e = self.frame([shot(0, 5000, 0.98)])
        self.assertAlmostEqual(e[0]["offset_x"], -LIM, delta=0.5)

    def test_group_fits_uses_group_centre(self):
        e = self.frame([shot(0, 5000, 0.45, 0.55)])
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["decision_id"], "AUTO_SHOT")
        self.assertAlmostEqual(e[0]["offset_x"], 0.0, delta=0.5)

    def test_no_face_is_cutaway(self):
        e = self.frame([shot(0, 3000)])
        self.assertEqual(e[0]["decision_id"], "AUTO_CUTAWAY")
        self.assertEqual(e[0]["scale_factor"], round((1080 / 1920) / COVER, 5))
        self.assertEqual(e[0]["offset_x"], 0.0)

    def test_two_shot_follows_speaker(self):
        e = self.frame([shot(0, 9000, 0.25, 0.75)], SPEAKERS)
        self.assertEqual([(x["at_ms"], x["until_ms"], x["target"]) for x in e], [(0, 4000, "host"), (4000, 9000, "guest")])
        self.assertAlmostEqual(e[0]["offset_x"], -(0.25 - 0.5) * 1920 * COVER, delta=0.5)
        self.assertAlmostEqual(e[1]["offset_x"], -(0.75 - 0.5) * 1920 * COVER, delta=0.5)

    def test_min_hold_merges_short_turns(self):
        sp = {"people": SPEAKERS["people"], "turns": [{"start_ms": 0, "end_ms": 4000, "speaker": "host"},
                                                      {"start_ms": 4000, "end_ms": 4900, "speaker": "guest"},
                                                      {"start_ms": 4900, "end_ms": 9000, "speaker": "host"}]}
        e = self.frame([shot(0, 9000, 0.25, 0.75)], sp)
        self.assertEqual([(x["at_ms"], x["until_ms"], x["target"]) for x in e], [(0, 9000, "host")])

    def test_unknown_layout_whole(self):
        e = self.frame([shot(0, 9000, 0.25, 0.75)])
        self.assertEqual(e[0]["decision_id"], "AUTO_CUTAWAY")
        self.assertIn("speaker", e[0]["rationale"])

    def test_split_by_face_presence_catches_dissolves(self):
        from lib.shots import split_by_presence
        face = [[0.5, 0.4, 0.1, 0.16]]
        samples = [(t, face if (t < 4000 or t >= 8000) else []) for t in range(0, 10000, 500)]
        parts = split_by_presence(samples, 0, 10000, 1000)
        self.assertEqual(len(parts), 3)
        self.assertLessEqual(abs(parts[0][1] - 4000), 500)
        self.assertLessEqual(abs(parts[1][1] - 8000), 500)
        self.assertEqual([bool(p[2]) for p in parts], [True, False, True])
        self.assertEqual((parts[0][0], parts[-1][1]), (0, 10000))
        flicker = [(t, face if t != 3000 else []) for t in range(0, 10000, 500)]   # one missed detection: no split
        self.assertEqual(len(split_by_presence(flicker, 0, 10000, 1000)), 1)
        # speaker looking down for 1.5 s (no face detected) but the frames look like the speaker's: no split, and the
        # part keeps the speaker's face position
        turned = [(t, face if not 3000 <= t < 4500 else [], True) for t in range(0, 10000, 500)]
        parts = split_by_presence(turned, 0, 10000, 1000)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0][2], face)

    def test_shots_from_cuts_merges_short(self):
        from lib.shots import shots_from_cuts
        self.assertEqual(shots_from_cuts([2000, 2300, 6000], 9000, 400), [(0, 2000), (2000, 6000), (6000, 9000)])

    def test_no_faces_anywhere_note(self):
        from lib.shots import analyze_window
        tmp = Path(tempfile.mkdtemp())
        try:
            v = tmp / "v.mp4"
            ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt",
               "yuv420p", str(v))
            r = analyze_window(v, 1000, 2000, faces_fn=lambda im: [])
            self.assertTrue(r["shots"])
            self.assertIn("motion", r["note"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_preflight_runs_shot_analysis_for_episode_reels(self):
        from lib.media import preflight
        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "PF"
            for d in ("assets/Brand", "data/Episodes"):
                (root / d).mkdir(parents=True)
            src = root / "data/Episodes/E.mp4"
            ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=4", "-f", "lavfi", "-i", "color=c=red:s=640x360:r=25:d=4",
               "-f", "lavfi", "-i", "sine=f=300:r=48000:d=8", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
               "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(src))
            common.set_context(root)
            reel = Paths(root, "E_R01")
            reel.ensure_project()
            write_json(reel.p("00_inputs/source.json"), {"footage": "data/Episodes/E.mp4", "in_ms": 1000, "out_ms": 7000,
                                                          "duration_ms": 6000, "kind": "episode_reel"})
            rep = preflight(reel, [src])
            sh = rep["shots"]
            self.assertEqual(sh["window"], {"offset_ms": 1000, "duration_ms": 6000})
            self.assertGreaterEqual(len(sh["shots"]), 2)
            self.assertTrue(any(abs(c - 3000) <= 200 for c in sh["cuts_ms"]), sh["cuts_ms"])   # the cut at 4 s -> 3 s
            self.assertEqual(rep["reframe"][str(src)]["mode"], "per-shot")
            plain = Paths(root, "E_PLAIN")
            plain.ensure_project()
            self.assertNotIn("shots", preflight(plain, [src]))                  # whole-file clips: unchanged path
        finally:
            common.set_context(None)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_compose_punch_in_over_shot(self):
        from lib.shots import compose_camera
        layer = [{"decision_id": "AUTO_SHOT", "type": "reframe", "at_ms": 0, "until_ms": 9000, "scale_factor": 1.0,
                  "offset_x": -300.0, "offset_y": 0.0, "rationale": "face", "target": None}]
        story = [{"decision_id": "EDIT_001", "type": "punch_in", "at_ms": 1000, "until_ms": 3000, "scale_factor": 1.15,
                  "offset_x": 0.0, "offset_y": 0.0, "rationale": ""}]
        out = compose_camera(story, layer, 1920, 1080)
        spans = [(c["at_ms"], c["until_ms"], c["decision_id"]) for c in out]
        self.assertEqual(spans, [(0, 1000, "AUTO_SHOT"), (1000, 3000, "EDIT_001"), (3000, 9000, "AUTO_SHOT")])
        mid = out[1]
        self.assertEqual(mid["scale_factor"], 1.15)
        self.assertAlmostEqual(mid["offset_x"], -345.0, delta=0.01)
        self.assertEqual(mid["type"], "punch_in")

    def test_compose_keeps_cutaway(self):
        from lib.shots import compose_camera
        layer = [{"decision_id": "AUTO_CUTAWAY", "type": "reframe", "at_ms": 0, "until_ms": 3000, "scale_factor": 0.3,
                  "offset_x": 0.0, "offset_y": 0.0, "rationale": "no face"}]
        story = [{"decision_id": "EDIT_001", "type": "punch_in", "at_ms": 1000, "until_ms": 2000, "scale_factor": 1.15,
                  "offset_x": 0.0, "offset_y": 0.0, "rationale": ""}]
        out = compose_camera(story, layer, 1920, 1080)
        self.assertIn("AUTO_CUTAWAY", [c["decision_id"] for c in out])

    def test_timemap_scales_offset_on_mask_step(self):
        from lib.timemap import TimeMap
        cam = [{"decision_id": "AUTO_SHOT", "type": "reframe", "at_ms": 0, "until_ms": 5000, "scale_factor": 1.0,
                "offset_x": -300.0, "offset_y": 0.0}]
        tm = TimeMap([(0, 2000), (2500, 5000)], cam)
        self.assertEqual(tm.pieces[0]["offset_x"], -300.0)
        self.assertEqual(tm.pieces[1]["scale_factor"], 1.06)
        self.assertAlmostEqual(tm.pieces[1]["offset_x"], -318.0, delta=0.01)

    def test_plan_uses_shot_layer(self):
        from lib.plan import compile_plan
        from lib.transcribe import finalize
        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "SC"
            for d in ("assets/Brand", "data/Episodes"):
                (root / d).mkdir(parents=True)
            src = root / "data/Episodes/E.mp4"
            ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=12", "-f", "lavfi", "-i", "sine=f=300:r=48000:d=12",
               "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src))
            common.set_context(root)
            reel = Paths(root, "E_R01")
            reel.ensure_project()
            write_json(reel.p("00_inputs/source.json"), {"footage": "data/Episodes/E.mp4", "in_ms": 1000, "out_ms": 9000,
                                                          "duration_ms": 8000, "kind": "episode_reel"})
            ws = [{"id": i + 1, "segment_id": 1, "word": f"كلمه{i}", "start_ms": i * 500, "end_ms": i * 500 + 400,
                   "probability": 0.9} for i in range(16)]
            finalize(reel, {"source_video": str(src), "backend": "test", "model": "none", "language": "ar",
                            "language_probability": 1.0, "duration_ms": 8000},
                     [{"id": 1, "start_ms": 0, "end_ms": 7900, "text": " ".join(w["word"] for w in ws), "avg_logprob": -0.2,
                       "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}], ws)
            from lib.media import preflight
            preflight(reel, [src])
            pre = read_json(reel.p("00_inputs/preflight.json"))
            pre["shots"] = {"window": {"offset_ms": 1000, "duration_ms": 8000}, "method": "test",
                            "shots": [shot(0, 3000, 0.70), shot(3000, 8000, 0.30)]}
            write_json(reel.p("00_inputs/preflight.json"), pre)
            for f in ("main-topic.md", "medical-content-review.md"):
                (reel.p("01_analysis") / f).write_text("# stub\n", encoding="utf-8")
            for f in ("narrative-segments.json", "transcript-semantic-analysis.json", "editing-style.json"):
                write_json(reel.p("01_analysis") / f, {"stub": True})
            write_json(reel.p("01_analysis/edit-decisions.json"), {"video_id": "E_R01", "global": {}, "decisions": [
                {"decision_id": "EDIT_001", "segment_id": "S1", "evidence": "كلمه1 كلمه2", "start": "00:00:00.500",
                 "end": "00:00:02.000", "semantic_intent": "hook", "visual_treatment": "punch", "confidence": "high",
                 "camera": {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:02.000", "scale_factor": 1.1}}]})
            r = compile_plan(reel)
            self.assertTrue(r["ok"], r["errors"])
            spec = read_json(reel.p("01_analysis/timeline-spec.json"))
            self.assertTrue(spec["framing"].startswith("per-shot"), spec["framing"])
            self.assertAlmostEqual(spec["base_scale_percent"], max(1080 / 640, 1920 / 360) * 100, delta=0.01)
            starts = [round(s["src_in_ms"]) for s in spec["main_segments"]]
            self.assertTrue(any(abs(t - 3000) <= 50 for t in starts), starts)           # a cut at the shot change
            offs = {round(s["offset_x"]) for s in spec["main_segments"] if s["src_in_ms"] >= 3000}
            self.assertTrue(offs and all(o > 0 for o in offs), offs)                     # face at 0.30 -> shifted right
        finally:
            common.set_context(None)
            shutil.rmtree(tmp, ignore_errors=True)


def reel_fixture(tmp: Path, recipe_type: str | None = "drama", dur_s: int = 12, music: bool = True):
    """A client with a 16:9 episode and one reel project E_R01 (window 1-11 s), a transcript, semantic stubs and a
    licensed music file in data/Music."""
    from lib.transcribe import finalize
    root = tmp / "RC"
    for d in ("assets/Brand", "data/Episodes", "data/Music"):
        (root / d).mkdir(parents=True, exist_ok=True)
    src = root / "data/Episodes/E.mp4"
    ff("-f", "lavfi", "-i", f"testsrc2=s=640x360:r=25:d={dur_s}", "-f", "lavfi", "-i", f"sine=f=300:r=48000:d={dur_s}",
       "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src))
    if music:
        ff("-f", "lavfi", "-i", "sine=f=220:r=48000:d=30", "-ac", "2", "-c:a", "pcm_s16le", str(root / "data/Music/warm_track.wav"))
    common.set_context(root)
    reel = Paths(root, "E_R01")
    reel.ensure_project()
    from lib.recipes import resolve
    src_rec = {"footage": "data/Episodes/E.mp4", "in_ms": 1000, "out_ms": 11000, "duration_ms": 10000, "kind": "episode_reel"}
    if recipe_type:
        src_rec.update(content_type=recipe_type, recipe=resolve(recipe_type))
    write_json(reel.p("00_inputs/source.json"), src_rec)
    ws = [{"id": i + 1, "segment_id": 1, "word": f"كلمه{i}", "start_ms": i * 500, "end_ms": i * 500 + 400,
           "probability": 0.9} for i in range(20)]
    finalize(reel, {"source_video": str(src), "backend": "test", "model": "none", "language": "ar",
                    "language_probability": 1.0, "duration_ms": 10000},
             [{"id": 1, "start_ms": 0, "end_ms": 9900, "text": " ".join(w["word"] for w in ws), "avg_logprob": -0.2,
               "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}], ws)
    for f in ("main-topic.md", "medical-content-review.md"):
        (reel.p("01_analysis") / f).write_text("# stub\n", encoding="utf-8")
    for f in ("narrative-segments.json", "transcript-semantic-analysis.json", "editing-style.json"):
        write_json(reel.p("01_analysis") / f, {"stub": True})
    from lib.media import preflight
    preflight(reel, [src])
    return root, reel, src


def decision(did, a, b, evidence, **kw):
    d = {"decision_id": did, "segment_id": "S1", "evidence": evidence, "start": a, "end": b, "semantic_intent": "x",
         "visual_treatment": "x", "confidence": "high"}
    d.update(kw)
    return d


class TestRecipes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_audio_clean_defaults_from_recipe(self):
        from lib.recipes import pause_params
        root, reel, _src = reel_fixture(self.tmp, "drama", music=False)
        self.assertEqual(pause_params(reel), {"min_pause_ms": 600, "pad_ms": 160, "source": "recipe drama"})
        self.assertEqual(pause_params(reel, 300, None)["min_pause_ms"], 300)          # an explicit value wins
        self.assertEqual(pause_params(reel, 300, None)["pad_ms"], 160)
        clip = Paths(root, "CLIPX")
        clip.ensure_project()
        self.assertEqual(pause_params(clip), {"min_pause_ms": 250, "pad_ms": 80, "source": "default"})
        write_json(root / common.CLIENT_PROFILE_REL / "style.json", {"remove_pauses": {"min_pause_ms": 300, "pad_ms": 100}})
        self.assertEqual(pause_params(clip), {"min_pause_ms": 300, "pad_ms": 100, "source": "profile style.json"})
        self.assertEqual(pause_params(reel)["source"], "recipe drama")                # the reel's recipe beats the profile

    def test_plan_warns_on_recipe_excess(self):
        from lib.plan import compile_plan
        _root, reel, _src = reel_fixture(self.tmp, "emotional", music=False)
        write_json(reel.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": [
            decision("EDIT_001", "00:00:00.000", "00:00:04.000", "كلمه0 كلمه1", recipe_note="she pauses here; keep it calm",
                     graphics=[{"id": "GFX_001", "template": "hook_title", "start": "00:00:00.000", "end": "00:00:02.000",
                                "text": "كلمه0"},
                               {"id": "GFX_002", "template": "term_callout", "start": "00:00:02.500", "end": "00:00:04.000",
                                "text": "كلمه1"}])]})
        r = compile_plan(reel)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("recipe emotional" in w and "graphics" in w for w in r["warnings"]), r["warnings"])
        self.assertTrue(any("term_callout" in w for w in r["warnings"]))               # a template the recipe avoids
        md = reel.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        self.assertIn("Recipe: emotional", md)
        self.assertIn("she pauses here", md)

    def test_music_placed_in_xml(self):
        import xml.etree.ElementTree as ET
        from lib.plan import compile_plan
        from lib.premiere_xml import build_xml
        _root, reel, _src = reel_fixture(self.tmp, "drama")
        write_json(reel.p("01_analysis/edit-decisions.json"), {"global": {}, "music": {"file": "data/Music/warm_track.wav"},
                   "decisions": [decision("EDIT_001", "00:00:00.000", "00:00:04.000", "كلمه0 كلمه1")]})
        r = compile_plan(reel)
        self.assertTrue(r["ok"], r["errors"])
        spec = read_json(reel.p("01_analysis/timeline-spec.json"))
        self.assertEqual(spec["music"]["status"], "PLACED")
        self.assertEqual(spec["music"]["level_db"], -26)                                 # drama recipe level
        tm = build_xml(reel, prefer_ae_renders=False)
        x = ET.parse(tm["xml"]).getroot()
        mus = [c for c in x.iter("clipitem") if (c.findtext("name") or "").startswith("MUSIC")]
        self.assertEqual(len(mus), 2)                                                     # L/R mono pair
        self.assertEqual(int(mus[0].findtext("start")), 0)
        self.assertEqual(int(mus[0].findtext("end")), spec["duration_frames"])
        lv = mus[0].find(".//parameter[parameterid='level']")
        self.assertAlmostEqual(float(lv.findtext("value")), 10 ** (-26 / 20), places=4)
        self.assertTrue(any(t["id"] == "A06" for t in tm["tracks"]["audio"]))

    def test_preview_mixes_music(self):
        import numpy as np
        from lib.plan import compile_plan
        from lib.preview_video import build_audio
        from lib.audio_clean import _read_stereo
        _root, reel, src = reel_fixture(self.tmp, "drama")
        write_json(reel.p("01_analysis/edit-decisions.json"), {"global": {}, "music": {"file": "data/Music/warm_track.wav"},
                   "decisions": [decision("EDIT_001", "00:00:00.000", "00:00:04.000", "كلمه0 كلمه1")]})
        self.assertTrue(compile_plan(reel)["ok"])
        spec = read_json(reel.p("01_analysis/timeline-spec.json"))

        def energy_220(sp, name):
            x = _read_stereo(build_audio(reel, sp, self.tmp / name, src))[:, 0]
            seg = x[48000:48000 * 3]                         # 1-3 s: well before the fade-out
            mag = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
            return mag[int(220 * len(seg) / 48000)]
        with_music = energy_220(spec, "m.wav")
        without = energy_220(dict(spec, music={"status": "NO_MUSIC_SUPPLIED"}), "n.wav")
        self.assertGreater(with_music, 10 * max(without, 1e-6))

    def test_music_outside_library_rejected(self):
        from lib.plan import compile_plan
        _root, reel, src = reel_fixture(self.tmp, "drama")
        write_json(reel.p("01_analysis/edit-decisions.json"), {"global": {}, "music": {"file": "data/Episodes/E.mp4"},
                   "decisions": [decision("EDIT_001", "00:00:00.000", "00:00:04.000", "كلمه0 كلمه1")]})
        r = compile_plan(reel)
        self.assertFalse(r["ok"])
        self.assertTrue(any("data/Music" in e for e in r["errors"]))

    def test_music_library_tags(self):
        from lib.recipes import music_library
        root, _reel, _src = reel_fixture(self.tmp, "drama")
        ff("-f", "lavfi", "-i", "sine=f=500:r=48000:d=2", str(root / "data/Music/tense_dark_loop.wav"))
        write_json(root / "data/Music/music.json", {"tracks": [{"file": "warm_track.wav", "moods": ["uplifting"],
                                                                "license": "Artlist #123"}]})
        lib = {x["rel"]: x for x in music_library(root)}
        self.assertEqual(lib["data/Music/warm_track.wav"]["moods"], ["uplifting"])        # music.json wins
        self.assertEqual(lib["data/Music/warm_track.wav"]["license"], "Artlist #123")
        self.assertIn("tense", lib["data/Music/tense_dark_loop.wav"]["moods"])            # file-name tokens

    def test_protected_pauses_stay(self):
        from lib.plan import compile_plan
        _root, reel, _src = reel_fixture(self.tmp, "comedy", music=False)
        write_json(reel.p("06_audio/dialogue/pauses.json"), {"keep_ms": [[0, 2000], [3000, 10000]], "removed_ms": 1000,
                                                             "cuts_ms": [[2000, 3000]], "pauses_ms": [[1900, 3100]]})
        write_json(reel.p("01_analysis/edit-decisions.json"), {"global": {"remove_pauses": {"protect": [
            ["00:00:01.800", "00:00:03.200"]]}}, "decisions": [decision("EDIT_001", "00:00:00.000", "00:00:04.000", "كلمه0 كلمه1")]})
        r = compile_plan(reel)
        self.assertTrue(r["ok"], r["errors"])
        tm = read_json(reel.p("01_analysis/timeline-spec.json"))["time_map"]
        self.assertEqual(tm["keep_ms"], [[0, 10000]])
        self.assertEqual(tm["removed_ms"], 0)


class TestNewTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.reel, self.src = reel_fixture(self.tmp, "success_story", music=False)

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plan(self, graphics):
        from lib.plan import compile_plan
        write_json(self.reel.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": [
            decision("EDIT_001", "00:00:00.000", "00:00:06.000", "كلمه0 كلمه1", graphics=graphics)]})
        return compile_plan(self.reel)

    def test_stat_card_requires_value(self):
        r = self.plan([{"id": "GFX_001", "template": "stat_card", "start": "00:00:01.000", "end": "00:00:04.000",
                        "label": "سنين"}])
        self.assertFalse(r["ok"])
        self.assertTrue(any("stat_card" in e and "value" in e for e in r["errors"]), r["errors"])

    def test_render_new_templates(self):
        from PIL import Image
        from lib.previews import render_all
        from lib.ppro_build import job_data
        r = self.plan([{"id": "GFX_001", "template": "stat_card", "start": "00:00:01.000", "end": "00:00:03.000",
                        "value": "+200%", "label": "نمو في سنة"},
                       {"id": "GFX_002", "template": "context_card", "start": "00:00:03.500", "end": "00:00:05.500",
                        "text": "بيحكي عن أول شركة خسرها"}])
        self.assertTrue(r["ok"], r["errors"])
        render_all(self.reel, composite_preview=False)
        for gid, top_min in (("GFX_001", 250), ("GFX_002", 250)):
            png = self.reel.p(f"03_broll/typography/{gid}.png")
            bb = Image.open(png).getchannel("A").getbbox()
            self.assertIsNotNone(bb, gid)
            self.assertGreaterEqual(bb[0], 40)
            self.assertLessEqual(bb[2], 1040)
            self.assertGreaterEqual(bb[1], top_min)
        ctx = Image.open(self.reel.p("03_broll/typography/GFX_002.png")).getchannel("A").getbbox()
        self.assertLess(ctx[3], 700)                                         # a pill near the top, above the face
        lanes = {g["id"]: g for g in job_data(self.reel)["graphics"]}
        self.assertEqual(lanes["GFX_001"]["anim"], "card")
        self.assertEqual(lanes["GFX_002"]["anim"], "card")

    def test_hb_font_sizes_independent(self):
        """Two sizes of the SAME font file in one still (stat value 150 px + label 52 px): each renders at its own size
        (the FreeType face is shared per file; its size must be set at render time)."""
        from lib import hb_text
        from lib.plat import font_dirs
        if not hb_text.AVAILABLE:
            self.skipTest("uharfbuzz/freetype not installed")
        font = next((f for d in font_dirs() if d.exists() for f in sorted(d.glob("*.ttf"))
                     if f.name.lower() in ("arial.ttf", "dejavusans.ttf", "notosansarabic-regular.ttf",
                                           "ibmplexsansarabic-medium.ttf")), None)
        if font is None:
            self.skipTest("no test font found")
        big = hb_text.HBFontSpec(str(font), 150)
        hb_text.HBFontSpec(str(font), 40)                     # created later: must not shrink `big`
        im, _base, _w = big.render("سنين 3", (255, 255, 255, 255))
        bb = im.getchannel("A").getbbox()
        self.assertGreater(bb[3] - bb[1], 70)                 # glyph ink ~ 0.5-0.9 em at 150 px

    def test_flagged_word_blocks_stat_value(self):
        wj = read_json(self.reel.p("02_transcription/words.json"))
        wj["words"][3]["flagged"] = {"note": "unclear"}
        write_json(self.reel.p("02_transcription/words.json"), wj)
        r = self.plan([{"id": "GFX_001", "template": "stat_card", "start": "00:00:01.000", "end": "00:00:03.000",
                        "value": "كلمه3", "label": "x"}])
        self.assertFalse(r["ok"])
        self.assertTrue(any("flagged" in e for e in r["errors"]), r["errors"])


PUB_SHEET = SHEET.replace("https://www.instagram.com/sara.ceo/", "https://www.x.com/a.")


def good_pub():
    return {"episode_id": "EP12", "language": "ar",
            "youtube": {"titles": ["قصة سارة مع أول شركة", "ازاي خسرت كل حاجة وبدأت تاني", "سارة: الفشل علمني"],
                        "description": {"hook": "سارة بتحكي إزاي خسرت أول شركة.", "summary": "حلقة عن الفشل والبداية من جديد.",
                                        "guest": "ضيفة الحلقة: Sara — CEO", "links": [{"label": "Sara", "url": "https://www.x.com/a"}],
                                        "sponsor": "", "cta": "اشترك في القناة", "hashtags": ["#بودكاست", "#قصة_نجاح"]},
                        "tags": ["بودكاست", "ريادة أعمال", "قصة نجاح"]},
            "thumbnail": {"designs": []}, "approval_required": []}


def good_reel():
    return {"reel_id": "EP12_R01", "instagram": {"caption": "«انا قلت ان الشركه» — سارة عن أول خسارة", "hashtags": ["#بودكاست"]},
            "tiktok": {"caption": "سارة عن أول خسارة", "hashtags": ["#بودكاست"]},
            "shorts": {"title": "سارة عن أول خسارة", "description": "من الحلقة 12"}, "approval_required": []}


class TestPublish(unittest.TestCase):
    def setUp(self):
        from lib.episode import EpisodePaths
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "C"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data").mkdir()
        common.set_context(self.root)
        self.ep = EpisodePaths(self.root, "EP12")
        synthetic_episode_transcript(self.ep)
        from lib.episode import parse_sheet
        write_json(self.ep.p("00_inputs/episode.json"), {"episode_id": "EP12", "duration_ms": 121000, "sheet_text": PUB_SHEET,
                                                         "sheet": {k: v for k, v in parse_sheet(PUB_SHEET).items() if k != "_text"}})
        write_json(self.ep.p("01_analysis/topics.json"), {"topics": [
            {"id": "T01", "start": "00:00:00.000", "end": "00:00:40.000", "title": "البداية"},
            {"id": "T02", "start": "00:00:40.000", "end": "00:01:20.000", "title": "أول خسارة"},
            {"id": "T03", "start": "00:01:20.000", "end": "00:02:01.000", "title": "البداية من جديد"}]})

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, pub=None, reel=None):
        from lib.publish import check
        write_json(self.ep.p("publish/publish.json"), pub or good_pub())
        write_json(self.ep.p("publish/reels/EP12_R01.json"), reel or good_reel())
        return check(self.ep)

    def test_valid_package_renders_files(self):
        r = self.run_check()
        self.assertTrue(r["ok"], r["errors"])
        ch = self.ep.p("publish/chapters.txt").read_text(encoding="utf-8").splitlines()
        self.assertTrue(ch[0].startswith("00:00 "), ch)
        self.assertEqual(ch[1], "00:40 أول خسارة")
        md = self.ep.p("publish/youtube.md").read_text(encoding="utf-8")
        for t in good_pub()["youtube"]["titles"]:
            self.assertIn(t, md)
        self.assertIn("https://www.x.com/a", md)
        self.assertIn("بودكاست", self.ep.p("publish/tags.txt").read_text(encoding="utf-8"))
        self.assertTrue(self.ep.p("publish/EP12.srt").exists())
        self.assertTrue(self.ep.p("publish/reels/EP12_R01.md").exists())
        self.assertTrue(read_json(self.ep.p("publish/publish-validation.json"))["ok"])

    def test_title_limits(self):
        p = good_pub()
        p["youtube"]["titles"][0] = "ا" * 101
        self.assertTrue(any("title" in e and "100" in e for e in self.run_check(p)["errors"]))
        p = good_pub()
        p["youtube"]["titles"] = p["youtube"]["titles"][:2]
        self.assertTrue(any("titles" in e for e in self.run_check(p)["errors"]))
        p = good_pub()
        p["youtube"]["titles"][0] = "ا" * 80
        r = self.run_check(p)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("70" in w for w in r["warnings"]))

    def test_angle_brackets_rejected(self):
        p = good_pub()
        p["youtube"]["description"]["summary"] = "حلقة <مهمة>"
        self.assertTrue(any("<" in e for e in self.run_check(p)["errors"]))

    def test_description_5000(self):
        p = good_pub()
        p["youtube"]["description"]["summary"] = "كلام " * 1100
        self.assertTrue(any("5000" in e for e in self.run_check(p)["errors"]))

    def test_tags_500(self):
        from lib.publish import count_tags_chars
        self.assertEqual(count_tags_chars(["ab", "c d"]), 2 + 1 + (3 + 2))     # comma + quotes around a spaced tag
        p = good_pub()
        p["youtube"]["tags"] = ["وسم طويل جدا"] * 40
        self.assertTrue(any("500" in e for e in self.run_check(p)["errors"]))

    def test_hashtags_15(self):
        p = good_pub()
        p["youtube"]["description"]["hashtags"] = [f"#وسم{i}" for i in range(16)]
        self.assertTrue(any("hashtag" in e for e in self.run_check(p)["errors"]))
        p = good_pub()
        p["youtube"]["description"]["hashtags"] = ["#قصة نجاح"]
        self.assertTrue(any("hashtag" in e for e in self.run_check(p)["errors"]))

    def test_chapter_rules(self):
        p = good_pub()
        p["youtube"]["chapters"] = [{"at": "00:05", "title": "a"}, {"at": "00:40", "title": "b"}, {"at": "01:20", "title": "c"}]
        self.assertTrue(any("00:00" in e for e in self.run_check(p)["errors"]))
        p["youtube"]["chapters"] = [{"at": "00:00", "title": "a"}, {"at": "00:40", "title": "b"}]
        self.assertTrue(any("3 chapters" in e for e in self.run_check(p)["errors"]))
        p["youtube"]["chapters"] = [{"at": "00:00", "title": "a"}, {"at": "00:05", "title": "b"}, {"at": "01:20", "title": "c"}]
        self.assertTrue(any("10 s" in e for e in self.run_check(p)["errors"]))

    def test_invented_link_rejected(self):
        p = good_pub()
        p["youtube"]["description"]["links"].append({"label": "x", "url": "https://instagram.com/invented"})
        self.assertTrue(any("instagram.com/invented" in e for e in self.run_check(p)["errors"]))

    def test_link_normalisation(self):
        from lib.publish import norm_url
        self.assertEqual(norm_url("https://www.X.com/a."), norm_url("x.com/a/"))
        p = good_pub()
        p["youtube"]["description"]["links"] = [{"label": "Sara", "url": "x.com/a/"}]
        r = self.run_check(p)
        self.assertTrue(r["ok"], r["errors"])

    def test_quote_must_exist(self):
        p = good_pub()
        p["youtube"]["titles"][0] = "«أنا قلت إن الشركة» — سارة"
        self.assertTrue(self.run_check(p)["ok"])
        p["youtube"]["titles"][0] = "«الفلوس مش كل حاجة» — سارة"
        self.assertTrue(any("quote" in e for e in self.run_check(p)["errors"]))

    def test_reel_caption_limits(self):
        reel = good_reel()
        reel["instagram"]["caption"] = "ا" * 2300
        self.assertTrue(any("instagram" in e and "2200" in e for e in self.run_check(reel=reel)["errors"]))
        reel = good_reel()
        reel["instagram"]["hashtags"] = [f"#و{i}" for i in range(31)]
        self.assertTrue(any("instagram" in e and "hashtag" in e for e in self.run_check(reel=reel)["errors"]))


class TestThumbnails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from lib.episode import EpisodePaths, prep
        cls.tmp = Path(tempfile.mkdtemp())
        root = cls.root = cls.tmp / "TC"
        for d in ("assets/Brand", "data/Episodes"):
            (root / d).mkdir(parents=True)
        # 120 s: bright 10 s / dark 10 s, alternating
        ff("-f", "lavfi", "-i", "color=c=black:s=640x360:r=5:d=120,geq=lum='if(lt(mod(T,20),10),200,30)':cb=128:cr=128",
           "-f", "lavfi", "-i", "sine=f=300:r=48000:d=120", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", str(root / "data/Episodes/EP9.mp4"))
        common.set_context(root)
        cls.ep = EpisodePaths(root, "EP9")
        prep(cls.ep)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_candidates_spaced_and_faced(self):
        from PIL import ImageStat
        from lib.publish import thumbnail_candidates

        def faces(im):
            return [(0.5, 0.4, 0.2, 0.3)] if ImageStat.Stat(im.convert("L")).mean[0] > 100 else []
        r = thumbnail_candidates(self.ep, n=3, faces_fn=faces, every_s=5)
        ts = [c["frame_ms"] for c in r["candidates"]]
        self.assertEqual(len(ts), 3)
        for t in ts:
            self.assertLess((t / 1000) % 20, 10.5)                       # bright frames only
        for a in ts:
            for b in ts:
                if a != b:
                    self.assertGreaterEqual(abs(a - b), 30000)
        for c in r["candidates"]:
            self.assertTrue(Path(c["file"]).exists())
        self.assertTrue(self.ep.p("publish/thumbnail/_candidates.jpg").exists())

    def test_render_design(self):
        from PIL import Image
        from lib.publish import render_thumbnails
        write_json(self.ep.p("publish/publish.json"), {"thumbnail": {"designs": [
            {"frame_ms": 22000, "text": "كلمة كلمة كلمة كلمة كلمة كلمة كلمة", "highlight": "كلمة"}]}})
        r = render_thumbnails(self.ep)
        self.assertTrue(r["ok"], r)
        f = Path(r["files"][0])
        self.assertEqual(Image.open(f).size, (1280, 720))
        self.assertLessEqual(f.stat().st_size, 2_000_000)
        self.assertTrue(any("words" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
