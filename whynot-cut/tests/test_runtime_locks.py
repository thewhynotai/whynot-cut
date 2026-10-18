# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 T4.12 (G-LOCKS): runtime locks per hardware class (torch + torchaudio 2.8: cuda / mps / cpu), one CUDA
library set through torch\\lib, `setup_env.py --runtime base|full --class`, and the TLS rules (the OS trust store via
truststore, verification always on; uv with --system-certs).
No test downloads anything: builds use fake runners; the TLS test uses a loopback server with a throwaway CA.
Case list: the lane's work/t412/cases.md.
Run:  bash tools/test.sh -p test_runtime_locks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
for p in (SK / "engine" / "reel", SK / "setup"):
    if str(p) not in _sys.path:
        _sys.path.insert(0, str(p))

from lib import runtime as R  # noqa: E402

LOCKS = SK / "setup" / "locks"
CLASS_LOCKS = ("runtime-cuda.txt", "runtime-mps.txt", "runtime-cpu.txt")


def text(name):
    return (LOCKS / name).read_text(encoding="utf-8")


def head(name):
    return "\n".join(text(name).splitlines()[:6])


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


# --------------------------------------------------------------------------- classes and entries
class TestClasses(unittest.TestCase):
    def test_hardware_class(self):
        self.assertEqual(R.hardware_class("win-x64", nvidia=True), "cuda")
        self.assertEqual(R.hardware_class("win-x64", nvidia=False), "cpu")
        self.assertEqual(R.hardware_class("mac-arm64", nvidia=False), "mps")
        self.assertEqual(R.hardware_class("mac-arm64", nvidia=True), "mps")
        self.assertIsNone(R.hardware_class("mac-x64", nvidia=False))
        self.assertIsNone(R.hardware_class("linux-x64", nvidia=True))
        self.assertIsNone(R.hardware_class(None, nvidia=True))

    def test_lock_entry_class_path_and_pending_fallback(self):
        comp = {"runtime": {"locks": {"win-x64": {"file": "setup/locks/runtime-win-x64.lock", "id": "<release>"},
                                      "cuda": {"path": "setup/locks/runtime-cuda.txt", "size_gb": 3.1},
                                      "cpu": {"path": "<pending>", "size_gb": "<pending>"}}}}
        e = R.lock_entry("win-x64", comp, SK, klass="cuda")
        self.assertEqual(e["file"], SK / "setup/locks/runtime-cuda.txt")
        self.assertEqual(e["klass"], "cuda")
        for k in ("cpu", "mps", None, "bogus"):                       # placeholder / missing -> the platform lock
            e = R.lock_entry("win-x64", comp, SK, klass=k)
            self.assertEqual(e["file"], SK / "setup/locks/runtime-win-x64.lock", k)
            self.assertIsNone(e["klass"], k)
        self.assertEqual(set(R.lock_entry("win-x64", comp, SK)), {"file", "declared_id", "klass"})
        e = R.lock_entry("win-x64", {"runtime": {"locks": {"cuda": {"path": "../../etc/passwd"}}}}, SK, klass="cuda")
        self.assertEqual(e["file"], SK / "setup/locks/runtime-win-x64.lock")    # never outside the plugin

    def test_parse_lock_ignores_index_lines(self):
        lock = R.parse_lock("--index-url https://pypi.org/simple\n--extra-index-url https://download.pytorch.org/whl/cu128\n"
                            "torch==2.8.0+cu128 \\\n    --hash=sha256:" + "a" * 64 + "\n")
        self.assertEqual(lock["torch"]["version"], "2.8.0+cu128")

    def test_corrupt_lock_refused(self):
        for bad in ("torch>=2.8\n", "torch==2.8.0\n", "garbage line here\n"):
            with self.assertRaises(ValueError):
                R.parse_lock(bad)


