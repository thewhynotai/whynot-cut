# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 15 (T4.15) hook tests: the `reel clean` verb (cli.py), the doctor's disk line (onboard.py), the cache
cap after a handoff (handoff.py), the link-safe runtime.prune (runtime.py), the Whisper last-used stamp
(whisper_backends.py), the guard's lead-only `reel clean --apply` (guard.py, r3: review 41bc006 P2-1), plus the setup
skill's "Free up space" step and trigger. They go with hooks/T4.15/patch.diff: red on a tree without the patch, green
with it. Links are made in the test's own temp folder. Run:
    bash tools/test.sh -p test_t415_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from lib import housekeeping as HK  # noqa: E402
from lib import lead_steps, linksafe, plat, runtime  # noqa: E402
from test_handoff_native import HandoffFixture  # noqa: E402
from test_housekeeping import OLD, Home, dir_link, rm_links, tree_digest, write  # noqa: E402
from test_plugin import GUARD, find_bash, hook, isolated_env  # noqa: E402

SK = Path(__file__).resolve().parents[1]
CLI = SK / "engine" / "reel" / "cli.py"


def cli_env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in plat.HOME_ENV}
    env["WHYNOT_HOME"] = str(home)
    return env


def run_cli(env: dict, argv) -> subprocess.CompletedProcess:
    """cli.py with `argv`, as the lead runs it. Once `clean --apply` is a BL-15 LEAD_STEPS row, the engine wants the
    approval token the guard issues for the lead's plain call: issue_for writes it (it does nothing for a step that
    is not in the table)."""
    lead_steps.issue_for(list(argv), env)
    return subprocess.run([sys.executable, "-B", str(CLI), *argv], capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=300)


def reel(home: Path, *argv) -> dict:
    r = run_cli(cli_env(home), argv)
    if r.returncode != 0:
        raise AssertionError(f"reel {' '.join(argv)} exit {r.returncode}: {r.stderr[-2000:]}")
    return json.loads(r.stdout)


class TestCleanVerb(Home):
    def test_dry_run_default_then_apply_then_models(self):
        (self.home / "bin" / ("uv.exe" if os.name == "nt" else "uv")).unlink()   # the fixture's uv is a fake
        before = tree_digest(self.home)
        rep = reel(self.home, "clean")
        self.assertFalse(rep["apply"])
        self.assertEqual(tree_digest(self.home), before)
        self.assertEqual([i["key"] for i in rep["items"]], list(HK.KEYS))
        rep = reel(self.home, "clean", "--apply")
        self.assertTrue(rep["apply"])
        self.assertFalse((self.home / "cache" / "font-index.json").exists())
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-small").exists())
        reel(self.home, "clean", "--apply", "--models")
        self.assertFalse((self.home / "models" / "models--Systran--faster-whisper-small").exists())
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-medium").exists())   # a fallback
        self.assertTrue((self.home / "models" / "models--Systran--faster-whisper-large-v3" / "blobs" / "b1").exists())

    def test_uv_cache_only_with_its_own_flag(self):
        rep = reel(self.home, "clean", "--apply", "--models")   # the fixture's fake uv would fail if it ran
        self.assertTrue(rep["ok"], rep)
        self.assertFalse(rep["uv_cache"])
        self.assertTrue((self.home / "cache" / "uv" / "wheels" / "a.whl").exists())
        it = next(i for i in rep["items"] if i["key"] == "uv_cache")
        self.assertIn("--uv-cache", it["why"])
        self.assertIn("التثبيت الجاي هيحمّل تاني", it["why"])

    def test_an_item_error_exits_1_with_the_report(self):
        r = run_cli(cli_env(self.home), ["clean", "--apply", "--uv-cache"])   # the fixture's fake uv fails
        self.assertEqual(r.returncode, 1, r.stderr)
        rep = json.loads(r.stdout)
        self.assertFalse(rep["ok"])
        self.assertTrue(rep["uv_cache"])
        self.assertTrue(next(i for i in rep["items"] if i["key"] == "uv_cache")["error"])
        self.assertFalse((self.home / "cache" / "font-index.json").exists())    # the other items still ran

    def test_clean_is_machine_level_and_never_writes_the_client(self):
        sys.path.insert(0, str(CLI.parent))
        self.addCleanup(sys.path.remove, str(CLI.parent))
        import cli
        self.assertIn("clean", cli.NO_ROOT)
        self.assertIn("clean", cli.CORE_READS)
        self.assertNotIn("clean", cli.CORE_WRITES)
        self.assertIn("clean", cli.command_table())


