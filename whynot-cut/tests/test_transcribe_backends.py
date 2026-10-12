"""Transcription performance and backends (3.0 T2.12: engine IM-13, IM-14, MI-12; decision D9).

No real Whisper model is ever loaded here: faster-whisper, mlx-whisper and huggingface_hub are replaced by fake modules
in sys.modules, and the chunk runner gets a fake decoder. The live checks (GPU timing on EP02, MLX on a Mac) are in the
task report; the MLX/CT2 parity test below runs only on a Mac with both backends and WHYNOT_PARITY_AUDIO set.
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))

from lib import common  # noqa: E402
from lib import whisper_backends as WB  # noqa: E402
from lib.common import Context, Paths, read_json, use_context, write_json  # noqa: E402

SR = 16000
_QUIET = []


def setUpModule():
    """The engine logs progress to stderr; keep the test output clean."""
    from lib import transcribe as T
    for target in (WB, common, T):
        p = mock.patch.object(target, "log", lambda *a, **k: None)
        p.start()
        _QUIET.append(p)


def tearDownModule():
    while _QUIET:
        _QUIET.pop().stop()


# --------------------------------------------------------------------------- fakes
class FakeWord:
    def __init__(self, word, start, end, p=0.9):
        self.word, self.start, self.end, self.probability = word, start, end, p


class FakeSeg:
    def __init__(self, text, start, end, words):
        self.text, self.start, self.end, self.words = text, start, end, words
        self.avg_logprob, self.no_speech_prob, self.compression_ratio = -0.21, 0.01, 1.3


def ct2_segments():
    return [FakeSeg(" أهلا بيك", 0.5, 1.4, [FakeWord(" أهلا", 0.5, 0.9), FakeWord(" بيك", 1.0, 1.4)]),
            FakeSeg(" Botox", 2.0, 2.6, [FakeWord(" Botox", 2.0, 2.6, 0.7)])]


class FakeWhisperModel:
    instances: list = []
    fail_on_cuda = False
    seq_fn = None              # (audio, kw) -> segments of a sequential decode
    fail_names = False         # loading by model NAME fails (no network)

    def __init__(self, model_size_or_path, device="auto", compute_type="default", cpu_threads=0, download_root=None,
                 **kw):
        if FakeWhisperModel.fail_names and not os.path.isdir(str(model_size_or_path)):
            raise OSError("cannot reach huggingface.co")
        self.src, self.device, self.compute_type = model_size_or_path, device, compute_type
        self.cpu_threads, self.download_root = cpu_threads, download_root
        self.calls = []
        FakeWhisperModel.instances.append(self)

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        if self.device == "cuda" and FakeWhisperModel.fail_on_cuda:
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
        segs = FakeWhisperModel.seq_fn(audio, kw) if FakeWhisperModel.seq_fn else ct2_segments()
        return iter(segs), SimpleNamespace(language=kw.get("language") or "ar", language_probability=0.97,
                                                     duration=len(audio) / SR)


class FakeBatched:
    instances: list = []
    segments = None            # the batched pass's segments (default: ct2_segments())
    max_ok = 99                # a larger batch raises CUDA out of memory

    def __init__(self, model):
        self.model, self.calls = model, []
        FakeBatched.instances.append(self)

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        if kw["batch_size"] > FakeBatched.max_ok:
            raise RuntimeError("CUDA failed with error out of memory")
        return iter(FakeBatched.segments or ct2_segments()), SimpleNamespace(
            language=kw.get("language") or "ar", language_probability=0.97, duration=len(audio) / SR)


def fake_faster_whisper():
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = FakeWhisperModel
    fw.BatchedInferencePipeline = FakeBatched
    utils = types.ModuleType("faster_whisper.utils")
    utils._MODELS = {"large-v3": "Systran/faster-whisper-large-v3",
                     "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo"}
    fw.utils = utils
    return {"faster_whisper": fw, "faster_whisper.utils": utils}


def fake_ctranslate2(cuda_devices=1):
    ct = types.ModuleType("ctranslate2")
    ct.get_cuda_device_count = lambda: cuda_devices
    return ct


def fake_mlx_whisper(calls):
    m = types.ModuleType("mlx_whisper")

    def transcribe(audio, *, path_or_hf_repo, **kw):
        calls.append(dict(kw, path_or_hf_repo=path_or_hf_repo, samples=len(audio)))
        return {"text": "أهلا بيك Botox", "language": kw.get("language") or "ar", "segments": [
            {"id": 0, "seek": 0, "start": 0.5, "end": 1.4, "text": " أهلا بيك", "tokens": [1, 2], "temperature": 0.0,
             "avg_logprob": -0.21, "compression_ratio": 1.3, "no_speech_prob": 0.01,
             "words": [{"word": " أهلا", "start": 0.5, "end": 0.9, "probability": 0.9},
                       {"word": " بيك", "start": 1.0, "end": 1.4, "probability": 0.9}]},
            {"id": 1, "seek": 0, "start": 2.0, "end": 2.6, "text": " Botox", "tokens": [3], "temperature": 0.0,
             "avg_logprob": -0.21, "compression_ratio": 1.3, "no_speech_prob": 0.01,
             "words": [{"word": " Botox", "start": 2.0, "end": 2.6, "probability": 0.7}]}]}
    m.transcribe = transcribe
    return m


class _Home(unittest.TestCase):
    """A throwaway engine home (models/, bench cache) and fresh fakes per test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t212-"))
        self.home = self.tmp / "home"
        (self.home / "models").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        FakeWhisperModel.instances, FakeBatched.instances = [], []
        FakeWhisperModel.fail_on_cuda = FakeWhisperModel.fail_names = False
        FakeWhisperModel.seq_fn = FakeBatched.segments = None
        FakeBatched.max_ok = 99

    def fakes(self, cuda=1, cuda_missing=()):
        mods = dict(fake_faster_whisper(), ctranslate2=fake_ctranslate2(cuda))
        p = mock.patch.dict(sys.modules, mods)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch("lib.plat.cuda_libs_missing", return_value=list(cuda_missing))
        q.start()
        self.addCleanup(q.stop)

    def snapshot(self, repo="Systran/faster-whisper-large-v3", rev="abc123", complete=True, ref=True, files=None):
        d = self.home / "models" / ("models--" + repo.replace("/", "--"))
        s = d / "snapshots" / rev
        s.mkdir(parents=True)
        for f in files or (["config.json", "tokenizer.json", "preprocessor_config.json"]
                           + (["model.bin"] if complete else [])):
            (s / f).write_bytes(b"x" * 64)
        if ref:
            (d / "refs").mkdir()
            (d / "refs" / "main").write_text(rev)
        return s


# --------------------------------------------------------------------------- threads
class TestCpuThreads(unittest.TestCase):
    def test_physical_cores_is_a_positive_int_not_above_logical(self):
        n = WB.physical_cores()
        self.assertIsInstance(n, int)
        self.assertGreaterEqual(n, 1)
        self.assertLessEqual(n, os.cpu_count() or n)

    def test_auto_means_physical_cores(self):
        with mock.patch.object(WB, "physical_cores", return_value=12):
            self.assertEqual(WB.cpu_threads({"cpu_threads": "auto"}), 12)
            self.assertEqual(WB.cpu_threads({}), 12)
            self.assertEqual(WB.cpu_threads({"cpu_threads": 0}), 12)
            self.assertEqual(WB.cpu_threads({"cpu_threads": None}), 12)

    def test_explicit_count_wins(self):
        with mock.patch.object(WB, "physical_cores", return_value=12):
            self.assertEqual(WB.cpu_threads({"cpu_threads": 6}), 6)
            self.assertEqual(WB.cpu_threads({"cpu_threads": "8"}), 8)

    def test_shipped_default_is_auto(self):
        cfg = read_json(common.CONFIG_DIR / "transcription.json")
        self.assertEqual(cfg["cpu_threads"], "auto")
        self.assertEqual(cfg["backend"], "auto")
        self.assertGreater(cfg["batch_size"], 1)
        self.assertEqual(cfg["long_clip_minutes"], 10)


