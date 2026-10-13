"""3.0 G79: unit tests never reach the real engine home or a running Adobe app.

Found 2026-10-12: two `build_project` jobs from a unit test sat in the real ~/.whynot-cut/ppro-queue and a running
Premiere executed them. Two layers now:
  * tests/_isolation.py, imported first by every test module (enforced here), points WHYNOT_HOME, HOME/USERPROFILE,
    APPDATA (the CEP folder) and CLAUDE_CONFIG_DIR at a per-run temp sandbox and sets WHYNOT_TEST_SANDBOX;
  * under that flag the engine itself (plat.sandbox_refusal) refuses to queue a job in, sync scripts into or install the
    bridge into the REAL engine home / CEP folder, and refuses to launch After Effects, Photoshop or aerender, unless a
    deliberate live run sets WHYNOT_TEST_ALLOW_LIVE_BRIDGE=1.
Nothing here can reach a real queue: every submit below is also mocked one level down.
Run:  tools/test.sh -p test_isolation.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import plat  # noqa: E402

TESTS = Path(__file__).resolve().parent


def _under(p, root) -> bool:
    p, root = os.path.normcase(os.path.abspath(str(p))), os.path.normcase(os.path.abspath(str(root)))
    return p == root or p.startswith(root.rstrip("\\/") + os.sep)


class TestEveryModuleIsSandboxed(unittest.TestCase):
    def test_every_test_module_imports_isolation_first(self):
        """unittest has no conftest: the sandbox holds only because each module imports _isolation before it imports
        the engine or touches the environment (the bytecode prelude may come first). Every file unittest could
        discover counts (its pattern test*.py, subfolders included), not only test_*.py at the top."""
        bad = []
        files = sorted(f for f in TESTS.rglob("test*.py") if "__pycache__" not in f.parts)
        self.assertIn(TESTS / "test_isolation.py", files)
        for f in files:
            body = ast.parse(f.read_text(encoding="utf-8")).body
            for node in body:
                if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
                    continue                                                    # the docstring
                if isinstance(node, ast.Import) and [a.name for a in node.names] == ["sys"]:
                    continue                                                    # import sys as _sys
                if isinstance(node, ast.Assign) and ast.unparse(node).startswith("_sys.dont_write_bytecode"):
                    continue
                if not (isinstance(node, ast.Import) and [a.name for a in node.names] == ["_isolation"]):
                    bad.append(f"{f.relative_to(TESTS)}:{node.lineno}: {ast.unparse(node)[:60]}")
                break
            else:
                bad.append(f"{f.name}: no statements")
        self.assertEqual(bad, [], "every test module starts with `import _isolation` (after the bytecode prelude)")

    def test_the_process_runs_in_the_sandbox(self):
        box = os.environ.get(plat.SANDBOX_ENV)
        self.assertTrue(box and Path(box).is_dir(), box)
        for p in (plat.engine_home(), Path.home(), plat.cep_extensions_dir(), plat.options_file()):
            self.assertTrue(_under(p, box), f"{p} is outside the sandbox {box}")
        for root in plat.live_roots():
            self.assertFalse(_under(root, box), root)
            self.assertFalse(_under(plat.engine_home(), root), root)
        self.assertNotIn("CLAUDE_PLUGIN_DATA", os.environ)
        self.assertNotIn("CLAUDE_ENV_FILE", os.environ)
        self.assertTrue(_under(os.environ["CLAUDE_CONFIG_DIR"], box))

    def test_temp_folders_land_in_the_sandbox(self):
        box = os.environ[plat.SANDBOX_ENV]
        self.assertTrue(_under(tempfile.gettempdir(), box), tempfile.gettempdir())
        for k in ("TMP", "TEMP", "TMPDIR"):
            self.assertTrue(_under(os.environ[k], box), k)
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(_under(t, box), t)

    def test_temporary_directory_cleanup_survives_windows_refusals(self):
        """WinError 145 ("directory is not empty") under load and read-only files: cleanup retries, never raises."""
        import shutil
        real = shutil.rmtree
        calls = []

        def flaky(path, *a, **kw):
            calls.append(path)
            if len(calls) == 1:
                raise OSError(145, "The directory is not empty")
            return real(path, *a, **kw)
        t = tempfile.TemporaryDirectory()
        ro = Path(t.name) / "sub" / "ro.txt"
        ro.parent.mkdir()
        ro.write_text("x", encoding="utf-8")
        ro.chmod(0o444)
        with mock.patch.object(shutil, "rmtree", flaky):
            t.cleanup()
        self.assertFalse(Path(t.name).exists())
        self.assertGreaterEqual(len(calls), 2)

    def test_a_folder_that_will_not_go_stays_in_the_sandbox_without_an_error(self):
        import shutil
        t = tempfile.TemporaryDirectory()
        with mock.patch.object(shutil, "rmtree", side_effect=OSError(145, "busy")), \
                mock.patch.object(_isolation.time, "sleep", lambda s: None):
            t.cleanup()                                                  # no exception
        self.assertTrue(_under(t.name, os.environ[plat.SANDBOX_ENV]))
        self.assertTrue(_isolation.rmtree_retry(t.name))

    def test_stale_sandboxes_of_killed_runs_are_swept(self):
        """A killed run leaves its sandbox in the real temp folder: the next run removes those older than 24 h, and only
        folders with the exact prefix that hold the sandbox marker."""
        import time
        with tempfile.TemporaryDirectory() as t:
            t, old = Path(t), time.time() - 25 * 3600

            def box(name, marker=True, age=old):
                d = t / name
                (d / "user-home").mkdir(parents=True)
                if marker:
                    m = d / _isolation.MARKER
                    m.write_text("x", encoding="utf-8")
                    os.utime(m, (age, age))
                return d
            stale = box("whynot-test-sandbox-aaa")
            fresh = box("whynot-test-sandbox-bbb", age=time.time())
            unmarked = box("whynot-test-sandbox-ccc", marker=False)
            other = box("whynot-test-sandboxed-ddd")
            plain = t / "whynot-test-sandbox-file"
            plain.write_text("x", encoding="utf-8")
            self.assertEqual(_isolation.sweep_stale(t), [str(stale)])
            self.assertFalse(stale.exists())
            for keep in (fresh, unmarked, other, plain):
                self.assertTrue(keep.exists(), keep)

    def test_this_run_marks_its_sandbox(self):
        self.assertTrue((Path(os.environ[plat.SANDBOX_ENV]) / _isolation.MARKER).is_file())

    def test_the_real_engine_home_is_a_live_root(self):
        self.assertTrue(any(_under(_isolation.REAL_ENGINE_HOME, r) for r in plat.live_roots()))


class LiveRootCase(unittest.TestCase):
    """A temp folder plays the real machine: it is the only live root."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.real = self.t / "real-home" / ".whynot-cut"
        env = {plat.SANDBOX_ENV: os.environ.get(plat.SANDBOX_ENV) or str(self.t), plat.LIVE_ROOTS_ENV: str(self.real),
               "WHYNOT_HOME": str(self.real)}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop(plat.ALLOW_LIVE_ENV, None)

    def tearDown(self):
        self.tmp.cleanup()

    def assertUntouched(self):
        self.assertFalse(self.real.exists(), list(self.real.rglob("*")) if self.real.exists() else None)


