"""T2.14 (3.0): performance changes that must not change the output. One test per change, each proving the fast path
gives the same result as the slow one (timing is reported by the task, never asserted here).

Run one file: <engine runtime python> -s -B -m unittest discover -s whynot-cut/tests -p test_perf.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402


def decoded_md5(video) -> str:
    """md5 of the DECODED video frames (container details excluded)."""
    p = subprocess.run([common.ffmpeg_exe(), "-loglevel", "error", "-i", str(video), "-map", "0:v", "-f", "md5", "-"],
                       capture_output=True, text=True, check=True)
    return p.stdout.strip()


class TestParallelMap(unittest.TestCase):
    def test_order_and_errors_per_item(self):
        from lib.parallel import parallel_map

        def f(x):
            if x == 2:
                raise ValueError("two")
            return x * 10
        r = parallel_map(f, [1, 2, 3, 4], workers=3)
        self.assertEqual([ok for ok, _ in r], [True, False, True, True])
        self.assertEqual([v for ok, v in r if ok], [10, 30, 40])
        self.assertIsInstance(r[1][1], ValueError)
        self.assertEqual(parallel_map(f, [1, 2, 3, 4], workers=1)[0], (True, 10))

    def test_workers_see_the_callers_context(self):
        from lib.common import Context, use_context
        from lib.parallel import parallel_map
        root = Path(tempfile.mkdtemp())
        try:
            with use_context(Context(root)):
                seen = parallel_map(lambda _: common.current_context().root, range(4), workers=3)
            self.assertEqual({v for _, v in seen}, {root})
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestReelsPreviewParallel(unittest.TestCase):
    """reels-preview renders the candidates in a thread pool: the same files, in the same order, errors per reel."""

    @classmethod
    def setUpClass(cls):
        import test_podcast as T
        from lib.episode import EpisodePaths, prep
        from lib.transcribe import finalize
        cls.T = T
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = T.make_episode_client(cls.tmp, dur_s=14, size="320x180", with_clip=False)
        cls.ep = EpisodePaths(cls.root, "EP12")
        prep(cls.ep)
        ws = [{"id": i + 1, "segment_id": 1, "word": f"w{i}", "start_ms": i * 500, "end_ms": i * 500 + 400,
               "probability": 0.9} for i in range(27)]
        finalize(cls.ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                          "language_probability": 1.0, "duration_ms": 14000},
                 [{"id": 1, "start_ms": 0, "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
                   "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [w["id"] for w in ws]}], ws)
        cls.cands = [{"id": f"R0{k}", "in_ms": 1000 + 3000 * (k - 1), "out_ms": 3000 + 3000 * (k - 1),
                      "duration_ms": 2000, "type": "advice", "total": 7.0 + k / 10, "title": "t", "score": {}}
                     for k in range(1, 5)]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.T.validated_plan(self.ep, self.cands)

    def snapshot(self, r):
        return [(o["id"], Path(o["mp4"]).name, decoded_md5(o["mp4"]), hashlib.md5(Path(o["jpg"]).read_bytes()).hexdigest())
                for o in r["previews"]]

    def test_the_pool_gives_the_sequential_output(self):
        from lib.reels import render_candidates
        seq = render_candidates(self.ep, workers=1)
        self.assertTrue(seq["ok"], seq)
        want = self.snapshot(seq)
        for f in self.ep.p("03_candidates").glob("R0*"):
            f.unlink()
        par = render_candidates(self.ep)                       # default: the pool
        self.assertTrue(par["ok"], par)
        self.assertEqual([o["id"] for o in par["previews"]], ["R01", "R02", "R03", "R04"])   # deterministic order
        self.assertEqual(self.snapshot(par), want)
        self.assertEqual(par["failed"], [])
        self.assertTrue(Path(par["sheet"]).exists())

    def test_errors_are_collected_per_reel(self):
        from lib import reels
        real = reels._label_png

        def label(path, lines, *a, **k):
            if "R02" in lines[0]:
                raise OSError("disk said no")
            return real(path, lines, *a, **k)
        with mock.patch.object(reels, "_label_png", side_effect=label):
            r = reels.render_candidates(self.ep)
        self.assertEqual([o["id"] for o in r["previews"]], ["R01", "R03", "R04"])
        self.assertEqual([f["id"] for f in r["failed"]], ["R02"])
        self.assertIn("disk said no", r["failed"][0]["error"])
        self.assertFalse(r["ok"])


class TestDocumentQuotesIndex(unittest.TestCase):
    """document_quotes finds a quote through a token index instead of scanning every window: same quotes, same fields."""

    @staticmethod
    def long_words(n=3000, seed=7):
        import random
        rng = random.Random(seed)
        vocab = [f"كلمة{i}" for i in range(260)] + ["في", "من", "على"] * 40
        words = []
        for i in range(n):
            words.append({"id": i + 1, "word": rng.choice(vocab), "start_ms": i * 400, "end_ms": i * 400 + 350,
                          "probability": 0.9})
        return words

    def test_same_quotes_with_and_without_the_index(self):
        import test_pipeline as T
        from lib.discover import run_discovery
        from lib.transcribe import document_quotes
        words = self.long_words()
        say = lambda a, n: [w["word"] for w in words[a:a + n]]
        quotes = [
            " ".join(say(40, 7)),                                         # exact
            " ".join(say(1500, 6)),                                       # exact, far into the transcript
            " ".join(say(2200, 5)[:2] + ["مختلف"] + say(2203, 3)),   # one word differs
            " ".join(say(900, 4) + say(905, 3)),                          # the writer dropped a word
            " ".join(say(2600, 6) + ["زائد"]),             # the writer added a word
            "جملة لم تُقل أبداً في هذا الفيديو",          # nowhere
            "في من على في من على",                        # only very frequent words
        ]
        with tempfile.TemporaryDirectory() as t:
            root, p, _ = T.make_project(Path(t))
            (root / "data/Ref/plan.md").write_text("\n".join(f"«{q}»" for q in quotes) + "\n", encoding="utf-8")
            run_discovery(p)
            fast = document_quotes(p, words)
            slow = document_quotes(p, words, use_index=False)
        self.assertEqual(fast, slow)
        self.assertGreaterEqual(len(fast), 4, fast)                      # the fixture really finds quotes
        self.assertTrue(any(q["exact"] for q in fast))
        self.assertTrue(any(not q["exact"] for q in fast))


class TestDiscoveryCache(unittest.TestCase):
    """Discovery re-reads only the files whose (size, mtime_ns) changed; `inbox` skips the module audit."""

    def setUp(self):
        import test_pipeline as T
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.p, _ = T.make_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def stable(res):
        inv = dict(res["inventory"])
        inv.pop("generated")
        return inv

    def run_counting(self, **kw):
        from lib import discover
        with mock.patch.object(discover, "sha1_head", wraps=discover.sha1_head) as fp, \
                mock.patch.object(discover, "read_document", wraps=discover.read_document) as rd:
            res = discover.run_discovery(self.p, **kw)
        return res, fp.call_count, rd.call_count

    def test_unchanged_files_are_not_fingerprinted_or_read_again(self):
        first, fp1, rd1 = self.run_counting()
        n = first["inventory"]["file_count"]
        self.assertEqual(fp1, n)
        self.assertGreaterEqual(rd1, 2)                                   # the brief and the style reference
        texts = {f: f.read_text(encoding="utf-8") for f in sorted((self.p.output / "discovery/extracted_text").glob("*.txt"))}
        second, fp2, rd2 = self.run_counting()
        self.assertEqual((fp2, rd2), (0, 0))                              # nothing changed: nothing read
        self.assertEqual(self.stable(second), self.stable(first))         # the same inventory, field for field
        self.assertEqual({f: f.read_text(encoding="utf-8") for f in sorted((self.p.output / "discovery/extracted_text").glob("*.txt"))},
                         texts)                                           # and the same extracted texts
        self.assertTrue((self.p.output / "discovery/discovery-cache.json").exists())
        self.assertFalse(list(self.root.joinpath("assets").rglob("*cache*")) + list(self.root.joinpath("data").rglob("*cache*")))

    def test_a_changed_file_is_read_again_and_only_that_one(self):
        first, _, _ = self.run_counting()
        ref = self.root / "data/Ref/style.md"
        new_text = "# Style\nFast captions, bigger hook.\n"
        ref.write_text(new_text, encoding="utf-8")                     # new size and mtime
        second, fp, rd = self.run_counting()
        self.assertEqual((fp, rd), (1, 1))
        one = next(f for f in second["inventory"]["files"] if f["rel"] == "data/Ref/style.md")
        self.assertEqual(one["text_chars"], len(new_text))
        text = (self.p.output / "discovery/extracted_text/data__Ref__style.md.txt").read_text(encoding="utf-8")
        self.assertIn("bigger hook", text)
        others = lambda r: [f for f in r["inventory"]["files"] if f["rel"] != "data/Ref/style.md"]
        self.assertEqual(others(second), others(first))

    def test_a_broken_or_foreign_cache_is_ignored(self):
        first, _, _ = self.run_counting()
        cache = self.p.output / "discovery/discovery-cache.json"
        for junk in ("{not json", "[1, 2]", '{"version": 99, "files": {"x": 1}}', '{"version": 1, "files": {"data/Ref/style.md": 5}}'):
            cache.write_text(junk, encoding="utf-8")
            again, fp, rd = self.run_counting()
            self.assertEqual(self.stable(again), self.stable(first))
            self.assertEqual(fp, first["inventory"]["file_count"])        # rebuilt from scratch

    def test_the_cache_is_read_and_written_inside_the_client_lock(self):
        from lib import discover, file_lock
        seen = []
        real = discover._load_cache
        real_w = discover._save_cache
        held = lambda: file_lock.lock_path(self.p.output / "discovery/input-inventory.json")

        def load(f):
            seen.append(("load", file_lock._entry(held()).depth))
            return real(f)

        def save(f, c):
            seen.append(("save", file_lock._entry(held()).depth))
            return real_w(f, c)
        with mock.patch.object(discover, "_load_cache", side_effect=load), mock.patch.object(discover, "_save_cache", side_effect=save):
            discover.run_discovery(self.p)
        self.assertEqual(seen, [("load", 1), ("save", 1)])

    def test_inbox_skips_the_module_audit_when_it_has_one(self):
        from lib import discover
        from lib.onboard import inbox
        full = discover.run_discovery(self.p)                             # a full discovery: the audit runs
        env_file = self.p.output / "discovery/environment.json"
        before = env_file.read_bytes()
        with mock.patch.object(discover, "audit_environment", side_effect=AssertionError("audit ran")) as audit:
            r = inbox(self.root)                                          # refresh: discovery without the audit
            self.assertEqual(audit.call_count, 0)
        self.assertEqual(env_file.read_bytes(), before)
        self.assertEqual([c["file"] for c in r["clips"]], ["data/Raw/CLIP1.mov"])
        report = (self.p.output / "discovery/discovery-report.md").read_text(encoding="utf-8")
        self.assertIn("## Environment", report)                           # the report keeps the last audit
        # a first discovery (no environment.json yet) still audits: the report and ae_builder need it
        env_file.unlink()
        with mock.patch.object(discover, "audit_environment", wraps=discover.audit_environment) as audit:
            discover.run_discovery(self.p, audit=False)
            self.assertEqual(audit.call_count, 1)
        self.assertEqual(json.loads(env_file.read_text(encoding="utf-8"))["os"], full["environment"]["os"])


def legacy_analyze_shots(path, duration_s, fps=2.0, threshold=0.55, start_s=0.0):
    """analyze_shots as it was before T2.14 (Python lists, one histogram per sample): the reference the NumPy one must equal."""
    from PIL import Image
    from lib.media import _hist, _similarity, cutaway_ranges
    from lib.previews import _face_center
    W, H = 480, 270
    rng = ["-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}"] if start_s else []
    p = subprocess.Popen([common.ffmpeg_exe(), "-loglevel", "error", *rng, "-i", str(path), "-an", "-vf", f"fps={fps},scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    rows = []
    try:
        while True:
            b = p.stdout.read(W * H * 3)
            if len(b) < W * H * 3:
                break
            im = Image.frombuffer("RGB", (W, H), b, "raw", "RGB", 0, 1)
            rows.append({"t": len(rows) / fps, "face": bool(_face_center(im)), "hist": _hist(im)})
    finally:
        p.stdout.close()
        p.wait()
    ref = [r["hist"] for r in rows if r["face"]]
    if not ref:
        return {"samples": len(rows), "cutaways_ms": [], "other_people_ms": [],
                "note": "no face found anywhere: cutaway detection skipped"}
    mean = [sum(c) / len(ref) for c in zip(*ref)]
    sims = sorted(_similarity(r["hist"], mean) for r in rows if r["face"])
    thr = max(threshold, sims[len(sims) // 2] - 0.12)
    ref2 = [r["hist"] for r in rows if r["face"] and _similarity(r["hist"], mean) >= thr]
    if ref2:
        mean = [sum(c) / len(ref2) for c in zip(*ref2)]
        sims = sorted(_similarity(h, mean) for h in ref2)
        thr = max(threshold, sims[len(sims) // 2] - 0.12)
    for r in rows:
        r["sim"] = round(_similarity(r.pop("hist"), mean), 3)
        r["speaker"] = r["sim"] >= thr
    cut = cutaway_ranges([r["speaker"] for r in rows], fps, duration_s)
    other = []
    for a, b in cut:
        inside = [r for r in rows if a <= r["t"] * 1000 < b]
        if inside and sum(r["face"] for r in inside) >= 0.5 * len(inside):
            other.append([a, b])
    return {"samples": len(rows), "fps": fps, "threshold": round(thr, 3), "cutaways_ms": cut, "other_people_ms": other,
            "speaker_similarity_median": round(sims[len(sims) // 2], 3) if sims else None}


class TestAnalyzeShotsNumpy(unittest.TestCase):
    """The vectorised histograms / similarities give the same cutaways, thresholds and medians as the list version."""

    def clip(self, folder):
        v = Path(folder) / "ep.mp4"      # speaker look 0-3 s, a card 3-5 s, the host (another look, a face) 5-7 s, speaker
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=3",
                        "-f", "lavfi", "-i", "color=c=0xE8E2D8:s=320x180:r=10:d=2",
                        "-f", "lavfi", "-i", "smptebars=s=320x180:r=10:d=2",
                        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=10:d=2",
                        "-filter_complex", "[0][1][2][3]concat=n=4:v=1:a=0", "-pix_fmt", "yuv420p", str(v)], check=True)
        return v

    def test_numpy_histograms_equal_the_list_version(self):
        from lib import media, previews
        card = (0xE8, 0xE2, 0xD8)
        face = lambda im: None if all(abs(a - b) < 12 for a, b in zip(im.getpixel((5, 5)), card)) else (0.5, 0.4)
        with tempfile.TemporaryDirectory() as t, mock.patch.object(previews, "_face_center", face):
            v = self.clip(t)
            for kw in ({}, {"fps": 4.0}, {"threshold": 0.3}):
                with self.subTest(**kw):
                    got = media.analyze_shots(v, 9.0, **kw)
                    self.assertEqual(got, legacy_analyze_shots(v, 9.0, **kw))
                    self.assertTrue(got["cutaways_ms"], got)                      # the fixture has a cutaway to find

    def test_the_same_when_no_face_is_found(self):
        from lib import media, previews
        with tempfile.TemporaryDirectory() as t, mock.patch.object(previews, "_face_center", lambda im: None):
            v = self.clip(t)
            got = media.analyze_shots(v, 9.0)
            self.assertEqual(got, legacy_analyze_shots(v, 9.0))
            self.assertEqual(got["cutaways_ms"], [])

    def test_the_histogram_vector_is_the_list(self):
        import numpy as np
        from PIL import Image
        from lib.media import _hist, _hist_np
        rng = np.random.default_rng(3)
        for _ in range(3):
            im = Image.fromarray(rng.integers(0, 256, (270, 480, 3), dtype=np.uint8))
            self.assertEqual(_hist_np(im).tolist(), _hist(im))


def decode_frames(video):
    import av
    with av.open(str(video)) as c:
        return [f.to_ndarray(format="rgb24") for f in c.decode(video=0)]


def build_preview_project(tmp: Path, broll: bool = False):
    """A planned and previewed 12 s synthetic reel (270x480 preview): (Context, Paths). `broll`: a licensed-looking clip
    (testsrc2, so every frame is recognisable) fills 00:02.000-00:03.900."""
    import test_frame_size as FS
    import test_pipeline as T
    from lib.client_db import build as build_db
    from lib.discover import run_discovery
    from lib.media import preflight
    from lib.plan import compile_plan
    from lib.previews import render_all
    root, p, _words = T.make_project(tmp / "c")
    ctx = common.Context(root, home=tmp / "home")
    if broll:
        (root / "data/Broll").mkdir()
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(root / "data/Broll/stock.mp4")], check=True)
    with common.use_context(ctx):
        build_db(p, run_discovery(p)["inventory"])
        preflight(p, [root / "data/Raw/CLIP1.mov"])
        FS._stub_edit(p)
        if broll:
            ed = common.read_json(p.p("01_analysis/edit-decisions.json"))
            ed["decisions"][0]["graphics"].append({"id": "BR_001", "template": "broll_video", "start": "00:00:02.000",
                                                   "end": "00:00:03.900", "video": "data/Broll/stock.mp4", "in": 0.5})
            common.write_json(p.p("01_analysis/edit-decisions.json"), ed)
        assert compile_plan(p)["ok"]
        render_all(p, composite_preview=True)
    return ctx, p


class TestPreviewVideoParallel(unittest.TestCase):
    """preview-video renders the timeline in chunks in parallel and concatenates them: the same frames as one pass."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.ctx, cls.p = build_preview_project(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def render(self, **kw):
        import contextlib
        import io
        from lib.preview_video import render
        with common.use_context(self.ctx), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return render(self.p, width=270, **kw)

    def compare(self, workers, min_chunk_frames, chunks, frames):
        """One pass vs `workers` chunks: same frame count, duration, codec; frames at `frames` (and their neighbours) match."""
        import numpy as np
        from lib.media import probe
        one = self.render(workers=1)
        self.assertTrue(one["ok"], one)
        want = decode_frames(one["video"])
        pr1 = probe(Path(one["video"]))
        self.assertEqual((len(want), one["chunks"]), (one["frames"], 1))
        par = self.render(workers=workers, min_chunk_frames=min_chunk_frames)
        self.assertTrue(par["ok"], par)
        self.assertEqual(par["chunks"], chunks)
        got = decode_frames(par["video"])
        pr2 = probe(Path(par["video"]))
        self.assertEqual((par["frames"], par["size"], par["layers"]), (one["frames"], one["size"], one["layers"]))
        self.assertEqual(len(got), len(want))                            # the same frame count ...
        self.assertAlmostEqual(pr2["duration_s"], pr1["duration_s"], delta=0.05)   # ... and duration
        self.assertEqual(pr2["video"]["fps_fraction"], pr1["video"]["fps_fraction"])
        self.assertEqual((pr2["video"]["codec"], pr2["video"]["pix_fmt"]), (pr1["video"]["codec"], pr1["video"]["pix_fmt"]))
        self.assertTrue(pr2["audio"] and pr2["audio"][0]["codec"] == pr1["audio"][0]["codec"])
        diff = lambda a, b: float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())
        n = len(want)
        for k in frames:
            with self.subTest(frame=k):
                # two lossy encodings of the same picture (x264 CRF 23 on a busy test pattern) differ by ~2 grey
                # levels; a frame off by one (the frame counter and the bouncing ball move) differs by 7 or more
                self.assertLess(diff(want[k], got[k]), 4.0)
                for j in (k - 1, k + 1):
                    if 0 <= j < n:
                        self.assertLess(diff(want[k], got[k]), diff(want[j], got[k]), f"frame {k} is closer to {j}")
        self.assertEqual(list((Path(par["video"]).parent).glob("_preview_chunk*")), [])     # no chunk files left behind
        return one, par

    def test_chunks_in_parallel_equal_one_pass(self):
        n, third = 288, 96
        self.compare(3, 8, 3, (0, 1, third - 1, third, third + 1, 2 * third - 1, 2 * third, 2 * third + 1, n // 2, n - 1))

    def test_a_chunk_that_starts_inside_a_broll_clip(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            case = TestPreviewVideoParallel.__new__(TestPreviewVideoParallel)
            unittest.TestCase.__init__(case)
            case.ctx, case.p = build_preview_project(tmp, broll=True)
            # 8 chunks of 36 frames: the join at frame 72 is inside the B-roll event (frames 48-93)
            one, par = case.compare(8, 8, 8, (47, 48, 49, 71, 72, 73, 93, 94, 150, 287))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_short_timeline_is_one_chunk(self):
        r = self.render(min_chunk_frames=10 ** 6)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["chunks"], 1)


if __name__ == "__main__":
    unittest.main()