# --------------------------------------------------------------------------- backend selection
class TestBackendSelection(unittest.TestCase):
    def pick(self, want, sysname, machine, mlx=True, verified=True):
        return WB.choose_backend({"backend": want, "mlx_verified": verified}, sysname=sysname, machine=machine,
                                 mlx_ok=lambda: mlx)

    def test_auto_on_apple_silicon_with_verified_mlx_is_mlx(self):
        self.assertEqual(self.pick("auto", "darwin", "arm64")[0], "mlx")

    def test_auto_never_picks_unverified_mlx(self):
        """M6: until the Mac parity test sets mlx_verified, auto stays on the verified faster-whisper."""
        name, note = self.pick("auto", "darwin", "arm64", verified=False)
        self.assertEqual(name, "ct2")
        self.assertIn("mlx_verified", note)
        self.assertFalse(read_json(common.CONFIG_DIR / "transcription.json")["mlx_verified"])

    def test_explicit_mlx_works_before_verification(self):
        self.assertEqual(self.pick("mlx", "darwin", "arm64", verified=False), ("mlx", None))

    def test_auto_on_apple_silicon_without_mlx_falls_back_to_ct2_with_a_note(self):
        name, note = self.pick("auto", "darwin", "arm64", mlx=False)
        self.assertEqual(name, "ct2")
        self.assertIn("mlx-whisper", note)

    def test_auto_elsewhere_is_ct2_silently(self):
        for sysname, machine in (("win32", "AMD64"), ("darwin", "x86_64"), ("linux", "x86_64")):
            self.assertEqual(self.pick("auto", sysname, machine), ("ct2", None))

    def test_mlx_forced_off_apple_silicon_falls_back_with_a_note(self):
        name, note = self.pick("mlx", "win32", "AMD64")
        self.assertEqual(name, "ct2")
        self.assertIn("Apple Silicon", note)

    def test_ct2_and_legacy_name(self):
        self.assertEqual(self.pick("ct2", "darwin", "arm64"), ("ct2", None))
        self.assertEqual(self.pick("faster-whisper", "darwin", "arm64"), ("ct2", None))   # 2.x transcription.json

    def test_unknown_backend_is_an_error_with_the_choices(self):
        with self.assertRaises(ValueError) as cm:
            self.pick("whisper.cpp", "win32", "AMD64")
        self.assertIn("auto", str(cm.exception))

    def test_explicit_argument_overrides_config(self):
        self.assertEqual(WB.choose_backend({"backend": "mlx"}, "ct2", sysname="darwin", machine="arm64",
                                           mlx_ok=lambda: True), ("ct2", None))


# --------------------------------------------------------------------------- offline snapshot
class TestOfflineSnapshot(_Home):
    def test_complete_snapshot_from_refs_main(self):
        s = self.snapshot()
        self.assertEqual(WB.snapshot_dir("large-v3", min_bytes=10), s)

    def test_partial_download_is_not_used(self):
        self.snapshot(complete=False)
        self.assertIsNone(WB.snapshot_dir("large-v3", min_bytes=10))

    def test_tiny_model_bin_is_partial(self):
        self.snapshot()
        self.assertIsNone(WB.snapshot_dir("large-v3", min_bytes=1000))

    def test_missing_refs_main_still_finds_the_complete_snapshot(self):
        s = self.snapshot(ref=False)   # an interrupted first download leaves no refs/main: offline it used to fail
        self.assertEqual(WB.snapshot_dir("large-v3", min_bytes=10), s)

    def test_unknown_model_or_no_cache(self):
        self.assertIsNone(WB.snapshot_dir("large-v3", min_bytes=10))
        self.assertIsNone(WB.snapshot_dir("no-such-model", min_bytes=10))

    def test_load_passes_the_snapshot_dir_and_threads(self):
        self.fakes(cuda=0)
        s = self.snapshot()
        with mock.patch.object(WB, "MIN_MODEL_BYTES", 10), mock.patch.object(WB, "physical_cores", return_value=7):
            model, dev, ct = WB.load_ct2("large-v3")
        self.assertEqual((dev, ct), ("cpu", "int8"))
        self.assertEqual(model.src, str(s))                 # a path: huggingface_hub is never asked (offline-safe)
        self.assertEqual(model.cpu_threads, 7)

    def test_load_without_a_complete_snapshot_downloads_by_name(self):
        self.fakes(cuda=0)
        with mock.patch.object(WB, "physical_cores", return_value=7):
            model, _, _ = WB.load_ct2("large-v3")
        self.assertEqual(model.src, "large-v3")
        self.assertEqual(model.download_root, str(self.home / "models"))

    def test_cuda_when_usable(self):
        self.fakes(cuda=1)
        model, dev, ct = WB.load_ct2("large-v3")
        self.assertEqual((dev, ct), ("cuda", "float16"))

    def test_cuda_libs_missing_means_cpu(self):
        self.fakes(cuda=1, cuda_missing=["cublas64_12.dll"])
        self.assertEqual(WB.load_ct2("large-v3")[1], "cpu")

    def test_transcribe_whisper_model_is_the_same_loader(self):
        """audio_clean.verify_cuts (T2.13) and relisten keep calling transcribe.whisper_model(model, ct)."""
        from lib import transcribe as T
        self.fakes(cuda=0)
        with mock.patch.object(WB, "physical_cores", return_value=5):
            model, dev, ct = T.whisper_model("large-v3")
        self.assertEqual((model.cpu_threads, dev, ct), (5, "cpu", "int8"))


# --------------------------------------------------------------------------- the runner (both backends)
SCHEMA_SEG = {"id", "start_ms", "end_ms", "text", "avg_logprob", "no_speech_prob", "compression_ratio", "words"}
SCHEMA_WORD = {"id", "segment_id", "word", "start_ms", "end_ms", "probability"}


