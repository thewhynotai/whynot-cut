"""3.0 T2.2 — errors and exit codes (engine IM-7, MI-24; gap G71).

Common authoring mistakes give a plain-English `{"ok": false, "error", "where", "how"}` on stdout, never a Python
traceback on stdout or stderr (the traceback goes to logs/pipeline.log). Exit codes: 0 success, 1 an error or a failed
result (`ok: false`, a FAILED/REFUSED/BLOCKED status), 2 a refusal (`blocked` / `refused`, the approval gate, the
writer lease).
Run:  bash tools/test.sh -p test_errors.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import os
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


def reel(root, *argv, video_id=None):
    """Run the CLI as the editor's wrapper does: (exit code, stdout JSON or text, stderr)."""
    cmd = [sys.executable, "-B", str(CLI)] + (["--root", str(root)] if root else []) + \
        (["--video-id", video_id] if video_id else []) + list(argv)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=_isolation_env())
    doc = r.stdout
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        pass
    return r.returncode, doc, r.stderr


def _isolation_env():
    from test_plugin import isolated_env
    return isolated_env()


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t22", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_main(m, argv):
    """cli.main(argv) in this process: (exit code, stdout, stderr)."""
    so, se = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            m.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, so.getvalue(), se.getvalue()


def make_client(tmp: Path) -> Path:
    root = tmp / "Dr Test"
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t22_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestExitCodeOfAResult(unittest.TestCase):
    def test_mapping(self):
        from lib.errors import exit_code
        self.assertEqual(exit_code({"ok": True}), 0)
        self.assertEqual(exit_code({"files": 3}), 0)
        self.assertEqual(exit_code({"ok": False, "error": "x"}), 1)
        for st in ("FAILED", "REFUSED", "BLOCKED", "BRIDGE_NOT_RUNNING"):
            self.assertEqual(exit_code({"status": st}), 1, st)
        self.assertEqual(exit_code({"status": "PRPROJ_BUILT"}), 0)
        self.assertEqual(exit_code({"blocked": "edit plan not approved", "how": "approve"}), 2)
        self.assertEqual(exit_code({"ok": False, "blocked": "stale window"}), 2)
        self.assertEqual(exit_code({"refused": "sliced from the episode"}), 2)
        self.assertEqual(exit_code(["a list"]), 0)
        self.assertEqual(exit_code({"status": {"alive": False}}), 0)          # a nested status record
        self.assertEqual(exit_code({"ok": False, "status": {"alive": False}}), 1)

    def test_emit_prints_one_json_document_then_exits(self):
        from lib.errors import emit
        for doc, code in (({"ok": True}, None), ({"ok": False}, 1), ({"blocked": "x", "how": "y"}, 2)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                if code is None:
                    emit(doc)
                else:
                    with self.assertRaises(SystemExit) as cm:
                        emit(doc)
                    self.assertEqual(cm.exception.code, code)
            self.assertEqual(json.loads(buf.getvalue()), doc)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            emit({"status": "BLOCKED"}, check=False)            # `reel status`: a project state, not a failure
        self.assertEqual(json.loads(buf.getvalue()), {"status": "BLOCKED"})


class TestJsonFiles(TempDir):
    """MI-24 / IM-7: PowerShell 5.1 writes UTF-8 with a BOM; a broken file names itself and the line."""

    def test_read_json_accepts_a_bom(self):
        f = self.tmp / "edit-decisions.json"
        f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"global": {}, "decisions": []}).encode("utf-8"))
        self.assertEqual(read_json(f), {"global": {}, "decisions": []})

    def test_broken_json_names_the_file_and_line(self):
        from lib.errors import FileFormatError
        f = self.tmp / "broken.json"
        f.write_text('{\n  "a": 1,\n  "b": \n}\n', encoding="utf-8")
        with self.assertRaises(FileFormatError) as cm:
            read_json(f)
        e = cm.exception
        self.assertIsInstance(e, ValueError)                          # callers catching ValueError still do
        self.assertEqual((Path(e.path), e.line), (f, 4))
        self.assertIn(str(f), str(e))
        self.assertIn("line 4", str(e))

    def test_not_utf8_names_the_file_and_line(self):
        from lib.errors import FileFormatError
        f = self.tmp / "latin1.json"
        f.write_bytes(b'{\n"a": "caf\xe9"}\n')
        with self.assertRaises(FileFormatError) as cm:
            read_json(f)
        self.assertEqual(cm.exception.line, 2)
        self.assertIn("UTF-8", str(cm.exception))

    def test_settings_with_a_bom(self):
        from lib import settings as S
        fm, body = S.parse("﻿---\nlanguage: ar\napproval: auto\n---\nnotes\n")
        self.assertEqual((fm, body.strip()), ({"language": "ar", "approval": "auto"}, "notes"))
        d = self.tmp / "client" / ".claude"
        d.mkdir(parents=True)
        (d / S.FILE).write_bytes(b"\xef\xbb\xbf---\r\nlanguage: ar\r\n---\r\n")
        st = S.load(d.parent)
        self.assertEqual(st["language"], "ar")
        self.assertEqual(st["_problems"], [])

    def test_settings_not_utf8_is_a_problem_with_file_and_line(self):
        from lib import settings as S
        d = self.tmp / "client" / ".claude"
        d.mkdir(parents=True)
        (d / S.FILE).write_bytes(b"---\nlanguage: ar\neditor_name: Ren\xe9\n---\n")
        st = S.load(d.parent)                                     # the hooks read it: never a crash
        self.assertEqual(st["language"], "en")
        self.assertEqual(len(st["_problems"]), 1)
        self.assertIn("line 3", st["_problems"][0])
        self.assertIn(str(d / S.FILE), st["_problems"][0])


