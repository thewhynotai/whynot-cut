"""The WhyNot Cut CEP bundle (3.0 T6.3): the shell in <repo>/adobe/cep-bridge, bundle 3.0.0 "WhyNot Cut" (Task 4): an
After Effects-only visible panel, a hidden daemon, the libraries bundled from whynot-cut/templates with a build.json,
the install rule by family and build, and ~/.whynot-cut/bridge/config.json. The legacy 3.1.1 bridge is frozen in
tests/fixtures/cep-bridge-3.1.1. Every install here runs in temp folders (WHYNOT_HOME, plat.cep_extensions_dir,
cep_bundle.config_path and, where needed, cep_bundle.source_dir patched). Run:
    tools/test.sh -p test_cep_bridge.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import os
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import cep_bundle, plat, ppro_bridge  # noqa: E402

SRC = SK.parent / "adobe" / "cep-bridge"
FROZEN = SK / "tests" / "fixtures" / "cep-bridge-3.1.1"
# sha256 of the files of the bridge 3.1.1 installed on the owner's PC (%APPDATA%\Adobe\CEP\extensions\
# ai.thewhynot.cut.bridge, read 2026-10-13); Task 4 froze bridge.js and the manifest before rewriting the shell.
LIVE_3_1_1 = {
    "CSXS/manifest.xml": "1035a42c41a82bc81233506a1b6a4dbc9ea2c0fa7e6fd81db873007348290824",
    "index.html": "ac5fd81bc7728e6bf8dda1a74df925e3e3b9cdb5b31d5b5e2f72ec128f8b3fb9",
    "js/bridge.js": "7506b0701341d0ac68c845e74849a3ab741fd822d3b1a570be449f7b456d58d9",
    "jsx/host.jsx": "2bf44b5d47becea6ec4e824eac67681d36e4bab15b2a55ecb88aa7028d1dde35",
}
SHELL = ["CSXS/manifest.xml", "daemon.html", "js/bridge.js", "jsx/wnc_host.jsx", "ui/index.html", "ui/js/panel.js"]
LIBS = ["wnc_ae_bridge.jsx", "wnc_ae_lib.jsx", "wnc_motion_lib.jsx", "wnc_ppro_lib.jsx"]
BUNDLE_FILES = sorted(SHELL + [f"jsx/{n}" for n in LIBS] + ["build.json"])
PANEL, DAEMON = "ai.thewhynot.cut.bridge.panel", "ai.thewhynot.cut.bridge.daemon"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _files(root: Path) -> dict:
    """{posix relative path: sha256} of every file under root."""
    return {p.relative_to(root).as_posix(): _sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _ext(root: ET.Element, ext_id: str, where: str) -> ET.Element:
    found = [e for e in root.iter("Extension") if e.get("Id") == ext_id and e.find("DispatchInfo") is not None]
    assert len(found) == 1, (ext_id, where)
    return found[0]


class TestSource(unittest.TestCase):
    def test_source_dir_is_the_adobe_folder(self):
        self.assertEqual(cep_bundle.source_dir(), SRC)
        self.assertEqual(cep_bundle.source_dir(), cep_bundle.PLUGIN_DIR.parent / "adobe" / "cep-bridge")

    def test_holds_exactly_the_shell(self):
        self.assertEqual(sorted(_files(SRC)), SHELL)
        self.assertEqual(sorted(cep_bundle.SHELL_FILES), SHELL)
        self.assertTrue(cep_bundle.has_source())

    def test_the_old_templates_copy_is_gone(self):
        """One source: nothing of the shell is left under the plugin's templates, and no library in the shell."""
        self.assertFalse((SK / "templates" / "premiere" / "cep_bridge").exists())
        self.assertEqual([p for p in (SK / "templates").rglob("*") if p.name in ("bridge.js", "host.jsx")], [])
        self.assertEqual(sorted(p.name for p in (SRC / "jsx").iterdir()), ["wnc_host.jsx"])

    def test_the_frozen_3_1_1_is_byte_identical_to_the_live_one(self):
        self.assertEqual(sorted(p.name for p in FROZEN.iterdir()), ["README.md", "bridge.js", "manifest.xml"])
        self.assertEqual(_sha(FROZEN / "bridge.js"), LIVE_3_1_1["js/bridge.js"])
        self.assertEqual(_sha(FROZEN / "manifest.xml"), LIVE_3_1_1["CSXS/manifest.xml"])
        readme = (FROZEN / "README.md").read_text(encoding="utf-8")
        for f in ("js/bridge.js", "CSXS/manifest.xml"):
            self.assertIn(LIVE_3_1_1[f], readme)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(SRC / "CSXS" / "manifest.xml").getroot()

    def test_bundle_3_0_0_named_whynot_cut_with_the_same_ids(self):
        r = self.root
        self.assertEqual((r.get("ExtensionBundleId"), r.get("ExtensionBundleVersion"), r.get("ExtensionBundleName")),
                         ("ai.thewhynot.cut.bridge", "3.0.0", "WhyNot Cut"))
        exts = {e.get("Id"): e.get("Version") for e in r.find("ExtensionList")}
        self.assertEqual(exts, {PANEL: "3.0.0", DAEMON: "3.0.0"})
        hosts = {h.get("Name"): h.get("Version") for h in r.find("ExecutionEnvironment/HostList")}
        self.assertEqual(hosts, {"PPRO": "[22.0,99.9]", "AEFT": "[24.0,99.9]"})

    def test_the_visible_panel_is_after_effects_only(self):
        panel = _ext(self.root, PANEL, "panel")
        self.assertEqual([(h.get("Name"), h.get("Version")) for h in panel.find("HostList")],
                         [("AEFT", "[24.0,99.9]")])
        di = panel.find("DispatchInfo")
        self.assertEqual(di.get("Host"), "AEFT")                      # the fallback for a CEP without extension hosts
        self.assertEqual(di.findtext("Resources/MainPath"), "./ui/index.html")
        self.assertEqual(di.findtext("Resources/ScriptPath"), "./jsx/wnc_host.jsx")
        self.assertEqual(di.findtext("UI/Type"), "Panel")
        self.assertEqual(di.findtext("UI/Menu"), "WhyNot Cut")
        self.assertEqual((di.findtext("UI/Geometry/Size/Width"), di.findtext("UI/Geometry/Size/Height")), ("340", "640"))
        self.assertEqual((di.findtext("UI/Geometry/MinSize/Width"), di.findtext("UI/Geometry/MinSize/Height")),
                         ("280", "320"))

    def test_the_daemon_is_hidden_and_starts_with_the_app(self):
        daemon = _ext(self.root, DAEMON, "daemon")
        self.assertIsNone(daemon.find("HostList"))                    # both hosts (the bundle's list)
        di = daemon.find("DispatchInfo")
        self.assertEqual(di.findtext("Resources/MainPath"), "./daemon.html")
        self.assertEqual(di.findtext("Resources/ScriptPath"), "./jsx/wnc_host.jsx")
        self.assertEqual(di.findtext("Lifecycle/AutoVisible"), "false")
        self.assertIsNone(di.find("UI/Menu"))
        old = _ext(ET.parse(FROZEN / "manifest.xml").getroot(), DAEMON, "3.1.1")
        self.assertEqual([e.text for e in di.find("Lifecycle/StartOn")],
                         [e.text for e in old.find("DispatchInfo/Lifecycle/StartOn")])     # the same StartOn
        for ext in (PANEL, DAEMON):
            params = [p.text for p in _ext(self.root, ext, ext).find("DispatchInfo/Resources/CEFCommandLine")]
            self.assertEqual(params, ["--enable-nodejs", "--mixed-context"])

    def test_the_pages_exist_and_load_the_right_scripts(self):
        self.assertIn('<script src="js/bridge.js"></script>', (SRC / "daemon.html").read_text(encoding="utf-8"))
        ui = (SRC / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="../js/bridge.js"></script>', ui)
        self.assertIn('<script src="js/panel.js"></script>', ui)

    def test_host_script_is_the_wnc_host_namespace(self):
        """Lint finding 18: the host script's global was nhBridgeAlive; now WNC_HOST.alive (tools/jsx_lint.py clean)."""
        host = (SRC / "jsx" / "wnc_host.jsx").read_text(encoding="utf-8")
        self.assertIn("var WNC_HOST = WNC_HOST || {};", host)
        self.assertIn("WNC_HOST.alive = function () {", host)
        self.assertNotIn("nhBridgeAlive", host)
        import importlib.util
        spec = importlib.util.spec_from_file_location("jsx_lint_t63", SK.parent / "tools" / "jsx_lint.py")
        lint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lint)
        self.assertEqual(lint.lint_file(SRC / "jsx" / "wnc_host.jsx"), [])