class TestCt2Runner(_Home):
    audio = np.zeros(SR * 40, np.float32)

    def runner(self, **kw):
        return WB.make_runner("large-v3", vad=kw.pop("vad", True), backend="ct2", **kw)

    def test_batched_on_cuda_with_vad(self):
        self.fakes(cuda=1)
        run = self.runner(batch_size=8)
        r = run(self.audio, 0, None, "د. سامبل إكزامبل")
        self.assertEqual(len(FakeBatched.instances), 1)
        kw = FakeBatched.instances[0].calls[0]
        self.assertEqual(kw["batch_size"], 8)
        self.assertTrue(kw["vad_filter"])
        self.assertTrue(kw["word_timestamps"])
        self.assertEqual(kw["initial_prompt"], "د. سامبل إكزامبل")
        self.assertEqual(run.state["batch_size"], 8)
        self.assertEqual(run.state["device"], "cuda")
        self.assertEqual([w["word"] for w in r["words"]], ["أهلا", "بيك", "Botox"])

    def test_batch_size_from_config(self):
        self.fakes(cuda=1)
        with mock.patch.object(WB, "load_config", return_value={"batch_size": 12}):
            run = self.runner()
            run(self.audio, 0, None, None)
        self.assertEqual(FakeBatched.instances[0].calls[0]["batch_size"], 12)

    def test_sequential_when_batch_size_zero(self):
        self.fakes(cuda=1)
        run = self.runner(batch_size=0)
        run(self.audio, 0, None, None)
        self.assertEqual(FakeBatched.instances, [])
        kw = FakeWhisperModel.instances[0].calls[0]
        self.assertTrue(kw["vad_filter"])
        self.assertEqual(kw["beam_size"], 5)
        self.assertEqual(run.state["batch_size"], 0)

    def test_never_batched_without_vad(self):
        """The batched pipeline needs VAD to split the audio: a short clip (one pass, no VAD) stays sequential."""
        self.fakes(cuda=1)
        run = self.runner(batch_size=8, vad=False)
        run(self.audio, 0, None, None)
        self.assertEqual(FakeBatched.instances, [])
        self.assertFalse(FakeWhisperModel.instances[0].calls[0]["vad_filter"])

    def test_never_batched_on_cpu(self):
        self.fakes(cuda=0)
        run = self.runner(batch_size=8)
        run(self.audio, 0, None, None)
        self.assertEqual(FakeBatched.instances, [])
        self.assertEqual(run.state["device"], "cpu")

    def test_gpu_failure_retries_on_cpu_once(self):
        self.fakes(cuda=1)
        FakeWhisperModel.fail_on_cuda = True
        run = self.runner(batch_size=0)
        r = run(self.audio, 0, "ar", None)
        self.assertEqual(run.state["device"], "cpu")
        self.assertEqual(len(r["words"]), 3)
        run(self.audio, 0, "ar", None)
        self.assertEqual(len(FakeWhisperModel.instances), 2)      # loaded once on cuda, once on cpu, then reused

    def test_output_schema(self):
        self.fakes(cuda=0)
        r = self.runner()(self.audio, 0, None, None)
        self.assertEqual(set(r), {"segments", "words", "language", "language_probability"})
        self.assertTrue(all(set(s) == SCHEMA_SEG for s in r["segments"]))
        self.assertTrue(all(set(w) == SCHEMA_WORD for w in r["words"]))
        self.assertEqual(r["words"][0], {"id": 1, "segment_id": 1, "word": "أهلا", "start_ms": 500, "end_ms": 900,
                                         "probability": 0.9})
        self.assertEqual(r["segments"][1]["words"], [3])


class TestMlxRunner(_Home):
    def setUp(self):
        super().setUp()
        self.calls = []
        for p in (mock.patch.dict(sys.modules, {"mlx_whisper": fake_mlx_whisper(self.calls)}),
                  mock.patch.object(WB, "_platform", return_value=("darwin", "arm64")),   # an Apple Silicon Mac
                  mock.patch.object(WB, "MIN_MODEL_BYTES", 10)):
            p.start()
            self.addCleanup(p.stop)

    def test_same_schema_and_values_as_ct2(self):
        self.snapshot(repo=WB.MLX_REPOS["large-v3"], files=["config.json", "weights.safetensors"])
        mlx = WB.make_runner("large-v3", vad=True, backend="mlx")(np.zeros(SR * 5, np.float32), 0, None, "هنا")
        self.fakes(cuda=0)
        ct2 = WB.make_runner("large-v3", vad=True, backend="ct2")(np.zeros(SR * 5, np.float32), 0, None, "هنا")
        self.assertEqual(mlx["segments"], ct2["segments"])
        self.assertEqual(mlx["words"], ct2["words"])
        self.assertEqual(mlx["language"], "ar")
        self.assertEqual(WB.parity(mlx, ct2)["ok"], True)

    def test_options_word_timestamps_prompt_no_beam_search(self):
        snap = self.snapshot(repo=WB.MLX_REPOS["large-v3"], files=["config.json", "weights.safetensors"])
        run = WB.make_runner("large-v3", vad=True, backend="mlx")
        run(np.zeros(SR * 5, np.float32), 0, "ar", "د. سامبل إكزامبل")
        kw = self.calls[0]
        self.assertTrue(kw["word_timestamps"])
        self.assertEqual(kw["initial_prompt"], "د. سامبل إكزامبل")
        self.assertEqual(kw["language"], "ar")
        self.assertFalse(kw["condition_on_previous_text"])
        self.assertNotIn("beam_size", kw)                 # mlx-whisper has no beam search: it would raise
        self.assertEqual(kw["path_or_hf_repo"], str(snap))  # the local snapshot: no network when complete
        self.assertEqual(run.state["backend"], "mlx-whisper")
        self.assertEqual(run.state["device"], "metal")

    def test_downloads_into_the_engine_home_when_missing(self):
        got = {}
        hub = types.ModuleType("huggingface_hub")

        def snapshot_download(repo_id, cache_dir=None, **kw):
            got.update(repo_id=repo_id, cache_dir=cache_dir)
            return str(Path(cache_dir) / "fake-snapshot")
        hub.snapshot_download = snapshot_download
        with mock.patch.dict(sys.modules, {"huggingface_hub": hub}):
            WB.make_runner("large-v3-turbo", vad=False, backend="mlx")(np.zeros(SR, np.float32), 0, None, None)
        self.assertEqual(got["repo_id"], WB.MLX_REPOS["large-v3-turbo"])
        self.assertEqual(got["cache_dir"], str(self.home / "models"))


class TestParity(unittest.TestCase):
    def words(self, items):
        return {"words": [{"id": i + 1, "word": w, "start_ms": a, "end_ms": b} for i, (w, a, b) in enumerate(items)]}

    def test_within_80_ms_and_same_text_after_normalisation(self):
        a = self.words([("أهلاً", 500, 900), ("بالمدرسة", 1000, 1400)])
        b = self.words([("اهلا", 560, 950), ("بالمدرسه", 1070, 1460)])
        self.assertTrue(WB.parity(a, b)["ok"])

    def test_time_drift_beyond_tolerance_fails(self):
        a = self.words([("اهلا", 500, 900)])
        b = self.words([("اهلا", 600, 900)])
        r = WB.parity(a, b)
        self.assertFalse(r["ok"])
        self.assertEqual(r["max_drift_ms"], 100)

    def test_text_difference_fails(self):
        r = WB.parity(self.words([("اهلا", 0, 1)]), self.words([("سهلا", 0, 1)]))
        self.assertFalse(r["ok"])
        self.assertFalse(r["text_equal"])


@unittest.skipUnless(os.environ.get("WHYNOT_PARITY_AUDIO") and WB.mlx_available(),
                     "live MLX/CT2 parity: a Mac with mlx-whisper and WHYNOT_PARITY_AUDIO=<short Arabic wav>")
class TestLiveParity(unittest.TestCase):          # pragma: no cover - runs on the Mac test machine (T9.3)
    def test_arabic_fixture_parity(self):
        from lib.transcribe import whisper_audio
        audio = whisper_audio(Path(os.environ["WHYNOT_PARITY_AUDIO"]))
        prompt = common.load_config("transcription.json").get("initial_prompt")
        model = os.environ.get("WHYNOT_PARITY_MODEL", "large-v3")
        a = WB.make_runner(model, vad=False, backend="mlx")(audio, 0, "ar", prompt)
        b = WB.make_runner(model, vad=False, backend="ct2")(audio, 0, "ar", prompt)
        r = WB.parity(a, b, tol_ms=80)
        self.assertTrue(r["ok"], r)


