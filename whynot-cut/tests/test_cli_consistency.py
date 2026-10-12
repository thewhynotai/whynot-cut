"""3.0 T2.16 — CLI consistency (engine MI-1..5, plugin structure 3.7) and the minors carried from earlier reviews.

One CLI-level (subprocess or in-process `cli.main`) or unit test per fixed form: `reels-select --by` only with
`--pick`, the `verify --record --verdict` form, `music --list`, `--note` / `--notes` everywhere, comma lists everywhere
(`--confirm-avoid R05,R06`), "nothing built" is never exit 0, the log fallback, status / next notes, validate lookup,
handoff --delivered, half-made reel folders, frame size through common, the ffmpeg timeout cap.
Run:  bash tools/test.sh -p test_cli_consistency.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

CLI = SK / "engine/reel/cli.py"
GUARD = SK / "hooks/guard.py"


def env():
    from test_plugin import isolated_env
    return isolated_env()


def reel(root, *argv, video_id=None, episode=None):
    """The CLI as a subprocess: (exit code, stdout JSON or text, stderr)."""
    cmd = [sys.executable, "-B", str(CLI)] + (["--root", str(root)] if root else []) + \
        (["--video-id", video_id] if video_id else []) + (["--episode", episode] if episode else []) + list(argv)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env())
    try:
        return r.returncode, json.loads(r.stdout), r.stderr
    except ValueError:
        return r.returncode, r.stdout, r.stderr


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t216", CLI)
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
            if isinstance(e.code, str):           # what `reel` prints on stderr for a message exit
                se.write(e.code + "\n")
    return code, so.getvalue(), se.getvalue()


def make_client(tmp: Path) -> Path:
    root = tmp / "Dr Test"
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t216_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = make_client(self.tmp)
        self.addCleanup(common.set_context, None)


class InProcess(Base):
    """cli.main in this process with the work patched out: the parsed forms reach the command as one list."""

    def setUp(self):
        super().setUp()
        self.m = cli_module()

    def main(self, *argv):
        return run_main(self.m, ["--root", str(self.root), *argv])


# --------------------------------------------------------------------------- comma lists (MI-5)
class TestArgLists(unittest.TestCase):
    def test_items_split_commas_and_repeats(self):
        from lib.arglists import items
        self.assertEqual(items(["R01,R03", "R05", " R03 ", ""]), ["R01", "R03", "R05"])
        self.assertEqual(items("R05,R06"), ["R05", "R06"])
        self.assertEqual(items(None), [])

    def test_adjust_and_set_split_only_where_an_item_starts(self):
        from lib.arglists import ADJUST_START, SETTING_START, items
        self.assertEqual(items(["R03:in=00:12:04,000,R05:out=00:13:05"], start=ADJUST_START),
                         ["R03:in=00:12:04,000", "R05:out=00:13:05"])
        self.assertEqual(items(["editor_name=Ali, Omar,approval=auto"], start=SETTING_START),
                         ["editor_name=Ali, Omar", "approval=auto"])

    def test_int_items_names_a_bad_value(self):
        from lib.arglists import int_items
        self.assertEqual(int_items(["79,80", "81"], "--words"), [79, 80, 81])
        with self.assertRaises(SystemExit) as cm:
            int_items(["79,x"], "--words")
        self.assertIn("'x'", str(cm.exception))


class TestListOptionsReachTheCommand(InProcess):
    def test_reels_select_lists_note_alias_and_confirm_avoid(self):
        with mock.patch("lib.reels.select", return_value={"reels": []}) as sel:
            code, out, err = self.main("--episode", "EP1", "reels-select", "--pick", "R01,R03", "--pick", "R05",
                                       "--adjust", "R03:in=00:12:04,000,R05:out=00:13:05", "--by", "delegated",
                                       "--notes", "you choose", "--confirm-avoid", "R05,R06")
        self.assertEqual(code, 0, (out, err))
        args, kw = sel.call_args
        self.assertEqual(args[1:4], (["R01", "R03", "R05"], ["R03:in=00:12:04,000", "R05:out=00:13:05"],
                                     "delegated"))
        self.assertEqual(kw["confirm_avoid"], ["R05", "R06"])
        self.assertEqual(kw["note"], "you choose")

    def test_reels_preview_ids(self):
        with mock.patch("lib.reels.render_candidates", return_value={}) as rc:
            code, out, err = self.main("--episode", "EP1", "reels-preview", "--ids", "R01,R03", "--ids", "R07")
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(rc.call_args.args[1], ["R01", "R03", "R07"])

    def test_motion_render_scenes(self):
        with mock.patch("lib.motion_render.render", return_value={"status": "RENDERED"}) as r:
            code, out, err = self.main("--video-id", "EP1_R01_MO", "motion-render", "--scenes", "S03,S05",
                                       "--scenes", "S07")
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(r.call_args.kwargs["scenes"], ["S03", "S05", "S07"])

    def test_transcript_relisten_words(self):
        with mock.patch("lib.transcribe.relisten", return_value={}) as r:
            code, out, err = self.main("--video-id", "CLIP1", "transcript-relisten", "--words", "79,80", "--words", "81")
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(r.call_args.args[1], [79, 80, 81])

    def test_settings_set_takes_a_comma_list(self):
        folder = self.tmp / "editor"
        folder.mkdir()
        code, doc, err = reel(None, "settings", "--init", str(folder), "--set", "approval=auto,preview_video=false")
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual((doc["approval"], doc["preview_video"]), ("auto", False))


# --------------------------------------------------------------------------- reels-select --by (MI-1)
class TestReelsSelectBy(InProcess):
    def test_resync_needs_no_by(self):
        from lib.episode import EpisodePaths
        ep = EpisodePaths(self.root, "EP1")
        ep.p("01_analysis").mkdir(parents=True)
        src = self.root / "data/ep.mp4"
        src.write_bytes(b"x" * 64)
        with mock.patch("lib.episode.load_episode", return_value={}), \
                mock.patch("lib.episode.episode_file", return_value=src):
            code, out, err = self.main("--episode", "EP1", "reels-select", "--resync")
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(json.loads(out)["reels"], [])

    def test_pick_without_by_is_refused_with_the_form(self):
        with mock.patch("lib.reels.select") as sel:
            code, out, err = self.main("--episode", "EP1", "reels-select", "--pick", "R01")
        self.assertEqual(code, 2, (out, err))                 # a JSON refusal, like verify --record (T2.16 review)
        doc = json.loads(out)
        self.assertIn("--by editor|delegated required with --pick", doc["refused"])
        self.assertIn("--pick R01,R03 --by editor", doc["how"])
        sel.assert_not_called()

    def test_the_avoid_hint_names_the_comma_form(self):
        src = (SK / "engine/reel/lib/reels.py").read_text(encoding="utf-8")
        self.assertIn("--confirm-avoid {','.join(blocked)}", src)


# --------------------------------------------------------------------------- --note / --notes (MI-5), verify (MI-2)
class TestNoteAlias(InProcess):
    def parsed(self, *argv):
        box = []
        with mock.patch.object(self.m, "start", side_effect=lambda a: box.append(a)):
            run_main(self.m, list(argv))
        return box[0]

    def test_every_command_takes_both_spellings(self):
        for argv in (["approve-plan", "--by", "editor"], ["transcript-verify"], ["verify", "--record"],
                     ["handoff", "--delivered"]):
            for flag in ("--note", "--notes"):
                with self.subTest(cmd=argv[0], flag=flag):
                    self.assertEqual(self.parsed(*argv, flag, "words").note, "words")

    def test_reels_select_and_ae_probe(self):
        self.assertEqual(self.parsed("reels-select", "--notes", "w").note, "w")
        with mock.patch("lib.ae_probe.record", return_value={"ok": True}) as rec:
            code, out, err = run_main(self.m, ["ae-probe", "--record", "ok", "--word-order", "logical", "--note", "x"])
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(rec.call_args.args, ("ok", "x", "logical"))


class TestVerifyForm(InProcess):
    def test_record_without_verdict_is_a_refusal(self):
        Paths(self.root, "CLIP1").ensure_project()
        code, doc, err = reel(self.root, "verify", "--record", "--note", "x", video_id="CLIP1")
        self.assertEqual(code, 2, (doc, err))
        self.assertIn("--verdict", doc["refused"])
        self.assertIn("--record --verdict pass|fail", doc["how"])

    def test_motion_frames_hint_is_the_real_form(self):
        with mock.patch("lib.motion_render.frames", return_value={"frames": []}):
            code, out, err = self.main("--video-id", "EP1_R01_MO", "motion-frames")
        self.assertEqual(code, 0, (out, err))
        self.assertIn("reel verify --record --verdict pass|fail", json.loads(out)["next"])
        self.assertNotIn("--record pass", out)

    def test_verify_without_a_plan_is_guidance(self):
        Paths(self.root, "CLIP1").ensure_project()
        code, doc, err = reel(self.root, "verify", video_id="CLIP1")
        self.assertEqual(code, 1, (doc, err))
        self.assertIn("no compiled plan yet", doc["error"])
        self.assertEqual(doc["how"], "Run `reel plan` first")
        self.assertNotIn("not found:", doc["error"])


class TestMusicList(Base):
    def test_music_list_works(self):
        code, doc, err = reel(self.root, "music", "--list")
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual(doc["tracks"], [])
        self.assertIn("data/Music", doc["how"])


# --------------------------------------------------------------------------- exit codes: nothing built
class TestNothingBuiltIsNotExit0(Base):
    def setUp(self):
        super().setUp()
        common.set_context(self.root)
        self.p = Paths(self.root, "CLIP1")
        self.p.ensure_project()

    def test_ppro_build_exists_is_a_refusal(self):
        from lib import ppro_build
        from lib.errors import exit_code
        prproj = self.p.p(f"07_premiere/project/CLIP1_{common.project_prefix()}_EDIT.prproj")
        prproj.parent.mkdir(parents=True, exist_ok=True)
        prproj.write_bytes(b"x")
        r = ppro_build._build_locked(self.p, prproj, overwrite=False, replace_edited=False)
        self.assertEqual(r["status"], "EXISTS")
        self.assertIn("--force", r["how"])
        self.assertEqual(exit_code(r), 2)

    def test_ppro_build_missing_graphics_fails(self):
        from lib import ppro_build
        from lib.errors import exit_code
        prproj = self.p.p(f"07_premiere/project/CLIP1_{common.project_prefix()}_EDIT.prproj")
        with mock.patch.object(ppro_build, "job_data", return_value={"_missing": ["GFX_001.png"]}):
            r = ppro_build._build_locked(self.p, prproj, overwrite=False, replace_edited=False)
        self.assertEqual(r["status"], "MISSING_GRAPHICS")
        self.assertIn("reel previews", r["how"])
        self.assertEqual(exit_code(r), 1)

    def test_ae_build_unsupported_and_refused(self):
        from lib import ae_builder
        from lib.errors import exit_code
        jsx = self.tmp / "b.jsx"
        for res in ({"status": "UNSUPPORTED", "msg": "After Effects not installed"},
                    {"status": "REFUSED", "msg": "sandbox", "how": "x"}):
            with self.subTest(status=res["status"]), mock.patch("lib.adobe_run.run_after_effects", return_value=res):
                r = ae_builder.execute(self.p, jsx)
            self.assertEqual(r["status"], res["status"])          # REFUSED is not overwritten by FAILED
            self.assertIs(r["ok"], False)
            self.assertEqual(exit_code(r), 1)

    def test_ae_render_skipped_fails(self):
        from lib import ae_builder
        from lib.errors import exit_code
        with mock.patch("lib.adobe_run.aerender", return_value=None):
            r = ae_builder.render(self.p)
        self.assertEqual(r["status"], "SKIPPED")
        self.assertEqual(exit_code(r), 1)
        self.assertTrue(r["how"])

    def test_ps_build_unsupported_refused_and_nothing_saved(self):
        from lib import ps_builder
        from lib.errors import exit_code
        jsx = self.tmp / "p.jsx"
        for res, want in (({"status": "UNSUPPORTED"}, "UNSUPPORTED"), ({"status": "REFUSED", "how": "x"}, "REFUSED"),
                          ({"status": "DONE"}, "FAILED")):
            with self.subTest(status=want), mock.patch("lib.adobe_run.run_photoshop", return_value=res):
                r = ps_builder.execute(self.p, jsx)
            self.assertEqual(r["status"], want)
            self.assertEqual(exit_code(r), 1)

    def test_mogrt_build_unsupported_fails(self):
        from lib import mogrt_builder
        from lib.errors import exit_code
        with mock.patch.object(mogrt_builder, "generate", return_value=self.tmp / "m.jsx"), \
                mock.patch("lib.adobe_run.run_after_effects", return_value={"status": "UNSUPPORTED"}):
            self.assertEqual(exit_code(mogrt_builder.build(self.p)), 1)


class TestPodcastAndMotionFailuresExit1(InProcess):
    def test_reels_plan_with_errors(self):
        r = {"ok": False, "errors": ["R01: no evidence"], "warnings": [], "candidates": []}
        with mock.patch("lib.reels.compile_reels_plan", return_value=r):
            code, out, err = self.main("--episode", "EP1", "reels-plan")
        self.assertEqual(code, 1, (out, err))
        self.assertFalse(json.loads(out)["ok"])

    def test_motion_plan_with_errors(self):
        r = {"ok": False, "errors": ["S01: x"], "warnings": [], "approvals": [], "editorial_lines": [], "plan": None,
             "md": "m"}
        with mock.patch("lib.motion_plan.compile_motion", return_value=r):
            code, out, err = self.main("--video-id", "EP1_R01_MO", "motion-plan")
        self.assertEqual(code, 1, (out, err))

    def test_episode_next_reports_a_state(self):
        with mock.patch("lib.episode.episode_next", return_value={"status": "BLOCKED", "next": "x"}):
            code, out, err = self.main("--episode", "EP1", "episode-next")
        self.assertEqual(code, 0, (out, err))


class TestLockAndInterrupts(InProcess):
    def test_the_lock_is_released_when_the_command_fails(self):
        lock = mock.MagicMock()
        with mock.patch("lib.writer_lock.acquire", return_value=lock), \
                mock.patch.object(self.m, "cmd_preflight", side_effect=ValueError("boom")):
            code, out, err = self.main("--video-id", "CLIP1", "preflight")
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["ok"])
        lock.release.assert_called_once()

    def test_keyboard_interrupt_propagates_and_releases(self):
        lock = mock.MagicMock()
        with mock.patch("lib.writer_lock.acquire", return_value=lock), \
                mock.patch.object(self.m, "cmd_preflight", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.m.main(["--root", str(self.root), "--video-id", "CLIP1", "preflight"])
        lock.release.assert_called_once()


# --------------------------------------------------------------------------- errors.py / settings.py minors
class TestErrorLog(Base):
    def test_an_unwritable_log_falls_back_to_the_engine_home(self):
        from lib import errors
        blocker = self.tmp / "afile"
        blocker.write_text("x", encoding="utf-8")
        try:
            raise ValueError("boom")
        except ValueError as e:
            doc = errors.report(e, blocker / "logs" / "pipeline.log", "reel test")
        want = common.engine_home() / "logs" / "pipeline.log"
        self.assertEqual(Path(doc["log"]), want)
        self.assertIn("ValueError: boom", want.read_text(encoding="utf-8"))

    def test_whynot_debug_prints_the_traceback(self):
        from lib import errors
        se = io.StringIO()
        with mock.patch.dict(os.environ, {"WHYNOT_DEBUG": "1"}), contextlib.redirect_stderr(se):
            try:
                raise KeyError("start")
            except KeyError as e:
                errors.report(e, self.tmp / "pipeline.log", "reel test")
        self.assertIn("Traceback", se.getvalue())
        se = io.StringIO()
        with mock.patch.dict(os.environ, {"WHYNOT_DEBUG": ""}), contextlib.redirect_stderr(se):
            try:
                raise KeyError("start")
            except KeyError as e:
                errors.report(e, self.tmp / "pipeline.log", "reel test")
        self.assertEqual(se.getvalue(), "")

    def test_settings_source_has_no_literal_bom(self):
        self.assertNotIn(b"\xef\xbb\xbf", (SK / "engine/reel/lib/settings.py").read_bytes())
        from lib import settings as S
        self.assertEqual(S.parse("﻿---\nlanguage: ar\n---\n")[0], {"language": "ar"})


class TestNoFootageGuidance(Base):
    """A spec without main_footage: preview-video, verify and premiere give guidance (exit 1), not a traceback."""

    def test_cli_no_footage(self):
        p = Paths(self.root, "CLIP1")
        p.ensure_project()
        write_json(p.p("01_analysis/timeline-spec.json"),
                   {"video_id": "CLIP1", "fps": 24, "main_footage": None, "events": [], "main_segments": [],
                    "duration_ms": 1000, "duration_frames": 24})
        write_json(p.p("00_inputs/preflight.json"), {"files": []})
        for cmd in ("preview-video", "verify", "premiere"):
            with self.subTest(cmd=cmd):
                code, doc, err = reel(self.root, cmd, video_id="CLIP1")
                self.assertEqual(code, 1, (cmd, doc, err))
                self.assertIn("main_footage", json.dumps(doc))
                self.assertNotIn("Traceback", err)


# --------------------------------------------------------------------------- status / next
class TestStatusAndNext(Base):
    def setUp(self):
        super().setUp()
        common.set_context(self.root)
        self.p = Paths(self.root, "CLIP1")
        self.p.ensure_project()

    def park(self):
        f = self.p.p(f"07_premiere/project/CLIP1_{common.project_prefix()}_EDIT_prev_20261012-101010.prproj")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
        return f

    def test_status_and_next_report_a_lone_parked_project(self):
        f = self.park()
        code, doc, err = reel(self.root, "status", video_id="CLIP1")
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual(Path(doc["parked_previous"]["file"]), f)
        self.assertIn("rename", doc["parked_previous"]["how"])
        code, doc, err = reel(self.root, "next", video_id="CLIP1")
        self.assertEqual(code, 0, (doc, err))
        self.assertIn(f.name, doc["parked_previous"]["file"])
        self.assertTrue(any(f.name in n for n in doc["notices"]), doc["notices"])

    def test_status_and_next_surface_version_warnings(self):
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"engine_version": "1.0.0", "events": []})
        for cmd in ("status", "next"):
            with self.subTest(cmd=cmd):
                code, doc, err = reel(self.root, cmd, video_id="CLIP1")
                self.assertEqual(code, 0, (doc, err))
                self.assertTrue(any("timeline-spec.json" in w and "reel plan" in w for w in doc["version_warnings"]),
                                doc.get("version_warnings"))

    def test_nothing_to_report_adds_nothing(self):
        code, doc, err = reel(self.root, "status", video_id="CLIP1")
        self.assertEqual(code, 0, (doc, err))
        self.assertNotIn("parked_previous", doc)
        self.assertNotIn("version_warnings", doc)


# --------------------------------------------------------------------------- handoff --delivered, partial render
class TestDelivered(Base):
    def setUp(self):
        super().setUp()
        common.set_context(self.root)
        self.p = Paths(self.root, "CLIP1")
        self.p.ensure_project()

    def test_delivered_after_qc_and_handoff(self):
        common.set_status(self.p, "READY_FOR_HUMAN_EDITOR", "handoff written")
        self.p.p("09_handoff/README.md").write_text("# handoff", encoding="utf-8")
        code, doc, err = reel(self.root, "handoff", "--delivered", "--note", "sent by email", video_id="CLIP1")
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual(doc["status"], "DELIVERED")
        st = common.load_status(self.p)
        self.assertEqual(st["status"], "DELIVERED")
        self.assertIn("sent by email", st["history"][-1]["note"])
        code, doc, _ = reel(self.root, "handoff", "--delivered", video_id="CLIP1")
        self.assertEqual((code, doc.get("unchanged")), (0, True))

    def test_delivered_before_qc_is_refused(self):
        common.set_status(self.p, "TRANSCRIBED", "x")
        code, doc, err = reel(self.root, "handoff", "--delivered", video_id="CLIP1")
        self.assertEqual(code, 2, (doc, err))
        self.assertIn("not ready", doc["refused"])
        self.assertEqual(common.load_status(self.p)["status"], "TRANSCRIBED")

    def test_delivered_after_a_stale_qc_is_refused(self):
        """T2.16 review (Minor 2): QC passed, then the frames were verified again: `reel next` says STALE (qc and the
        handoff are older than what they checked), so the delivery is refused (exit 2) and the status stays."""
        common.set_status(self.p, "READY_FOR_HUMAN_EDITOR", "handoff written")
        old = 1_700_000_000
        for rel in ("08_quality_control/qc-results.json", "09_handoff/README.md",
                    "08_quality_control/visual-verification.json"):
            f = self.p.p(rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}", encoding="utf-8")
            if "verification" not in rel:                 # visual-verification.json was written after QC
                os.utime(f, (old, old))
        stale = cli_module().stale_steps(self.p)
        self.assertTrue(any(s.startswith("qc (") for s in stale), stale)
        code, doc, err = reel(self.root, "handoff", "--delivered", video_id="CLIP1")
        self.assertEqual(code, 2, (doc, err))
        self.assertIn("STALE", doc["refused"])
        self.assertTrue(doc["stale"])
        self.assertIn("reel next", doc["how"])
        self.assertEqual(common.load_status(self.p)["status"], "READY_FOR_HUMAN_EDITOR")

    def test_abbreviated_flags_are_usage_errors(self):
        """T2.16 review (Minor 1): allow_abbrev=False — `--deliv` is not `--delivered`, on any parser."""
        common.set_status(self.p, "READY_FOR_HUMAN_EDITOR", "handoff written")
        self.p.p("09_handoff/README.md").write_text("# handoff", encoding="utf-8")
        for argv in (["handoff", "--deliv"], ["verify", "--rec", "--verdict", "pass"]):
            with self.subTest(argv=argv):
                code, out, err = reel(self.root, *argv, video_id="CLIP1")
                self.assertEqual(code, 2, (out, err))
                self.assertIn("unrecognized arguments", err)
        code, out, err = reel(None, "--ro", str(self.root), "status")
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(common.load_status(self.p)["status"], "READY_FOR_HUMAN_EDITOR")

    def test_only_the_lead_records_a_delivery(self):
        def guard(agent):
            payload = {"tool_name": "Bash", "tool_input": {"command": "reel handoff --delivered --video-id C1"},
                       "cwd": "."}
            if agent:
                payload["agent_type"] = agent
            return subprocess.run([sys.executable, "-B", str(GUARD)], input=json.dumps(payload), capture_output=True,
                                  text=True, encoding="utf-8", env=env()).returncode
        self.assertEqual(guard("whynot-cut:qc-reviewer"), 2)
        self.assertEqual(guard(None), 0)


try:
    from test_handoff_native import HandoffFixture
except ImportError:                       # pragma: no cover — the fixture module is part of the suite
    HandoffFixture = Base


class TestHandoffPartialRender(HandoffFixture):
    def test_a_partial_ae_render_reads_partial(self):
        self.native_build()
        write_json(self.p.p("04_after_effects/ae-build-result.json"), {"status": "AEP_CREATED"})
        write_json(self.p.p("04_after_effects/ae-render-result.json"), {"status": "RENDERED", "partial": True})
        self.assertIn("| RENDERED (partial) |", self.readme())
        write_json(self.p.p("04_after_effects/ae-render-result.json"), {"status": "RENDERED"})
        self.assertNotIn("(partial)", self.readme())


# --------------------------------------------------------------------------- half-made reel folders
class TestUnfinishedReel(Base):
    def setUp(self):
        super().setUp()
        (self.root / "output/episodes/EP1").mkdir(parents=True)
        (self.root / "output/projects/EP1_R01").mkdir(parents=True)
        (self.root / "output/projects/EP1_T02_MO").mkdir(parents=True)
        (self.root / "output/projects/OLDVIDEO").mkdir(parents=True)

    def test_inbox_lists_them_apart_from_orphans(self):
        from lib.onboard import orphan_projects
        r = orphan_projects(Paths(self.root), {})
        self.assertEqual(r["orphan_projects"], ["OLDVIDEO"])
        got = {u["video_id"]: u for u in r["unfinished_reels"]}
        self.assertEqual(set(got), {"EP1_R01", "EP1_T02_MO"})
        self.assertIn("reels-select --episode EP1 --pick R01 --by editor", got["EP1_R01"]["how"])
        self.assertIn("--as motion", got["EP1_T02_MO"]["how"])

    def test_a_reel_folder_of_no_episode_or_with_source_is_not_unfinished(self):
        from lib.reels import unfinished_reel
        self.assertIsNone(unfinished_reel(self.root, "EP9_R01"))
        write_json(self.root / "output/projects/EP1_R01/00_inputs/source.json", {"footage": "x"})
        self.assertIsNone(unfinished_reel(self.root, "EP1_R01"))
        self.assertIsNone(unfinished_reel(self.root, "CLIP1"))

    def test_plan_refuses_it(self):
        code, doc, err = reel(self.root, "plan", video_id="EP1_R01")
        self.assertEqual(code, 2, (doc, err))
        self.assertIn("unfinished reel", doc["refused"])
        self.assertIn("reels-select", doc["how"])


# --------------------------------------------------------------------------- plan footage hint, frame size, framing
class TestPlanFootageHint(Base):
    def test_a_moved_clip_names_the_path_the_clip_id_map_resolves(self):
        from test_pipeline import make_project
        from lib.plan import compile_plan
        root, p, _ = make_project(self.tmp)
        common.set_context(root)
        clip = root / "data/Raw/CLIP1.mov"
        write_json(root / "output/discovery/input-inventory.json",
                   {"files": [{"path": str(clip), "rel": "data/Raw/CLIP1.mov", "role": "source_footage"}]})
        write_json(p.p("01_analysis/edit-decisions.json"), {
            "video_id": "CLIP1", "global": {"main_footage": "data/Raw/OLD.mov"},
            "decisions": [{"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
                           "start": "00:00:00.200", "end": "00:00:04.000", "semantic_intent": "hook",
                           "visual_treatment": "hook", "confidence": "high"}]})
        r = compile_plan(p)
        self.assertFalse(r["ok"])
        err = next(e for e in r["errors"] if "data/Raw/OLD.mov" in e)
        self.assertIn('"main_footage": "data/Raw/CLIP1.mov"', err)


class TestFrameSizeThroughCommon(unittest.TestCase):
    def test_no_module_reads_the_frame_size_raw(self):
        bad = []
        for f in sorted((SK / "engine/reel/lib").glob("*.py")):
            if f.name == "common.py":
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"""\[["']frame_(width|height)["']\]""", line):
                    bad.append(f"{f.name}:{n}")
        self.assertEqual(bad, [])

    def test_the_plan_refuses_a_bad_size_like_everywhere_else(self):
        from lib.common import Context
        from lib.errors import Guidance
        from lib.plan import apply_framing
        inp = SimpleNamespace(ctx=Context(Path(tempfile.gettempdir())), base={"framing": "4:5"}, style={}, pre_all={},
                              main_file=None, main_v={"display_width": 1080, "display_height": 1920}, dur_ms=2000,
                              fps=25.0, seq_cfg={"general": {"frame_width": "wide", "frame_height": 1920}})
        cam = {"camera": [], "main_v": inp.main_v, "bsp": 100.0, "box": 0.0, "framing": ""}
        with self.assertRaises(Guidance) as cm:
            apply_framing(inp, cam)
        self.assertIn("general.frame_width", cm.exception.error)


class TestFramingCase(unittest.TestCase):
    def test_upper_case_x_is_the_same_framing(self):
        from lib.plan import window_rect
        self.assertEqual(window_rect("4X5"), window_rect("4:5"))
        self.assertEqual(window_rect(" 4 x 5 ")["mode"], "4:5")
        self.assertIsNone(window_rect("FULL"))

    def test_the_schema_accepts_it(self):
        from lib.schemas import validate_file
        doc = json.loads((SK / "tests/fixtures/schemas/edit-decisions.json").read_text(encoding="utf-8"))["valid"][0]
        with tempfile.TemporaryDirectory() as d:
            for framing, ok in (("4X5", True), ("4x5", True), ("4Y5", False)):
                f = Path(d) / "edit-decisions.json"
                write_json(f, dict(doc, **{"global": dict(doc.get("global") or {}, framing=framing)}))
                with self.subTest(framing=framing):
                    self.assertEqual(validate_file(f, None)["ok"], ok)


# --------------------------------------------------------------------------- compiled reads, ffmpeg timeout cap
class TestCompiledReads(unittest.TestCase):
    def test_consumers_read_compiled_artefacts_through_the_version_check(self):
        bad = []
        pat = re.compile(r"read_json\([^)]*(timeline-spec|motion-plan)\.json")
        for f in sorted((SK / "engine/reel/lib").glob("*.py")):
            if f.name == "plan.py":                   # the compiler reads back what it just wrote
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if pat.search(line):
                    bad.append(f"{f.name}:{n}")
        self.assertEqual(bad, [])


class TestFfmpegTimeoutCap(unittest.TestCase):
    def test_the_scale_is_capped_at_100(self):
        from lib import media_util
        for v, want in (("5000", 100.0), ("1e12", 100.0), ("100", 100.0), ("3", 3.0)):
            with self.subTest(scale=v), mock.patch.dict(os.environ, {media_util.FF_TIMEOUT_SCALE_ENV: v}):
                self.assertEqual(media_util.ff_timeout_scale(), want)

    def test_every_timeout_stays_below_timeout_max(self):
        from lib import media_util
        with mock.patch.dict(os.environ, {media_util.FF_TIMEOUT_SCALE_ENV: "5000"}):
            t = media_util.ff_timeout(["ffmpeg", "-t", "99999999999", "-i", "x.wav", "-f", "null", "-"])
            u = media_util.ff_timeout(["ffmpeg", "-f", "lavfi", "-i", "sine"])
        self.assertLess(t, threading.TIMEOUT_MAX)
        self.assertEqual(u, 100 * media_util.FF_TIMEOUT_UNKNOWN_S)
        subprocess.run([sys.executable, "-c", "pass"], timeout=t, check=True)          # no OverflowError
        timer = threading.Timer(t, lambda: None)
        timer.start()
        timer.cancel()
        timer.join()


if __name__ == "__main__":
    unittest.main()