class TestPlanValidation(TempDir):
    """IM-7: a decision without `start` (or with a time that is not one) is an error in the plan, not a KeyError."""

    def setUp(self):
        super().setUp()
        from test_pipeline import make_project
        self.root, self.p, self.words = make_project(self.tmp)

    def decisions(self, **glob):
        return {"video_id": "CLIP1", "global": glob, "decisions": [
            {"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
             "end": "00:00:04.000", "semantic_intent": "hook", "visual_treatment": "hook", "confidence": "high",
             "camera": {"type": "punch_in", "scale_factor": 1.1},
             "graphics": [{"id": "GFX_001", "template": "hook_title", "text": "حاجات"}],
             "sound": [{"type": "pop"}]},
            {"decision_id": "EDIT_002", "segment_id": "SEG_002", "evidence": "التشخيص الصحيح",
             "start": "soon", "end": "00:00:09.000", "semantic_intent": "x", "visual_treatment": "x",
             "confidence": "high"},
            {"decision_id": "EDIT_003", "segment_id": "SEG_003", "evidence": "التشخيص الصحيح",
             "start": "00:00:05.000", "end": "00:00:09.000", "semantic_intent": "x", "visual_treatment": "x",
             "confidence": "high", "camera": {"type": "punch_in", "scale_factor": "big"},
             "graphics": [{"id": "GFX_002", "template": "hook_title", "text": "x", "start": "later"}]}],
            "caption_highlights": [{"text": "التشخيص", "at": "then"}],
            "music": {"status": "NO_MUSIC_SUPPLIED", "cue_points": [{"label": "drop", "at": "drop"}]}}

    def good(self, **glob):
        """One valid decision."""
        d = self.decisions(**glob)
        d["decisions"] = d["decisions"][:1]
        d["decisions"][0]["start"] = "00:00:00.200"
        del d["caption_highlights"], d["music"]
        return d

    def test_missing_and_bad_times_are_plan_errors(self):
        from lib.plan import compile_plan
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.decisions(main_footage="data/Raw/CLIP1.mov"))
        r = compile_plan(self.p)
        self.assertFalse(r["ok"])
        errs = " | ".join(r["errors"])
        self.assertIn("EDIT_001: missing 'start'", errs)
        self.assertIn("EDIT_002: start", errs)
        self.assertIn("'soon'", errs)
        self.assertIn("GFX_002: start", errs)
        self.assertIn("EDIT_003: camera.scale_factor 'big'", errs)
        self.assertIn("caption_highlights", errs)
        self.assertIn("music cue 'drop'", errs)
        self.assertFalse(self.p.p("01_analysis/timeline-spec.json").exists())

    def test_bom_edit_decisions_compile(self):
        from lib.plan import compile_plan
        good = self.good(main_footage="data/Raw/CLIP1.mov")
        self.p.p("01_analysis/edit-decisions.json").write_bytes(
            b"\xef\xbb\xbf" + json.dumps(good, ensure_ascii=False).encode("utf-8"))
        r = compile_plan(self.p)
        self.assertTrue(r["ok"], r["errors"])

    def test_g71_main_footage_defaults_to_the_clip_of_this_id(self):
        from lib.plan import compile_plan
        clip = self.root / "data/Raw/CLIP1.mov"
        write_json(self.root / "output/discovery/input-inventory.json",
                   {"files": [{"path": str(clip), "rel": "data/Raw/CLIP1.mov", "role": "source_footage"}]})
        good = self.good()
        write_json(self.p.p("01_analysis/edit-decisions.json"), good)
        r = compile_plan(self.p)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("global.main_footage" in w for w in r["warnings"]), r["warnings"])
        spec = read_json(self.p.p("01_analysis/timeline-spec.json"))
        self.assertEqual(spec["main_footage"], "data/Raw/CLIP1.mov")

    def test_g71_no_main_footage_and_no_clip_is_a_plan_error(self):
        from lib.plan import compile_plan
        good = self.good()                                       # no discovery: nothing to default to
        write_json(self.p.p("01_analysis/edit-decisions.json"), good)
        r = compile_plan(self.p)
        self.assertFalse(r["ok"])
        self.assertTrue(any("global.main_footage missing" in e for e in r["errors"]), r["errors"])

    def test_g71_main_footage_that_does_not_exist_is_a_plan_error(self):
        from lib.plan import compile_plan
        good = self.good(main_footage="data/Raw/GONE.mov")
        write_json(self.p.p("01_analysis/edit-decisions.json"), good)
        r = compile_plan(self.p)
        self.assertFalse(r["ok"])
        self.assertTrue(any("data/Raw/GONE.mov" in e and "not found" in e for e in r["errors"]), r["errors"])

    def test_g71_later_stages_give_guidance_for_a_spec_without_footage(self):
        """A spec compiled before the fix (main_footage null): previews / preview-video / verify / premiere say what
        to do instead of a TypeError."""
        from lib.errors import Guidance
        spec = {"video_id": "CLIP1", "fps": 24, "main_footage": None, "events": [], "main_segments": [],
                "duration_ms": 1000, "duration_frames": 24}
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec)
        with self.assertRaises(Guidance) as cm:
            common.spec_footage(self.p, spec)
        self.assertIn("main_footage", cm.exception.error)
        self.assertIn("reel plan", cm.exception.how)
        code, doc, err = reel(self.root, "previews", video_id="CLIP1")
        self.assertEqual(code, 1, (doc, err))
        self.assertIn("main_footage", doc["error"])
        self.assertNotIn("Traceback", err)

    def test_plan_with_errors_exits_1(self):
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.decisions(main_footage="data/Raw/CLIP1.mov"))
        for f in ("01_analysis/editing-style.json", "01_analysis/narrative-segments.json",
                  "01_analysis/transcript-semantic-analysis.json"):
            write_json(self.p.p(f), {})
        for f in ("01_analysis/main-topic.md", "01_analysis/medical-content-review.md"):
            self.p.p(f).write_text("x", encoding="utf-8")
        code, doc, err = reel(self.root, "plan", video_id="CLIP1")
        self.assertEqual(code, 1, err)
        self.assertFalse(doc["ok"])
        self.assertNotIn("Traceback", err)