class TestDoctorDisk(Home):
    def test_disk_summary_is_read_only_and_never_fails(self):
        from lib import onboard
        before = tree_digest(self.home)
        with self.status():
            d = onboard.disk_summary(self.home)
        self.assertEqual(tree_digest(self.home), before)
        self.assertEqual(set(d["items"]), set(HK.KEYS))
        self.assertGreater(d["removable_bytes"], 0)
        with self.status():
            rep = HK.scan(self.home)
        self.assertEqual(d["removable_bytes"], rep["removable_bytes"])     # review 41bc006 P3-2: what a yes frees
        self.assertLess(d["removable_bytes"], sum(d["items"].values()))     # kept items are not added in
        self.assertNotIn("total_bytes", d)
        self.assertIn("reel clean", d["how"])
        with mock.patch.object(HK, "scan", side_effect=OSError("disk gone")):
            self.assertIn("disk gone", onboard.disk_summary(self.home)["error"])

    def test_doctor_reports_disk(self):
        from lib import onboard, portability
        with mock.patch.object(onboard, "disk_summary", return_value={"marker": 1}) as ds, \
                mock.patch.object(portability, "doctor_checks", side_effect=RuntimeError("stop here")):
            with self.assertRaises(RuntimeError):
                onboard.doctor()
        ds.assert_called_once_with()


class TestHandoffAutoPrune(HandoffFixture):
    def test_handoff_survives_auto_prune_failure(self):
        self.approve()
        with mock.patch.object(HK, "auto_prune", side_effect=RuntimeError("cache exploded")) as ap:
            rep = __import__("lib.handoff", fromlist=["build"]).build(self.p)
        ap.assert_called_once()
        self.assertTrue(self.p.p("09_handoff/README.md").exists())
        self.assertTrue(Path(rep["checklist"]).exists())

    def test_handoff_calls_auto_prune_once(self):
        self.approve()
        with mock.patch.object(HK, "auto_prune", return_value={"errors": []}) as ap:
            __import__("lib.handoff", fromlist=["build"]).build(self.p)
        ap.assert_called_once_with()


