# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""T4.11 hooks (G13-RUN): cli.main lowers every verb but `serve` (cli.py.patch), episode-transcribe releases Whisper
inside its GPU slot (episode.py.patch), the preferences skill names the setting (SKILL.md.patch). Proved with the
patches applied (hooks/t411/*.patch); red without them.
Run:  bash tools/test.sh -p test_lean_runtime_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
if str(ENGINE) not in _sys.path:
    _sys.path.insert(0, str(ENGINE))

import cli  # noqa: E402
from lib import priority  # noqa: E402


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


class CliWiring(unittest.TestCase):
    def run_main(self, argv, apply_effect=None):
        calls, started = [], []
        with mock.patch.object(priority, "apply", side_effect=apply_effect or (lambda *a, **k: calls.append(1) or "normal")), \
                mock.patch.object(cli, "start", side_effect=lambda a: started.append(a.cmd)), quiet():
            try:
                cli.main(argv)
            except SystemExit:
                pass
        return calls, started

    def test_serve_is_never_lowered(self):
        for verb in (["serve"], ["serve", "status"], ["serve", "run"], ["serve", "ensure"]):
            calls, started = self.run_main(verb)
            self.assertEqual((calls, started), ([], ["serve"]), verb)

    def test_every_other_verb_is_lowered_once_after_parsing(self):
        calls, started = self.run_main(["doctor"])
        self.assertEqual((calls, started), ([1], ["doctor"]))
        for argv in (["--version"], ["--help"], ["no-such-verb"]):          # usage / version exit before it
            calls, started = self.run_main(argv)
            self.assertEqual((calls, started), ([], []), argv)

    def test_priority_is_imported_with_the_cli(self):
        # batch A: the "don't lower" decision is the WHYNOT_PRIORITY flag as the process started (priority._START);
        # cli imports priority at load, so a test that clears os.environ before cli.main cannot lower the runner
        src = (ENGINE / "cli.py").read_text(encoding="utf-8")
        self.assertRegex(src, r"(?m)^from lib import priority\b")
        self.assertIs(cli.priority, priority)
        self.assertEqual(priority._START, "normal")

    def test_a_failing_apply_never_breaks_the_verb(self):
        def boom(*a, **k):
            raise RuntimeError("no priority")
        calls, started = self.run_main(["doctor"], apply_effect=boom)
        self.assertEqual(started, ["doctor"])


class EpisodeRelease(unittest.TestCase):
    def go(self, ev, fail=None):
        from lib import episode as E
        from lib import gpu_lock
        from lib import transcribe as T
        tmp = Path(tempfile.mkdtemp())

        def p(rel):
            return tmp / rel
        ep = SimpleNamespace(p=p, ensure_project=lambda: None, episode_id="EP01")
        (tmp / "02_transcription").mkdir(parents=True)
        for n in ("transcript", "words"):
            (tmp / "02_transcription" / f"{n}.json").write_text("{}", encoding="utf-8")

        @contextlib.contextmanager
        def slot(*a, **k):
            ev.append("slot-in")
            try:
                yield "cpu"
            finally:
                ev.append("slot-out")

        def runner(*a, **k):
            return {}
        runner.backend, runner.state = "ct2", {}
        runner.release = lambda: ev.append("release")

        def chunks(*a, **k):
            ev.append("decode")
            if fail:
                raise fail
            return {"results": [], "language": "ar", "language_probability": 0.9, "elapsed_s": 1.0, "decoders": [],
                    "redecoded": [], "ran": 1}
        with mock.patch.object(E, "episode_file", return_value=tmp / "EP01.mp4"), \
                mock.patch.object(E, "sha1_head", return_value="fp"), \
                mock.patch.object(E, "read_json", return_value={"fingerprint": "fp"}), \
                mock.patch.object(E, "chunk_plan", return_value={"chunks": [1], "total_ms": 1000}), \
                mock.patch.object(E, "podcast_cfg", return_value={}), \
                mock.patch.object(E, "whisper_runner", return_value=runner), \
                mock.patch.object(E, "run_chunks", side_effect=chunks), \
                mock.patch.object(E, "stitch", return_value=([], [])), \
                mock.patch.object(T, "extract_audio", side_effect=lambda *a, **k: None), \
                mock.patch.object(T, "whisper_audio", return_value=[0.0] * 16000), \
                mock.patch.object(T, "finalize", return_value={"ok": True}), \
                mock.patch.object(gpu_lock, "whisper_slot", side_effect=slot), quiet():
            (tmp / "02_transcription" / "dialogue_16k_mono.wav").write_bytes(b"x")
            E.transcribe_episode(ep, "large-v3", force=False)
        return ev

    def test_released_inside_the_slot(self):
        ev = []
        self.go(ev)
        self.assertEqual(ev, ["slot-in", "decode", "release", "slot-out"])

    def test_released_on_error_and_ctrl_c(self):
        for err in (RuntimeError("decode failed"), KeyboardInterrupt()):
            ev = []
            with self.assertRaises(type(err)):
                self.go(ev, err)
            self.assertEqual(ev, ["slot-in", "decode", "release", "slot-out"], type(err).__name__)


class SkillText(unittest.TestCase):
    def test_preferences_skill_names_the_setting_in_words_a_user_understands(self):
        t = (SK / "skills" / "preferences" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`background_priority`", t)
        self.assertIn("شغل الخلفية بأولوية أقل عشان البريمير يفضل سلس", t)
        self.assertIn("Run background work at lower priority so Premiere stays smooth", t)


if __name__ == "__main__":
    unittest.main()