class TestCliGuidance(TempDir):
    """No traceback reaches the editor: the handler prints guidance JSON, exits 1 and logs the traceback."""

    def setUp(self):
        super().setUp()
        self.root = make_client(self.tmp)

    def assert_guidance(self, code, doc, err, *, error_has=(), how_has=()):
        self.assertEqual(code, 1, (doc, err))
        self.assertIsInstance(doc, dict, doc)
        self.assertIs(doc["ok"], False)
        for k in ("error", "where", "how", "log"):
            self.assertTrue(doc.get(k), (k, doc))
        for s in error_has:
            self.assertIn(s, doc["error"])
        for s in how_has:
            self.assertIn(s, doc["how"])
        self.assertNotIn("Traceback", err)
        self.assertNotIn("Traceback", json.dumps(doc))
        log = Path(doc["log"])
        self.assertTrue(log.is_file(), log)
        self.assertIn("Traceback", log.read_text(encoding="utf-8"))
        return doc

    def test_ref_analyze_before_discover(self):
        code, doc, err = reel(self.root, "ref-analyze")
        doc = self.assert_guidance(code, doc, err, how_has=("reel discover",))
        self.assertEqual(Path(doc["log"]), self.root / "output/logs/pipeline.log")

    def test_broken_json_file_names_file_and_line(self):
        p = Paths(self.root, "C1")
        p.ensure_project()
        p.p("00_inputs/source.json").write_text('{"footage": "data/Raw/a.mp4",\n "in_ms": }', encoding="utf-8")
        code, doc, err = reel(self.root, "range", video_id="C1")
        doc = self.assert_guidance(code, doc, err, error_has=("line 2",))
        self.assertIn("source.json", doc["where"])
        self.assertEqual(Path(doc["log"]), p.p("logs/pipeline.log"))     # the project's own log

    def test_timeout_gives_guidance(self):
        m = cli_module()
        boom = subprocess.TimeoutExpired(["ffmpeg", "-i", "x.mov"], 600)
        with mock.patch.object(m, "cmd_status", side_effect=boom):
            code, out, err = run_main(m, ["--root", str(self.root), "--video-id", "C1", "status"])
        self.assert_guidance(code, json.loads(out), err, error_has=("ffmpeg", "600"))

    def test_failed_ffmpeg_keeps_its_message(self):
        """Gate 2 minor: a CalledProcessError lost ffmpeg's stderr ("unexpected CalledProcessError")."""
        m = cli_module()
        boom = subprocess.CalledProcessError(1, ["ffmpeg", "-i", "x.mov"], output="",
                                             stderr="ffmpeg version 7.1\n...\nx.mov: Invalid data found when processing input\n")
        with mock.patch.object(m, "cmd_status", side_effect=boom):
            code, out, err = run_main(m, ["--root", str(self.root), "--video-id", "C1", "status"])
        doc = self.assert_guidance(code, json.loads(out), err, error_has=("ffmpeg", "exit 1", "Invalid data found"),
                                   how_has=("media file plays",))
        self.assertNotIn("unexpected", doc["error"])
        from lib.errors import describe
        d = describe(subprocess.CalledProcessError(2, ["tool"], stderr=b"bad \xff byte\n"))
        self.assertIn("tool failed (exit 2): bad", d["error"])

    def test_bench_without_audio_goes_through_the_handler(self):
        """Gate 2 minor: `reel bench` printed its own JSON and exited 2; now the one guidance document, exit 1."""
        m = cli_module()
        code, out, err = run_main(m, ["bench", "--audio", str(self.tmp / "missing.wav")])
        doc = json.loads(out)
        self.assertEqual((code, doc["ok"]), (1, False), doc)
        self.assertIn("no speech recording", doc["error"])
        self.assertIn("reel bench --audio", doc["how"])

    def test_audio_clean_failed_verification_exits_1(self):
        """Gate 2 minor: cuts not proven to keep every word (cut verification ok false) exited 0."""
        import argparse
        from lib import audio_clean, recipes
        m = cli_module()
        p = Paths(self.root, "C1")
        a = argparse.Namespace(hum="off", min_pause=None, pad=None, nr=12, expander=True, no_verify=False)
        clean = {"decisions": {}, "loudness": {}, "metrics": {}, "regions_ms": []}
        pauses = {"pauses_ms": [[1000, 1500]], "removed_ms": 500, "new_duration_ms": 9500}
        for verdict, want in (({"ok": False, "missing": ["كلمة"]}, 1), ({"ok": True, "missing": []}, 0)):
            so = io.StringIO()
            with mock.patch.object(m, "P", return_value=p), mock.patch.object(m, "refuse_stale_window"), \
                    mock.patch.object(m, "main_footage", return_value=[self.tmp / "a.mov"]), \
                    mock.patch.object(recipes, "pause_params", return_value={"min_pause_ms": 250, "pad_ms": 80}), \
                    mock.patch.object(audio_clean, "clean", return_value=clean), \
                    mock.patch.object(audio_clean, "detect_pauses", return_value=dict(pauses)), \
                    mock.patch.object(audio_clean, "verify_cuts", return_value=verdict), \
                    contextlib.redirect_stdout(so):
                code = 0
                try:
                    m.cmd_audio_clean(a)
                except SystemExit as e:
                    code = e.code
            doc = json.loads(so.getvalue())
            self.assertEqual(code, want, doc)
            self.assertEqual(doc.get("ok", True), not want)

    def test_unexpected_error_still_gives_guidance(self):
        m = cli_module()
        with mock.patch.object(m, "cmd_status", side_effect=TypeError("'NoneType' object is not subscriptable")):
            code, out, err = run_main(m, ["--root", str(self.root), "--video-id", "C1", "status"])
        doc = self.assert_guidance(code, json.loads(out), err)
        self.assertIn("cli.py", doc["where"])

    def test_without_a_client_the_traceback_goes_to_the_engine_home_log(self):
        m = cli_module()
        with mock.patch.object(m, "cmd_profile", side_effect=KeyError("id")):
            code, out, err = run_main(m, ["profile"])
        doc = self.assert_guidance(code, json.loads(out), err)
        self.assertEqual(Path(doc["log"]), common.engine_home() / "logs" / "pipeline.log")

    def test_refusals_stay_2_and_string_exits_stay_1(self):
        code, doc, err = reel(self.root, "ae-script", video_id="C1")          # an extra without --extras
        self.assertEqual(code, 2, err)
        self.assertIn("blocked", doc)
        code, doc, err = reel(None, "scaffold")                                 # SystemExit("...") message
        self.assertEqual(code, 1)
        self.assertIn("--root required", err)
        self.assertNotIn("Traceback", err)

    def test_status_of_a_blocked_project_exits_0(self):
        p = Paths(self.root, "C1")
        p.ensure_project()
        common.set_status(p, "BLOCKED", "qc failed", "qc")
        code, doc, err = reel(self.root, "status", video_id="C1")
        self.assertEqual((code, doc["status"]), (0, "BLOCKED"), err)

    def test_failed_preview_video_exits_1(self):
        p = Paths(self.root, "C1")
        p.ensure_project()
        code, doc, err = reel(self.root, "preview-video", video_id="C1")      # no plan yet
        self.assertEqual(code, 1, (doc, err))
        self.assertIs(doc["ok"], False)