# --------------------------------------------------------------------------- the shipped class locks
class TestClassLocks(unittest.TestCase):
    def test_class_locks_pinned_hashed_and_headed(self):
        for f in CLASS_LOCKS:
            reqs = R.parse_lock(text(f))
            self.assertTrue(all(r["version"] and r["hashes"] for r in reqs.values()), f)
            self.assertIn("uv pip compile", head(f), f)
            self.assertIn("--generate-hashes", head(f), f)
            self.assertIn("setup/requirements-torch.in", head(f), f)
            self.assertNotIn("\r", text(f), f)

    def test_torch_and_torchaudio_2_8(self):
        for f in CLASS_LOCKS:
            lock = R.parse_lock(text(f))
            for n in ("torch", "torchaudio"):
                self.assertTrue(lock[n]["version"].startswith("2.8."), (f, n, lock[n]["version"]))
                self.assertEqual(lock[n]["version"].endswith("+cu128"), f == "runtime-cuda.txt", (f, n))

    def test_cuda_lock_index_lines(self):
        idx = [ln for ln in text("runtime-cuda.txt").splitlines() if ln.startswith("--")]
        self.assertEqual(idx, ["--index-url https://pypi.org/simple",
                               "--extra-index-url https://download.pytorch.org/whl/cu128"])
        for f in ("runtime-mps.txt", "runtime-cpu.txt"):
            self.assertFalse([ln for ln in text(f).splitlines() if "download.pytorch.org" in ln], f)

    def test_index_order_mistake_is_caught(self):
        """A torch from PyPI in the cuda lock (the reversed index order) has no +cu128 and PyPI's hashes."""
        lock = R.parse_lock(text("runtime-cuda.txt"))
        self.assertTrue(lock["torch"]["version"].endswith("+cu128"))
        cpu = R.parse_lock(text("runtime-cpu.txt"))
        self.assertFalse(set(lock["torch"]["hashes"]) & set(cpu["torch"]["hashes"]))

    def test_cuda_lock_has_no_nvidia_wheels(self):
        self.assertFalse([n for n in R.parse_lock(text("runtime-cuda.txt")) if n.startswith("nvidia-")])

    def test_class_locks_keep_the_engine_packages(self):
        base = R.parse_lock((LOCKS / "runtime-win-x64.lock").read_text(encoding="utf-8"))
        for f in CLASS_LOCKS:
            lock = R.parse_lock(text(f))
            for n in ("faster-whisper", "ctranslate2", "av", "numpy", "pillow", "uharfbuzz", "huggingface-hub",
                      "truststore"):
                self.assertIn(n, lock, (f, n))
            self.assertEqual(lock["faster-whisper"]["version"], base["faster-whisper"]["version"])
            if f != "runtime-mps.txt":
                self.assertIn("opencv-python-headless", lock)
            else:
                self.assertIn("pyobjc-framework-coretext", lock)

    def test_torch_in_file(self):
        t = (SK / "setup" / "requirements-torch.in").read_text(encoding="utf-8")
        self.assertIn("-r requirements.txt", t)
        self.assertIn("torch==2.8.*", t)
        self.assertIn("torchaudio==2.8.*", t)
        req = (SK / "setup" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("runtime-cuda.txt", req)                        # the header says how to recompile them
        self.assertRegex(req, r"(?m)^truststore[><=]")


# --------------------------------------------------------------------------- one CUDA set, the doctor
class TestCudaLibs(unittest.TestCase):
    def test_cuda_lib_dirs_includes_torch_lib(self):
        from lib import plat
        sp = Path(tempfile.mkdtemp())
        tl = sp / "torch" / "lib"
        tl.mkdir(parents=True)
        (tl / ("cublas64_12.dll" if plat.IS_WIN else "libcublas.so.12")).write_bytes(b"x")
        with mock.patch.object(_sys, "path", [str(sp)] + _sys.path):
            self.assertIn(tl, plat.cuda_lib_dirs())
        shutil.rmtree(sp)
        empty = Path(tempfile.mkdtemp())
        (empty / "torch" / "lib").mkdir(parents=True)                   # torch without cuBLAS (the cpu build)
        with mock.patch.object(_sys, "path", [str(empty)] + _sys.path):
            self.assertNotIn(empty / "torch" / "lib", plat.cuda_lib_dirs())


# --------------------------------------------------------------------------- setup_env
class TestSetup(unittest.TestCase):
    def setUp(self):
        import setup_env as SE
        self.SE = SE
        self.home = Path(tempfile.mkdtemp(prefix="whynot-t412-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def builds(self, argv, key="win-x64", nvidia=True, fail_cuda=False):
        calls = []

        def fake_build(home, **kw):
            calls.append(kw["lock_file"].name)
            if fail_cuda and kw["lock_file"].name == "runtime-cuda.txt":
                raise self.SE.Failed("cuda wheels failed")
            return {"id": "r-x", "action": "create"}
        out = io.StringIO()
        with mock.patch.object(self.SE, "build", side_effect=fake_build), \
                mock.patch.object(self.SE.R, "platform_key", return_value=key), \
                mock.patch.object(self.SE, "nvidia_present", return_value=nvidia), \
                mock.patch.object(self.SE, "find_uv", return_value=(Path("C:/uv.exe"), None)), \
                mock.patch.object(self.SE.plat, "engine_runtime", return_value={"kind": "runtime", "id": "r-x",
                                                                                "python": None}), \
                mock.patch.object(self.SE.plat, "adobe_report", return_value={"all": []}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.SE.main(["--home", str(self.home), *argv])
        return calls, out.getvalue()

    def test_setup_default_is_base(self):
        calls, _ = self.builds([])
        self.assertEqual(calls, ["runtime-win-x64.lock"])

    def test_full_picks_the_class(self):
        self.assertEqual(self.builds(["--runtime", "full"])[0], ["runtime-cuda.txt"])
        self.assertEqual(self.builds(["--runtime", "full"], nvidia=False)[0], ["runtime-cpu.txt"])
        self.assertEqual(self.builds(["--runtime", "full"], key="mac-arm64")[0], ["runtime-mps.txt"])
        self.assertEqual(self.builds(["--runtime", "full", "--class", "cpu"])[0], ["runtime-cpu.txt"])

    def test_setup_full_cuda_failure_falls_back_to_cpu_lock(self):
        calls, out = self.builds(["--runtime", "full"], fail_cuda=True)
        self.assertEqual(calls, ["runtime-cuda.txt", "runtime-cpu.txt"])
        self.assertIn("installing the processor version instead", out)
        self.assertIn("المعالج", out)

    def test_setup_full_on_intel_mac_uses_base_lock_with_note(self):
        calls, out = self.builds(["--runtime", "full"], key="mac-x64", nvidia=False)
        self.assertEqual(calls, ["runtime-mac-x64.lock"])
        self.assertIn("Intel", out)

    def test_nvidia_detection(self):
        ok = subprocess.CompletedProcess([], 0, "GPU 0: NVIDIA GeForce RTX 4060 Laptop GPU (UUID: x)\n", "")
        self.assertTrue(self.SE.nvidia_present(runner=lambda *a, **k: ok, smi="C:/Windows/System32/nvidia-smi.exe"))
        self.assertFalse(self.SE.nvidia_present(runner=lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""),
                                                smi="C:/x/nvidia-smi.exe"))
        self.assertFalse(self.SE.nvidia_present(runner=lambda *a, **k: subprocess.CompletedProcess([], 9, "GPU 0", ""),
                                                smi="C:/x/nvidia-smi.exe"))

        def slow(*a, **k):
            raise subprocess.TimeoutExpired("nvidia-smi", 10)
        self.assertFalse(self.SE.nvidia_present(runner=slow, smi="C:/x/nvidia-smi.exe"))       # a hang -> cpu
        self.assertFalse(self.SE.nvidia_present(runner=lambda *a, **k: ok, smi=None))          # none -> cpu
        seen = {}
        self.SE.nvidia_present(runner=lambda cmd, **k: seen.update(cmd=cmd, timeout=k.get("timeout")) or ok,
                               smi="C:/Windows/System32/nvidia-smi.exe")
        self.assertEqual((seen["cmd"][1:], seen["timeout"]), (["-L"], 10))

    def test_uv_env_uses_the_system_certificates(self):
        env = self.SE.uv_env(self.home)
        self.assertEqual(env.get("UV_SYSTEM_CERTS"), "1")
        self.assertNotIn("UV_INSECURE_HOST", env)

    def test_hash_mismatch_is_refused_by_the_installer_command(self):
        """build() always installs with --require-hashes (uv refuses a wheel whose hash is not in the lock)."""
        seen = []

        def runner(cmd, env=None):
            seen.append([str(c) for c in cmd])
        with quiet():
            try:
                self.SE.build(self.home, comp={}, key="win-x64", lock_file=LOCKS / "runtime-cuda.txt", rid="r-t",
                              uv=Path("C:/uv.exe"), runner=runner, versions=lambda py: None, probe=lambda py: False,
                              smoke=[], prune=False)
            except Exception:  # noqa: BLE001  the fake runner builds nothing; only the commands matter here
                pass
        sync = [c for c in seen if "sync" in c]
        self.assertTrue(sync and "--require-hashes" in sync[0])


# --------------------------------------------------------------------------- TLS
class TestTls(unittest.TestCase):
    def test_trust_context_never_disables_verification(self):
        import ssl
        ctx = R.trust_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_loopback_self_signed_refused_and_accepted_through_a_temp_ca(self):
        """A local HTTPS server with a throwaway CA: refused with the default trust (verification on), accepted when
        the CA is in a temp trust store (cafile) — never by turning verification off."""
        import ssl
        import threading
        import urllib.request
        from http.server import BaseHTTPRequestHandler, HTTPServer
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        ca, cert, key = _make_ca(d)
        if not (cert.is_file() and key.is_file()):          # the J-T1 loopback fixture lands with Addendum J's commit
            self.skipTest("tests/fixtures/brand_web/tls is not committed yet (J-T1)")

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass
        srv = HTTPServer(("127.0.0.1", 0), H)
        sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sctx.load_cert_chain(cert, key)
        srv.socket = sctx.wrap_socket(srv.socket, server_side=True)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        url = f"https://localhost:{srv.server_address[1]}/"
        try:
            with self.assertRaises(Exception):
                urllib.request.urlopen(url, context=R.trust_context(), timeout=10)
            with urllib.request.urlopen(url, context=R.trust_context(cafile=str(ca)), timeout=10) as r:
                self.assertEqual(r.read(), b"ok")
        finally:
            srv.shutdown()
            srv.server_close()
            th.join(5)

    def test_truststore_branch_when_installed(self):
        import importlib.util
        import ssl
        if importlib.util.find_spec("truststore") is None:
            self.skipTest("truststore is not in this runtime yet (the base locks are recompiled by the executor)")
        import truststore
        ctx = R.trust_context()
        self.assertIsInstance(ctx, truststore.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_hf_factory_keeps_the_hubs_request_hook(self):
        made = {}

        def hook(request):
            return None

        class FakeHub:
            @staticmethod
            def set_client_factory(f):
                made["factory"] = f
        utils = type(_sys)("huggingface_hub.utils")
        http = type(_sys)("huggingface_hub.utils._http")
        http.hf_request_event_hook = hook
        with mock.patch.dict(_sys.modules, {"huggingface_hub": FakeHub, "huggingface_hub.utils": utils,
                                            "huggingface_hub.utils._http": http}):
            self.assertTrue(R.configure_downloads())
            client = made["factory"]()
        try:
            self.assertIn(hook, client.event_hooks["request"])               # HF_HUB_OFFLINE is still enforced
        finally:
            client.close()

    def test_hf_downloads_use_the_trust_context(self):
        made = {}

        class FakeHub:
            @staticmethod
            def set_client_factory(f):
                made["factory"] = f
        with mock.patch.dict(_sys.modules, {"huggingface_hub": FakeHub}):
            self.assertTrue(R.configure_downloads())
        client = made["factory"]()
        try:
            import ssl
            v = client._transport._pool._ssl_context            # httpx: the context the pool verifies with
            self.assertEqual(v.verify_mode, ssl.CERT_REQUIRED)
        finally:
            client.close()

    def test_source_never_turns_verification_off(self):
        for f in (SK / "engine" / "reel" / "lib" / "runtime.py", SK / "setup" / "setup_env.py"):
            src = f.read_text(encoding="utf-8")
            for bad in ("CERT_NONE", "check_hostname = False", "verify=False", "inject_into_ssl", "--allow-insecure"):
                self.assertNotIn(bad, src, (f.name, bad))


def _make_ca(d: Path):
    """The repo's loopback TLS fixture (a self-signed localhost certificate, J-T1): trusted nowhere but in the temp
    trust store the test hands to trust_context(cafile=)."""
    tls = SK / "tests" / "fixtures" / "brand_web" / "tls"
    return tls / "localhost-cert.pem", tls / "localhost-cert.pem", tls / "localhost-key.pem"

# --------------------------------------------------------------------------- full-suite findings (366b0de on the cuda runtime)
class TestClassRuntimeKept(unittest.TestCase):
    """A runtime built from a class lock is judged against THAT lock (doctor, isolation), and a later `reel setup`
    without --runtime keeps the class instead of silently going back to the base runtime."""

    def make(self, lock_name):
        home = Path(tempfile.mkdtemp(prefix="whynot-t412c-"))
        self.addCleanup(shutil.rmtree, home, True)
        lock = LOCKS / lock_name
        rid = R.runtime_id(lock.read_bytes())
        rt = R.runtime_dir(home, rid)
        (rt / "Scripts").mkdir(parents=True)
        (rt / "Scripts" / "python.exe").write_bytes(b"")
        (rt / "bin").mkdir()
        (rt / "bin" / "python").write_bytes(b"")
        R.write_stamps(rt, rid=rid, key="win-x64", python="3.12.15", lock_file=f"setup/locks/{lock_name}",
                       lock_sha=R.lock_sha256(lock.read_bytes()), by="test")
        R.write_current(home, rid)
        return home, rid

    def test_status_uses_the_class_lock_of_the_current_runtime(self):
        home, rid = self.make("runtime-cuda.txt")
        with mock.patch.object(R.plat, "engine_runtime", return_value={"kind": "runtime", "id": rid,
                                                                       "dir": R.runtime_dir(home, rid),
                                                                       "python": None}):
            st = R.status(home, "win-x64", {})
        self.assertEqual(Path(st["lock_file"]).name, "runtime-cuda.txt")
        self.assertEqual(st["klass"], "cuda")
        self.assertTrue(st["up_to_date"])
        self.assertEqual(R.current_class(home), "cuda")
        home2, _ = self.make("runtime-win-x64.lock")
        self.assertIsNone(R.current_class(home2))

    def test_setup_without_runtime_keeps_the_current_class(self):
        import setup_env as SE
        home, rid = self.make("runtime-cuda.txt")
        calls = []

        def fake_build(h, **kw):
            calls.append(kw["lock_file"].name)
            return {"id": rid, "action": "none"}
        for argv, want in (([], "runtime-cuda.txt"), (["--runtime", "base"], "runtime-win-x64.lock")):
            calls.clear()
            with mock.patch.object(SE, "build", side_effect=fake_build), \
                    mock.patch.object(SE.R, "platform_key", return_value="win-x64"), \
                    mock.patch.object(SE, "nvidia_present", return_value=True), \
                    mock.patch.object(SE, "find_uv", return_value=(Path("C:/uv.exe"), None)), \
                    mock.patch.object(SE.plat, "engine_runtime", return_value={"kind": "runtime", "id": rid,
                                                                                "python": None}), \
                    mock.patch.object(SE.plat, "adobe_report", return_value={"all": []}), quiet():
                SE.main(["--home", str(home), *argv])
            self.assertEqual(calls, [want], argv)


if __name__ == "__main__":
    unittest.main()
