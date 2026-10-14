"""The WhyNot Cut CEP bundle (3.0 T6.3): the shell in <repo>/adobe/cep-bridge, bundle 3.0.0 "WhyNot Cut" (Task 4): an
After Effects-only visible panel, a hidden daemon, the libraries bundled from whynot-cut/templates with a build.json,
the install rule by family and build, and ~/.whynot-cut/bridge/config.json; the signed path (Task 6: install_zxp, the
ZXP preferred by ppro_bridge.install, the dev source only with WHYNOT_BRIDGE_DEV=1). The legacy 3.1.1 bridge is frozen in
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
BUNDLE_FILES = sorted(SHELL + [f"jsx/{n}" for n in LIBS] + ["build.json", "ui/tokens.css"])
BRAND_TOKENS = SK.parent / "brand" / "tokens.css"
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
        self.assertEqual(got["ui/tokens.css"], _sha(BRAND_TOKENS))                    # the one brand token source
        self.assertEqual(cep_bundle.BRAND_TOKENS, BRAND_TOKENS)
        self.assertFalse((SRC / "ui" / "tokens.css").exists())                        # an artefact, never a source

    def test_assemble_refuses_without_the_brand_tokens(self):
        with mock.patch.object(cep_bundle, "BRAND_TOKENS", self.tmp / "no-tokens.css"):
            with self.assertRaises(FileNotFoundError):
                cep_bundle.assemble(self.tmp / "bundle")
        self.assertFalse((self.tmp / "bundle").exists())

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
        """Legacy (replaced without force) = unsigned, no build.json, and ours: ai.thewhynot.cut.bridge up to 3.1.1
        (T6.3 Task 6 widened it from exactly 3.1.1), or the reel-editor com.nh.bridge. A later version or another id
        without build.json is unknown (kept unless forced). The queue still drives exactly 3.1.1 (`family`)."""
        ext = _legacy(self.tmp / "3.1.1", "3.1.1")
        got = cep_bundle.installed(ext)
        self.assertEqual((got["family"], got["version"], got["build"]), ("legacy", "3.1.1", None))
        for version in ("3.1.0", "3.0.0", "1.2.0", "3.1"):
            got = cep_bundle.installed(_legacy(self.tmp / version, version))
            self.assertEqual((got["family"], got["version"]), ("legacy", version), version)
        for version, bid in (("3.1.2", "ai.thewhynot.cut.bridge"), ("4.0.0", "ai.thewhynot.cut.bridge"),
                             ("3.1.0", "com.someone.else"), ("", "ai.thewhynot.cut.bridge")):
            got = cep_bundle.installed(_legacy(self.tmp / "u" / f"{bid}-{version}", version, bid))
            self.assertEqual(got["family"], "unknown", (version, bid))
        got = cep_bundle.installed(_legacy(self.tmp / "nh" / "com.nh.bridge", "9.0.0", "com.nh.bridge", cfg=False))
        self.assertEqual((got["family"], got["id"]), ("legacy", "com.nh.bridge"))

    def test_a_signed_extension_without_a_readable_build_json_is_never_legacy(self):
        """Review T6.3 1-4: a signed bundle whose build.json is missing or unreadable was classed legacy and replaced
        without force. Signed is checked first: such an extension is unknown, and the install rule keeps it."""
        def signed(ext: Path) -> Path:
            (ext / "META-INF").mkdir(parents=True)
            (ext / "META-INF" / "signatures.xml").write_text("<signatures/>", encoding="utf-8")
            return ext
        missing = cep_bundle.assemble(self.tmp / "missing")
        (missing / "build.json").unlink()
        broken = cep_bundle.assemble(self.tmp / "broken")
        (broken / "build.json").write_text("{not json", encoding="utf-8")
        cases = {"no build.json": signed(missing), "unreadable build.json": signed(broken),
                 "signed 3.1.1": signed(_legacy(self.tmp / "s311", "3.1.1")),
                 "signed com.nh.bridge": signed(_legacy(self.tmp / "nh2" / "com.nh.bridge", "1.0.0", "com.nh.bridge"))}
        new = cep_bundle.installed(cep_bundle.assemble(self.tmp / "new"))
        for name, ext in cases.items():
            with self.subTest(name):
                got = cep_bundle.installed(ext)
                self.assertEqual((got["family"], got["signed"]), ("unknown", True))
                self.assertEqual(cep_bundle.decide_install(got, new)["action"], "keep")
                self.assertEqual(cep_bundle.decide_install(got, new, force=True)["action"], "replace")

    def test_an_unknown_layout(self):
        got = cep_bundle.installed(_legacy(self.tmp / "u", "9.1.0", cfg=False))
        self.assertEqual((got["family"], got["version"]), ("unknown", "9.1.0"))

    def test_bridge_config_json_is_never_read(self):
        """Task 5 dropped the last bridge-config.json read: the version is the manifest's (or build.json's)."""
        ext = _legacy(self.tmp / "l", "3.1.1")
        (ext / "bridge-config.json").write_text(json.dumps({"base": "x", "version": "9.9.9"}), encoding="utf-8")
        self.assertEqual(cep_bundle.installed(ext)["version"], "3.1.1")
        alone = self.tmp / "alone"
        alone.mkdir()
        (alone / "bridge-config.json").write_text(json.dumps({"version": "3.1.1"}), encoding="utf-8")
        self.assertIsNone(cep_bundle.installed(alone))
        self.assertNotIn("bridge-config.json", Path(cep_bundle.__file__).read_text(encoding="utf-8")
                         .split('"""', 2)[2].replace("# a 3.1.x bridge-config.json alone", ""))


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
            ("unsigned 3.1.0 (ours)", dict(legacy, version="3.1.0"), False, "replace"),
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

    def test_the_signed_build_replaces_the_unsigned_copy_of_the_same_sources(self):
        """The build id covers the bundle without META-INF: a dev install of the same sources has the same build, and
        the signed ZXP still replaces it (the reverse is skipped)."""
        same = self.bundle(build="b" * 16)
        self.assertEqual(cep_bundle.decide_install(same, dict(self.NEW, signed=True))["action"], "replace")
        self.assertEqual(cep_bundle.decide_install(dict(same, signed=True), dict(self.NEW, signed=True))["action"],
                         "skip")
        self.assertEqual(cep_bundle.decide_install(dict(same, signed=True), self.NEW)["action"], "skip")