class TestSilentAudio(TempDir):
    def test_loudness_of_silence_is_guidance(self):
        from lib import audio_clean
        from lib.errors import Guidance
        wav = self.tmp / "silence.wav"
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=48000:cl=mono", "-t", "2", str(wav)], check=True)
        with self.assertRaises(Guidance) as cm:
            audio_clean._loudness(wav)
        self.assertIn("silent", cm.exception.error)
        self.assertTrue(cm.exception.how)

    def test_loudness_of_speech_level_audio(self):
        from lib import audio_clean
        wav = self.tmp / "tone.wav"
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "sine=f=440:r=48000:d=2", str(wav)], check=True)
        lufs, tp = audio_clean._loudness(wav)
        self.assertLess(lufs, 0)
        self.assertLess(tp, 1)


class TestRenderTimeouts(TempDir):
    """aerender that never returns: a FAILED result that says what to do, not a TimeoutExpired traceback."""

    def test_ae_render_timeout(self):
        from lib import ae_render
        exe = self.tmp / "aer_fake.exe"
        exe.write_bytes(b"")
        aep = self.tmp / "p.aep"
        aep.write_bytes(b"aep")
        log = self.tmp / "aerender.log"
        boom = subprocess.TimeoutExpired(["aerender"], 7, output="rendering 10%")
        with mock.patch.object(ae_render, "aerender_exe", return_value=str(exe)), \
                mock.patch.object(ae_render, "run", side_effect=boom):
            r = ae_render.render(aep, "MAIN", self.tmp / "o.mov", "Best", "Lossless", timeout=7, log=log)
        self.assertEqual(r["status"], "FAILED")
        self.assertIn("7", r["msg"])
        self.assertTrue(r["how"])
        self.assertEqual(r["log"], str(log))
        self.assertIn("rendering 10%", log.read_text(encoding="utf-8"))

    def test_document_tools_have_a_timeout(self):
        """Gate 2 minor: textutil / mdls ran without a timeout inside the discovery lock (a cloud placeholder hangs)."""
        from lib import discover
        calls = []

        def run(cmd, **kw):
            calls.append((cmd[0], kw.get("timeout")))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 0)
        for name in ("brief.docx", "colours.pdf"):
            f = self.tmp / name
            f.write_bytes(b"x")
            with mock.patch.object(discover.shutil, "which", return_value="/usr/bin/tool"), \
                    mock.patch.object(discover, "run", run):
                self.assertIn("unreadable", discover.read_document(f))
        self.assertEqual([c[0] for c in calls], ["textutil", "mdls"])
        self.assertTrue(all(t and t <= 120 for _, t in calls), calls)

    def test_ae_builder_render_timeout(self):
        from lib import ae_builder
        root = make_client(self.tmp)
        p = Paths(root, "C1")
        p.ensure_project()
        exe = self.tmp / "aer_fake.exe"
        exe.write_bytes(b"")
        write_json(p.output / "discovery/environment.json", {"aerender": str(exe)})
        aep = p.p(f"04_after_effects/project/C1_{common.project_prefix()}_GFX.aep")
        aep.parent.mkdir(parents=True, exist_ok=True)
        aep.write_bytes(b"aep")
        with mock.patch.object(ae_builder, "run", side_effect=subprocess.TimeoutExpired(["aerender"], 9)):
            r = ae_builder.render(p, timeout=9)
        self.assertEqual(r["status"], "FAILED")
        self.assertIn("9", r["msg"])
        self.assertTrue(r["how"])


if __name__ == "__main__":
    unittest.main()
