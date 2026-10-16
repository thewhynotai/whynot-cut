# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N6/N8 - WhyNot Hush on the engine: words (Whisper), store (settings, presets, log, cache) and the
chat entry points (lib/hush/{words,store,run}.py).

Everything here runs in the engine runtime with a FAKE Whisper runner (no model, no network: every test blocks socket
connections); only the parity checks against the owner's upstream `hush_whisper.py` need adobe/tools and skip with a
reason in the plugin zip.

* HushWords: the disfluency prompt per language (verbatim), auto = None, the runner's arguments, the output schema
  {language, duration, words:[{w,s,e,p}], elapsed}, offline environment during the call, HUSH_WHISPER_MODEL, the GPU
  slot lane -> device, the progress JSON lines of the process entry point, errors.
* HushWavLoader: load_wav equals the upstream hush_whisper.load_wav on generated WAVs (8/16/24/32-bit, mono / stereo,
  16 / 44.1 / 48 kHz), and the prompts equal the upstream PROMPTS.
* HushStore: files under <engine home>/tools/hush, settings, presets (FR-24), log, scan cache (the last 3, keyed by
  sequence + range + tracks + audio sha256), user-only files, UTF-8 and \\n, no settings or keys in the log.
* HushRun: scan -> {env, duration, stats, words, fillers}, plan with Tight, cache hit without a second transcription,
  the `scan` / `plan` command line.
Run:  bash tools/test.sh -p test_hush_engine.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib  # noqa: E402
import importlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import wave  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402

SK = Path(__file__).resolve().parents[1]
sys = _sys
sys.path.insert(0, str(SK / "engine" / "reel"))

import test_hush_characterization as HC  # noqa: E402  (module import: its TestCases are not collected twice)

UPSTREAM_PY = HC.ADOBE_TOOLS / "hush" / "_upstream" / "py" / "hush_whisper.py"
LIB = SK / "engine" / "reel" / "lib" / "hush"

PROMPT_EN = "Umm, uh, so, uhh... I mean, like, hmm, you know, erm, ah."
PROMPT_AR = ("\u0627\u0645\u0645\u0645\u060c \u0622\u0647\u060c \u064a\u0639\u0646\u064a\u060c \u0627\u0627\u0647\u060c "
             "\u0627\u0645\u0645... \u0637\u064a\u0628\u060c \u0647\u0645\u0645\u0645\u060c \u064a\u0639\u0646\u064a "
             "\u0625\u064a\u0647.")
PROMPT_AUTO = ("Umm, uh, hmm... \u0627\u0645\u0645\u0645\u060c \u0622\u0647\u060c \u064a\u0639\u0646\u064a\u060c "
               "\u0627\u0627\u0647... like, you know, erm.")


def mod(name):
    """Import lib.hush.<name> inside the test (a missing module is that test's failure, not the whole file's)."""
    return importlib.import_module("lib.hush." + name)


class NoNetwork(unittest.TestCase):
    """Every engine test blocks socket connections: the fake runner is the only 'Whisper'."""

    def setUp(self):
        p = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network access in a unit test"))
        p.start()
        self.addCleanup(p.stop)
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)


# ------------------------------------------------------------------ fakes and fixtures -----------------------------
def words_schema(items, language="en"):
    """What lib.whisper_backends.make_runner's run() returns: ms times, probability, ids."""
    return {"segments": [], "language": language, "language_probability": 1.0,
            "words": [{"id": i + 1, "segment_id": 1, "word": w, "start_ms": s, "end_ms": e, "probability": p}
                      for i, (w, s, e, p) in enumerate(items)]}


class FakeRunner:
    def __init__(self, items=None, language="en"):
        self.items = items if items is not None else [(" um", 1234, 1500, 0.98765), ("like,", 2000, 2300, 0.5)]
        self.language = language
        self.calls = []

    def __call__(self, audio, start_ms, language, prompt):
        self.calls.append({"audio": audio, "start_ms": start_ms, "language": language, "prompt": prompt,
                           "offline": os.environ.get("HF_HUB_OFFLINE")})
        return words_schema(self.items, self.language)


