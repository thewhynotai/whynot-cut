"""Addendum M5-T3 (Task 58), the executor's cli.py and transcribe.py hunks: `reel brief`, `reel transcript-compact`,
`--verbose` and the short JSON of the six top token sinks (previews, plan, ppro-build, transcript-correct, audio-clean,
qc; ruling Q58-1), and the compact transcript written by transcribe's finalize().

Without --verbose those six verbs print lib/brief.SHORT_KEYS plus `full` (the file holding the whole document) and a
one-line `summary`; --verbose prints today's document byte for byte. Failures and refusals print whole in both modes,
with the same exit code. The library side (brief.py, transcript_compact.py) is tested in test_brief.py and
test_transcript_compact.py.
Case list: D:/ClaudeData/claude-api-lane/lane4/work/task58/cases.md (F22–F25, E19, A1; case ids in the test names).
Run:  bash tools/test.sh -p test_brief_cli.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

CLI = SK / "engine/reel/cli.py"
VID = "C0001"
SCOPE = ("previews", "plan", "ppro-build", "transcript-correct", "audio-clean", "qc")

FULL = {
    "previews": {"previews": 12, "contact_sheet": "x/_contact_sheet.jpg", "warnings": ["w"]},
    "plan": {"ok": True, "errors": [], "warnings": ["تحذير"], "events": 7, "cues": 3, "main_segments": 4,
             "edit_plan": "x/edit-plan.md"},
    "ppro-build": {"status": "PRPROJ_BUILT", "checks": {"all_graphics_placed": True}, "project": "x.prproj",
                   "bridge": {"ok": True, "elapsed_s": 3.2}, "result": {"placed": list(range(60))}, "at": "t",
                   "job_data": {"sequence_name": "s"}, "content_signature": "abc", "prproj_mtime": 1.5},
    "transcript-correct": {"meta": {"language": "ar", "video_vocabulary": ["a"] * 40}, "segments": 10, "words": 80,
                           "cues": 12, "short_cues": 30, "applied": 2, "flagged": 1, "reanchored": [], "problems": [],
                           "restored": []},
    "audio-clean": {"decisions": {"nr_db": 24}, "loudness": {"i": -16}, "metrics": {"snr": [1.0] * 50},
                    "regions_ms": [[i, i + 9] for i in range(300)], "pauses": 9, "removed_ms": 3100,
                    "new_duration_ms": 51000, "pause_params": {"min_pause_ms": 250, "pad_ms": 80},
                    "cut_verification": {"ok": True, "verdict": "pass"}},
    "qc": {"ok": True, "failed": [], "warnings": [{"check": "c", "result": "WARN", "detail": "d"}]},
}


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t58c", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_main(m, argv):
    so, se = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            m.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, so.getvalue(), se.getvalue()


def env():
    from test_plugin import isolated_env
    return isolated_env()


def make_root(tmp: Path) -> Path:
    root = tmp / "عميل تجربة Dr X"
    for d in ("assets", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text('{"whynot_client": 1}', encoding="utf-8")
    return root


def emitted(doc) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2, default=str) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t58cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = make_root(self.tmp)
        common.set_context(self.root, None)
        self.addCleanup(common.set_context, None)
        self.p = Paths(self.root, VID)
        self.p.ensure_project()
        self.m = cli_module()

    def out(self, verb, doc, verbose):
        self.m._RUN["a"] = argparse.Namespace(cmd=verb, verbose=verbose, root=str(self.root), video_id=VID,
                                              episode=None)
        so = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(so):
                self.m.out(json.loads(json.dumps(doc)))
        except SystemExit as e:
            code = e.code
        finally:
            self.m._RUN.pop("a", None)
        return code, so.getvalue()


class TestOut(Base):
    def test_f22_verbose_prints_todays_document_byte_for_byte(self):
        for v in SCOPE:
            with self.subTest(v):
                code, text = self.out(v, FULL[v], verbose=True)
                self.assertEqual((code, text), (0, emitted(FULL[v])))

    def test_f22_default_prints_the_short_schema(self):
        from lib import brief
        for v in SCOPE:
            with self.subTest(v):
                code, text = self.out(v, FULL[v], verbose=False)
                doc = json.loads(text)
                short, dropped = brief.short_doc(v, FULL[v])
                if dropped:
                    self.assertEqual({k: doc[k] for k in short}, short)
                    self.assertEqual(set(doc) - set(short), {"full", "summary"})
                    self.assertEqual(read_json(self.root / doc["full"]), FULL[v])
                else:
                    self.assertEqual(doc, FULL[v])
                self.assertEqual(code, 0)

    def test_f22_other_verbs_unchanged(self):
        doc = {"status": "TRANSCRIBED", "history": [1] * 30}
        for v in ("status", "next", "transcribe", "board"):
            self.m._RUN["a"] = argparse.Namespace(cmd=v, verbose=False, root=str(self.root), video_id=VID, episode=None)
            so = io.StringIO()
            with contextlib.redirect_stdout(so):
                self.m.out(doc, check=False)
            self.m._RUN.pop("a", None)
            self.assertEqual(so.getvalue(), emitted(doc), v)

    def test_f24_long_output_in_a_file_the_command_prints_path_and_summary(self):
        code, text = self.out("audio-clean", FULL["audio-clean"], verbose=False)
        doc = json.loads(text)
        self.assertEqual(doc["full"], f"output/projects/{VID}/logs/out/audio-clean.json")
        self.assertIn("regions_ms", doc["summary"])
        self.assertLess(len(text) * 4, len(emitted(FULL["audio-clean"])))

    def test_f25_failures_and_refusals_same_in_both_modes(self):
        fails = {"qc": {"ok": False, "failed": [{"check": "a"}], "warnings": [], "checks": [1] * 9},
                 "ppro-build": {"status": "EXISTS", "refused": "exists", "how": "--force", "result": {}},
                 "audio-clean": dict(FULL["audio-clean"], ok=False, how="listen")}
        for v, d in fails.items():
            with self.subTest(v):
                a = self.out(v, d, verbose=False)
                b = self.out(v, d, verbose=True)
                self.assertEqual(a, b)
                self.assertNotEqual(a[0], 0)

    def test_out_outside_main_prints_the_full_document(self):
        """A test or tool calling cmd_<verb>(a) directly (no main) gets the full document, as before."""
        so = io.StringIO()
        with contextlib.redirect_stdout(so):
            self.m.out(FULL["audio-clean"])
        self.assertEqual(so.getvalue(), emitted(FULL["audio-clean"]))


class TestMain(Base):
    def test_f22_qc_through_main_both_modes(self):
        r = {"ok": True, "failed": [], "checks": [{"check": "c", "result": "WARN", "detail": "d", "mandatory": False}]}
        with mock.patch("lib.qc.run_qc", return_value=r), mock.patch("lib.motion_config.is_motion", return_value=False):
            c1, o1, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "qc"])
            c2, o2, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "qc", "--verbose"])
            c3, o3, _ = run_main(self.m, ["--verbose", "--root", str(self.root), "--video-id", VID, "qc"])
        self.assertEqual((c1, c2, c3), (0, 0, 0))
        self.assertEqual(o2, o3)
        self.assertEqual(json.loads(o1), json.loads(o2))     # qc's short form is its whole document

    def test_f22_transcript_correct_through_main(self):
        full = FULL["transcript-correct"]
        with mock.patch("lib.transcribe.apply_corrections", return_value=dict(full)):
            c1, o1, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-correct"])
            c2, o2, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-correct",
                                          "--verbose"])
        self.assertEqual((c1, c2), (0, 0))
        self.assertEqual(o2, emitted(full))
        short = json.loads(o1)
        self.assertNotIn("meta", short)
        self.assertEqual(short["applied"], 2)
        self.assertEqual(read_json(self.root / short["full"]), full)

    def test_f25_error_guidance_same_in_both_modes(self):
        with mock.patch("lib.transcribe.apply_corrections", side_effect=FileNotFoundError("transcript-corrections.json missing")):
            c1, o1, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-correct"])
            c2, o2, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-correct",
                                          "--verbose"])
        self.assertEqual(c1, 1)
        self.assertEqual((c1, json.loads(o1)), (c2, json.loads(o2)))
        self.assertIs(json.loads(o1)["ok"], False)


class TestVerbs(Base):
    def test_a1_brief_verb_prints_the_brief_read_only(self):
        write_json(self.p.p("08_quality_control/qc-results.json"), {"ok": False, "checks": [],
                                                                   "failed": [{"check": "safe_area", "detail": "d"}]})
        before = {str(f): f.stat().st_mtime_ns for f in self.root.rglob("*")}
        code, text, err = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "brief"])
        self.assertEqual(code, 0, err)
        self.assertTrue(text.startswith(f"# brief {VID} · ~"), text[:80])
        self.assertIn("safe_area", text)
        self.assertEqual({str(f): f.stat().st_mtime_ns for f in self.root.rglob("*")}, before, "brief wrote a file")
        code, js, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "brief", "--json"])
        doc = json.loads(js)
        self.assertEqual(doc["text"], text)
        self.assertLessEqual(doc["tokens"], 1500)

    def test_brief_and_compact_classified(self):
        self.assertIn("brief", self.m.CORE_READS)
        self.assertIn("transcript-compact", self.m.CORE_WRITES)
        self.assertIn("brief", self.m.registered_commands())
        self.assertIn("transcript-compact", self.m.registered_commands())

    def test_brief_refuses_an_episode(self):
        code, text, _ = run_main(self.m, ["--root", str(self.root), "--episode", "EP01", "brief"])
        self.assertEqual(code, 2)
        self.assertIn("per video", json.loads(text)["refused"])

    def test_e19_transcript_compact_verb_path_and_summary(self):
        from test_transcript_compact import words_doc, AR
        tj, wj = words_doc(AR)
        write_json(self.p.p("02_transcription/transcript.json"), tj)
        write_json(self.p.p("02_transcription/words.json"), wj)
        code, text, err = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-compact"])
        self.assertEqual(code, 0, err)
        doc = json.loads(text)
        self.assertEqual(doc["path"], f"output/projects/{VID}/02_transcription/transcript.compact.md")
        self.assertTrue(doc["changed"])
        self.assertIn("3 lines", doc["summary"])
        code, text, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-compact"])
        self.assertFalse(json.loads(text)["changed"])

    def test_e21_transcript_compact_without_transcript_refuses_and_writes_nothing(self):
        code, text, _ = run_main(self.m, ["--root", str(self.root), "--video-id", VID, "transcript-compact"])
        self.assertEqual(code, 1)
        self.assertFalse(self.p.p("02_transcription/transcript.compact.md").exists())

    def test_e19_finalize_writes_the_compact_after_a_correction(self):
        from test_transcript_compact import words_doc, AR
        from lib import transcript_compact as TC
        from lib.transcribe import apply_corrections
        tj, wj = words_doc(AR)
        write_json(self.p.p("02_transcription/transcript.json"), tj)
        write_json(self.p.p("02_transcription/words.json"), wj)
        write_json(self.p.p("02_transcription/transcript-corrections.json"),
                   {"corrections": [{"word_id": 6, "from": "بيبيّن", "to": "بيبيّن لنا", "reason": "heard"}]})
        with mock.patch("lib.transcribe.document_quotes", return_value=[]):
            apply_corrections(self.p)
        self.assertEqual(TC.state(self.p)["state"], "current")
        self.assertIn("بيبيّن لنا", self.p.p(TC.REL).read_text(encoding="utf-8"))

    def test_e19_finalize_never_fails_on_the_compact(self):
        from test_transcript_compact import words_doc, AR
        from lib.transcribe import apply_corrections
        tj, wj = words_doc(AR)
        write_json(self.p.p("02_transcription/transcript.json"), tj)
        write_json(self.p.p("02_transcription/words.json"), wj)
        write_json(self.p.p("02_transcription/transcript-corrections.json"), {"corrections": []})
        with mock.patch("lib.transcribe.document_quotes", return_value=[]), \
                mock.patch("lib.transcript_compact.write", side_effect=OSError("disk")):
            r = apply_corrections(self.p)
        self.assertIn("segments", r)

    def test_brief_subprocess_on_a_fresh_client(self):
        r = subprocess.run([sys.executable, "-B", str(CLI), "--root", str(self.root), "--video-id", VID, "brief"],
                           capture_output=True, text=True, encoding="utf-8", env=env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("decision log: not built (K-T9 deferred)", r.stdout)
        self.assertIn("next: ", r.stdout)


if __name__ == "__main__":
    unittest.main()