class TestBridgeSubmitRefusesTheRealHome(LiveRootCase):
    def _submit(self, mod, **kw):
        from lib import cep_queue
        sent = []
        with mock.patch.object(mod, "status", return_value={"alive": True}), \
                mock.patch.object(mod, "sync_scripts", side_effect=AssertionError("synced into the real home")), \
                mock.patch.object(cep_queue, "submit", lambda *a, **k: sent.append(a) or {"ok": True}):
            r = mod.submit("ping", {"x": 1}, **kw)
        return r, sent

    def test_ppro_submit_refuses(self):
        from lib import ppro_bridge
        r, sent = self._submit(ppro_bridge)
        self.assertFalse(r["ok"])
        self.assertIn("test sandbox", r["error"])
        self.assertIn("WHYNOT_TEST_ALLOW_LIVE_BRIDGE", r["how"])
        self.assertEqual(sent, [])
        self.assertUntouched()

    def test_ae_submit_refuses(self):
        from lib import ae_bridge
        r, sent = self._submit(ae_bridge)
        self.assertFalse(r["ok"])
        self.assertIn("test sandbox", r["error"])
        self.assertEqual(sent, [])
        self.assertUntouched()

    def test_the_actual_real_default_home_is_refused(self):
        """The brief's proof: sandbox flag set, WHYNOT_HOME = the machine's real default engine home -> refused."""
        from lib import ppro_bridge
        os.environ[plat.LIVE_ROOTS_ENV] = _isolation.LIVE_ROOTS
        os.environ["WHYNOT_HOME"] = str(_isolation.REAL_ENGINE_HOME)
        r, sent = self._submit(ppro_bridge)
        self.assertFalse(r["ok"])
        self.assertIn("test sandbox", r["error"])
        self.assertEqual(sent, [])

    def test_a_temp_home_is_not_refused(self):
        from lib import cep_queue, ppro_bridge
        os.environ["WHYNOT_HOME"] = str(self.t / "elsewhere")
        sent = []
        with mock.patch.object(ppro_bridge, "status", return_value={"alive": True, "bridge_version": "3.1.1"}), \
                mock.patch.object(ppro_bridge, "sync_scripts", lambda: {}), \
                mock.patch.object(cep_queue, "submit", lambda *a, **k: sent.append(a) or {"ok": True}):
            self.assertEqual(ppro_bridge.submit("ping"), {"ok": True})
        self.assertEqual(sent[0][0], self.t / "elsewhere" / "ppro-queue")

    def test_explicit_opt_in_reaches_the_queue(self):
        from lib import cep_queue, ppro_bridge
        os.environ[plat.ALLOW_LIVE_ENV] = "1"
        sent = []
        with mock.patch.object(ppro_bridge, "status", return_value={"alive": True, "bridge_version": "3.1.1"}), \
                mock.patch.object(ppro_bridge, "sync_scripts", lambda: {}), \
                mock.patch.object(cep_queue, "submit", lambda *a, **k: sent.append(a) or {"ok": True}):
            self.assertEqual(ppro_bridge.submit("ping"), {"ok": True})
        self.assertEqual(sent[0][0], self.real / "ppro-queue")

    def test_cep_queue_submit_refuses_a_real_queue(self):
        from lib import cep_queue
        r = cep_queue.submit(self.real / "ppro-queue", self.real / "ppro-scripts" / "x.jsx", "ping",
                             st={"alive": True}, timeout=1)
        self.assertFalse(r["ok"])
        self.assertIn("test sandbox", r["error"])
        self.assertUntouched()

    def test_outside_the_sandbox_nothing_is_refused(self):
        os.environ.pop(plat.SANDBOX_ENV)
        self.assertIsNone(plat.sandbox_refusal("queue a job", self.real / "ppro-queue"))
        self.assertIsNone(plat.sandbox_refusal("launch After Effects"))


