"""The WhyNot Cut CEP bundle source (3.0 T6.3): the shell lives in <repo>/adobe/cep-bridge, byte-identical to the
3.1.1 installed on the owner's PC; lib/cep_bundle.source_dir()/assemble(); ppro_bridge.install() reads it, and a
plugin build without it (a shipped plugin) answers ok:false with a `how` and touches nothing. Every install here runs
in temp folders (WHYNOT_HOME, plat.cep_extensions_dir and cep_bundle.source_dir patched). Run:
    tools/test.sh -p test_cep_bridge.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import cep_bundle, plat, ppro_bridge  # noqa: E402

SRC = SK.parent / "adobe" / "cep-bridge"
# sha256 of the files of the bridge 3.1.1 installed on the owner's PC (%APPDATA%\Adobe\CEP\extensions\
# ai.thewhynot.cut.bridge, read 2026-10-13): Task 1 moves the shell without changing a byte.
LIVE_3_1_1 = {
    "CSXS/manifest.xml": "1035a42c41a82bc81233506a1b6a4dbc9ea2c0fa7e6fd81db873007348290824",
    "index.html": "ac5fd81bc7728e6bf8dda1a74df925e3e3b9cdb5b31d5b5e2f72ec128f8b3fb9",
    "js/bridge.js": "7506b0701341d0ac68c845e74849a3ab741fd822d3b1a570be449f7b456d58d9",
    "jsx/host.jsx": "2bf44b5d47becea6ec4e824eac67681d36e4bab15b2a55ecb88aa7028d1dde35",
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _files(root: Path) -> dict:
    """{posix relative path: sha256} of every file under root."""
    return {p.relative_to(root).as_posix(): _sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


class TestSource(unittest.TestCase):
    def test_source_dir_is_the_adobe_folder(self):
        self.assertEqual(cep_bundle.source_dir(), SRC)
        self.assertEqual(cep_bundle.source_dir(), cep_bundle.PLUGIN_DIR.parent / "adobe" / "cep-bridge")

    def test_holds_exactly_the_four_shell_files(self):
        self.assertEqual(sorted(_files(SRC)), sorted(LIVE_3_1_1))
        self.assertEqual(sorted(cep_bundle.SHELL_FILES), sorted(LIVE_3_1_1))

    def test_byte_identical_to_the_live_3_1_1(self):
        self.assertEqual(_files(SRC), LIVE_3_1_1)

    def test_the_old_templates_copy_is_gone(self):
        """One source: nothing of the shell is left under the plugin's templates."""
        self.assertFalse((SK / "templates" / "premiere" / "cep_bridge").exists())
        self.assertEqual([p for p in (SK / "templates").rglob("*") if p.name in ("bridge.js", "host.jsx")], [])


class TestAssemble(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_assemble_copies_the_shell_byte_for_byte(self):
        out = cep_bundle.assemble(self.tmp / "bundle")
        self.assertEqual(out, self.tmp / "bundle")
        self.assertEqual(_files(out), LIVE_3_1_1)

    def test_assemble_refuses_an_existing_folder(self):
        (self.tmp / "bundle").mkdir()
        with self.assertRaises(FileExistsError):
            cep_bundle.assemble(self.tmp / "bundle")

    def test_assemble_without_a_source_raises_and_writes_nothing(self):
        with mock.patch.object(cep_bundle, "source_dir", lambda: self.tmp / "missing"):
            with self.assertRaises(FileNotFoundError):
                cep_bundle.assemble(self.tmp / "bundle")
        self.assertFalse((self.tmp / "bundle").exists())


class TestInstall(unittest.TestCase):
    """ppro_bridge.install() in a sandbox: the engine home and the CEP folder are temp folders (resolved per call)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.ext_root = self.tmp / "ext"
        self._p = [mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.tmp / "home")}),
                   mock.patch.object(plat, "cep_extensions_dir", lambda: self.ext_root),
                   mock.patch.object(plat, "player_debug_mode", lambda: {})]
        for p in self._p:
            p.start()
        self.ext = ppro_bridge.ext_dir()
        self.assertEqual(self.ext, self.ext_root / ppro_bridge.EXT_ID)                  # never the real CEP folder
        self.assertEqual(ppro_bridge.queue_dir(), self.tmp / "home" / "ppro-queue")     # never the real engine home

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()

    def test_install_equals_the_source_plus_bridge_config(self):
        r = ppro_bridge.install(force=True)
        self.assertNotIn("error", r, r)
        self.assertEqual(r["installed"], str(self.ext))
        got = _files(self.ext)
        cfg = got.pop("bridge-config.json")
        self.assertEqual(got, _files(SRC))
        self.assertEqual(got, LIVE_3_1_1)
        self.assertEqual(_sha(self.ext / "bridge-config.json"), cfg)
        self.assertEqual(json.loads((self.ext / "bridge-config.json").read_text(encoding="utf-8")),
                         {"base": str((self.tmp / "home").resolve()), "version": ppro_bridge.BRIDGE_VERSION})

    def test_reinstall_replaces_the_old_folder(self):
        (self.ext / "stale").mkdir(parents=True)
        (self.ext / "stale" / "old.js").write_text("x", encoding="utf-8")
        ppro_bridge.install(force=True)
        self.assertFalse((self.ext / "stale").exists())
        self.assertEqual(sorted(_files(self.ext)), sorted([*LIVE_3_1_1, "bridge-config.json"]))

    def _installed_before(self) -> dict:
        (self.ext / "CSXS").mkdir(parents=True)
        (self.ext / "CSXS" / "manifest.xml").write_text('<ExtensionManifest ExtensionBundleVersion="3.1.1">',
                                                        encoding="utf-8")
        (self.ext / "bridge-config.json").write_text('{"version": "3.1.1"}', encoding="utf-8")
        return _files(self.ext)

    def test_missing_source_is_ok_false_with_how_and_touches_nothing(self):
        before = self._installed_before()
        for force in (False, True):
            with mock.patch.object(cep_bundle, "source_dir", lambda: self.tmp / "no-such-source"):
                r = ppro_bridge.install(force=force)
            self.assertEqual(r, {"ok": False, "error": "this plugin build carries no WhyNot Cut extension",
                                 "how": "install WhyNot Cut with its installer (the signed extension comes with it)"})
            self.assertEqual(_files(self.ext), before)                   # the installed extension is left as it is
        self.assertFalse((self.tmp / "home" / "ppro-queue").exists())
        self.assertFalse((self.tmp / "home" / "ppro-scripts").exists())

    def test_incomplete_source_is_refused_before_anything_is_removed(self):
        before = self._installed_before()
        partial = self.tmp / "partial"
        shutil.copytree(SRC, partial)
        (partial / "js" / "bridge.js").unlink()
        with mock.patch.object(cep_bundle, "source_dir", lambda: partial):
            r = ppro_bridge.install(force=True)
        self.assertFalse(r["ok"], r)
        self.assertIn("how", r)
        self.assertEqual(_files(self.ext), before)


if __name__ == "__main__":
    unittest.main()
