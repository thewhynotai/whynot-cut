"""T2.14 (3.0): performance changes that must not change the output. One test per change, each proving the fast path
gives the same result as the slow one (timing is reported by the task, never asserted here).

Run one file: <engine runtime python> -s -B -m unittest discover -s whynot-cut/tests -p test_perf.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import os
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
            self.assertEqual({v for _, v in seen}, {root.resolve()})        # Context resolves its root (macOS /var -> /private/var)
        finally:
            shutil.rmtree(root, ignore_errors=True)


    def interrupt_at(self, seconds):
        import _thread
        import threading
        t = threading.Timer(seconds, _thread.interrupt_main)
        t.start()
        return t

    def test_ctrl_c_cancels_the_queued_items(self):
        """T2.14 review I1: 12 slow items, 2 workers, Ctrl+C at 0.05 s -> raised at once, no queued item starts."""
        import threading
        import time
        from lib.parallel import parallel_map
        started, lock = [], threading.Lock()

        def slow(i):
            with lock:
                started.append(i)
            time.sleep(0.4)
            return i
        t0 = time.monotonic()
        timer = self.interrupt_at(0.05)
        try:
            with self.assertRaises(KeyboardInterrupt):
                parallel_map(slow, range(12), workers=2)
        finally:
            timer.cancel()
        # not after the 12 items (12 x 0.4 s / 2 workers = 2.4 s); the bound leaves room for a busy machine (a full
        # suite next to GPU jobs measured 1.5 s for the raise), the real proof is the line after the sleep below
        self.assertLess(time.monotonic() - t0, 2.0)
        time.sleep(0.8)                                                   # the running two end; nothing new starts
        self.assertEqual(sorted(started), [0, 1])

    def test_ctrl_c_kills_the_processes_the_workers_registered(self):
        import time
        from lib.parallel import parallel_map, track, untrack
        procs = []

        def child(_):
            p = track(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]))
            procs.append(p)
            try:
                return p.wait()
            finally:
                untrack(p)
        import _thread
        import threading

        def when_both_run():                                            # Ctrl+C once both children are registered
            end = time.monotonic() + 60                                  # (a fixed 1 s was too early on a busy machine)
            while len(procs) < 2 and time.monotonic() < end:
                time.sleep(0.02)
            time.sleep(0.1)
            _thread.interrupt_main()
        timer = threading.Thread(target=when_both_run, daemon=True)
        timer.cancel = lambda: None
        timer.start()
        try:
            with self.assertRaises(KeyboardInterrupt):
                parallel_map(child, range(2), workers=2)
        finally:
            timer.cancel()
        t0 = time.monotonic()
        for p in procs:
            p.wait(timeout=10)
        self.assertEqual(len(procs), 2)
        self.assertLess(time.monotonic() - t0, 5)


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


    def test_seeded_fuzz_the_index_finds_what_the_full_scan_finds(self):
        """T2.14 review I5: >= 2000 seeded cases (small vocabularies with repeats, Arabic spelling variants that norm()
        folds together, random edits, min_ratio values that land exactly on 2M/(T+n)): wherever the full scan finds a
        window at or above min_ratio, the indexed lookup returns the same (ratio, start, length); where it finds none,
        neither does the index. Made one stricter (`need + 1` in _window_starts), this test fails."""
        import random
        from lib.plan import norm
        from lib.transcribe import _best_window, _token_index
        rng = random.Random(20261012)
        arabic = ["إيمانهم", "ايمانهم", "آمانه", "الْفِكْرَةِ", "الفكرة", "مسئول", "مسؤول", "شئون", "شؤون", "في", "من",
                  "هي", "شوف", "أحمد", "احمد", "إلى", "الى", "مَرِيض", "مريض", "ٱلله", "الله"]
        ratios = [0.6, 2 / 3, 4 / 7, 0.5, 0.75, 0.8, 1.0, 0.3, 0.65, 5 / 9, 0.7]
        compared, boundary, found, bad = 0, 0, 0, []
        while compared < 2200:
            vocab = rng.sample(arabic, rng.randint(1, 8)) + [f"w{i}" for i in range(rng.randint(1, 32))]
            raw = [rng.choice(vocab) for _ in range(rng.randint(4, 45))]
            if rng.random() < 0.8:                          # a stretch of the transcript, then a few edits
                a = rng.randrange(len(raw))
                q = raw[a:a + rng.randint(3, 10)]
                for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
                    op, j = rng.random(), rng.randrange(len(q) + 1)
                    if op < 0.35 and j < len(q):
                        q[j] = rng.choice(vocab + ["زائد"])           # a word differs
                    elif op < 0.55 and j < len(q) and len(q) > 1:
                        del q[j]                                     # the writer dropped a word
                    elif op < 0.8:
                        q.insert(j, rng.choice(vocab + ["زائد"]))     # ... or added one
                    elif j < len(q):
                        q.insert(j, q[j])                            # a repeated word
            else:                                           # words from the vocabulary in any order
                q = [rng.choice(vocab) for _ in range(rng.randint(3, 9))]
            seq = [norm(w) for w in raw]
            qt = norm(" ".join(q)).split()
            if len(qt) < 3:                                 # document_quotes skips those
                continue
            mr = rng.choice(ratios)
            full = _best_window(seq, qt, mr, None)
            fast = _best_window(seq, qt, mr, _token_index(seq))
            compared += 1
            if full[0] >= mr:
                found += 1
                boundary += full[0] == mr
                if fast != full:
                    bad.append((raw, q, mr, full, fast))
            elif fast[0] >= mr:
                bad.append((raw, q, mr, full, fast))
        self.assertEqual(bad[:3], [])
        self.assertGreater(found, 1000)                     # most cases do find their quote
        self.assertGreater(boundary, 50)                    # and many sit exactly on the bound


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

    def test_another_engine_or_extractor_version_rebuilds_the_cache(self):
        """T2.14 review I4: cached texts are only reused by the engine and the extractor version that made them."""
        from lib import discover, stamps
        first, _, _ = self.run_counting()
        n = first["inventory"]["file_count"]
        _, fp, rd = self.run_counting()
        self.assertEqual((fp, rd), (0, 0))
        head = json.loads((self.p.output / "discovery/discovery-cache.json").read_text(encoding="utf-8"))
        self.assertEqual((head["engine_version"], head["extractor"]), (stamps.engine_version(), discover.READ_DOC_VERSION))
        with mock.patch.object(stamps, "engine_version", return_value="99.0.0"):
            _, fp, rd = self.run_counting()
            self.assertEqual(fp, n)                                       # everything again
            self.assertGreaterEqual(rd, 2)
            _, fp, rd = self.run_counting()
            self.assertEqual((fp, rd), (0, 0))                            # and cached under that version
        with mock.patch.object(discover, "READ_DOC_VERSION", discover.READ_DOC_VERSION + 1):
            _, fp, rd = self.run_counting()
            self.assertEqual(fp, n)
            self.assertGreaterEqual(rd, 2)

    def test_a_replaced_file_with_the_same_size_and_time_is_read_again(self):
        """M3: a copy that keeps size and mtime (robocopy /COPY:DAT) still has a new file id where the volume has ids."""
        import os
        self.run_counting()
        ref = self.root / "data/Ref/style.md"
        old = ref.read_bytes()
        st = ref.stat()
        if not st.st_ino:
            self.skipTest("this filesystem reports no file ids")
        repl = ref.with_name("style.md.new")
        repl.write_bytes(b"!" + old[1:])                                 # same length, other content
        self.assertEqual(repl.stat().st_size, st.st_size)
        os.utime(repl, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(repl, ref)
        st2 = ref.stat()
        self.assertEqual((st2.st_size, st2.st_mtime_ns), (st.st_size, st.st_mtime_ns))
        if st2.st_ino == st.st_ino:
            self.skipTest("the volume reused the file id")
        _, fp, rd = self.run_counting()
        self.assertEqual((fp, rd), (1, 1))

    def test_inbox_audits_again_when_the_environment_is_old_or_another_engines(self):
        """M4: `inbox` keeps environment.json for a day and for one engine version, then audits again."""
        import os
        import time
        from lib import discover, stamps
        from lib.onboard import inbox
        discover.run_discovery(self.p)
        env_file = self.p.output / "discovery/environment.json"
        self.assertEqual(json.loads(env_file.read_text(encoding="utf-8"))["engine_version"], stamps.engine_version())

        def audits():
            with mock.patch.object(discover, "audit_environment", wraps=discover.audit_environment) as audit:
                inbox(self.root)
                return audit.call_count
        self.assertEqual(audits(), 0)                                     # fresh, this engine: kept
        old = time.time() - 25 * 3600
        os.utime(env_file, (old, old))
        self.assertEqual(audits(), 1)                                     # a day old: audited again ...
        self.assertEqual(audits(), 0)                                     # ... and fresh again
        with mock.patch.object(stamps, "engine_version", return_value="99.0.0"):
            self.assertEqual(audits(), 1)                                 # another engine version
        self.assertEqual(audits(), 1)                                     # (and back)

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


def build_preview_project(tmp: Path, broll: bool = False, broll_in: float = 0.5):
    """A planned and previewed 12 s synthetic reel (270x480 preview): (Context, Paths). `broll`: a licensed-looking clip
    (testsrc2 5 s, so every frame is recognisable) fills 00:02.000-00:03.900 from `broll_in` s into the clip."""
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
                                                   "end": "00:00:03.900", "video": "data/Broll/stock.mp4", "in": broll_in})
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
                    if 0 <= j < n and diff(want[j], want[k]) >= 4.0:     # a held frame: its neighbour IS the picture
                        self.assertLess(diff(want[k], got[k]), diff(want[j], got[k]), f"frame {k} is closer to {j}")
        self.assertEqual(list((Path(par["video"]).parent).glob("_preview_chunk*")), [])     # no chunk files left behind
        return one, par

    def test_chunks_in_parallel_equal_one_pass(self):
        n, third = 288, 96
        self.compare(3, 8, 3, (0, 1, third - 1, third, third + 1, 2 * third - 1, 2 * third, 2 * third + 1, n // 2, n - 1))

    def test_a_dying_broll_decoder_is_an_error(self):
        """T2.14 review I3: a B-roll clip that does not decode is not silently replaced by the speaker."""
        from lib.errors import Guidance
        tmp = Path(tempfile.mkdtemp())
        try:
            case = TestPreviewVideoParallel.__new__(TestPreviewVideoParallel)
            unittest.TestCase.__init__(case)
            case.ctx, case.p = build_preview_project(tmp, broll=True)
            patch, hits = case.fake_decoder(lambda c: any("force_original" in str(x) for x in c),
                                            "import sys; sys.stderr.write('no such clip'); sys.exit(1)")
            with patch, self.assertRaises(Guidance) as cm:
                case.render(workers=2, min_chunk_frames=8)
            self.assertTrue(hits)
            self.assertIn("B-roll decoder (data/Broll/stock.mp4) ffmpeg exited with code 1: no such clip",
                          cm.exception.error)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

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

    def test_a_chunk_that_starts_after_a_short_broll_clip_ended(self):
        """T2.14 review 2, I1: a clip shorter than its event (5 s clip from 4.6 s: ~10 frames for the event 48-93). The
        chunk from frame 72 starts after the clip's last frame: it holds that frame, as the single pass does, and does
        not fail with "no frame decoded"."""
        tmp = Path(tempfile.mkdtemp())
        try:
            case = TestPreviewVideoParallel.__new__(TestPreviewVideoParallel)
            unittest.TestCase.__init__(case)
            case.ctx, case.p = build_preview_project(tmp, broll=True, broll_in=4.6)
            one, par = case.compare(8, 8, 8, (47, 48, 49, 56, 57, 58, 59, 71, 72, 73, 90, 93, 94, 108, 287))
            self.assertTrue(par["ok"], par)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def counting_popen(self, interrupt_on=None):
        """Patch Popen (real processes) and record, for the rawvideo ffmpeg of the render: each command, the largest
        number alive at once, and for each B-roll decoder how many frames its chunk's encoder had received when it was
        stopped. `interrupt_on(n)`: every source decoder stalls (sleeps), and Ctrl+C (interrupt_main) comes while the
        n-th one starts, inside _Watch.spawn."""
        import _thread
        import threading
        from lib import preview_video as PV
        real, rec = subprocess.Popen, {"cmds": [], "procs": [], "peak": 0, "broll_stopped_at": [], "src": 0}
        lock, enc_of = threading.Lock(), {}

        class Counting:
            def __init__(self, f):
                self.f, self.n = f, 0

            def write(self, b):
                self.n += 1
                return self.f.write(b)

            def __getattr__(self, a):
                return getattr(self.f, a)

        def popen(cmd, *a, **kw):
            if not (isinstance(cmd, list) and "rawvideo" in cmd):
                return real(cmd, *a, **kw)
            tid = threading.get_ident()
            if interrupt_on and self.is_source_decoder(cmd):
                with lock:
                    rec["src"] += 1
                    n = rec["src"]
                if interrupt_on(n):
                    rec["interrupted_at"] = __import__("time").monotonic()
                    _thread.interrupt_main()
                cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
            p = real(cmd, *a, **kw)
            with lock:
                rec["cmds"].append(cmd)
                rec["procs"].append(p)
                rec["peak"] = max(rec["peak"], sum(q.poll() is None for q in rec["procs"]))
            if kw.get("stdin") == subprocess.PIPE:                        # a chunk's encoder: count its frames
                p.stdin = enc_of[tid] = Counting(p.stdin)
            elif any("force_original" in str(c) for c in cmd):            # a B-roll decoder: when is it stopped?
                kill, enc = p.kill, enc_of.get(tid)

                def stopped():
                    rec["broll_stopped_at"].append(enc.n if enc else None)
                    kill()
                p.kill = stopped
            return p
        return mock.patch.object(PV.subprocess, "Popen", side_effect=popen), rec

    def test_at_most_six_ffmpeg_with_threads_and_broll_closed_after_its_event(self):
        """T2.14 review 2, M1 (guards I2): the default worker count and chunk length keep a reel to 2 chunks and a short
        one to 1; a chunked render runs <= 6 ffmpeg at once (2 x decoder + encoder + B-roll decoder), each with `-threads
        N >= 1`, and a B-roll decoder is stopped when its event ends, not at the end of the chunk."""
        from lib import preview_video as PV
        from lib.stamps import read_compiled
        if (os.cpu_count() or 1) < 2:
            self.skipTest("one CPU: the preview is one pass")
        self.assertLessEqual(len(PV.chunk_bounds(40 * 24, PV.PREVIEW_WORKERS)) - 1, 2)   # a 40 s reel: <= 2 chunks
        self.assertEqual(len(PV.chunk_bounds(8 * 24, PV.PREVIEW_WORKERS)) - 1, 1)        # an 8 s one: one pass
        tmp = Path(tempfile.mkdtemp())
        try:
            case = TestPreviewVideoParallel.__new__(TestPreviewVideoParallel)
            unittest.TestCase.__init__(case)
            case.ctx, case.p = build_preview_project(tmp, broll=True)
            patch, rec = self.counting_popen()
            with patch:
                r = case.render(min_chunk_frames=8)                       # the default worker count
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["chunks"], 2)
            self.assertLessEqual(rec["peak"], 6, rec["peak"])
            self.assertEqual(len(rec["cmds"]), 5)                         # 2 x (decoder + encoder) + 1 B-roll decoder
            for cmd in rec["cmds"]:
                with self.subTest(cmd=cmd[:6]):
                    self.assertIn("-threads", cmd)
                    self.assertGreaterEqual(int(cmd[cmd.index("-threads") + 1]), 1)
            ev = next(e for e in read_compiled(case.p.p("01_analysis/timeline-spec.json"))["events"]
                      if e["template"] == "broll_video")
            self.assertLess(ev["end_frame"], 144)                         # the event is inside the first chunk (0-143)
            self.assertEqual(rec["broll_stopped_at"], [ev["end_frame"]])  # stopped at its end frame, not at 144
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_watchdog_counts_the_source_span_of_a_chunk(self):
        """T2.14 review 2, M3: the second chunk's decoder decodes the source from the start to the chunk's end."""
        from lib import preview_video as PV
        got = []
        with mock.patch.object(PV, "chunk_timeout_s", lambda d: got.append(d) or 600.0):
            r = self.render(workers=2, min_chunk_frames=8)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(min(got), 144 / 24, delta=0.5)             # 0-143: its timeline and source span alike
        self.assertGreaterEqual(max(got), 288 / 24 - 0.1)                 # 144-287: the source up to frame 287, not 6 s

    def test_ctrl_c_during_a_chunked_render(self):
        """T2.14 review 2, M4: Ctrl+C while the second chunk starts its decoder (stalled decoders: only a kill ends them).
        The KeyboardInterrupt comes out, every ffmpeg of the render is killed at once (registered with the parallel map
        in _Watch.spawn), and a chunk file left by a killed encoder can be deleted."""
        import threading
        import time
        patch, rec = self.counting_popen(interrupt_on=lambda n: n == 2)
        t0 = time.monotonic()
        try:
            with patch, self.assertRaises(KeyboardInterrupt):
                self.render(workers=2, min_chunk_frames=8)
            # from the Ctrl+C, not from the render's start (its setup took 18 s on a busy machine)
            self.assertLess(time.monotonic() - rec["interrupted_at"], 10)
            self.assertLess(time.monotonic() - t0, 120)
            self.assertEqual(len(rec["procs"]), 4)                        # 2 encoders, 2 (stalled) decoders
            t1 = time.monotonic()
            for p in rec["procs"]:
                p.wait(timeout=15)
            self.assertLess(time.monotonic() - t1, 5)                     # killed by the map, not the ~28 s watchdog
        finally:
            for t in threading.enumerate():
                if t.name.startswith("wnc"):
                    t.join(timeout=30)
        for c in self.p.p("08_quality_control/preview").glob("_preview_chunk*"):
            c.unlink()                                                    # left by a killed encoder: harmless

    def test_a_locked_chunk_file_never_replaces_the_ctrl_c(self):
        """T2.14 review 2, M2: deleting a chunk file still held by a killed encoder (WinError 32) is not an error."""
        from lib import parallel
        out = self.p.p("08_quality_control/preview")
        real = Path.unlink

        def interrupted(fn, items, workers):
            for i in items:
                (out / f"_preview_chunk_{i}.mp4").write_bytes(b"x")
            raise KeyboardInterrupt

        def unlink(path, *a, **kw):
            if path.name.startswith("_preview_chunk_"):
                raise PermissionError(32, "The process cannot access the file")
            return real(path, *a, **kw)
        try:
            with mock.patch.object(parallel, "parallel_map", interrupted), \
                    mock.patch.object(Path, "unlink", unlink), self.assertRaises(KeyboardInterrupt):
                self.render(workers=2, min_chunk_frames=8)
        finally:
            for c in out.glob("_preview_chunk*"):
                real(c)

    def fake_decoder(self, match, script, times=10 ** 6):
        """Patch Popen: the first `times` ffmpeg commands that `match` run `python -c script` instead."""
        from lib import preview_video as PV
        real, hits = subprocess.Popen, []

        def popen(cmd, *a, **kw):
            if isinstance(cmd, list) and match(cmd) and len(hits) < times:
                hits.append(cmd)
                cmd = [sys.executable, "-c", script]
            return real(cmd, *a, **kw)
        return mock.patch.object(PV.subprocess, "Popen", side_effect=popen), hits

    @staticmethod
    def is_source_decoder(cmd):
        return ("rawvideo" in cmd and cmd[-1] == "-" and "-s" not in cmd
                and not any("force_original" in str(c) for c in cmd))

    def test_a_dying_source_decoder_is_an_error_not_a_black_chunk(self):
        """T2.14 review I3: one pass and a chunk of a parallel render alike."""
        from lib.errors import Guidance, describe
        die = "import sys; sys.stderr.write('fake decoder died'); sys.exit(3)"
        for kw in ({"workers": 1}, {"workers": 2, "min_chunk_frames": 8}):
            with self.subTest(**kw):
                patch, hits = self.fake_decoder(self.is_source_decoder, die)
                with patch, self.assertRaises(Guidance) as cm:
                    self.render(**kw)
                self.assertTrue(hits)
                doc = describe(cm.exception)
                self.assertIs(doc["ok"], False)
                self.assertIn("source decoder ffmpeg exited with code 3: fake decoder died", doc["error"])
                self.assertEqual(list(self.p.p("08_quality_control/preview").glob("_preview_chunk*")), [])
        patch, hits = self.fake_decoder(self.is_source_decoder, "import sys; sys.exit(0)")   # exit 0, no frame at all
        with patch, self.assertRaises(Guidance) as cm:
            self.render(workers=1)
        self.assertIn("no frame decoded", cm.exception.error)

    def test_a_process_windows_could_not_start_is_retried_once(self):
        from lib import preview_video as PV
        from lib.errors import Guidance
        patch, hits = self.fake_decoder(self.is_source_decoder, "import sys; sys.exit(7)", times=1)
        with patch, mock.patch.object(PV, "DLL_INIT_FAILED", (7,)):
            r = self.render(workers=1)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(hits), 1)
        patch, hits = self.fake_decoder(self.is_source_decoder, "import sys; sys.exit(7)", times=2)
        with patch, mock.patch.object(PV, "DLL_INIT_FAILED", (7,)), self.assertRaises(Guidance):
            self.render(workers=1)                                        # only once
        self.assertEqual(len(hits), 2)

    def test_a_stalled_decoder_is_stopped_by_the_watchdog(self):
        """M1: a chunk past its deadline (T2.15: 10 s + 3 x its duration; 1.5 s here) kills its ffmpeg and says so."""
        import time
        from lib import preview_video as PV
        from lib.errors import Guidance
        patch, hits = self.fake_decoder(self.is_source_decoder, "import time; time.sleep(60)")
        t0 = time.monotonic()
        with patch, mock.patch.object(PV, "chunk_timeout_s", lambda d: 1.5), self.assertRaises(Guidance) as cm:
            self.render(workers=2, min_chunk_frames=8)
        self.assertLess(time.monotonic() - t0, 30)
        self.assertIn("did not finish within 2 s", cm.exception.error)

    def test_a_short_timeline_is_one_chunk(self):
        r = self.render(min_chunk_frames=10 ** 6)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["chunks"], 1)


if __name__ == "__main__":
    unittest.main()