class _Sandbox(unittest.TestCase):
    """The engine home, the CEP folder and config.json are temp paths (resolved per call)."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.ext_root = self.tmp / "ext"
        self.cfg = self.tmp / "user" / ".whynot-cut" / "bridge" / "config.json"
        self.zxp = self.tmp / "plugin" / "adobe" / cep_bundle.ZXP_NAME        # absent unless a test makes it
        self._p = [mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.tmp / "home"), "WHYNOT_BRIDGE_DEV": "1"}),
                   mock.patch.object(cep_bundle, "zxp_path", lambda: self.zxp),
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
        launcher = self.tmp / "home" / "bin" / cep_bundle.LAUNCHER_NAME
        launcher.parent.mkdir(parents=True)
        launcher.write_text("@rem shim\n", encoding="utf-8")
        doc = json.loads(cep_bundle.write_config(self.tmp / "home", launcher=launcher, written_by="installer")
                         .read_text(encoding="utf-8"))
        self.assertEqual((doc["launcher"], doc["written_by"]), (str(launcher.resolve()), "installer"))
        with self.assertRaises(ValueError):
            cep_bundle.write_config(self.tmp / "home", written_by="someone")

    def test_the_launcher_is_filled_only_when_the_file_exists(self):
        home = self.tmp / "home"
        shim = home / "bin" / cep_bundle.LAUNCHER_NAME
        self.assertEqual(cep_bundle.LAUNCHER_NAME, "wnc-engine.cmd" if os.name == "nt" else "wnc-engine")
        self.assertEqual(cep_bundle.launcher_path(home), shim)
        read = lambda: json.loads(self.cfg.read_text(encoding="utf-8"))["launcher"]  # noqa: E731
        cep_bundle.write_config(home)                                     # no shim yet: null
        self.assertIsNone(read())
        cep_bundle.write_config(home, launcher=shim)                      # named, still missing: null
        self.assertIsNone(read())
        shim.parent.mkdir(parents=True)
        (home / "bin" / "other.cmd").mkdir()
        cep_bundle.write_config(home, launcher=home / "bin" / "other.cmd")  # a folder is not a launcher
        self.assertIsNone(read())
        shim.write_text("shim\n", encoding="utf-8")
        cep_bundle.write_config(home)                                     # the default, now present
        self.assertEqual(read(), str(shim.resolve()))
        cep_bundle.write_config(home, written_by="installer")
        self.assertEqual(read(), str(shim.resolve()))

    def test_install_fills_the_launcher_when_the_shim_exists(self):
        shim = cep_bundle.launcher_path(self.tmp / "home")
        shim.parent.mkdir(parents=True)
        shim.write_text("shim\n", encoding="utf-8")
        ppro_bridge.install(force=True)
        self.assertEqual(json.loads(self.cfg.read_text(encoding="utf-8"))["launcher"], str(shim.resolve()))

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


# ===================================================================================================== Task 6: the signed path
SIGNED_FILES = sorted(BUNDLE_FILES + ["META-INF/signatures.xml", "mimetype"])


def _make_zxp(out: Path, src: Path, *, signed=True, extra=None, drop=(), product=None) -> Path:
    """A ZXP like ZXPSignCmd writes one: mimetype, the bundle, META-INF/signatures.xml (when signed). `extra` adds
    raw entries {name: bytes | ZipInfo-with-data}; `product` rewrites build.json's product and build."""
    import zipfile
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("mimetype", "application/vnd.adobe.air-ucf-package+zip")
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src).as_posix()
            if p.is_file() and rel not in drop:
                data = p.read_bytes()
                if rel == "build.json" and product:
                    doc = json.loads(data)
                    data = json.dumps(dict(doc, product=product, build="9" * 16)).encode()
                zf.writestr(rel, data)
        if signed:
            zf.writestr("META-INF/signatures.xml", "<signatures/>")
        for name, data in (extra or {}).items():
            if isinstance(name, tuple):          # (ZipInfo, data)
                zf.writestr(name[0], data)
            else:
                zf.writestr(name, data)
    return out