class FakeFactory:
    def __init__(self, runner):
        self.runner, self.calls = runner, []

    def __call__(self, model, vad=False, **kw):
        self.calls.append(dict(kw, model=model, vad=vad, offline=os.environ.get("HF_HUB_OFFLINE")))
        return self.runner


def write_wav(path, samples, rate=16000, width=2, channels=1):
    """Plain PCM WAV through the stdlib `wave` (what Premiere exports)."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(samples)


def pcm16(x):
    return np.round(np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


def speech_like(rate=16000, seconds=6.0, seed=3):
    """Loud 440 Hz stretches with 1 s of silence between them (speech 0-1.5 s, gap, speech 2.5-4 s, gap 4-5 s, 5-6 s)."""
    rng = np.random.default_rng(seed)
    n = int(rate * seconds)
    t = np.arange(n) / rate
    x = 0.0005 * rng.standard_normal(n)
    for a, b in ((0.0, 1.5), (2.5, 4.0), (5.0, 6.0)):
        m = (t >= a) & (t < b)
        x[m] = 0.3 * np.sin(2 * np.pi * 440 * t[m])
    return x


# ------------------------------------------------------------------ words ---------------------------------------------
class HushWords(NoNetwork):
    def wav(self, seconds=1.5, rate=16000):
        p = self.tmp / "a.wav"
        write_wav(p, pcm16(0.1 * np.sin(2 * np.pi * 300 * np.arange(int(rate * seconds)) / rate)), rate)
        return p

    def run_words(self, language=None, runner=None, **kw):
        words = mod("words")
        runner = runner or FakeRunner()
        factory = FakeFactory(runner)
        res = words.transcribe(self.wav(), language, make_runner=factory,
                               slot=lambda backend=None: contextlib.nullcontext("cuda"), **kw)
        return res, runner, factory

    def test_prompts_are_the_upstream_text_per_language(self):
        words = mod("words")
        self.assertEqual(words.PROMPTS["en"], PROMPT_EN)
        self.assertEqual(words.PROMPTS["ar"], PROMPT_AR)
        self.assertEqual(words.PROMPTS[None], PROMPT_AUTO)
        self.assertEqual(set(words.PROMPTS), {"en", "ar", None})

    def test_the_prompt_and_language_reach_the_runner(self):
        cases = [("en", "en", PROMPT_EN), ("ar", "ar", PROMPT_AR), (None, None, PROMPT_AUTO), ("auto", None, PROMPT_AUTO),
                 ("", None, PROMPT_AUTO), ("fr", "fr", PROMPT_AUTO)]  # an unknown language: told to Whisper, auto prompt
        for given, lang, prompt in cases:
            res, runner, _ = self.run_words(given)
            self.assertEqual(len(runner.calls), 1)
            c = runner.calls[0]
            self.assertEqual((c["language"], c["prompt"], c["start_ms"]), (lang, prompt, 0), given)
            self.assertEqual(c["audio"].dtype, np.float32)  # 16 kHz mono float32, as load_wav gives it

    def test_the_runner_is_made_for_large_v3_turbo_without_vad(self):
        words = mod("words")
        from lib import whisper_backends as WB
        self.assertIn("large-v3-turbo", WB.CT2_REPOS)
        self.assertEqual(words.DEFAULT_MODEL, "large-v3-turbo")
        _, _, factory = self.run_words("en")
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual((factory.calls[0]["model"], factory.calls[0]["vad"]), ("large-v3-turbo", False))  # VAD drops fillers

    def test_hush_whisper_model_override(self):
        with mock.patch.dict(os.environ, {"HUSH_WHISPER_MODEL": "small"}):
            _, _, factory = self.run_words("en")
        self.assertEqual(factory.calls[0]["model"], "small")
        # the upstream default (an mlx repo id) and the CT2 repo id both name the same model
        for repo in ("mlx-community/whisper-large-v3-turbo", "dropbox-dash/faster-whisper-large-v3-turbo"):
            with mock.patch.dict(os.environ, {"HUSH_WHISPER_MODEL": repo}):
                _, _, factory = self.run_words("en")
            self.assertEqual(factory.calls[0]["model"], "large-v3-turbo", repo)
        with mock.patch.dict(os.environ, {"HUSH_WHISPER_MODEL": str(self.tmp)}):  # a local model folder passes through
            _, _, factory = self.run_words("en")
        self.assertEqual(factory.calls[0]["model"], str(self.tmp))
        env = dict(os.environ)
        env.pop("HUSH_WHISPER_MODEL", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(mod("words").model_name(), "large-v3-turbo")

    def test_output_schema_rounding_and_duration(self):
        res, _, _ = self.run_words("en", clock=iter([100.0, 103.456]).__next__)  # start, end
        self.assertEqual(sorted(res), ["duration", "elapsed", "language", "words"])
        self.assertEqual(res["language"], "en")
        self.assertEqual(res["duration"], 1.5)  # 24000 frames at 16 kHz (PRD 7.2 adds duration)
        self.assertEqual(res["words"], [{"w": "um", "s": 1.234, "e": 1.5, "p": 0.988},
                                        {"w": "like,", "s": 2.0, "e": 2.3, "p": 0.5}])
        self.assertEqual(res["elapsed"], 3.46)

    def test_duration_is_taken_from_the_file_before_it_is_resampled(self):
        words = mod("words")
        p = self.tmp / "r48.wav"
        write_wav(p, pcm16(np.zeros(48000 * 2)), rate=48000)
        res = words.transcribe(p, "en", make_runner=FakeFactory(FakeRunner()), slot=lambda backend=None: contextlib.nullcontext("cuda"))
        self.assertEqual(res["duration"], 2.0)

    def test_offline_for_the_whole_call_and_restored_after(self):
        for before in (None, "0"):
            env = dict(os.environ)
            env.pop("HF_HUB_OFFLINE", None)
            if before is not None:
                env["HF_HUB_OFFLINE"] = before
            with mock.patch.dict(os.environ, env, clear=True):
                _, runner, factory = self.run_words("en")
                self.assertEqual(runner.calls[0]["offline"], "1")
                self.assertEqual(factory.calls[0]["offline"], "1")
                self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), before)

    def test_gpu_slot_lane_decides_the_device(self):
        words = mod("words")
        for lane, device in (("cuda", None), ("mlx", None), ("cpu", "cpu")):
            factory = FakeFactory(FakeRunner())
            seen = []

            @contextlib.contextmanager
            def slot(backend=None, lane=lane):
                seen.append("enter")
                yield lane
                seen.append("exit")
            words.transcribe(self.wav(), "en", make_runner=factory, slot=slot)
            self.assertEqual(factory.calls[0].get("device"), device, lane)
            self.assertEqual(seen, ["enter", "exit"])  # the slot is held around the model load and the decode

    def test_without_the_gpu_lock_module_the_job_still_runs(self):
        words = mod("words")
        factory = FakeFactory(FakeRunner())
        with mock.patch.dict(sys.modules, {"lib.gpu_lock": None}):  # ImportError: another session's module is absent
            res = words.transcribe(self.wav(), "en", make_runner=factory)
        self.assertEqual(len(res["words"]), 2)
        self.assertIsNone(factory.calls[0].get("device"))

    def test_non_wav_audio_is_passed_as_a_path(self):
        words = mod("words")
        p = self.tmp / "clip.mp3"
        p.write_bytes(b"not really audio")
        runner = FakeRunner()
        res = words.transcribe(p, "en", runner=runner)
        self.assertEqual(runner.calls[0]["audio"], str(p))
        self.assertEqual(res["duration"], 2.3)  # no WAV header to read: the end of the last word

    def test_process_entry_point_prints_stage_lines_and_writes_the_json(self):
        words = mod("words")
        out = self.tmp / "words.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = words.main([str(self.wav()), str(out), "en"], runner=FakeRunner())
        self.assertEqual(rc, 0)
        lines = [json.loads(x) for x in buf.getvalue().splitlines()]
        self.assertEqual([x["stage"] for x in lines], ["loading", "transcribing", "done"])
        self.assertEqual((lines[-1]["words"], lines[-1]["language"]), (2, "en"))
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data), ["duration", "elapsed", "language", "words"])
        self.assertNotIn(b"\r", out.read_bytes())

    def test_process_entry_point_reports_errors_as_a_stage_line(self):
        words = mod("words")

        class Boom:
            def __call__(self, *a):
                raise RuntimeError("boom")
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = words.main([str(self.wav()), str(self.tmp / "o.json")], runner=Boom())
        self.assertEqual(rc, 1)
        last = json.loads(buf.getvalue().splitlines()[-1])
        self.assertEqual(last, {"stage": "error", "error": "RuntimeError: boom"})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(words.main([]), 2)  # usage


# ------------------------------------------------------------------ WAV loader and prompts vs upstream ----------------
def upstream():
    spec = importlib.util.spec_from_file_location("hush_whisper_upstream", str(UPSTREAM_PY))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(HC.TOOLS_PRESENT, HC.NO_TOOLS)
class HushWavLoader(NoNetwork):
    def make(self, name, width, rate, channels, n=4000, seed=0):
        rng = np.random.default_rng(seed)
        x = rng.uniform(-0.9, 0.9, n * channels)
        if width == 1:
            raw = (np.round(x * 127) + 128).astype(np.uint8).tobytes()
        elif width == 2:
            raw = np.round(x * 32767).astype("<i2").tobytes()
        elif width == 3:
            v = np.round(x * 8388607).astype(np.int32)
            raw = b"".join(int(i).to_bytes(4, "little", signed=True)[:3] for i in v)
        else:
            raw = np.round(x * 2147483647).astype("<i4").tobytes()
        p = self.tmp / name
        write_wav(p, raw, rate, width, channels)
        return p

    def test_load_wav_equals_upstream(self):
        up, words = upstream(), mod("words")
        cases = [(1, 16000, 1), (2, 16000, 1), (2, 48000, 1), (2, 48000, 2), (3, 48000, 1), (3, 32000, 2), (4, 16000, 1),
                 (4, 48000, 2), (2, 44100, 1), (2, 44100, 2), (3, 22050, 1), (1, 8000, 2), (2, 96000, 1)]
        for k, (width, rate, ch) in enumerate(cases):
            p = self.make("w%d.wav" % k, width, rate, ch, seed=k)
            a, b = up.load_wav(str(p)), words.load_wav(str(p))
            self.assertEqual(a.dtype, b.dtype)
            self.assertTrue(np.array_equal(a, b), (width, rate, ch))

    def test_prompts_equal_upstream(self):
        self.assertEqual(mod("words").PROMPTS, upstream().PROMPTS)


# ------------------------------------------------------------------ store ---------------------------------------------
class HushStore(NoNetwork):
    def store(self):
        return mod("store").Store()

    def test_files_live_under_the_engine_home_tools_hush(self):
        from lib import plat
        st = self.store()
        self.assertEqual(st.home, plat.engine_home() / "tools" / "hush")
        self.assertTrue(str(st.home).startswith(os.environ["WHYNOT_TEST_SANDBOX"]))  # never the real engine home
        self.assertEqual(st.settings_file.name, "settings.json")
        self.assertEqual(st.presets_file.name, "presets.json")
        self.assertEqual(st.log_file, st.home / "logs" / "whynot-hush.log")
        self.assertEqual(st.cache_dir, st.home / "cache")
        explicit = mod("store").Store(self.tmp)
        self.assertEqual(explicit.home, self.tmp / "tools" / "hush")

    def test_settings_round_trip_and_defaults(self):
        st = mod("store").Store(self.tmp)
        self.assertEqual(st.load_settings({"intensity": 50, "tight": True}), {"intensity": 50, "tight": True})
        self.assertTrue(st.save_settings({"intensity": 80, "name": "\u0647\u0634"}))
        self.assertEqual(st.load_settings({"intensity": 50, "tight": True}),
                         {"intensity": 80, "tight": True, "name": "\u0647\u0634"})
        raw = st.settings_file.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertIn("\u0647\u0634", raw.decode("utf-8"))  # UTF-8, not \\u escapes
        st.settings_file.write_text("{not json", encoding="utf-8")
        self.assertEqual(st.load_settings({"a": 1}), {"a": 1})  # a broken file: the defaults

    def test_presets_round_trip_by_name(self):
        st = mod("store").Store(self.tmp)
        self.assertEqual(st.list_presets(), [])
        adv = {"threshold": -45, "minSilence": 0.5, "padBefore": 0.12, "padAfter": 0.12}
        self.assertTrue(st.save_preset("Podcast", adv))
        self.assertTrue(st.save_preset("\u0628\u0648\u062f\u0643\u0627\u0633\u062a", dict(adv, threshold=-50)))
        self.assertEqual([p["name"] for p in st.list_presets()], ["Podcast", "\u0628\u0648\u062f\u0643\u0627\u0633\u062a"])
        self.assertEqual(st.get_preset("Podcast"), adv)
        self.assertEqual(st.get_preset("\u0628\u0648\u062f\u0643\u0627\u0633\u062a")["threshold"], -50)
        self.assertIsNone(st.get_preset("missing"))
        self.assertTrue(st.save_preset("Podcast", dict(adv, minSilence=0.9)))  # same name: replaced, not duplicated
        self.assertEqual(len(st.list_presets()), 2)
        self.assertEqual(st.get_preset("Podcast")["minSilence"], 0.9)
        # the file is the upstream shape: a list of {name, adv}
        data = json.loads(st.presets_file.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data[0]), ["adv", "name"])
        self.assertTrue(st.delete_preset("Podcast"))
        self.assertFalse(st.delete_preset("Podcast"))
        self.assertEqual([p["name"] for p in st.list_presets()], ["\u0628\u0648\u062f\u0643\u0627\u0633\u062a"])
        self.assertFalse(st.save_preset("", adv))  # a preset needs a name
        raw = st.presets_file.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n"))

    def test_log_lines_are_utf8_with_lf_and_never_raise(self):
        st = mod("store").Store(self.tmp)
        self.assertTrue(st.log("scan a.wav 12.00s @48000"))
        self.assertTrue(st.log("two\r\nlines \u0647\u0634"))
        raw = st.log_file.read_bytes()
        self.assertNotIn(b"\r", raw)
        lines = raw.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT[\d:.]+Z  scan a\.wav 12\.00s @48000$")
        self.assertTrue(lines[1].endswith("two lines \u0647\u0634"))

    def test_files_are_user_only(self):
        from serve import security
        st = mod("store").Store(self.tmp)
        st.save_settings({"a": 1})
        st.save_preset("x", {"threshold": -40})
        st.log("hello")
        st.cache_put(st.cache_key("seq", [0, 1], ["A1"], "ab" * 32), {"duration": 1.0})
        for p in (st.settings_file, st.presets_file, st.log_file, *st.cache_dir.glob("scan-*.json")):
            if os.name == "nt":
                self.assertTrue(security.user_only(p), str(p))
            else:
                self.assertEqual(os.stat(p).st_mode & 0o077, 0, str(p))

    def test_cache_key_changes_with_every_part(self):
        st = mod("store").Store(self.tmp)
        sha = "ab" * 32
        base = st.cache_key("seq-1", [0.0, 12.5], ["V1", "A1", "A2"], sha)
        self.assertRegex(base, r"^[0-9a-f]{64}$")
        self.assertEqual(base, st.cache_key("seq-1", (0.0, 12.5), ["A2", "V1", "A1", "A1"], sha))  # order and repeats
        self.assertEqual(base, st.cache_key("seq-1", [0, 12.5], ["V1", "A1", "A2"], sha))  # 0 == 0.0
        changed = [st.cache_key("seq-2", [0.0, 12.5], ["V1", "A1", "A2"], sha),
                   st.cache_key("seq-1", [0.1, 12.5], ["V1", "A1", "A2"], sha),
                   st.cache_key("seq-1", [0.0, 12.6], ["V1", "A1", "A2"], sha),
                   st.cache_key("seq-1", [0.0, 12.5], ["V1", "A1"], sha),
                   st.cache_key("seq-1", [0.0, 12.5], ["V1", "A1", "A2"], "cd" * 32)]
        self.assertEqual(len({base, *changed}), 6)

    def test_audio_sha256(self):
        import hashlib
        st = mod("store").Store(self.tmp)
        p = self.tmp / "a.bin"
        p.write_bytes(b"hello" * 100000)
        self.assertEqual(st.audio_sha256(p), hashlib.sha256(b"hello" * 100000).hexdigest())

    def test_cache_keeps_exactly_the_three_newest_scans(self):
        st = mod("store").Store(self.tmp)
        keys = [st.cache_key("seq", [0, i], ["A1"], "ab" * 32) for i in range(1, 6)]
        for i, k in enumerate(keys):
            self.assertTrue(st.cache_put(k, {"n": i}))
            self.assertLessEqual(len(st.cache_list()), 3)
        self.assertEqual(st.cache_list(), [keys[4], keys[3], keys[2]])  # newest first
        self.assertEqual([k for k in keys if st.cache_get(k) is not None], keys[2:])
        self.assertEqual(st.cache_get(keys[4]), {"n": 4})
        self.assertEqual(len(list(st.cache_dir.glob("scan-*.json"))), 3)
        # a put of a known key refreshes it: it becomes the newest and nothing is evicted
        st.cache_put(keys[2], {"n": 22})
        self.assertEqual(st.cache_list(), [keys[2], keys[4], keys[3]])
        self.assertEqual(len(st.cache_list()), 3)
        self.assertEqual(st.cache_get(keys[2]), {"n": 22})

    def test_cache_ignores_foreign_and_broken_files(self):
        st = mod("store").Store(self.tmp)
        k = st.cache_key("seq", [0, 1], ["A1"], "ab" * 32)
        st.cache_put(k, {"n": 1})
        (st.cache_dir / "notes.txt").write_text("keep me", encoding="utf-8")
        (st.cache_dir / ("scan-" + "0" * 64 + ".json")).write_text("{broken", encoding="utf-8")
        self.assertEqual(st.cache_list(), [k])
        self.assertIsNone(st.cache_get("0" * 64))
        for i in range(4):
            st.cache_put(st.cache_key("seq", [0, 10 + i], ["A1"], "ab" * 32), {"n": i})
        self.assertTrue((st.cache_dir / "notes.txt").exists())  # only scan entries are ever evicted

    def test_cache_get_rejects_a_key_that_is_not_a_hash(self):
        st = mod("store").Store(self.tmp)
        self.assertIsNone(st.cache_get("../../settings"))
        self.assertIsNone(st.cache_get(""))


# ------------------------------------------------------------------ run -----------------------------------------------
class HushRun(NoNetwork):
    ITEMS = [("um", 500, 900, 0.9), ("so", 2600, 2900, 0.9), ("like", 3300, 3600, 0.8), ("uh", 5200, 5500, 0.9)]
    # speech_like(): speech 0-1.5 s, 2.5-4.0 s, 5.0-6.0 s; silences 1.5-2.5 s and 4.0-5.0 s; the words sit in the speech

    def wav(self, name="clip.wav", seed=3):
        p = self.tmp / name
        write_wav(p, pcm16(speech_like(seed=seed)), 16000)
        return p

    def scan(self, **kw):
        run = mod("run")
        runner = kw.pop("runner", None) or FakeRunner(self.ITEMS)
        kw.setdefault("make_runner", FakeFactory(runner))
        kw.setdefault("slot", lambda backend=None: contextlib.nullcontext("cuda"))
        return run.scan(kw.pop("wav", None) or self.wav(), **kw), runner

    def test_scan_without_fillers_has_the_envelope_stats_and_no_words(self):
        res, runner = self.scan(fillers_on=False)
        self.assertEqual(runner.calls, [])  # nothing transcribed
        self.assertEqual(res["duration"], 6.0)
        self.assertEqual(len(res["env"]), 600)
        self.assertEqual(res["env"].dtype, np.float32)
        self.assertEqual(res["fillers"], [])
        self.assertIsNone(res["words"])
        st = res["stats"]
        self.assertLess(st["floor"], -50)  # silence floor (the 0.0005 noise is about -66 dB)
        self.assertAlmostEqual(st["speech"], 20 * math.log10(0.3 / math.sqrt(2)), delta=1.0)  # 4.4 cycles per hop

    def test_scan_with_fillers_finds_strong_and_soft_ones_in_time_order(self):
        res, runner = self.scan(fillers_on=True, language="en")
        self.assertEqual(len(runner.calls), 1)
        labels = [(f["label"], f["on"], f["source"]) for f in res["fillers"]]
        self.assertEqual(labels, [("um", True, "word"), ("like", False, "word"), ("uh", True, "word")])  # "so" is no filler
        self.assertEqual([f["s"] for f in res["fillers"]], sorted(f["s"] for f in res["fillers"]))
        self.assertEqual([w["w"] for w in res["words"]], ["um", "so", "like", "uh"])
        self.assertEqual(res["language"], "en")

    def test_unclear_sounds_are_added_only_when_asked(self):
        res, _ = self.scan(fillers_on=True, language="en", cfg={"soundsOn": False})
        self.assertFalse([f for f in res["fillers"] if f["source"] == "sound"])
        res, _ = self.scan(fillers_on=True, language="en", cfg={"soundsOn": True})
        sounds = [f for f in res["fillers"] if f["source"] == "sound"]
        self.assertGreaterEqual(len(sounds), 2)  # loud stretches no word is near, e.g. 5.0-5.05 s and 5.65-6.0 s
        for f in sounds:
            self.assertEqual((f["label"], f["on"], f["kind"]), ("(sound)", False, "filler"))
            self.assertTrue(0.15 - 1e-9 <= f["e"] - f["s"] <= 1.2 + 1e-9, f)
            for w in res["words"]:  # nothing within 150 ms of a word
                self.assertTrue(f["e"] <= w["s"] - 0.14 or f["s"] >= w["e"] + 0.14, (f, w))
        self.assertEqual([f["s"] for f in res["fillers"]], sorted(f["s"] for f in res["fillers"]))  # one time-ordered list

    def test_plan_uses_the_settings_in_force_and_only_the_ticked_fillers(self):
        run, detect = mod("run"), mod("detect")
        res, _ = self.scan(fillers_on=True, language="en")
        cfg = run.default_cfg()
        cfg.update(tab="simple", intensity=50, tight=False)
        ticked = [f for f in res["fillers"] if f["on"]]
        p = run.plan(res, cfg, 25)  # chosen = the ticked ones
        st = mod("settings").current(cfg, res["stats"])
        want = detect.plan(res["env"], st, ticked, res["duration"], 25)
        self.assertEqual(p, want)
        self.assertGreater(p["removed"], 1.5)  # both silences (1.0 s each, minus 0.24 pads) and the fillers go
        self.assertEqual(p["before"], 6.0)
        none = run.plan(res, cfg, 25, [])
        self.assertLess(none["removed"], p["removed"])
        with_soft = run.plan(res, cfg, 25, res["fillers"])  # the unticked "like" included on request
        self.assertGreater(with_soft["removed"], p["removed"])

    def test_tight_cuts_right_up_to_the_speech(self):
        run = mod("run")
        res, _ = self.scan(fillers_on=False)
        loose = dict(run.default_cfg(), tab="simple", intensity=50, tight=False)
        tight = dict(loose, tight=True)
        a, b = run.plan(res, loose, 25), run.plan(res, tight, 25)
        self.assertGreater(b["removed"], a["removed"] + 0.2)  # the 0.12 s pads on both sides of 2 silences come back
        # the advanced tab ignores Tight and the intensity: the numbers typed in are used
        adv = dict(loose, tab="adv", tight=True, adv={"threshold": -40, "minSilence": 0.5, "padBefore": 0.1, "padAfter": 0.1})
        c = run.plan(res, adv, 25)
        self.assertAlmostEqual(c["removed"], 2 * (1.0 - 0.2), delta=0.1)

    def test_scan_cache_second_scan_does_not_transcribe_again(self):
        st = mod("store").Store(self.tmp)
        parts = {"sequence": "seq-1", "range": [0.0, 6.0], "tracks": ["A1"]}
        res1, runner = self.scan(fillers_on=True, language="en", store=st, key_parts=parts)
        self.assertFalse(res1["cached"])
        self.assertEqual(len(runner.calls), 1)
        res2, _ = self.scan(fillers_on=True, language="en", store=st, key_parts=parts, runner=runner)
        self.assertTrue(res2["cached"])
        self.assertEqual(len(runner.calls), 1)  # still one: the words came from the cache
        self.assertEqual(res2["fillers"], res1["fillers"])
        self.assertEqual(res2["stats"], res1["stats"])
        # another range or track set, other audio, or another language: transcribed again
        self.scan(fillers_on=True, language="en", store=st, key_parts=dict(parts, tracks=["A1", "A2"]), runner=runner)
        self.assertEqual(len(runner.calls), 2)
        self.scan(fillers_on=True, language="en", store=st, key_parts=parts, runner=runner, wav=self.wav("other.wav", seed=9))
        self.assertEqual(len(runner.calls), 3)
        self.scan(fillers_on=True, language="ar", store=st, key_parts=parts, runner=runner)
        self.assertEqual(len(runner.calls), 4)
        self.assertLessEqual(len(st.cache_list()), 3)

    def test_the_log_has_no_settings_and_no_keys(self):
        st = mod("store").Store(self.tmp)
        parts = {"sequence": "seq-secret-id", "range": [0.0, 6.0], "tracks": ["A1"]}
        cfg = {"listStrong": "zzmarkerzz", "adv": {"threshold": -123.456}, "intensity": 7713}
        self.scan(fillers_on=True, language="en", store=st, key_parts=parts, cfg=cfg)
        key = st.cache_list()[0]
        text = st.log_file.read_text(encoding="utf-8")
        self.assertIn("scan clip.wav 6.00s @16000", text)
        for secret in ("zzmarkerzz", "-123.456", "seq-secret-id", key, "listStrong", "intensity", "7713"):
            self.assertNotIn(secret, text, secret)

    def test_save_and_load_scan_round_trip(self):
        run = mod("run")
        res, _ = self.scan(fillers_on=True, language="en")
        p = self.tmp / "scan.json"
        run.save_scan(res, p)
        back = run.load_scan(p)
        self.assertTrue(np.array_equal(back["env"], res["env"]))
        self.assertEqual(back["env"].dtype, np.float32)
        self.assertEqual(back["fillers"], res["fillers"])
        self.assertEqual(run.plan(back, run.default_cfg(), 25), run.plan(res, run.default_cfg(), 25))
        self.assertNotIn(b"\r", p.read_bytes())

    def test_command_line_scan_then_plan(self):
        run = mod("run")
        wav = self.wav()
        out = self.tmp / "scan.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = run.main(["scan", str(wav), "--fillers", "--lang", "en", "--out", str(out), "--sequence", "seq-1",
                           "--start", "0", "--end", "6", "--tracks", "A1,A2"],
                          runner=FakeRunner(self.ITEMS), store=mod("store").Store(self.tmp))
        self.assertEqual(rc, 0)
        summary = json.loads(buf.getvalue().splitlines()[-1])
        self.assertTrue(summary["ok"])
        self.assertEqual((summary["duration"], summary["words"], summary["fillers"]), (6.0, 4, 3))
        self.assertTrue(out.is_file())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = run.main(["plan", str(out), "--fps", "29.97", "--intensity", "80", "--no-tight"])
        self.assertEqual(rc, 0)
        res = json.loads(buf.getvalue().splitlines()[-1])
        self.assertTrue(res["ok"])
        self.assertEqual(res["plan"]["before"], 6.0)
        self.assertEqual(set(res["summary"]), {"before", "after", "saved", "silences", "fillers"})
        self.assertRegex(res["summary"]["saved"], r"^\d+:\d\d\.\d$")
        self.assertEqual(res["summary"]["before"], "0:06.0")

    def test_command_line_errors(self):
        run = mod("run")
        for argv in ([], ["nope"], ["scan"], ["scan", str(self.tmp / "missing.wav")], ["plan", str(self.tmp / "missing.json")]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                rc = run.main(argv, runner=FakeRunner(self.ITEMS))
            self.assertNotEqual(rc, 0, argv)
            if buf.getvalue().strip():
                self.assertFalse(json.loads(buf.getvalue().splitlines()[-1])["ok"])


class HushPackage(unittest.TestCase):
    def test_licence_header_no_hoka_no_upstream_in_names(self):
        for name in ("words.py", "store.py", "run.py"):
            text = (LIB / name).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# SPDX-License-Identifier: GPL-3.0-or-later\n# © 2026 The Why Not AI"), name)
            self.assertNotIn("hoka", text.lower(), name)
        self.assertFalse([p for p in LIB.rglob("*") if "_upstream" in p.name])


if __name__ == "__main__":
    unittest.main()