class TestInstallAndLaunchRefused(LiveRootCase):
    def test_bridge_install_refuses_the_real_cep_folder(self):
        from lib import ppro_bridge
        os.environ["WHYNOT_HOME"] = str(self.t / "elsewhere")
        ext = self.real / "CEP" / "extensions"
        with mock.patch.object(plat, "cep_extensions_dir", lambda: ext), \
                mock.patch.object(plat, "player_debug_mode", lambda: {}):
            r = ppro_bridge.install(force=True)
        self.assertIn("test sandbox", r["error"])
        self.assertUntouched()
        self.assertFalse((self.t / "elsewhere").exists())

    def test_after_effects_and_photoshop_are_never_launched(self):
        from lib import adobe_run
        app = {"name": "Adobe After Effects 2026", "exe": str(self.t / "AfterFX.exe")}
        with mock.patch.object(plat, "newest_app", lambda key: app), \
                mock.patch.object(adobe_run.subprocess, "Popen", side_effect=AssertionError("launched AE")), \
                mock.patch.object(adobe_run, "run", side_effect=AssertionError("launched")):
            self.assertEqual(adobe_run.run_after_effects(self.t / "x.jsx", 1)["status"], "REFUSED")
            self.assertEqual(adobe_run.run_photoshop(self.t / "x.jsx", 1)["status"], "REFUSED")

    def test_the_real_aerender_is_never_run(self):
        from lib import ae_render
        exe = self.t / ("aerender.exe" if plat.IS_WIN else "aerender")
        exe.write_bytes(b"")
        aep = self.t / "p.aep"
        aep.write_bytes(b"AEP")
        with mock.patch.object(ae_render, "aerender_exe", lambda: str(exe)), \
                mock.patch.object(ae_render, "run", side_effect=AssertionError("ran aerender")):
            r = ae_render.render(aep, "MAIN", self.t / "out.mov", "Best Settings", "High Quality")
        self.assertEqual(r["status"], "REFUSED")
        self.assertIn("test sandbox", r["msg"])


if __name__ == "__main__":
    unittest.main()