class TestRuntimePrune(Home):
    def setUp(self):
        super().setUp()
        self.rt = self.home / "runtimes"
        self.ext = self.outside / "r-ext"
        write(self.ext / "pyvenv.cfg", b"home = x\n")
        write(self.ext / "Lib" / "keep.bin", b"k" * 100)
        dir_link(self.rt / "r-linked", self.ext)

    def test_link_safe_flag_and_dry_run(self):
        self.assertTrue(runtime.PRUNE_LINK_SAFE)
        before = tree_digest(self.home)
        res = runtime.prune(self.home, {"r-cur", "r-prev"}, dry_run=True)
        self.assertEqual(sorted(res["removed"]), ["r-linked", "r-old"])
        self.assertEqual(tree_digest(self.home), before)

    def test_removes_through_linksafe_never_enters_a_link(self):
        before = tree_digest(self.outside)
        res = runtime.prune(self.home, {"r-cur", "r-prev"})
        self.assertEqual(sorted(res["removed"]), ["r-linked", "r-old"])
        self.assertFalse(os.path.lexists(self.rt / "r-linked"))
        self.assertFalse(os.path.lexists(self.rt / "r-old"))
        self.assertTrue((self.rt / "r-cur" / "pyvenv.cfg").exists())
        self.assertEqual(tree_digest(self.outside), before)

    def test_home_through_a_junction_and_a_locked_runtime(self):
        via = self.tmp / "home-link"
        dir_link(via, self.home)
        with mock.patch.object(linksafe, "remove", side_effect=linksafe.RemoveIncomplete(0, [("x", "in use")])):
            res = runtime.prune(via, {"r-cur", "r-prev"})
        self.assertEqual(res["removed"], [])
        self.assertIn("r-old", res["failed"])
        res = runtime.prune(via, {"r-cur", "r-prev"})
        self.assertIn("r-old", res["removed"])
        self.assertTrue(self.ext.joinpath("Lib", "keep.bin").exists())

    def test_runtimes_folder_a_link_is_refused(self):
        rm_links(self.rt)
        other = self.home / "runtimes-real"
        os.replace(self.rt, other)
        dir_link(self.rt, other)
        res = runtime.prune(self.home, {"r-cur"})
        self.assertEqual(res["removed"], [])
        self.assertIn("runtimes", res["failed"])
        self.assertTrue((other / "r-old" / "pyvenv.cfg").exists())

    def test_current_runtime_always_kept(self):
        res = runtime.prune(self.home, {"r-prev"})                    # a stale keep set without the current one
        self.assertIn("r-cur", res["kept"])
        self.assertNotIn("r-cur", res["removed"])
        self.assertTrue((self.rt / "r-cur" / "pyvenv.cfg").exists())

    def test_setup_env_plain_module_import(self):
        lib = SK / "engine" / "reel" / "lib"
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import runtime as R; import json; "
                "print(json.dumps(R.prune(__import__('pathlib').Path(sys.argv[2]), {'r-cur', 'r-prev'})))")
        r = subprocess.run([sys.executable, "-B", "-c", code, str(lib), str(self.home)], capture_output=True,
                           text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(json.loads(r.stdout)["removed"]), ["r-linked", "r-old"])
        self.assertTrue(self.ext.joinpath("Lib", "keep.bin").exists())

    def test_clean_removes_old_runtimes_with_the_patch(self):
        rm_links(self.rt)
        with self.status():
            dry = HK.scan(self.home)
            rep = HK.clean(self.home, apply=True)
        it = next(i for i in rep["items"] if i["key"] == "runtimes_old")
        self.assertTrue(next(i for i in dry["items"] if i["key"] == "runtimes_old")["removable"])
        self.assertFalse((self.rt / "r-old").exists())
        self.assertTrue((self.rt / "r-prev").exists())
        self.assertEqual(it["removed"], next(i for i in dry["items"] if i["key"] == "runtimes_old")["bytes"])
        self.assertIsNone(it["error"])


class TestWhisperStamp(Home):
    def test_loader_stamps_the_model_it_loads(self):
        from lib import whisper_backends as WB
        repo = self.home / "models" / "models--Systran--faster-whisper-medium"
        fake = types.ModuleType("faster_whisper")
        fake.WhisperModel = lambda *a, **kw: object()
        with mock.patch.dict(sys.modules, {"faster_whisper": fake}), \
                mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home), "HF_HUB_OFFLINE": ""}):
            WB.load_ct2("medium", device="cpu")
        st = repo / HK.STAMP
        self.assertTrue(st.is_file())
        self.assertLess(time.time() - st.stat().st_mtime, 60)

    def test_a_failed_load_writes_no_stamp(self):
        from lib import whisper_backends as WB
        repo = self.home / "models" / "models--Systran--faster-whisper-medium"
        fake = types.ModuleType("faster_whisper")

        def boom(*a, **kw):
            raise RuntimeError("no")
        fake.WhisperModel = boom
        with mock.patch.dict(sys.modules, {"faster_whisper": fake}), \
                mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home), "HF_HUB_OFFLINE": ""}):
            with self.assertRaises(RuntimeError):
                WB.load_ct2("medium", device="cpu")
        self.assertFalse((repo / HK.STAMP).exists())


    def test_a_stamp_failure_never_fails_the_load(self):
        from lib import whisper_backends as WB
        fake = types.ModuleType("faster_whisper")
        fake.WhisperModel = lambda *a, **kw: "model"
        with mock.patch.dict(sys.modules, {"faster_whisper": fake}), \
                mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home), "HF_HUB_OFFLINE": ""}), \
                mock.patch.object(HK, "mark_model_used", side_effect=RuntimeError("stamp broke")):
            m, dev, ct = WB.load_ct2("medium", device="cpu")
        self.assertEqual((m, dev), ("model", "cpu"))


