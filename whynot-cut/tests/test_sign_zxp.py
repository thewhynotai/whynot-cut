"""tools/sign_zxp.py (3.0 T6.3 Task 6): ZXPSignCmd pinned by commit + size + sha256 (Windows x64; the macOS pin is
refused until it is set), `setup --from`, the self-signed certificate made once, its password only in the credential
store (never printed, logged, raised or shown in a command), `-tsa` on every signing with a failed timestamp failing
the build, the staging checks (no link, junction, .DS_Store or __MACOSX), the archive checks, and exactly one .zxp
left. Everything runs with fakes: a fake ZXPSignCmd runner, a fake credential store, a fake fetch, temp folders. No
download, no real ZXPSignCmd, no real credential write. Run:
    tools/test.sh -p test_sign_zxp.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import hashlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
if str(REPO / "tools") not in _sys.path:
    _sys.path.insert(0, str(REPO / "tools"))
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

import sign_zxp  # noqa: E402
from lib import cep_bundle  # noqa: E402

TOOL_BYTES = b"MZ fake ZXPSignCmd 4.1.3 for tests"
TEST_PIN = {"version": "test", "path": "ZXPSignCMD/test/ZXPSignCmd.exe", "file": "ZXPSignCmd.exe",
            "size": len(TOOL_BYTES), "sha256": hashlib.sha256(TOOL_BYTES).hexdigest()}
GOOD_VERIFY = "Signature verified successfully\nCertificate: CN=WhyNot Cut, O=The Why Not AI\nTimestamp: Valid\n"


class FakeStore:
    def __init__(self, secret=None):
        self.data = {} if secret is None else {sign_zxp.CRED_TARGET: secret}
        self.writes = 0

    def read(self, target):
        return self.data.get(target)

    def write(self, target, secret):
        self.writes += 1
        self.data[target] = secret


class FakeZXPSignCmd:
    """Records every argv. -selfSignedCert writes the .p12; -sign zips the staging folder with mimetype +
    META-INF/signatures.xml (or fails like an unreachable timestamp server, echoing its arguments); -verify prints
    `verify_out`. `echo` makes every answer quote the whole argv (the password included)."""

    def __init__(self, tsa_fail=False, verify_out=GOOD_VERIFY, extra=None, echo=False, write_zxp=True):
        self.calls, self.tsa_fail, self.verify_out, self.extra = [], tsa_fail, verify_out, extra or {}
        self.echo, self.write_zxp = echo, write_zxp

    def __call__(self, argv):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        said = (" ".join(argv) + "\n") if self.echo else ""
        op = argv[1]
        if op == "-selfSignedCert":
            Path(argv[7]).write_bytes(b"p12 for " + argv[4].encode())
            return 0, said + "Self-signed certificate generated successfully"
        if op == "-sign":
            if self.tsa_fail:
                return 1, said + f"Error: timestamp server {argv[7]} unreachable; args {' '.join(argv)}"
            if self.write_zxp:
                stage, out = Path(argv[2]), Path(argv[3])
                with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("mimetype", "application/vnd.adobe.air-ucf-package+zip")
                    for p in sorted(stage.rglob("*")):
                        if p.is_file():
                            zf.write(p, p.relative_to(stage).as_posix())
                    zf.writestr("META-INF/signatures.xml", "<signatures/>")
                    for name, data in self.extra.items():
                        zf.writestr(name, data)
            return 0, said + "Signed successfully"
        if op == "-verify":
            return 0, said + self.verify_out
        return 2, "unknown"

    def ops(self):
        return [c[1] for c in self.calls]


class _Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.sdir = self.tmp / "user" / ".whynot-cut" / "signing"
        self.out = self.tmp / "plugin" / "adobe"
        self.dl = self.tmp / "downloads"
        self.dl.mkdir()
        self.src = self.dl / "ZXPSignCmd.exe"
        self.src.write_bytes(TOOL_BYTES)
        self.logs = []
        p = mock.patch.dict(sign_zxp.PINS, {"test-x64": TEST_PIN})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self._t.cleanup()

    def log(self, m):
        self.logs.append(str(m))

    def setup_ok(self, store=None, runner=None):
        store, runner = store or FakeStore(), runner or FakeZXPSignCmd()
        r = sign_zxp.setup(src=self.src, home=self.sdir, runner=runner, store=store, key="test-x64", log=self.log)
        return r, store, runner

    def build(self, store, runner, **kw):
        return sign_zxp.build(home=self.sdir, out_dir=self.out, runner=runner, store=store, key="test-x64",
                              log=self.log, **kw)


class TestPin(_Base):
    def test_the_windows_x64_pin_is_the_controllers(self):
        pin = sign_zxp.PINS["windows-x64"]
        self.assertEqual((sign_zxp.PIN_REPO, sign_zxp.PIN_COMMIT), ("Adobe-CEP/CEP-Resources",
                                                                      "8897cfaf9801b0ad5321951199dd831a82964583"))
        self.assertEqual((pin["version"], pin["path"], pin["size"], pin["sha256"], pin["git_blob"]),
                         ("4.1.3", "ZXPSignCMD/4.1.3/x64/ZXPSignCmd.exe", 4542464,
                          "ffc2223167225ce61d024eb463fc5ad1a1be16133f99ef334a646f7311916c98",
                          "f5df2ed805e04a4d3c6adc722f602d4df6c762f7"))
        self.assertEqual(sign_zxp.pin_url(pin), "https://raw.githubusercontent.com/Adobe-CEP/CEP-Resources/"
                                                "8897cfaf9801b0ad5321951199dd831a82964583/ZXPSignCMD/4.1.3/x64/"
                                                "ZXPSignCmd.exe")
        self.assertNotIn("PIN_UNVERIFIED", (REPO / "tools" / "sign_zxp.py").read_text(encoding="utf-8"))

    def test_the_macos_pin_is_refused_not_guessed(self):
        self.assertIsNone(sign_zxp.PINS["macos"])
        for call in (lambda: sign_zxp.setup(src=self.src, home=self.sdir, store=FakeStore(), key="macos"),
                     lambda: sign_zxp.build(home=self.sdir, out_dir=self.out, store=FakeStore(), key="macos")):
            with self.assertRaises(sign_zxp.SignError) as cm:
                call()
            self.assertIn("macOS pin not set", cm.exception.error)
        self.assertFalse(self.sdir.exists())
        with self.assertRaises(sign_zxp.SignError):
            sign_zxp.pin_for("linux")

    def test_a_mismatch_from_a_local_file_is_refused_and_nothing_is_written(self):
        for data in (TOOL_BYTES + b"x", TOOL_BYTES[:-1] + b"?"):          # wrong size; same size, wrong sha256
            self.src.write_bytes(data)
            store, runner = FakeStore(), FakeZXPSignCmd()
            with self.assertRaises(sign_zxp.SignError) as cm:
                sign_zxp.setup(src=self.src, home=self.sdir, runner=runner, store=store, key="test-x64", log=self.log)
            self.assertIn("refused", cm.exception.error)
            self.assertFalse(self.sdir.exists())
            self.assertEqual((runner.calls, store.writes), ([], 0))

    def test_the_network_path_checks_the_same_pin_and_never_downloads_for_real(self):
        fetched = []

        def fetch(url, dest, data=b"tampered"):
            fetched.append(url)
            Path(dest).write_bytes(data)

        with self.assertRaises(sign_zxp.SignError):
            sign_zxp.setup(home=self.sdir, runner=FakeZXPSignCmd(), store=FakeStore(), fetch=fetch, key="test-x64",
                           log=self.log)
        self.assertFalse(self.sdir.exists())
        r = sign_zxp.setup(home=self.sdir, runner=FakeZXPSignCmd(), store=FakeStore(), key="test-x64", log=self.log,
                           fetch=lambda url, dest: fetch(url, dest, TOOL_BYTES))
        self.assertEqual(r["tool_state"], "installed")
        self.assertEqual(fetched, [sign_zxp.pin_url(TEST_PIN)] * 2)
        self.assertEqual((self.sdir / "ZXPSignCmd.exe").read_bytes(), TOOL_BYTES)

    def test_a_tool_changed_after_setup_is_refused(self):
        _, store, runner = self.setup_ok()
        (self.sdir / "ZXPSignCmd.exe").write_bytes(TOOL_BYTES[:-1] + b"!")
        with self.assertRaises(sign_zxp.SignError) as cm:
            self.build(store, runner)
        self.assertIn("not set up", cm.exception.error)
        self.assertNotIn("-sign", runner.ops())
        with self.assertRaises(sign_zxp.SignError):
            sign_zxp.verify(self.out / "x.zxp", home=self.sdir, runner=runner, key="test-x64")


class TestSetup(_Base):
    def test_the_certificate_is_made_once(self):
        r, store, runner = self.setup_ok()
        self.assertEqual((r["tool_state"], r["cert_state"]), ("installed", "made"))
        self.assertEqual((self.sdir / "ZXPSignCmd.exe").read_bytes(), TOOL_BYTES)
        (call,) = runner.calls
        secret = store.data[sign_zxp.CRED_TARGET]
        self.assertEqual(call, [str(self.sdir / "ZXPSignCmd.exe"), "-selfSignedCert", "EG", "Cairo", "The Why Not AI",
                                "WhyNot Cut", secret, str(self.sdir / "whynot-cut.p12"), "-validityDays", "3650"])
        self.assertGreaterEqual(len(secret), 43)
        cert = (self.sdir / "whynot-cut.p12").read_bytes()
        r2 = sign_zxp.setup(home=self.sdir, runner=runner, store=store, key="test-x64", log=self.log,
                            fetch=lambda *a: self.fail("the pinned tool in place is never fetched again"))
        self.assertEqual((r2["tool_state"], r2["cert_state"]), ("kept", "kept"))
        self.assertEqual(runner.ops(), ["-selfSignedCert"])
        self.assertEqual((self.sdir / "whynot-cut.p12").read_bytes(), cert)
        self.assertEqual((store.writes, store.data[sign_zxp.CRED_TARGET]), (1, secret))

    def test_a_certificate_without_its_password_is_refused_never_replaced(self):
        _, store, runner = self.setup_ok()
        cert = (self.sdir / "whynot-cut.p12").read_bytes()
        with self.assertRaises(sign_zxp.SignError) as cm:
            sign_zxp.setup(src=self.src, home=self.sdir, runner=runner, store=FakeStore(), key="test-x64",
                           log=self.log)
        self.assertIn("password is not in the credential store", cm.exception.error)
        self.assertEqual((self.sdir / "whynot-cut.p12").read_bytes(), cert)
        self.assertEqual(runner.ops(), ["-selfSignedCert"])

    def test_the_password_never_starts_with_a_dash(self):
        with mock.patch.object(sign_zxp.secrets, "token_urlsafe", side_effect=["-abc", "-def", "ghi"]):
            self.assertEqual(sign_zxp.new_password(), "ghi")

    def test_the_real_signing_folder_is_refused_in_the_test_sandbox(self):
        real = [Path(r) for r in sign_zxp.plat.live_roots() if Path(r).name == ".whynot-cut"][0] / "signing"
        with self.assertRaises(sign_zxp.SignError) as cm:
            sign_zxp.setup(src=self.src, home=real, runner=FakeZXPSignCmd(), store=FakeStore(), key="test-x64")
        self.assertIn("test sandbox", cm.exception.error)
        _, store, runner = self.setup_ok()
        with self.assertRaises(sign_zxp.SignError) as cm:                          # the repo's own adobe folder
            sign_zxp.build(home=self.sdir, out_dir=sign_zxp.OUT_DIR, runner=runner, store=store, key="test-x64")
        self.assertIn("test sandbox", cm.exception.error)
        self.assertEqual(runner.ops(), ["-selfSignedCert"])

    @unittest.skipUnless(os.name == "nt", "the Windows Credential Manager")
    def test_the_windows_credential_store_reads_a_missing_target_as_none(self):
        """Read-only: a target that does not exist (nothing is ever written to the real store in tests)."""
        self.assertIsNone(sign_zxp.WinCredStore().read("WhyNotCut/zxp-signing-test-does-not-exist-" + os.urandom(8).hex()))


class TestBuild(_Base):
    def ready(self, **kw):
        if not hasattr(self, "_store"):
            _, self._store, _ = self.setup_ok()
        return self._store, FakeZXPSignCmd(**kw)

    def test_signs_with_tsa_verifies_and_leaves_exactly_one_zxp(self):
        store, runner = self.ready()
        self.out.mkdir(parents=True)
        (self.out / "WhyNotCut-Bridge-2.9.0.zxp").write_bytes(b"old")
        (self.out / "stray.zxp").write_bytes(b"stray")
        (self.out / "WhyNotCut-Premiere-3.0.0.ccx").write_bytes(b"ccx")
        r = self.build(store, runner)
        final = self.out / "WhyNotCut-Bridge-3.0.0.zxp"
        self.assertEqual(r["zxp"], str(final))
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["WhyNotCut-Bridge-3.0.0.zxp", "WhyNotCut-Premiere-3.0.0.ccx"])   # one .zxp, no work folder
        self.assertEqual(sorted(r["removed"]), ["WhyNotCut-Bridge-2.9.0.zxp", "stray.zxp"])
        self.assertEqual(runner.ops(), ["-sign", "-verify"])
        sign, ver = runner.calls
        self.assertEqual(sign[1:2] + sign[4:], ["-sign", str(self.sdir / "whynot-cut.p12"),
                                                store.data[sign_zxp.CRED_TARGET], "-tsa", "http://timestamp.digicert.com"])
        self.assertEqual(Path(sign[2]).name, cep_bundle.EXT_ID)
        self.assertEqual(ver[1:], ["-verify", sign[3], "-certinfo"])
        with zipfile.ZipFile(final) as zf:
            names = set(zf.namelist())
        self.assertIn("META-INF/signatures.xml", names)
        self.assertIn("build.json", names)
        self.assertIn("jsx/wnc_ppro_lib.jsx", names)
        self.assertEqual(r["sha256"], hashlib.sha256(final.read_bytes()).hexdigest())
        v = sign_zxp.verify(final, home=self.sdir, runner=runner, key="test-x64", log=self.log)
        self.assertTrue(v["ok"])

    def test_tsa_is_always_passed(self):
        store, runner = self.ready()
        self.build(store, runner, tsa="https://tsa.example.test/ts")
        (sign,) = [c for c in runner.calls if c[1] == "-sign"]
        self.assertEqual(sign[-2:], ["-tsa", "https://tsa.example.test/ts"])
        for bad in ("", "ftp://x", "http://a b", None):
            with self.subTest(tsa=bad), self.assertRaises(sign_zxp.SignError):
                self.build(store, runner, tsa=bad)
        self.assertEqual(runner.ops().count("-sign"), 1)                       # a bad --tsa never reaches signing

    def test_a_failed_timestamp_fails_the_build_and_leaves_the_folder_as_it_was(self):
        store, runner = self.ready(tsa_fail=True)
        self.out.mkdir(parents=True)
        prev = self.out / "WhyNotCut-Bridge-3.0.0.zxp"
        prev.write_bytes(b"the previous good build")
        with self.assertRaises(sign_zxp.SignError) as cm:
            self.build(store, runner)
        self.assertIn("exit 1", cm.exception.error)
        self.assertIn("timestamp", cm.exception.error)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["WhyNotCut-Bridge-3.0.0.zxp"])
        self.assertEqual(prev.read_bytes(), b"the previous good build")

    def test_a_signature_without_a_valid_timestamp_fails_the_build(self):
        for out in ("Signature verified successfully\n",
                    "Signature verified successfully\nTimestamp: Not available\n",
                    "Signature verified successfully\nTimestamp: Invalid\n",
                    "Error: signature invalid\nTimestamp: Valid\n"):
            with self.subTest(out=out):
                store, runner = self.ready(verify_out=out)
                with self.assertRaises(sign_zxp.SignError):
                    self.build(store, runner)
                self.assertEqual(list(self.out.glob("*.zxp")), [])
                self.assertEqual([p.name for p in self.out.iterdir()], [])

    def test_an_archive_that_is_not_the_staged_bundle_is_refused(self):
        store, runner = self.ready(extra={"evil.js": "x"})
        with self.assertRaises(sign_zxp.SignError) as cm:
            self.build(store, runner)
        self.assertIn("evil.js", cm.exception.error)
        self.assertEqual(list(self.out.glob("*.zxp")), [])
        store, runner = self.ready(write_zxp=False)
        with self.assertRaises(sign_zxp.SignError):
            self.build(store, runner)

    def test_macos_metadata_in_the_staging_tree_is_refused(self):
        for name in (".DS_Store", "__MACOSX", "ui/.ds_store"):
            with self.subTest(name=name):
                def assemble(dst, name=name):
                    cep_bundle.assemble(dst)
                    p = dst / name
                    if name == "__MACOSX":
                        (p / "x").mkdir(parents=True)
                    else:
                        p.write_bytes(b"\0")
                    return dst
                store, runner = self.ready()
                with self.assertRaises(sign_zxp.SignError) as cm:
                    self.build(store, runner, assemble=assemble)
                self.assertIn("nothing was signed", cm.exception.error)
                self.assertEqual(runner.calls, [])
                self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    @unittest.skipUnless(os.name == "nt", "a Windows junction")
    def test_a_junction_in_the_staging_tree_is_refused(self):
        import _winapi
        target = self.tmp / "elsewhere"
        target.mkdir()
        (target / "f.js").write_text("x", encoding="utf-8")

        def assemble(dst):
            cep_bundle.assemble(dst)
            _winapi.CreateJunction(str(target), str(dst / "js" / "linked"))
            return dst
        store, runner = self.ready()
        with self.assertRaises(sign_zxp.SignError) as cm:
            self.build(store, runner, assemble=assemble)
        self.assertIn("js/linked", cm.exception.error)
        self.assertEqual(runner.calls, [])
        self.assertTrue((target / "f.js").is_file())                            # the junction was never followed

    def test_a_symlink_in_the_staging_tree_is_refused(self):
        def assemble(dst):
            cep_bundle.assemble(dst)
            try:
                os.symlink(dst / "js" / "bridge.js", dst / "js" / "alias.js")
            except (OSError, NotImplementedError) as e:
                raise unittest.SkipTest(f"no symlink here ({e})")
            return dst
        store, runner = self.ready()
        with self.assertRaises(sign_zxp.SignError) as cm:
            self.build(store, runner, assemble=assemble)
        self.assertIn("js/alias.js", cm.exception.error)
        self.assertEqual(runner.calls, [])

    def test_staging_problems(self):
        root = cep_bundle.assemble(self.tmp / "s" / cep_bundle.EXT_ID)
        self.assertEqual(sign_zxp.staging_problems(root), [])
        (root / "__MACOSX").mkdir()
        (root / "jsx" / ".DS_Store").write_bytes(b"")
        self.assertEqual(sign_zxp.staging_problems(root), ["__MACOSX", "jsx/.DS_Store"])


class TestThePasswordNeverAppears(_Base):
    def test_not_in_logs_output_errors_or_any_shown_command(self):
        store = FakeStore()
        runner = FakeZXPSignCmd(echo=True)                     # a tool that quotes its whole argv back
        sign_zxp.setup(src=self.src, home=self.sdir, runner=runner, store=store, key="test-x64", log=self.log)
        secret = store.data[sign_zxp.CRED_TARGET]
        r = self.build(store, runner)
        bad = FakeZXPSignCmd(tsa_fail=True, echo=True)
        with self.assertRaises(sign_zxp.SignError) as cm:
            self.build(store, bad)
        self.assertIn(secret, " ".join(runner.calls[1]))                       # the tool did get it ...
        seen = "\n".join(self.logs) + repr(r) + str(cm.exception) + cm.exception.error + cm.exception.how
        seen += repr(cm.exception.args) + repr(sign_zxp.shown(runner.calls[1], secret))
        self.assertNotIn(secret, seen)                                         # ... and nothing shows it
        self.assertIn("***", "\n".join(self.logs))
        self.assertTrue(any(line.startswith("$ ") and "-sign" in line for line in self.logs))
        self.assertNotIn(secret, " ".join(sign_zxp.shown(runner.calls[0], secret)))

    def test_not_on_stdout_or_stderr_of_the_cli(self):
        store = FakeStore()
        out, err = io.StringIO(), io.StringIO()
        patches = [mock.patch.object(sign_zxp, "default_store", lambda: store),
                   mock.patch.object(sign_zxp, "run_tool", FakeZXPSignCmd(echo=True)),
                   mock.patch.object(sign_zxp, "platform_key", lambda: "test-x64"),
                   mock.patch.object(sign_zxp, "signing_dir", lambda home=None: self.sdir),
                   mock.patch.object(sign_zxp, "OUT_DIR", self.out)]
        with contextlib.ExitStack() as st:
            for p in patches:
                st.enter_context(p)
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            codes = [sign_zxp.main(["setup", "--from", str(self.src)]), sign_zxp.main(["build"]),
                     sign_zxp.main(["verify"])]
            st.enter_context(mock.patch.object(sign_zxp, "run_tool", FakeZXPSignCmd(echo=True, tsa_fail=True)))
            codes.append(sign_zxp.main(["build"]))
        secret = store.data[sign_zxp.CRED_TARGET]
        self.assertEqual(codes, [0, 0, 0, 2])
        self.assertNotIn(secret, out.getvalue() + err.getvalue())
        self.assertIn("sign_zxp:", err.getvalue())
        self.assertEqual([p.name for p in self.out.glob("*.zxp")], ["WhyNotCut-Bridge-3.0.0.zxp"])


class TestArtefact(unittest.TestCase):
    """The ZXP is a build artefact of the plugin: git-ignored, shipped by package.py, the name release.py pins."""

    def test_the_name_is_the_bundle_product(self):
        self.assertEqual(sign_zxp.ZXP_NAME, "WhyNotCut-Bridge-3.0.0.zxp")
        self.assertEqual(cep_bundle.zxp_path(), SK / "adobe" / "WhyNotCut-Bridge-3.0.0.zxp")
        self.assertEqual(sign_zxp.OUT_DIR, SK / "adobe")

    def test_git_ignores_it(self):
        lines = (SK / "adobe" / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("*.zxp", lines)
        if shutil.which("git"):
            names = ["whynot-cut/adobe/WhyNotCut-Bridge-3.0.0.zxp", "whynot-cut/adobe/.wnc-zxp-123/x.zxp"]
            r = subprocess.run(["git", "-C", str(REPO), "check-ignore", *names], capture_output=True, text=True,
                               timeout=60)
            self.assertEqual((r.returncode, r.stdout.split()), (0, names), r.stderr)

    def test_package_py_ships_it(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("wnc_package", REPO / "package.py")
        pkg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pkg)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            zxp = root / "whynot-cut" / "adobe" / "WhyNotCut-Bridge-3.0.0.zxp"
            zxp.parent.mkdir(parents=True)
            zxp.write_bytes(b"PK")
            self.assertTrue(pkg.wanted(zxp, root))

    def test_the_docstring_names_the_rules(self):
        import ast
        doc = ast.get_docstring(ast.parse((REPO / "tools" / "sign_zxp.py").read_text(encoding="utf-8")))
        for needle in ("-tsa", "timestamp.digicert.com", "WhyNotCut/zxp-signing", "3650", "--from", "KnownIssue2024",
                       "exactly", "never printed", "Stdlib only", "macOS pin is not set"):
            self.assertIn(needle, doc)


if __name__ == "__main__":
    unittest.main()