class TestInstallZxp(unittest.TestCase):
    """cep_bundle.install_zxp: signed only, every entry checked before anything is written, CRC-checked extraction to
    <CEP root>/.wnc-staging/new, then the swap with <CEP root>/.wnc-staging/prev kept (one previous copy): never a
    second folder inside the extensions folder CEP scans."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.src = cep_bundle.assemble(self.tmp / "src" / cep_bundle.EXT_ID)
        self.ext = self.tmp / "CEP" / "extensions" / cep_bundle.EXT_ID
        self.staging = self.tmp / "CEP" / ".wnc-staging"
        self.new, self.prev = self.staging / "new", self.staging / "prev"
        self.old_new = self.ext.with_name(self.ext.name + ".new")              # the Task 6 layout (migrated)
        self.old_prev = self.ext.with_name(self.ext.name + ".prev")

    def tearDown(self):
        self._t.cleanup()

    def zxp(self, name="a.zxp", **kw) -> Path:
        return _make_zxp(self.tmp / "zxp" / name, self.src, **kw)

    def refused(self, zxp, needle):
        before = _files(self.ext) if self.ext.exists() else None
        with self.assertRaises(cep_bundle.ZxpError) as cm:
            cep_bundle.install_zxp(zxp, self.ext)
        self.assertIn(needle, str(cm.exception))
        self.assertEqual(_files(self.ext) if self.ext.exists() else None, before)       # untouched
        self.assertFalse(self.new.exists())
        return str(cm.exception)

    def test_a_signed_zxp_installs_byte_identical(self):
        r = cep_bundle.install_zxp(self.zxp(), self.ext)
        self.assertEqual((r["action"], r["installed"]["family"], r["installed"]["signed"]), ("install", "bundle", True))
        self.assertEqual(sorted(_files(self.ext)), SIGNED_FILES)
        for rel, h in _files(self.src).items():
            self.assertEqual(_files(self.ext)[rel], h, rel)
        self.assertEqual((self.new.exists(), self.prev.exists(), r["prev"]), (False, False, None))
        again = cep_bundle.install_zxp(self.zxp(), self.ext)
        self.assertEqual(again["action"], "skip", again)
        self.assertFalse(self.new.exists())

    def test_an_update_keeps_exactly_one_prev(self):
        cep_bundle.install_zxp(self.zxp(), self.ext)
        first = _files(self.ext)
        (self.src / "ui" / "tokens.css").write_text("/* v2 */", encoding="utf-8")
        b2 = json.loads((self.src / "build.json").read_text(encoding="utf-8"))
        (self.src / "build.json").write_text(json.dumps(dict(b2, build="2" * 16)), encoding="utf-8")
        r = cep_bundle.install_zxp(self.zxp("b.zxp"), self.ext)
        self.assertEqual(r["action"], "replace", r)
        self.assertEqual(_files(self.prev), first)
        self.assertEqual(r["prev"], str(self.prev))
        (self.src / "build.json").write_text(json.dumps(dict(b2, build="3" * 16)), encoding="utf-8")
        second = _files(self.ext)
        cep_bundle.install_zxp(self.zxp("c.zxp"), self.ext)
        self.assertEqual(_files(self.prev), second)                                     # one .prev, the latest
        self.assertEqual(sorted(p.name for p in self.staging.iterdir()), ["prev"])

    def test_after_an_update_the_extensions_folder_holds_only_the_live_extension(self):
        """CEP loads every folder of the extensions folder by its manifest: the staged new copy and the previous
        copy live in <CEP root>/.wnc-staging (same volume, never scanned)."""
        self.assertEqual(cep_bundle.staging_dir(self.ext), self.staging)
        cep_bundle.install_zxp(self.zxp(), self.ext)
        b2 = json.loads((self.src / "build.json").read_text(encoding="utf-8"))
        (self.src / "build.json").write_text(json.dumps(dict(b2, build="2" * 16)), encoding="utf-8")
        r = cep_bundle.install_zxp(self.zxp("b.zxp"), self.ext)
        self.assertEqual(r["action"], "replace", r)
        self.assertEqual([p.name for p in self.ext.parent.iterdir()], [self.ext.name])
        self.assertEqual(r["prev"], str(self.prev))
        self.assertTrue((self.prev / "CSXS" / "manifest.xml").is_file())

    def test_the_real_staging_folder_is_beside_the_extensions_folder(self):
        with mock.patch.object(plat, "cep_extensions_dir", lambda: self.tmp / "CEP" / "extensions"):
            self.assertEqual(cep_bundle.staging_dir(), self.staging)
        self.assertEqual(cep_bundle.staging_dir(self.ext), self.staging)

    def test_an_old_new_and_prev_in_the_extensions_folder_are_moved_out(self):
        cep_bundle.install_zxp(self.zxp(), self.ext)
        shutil.copytree(self.ext, self.old_prev)
        shutil.copytree(self.ext, self.old_new)
        r = cep_bundle.install_zxp(self.zxp(), self.ext)                               # the same build: skip
        self.assertEqual(r["action"], "skip", r)
        self.assertEqual([p.name for p in self.ext.parent.iterdir()], [self.ext.name])
        self.assertTrue((self.prev / "CSXS" / "manifest.xml").is_file())               # kept as the previous copy
        self.assertFalse(self.new.exists())

    def test_an_old_prev_without_the_extension_is_put_back(self):
        cep_bundle.install_zxp(self.zxp(), self.ext)
        first = _files(self.ext)
        os.replace(self.ext, self.old_prev)                                         # a Task 6 crash between renames
        r = cep_bundle.install_zxp(self.zxp(), self.ext)
        self.assertEqual(r["action"], "skip", r)
        self.assertEqual(_files(self.ext), first)
        self.assertIn("put back", r["recovered"])
        self.assertEqual([p.name for p in self.ext.parent.iterdir()], [self.ext.name])

    # ------------------------------------------------------------------ the swap is crash-safe
    def _update_zxp(self) -> Path:
        cep_bundle.install_zxp(self.zxp(), self.ext)
        b2 = json.loads((self.src / "build.json").read_text(encoding="utf-8"))
        (self.src / "build.json").write_text(json.dumps(dict(b2, build="2" * 16)), encoding="utf-8")
        return self.zxp("b.zxp")

    def _failing_replace(self, fail):
        """os.replace that raises for the renames `fail(src, dst)` picks; every other rename is real."""
        real = os.replace

        def fake(src, dst, *a, **k):
            if fail(Path(src), Path(dst)):
                raise PermissionError(13, "in use (test)")
            return real(src, dst, *a, **k)
        return mock.patch.object(cep_bundle.os, "replace", fake)

    def test_a_failed_first_rename_leaves_the_extension_as_it_was(self):
        z = self._update_zxp()
        before = _files(self.ext)
        with self._failing_replace(lambda s, d: s == self.ext and d == self.prev):
            with self.assertRaises(cep_bundle.ZxpError) as cm:
                cep_bundle.install_zxp(z, self.ext)
        self.assertIn("left as it was", str(cm.exception))
        self.assertEqual(_files(self.ext), before)
        self.assertFalse(self.new.exists())

    def test_a_failed_second_rename_puts_the_previous_copy_back(self):
        z = self._update_zxp()
        before = _files(self.ext)
        with self._failing_replace(lambda s, d: s == self.new):
            with self.assertRaises(cep_bundle.ZxpError) as cm:
                cep_bundle.install_zxp(z, self.ext)
        self.assertIn("put back", str(cm.exception))
        self.assertEqual(_files(self.ext), before)
        self.assertFalse(self.new.exists())
        self.assertEqual([p.name for p in self.ext.parent.iterdir()], [self.ext.name])

    def test_a_crash_between_the_renames_recovers_on_the_next_run(self):
        """The second rename fails and so does the way back (a crash leaves the same state): the message says where
        the previous copy is, and the next install puts it back before anything else."""
        z = self._update_zxp()
        before = _files(self.ext)
        with self._failing_replace(lambda s, d: s in (self.new, self.prev)):
            with self.assertRaises(cep_bundle.ZxpError) as cm:
                cep_bundle.install_zxp(z, self.ext)
        self.assertIn(str(self.prev), str(cm.exception))
        self.assertFalse(self.ext.exists())
        self.assertEqual(_files(self.prev), before)
        self.assertFalse(self.new.exists())
        (self.new / "junk").mkdir(parents=True)                                      # a crash mid-extraction too
        r = cep_bundle.install_zxp(z, self.ext)
        self.assertIn("put back", r["recovered"])
        self.assertEqual(r["action"], "replace", r)
        self.assertEqual(_files(self.prev), before)                                  # the recovered copy is the prev
        self.assertEqual(json.loads((self.ext / "build.json").read_text(encoding="utf-8"))["build"], "2" * 16)
        self.assertFalse(self.new.exists())

    def test_install_source_recovers_a_missing_extension_first(self):
        cep_bundle.install_zxp(self.zxp(), self.ext)
        first = _files(self.ext)
        self.staging.mkdir(exist_ok=True)
        os.replace(self.ext, self.prev)
        r = cep_bundle.install_source(self.ext)
        self.assertIn("put back", r["recovered"])
        self.assertEqual(r["action"], "skip", r)                    # the same build, signed: never replaced unsigned
        self.assertEqual(_files(self.ext), first)

    # ------------------------------------------------------------------ archive limits
    def test_too_many_entries_are_refused(self):
        extra = {f"pad/{i}.txt": b"" for i in range(cep_bundle.ZXP_MAX_ENTRIES)}
        self.refused(self.zxp(extra=extra), "entries")

    def test_too_large_an_archive_is_refused(self):
        import zipfile
        z = self.zxp()
        with zipfile.ZipFile(z, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pad/big.bin", b"\0" * (cep_bundle.ZXP_MAX_BYTES + 1))       # deflates to a few KB
        self.assertLess(z.stat().st_size, 1 << 20)
        self.refused(z, "MB")

    def test_names_ending_in_a_dot_or_a_space_are_refused(self):
        _legacy(self.ext)
        for i, name in enumerate(("jsx/evil.jsx.", "jsx/evil.jsx ", "jsx./x.jsx", "ui /x.js", "CSXS./manifest.xml")):
            with self.subTest(name=name):
                self.refused(self.zxp(f"d{i}.zxp", extra={name: b"x"}), "unsafe entry")

    def test_an_unsigned_zxp_is_never_installed(self):
        _legacy(self.ext)
        self.refused(self.zxp(signed=False), "not signed")

    def test_unsafe_entries_refuse_the_whole_archive_before_anything_is_written(self):
        import stat
        import zipfile
        link = zipfile.ZipInfo("js/link.js")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases = {"../evil.js": b"x", "/abs.js": b"x", "C:/drive.js": b"x", "ui\\..\\..\\evil.js": b"x",
                 "jsx/../../evil.js": b"x", "a//b.js": b"x", "./dot.js": b"x", (link, ): b"/etc/passwd"}
        _legacy(self.ext)
        for i, (name, data) in enumerate(cases.items()):
            with self.subTest(name=name if isinstance(name, str) else "a symlink entry"):
                key = name if isinstance(name, str) else (name[0],)
                self.refused(self.zxp(f"u{i}.zxp", extra={key: data}), "unsafe entry")
        self.assertEqual([p.name for p in self.tmp.rglob("evil.js")], [])
        self.assertEqual([p.name for p in self.tmp.rglob("abs.js")], [])

    def test_a_duplicate_entry_is_refused(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")                     # zipfile warns about the duplicate name
            self.refused(self.zxp(extra={"ui/index.html": b"<html>2</html>"}), "twice")

    def test_a_crc_mismatch_is_refused_and_nothing_is_swapped(self):
        _legacy(self.ext)
        z = self.zxp()
        data = bytearray(z.read_bytes())
        marker = (self.src / "js" / "bridge.js").read_bytes()[:64]
        at = data.find(marker)
        self.assertGreater(at, 0)
        data[at + 10] ^= 0x01                                    # one bit of a stored file
        z.write_bytes(bytes(data))
        self.refused(z, "js/bridge.js")

    def test_another_bundle_id_is_refused(self):
        (self.src / "CSXS" / "manifest.xml").write_text(
            '<ExtensionManifest ExtensionBundleId="com.someone.else" ExtensionBundleVersion="3.0.0">', encoding="utf-8")
        self.refused(self.zxp(), "is not the WhyNot Cut extension")

    def test_not_a_zip(self):
        bad = self.tmp / "zxp" / "bad.zxp"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"not a zip")
        self.refused(bad, "not a readable ZXP")

    def test_the_install_rule_applies(self):
        """An unsigned 3.1.0 of ours is replaced without force; a newer bundle is kept unless forced; the signed ZXP
        replaces the unsigned dev copy of the same sources."""
        _legacy(self.ext, "3.1.0")
        r = cep_bundle.install_zxp(self.zxp(), self.ext)
        self.assertEqual(r["action"], "replace", r)
        self.assertEqual(_files(self.prev)["CSXS/manifest.xml"], _sha(self.prev / "CSXS" / "manifest.xml"))
        shutil.rmtree(self.ext)
        shutil.rmtree(self.prev)
        shutil.copytree(self.src, self.ext)                                           # the unsigned dev copy
        r = cep_bundle.install_zxp(self.zxp("same.zxp"), self.ext)
        self.assertEqual((r["action"], r["installed"]["signed"]), ("replace", True))
        r = cep_bundle.install_zxp(self.zxp("newer.zxp", product="9.0.0"), self.ext, force=True)
        self.assertEqual(r["installed"]["version"], "9.0.0")
        r = cep_bundle.install_zxp(self.zxp("older.zxp"), self.ext)
        self.assertEqual(r["action"], "keep", r)
        self.assertEqual(cep_bundle.installed(self.ext)["version"], "9.0.0")
        self.assertFalse(self.new.exists())

    @unittest.skipUnless(os.name == "nt", "a Windows junction")
    def test_a_linked_extension_folder_is_left_alone(self):
        import _winapi
        dev = self.tmp / "dev-checkout"
        dev.mkdir()
        self.ext.parent.mkdir(parents=True)
        _winapi.CreateJunction(str(dev), str(self.ext))
        with self.assertRaises(cep_bundle.ZxpError) as cm:
            cep_bundle.install_zxp(self.zxp(), self.ext)
        self.assertIn("is a link", str(cm.exception))
        self.assertEqual(list(dev.iterdir()), [])


class TestInstallPrefersTheSignedZxp(_Sandbox):
    """ppro_bridge.install (Task 6): the signed ZXP first, then the dev source with WHYNOT_BRIDGE_DEV=1, else ok:false."""

    def test_the_signed_zxp_is_installed_and_needs_no_debug_mode(self):
        _make_zxp(self.zxp, cep_bundle.assemble(self.tmp / "src" / cep_bundle.EXT_ID))
        _legacy(self.ext, "3.1.0")                                                    # an older bridge of ours
        r = ppro_bridge.install()
        self.assertNotIn("error", r, r)
        self.assertEqual((r["action"], r["source"], r["signed"], r["version"]), ("replace", "zxp", True, "3.0.0"))
        self.assertEqual(sorted(_files(self.ext)), SIGNED_FILES)
        self.assertEqual((r["debug_mode_ok"], r["editor_must_run"]), (True, []))       # PlayerDebugMode is off here
        self.assertTrue(self.cfg.is_file())
        with mock.patch.dict(os.environ, {"WHYNOT_BRIDGE_DEV": "0"}):                  # the ZXP wins either way
            self.assertEqual(ppro_bridge.install()["action"], "skip")

    def test_the_signed_zxp_replaces_a_dev_install_of_the_same_sources(self):
        ppro_bridge.install()                                                         # the dev source (env = 1)
        self.assertFalse(cep_bundle.installed(self.ext)["signed"])
        _make_zxp(self.zxp, cep_bundle.assemble(self.tmp / "src" / cep_bundle.EXT_ID))
        r = ppro_bridge.install()
        self.assertEqual((r["action"], r["signed"]), ("replace", True), r)

    def test_without_a_zxp_the_dev_source_needs_whynot_bridge_dev(self):
        _legacy(self.ext, "3.1.0")
        before = _files(self.ext)
        with mock.patch.dict(os.environ, {"WHYNOT_BRIDGE_DEV": ""}):
            r = ppro_bridge.install(force=True)
        self.assertIs(r["ok"], False)
        self.assertIn(cep_bundle.ZXP_NAME, r["error"])
        self.assertIn("python tools/sign_zxp.py build", r["how"])
        self.assertIn("WHYNOT_BRIDGE_DEV=1", r["how"])
        self.assertEqual(_files(self.ext), before)
        self.assertFalse(self.cfg.exists())
        r = ppro_bridge.install()                                                     # env = 1 (the sandbox)
        self.assertEqual((r["action"], r["source"], r["signed"]), ("replace", "source", False), r)

    def test_a_bad_zxp_is_ok_false_and_touches_nothing(self):
        _legacy(self.ext)
        before = _files(self.ext)
        _make_zxp(self.zxp, cep_bundle.assemble(self.tmp / "src" / cep_bundle.EXT_ID), signed=False)
        r = ppro_bridge.install(force=True)
        self.assertIs(r["ok"], False)
        self.assertIn("not signed", r["error"])
        self.assertIn("how", r)
        self.assertEqual(_files(self.ext), before)
        self.assertFalse(self.cfg.exists())


# ===================================================================================================== Task 5: engine start
NODE = shutil.which("node")
# Runs the real js/bridge.js in node with a stubbed CEP, a fake child_process (records every spawn), a fake clock and
# fake timers (the harness steps virtual seconds), a fake process.kill (only the scenario's pids are alive) and, when
# the scenario says so, os.platform() and fs.statSync uid / mode overrides (POSIX checks on any host). The scenario is
# a JSON file; HOME / USERPROFILE of the node process are a temp folder.
SPAWN_HARNESS = r"""
const vm = require('vm'), fs = require('fs'), path = require('path'), os = require('os');
const sc = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let now = 1000000000000;
class FakeDate extends Date {
  constructor(...a) { if (a.length) { super(...a); } else { super(now); } }
  static now() { return now; }
}
const alive = new Set(sc.alive || []), timers = [], spawns = [], pending = [];
const norm = (p) => { const r = path.resolve(p); return process.platform === 'win32' ? r.toLowerCase() : r; };
const statOv = {};
for (const k of Object.keys(sc.stat || {})) { statOv[norm(k)] = sc.stat[k]; }
const fakeFs = Object.assign({}, fs, {
  statSync(p, o) {
    const s = fs.statSync(p, o), ov = statOv[norm(p)];
    return ov ? Object.assign(Object.create(Object.getPrototypeOf(s)), s, ov) : s;
  }
});
const fakeOs = Object.assign({}, os, { platform: () => sc.platform || os.platform() });
let died = false;
function engineUp() {
  if (!sc.startEngine || died || spawns.length < (sc.startOnSpawn || 1)) { return; }
  fs.mkdirSync(path.dirname(sc.engineJson), { recursive: true });
  fs.writeFileSync(sc.engineJson, JSON.stringify({ port: 4321, token: sc.token, pid: sc.startEngine, version: '3.0.0' }));
  alive.add(sc.startEngine);
}
const fakeCp = {
  spawn(file, args, opts) {
    const rec = { file, args, opts: Object.assign({}, opts), at: now, unref: false };
    spawns.push(rec);
    if (sc.spawn === 'throw') { throw new Error('spawn EACCES'); }
    const ls = {};
    const child = { on(ev, f) { (ls[ev] = ls[ev] || []).push(f); return child; }, unref() { rec.unref = true; } };
    const fire = (ev, v) => (ls[ev] || []).forEach((f) => f(v));
    if (sc.spawn === 'error') { pending.push(() => fire('error', new Error('spawn ENOENT'))); }
    else if (sc.spawn === 'exit1') { pending.push(() => fire('exit', 1)); }
    else { pending.push(() => { engineUp(); fire('exit', 0); }); }
    return child;
  }
};
if (sc.realSpawn) { fakeCp.spawn = require('child_process').spawn; }
const fakeRequire = (n) => n === 'child_process' ? fakeCp : n === 'os' ? fakeOs : n === 'fs' ? fakeFs : require(n);
const fakeProcess = {
  env: Object.assign({}, process.env, sc.env || {}),
  kill(pid, sig) { if (alive.has(pid)) { return true; } const e = new Error('kill ESRCH'); e.code = 'ESRCH'; throw e; },
  getuid: () => (sc.uid === undefined ? 501 : sc.uid)
};
const state = { textContent: '' }, logEl = { textContent: '' };
const cep = {
  getExtensionId: () => 'ai.thewhynot.cut.bridge.' + sc.role,
  getHostEnvironment: () => JSON.stringify({ appName: sc.host || 'PPRO', appVersion: '26.5.2' }),
  getSystemPath: () => 'file:///' + sc.ext.replace(/\\/g, '/'),
  evalScript: (code, cb) => cb('{}')
};
const ctx = { window: { __adobe_cep__: cep, cep_node: { require: fakeRequire } },
              document: { getElementById: (id) => id === 'state' ? state : logEl },
              setInterval: (f) => { timers.push(f); }, process: fakeProcess, console, Date: FakeDate };