def _visible_strings() -> dict:
    """Every string an editor can see: the manifest's bundle name and menu, the pages' titles and text, the panel
    script's string literals."""
    root = ET.parse(SRC / "CSXS" / "manifest.xml").getroot()
    out = {"manifest:ExtensionBundleName": root.get("ExtensionBundleName")}
    for m in root.iter("Menu"):
        out["manifest:Menu"] = m.text
    for page in ("ui/index.html", "daemon.html"):
        html = (SRC / page).read_text(encoding="utf-8")
        html = re.sub(r"<!--.*?-->|<style>.*?</style>|<script.*?</script>", " ", html, flags=re.S)
        out[page] = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    js = re.sub(r"/\*.*?\*/|//[^\n]*", " ", (SRC / "ui" / "js" / "panel.js").read_text(encoding="utf-8"), flags=re.S)
    out["ui/js/panel.js"] = " | ".join(m.group(1) for m in re.finditer(r"'((?:[^'\\]|\\.)*)'", js))
    return out


class TestVisibleText(unittest.TestCase):
    def test_no_bridge_command_or_backtick_in_visible_strings(self):
        seen = _visible_strings()
        self.assertEqual(seen["manifest:ExtensionBundleName"], "WhyNot Cut")
        self.assertIn("WhyNot Cut", seen["ui/index.html"])
        self.assertIn("restart", seen["ui/js/panel.js"])
        for where, text in seen.items():
            with self.subTest(where):
                for bad in ("Bridge", "bridge", "reel ", "`", "Claude Code"):
                    self.assertNotIn(bad, text, f"{where}: {text!r}")