class TestSkillText(unittest.TestCase):
    def test_setup_skill_free_up_space(self):
        s = " ".join((SK / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8").split())
        for need in ("reel clean", "reel clean --apply", "reel clean --apply --models", "فضّي مساحة", "says yes",
                     "reel clean --apply --uv-cache", "التثبيت الجاي هيحمّل تاني", "removable_bytes",
                     "a subagent may not"):
            self.assertIn(need, s, need)

    def test_setup_skill_description_routes_free_up_space(self):    # review 41bc006 P3-3
        from test_plugin import _frontmatter
        d = _frontmatter(SK / "skills" / "setup" / "SKILL.md")["description"]
        for need in ("free up space", "فضّي مساحة", "reel: command not found", "Premiere bridge not responding"):
            self.assertIn(need, d, need)


def load_guard(name: str):
    spec = importlib.util.spec_from_file_location(name, GUARD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


DOCTOR, QC, STORY, OTHER = ("whynot-cut:setup-doctor", "whynot-cut:qc-reviewer", "whynot-cut:story-editor",
                            "other-plugin:helper")
SUBAGENTS = (DOCTOR, QC, STORY, OTHER)


class TestCleanApplyIsLeadOnly(unittest.TestCase):
    """Review 41bc006 P2-1: `reel clean --apply` (with any opt-in) deletes from the engine home, so only the lead runs
    it, after the editor's yes; a subagent (the read-only setup-doctor included) may run the dry run `reel clean`,
    with or without --models / --uv-cache, and report what it lists. Every form the guard reads: `reel`, the
    launcher by path (bin/reel, bin\\reel.cmd), cli.py, `bash hooks/run_python.sh cli.py`, and the hook itself run the
    way hooks.json runs it (bash hooks/run_python.sh hooks/guard.py)."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)
        self.cwd = self.tmp / "work"
        self.cwd.mkdir()
        self.bin = (SK / "bin" / "reel").as_posix()
        self.cli = CLI.as_posix()
        self.runner = (SK / "hooks" / "run_python.sh").as_posix()

    def payload(self, cmd: str, agent=None, tool="Bash") -> dict:
        p = {"session_id": "t415", "hook_event_name": "PreToolUse", "tool_name": tool,
             "tool_input": {"command": cmd}, "cwd": str(self.cwd)}
        if agent:
            p["agent_type"] = agent
        return p

    def guard(self, cmd: str, agent=None, tool="Bash"):
        rc, _, err = hook(GUARD, self.payload(cmd, agent, tool))
        return rc, err

    def forms(self, args: str):
        """(tool, command) for every way a caller can start the engine with `args`."""
        return (("Bash", f"reel {args}"), ("PowerShell", f"reel {args}"),
                ("Bash", f'"{self.bin}" {args}'), ("PowerShell", f"& '{(SK / 'bin' / 'reel.cmd')}' {args}"),
                ("Bash", f'python "{self.cli}" {args}'),
                ("Bash", f'bash "{self.runner}" "{self.cli}" {args}'))

    def test_a_subagent_s_clean_apply_is_refused_in_every_form(self):
        for args in ("clean --apply --models --uv-cache", "clean --apply", "clean --models --apply",
                     "clean --uv-cache --apply", "clean --apply=1", "clean --app", "clean --a --models"):
            for tool, cmd in self.forms(args):
                for agent in SUBAGENTS:
                    with self.subTest(cmd=cmd, tool=tool, agent=agent):
                        rc, err = self.guard(cmd, agent, tool)
                        self.assertEqual(rc, 2, err)
                        self.assertIn("clean --apply", err)

    def test_the_dry_run_stays_open_to_every_subagent(self):
        for args in ("clean", "clean --models", "clean --uv-cache", "clean --models --uv-cache", "clean --help"):
            for tool, cmd in self.forms(args):
                for agent in SUBAGENTS:
                    with self.subTest(cmd=cmd, tool=tool, agent=agent):
                        rc, err = self.guard(cmd, agent, tool)
                        self.assertEqual(rc, 0, err)
        for cmd in ('rg -n "clean --apply" docs', "reel audio-clean --root . --video-id C0001",
                    "reel ref-style --apply --video-id C0001"):        # a search, other steps: not the row
            with self.subTest(cmd=cmd):
                self.assertEqual(self.guard(cmd, STORY)[0], 0)

    def test_the_lead_runs_clean_apply(self):
        for args in ("clean --apply --models --uv-cache", "clean --apply", "clean"):
            for tool, cmd in self.forms(args):
                with self.subTest(cmd=cmd, tool=tool):
                    self.assertEqual(self.guard(cmd, None, tool)[0], 0)

    def test_through_run_python_sh_as_hooks_json_runs_the_guard(self):
        bash = find_bash()
        if not bash:
            self.skipTest("no bash")
        data = self.tmp / "plugin-data"
        data.mkdir()
        (data / "python").write_text(sys.executable + "\n", encoding="utf-8")   # the interpreter run_python.sh caches
        env = isolated_env({"WHYNOT_HOME": str(self.tmp / "no-engine"), "CLAUDE_PLUGIN_DATA": str(data),
                            "CLAUDE_PLUGIN_ROOT": str(SK)})

        def run(cmd, agent):
            r = subprocess.run([bash, self.runner, GUARD.as_posix()], input=json.dumps(self.payload(cmd, agent)),
                               capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
            return r.returncode, r.stderr
        for agent, cmd, want in ((DOCTOR, "reel clean --apply --models --uv-cache", 2),
                                 (DOCTOR, f'"{self.bin}" clean --apply', 2),
                                 (DOCTOR, "reel clean", 0), (DOCTOR, "reel clean --models --uv-cache", 0),
                                 (None, "reel clean --apply --models --uv-cache", 0)):
            with self.subTest(agent=agent, cmd=cmd):
                rc, err = run(cmd, agent)
                self.assertEqual(rc, want, err)
                if want:
                    self.assertIn("clean --apply", err)
        self.assertTrue((data / "hooks-ok").exists())        # Python really ran the guard (not the no-Python exit 0)

    def test_each_wall_refuses_on_its_own(self):
        """The text backstop row, the parsed check_reel rule and setup-doctor's own pair each refuse by themselves
        (so dropping one of them is seen)."""
        g = load_guard("guard_t415")
        self.assertIn(("clean", ("--apply",), None), g.BACKSTOP_STEPS)
        self.assertIn(("clean", "--apply"), g.SETUP_DOCTOR_FORBIDDEN)
        for agent in SUBAGENTS:
            with self.subTest(wall="backstop", agent=agent), mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit) as cm:
                    g.backstop("echo y | reel 'clean' --apply", agent)
                self.assertEqual(cm.exception.code, 2)
            with self.subTest(wall="check_reel", agent=agent), mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit) as cm:
                    g.check_reel("reel", ["reel", "clean", "--models", "--apply"], agent, self.cwd)
                self.assertEqual(cm.exception.code, 2)
            g.backstop("reel clean --models --uv-cache", agent)            # the dry run: no refusal
            g.check_reel("reel", ["reel", "clean", "--models", "--uv-cache"], agent, self.cwd)
        g.check_reel("reel", ["reel", "clean", "--apply", "--models", "--uv-cache"], None, self.cwd)   # the lead
        msgs = []

        def block(m):
            msgs.append(m)
            raise SystemExit(2)
        with mock.patch.object(g, "block", side_effect=block):
            for agent in (DOCTOR, QC):
                with self.assertRaises(SystemExit):
                    g.check_reel("reel", ["reel", "clean", "--apply"], agent, self.cwd)
        self.assertIn("setup-doctor diagnoses without changing anything", msgs[0])     # its own pair, first
        self.assertIn("reel clean --apply", msgs[0])
        self.assertIn("only the lead editor runs `reel clean --apply`", msgs[1])
        for name in ("setup", "model-download", "gpu-enable", "ppro-install"):    # the plain names still work
            with self.subTest(step=name), mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit):
                    g.check_reel("reel", ["reel", name], DOCTOR, self.cwd)


if __name__ == "__main__":
    unittest.main()