vm.runInNewContext(fs.readFileSync(sc.bridge, 'utf8'), ctx);
const flush = () => { while (pending.length) { pending.shift()(); } };
const beat = () => { try { return JSON.parse(fs.readFileSync(sc.heartbeat, 'utf8')); } catch (e) { return null; } };
const outcomes = [];
flush();
for (let s = 0; s < (sc.seconds || 0); s++) {
  now += 1000;
  if (sc.dieAt && s + 1 === sc.dieAt) { died = true; alive.delete(sc.startEngine); fs.unlinkSync(sc.engineJson); }
  timers.forEach((f) => f());
  flush();
  const b = beat();
  outcomes.push(b && b.engine_start ? b.engine_start.outcome : null);
}
const queueFiles = {};
try {
  for (const f of fs.readdirSync(path.dirname(sc.heartbeat))) {
    queueFiles[f] = fs.readFileSync(path.join(path.dirname(sc.heartbeat), f), 'utf8');
  }
} catch (e) {}
fs.writeFileSync(sc.out, JSON.stringify({ spawns, beat: beat(), outcomes, log: logEl.textContent, state: state.textContent,
  panel: ctx.window.WNC_BRIDGE ? { role: ctx.window.WNC_BRIDGE.role } : null, start: 1000000000000, queueFiles }));