class TestAssemble(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_the_bundle_is_the_shell_plus_the_libraries_plus_build_json(self):
        out = cep_bundle.assemble(self.tmp / "bundle")
        self.assertEqual(out, self.tmp / "bundle")
        got = _files(out)
        self.assertEqual(sorted(got), BUNDLE_FILES)
        for f in SHELL:
            self.assertEqual(got[f], _sha(SRC / f), f)                                # the shell byte for byte
        for name, src in cep_bundle.lib_sources().items():
            self.assertEqual(got[f"jsx/{name}"], _sha(src), name)                    # the libraries from templates
        self.assertEqual(sorted(cep_bundle.lib_sources()), LIBS)
        self.assertTrue(all(p.parent.parent.name == "templates" for p in cep_bundle.lib_sources().values()))

    def test_build_json(self):
        out = cep_bundle.assemble(self.tmp / "bundle")
        b = json.loads((out / "build.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(b), ["build", "libs", "product", "protocol", "sha"])
        self.assertEqual((b["product"], b["protocol"]), ("3.0.0", 4))
        self.assertEqual(b["libs"], cep_bundle.expected_libs())
        self.assertRegex(b["build"], r"^[0-9a-f]{16}$")
        self.assertTrue(b["sha"] is None or re.fullmatch(r"[0-9a-f]{40}", b["sha"]), b["sha"])
        files = {k: v for k, v in _files(out).items() if k != "build.json"}
        self.assertEqual(b["build"], cep_bundle.build_id(files))
        self.assertEqual(b["build"], hashlib.sha256("".join(f"{p}\t{h}\n" for p, h in sorted(files.items()))
                                                    .encode("utf-8")).hexdigest()[:16])

    def test_the_build_id_is_stable_and_follows_the_sources(self):
        a = json.loads((cep_bundle.assemble(self.tmp / "a") / "build.json").read_text(encoding="utf-8"))["build"]
        b = json.loads((cep_bundle.assemble(self.tmp / "b") / "build.json").read_text(encoding="utf-8"))["build"]
        self.assertEqual(a, b)
        other = self.tmp / "src"
        shutil.copytree(SRC, other)
        with open(other / "ui" / "js" / "panel.js", "a", encoding="utf-8") as f:
            f.write("\n")
        with mock.patch.object(cep_bundle, "source_dir", lambda: other):
            c = json.loads((cep_bundle.assemble(self.tmp / "c") / "build.json").read_text(encoding="utf-8"))["build"]
        self.assertNotEqual(a, c)

    def test_assemble_refuses_an_existing_folder(self):
        (self.tmp / "bundle").mkdir()
        with self.assertRaises(FileExistsError):
            cep_bundle.assemble(self.tmp / "bundle")

    def test_assemble_without_a_source_raises_and_writes_nothing(self):
        with mock.patch.object(cep_bundle, "source_dir", lambda: self.tmp / "missing"):
            self.assertFalse(cep_bundle.has_source())
            with self.assertRaises(FileNotFoundError):
                cep_bundle.assemble(self.tmp / "bundle")
        self.assertFalse((self.tmp / "bundle").exists())


class TestFamily(unittest.TestCase):
    def test_family(self):
        self.assertEqual(cep_bundle.family("3.0.0", 4), "bundle")
        self.assertEqual(cep_bundle.family("3.1.1", None), "legacy")
        for version, proto in (("3.1.0", None), ("3.0.0", None), ("3.0.0", 5), ("3.0.1", 4), ("3.1.1", 4), (None, None)):
            self.assertIsNone(cep_bundle.family(version, proto), (version, proto))


def _legacy(ext: Path, version="3.1.1", bid="ai.thewhynot.cut.bridge", cfg=True) -> Path:
    (ext / "CSXS").mkdir(parents=True)
    (ext / "CSXS" / "manifest.xml").write_text(f'<ExtensionManifest ExtensionBundleId="{bid}" '
                                               f'ExtensionBundleVersion="{version}">', encoding="utf-8")
    if cfg:
        (ext / "bridge-config.json").write_text(json.dumps({"base": "x", "version": version}), encoding="utf-8")
    return ext


class TestInstalled(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_nothing(self):
        self.assertIsNone(cep_bundle.installed(self.tmp / "none"))
        (self.tmp / "empty").mkdir()
        self.assertIsNone(cep_bundle.installed(self.tmp / "empty"))

    def test_the_bundle(self):
        b = cep_bundle.assemble(self.tmp / "b")
        got = cep_bundle.installed(b)
        build = json.loads((b / "build.json").read_text(encoding="utf-8"))
        self.assertEqual(got, {"path": str(b), "id": "ai.thewhynot.cut.bridge", "family": "bundle", "version": "3.0.0",
                               "build": build["build"], "libs": build["libs"], "signed": False})
        (b / "META-INF").mkdir()
        (b / "META-INF" / "signatures.xml").write_text("<signatures/>", encoding="utf-8")
        self.assertTrue(cep_bundle.installed(b)["signed"])

    def test_the_legacy_family(self):
        for version in ("3.1.1", "3.1.0", "3.0.0", "1.2.0"):
            ext = _legacy(self.tmp / version, version)
            got = cep_bundle.installed(ext)
            self.assertEqual((got["family"], got["version"], got["build"]), ("legacy", version, None), version)
        got = cep_bundle.installed(_legacy(self.tmp / "nh" / "com.nh.bridge", "9.0.0", "com.nh.bridge", cfg=False))
        self.assertEqual((got["family"], got["id"]), ("legacy", "com.nh.bridge"))

    def test_an_unknown_layout(self):
        got = cep_bundle.installed(_legacy(self.tmp / "u", "9.1.0", cfg=False))
        self.assertEqual((got["family"], got["version"]), ("unknown", "9.1.0"))


class TestDecideInstall(unittest.TestCase):
    NEW = {"family": "bundle", "version": "3.0.0", "build": "b" * 16, "signed": False}

    def bundle(self, **kw):
        return dict({"family": "bundle", "id": "ai.thewhynot.cut.bridge", "version": "3.0.0", "build": "a" * 16,
                     "signed": False}, **kw)

    def test_matrix(self):
        legacy = {"family": "legacy", "id": "ai.thewhynot.cut.bridge", "version": "3.1.1", "build": None, "signed": False}
        nh = {"family": "legacy", "id": "com.nh.bridge", "version": "1.0.0", "build": None, "signed": False}
        cases = [
            ("nothing installed", None, False, "install"),
            ("legacy 3.1.1", legacy, False, "replace"),
            ("com.nh.bridge", nh, False, "replace"),
            ("the same build", self.bundle(build="b" * 16), False, "skip"),
            ("a newer product", self.bundle(version="3.1.0"), False, "keep"),
            ("signed over unsigned", self.bundle(signed=True), False, "keep"),
            ("signed, same build", self.bundle(build="b" * 16, signed=True), False, "skip"),
            ("an unknown layout", {"family": "unknown", "version": "9.1.0", "build": None}, False, "keep"),
            ("another unsigned build", self.bundle(), False, "replace"),
            ("an older product", self.bundle(version="2.9.0"), False, "replace"),
            ("forced over signed", self.bundle(signed=True), True, "replace"),
            ("forced over newer", self.bundle(version="3.1.0"), True, "replace"),
            ("forced over the same build", self.bundle(build="b" * 16), True, "replace"),
        ]
        for name, cur, force, want in cases:
            with self.subTest(name):
                d = cep_bundle.decide_install(cur, self.NEW, force=force)
                self.assertEqual(d["action"], want, d)
                self.assertTrue(d["reason"])

    def test_a_signed_build_replaces_another_signed_build(self):
        d = cep_bundle.decide_install(self.bundle(signed=True), dict(self.NEW, signed=True))
        self.assertEqual(d["action"], "replace")


class _Sandbox(unittest.TestCase):
    """The engine home, the CEP folder and config.json are temp paths (resolved per call)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.ext_root = self.tmp / "ext"
        self.cfg = self.tmp / "user" / ".whynot-cut" / "bridge" / "config.json"
        self._p = [mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.tmp / "home")}),
                   mock.patch.object(plat, "cep_extensions_dir", lambda: self.ext_root),
                   mock.patch.object(plat, "player_debug_mode", lambda: {}),
                   mock.patch.object(cep_bundle, "config_path", lambda: self.cfg)]
        for p in self._p:
            p.start()
        self.ext = ppro_bridge.ext_dir()
        self.assertEqual(self.ext, self.ext_root / ppro_bridge.EXT_ID)                  # never the real CEP folder
        self.assertEqual(ppro_bridge.queue_dir(), self.tmp / "home" / "ppro-queue")     # never the real engine home

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()
        self._t.cleanup()


class TestWriteConfig(_Sandbox):
    def test_shape(self):
        p = cep_bundle.write_config(self.tmp / "home")
        self.assertEqual(p, self.cfg)
        doc = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(sorted(doc), ["at", "engine_home", "launcher", "schema", "written_by"])
        self.assertEqual((doc["schema"], doc["engine_home"], doc["launcher"], doc["written_by"]),
                         (1, str((self.tmp / "home").resolve()), None, "engine"))
        self.assertRegex(doc["at"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(cep_bundle.read_config(), doc)
        self.assertEqual([f.name for f in p.parent.iterdir()], ["config.json"])        # no temp file left
        if os.name == "posix":
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(p.parent.stat().st_mode & 0o777, 0o700)

    def test_installer_and_launcher(self):
        launcher = self.tmp / "home" / "bin" / "wnc-engine.cmd"
        doc = json.loads(cep_bundle.write_config(self.tmp / "home", launcher=launcher, written_by="installer")
                         .read_text(encoding="utf-8"))
        self.assertEqual((doc["launcher"], doc["written_by"]), (str(launcher.resolve()), "installer"))
        with self.assertRaises(ValueError):
            cep_bundle.write_config(self.tmp / "home", written_by="someone")

    def test_the_real_path_is_under_the_user_home(self):
        self._p[-1].stop()                    # only reads the path (Path.home() is the sandbox's here anyway)
        try:
            self.assertEqual(cep_bundle.config_path(), Path.home() / ".whynot-cut" / "bridge" / "config.json")
        finally:
            self._p[-1].start()


class TestInstall(_Sandbox):
    """ppro_bridge.install() delegates to cep_bundle: the install rule, config.json, never bridge-config.json."""

    def test_install_writes_the_bundle_and_config_json_never_bridge_config(self):
        r = ppro_bridge.install(force=True)
        self.assertNotIn("error", r, r)
        self.assertEqual((r["installed"], r["action"], r["version"]), (str(self.ext), "install", "3.0.0"))
        self.assertEqual(sorted(_files(self.ext)), BUNDLE_FILES)
        self.assertFalse((self.ext / "bridge-config.json").exists())
        self.assertEqual(r["build"], json.loads((self.ext / "build.json").read_text(encoding="utf-8"))["build"])
        cfg = json.loads(self.cfg.read_text(encoding="utf-8"))
        self.assertEqual((cfg["schema"], cfg["engine_home"], cfg["written_by"]),
                         (1, str((self.tmp / "home").resolve()), "engine"))
        self.assertEqual(r["config"], str(self.cfg))
        self.assertNotIn("Bridge", r["next"])
        self.assertIn("WhyNot Cut", r["next"])
        self.assertEqual(ppro_bridge.installed_version(), "3.0.0")
        self.assertFalse((self.tmp / "home" / "ppro-scripts").exists())               # the bundle carries its libs

    def test_the_same_build_is_skipped(self):
        ppro_bridge.install()
        before = _files(self.ext)
        r = ppro_bridge.install()
        self.assertEqual(r["action"], "skip", r)
        self.assertEqual(_files(self.ext), before)

    def test_the_legacy_3_1_1_is_replaced(self):
        _legacy(self.ext)
        (self.ext / "index.html").write_text("old", encoding="utf-8")
        r = ppro_bridge.install()
        self.assertEqual(r["action"], "replace", r)
        self.assertEqual(sorted(_files(self.ext)), BUNDLE_FILES)                       # no 3.1.1 file left

    def test_a_newer_or_signed_bundle_is_kept_unless_forced(self):
        ppro_bridge.install()
        build = self.ext / "build.json"
        doc = json.loads(build.read_text(encoding="utf-8"))
        build.write_text(json.dumps(dict(doc, product="3.1.0", build="f" * 16)), encoding="utf-8")
        r = ppro_bridge.install()
        self.assertTrue(r.get("skipped"), r)
        self.assertIn("3.1.0", r["detail"])
        self.assertIn("--force", r["detail"])
        self.assertEqual(json.loads(build.read_text(encoding="utf-8"))["product"], "3.1.0")
        build.write_text(json.dumps(dict(doc, build="f" * 16)), encoding="utf-8")       # same product, signed
        (self.ext / "META-INF").mkdir()
        (self.ext / "META-INF" / "signatures.xml").write_text("<s/>", encoding="utf-8")
        r = ppro_bridge.install()
        self.assertTrue(r.get("skipped"), r)
        self.assertIn("signed", r["detail"])
        r = ppro_bridge.install(force=True)
        self.assertEqual(r["action"], "replace", r)
        self.assertEqual(sorted(_files(self.ext)), BUNDLE_FILES)

    def test_missing_source_is_ok_false_with_how_and_touches_nothing(self):
        _legacy(self.ext)
        before = _files(self.ext)
        for force in (False, True):
            with mock.patch.object(cep_bundle, "source_dir", lambda: self.tmp / "no-such-source"):
                r = ppro_bridge.install(force=force)
            self.assertEqual(r, {"ok": False, "error": "this plugin build carries no WhyNot Cut extension",
                                 "how": "install WhyNot Cut with its installer (the signed extension comes with it)"})
            self.assertEqual(_files(self.ext), before)                   # the installed extension is left as it is
        self.assertFalse((self.tmp / "home" / "ppro-queue").exists())
        self.assertFalse((self.tmp / "home" / "ppro-scripts").exists())
        self.assertFalse(self.cfg.exists())

    def test_incomplete_source_is_refused_before_anything_is_removed(self):
        _legacy(self.ext)
        before = _files(self.ext)
        partial = self.tmp / "partial"
        shutil.copytree(SRC, partial)
        (partial / "js" / "bridge.js").unlink()
        with mock.patch.object(cep_bundle, "source_dir", lambda: partial):
            r = ppro_bridge.install(force=True)
        self.assertFalse(r["ok"], r)
        self.assertIn("how", r)
        self.assertEqual(_files(self.ext), before)

    def test_the_sandbox_refuses_the_real_config_json(self):
        """G79: an install that would write the real ~/.whynot-cut/bridge/config.json is refused in tests."""
        home = [Path(r) for r in plat.live_roots() if Path(r).name == ".whynot-cut"]
        self.assertTrue(home)
        real = home[0] / "bridge" / "config.json"
        with mock.patch.object(cep_bundle, "config_path", lambda: real),                 mock.patch.object(cep_bundle, "write_config", side_effect=AssertionError("must not write")):
            r = ppro_bridge.install(force=True)
        self.assertEqual(r.get("refused"), "test-sandbox", r)
        self.assertFalse(self.ext.exists())


if __name__ == "__main__":
    unittest.main()