# --------------------------------------------------------------------------- chunk checkpoints (MI-12)
class TestCheckpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t212-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paths = Paths(self.tmp / "C", "V1")
        self.cdir = self.tmp / "chunks"
        self.cdir.mkdir()
        self.audio = np.zeros(SR * 30, np.float32)
        self.plan = {"chunks": [[0, 10000], [10000, 20000], [20000, 30000]]}
        self.calls = []

    def fake(self, audio, start_ms, language, prompt):
        self.calls.append(start_ms)
        return {"language": "ar", "language_probability": 0.9,
                "segments": [{"id": 1, "start_ms": 100, "end_ms": 900, "text": "كلام", "avg_logprob": -0.2,
                              "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1]}],
                "words": [{"id": 1, "segment_id": 1, "word": "كلام", "start_ms": 100, "end_ms": 900, "probability": 0.9}]}

    def run_(self, model="large-v3", prompt="هنا", backend="ct2"):
        from lib.episode import run_chunks
        self.calls.clear()
        self.fake.__func__.backend = backend
        return run_chunks(self.paths, self.cdir, self.audio, self.plan, self.fake, model=model, prompt=prompt,
                          language=None, label="test")

    def test_checkpoints_record_model_prompt_backend(self):
        self.run_()
        rec = read_json(self.cdir / "chunk_000.json")
        self.assertEqual((rec["model"], rec["prompt"], rec["backend"]), ("large-v3", "هنا", "ct2"))

    def test_same_decoder_resumes(self):
        self.run_()
        r = self.run_()
        self.assertEqual(self.calls, [])
        self.assertEqual(r["ran"], 0)

    def test_model_change_redoes_every_chunk(self):
        self.run_()
        self.run_(model="large-v3-turbo")
        self.assertEqual(self.calls, [0, 10000, 20000])
        self.assertEqual(read_json(self.cdir / "chunk_001.json")["model"], "large-v3-turbo")

    def test_prompt_change_redoes(self):
        self.run_()
        self.run_(prompt="هناك")
        self.assertEqual(self.calls, [0, 10000, 20000])

    def test_backend_change_redoes(self):
        self.run_()
        self.run_(backend="mlx")
        self.assertEqual(self.calls, [0, 10000, 20000])

    def test_legacy_checkpoint_without_model_is_redone(self):
        self.run_()
        rec = read_json(self.cdir / "chunk_002.json")
        for k in ("model", "prompt", "backend"):
            rec.pop(k)
        write_json(self.cdir / "chunk_002.json", rec)
        self.run_()
        self.assertEqual(self.calls, [20000])

    def test_language_of_kept_first_chunk_is_reused(self):
        self.run_()
        (self.cdir / "chunk_001.json").unlink()
        seen = []
        orig = self.fake

        def spy(audio, start_ms, language, prompt):
            seen.append(language)
            return orig(audio, start_ms, language, prompt)
        spy.backend = "ct2"
        from lib.episode import run_chunks
        run_chunks(self.paths, self.cdir, self.audio, self.plan, spy, model="large-v3", prompt="هنا", language=None,
                   label="test")
        self.assertEqual(seen, ["ar"])


# --------------------------------------------------------------------------- long clips (IM-14)
class TestLongClip(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t212-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "C"
        for d in ("assets", "data/Raw", common.CLIENT_PROFILE_REL):
            (self.root / d).mkdir(parents=True)
        self.src = self.root / "data/Raw/C0001.mp4"
        self.src.write_bytes(b"not really a video" * 100)
        self.paths = Paths(self.root, "C0001")
        self.paths.ensure_project()
        self.calls = []

    def fake(self, audio, start_ms, language, prompt):
        self.calls.append({"start_ms": start_ms, "samples": len(audio), "prompt": prompt})
        return {"language": "ar", "language_probability": 0.9,
                "segments": [{"id": 1, "start_ms": 100, "end_ms": 900, "text": "كلام", "avg_logprob": -0.2,
                              "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1]}],
                "words": [{"id": 1, "segment_id": 1, "word": "كلام", "start_ms": 100, "end_ms": 900, "probability": 0.9}]}

    def go(self, seconds, profile=None, **kw):
        from lib import transcribe as T
        write_json(self.root / common.CLIENT_PROFILE_REL / "transcription.json",
                   profile or {"long_clip_minutes": 0.5, "chunk_minutes": 0.25, "initial_prompt": "هنا"})
        audio = np.zeros(int(SR * seconds), np.float32)
        self.vads = []

        def factory(model_size, vad, log_to=None, **k):
            self.vads.append(vad)
            self.fake.__func__.backend = "ct2"
            return self.fake
        with use_context(Context(self.root)), \
                mock.patch.object(T, "extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch.object(T, "whisper_audio", return_value=audio), \
                mock.patch.object(WB, "make_runner", side_effect=factory):
            return T.transcribe(self.paths, self.src, model_size="large-v3", **kw)

    def test_short_clip_is_one_pass_without_vad(self):
        r = self.go(20)
        self.assertEqual(self.vads, [False])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["start_ms"], 0)
        self.assertFalse(self.paths.p("02_transcription/chunks").exists() and
                         any(self.paths.p("02_transcription/chunks").glob("chunk_*.json")))
        self.assertNotIn("chunks", r["meta"])
        self.assertEqual(r["meta"]["backend"], "faster-whisper")

    def test_long_clip_uses_the_chunk_runner_with_vad_and_checkpoints(self):
        r = self.go(60)                     # > 0.5 min: chunks of ~15 s
        self.assertEqual(self.vads, [True])
        self.assertGreaterEqual(len(self.calls), 3)
        self.assertEqual(self.calls[0]["prompt"], "هنا")
        cdir = self.paths.p("02_transcription/chunks")
        self.assertEqual(len(list(cdir.glob("chunk_*.json"))), len(self.calls))
        self.assertEqual(r["meta"]["chunks"], len(self.calls))
        self.assertTrue(r["meta"]["vad"])
        tj = read_json(self.paths.p("02_transcription/transcript.json"))
        self.assertEqual(len(tj["segments"]), len(self.calls))
        self.assertEqual(tj["segments"][1]["start_ms"], self.calls[1]["start_ms"] + 100)
        # resumable: a crash after chunk 1 loses only the rest
        (cdir / "chunk_001.json").unlink()
        n = len(self.calls)
        self.calls.clear()
        self.go(60)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(list(cdir.glob("chunk_*.json"))), n)

    def test_force_redoes_every_chunk(self):
        self.go(60)
        n = len(self.calls)
        self.calls.clear()
        self.go(60, force=True)
        self.assertEqual(len(self.calls), n)

    def test_long_clip_threshold_zero_disables_chunking(self):
        self.go(60, profile={"long_clip_minutes": 0})
        self.assertEqual(self.vads, [False])
        self.assertEqual(len(self.calls), 1)

    def test_api_stays_backward_compatible(self):
        """audio_clean (T2.13) and the CLI call transcribe(paths, src, model_size=, language=)."""
        import inspect
        from lib import transcribe as T
        ps = inspect.signature(T.transcribe).parameters
        self.assertEqual(list(ps)[:6], ["paths", "source_video", "model_size", "language", "initial_prompt",
                                        "compute_type"])
        self.assertEqual(list(inspect.signature(T.whisper_model).parameters), ["model_size", "compute_type"])


# --------------------------------------------------------------------------- reel bench + doctor
class TestBench(_Home):
    def test_bench_measures_and_caches_the_rt_factor(self):
        audio = np.zeros(SR * 60, np.float32)
        clock = iter([0.0, 2.0, 2.0, 8.0])

        def factory(model_size, vad, log_to=None, backend=None, batch_size=None):
            def run(a, s, lang, prompt):
                return {"segments": [], "words": [], "language": "ar", "language_probability": 0.9}
            run.backend = "ct2"
            run.state = {"backend": "faster-whisper", "device": "cuda", "compute_type": "float16", "batch_size": 8,
                         "cpu_threads": 20}
            run.load = lambda: None
            return run
        with mock.patch.object(WB, "make_runner", side_effect=factory):
            r = WB.bench(audio, model="large-v3", source="sample.wav", clock=lambda: next(clock))
        self.assertEqual(r["audio_s"], 60.0)
        self.assertEqual(r["load_s"], 2.0)
        self.assertEqual(r["elapsed_s"], 6.0)
        self.assertEqual(r["rt_factor"], 10.0)
        cache = read_json(self.home / "bench" / "whisper-bench.json")
        self.assertEqual(cache["latest"], "ct2/large-v3/cuda/batch8/no-hint")
        self.assertEqual(cache["results"]["ct2/large-v3/cuda/batch8/no-hint"]["rt_factor"], 10.0)
        self.assertFalse(r["hint"])
        got = WB.read_bench()
        self.assertTrue(got["measured"])
        self.assertEqual(got["rt_factor"], 10.0)
        self.assertIn("min of audio per minute", got["summary"])

    def test_read_bench_without_a_measurement_says_how(self):
        got = WB.read_bench()
        self.assertFalse(got["measured"])
        self.assertIn("reel bench", got["how"])

    def test_doctor_reads_the_cached_rt_factor(self):
        from lib import onboard
        write_json(self.home / "bench" / "whisper-bench.json",
                   {"latest": "k", "results": {"k": {"rt_factor": 12.5, "backend": "ct2", "model": "large-v3",
                                                     "device": "cuda", "batch_size": 8, "measured": "2026-10-12"}}})
        self.assertEqual(onboard.transcription_speed()["rt_factor"], 12.5)

    def test_bench_command_is_registered_machine_level(self):
        sys.path.insert(0, str(ENGINE))
        import cli
        self.assertIn("bench", cli.CORE_COMMANDS)
        self.assertIn("bench", cli.CORE_READS)
        self.assertIn("bench", cli.NO_ROOT)
        r = subprocess.run([sys.executable, "-B", str(ENGINE / "cli.py"), "bench", "--help"], capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        for flag in ("--audio", "--seconds", "--model", "--backend", "--batch-size"):
            self.assertIn(flag, r.stdout)

    def test_bench_without_audio_refuses_with_how(self):
        r = subprocess.run([sys.executable, "-B", str(ENGINE / "cli.py"), "bench"], capture_output=True, text=True,
                           encoding="utf-8", env=dict(os.environ, WHYNOT_HOME=str(self.home)))
        self.assertEqual(r.returncode, 2, r.stderr[-400:])
        out = json.loads(r.stdout)
        self.assertIn("error", out)
        self.assertIn("--audio", out["how"])


class TestCliFlags(unittest.TestCase):
    def test_transcribe_commands_take_batch_size_and_backend(self):
        for cmd in ("transcribe", "episode-transcribe"):
            r = subprocess.run([sys.executable, "-B", str(ENGINE / "cli.py"), cmd, "--help"], capture_output=True,
                               text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            self.assertIn("--batch-size", r.stdout)
            self.assertIn("--backend", r.stdout)


# --------------------------------------------------------------------------- review round 1: batched safety nets (I1a)
def seg(text, start, end, words, cr=1.3, ns=0.01, lp=-0.2):
    s = FakeSeg(text, start, end, [FakeWord(w, a, b, p) for w, a, b, p in words])
    s.compression_ratio, s.no_speech_prob, s.avg_logprob = cr, ns, lp
    return s


GOOD = ("أهلا بيك", 0.5, 1.4, [(" أهلا", 0.5, 0.9, 0.9), (" بيك", 1.0, 1.4, 0.9)])


class TestBatchedSafetyNets(_Home):
    """The batched pipeline has no temperature fallback, no no-speech skip, and ~30 s segments: a suspect segment's
    span is decoded again sequentially (2.x options) and its words are spliced in."""
    audio = np.zeros(SR * 40, np.float32)

    def setUp(self):
        super().setUp()
        self.fakes(cuda=1)
        self.seq_calls = []

        def seq(audio, kw):
            self.seq_calls.append(dict(kw, samples=len(audio)))
            return [seg(" كلام صحيح", 1.0, 2.0, [(" كلام", 1.0, 1.5, 0.9), (" صحيح", 1.6, 2.0, 0.9)])]
        FakeWhisperModel.seq_fn = seq

    def run_with(self, bad):
        FakeBatched.segments = [seg(*GOOD), bad]
        run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4)
        return run, run(self.audio, 0, "ar", "هنا")

    def test_repetition_is_decoded_again_and_spliced(self):
        run, r = self.run_with(seg(" نعم نعم نعم نعم", 10.0, 20.0, [(" نعم", 10 + i, 10.5 + i, 0.9) for i in range(4)],
                                   cr=3.1))
        self.assertEqual(len(self.seq_calls), 1)
        kw = self.seq_calls[0]
        self.assertEqual(kw["samples"], 11 * SR)          # the suspect segment's span, padded 0.5 s each side
        self.assertFalse(kw["vad_filter"])
        self.assertEqual(kw["temperature"], [0.0, 0.2, 0.4])           # the 2.x temperature retry
        self.assertEqual((kw["beam_size"], kw["initial_prompt"], kw["language"]), (5, "هنا", "ar"))
        self.assertEqual([w["word"] for w in r["words"]], ["أهلا", "بيك", "كلام", "صحيح"])
        self.assertEqual(r["words"][2]["start_ms"], 10500)            # span-relative times made chunk-relative
        self.assertEqual([s["start_ms"] for s in r["segments"]], [500, 10500])
        self.assertEqual(run.state["redecoded"], [{"start_ms": 10000, "end_ms": 20000, "span_ms": [9500, 20500],
                                                   "reason": "compression_ratio", "words_before": 4, "words_after": 2}])

    def test_span_pads_half_the_gap_to_each_neighbour(self):
        """N2: batched segment edges come from DTW word alignment (often 100-300 ms off): pad into the gaps, never
        into the neighbours' words."""
        FakeBatched.segments = [seg(" أهلا", 9.0, 9.8, [(" أهلا", 9.0, 9.8, 0.9)]),
                                seg(" نعم نعم نعم", 10.0, 20.0, [(" نعم", 10 + i, 10.5 + i, 0.9) for i in range(3)],
                                    cr=3.0),
                                seg(" بيك", 20.2, 21.0, [(" بيك", 20.2, 21.0, 0.9)])]
        run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4)
        r = run(self.audio, 0, "ar", None)
        self.assertEqual(run.state["redecoded"][0]["span_ms"], [9900, 20100])
        self.assertEqual(self.seq_calls[0]["samples"], int(round(20.1 * SR)) - int(9.9 * SR))
        self.assertEqual([w["word"] for w in r["words"]], ["أهلا", "كلام", "صحيح", "بيك"])
        self.assertEqual(r["words"][1]["start_ms"], 10900)

    def test_span_padding_is_at_most_half_a_second_and_stays_in_the_audio(self):
        raws = [{"start": 0.1, "end": 5.0}, {"start": 30.0, "end": 39.9}]
        self.assertEqual(WB.redecode_span(raws, 0, 40.0), (0.05, 5.5))
        b = WB.redecode_span(raws, 1, 40.0)
        self.assertEqual(b[0], 29.5)
        self.assertAlmostEqual(b[1], 39.95)

    def test_redecode_out_of_memory_retries_with_beam_1_not_a_smaller_batch(self):
        """M3"""
        def seq(audio, kw):
            if kw["beam_size"] == 5:
                raise RuntimeError("CUDA failed with error out of memory")
            self.seq_calls.append(kw)
            return [seg(" كلام", 1.0, 1.5, [(" كلام", 1.0, 1.5, 0.9)])]
        FakeWhisperModel.seq_fn = seq
        run, r = self.run_with(seg(" نعم نعم نعم", 10.0, 20.0, [(" نعم", 10 + i, 10.5 + i, 0.9) for i in range(3)],
                                   cr=3.0))
        self.assertEqual(run.state["batch_size"], 4)
        self.assertNotIn("fallback_from", run.state)
        self.assertEqual(len(run.state["redecoded"]), 1)
        self.assertEqual(run.state["redecoded"][0]["beam_size"], 1)

    def test_records_only_a_decode_that_succeeded(self):
        """M3: a GPU failure after one re-decode retries the chunk (on the CPU): no duplicate records."""
        n = []

        def seq(audio, kw):
            n.append(1)
            if len(n) == 2:
                raise RuntimeError("CUDA error: an illegal memory access was encountered")
            return []
        FakeWhisperModel.seq_fn = seq
        FakeBatched.segments = [seg(" نعم نعم", 1.0, 5.0, [(" نعم", 1, 2, 0.9), (" نعم", 2, 3, 0.9)], cr=3.0),
                                seg(" لا لا", 10.0, 15.0, [(" لا", 10, 11, 0.9), (" لا", 11, 12, 0.9)], cr=3.0)]
        run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4)
        run(self.audio, 0, "ar", None)
        self.assertEqual(run.state["device"], "cpu")       # the chunk was decoded again, sequentially, on the CPU
        self.assertEqual(run.state["redecoded"], [])

    def test_likely_silence_is_decoded_again(self):
        FakeWhisperModel.seq_fn = lambda audio, kw: self.seq_calls.append(kw) or []   # 2.x skips it: no words
        run, r = self.run_with(seg(" شكرا", 25.0, 27.0, [(" شكرا", 25.0, 27.0, 0.3)], ns=0.8, lp=-1.4))
        self.assertEqual(run.state["redecoded"][0]["reason"], "no_speech")
        self.assertEqual([w["word"] for w in r["words"]], ["أهلا", "بيك"])

    def test_no_speech_alone_is_not_suspect(self):
        run, r = self.run_with(seg(" شكرا", 25.0, 27.0, [(" شكرا", 25.0, 27.0, 0.9)], ns=0.8, lp=-0.4))
        self.assertEqual(self.seq_calls, [])
        self.assertEqual(run.state["redecoded"], [])

    def test_hallucination_phrase_inside_a_long_segment(self):
        words = [(" طيب", 30.0, 30.4, 0.9), (" اشتركوا", 31.0, 31.1, 0.9), (" في", 31.1, 31.2, 0.9),
                 (" القناة", 31.2, 31.3, 0.9)]
        run, r = self.run_with(seg(" طيب اشتركوا في القناة", 30.0, 31.3, words))
        self.assertEqual(run.state["redecoded"][0]["reason"], "hallucination_phrase")

    def test_clean_batch_is_left_alone(self):
        run, r = self.run_with(seg(" Botox", 2.0, 2.6, [(" Botox", 2.0, 2.6, 0.7)]))
        self.assertEqual(self.seq_calls, [])
        self.assertEqual(len(r["words"]), 3)

    def test_sequential_decoding_is_never_double_checked(self):
        FakeWhisperModel.seq_fn = None
        run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=0)
        run(self.audio, 0, "ar", None)
        self.assertEqual(run.state["redecoded"], [])
        self.assertEqual(len(FakeWhisperModel.instances[0].calls), 1)


# --------------------------------------------------------------------------- review round 1: word-level G53 (I1b)
def transcript(words, ns=0.1):
    ws = [{"id": i + 1, "segment_id": 1, "word": w, "start_ms": a, "end_ms": b, "probability": p}
          for i, (w, a, b, p) in enumerate(words)]
    s = {"id": 1, "start_ms": ws[0]["start_ms"], "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
         "avg_logprob": -0.3, "no_speech_prob": ns, "compression_ratio": 1.2, "words": [w["id"] for w in ws]}
    return [s], ws


class TestWordLevelHallucinations(unittest.TestCase):
    def drop(self, words, ns=0.1):
        from lib.transcribe import drop_hallucinations
        return drop_hallucinations(*transcript(words, ns))

    def test_fast_phrase_inside_a_segment_is_dropped(self):
        segs, words, dropped = self.drop([("طيب", 0, 400, 0.9), ("اشتركوا", 1000, 1100, 0.9), ("في", 1100, 1200, 0.9),
                                          ("القناة", 1200, 1300, 0.9)])
        self.assertEqual([w["word"] for w in words], ["طيب"])
        self.assertEqual(segs[0]["text"], "طيب")
        self.assertEqual(segs[0]["words"], [1])
        self.assertEqual((segs[0]["start_ms"], segs[0]["end_ms"]), (0, 400))       # M4: the span of what is left
        self.assertEqual(dropped[0]["level"], "words")
        self.assertEqual(dropped[0]["text"], "اشتركوا في القناة")

    def test_unsure_short_phrase_alone_in_silence_is_dropped(self):
        _, words, dropped = self.drop([("كلام", 0, 400, 0.9), ("شكرا", 1200, 1600, 0.2), ("على", 1600, 1900, 0.3),
                                       ("المشاهدة", 1900, 2400, 0.25)])
        self.assertEqual([w["word"] for w in words], ["كلام"])
        self.assertEqual(dropped[0]["mean_probability"], 0.25)
        self.assertEqual(dropped[0]["reason"], "unsure, alone in silence")

    def test_real_outro_under_a_music_bed_is_kept(self):
        """N1 probe: «وفي النهاية شكرا على المشاهدة», 2.1 words/s, mean p 0.93, segment no-speech 0.55 (music)."""
        segs, words, dropped = self.drop([("وفي", 0, 450, 0.95), ("النهاية", 450, 1000, 0.94),
                                          ("شكرا", 1000, 1400, 0.92), ("على", 1400, 1750, 0.93),
                                          ("المشاهدة", 1750, 2400, 0.91)], ns=0.55)
        self.assertEqual(len(words), 5)
        self.assertEqual(dropped, [])

    def test_unsure_dialect_phrase_at_a_normal_pace_is_kept(self):
        """N1: low confidence alone is no proof (p 0.38 on a genuine Egyptian phrase between other words)."""
        _, words, dropped = self.drop([("يعني", 0, 400, 0.9), ("اشتركوا", 550, 1100, 0.38), ("في", 1100, 1300, 0.38),
                                       ("القناة", 1300, 1900, 0.38), ("بقى", 2000, 2300, 0.9)])
        self.assertEqual(len(words), 5)
        self.assertEqual(dropped, [])

    def test_keep_phrases_are_never_dropped(self):
        from lib.transcribe import drop_hallucinations
        segs, words = transcript([("طيب", 0, 400, 0.9), ("اشتركوا", 1000, 1100, 0.9), ("في", 1100, 1200, 0.9),
                                  ("القناة", 1200, 1300, 0.9)])
        _, kept, dropped = drop_hallucinations(segs, words, keep_phrases=["اشتركوا في القناه"])
        self.assertEqual((len(kept), dropped), (4, []))

    def project(self):
        tmp = Path(tempfile.mkdtemp(prefix="whynot-t212-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        p = Paths(tmp / "C", "V1")
        p.ensure_project()
        return p

    META = {"source_video": "x.mp4", "backend": "test", "model": "none", "language": "ar",
            "language_probability": 1.0, "duration_ms": 2000}

    def test_restore_brings_dropped_words_back_for_good(self):
        """N1: the editor heard it: "restore": [ids] in transcript-corrections.json."""
        from lib.transcribe import apply_corrections, finalize
        p = self.project()
        segs, words = transcript([("طيب", 0, 400, 0.9), ("اشتركوا", 1000, 1100, 0.9), ("في", 1100, 1200, 0.9),
                                  ("القناة", 1200, 1300, 0.9)])
        finalize(p, dict(self.META), segs, words)
        side = read_json(p.p("02_transcription/dropped-hallucinations.json"))
        self.assertEqual([w["id"] for w in side["dropped"][0]["words"]], [2, 3, 4])
        write_json(p.p("02_transcription/transcript-corrections.json"), {"corrections": [], "restore": [2]})
        r = apply_corrections(p)
        self.assertEqual(r["restored"], [2, 3, 4])
        wj = read_json(p.p("02_transcription/words.json"))
        self.assertEqual([w["word"] for w in wj["words"]], ["طيب", "اشتركوا", "في", "القناة"])
        self.assertTrue(wj["words"][1]["restored"])
        tj = read_json(p.p("02_transcription/transcript.json"))
        self.assertEqual(tj["segments"][0]["text"], "طيب اشتركوا في القناة")
        self.assertEqual((tj["segments"][0]["start_ms"], tj["segments"][0]["end_ms"]), (0, 1300))
        self.assertTrue(read_json(p.p("02_transcription/dropped-hallucinations.json"))["dropped"][0]["restored"])
        self.assertIn("RESTORED", p.p("02_transcription/subtitle-review.md").read_text(encoding="utf-8"))
        apply_corrections(p)                                   # idempotent from the machine originals
        self.assertEqual(len(read_json(p.p("02_transcription/words.json"))["words"]), 4)

    def test_restore_of_a_whole_dropped_segment(self):
        from lib.transcribe import apply_corrections, finalize
        p = self.project()
        segs, words = transcript([("اشتركوا", 0, 100, 0.9), ("في", 100, 200, 0.9), ("القناة", 200, 320, 0.9)], ns=0.93)
        finalize(p, dict(self.META), segs, words)
        self.assertEqual(read_json(p.p("02_transcription/words.json"))["words"], [])
        write_json(p.p("02_transcription/transcript-corrections.json"), {"corrections": [], "restore": "all"})
        apply_corrections(p)
        tj = read_json(p.p("02_transcription/transcript.json"))
        self.assertEqual([x["text"] for x in tj["segments"]], ["اشتركوا في القناة"])

    def test_a_host_who_really_says_it_is_kept(self):
        segs, words, dropped = self.drop([("وطبعا", 0, 500, 0.9), ("اشتركوا", 600, 1200, 0.9), ("في", 1200, 1400, 0.9),
                                          ("القناة", 1400, 2000, 0.9)])
        self.assertEqual(len(words), 4)
        self.assertEqual(dropped, [])
        self.assertEqual(segs[0]["text"], "وطبعا اشتركوا في القناة")

    def test_whole_segment_rule_still_applies(self):
        segs, words, dropped = self.drop([("اشتركوا", 0, 100, 0.9), ("في", 100, 200, 0.9), ("القناة", 200, 320, 0.9)],
                                         ns=0.93)
        self.assertEqual((segs, words), ([], []))
        self.assertEqual(dropped[0]["level"], "segment")

    def test_finalize_applies_it_to_every_transcript(self):
        """Episodes, long clips and reels sliced from an episode all go through finalize."""
        from lib.transcribe import finalize
        tmp = Path(tempfile.mkdtemp(prefix="whynot-t212-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        p = Paths(tmp / "C", "V1")
        p.ensure_project()
        segs, words = transcript([("طيب", 0, 400, 0.9), ("اشتركوا", 1000, 1100, 0.9), ("في", 1100, 1200, 0.9),
                                  ("القناة", 1200, 1300, 0.9)])
        finalize(p, {"source_video": "x.mp4", "backend": "test", "model": "none", "language": "ar",
                     "language_probability": 1.0, "duration_ms": 2000}, segs, words)
        wj = read_json(p.p("02_transcription/words.json"))
        self.assertEqual([w["word"] for w in wj["words"]], ["طيب"])
        self.assertEqual(wj["meta"]["dropped_hallucinations"][0]["level"], "words")
        self.assertIn("Dropped Whisper hallucinations — 1", p.p("02_transcription/subtitle-review.md").read_text(
            encoding="utf-8"))


# --------------------------------------------------------------------------- review round 1: decoder in checkpoints (I2)
class SigRunner:
    """A fake runner with a decoder signature, like make_runner's."""

    def __init__(self, sig):
        self.backend, self.sig, self.calls = "ct2", dict(sig), []
        self.state = {"redecoded": []}
        self.on_call = None

    def signature(self):
        return dict(self.sig)

    def __call__(self, audio, start_ms, language, prompt):
        self.calls.append(start_ms)
        if self.on_call:
            self.on_call(self, start_ms)
        return {"language": "ar", "language_probability": 0.9,
                "segments": [{"id": 1, "start_ms": 100, "end_ms": 900, "text": "كلام", "avg_logprob": -0.2,
                              "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1]}],
                "words": [{"id": 1, "segment_id": 1, "word": "كلام", "start_ms": 100, "end_ms": 900, "probability": 0.9}]}


GPU4 = {"device": "cuda", "batch_size": 4, "vad": True}


class TestDecoderCheckpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t212-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paths = Paths(self.tmp / "C", "V1")
        self.cdir = self.tmp / "chunks"
        self.cdir.mkdir()
        self.audio = np.zeros(SR * 30, np.float32)
        self.plan = {"chunks": [[0, 10000], [10000, 20000], [20000, 30000]]}

    def go(self, runner):
        from lib.episode import run_chunks
        return run_chunks(self.paths, self.cdir, self.audio, self.plan, runner, model="large-v3", prompt="هنا",
                          language=None, label="test")

    def test_records_device_batch_and_vad(self):
        self.go(SigRunner(GPU4))
        rec = read_json(self.cdir / "chunk_000.json")
        self.assertEqual(rec["decoder"], GPU4)
        self.assertNotIn("fallback_from", rec)

    def test_any_decoder_change_redoes_the_chunks(self):
        self.go(SigRunner(GPU4))
        for change in ({"batch_size": 0}, {"vad": False}, {"device": "cpu", "batch_size": 0}, {"batch_size": 8}):
            r = SigRunner(dict(GPU4, **change))
            self.go(r)
            self.assertEqual(r.calls, [0, 10000, 20000], change)
            self.go(SigRunner(GPU4))                  # back to the original decoder for the next case

    def test_same_decoder_resumes(self):
        self.go(SigRunner(GPU4))
        r = SigRunner(GPU4)
        self.assertEqual(self.go(r)["ran"], 0)

    def test_checkpoint_without_decoder_is_redone(self):
        self.go(SigRunner(GPU4))
        rec = read_json(self.cdir / "chunk_001.json")
        rec.pop("decoder")
        write_json(self.cdir / "chunk_001.json", rec)
        r = SigRunner(GPU4)
        self.go(r)
        self.assertEqual(r.calls, [10000])

    def test_mid_run_cpu_fallback_is_marked_kept_and_reported(self):
        def fall(runner, start_ms):
            if start_ms == 10000:                     # the GPU fails on the second chunk
                runner.state["fallback_from"] = dict(GPU4)
                runner.sig = {"device": "cpu", "batch_size": 0, "vad": True}
        r = SigRunner(GPU4)
        r.on_call = fall
        done = self.go(r)
        self.assertEqual(read_json(self.cdir / "chunk_000.json")["decoder"], GPU4)
        later = read_json(self.cdir / "chunk_002.json")
        self.assertEqual(later["decoder"]["device"], "cpu")
        self.assertEqual(later["fallback_from"], GPU4)
        self.assertEqual(done["decoders"], ["cuda/batch4/vad", "cpu/sequential/vad (fallback)"])
        again = SigRunner(GPU4)                        # a re-run that wants the GPU keeps every chunk (no force)
        self.assertEqual(self.go(again)["ran"], 0)
        seq = SigRunner(dict(GPU4, batch_size=0))     # but asking for another decoder redoes them all
        self.go(seq)
        self.assertEqual(seq.calls, [0, 10000, 20000])

    def test_redecoded_segments_are_recorded_per_chunk_in_absolute_time(self):
        def mark(runner, start_ms):
            if start_ms == 20000:
                runner.state["redecoded"].append({"start_ms": 1000, "end_ms": 4000, "reason": "compression_ratio"})
        r = SigRunner(GPU4)
        r.on_call = mark
        done = self.go(r)
        self.assertEqual(read_json(self.cdir / "chunk_002.json")["redecoded"][0]["start_ms"], 21000)
        self.assertEqual(read_json(self.cdir / "chunk_001.json")["redecoded"], [])
        self.assertEqual(len(done["redecoded"]), 1)

    def test_runner_signature_needs_no_model_load(self):
        h = _Home("setUp")
        h.setUp()
        try:
            h.fakes(cuda=1)
            run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4)
            self.assertEqual(run.signature(), GPU4)
            self.assertEqual(FakeWhisperModel.instances, [])
            self.assertEqual(WB.make_runner("large-v3", vad=False, backend="ct2", batch_size=4).signature(),
                             {"device": "cuda", "batch_size": 0, "vad": False})
        finally:
            h.doCleanups()


# --------------------------------------------------------------------------- review round 1: minors
class TestOutOfMemory(_Home):
    """M7: CUDA out of memory with a batch halves the batch before falling back to the CPU."""
    audio = np.zeros(SR * 40, np.float32)

    def test_halves_the_batch(self):
        self.fakes(cuda=1)
        FakeBatched.max_ok = 2
        run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=8)
        r = run(self.audio, 0, "ar", None)
        self.assertEqual([c["batch_size"] for b in FakeBatched.instances for c in b.calls], [8, 4, 2])
        self.assertEqual((run.state["device"], run.state["batch_size"]), ("cuda", 2))
        self.assertEqual(run.state["fallback_from"], {"device": "cuda", "batch_size": 8, "vad": True})
        self.assertEqual(len(r["words"]), 3)

    def test_sequential_gpu_before_cpu(self):
        self.fakes(cuda=1)
        FakeBatched.max_ok = 0
        run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4)
        run(self.audio, 0, "ar", None)
        self.assertEqual((run.state["device"], run.state["batch_size"]), ("cuda", 0))
        self.assertEqual(len(FakeWhisperModel.instances), 1)    # never reloaded on the CPU


class TestModelCompleteness(_Home):
    def test_every_128_mel_model_needs_its_preprocessor_config(self):
        """M6"""
        for m in ("large-v3", "large-v3-turbo", "turbo", "distil-large-v3"):
            self.assertIn("preprocessor_config.json", WB._ct2_needs(m), m)
        self.assertNotIn("preprocessor_config.json", WB._ct2_needs("medium"))

    def test_large_v3_needs_its_preprocessor_config(self):
        """M2: without preprocessor_config.json faster-whisper uses 80 mel bins; large-v3 needs 128."""
        self.snapshot(files=["config.json", "tokenizer.json", "model.bin"])
        self.assertIsNone(WB.snapshot_dir("large-v3", min_bytes=10))

    def test_offline_with_a_partial_model_says_what_to_do(self):
        """M1"""
        self.fakes(cuda=0)
        self.snapshot(complete=False)
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "1"}), self.assertRaises(RuntimeError) as cm:
            WB.load_ct2("large-v3")
        self.assertIn("incomplete", str(cm.exception))
        self.assertIn("reel model-download --model large-v3", str(cm.exception))
        self.assertEqual(FakeWhisperModel.instances, [])

    def test_offline_without_any_model(self):
        self.fakes(cuda=0)
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": "1"}), self.assertRaises(RuntimeError) as cm:
            WB.load_ct2("large-v3")
        self.assertIn("not downloaded", str(cm.exception))

    def test_partial_model_that_cannot_be_completed(self):
        self.fakes(cuda=0)
        self.snapshot(complete=False)
        FakeWhisperModel.fail_names = True
        with mock.patch.dict(os.environ, {"HF_HUB_OFFLINE": ""}), self.assertRaises(RuntimeError) as cm:
            WB.load_ct2("large-v3")
        self.assertIn("reel model-download", str(cm.exception))


class TestMacCores(unittest.TestCase):
    """M4: Apple Silicon counts its performance cores; Intel Macs every physical core."""

    def sysctl(self, values):
        def run(cmd, **kw):
            v = values.get(cmd[-1])
            return SimpleNamespace(returncode=0 if v else 1, stdout=f"{v}\n" if v else "")
        return mock.patch.object(WB.subprocess, "run", side_effect=run)

    def test_performance_cores_first(self):
        with self.sysctl({"hw.perflevel0.physicalcpu": 8, "hw.physicalcpu": 12}):
            self.assertEqual(WB._mac_physical_cores(), 8)

    def test_intel_mac(self):
        with self.sysctl({"hw.physicalcpu": 6}):
            self.assertEqual(WB._mac_physical_cores(), 6)


class TestBenchHint(_Home):
    def test_root_uses_the_client_hint_and_the_key_says_so(self):
        """M3"""
        root = self.tmp / "C"
        (root / common.CLIENT_PROFILE_REL).mkdir(parents=True)
        write_json(root / common.CLIENT_PROFILE_REL / "transcription.json", {"initial_prompt": "د. سامبل إكزامبل"})
        seen = []

        def factory(model_size, vad, log_to=None, backend=None, batch_size=None):
            def run(a, s, lang, prompt):
                seen.append(prompt)
                return {"segments": [], "words": [], "language": "ar", "language_probability": 0.9}
            run.backend, run.load = "ct2", lambda: None
            run.state = {"device": "cuda", "batch_size": 4, "compute_type": "float16"}
            return run
        with use_context(Context(root)), mock.patch.object(WB, "make_runner", side_effect=factory):
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3")
        self.assertEqual(seen, ["د. سامبل إكزامبل"])
        self.assertTrue(r["hint"])
        self.assertEqual(r["key"], "ct2/large-v3/cuda/batch4/hint")


if __name__ == "__main__":
    unittest.main()