"""
TOKEN = "7f" * 32          # what engine.json's token looks like (64 hex): must never leave the file


@unittest.skipUnless(NODE, "needs node to run js/bridge.js with a stubbed CEP")
class TestEngineStart(unittest.TestCase):
    """The hidden daemon starts the engine only through config.json `launcher`, only when it is the fixed
    <engine home>/bin/wnc-engine(.cmd), never from the panel, at most once per 30 s and never after 5 failures."""

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.user = self.tmp / "user"
        self.user.mkdir()
        self.ext = cep_bundle.assemble(self.tmp / "ext" / cep_bundle.EXT_ID)
        self.home = self.user / "engine home"           # a space: the Windows quoting must survive it; inside the
                                                         # profile (Windows refuses a launcher outside %USERPROFILE%)
        self.harness = self.tmp / "harness.js"
        self.harness.write_text(SPAWN_HARNESS, encoding="utf-8")
        self.engine_json = self.user / ".whynot-cut" / "bridge" / "engine.json"

    def tearDown(self):
        self._t.cleanup()

    def launcher(self, home: Path = None, name: str = None, platform: str = None) -> Path:
        home = home or self.home
        name = name or ("wnc-engine.cmd" if (platform or ("win32" if os.name == "nt" else "darwin")) == "win32"
                        else "wnc-engine")
        f = home / "bin" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("@echo off\r\n", encoding="utf-8")
        return f

    def config(self, launcher, home: Path = None):
        home = home or self.home
        home.mkdir(parents=True, exist_ok=True)
        cfg = self.user / ".whynot-cut" / "bridge" / "config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"schema": 1, "engine_home": str(home),
                                   "launcher": None if launcher is None else str(launcher),
                                   "written_by": "installer", "at": "2026-10-13T00:00:00+00:00"}), encoding="utf-8")
        return cfg

    def engine(self, pid: int, raw: str = None):
        self.engine_json.parent.mkdir(parents=True, exist_ok=True)
        self.engine_json.write_text(raw if raw is not None else
                                    json.dumps({"port": 4321, "token": TOKEN, "pid": pid, "pid_created": 1.0,
                                                "version": "3.0.0", "protocol": 4}), encoding="utf-8")

    def run_bridge(self, role="daemon", seconds=5, home: Path = None, **sc) -> dict:
        import subprocess
        home = home or self.home
        out = self.tmp / f"out-{role}.json"
        doc = dict({"bridge": str(SRC / "js" / "bridge.js"), "ext": str(self.ext), "role": role, "host": "PPRO",
                    "seconds": seconds, "out": str(out), "token": TOKEN, "engineJson": str(self.engine_json),
                    "heartbeat": str(home / "ppro-queue" / "bridge.heartbeat")}, **sc)
        scen = self.tmp / "scenario.json"
        scen.write_text(json.dumps(doc), encoding="utf-8")
        env = dict(os.environ, HOME=str(self.user), USERPROFILE=str(self.user))
        r = subprocess.run([NODE, str(self.harness), str(scen)], capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        res = json.loads(out.read_text(encoding="utf-8"))
        self.assertNotIn(TOKEN, json.dumps(res))                    # the token never leaves engine.json
        self.assertNotIn(TOKEN[:24], r.stdout + r.stderr)
        return res

    def platform(self):
        return "win32" if os.name == "nt" else "darwin"

    def expected_spawn(self, launcher: Path, platform: str, home: Path = None):
        home = home or self.home
        opts = {"detached": True, "windowsHide": True, "stdio": "ignore", "cwd": str(home)}
        if platform == "win32":
            return {"file": "C:\\Windows\\System32\\cmd.exe", "args": ["/d", "/s", "/c", '""' + str(launcher) + '""'],
                    "opts": dict(opts, windowsVerbatimArguments=True)}
        return {"file": str(launcher), "args": [], "opts": opts}

    # ---------------------------------------------------------------- no spawn
    def test_no_config_or_no_launcher_never_spawns(self):
        out = self.run_bridge(seconds=65, home=self.user / ".whynot-cut")   # no config: the fallback engine home
        self.assertEqual(out["spawns"], [])
        self.assertEqual(out["beat"]["engine_start"]["outcome"], "no_launcher")
        self.config(None)
        out = self.run_bridge(seconds=65)
        self.assertEqual((out["spawns"], out["beat"]["engine_start"]["outcome"]), ([], "no_launcher"))

    def test_a_launcher_that_is_not_the_fixed_file_is_refused(self):
        evil = self.tmp / "evil"
        evil.mkdir()
        good = self.launcher()
        cases = {
            "outside bin": self.home / good.name,
            "wrong name": self.launcher(name="evil.cmd"),
            "relative": Path("bin") / good.name,
            "elsewhere": evil / good.name,
            "missing": self.home / "bin" / ("nothere" + good.suffix),
        }
        cases["outside bin"].write_text("x", encoding="utf-8")
        cases["elsewhere"].write_text("x", encoding="utf-8")
        dirhome = self.tmp / "dir home"
        (dirhome / "bin" / good.name).mkdir(parents=True)
        for name, launcher in cases.items():
            with self.subTest(name):
                self.config(launcher)
                out = self.run_bridge(seconds=35)
                self.assertEqual(out["spawns"], [])
                self.assertEqual(out["beat"]["engine_start"]["outcome"], "refused")
        with self.subTest("a folder"):
            self.config(dirhome / "bin" / good.name, home=dirhome)
            out = self.run_bridge(seconds=35, home=dirhome)
            self.assertEqual((out["spawns"], out["beat"]["engine_start"]["outcome"]), ([], "refused"))
            self.assertIn("not a regular file", out["log"])

    def test_a_launcher_linked_elsewhere_is_refused(self):
        evil = self.tmp / "evil" / "wnc-engine.cmd"
        evil.parent.mkdir()
        evil.write_text("x", encoding="utf-8")
        link = self.home / "bin" / ("wnc-engine.cmd" if os.name == "nt" else "wnc-engine")
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(evil)
        except OSError as e:
            self.skipTest(f"no symlinks here: {e}")
        self.config(link)
        out = self.run_bridge(seconds=35)
        self.assertEqual((out["spawns"], out["beat"]["engine_start"]["outcome"]), ([], "refused"))

    def test_every_refusal_carries_a_static_reason(self):
        """engine_start {at, outcome, reason}: a fixed code per refusal (the doctor turns it into a sentence); never
        a path or any text from the file system."""
        evil = self.tmp / "evil"
        evil.mkdir()
        good = self.launcher()
        (evil / good.name).write_text("x", encoding="utf-8")
        dirhome = self.user / "dir home"
        (dirhome / "bin" / good.name).mkdir(parents=True)
        cases = {"not_absolute": (Path("bin") / good.name, None),
                 "not_found": (self.home / "bin" / ("nothere" + good.suffix), None),
                 "not_the_launcher": (evil / good.name, None),
                 "not_a_file": (dirhome / "bin" / good.name, dirhome)}
        for reason, (launcher, home) in cases.items():
            with self.subTest(reason):
                self.config(launcher, home=home)
                out = self.run_bridge(seconds=1, home=home)
                self.assertEqual(out["beat"]["engine_start"]["outcome"], "refused")
                self.assertEqual(out["beat"]["engine_start"]["reason"], reason)
        self.config(None)
        out = self.run_bridge(seconds=1)
        self.assertEqual(out["beat"]["engine_start"], {"at": out["start"], "outcome": "no_launcher", "reason": None})
        js = (SRC / "js" / "bridge.js").read_text(encoding="utf-8")
        for reason in ("not_absolute", "metachar_in_path", "not_found", "not_a_file", "unresolvable",
                       "not_the_launcher", "outside_profile", "not_owner", "writable_by_others", "gave_up"):
            self.assertIn("'" + reason + "'", js)

    def test_windows_refuses_a_launcher_outside_the_user_profile(self):
        home = self.tmp / "outside home"
        launcher = self.launcher(home=home, platform="win32")
        self.config(launcher, home=home)
        out = self.run_bridge(seconds=35, home=home, platform="win32", startEngine=1,
                              env={"USERPROFILE": str(self.user)})
        self.assertEqual(out["spawns"], [])
        self.assertEqual((out["beat"]["engine_start"]["outcome"], out["beat"]["engine_start"]["reason"]),
                         ("refused", "outside_profile"))
        launcher = self.launcher(platform="win32")                          # inside the profile: started
        self.config(launcher)
        out = self.run_bridge(seconds=1, platform="win32", startEngine=1, env={"USERPROFILE": str(self.user)})
        self.assertEqual(len(out["spawns"]), 1)

    def test_the_spawned_file_is_the_checked_realpath(self):
        """config.json names the launcher through a linked engine home: what is spawned is the realpath that passed
        the checks, never the configured string (a link swapped after the check cannot redirect the spawn)."""
        real_home = self.user / "real home"
        real_home.mkdir()
        link_home = self.user / "linked home"
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(real_home), str(link_home))
            else:
                link_home.symlink_to(real_home, target_is_directory=True)
        except OSError as e:
            self.skipTest(f"no links here: {e}")
        for platform in ("win32", "darwin"):
            with self.subTest(platform):
                real = self.launcher(home=real_home, platform=platform)
                configured = link_home / "bin" / real.name
                self.config(configured, home=link_home)
                if self.engine_json.exists():
                    self.engine_json.unlink()
                rp = str(Path(os.path.realpath(real)))
                stat = {} if platform == "win32" else {rp: {"uid": 501, "mode": 0o100755}}
                out = self.run_bridge(seconds=1, home=link_home, platform=platform, startEngine=9, stat=stat,
                                      env={"ComSpec": "C:\\Windows\\System32\\cmd.exe"})
                (sp,) = out["spawns"]
                if platform == "win32":
                    self.assertEqual(sp["args"][-1], '""' + rp + '""')
                else:
                    self.assertEqual(sp["file"], rp)
                self.assertNotIn("linked home", json.dumps(sp))

    def test_metacharacters_are_refused(self):
        for ch in "%^&!":                     # " < > | cannot be in a Windows file name; the check covers them too
            with self.subTest(ch):
                home = self.tmp / f"home {ch} x"
                self.config(self.launcher(home=home), home=home)
                out = self.run_bridge(seconds=35, home=home)
                self.assertEqual(out["spawns"], [])
                self.assertEqual(out["beat"]["engine_start"]["outcome"], "refused")
                self.assertEqual(out["beat"]["engine_start"]["reason"], "metachar_in_path")
        js = (SRC / "js" / "bridge.js").read_text(encoding="utf-8")
        self.assertIn("var LAUNCHER_META = /[\"%^&|<>!]/;", js)

    def test_the_panel_never_spawns(self):
        self.config(self.launcher())
        out = self.run_bridge(role="panel", seconds=65)
        self.assertEqual(out["spawns"], [])
        self.assertIsNone(out["beat"])
        self.assertEqual(out["panel"], {"role": "panel"})

    def test_a_live_engine_is_left_alone(self):
        self.config(self.launcher())
        self.engine(4242)
        out = self.run_bridge(seconds=95, alive=[4242])
        self.assertEqual(out["spawns"], [])
        self.assertEqual(out["beat"]["engine_start"]["outcome"], "running")

    # ---------------------------------------------------------------- spawn
    def test_a_missing_engine_json_spawns_exactly_once_with_the_exact_argv(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform):
                launcher = self.launcher(platform=platform)
                self.config(launcher)
                if self.engine_json.exists():
                    self.engine_json.unlink()
                stat = {} if platform == "win32" else {str(Path(os.path.realpath(launcher))): {"uid": 501,
                                                                                               "mode": 0o100755}}
                out = self.run_bridge(seconds=95, platform=platform, startEngine=31337, stat=stat,
                                      env={"ComSpec": "C:\\Windows\\System32\\cmd.exe"})
                (sp,) = out["spawns"]
                want = self.expected_spawn(launcher, platform)
                self.assertEqual((sp["file"], sp["args"], sp["opts"]), (want["file"], want["args"], want["opts"]))
                self.assertTrue(sp["unref"])
                self.assertEqual(sp["at"], out["start"])                     # at start, not 30 s later
                self.assertEqual(out["beat"]["engine_start"]["outcome"], "running")
                self.assertIn("spawned", out["log"])

    def test_a_dead_pid_is_restarted(self):
        self.config(self.launcher())
        self.engine(999999)                                                  # not alive
        out = self.run_bridge(seconds=5, startEngine=4343)
        self.assertEqual(len(out["spawns"]), 1)

    def test_a_comspec_that_is_not_cmd_exe_is_ignored(self):
        launcher = self.launcher(platform="win32")
        self.config(launcher)
        for comspec in ("C:\\evil\\evil.exe", "cmd.exe", ""):
            with self.subTest(comspec):
                out = self.run_bridge(seconds=1, platform="win32", startEngine=1, env={"ComSpec": comspec})
                self.assertEqual(out["spawns"][0]["file"], "C:\\Windows\\System32\\cmd.exe")

    def test_posix_owner_and_mode(self):
        launcher = self.launcher(platform="darwin")
        self.config(launcher)
        real = str(Path(os.path.realpath(launcher)))
        for name, st, want in (("another user", {"uid": 0, "mode": 0o100755}, "refused"),
                               ("group-writable", {"uid": 501, "mode": 0o100775}, "refused"),
                               ("world-writable", {"uid": 501, "mode": 0o100757}, "refused"),
                               ("owned, 0755", {"uid": 501, "mode": 0o100755}, "running")):
            with self.subTest(name):
                if self.engine_json.exists():
                    self.engine_json.unlink()
                out = self.run_bridge(seconds=35, platform="darwin", stat={real: st}, startEngine=77)
                self.assertEqual(out["beat"]["engine_start"]["outcome"], want)
                self.assertEqual(len(out["spawns"]), 0 if want == "refused" else 1)

    # ---------------------------------------------------------------- limits
    def test_one_attempt_per_30_s_and_it_stops_after_5_failures(self):
        self.config(self.launcher())
        for mode in ("ok", "error", "exit1", "throw"):             # ok = the launcher ran but no engine came up
            with self.subTest(mode):
                out = self.run_bridge(seconds=400, spawn=mode)
                at = [s["at"] - out["start"] for s in out["spawns"]]
                self.assertEqual(at, [0, 30000, 60000, 90000, 120000])
                self.assertEqual(out["beat"]["engine_start"]["outcome"], "gave_up")
                self.assertEqual(out["beat"]["engine_start"]["reason"], "gave_up")
                self.assertEqual(out["outcomes"][-1], "gave_up")
                self.assertIn("gave_up", out["log"])

    def test_a_success_resets_the_failures(self):
        """Two failures, the third attempt starts the engine, it dies at 100 s: five fresh attempts follow."""
        self.config(self.launcher())
        out = self.run_bridge(seconds=400, startEngine=5150, startOnSpawn=3, dieAt=100)
        at = [s["at"] - out["start"] for s in out["spawns"]]
        self.assertEqual(at, [0, 30000, 60000, 120000, 150000, 180000, 210000, 240000])
        self.assertIn("running", out["outcomes"])
        self.assertEqual(out["beat"]["engine_start"]["outcome"], "gave_up")

    def test_the_token_never_appears(self):
        """engine.json is read for its pid only: not in the heartbeat, the log, the queue, the state or a spawn."""
        self.config(self.launcher())
        for raw in (None, '{"token": "%s", "pid": 4242' % TOKEN, '{"token": "%s"}' % TOKEN,
                    '{"pid": "4242", "token": "%s"}' % TOKEN):
            with self.subTest(raw=raw and raw[:12]):
                self.engine(4242, raw)
                out = self.run_bridge(seconds=35, alive=[4242], startEngine=4242)   # run_bridge checks the token
                self.assertNotIn(TOKEN[:16], json.dumps(out["queueFiles"]))
                if raw is None:
                    self.assertEqual(out["spawns"], [])
                else:                                                        # unreadable pid: counted as not running
                    self.assertEqual(len(out["spawns"]), 1)

    @unittest.skipUnless(os.name == "nt", "the real cmd.exe quoting is a Windows check")
    def test_the_real_cmd_runs_a_launcher_in_a_folder_with_spaces(self):
        """The argv above, through the real child_process and cmd.exe: the quoted path survives a space."""
        import time
        launcher = self.launcher()
        marker = self.home / "started.txt"
        launcher.write_text('@echo off\r\necho started> "%~dp0..\\started.txt"\r\n', encoding="utf-8")
        self.config(launcher)
        self.run_bridge(seconds=0, realSpawn=True)
        deadline = time.time() + 20
        while not marker.exists() and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(marker.exists(), "the launcher did not run")
        self.assertEqual(marker.read_text(encoding="utf-8").strip(), "started")


def _ui_strings() -> list:
    """Every string an editor can see in the After Effects panel: the text of ui/**/*.html and every string literal of
    ui/**/*.js (comments removed)."""
    out = []
    for f in sorted((SRC / "ui").rglob("*")):
        if f.suffix == ".html":
            html = re.sub(r"<!--.*?-->|<style>.*?</style>|<script.*?</script>", " ", f.read_text(encoding="utf-8"),
                          flags=re.S)
            out += [t for t in (s.strip() for s in re.split(r"<[^>]+>", html)) if t]
        elif f.suffix == ".js":
            js = re.sub(r"/\*.*?\*/|//[^\n]*", " ", f.read_text(encoding="utf-8"), flags=re.S)
            out += [m.group(2) for m in re.finditer(r"(['\"`])((?:(?!\1)[^\\]|\\.)*)\1", js)]
    return out


class TestPanelStates(unittest.TestCase):
    """The After Effects panel: one sentence per state, Copy diagnostics, brand tokens, no command (C2.2)."""

    def test_one_sentence_per_state_and_copy_diagnostics(self):
        js = (SRC / "ui" / "js" / "panel.js").read_text(encoding="utf-8")
        for sentence in ("'WhyNot Cut is running in ' + app + '.'", "'WhyNot Cut is working in ' + app + '.'",
                         "'Starting WhyNot Cut…'", "'WhyNot Cut isn’t running in ' + app + ': restart ' + app"):
            self.assertIn(sentence, js)
        html = (SRC / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<button id="copy" type="button">Copy diagnostics</button>', html)
        self.assertIn("'Copy diagnostics'", js)

    def test_the_panel_uses_the_brand_tokens_only(self):
        html = (SRC / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="tokens.css">', html)
        style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", style), [])   # every colour is a token
        used = set(re.findall(r"var\((--twn-[\w-]+)\)", style))
        defined = set(re.findall(r"(--twn-[\w-]+):", BRAND_TOKENS.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertEqual(used - defined, set())

    @unittest.skipUnless(NODE, "needs node to run the panel's own command detector (adobe/panel-ui/src/commands.ts)")
    def test_ui_shows_no_command(self):
        """Every ui/** string through the SAME detector the panel kit uses, plus the Task 4 word list."""
        import subprocess
        strings = _ui_strings()
        self.assertIn("Copy diagnostics", strings)
        self.assertGreater(len(strings), 10)
        probe = ("import {commandIn} from %s; const xs = JSON.parse(process.argv[1]);"
                 "console.log(JSON.stringify(xs.map((x) => commandIn(x))));"
                 % json.dumps((SK.parent / "adobe" / "panel-ui" / "src" / "commands.ts").as_uri()))
        r = subprocess.run([NODE, "--input-type=module", "-e", probe, json.dumps(strings)], capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        hits = [(s, rule) for s, rule in zip(strings, json.loads(r.stdout)) if rule]
        self.assertEqual(hits, [])
        r = subprocess.run([NODE, "--input-type=module", "-e", probe, json.dumps(["run reel doctor", "claude -p x"])],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertTrue(all(json.loads(r.stdout)), r.stdout)                 # the detector is live
        for s in strings:
            for bad in ("Bridge", "reel ", "`", "Claude Code", "--", "whynotcut://"):
                self.assertNotIn(bad, s, s)


if __name__ == "__main__":
    unittest.main()
