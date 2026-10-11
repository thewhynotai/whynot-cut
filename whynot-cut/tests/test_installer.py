"""3.0 Phase 7 (T7.1): the per-user installer core (installer/core/wnc_installer) and setup/components.json.

  * components.json: parses, schema 1, plugin version = .claude-plugin/plugin.json, only the three platform ids,
    every real sha256 is 64 lowercase hex, every real URL is https, and the placeholders ("<release>" / null) are
    exactly the allowed ones (a real pin can never silently turn back into a placeholder).
  * base.py: platform ids, the engine-home Paths (sandbox home with a space and Arabic letters), the downloader
    (local http.server and file://: sha256 verified, cache reused, bad file and stale .part removed, placeholder pins
    refused without a request, urllib fallback), safe extraction (member map, tar.gz, `..` refused), state.json
    (atomic, corrupt file set aside), run_steps (dependencies, an exception is `red` and later steps still run) and
    safe_rmtree (outside the root, client marker, protected paths, symlinks/junctions never followed).
  * cli.py / wnc_install.py: `plan` prints the 14 step names in order, also under `python -I`.
Never touches the real ~/.whynot-cut or ~/.claude: every Paths is a sandbox home in a temp folder, and no real
network is used (artefacts come from a 127.0.0.1 http.server started here, or file://).
Run (repo root):
    bash tools/test.sh -p test_installer.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import argparse
import hashlib
import http.server
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
CORE = SK / "installer" / "core"
sys.path.insert(0, str(CORE))

from wnc_installer import base, cli  # noqa: E402

IS_WIN = os.name == "nt"
COMPONENTS = SK / "setup" / "components.json"
ARABIC_HOME = "محمد علي"
STEP_NAMES = ["preflight", "questions", "runtime", "ffmpeg", "gitbash", "gpu", "claude", "adobe", "fonts",
              "settings", "model", "state", "doctor", "launch"]
PLATFORMS = {"win-x64", "mac-arm64", "mac-x64"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Every dotted path in components.json that may hold a placeholder today. The release tool fills them; a pin that is
# real today must never come back as a placeholder, so anything outside this list fails the test.
ALLOWED_PLACEHOLDERS = {
    "marketplace.url",
    "release.index_url",
    "runtime.index_url",
    "runtime.locks.win-x64.id", "runtime.locks.mac-arm64.id", "runtime.locks.mac-x64.id",
    "bridge.cep.bundle", "bridge.cep.zxp", "bridge.cep.sha256",
    "bridge.uxp.version", "bridge.uxp.ccx", "bridge.uxp.sha256", "bridge.uxp.id",
    "models.large-v3.revision", "models.large-v3-turbo.revision", "models.large-v3-mlx.revision",
}


def leaves(obj, prefix=""):
    """(dotted path, value) for every scalar in a JSON tree; list items are addressed by index."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{prefix}.{i}")
    else:
        yield prefix, obj


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Quiet(base.Log):
    """A Log that only writes its file (keeps the test output clean)."""

    def __init__(self, path=None, dry_run=False):
        super().__init__(path, dry_run, console=False)


# --------------------------------------------------------------------------------------------- components.json
class TestComponents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = base.load_components(COMPONENTS)

    def test_parses_with_schema_1_and_the_plugin_version(self):
        self.assertEqual(self.c["schema"], 1)
        manifest = json.loads((SK / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(self.c["plugin"], manifest["version"])
        self.assertEqual(self.c["channel"], "stable")
        self.assertEqual(base.cget(self.c, "claude_code.min"), "2.1.224")

    def test_only_the_three_platforms(self):
        for section in ("uv.assets", "runtime.locks", "ffmpeg.assets"):
            self.assertEqual(set(base.cget(self.c, section)), PLATFORMS, section)
        self.assertLessEqual(set(base.cget(self.c, "git.assets")), PLATFORMS)
        for plat in PLATFORMS:
            self.assertEqual(base.cget(self.c, f"runtime.locks.{plat}.file"), f"setup/locks/runtime-{plat}.lock")

    def test_real_sha256_are_64_lowercase_hex(self):
        n = 0
        for path, v in leaves(self.c):
            if path.split(".")[-1] == "sha256" and not base.is_placeholder(v):
                self.assertRegex(v, HEX64, path)
                n += 1
        self.assertGreater(n, 20)  # uv x3, ffmpeg x5, git, 15 fonts, 4 licences

    def test_real_urls_are_https(self):
        for path, v in leaves(self.c):
            key = path.split(".")[-1]
            if (key in ("url", "source") or key.endswith("_url")) and not base.is_placeholder(v):
                self.assertTrue(isinstance(v, str) and v.startswith("https://"), f"{path} = {v!r}")
            if isinstance(v, str) and "://" in v:
                self.assertTrue(v.startswith("https://"), f"{path} = {v!r}")

    def test_placeholders_are_only_the_allowed_ones(self):
        found = {path for path, v in leaves(self.c) if base.is_placeholder(v)}
        self.assertLessEqual(found, ALLOWED_PLACEHOLDERS, sorted(found - ALLOWED_PLACEHOLDERS))
        for path, v in leaves(self.c):
            if isinstance(v, str) and v.startswith("<"):
                self.assertEqual(v, base.PLACEHOLDER, path)  # exactly "<release>", never a variant

    def test_pins_and_fixed_values(self):
        g = lambda d: base.cget(self.c, d)  # noqa: E731
        self.assertEqual(g("bridge.uxp.min_host"), "26.5.0")
        self.assertEqual((g("bridge.protocol"), g("bridge.min_protocol")), (4, 4))
        self.assertEqual(g("uv.version"), "0.13.0")
        self.assertEqual(g("runtime.python"), "3.12.15")
        self.assertEqual(g("ffmpeg.license"), "GPL-3.0-or-later")
        self.assertEqual(g("git.assets.win-x64.archive"), "7z-sfx")
        self.assertIn("PortableGit", g("git.assets.win-x64.url"))
        self.assertEqual(g("models.by_hardware"), {"nvidia": "large-v3", "apple_silicon": "large-v3",
                                                   "cpu": "large-v3-turbo"})
        self.assertEqual(g("runtime.smoke"), ["faster_whisper", "ctranslate2", "av", "numpy", "PIL", "uharfbuzz"])

    def test_ffmpeg_assets_name_both_binaries(self):
        for plat in PLATFORMS:
            exe = ".exe" if plat.startswith("win") else ""
            outs = []
            for f in base.cget(self.c, f"ffmpeg.assets.{plat}.files"):
                self.assertEqual(f["archive"], "zip")
                outs += list(f["members"].values())
            self.assertEqual(sorted(outs), [f"ffmpeg{exe}", f"ffprobe{exe}"], plat)

    def test_fonts_have_a_licence_per_family(self):
        fams = {f["family"] for f in base.cget(self.c, "fonts.files")}
        self.assertEqual(fams, {x["family"] for x in base.cget(self.c, "fonts.licenses")})
        self.assertEqual(base.cget(self.c, "fonts.version"), "1")

    def test_cget(self):
        self.assertIsNone(base.cget(self.c, "no.such.key"))
        self.assertEqual(base.cget(self.c, "no.such.key", 7), 7)
        self.assertEqual(base.cget(self.c, "fonts.files.0.family"), "Syne")


# --------------------------------------------------------------------------------------------- platform / paths
class TestPlatformId(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(base.platform_id("Windows", "AMD64"), "win-x64")
        self.assertEqual(base.platform_id("Darwin", "arm64"), "mac-arm64")
        self.assertEqual(base.platform_id("Darwin", "x86_64"), "mac-x64")
        with self.assertRaises(base.Unsupported):
            base.platform_id("Linux", "x86_64")

    def test_test_platform_only_in_the_sandbox(self):
        env = {"WNC_TEST_PLATFORM": "mac-arm64"}
        self.assertEqual(base.platform_id("Windows", "AMD64", sandbox=True, env=env), "mac-arm64")
        self.assertEqual(base.platform_id("Windows", "AMD64", sandbox=False, env=env), "win-x64")
        with self.assertRaises(base.Unsupported):
            base.platform_id("Windows", "AMD64", sandbox=True, env={"WNC_TEST_PLATFORM": "linux-x64"})

    def test_this_machine(self):
        if IS_WIN or sys.platform == "darwin":
            self.assertIn(base.platform_id(), PLATFORMS)


class TestPaths(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_sandbox_home_with_arabic_and_space(self):
        home = self.tmp / ARABIC_HOME
        outside = {"WHYNOT_HOME": str(self.tmp / "real-engine"), "CLAUDE_CONFIG_DIR": str(self.tmp / "real-claude")}
        p = base.Paths.from_env(str(home), env=outside)
        self.assertTrue(p.sandbox)
        self.assertEqual(p.home, home)
        self.assertEqual(p.whynot, home / ".whynot-cut")
        self.assertEqual(p.claude_dir, home / ".claude")
        self.assertEqual(p.settings_file, home / ".claude" / "settings.json")
        self.assertEqual(p.sandbox_dir, home / ".wnc-sandbox")
        self.assertEqual(p.state_file, home / ".whynot-cut" / "state.json")
        self.assertEqual(p.current_file, home / ".whynot-cut" / "current")
        for prop in ("bin_dir", "python_dir", "runtimes_dir", "ffmpeg_dir", "models_dir", "logs_dir", "cache_dir",
                     "downloads_dir", "fonts_dir", "marketplace_dir", "bridge_dir"):
            self.assertEqual(getattr(p, prop).parent, p.whynot, prop)
        env = p.child_env({"PATH": "keep-me", **outside})
        self.assertEqual(env["USERPROFILE"], str(home))
        self.assertEqual(env["HOME"], str(home))
        for k in ("APPDATA", "LOCALAPPDATA"):
            self.assertTrue(Path(env[k]).is_relative_to(home), k)
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], str(home / ".claude"))
        self.assertEqual(env["WHYNOT_HOME"], str(p.whynot))
        self.assertEqual(env["UV_PYTHON_INSTALL_DIR"], str(p.python_dir))
        self.assertTrue(Path(env["UV_CACHE_DIR"]).is_relative_to(p.cache_dir))
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["PATH"], "keep-me")
        self.assertFalse(home.exists())  # computing paths creates nothing

    def test_outside_the_sandbox_the_environment_wins(self):
        home = self.tmp / "user"
        env = {"HOME": str(home), "USERPROFILE": str(home), "WHYNOT_HOME": str(self.tmp / "engine"),
               "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg"), "APPDATA": str(self.tmp / "ad")}
        p = base.Paths.from_env(None, env=env)
        self.assertFalse(p.sandbox)
        self.assertEqual(p.whynot, self.tmp / "engine")
        self.assertEqual(p.claude_dir, self.tmp / "cfg")
        ce = p.child_env({"USERPROFILE": "untouched"})
        self.assertEqual(ce["USERPROFILE"], "untouched")
        self.assertEqual(ce["WHYNOT_HOME"], str(self.tmp / "engine"))
        p2 = base.Paths.from_env(None, env={"HOME": str(home), "USERPROFILE": str(home)})
        self.assertEqual(p2.whynot, home / ".whynot-cut")
        self.assertEqual(p2.claude_dir, home / ".claude")


# --------------------------------------------------------------------------------------------- files / log
class TestFiles(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name) / ARABIC_HOME

    def tearDown(self):
        self._td.cleanup()

    def test_atomic_write_json(self):
        f = self.tmp / "a" / "x.json"
        base.atomic_write_json(f, {"name": "عيادة", "n": 1})
        text = f.read_text(encoding="utf-8")
        self.assertIn("عيادة", text)
        self.assertTrue(text.endswith("}\n"))
        self.assertIn('\n  "n": 1', text)
        base.atomic_write_text(f, "r-abc\n")
        self.assertEqual(f.read_bytes(), b"r-abc\n")
        self.assertEqual([x.name for x in f.parent.iterdir()], ["x.json"])

    def test_log_file_utf8_with_iso_time(self):
        f = self.tmp / "logs" / "install-20261012-101010.log"
        log = Quiet(f)
        log.step("runtime")
        log.info("home " + ARABIC_HOME)
        log.warn("careful")
        log.error("broken")
        lines = f.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 4)
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
        self.assertIn(ARABIC_HOME, lines[1])
        self.assertIn("WARN", lines[2])
        self.assertIn("ERROR", lines[3])

    def test_dry_run_log_writes_no_file(self):
        f = self.tmp / "logs" / "x.log"
        Quiet(f, dry_run=True).info("nothing on disk")
        self.assertFalse(f.exists())


# --------------------------------------------------------------------------------------------- download
class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        srv = self.server
        srv.hits.append(self.path)
        body = srv.files.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestDownload(unittest.TestCase):
    BODY = b"pinned artefact " * 1000

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name) / ARABIC_HOME
        self.dl = self.tmp / ".whynot-cut" / "downloads"
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.srv.hits, self.srv.files = [], {"/a/tool.zip": self.BODY, "/a/Syne%5Bwght%5D.ttf": b"font"}
        self.thread = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/a/tool.zip"
        self.log = Quiet()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(5)
        self._td.cleanup()

    def test_good_sha_gives_the_file(self):
        out = base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual(out, self.dl / "tool.zip")
        self.assertEqual(out.read_bytes(), self.BODY)
        self.assertEqual([x.name for x in self.dl.iterdir()], ["tool.zip"])

    def test_name_comes_from_the_unquoted_url_or_the_argument(self):
        u = self.url.replace("tool.zip", "Syne%5Bwght%5D.ttf")
        self.assertEqual(base.download(u, sha(b"font"), self.dl, self.log).name, "Syne[wght].ttf")
        self.assertEqual(base.download(self.url, sha(self.BODY), self.dl, self.log, name="uv.zip").name, "uv.zip")

    def test_cached_file_is_reused(self):
        base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual(len(self.srv.hits), 1)
        out = base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual(len(self.srv.hits), 1)
        self.assertEqual(out.read_bytes(), self.BODY)

    def test_cached_file_with_the_wrong_hash_is_fetched_again(self):
        self.dl.mkdir(parents=True)
        (self.dl / "tool.zip").write_bytes(b"tampered")
        out = base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual(out.read_bytes(), self.BODY)
        self.assertEqual(len(self.srv.hits), 1)

    def test_bad_sha_leaves_nothing(self):
        with self.assertRaises(base.DownloadError) as cm:
            base.download(self.url, "0" * 64, self.dl, self.log)
        self.assertIn("sha256", str(cm.exception))
        self.assertEqual(list(self.dl.iterdir()) if self.dl.exists() else [], [])
        self.assertEqual(len(self.srv.hits), 1)  # a mismatch is not retried

    def test_stale_part_is_replaced(self):
        self.dl.mkdir(parents=True)
        (self.dl / "tool.zip.part").write_bytes(b"half a file from an interrupted run")
        out = base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual(out.read_bytes(), self.BODY)
        self.assertFalse((self.dl / "tool.zip.part").exists())

    def test_placeholders_are_refused_without_a_request(self):
        for url, digest in ((self.url, base.PLACEHOLDER), (self.url, None), (base.PLACEHOLDER, sha(self.BODY)),
                            (self.url, "not-a-sha")):
            with self.assertRaises(base.DownloadError):
                base.download(url, digest, self.dl, self.log)
        self.assertEqual(self.srv.hits, [])
        self.assertFalse(self.dl.exists())

    def test_unsupported_scheme_is_refused(self):
        with self.assertRaises(base.DownloadError):
            base.download("ftp://127.0.0.1/x.zip", sha(b"x"), self.dl, self.log)

    def test_http_error_is_a_download_error(self):
        with self.assertRaises(base.DownloadError):
            base.download(self.url.replace("tool.zip", "missing.zip"), sha(b"x"), self.dl, self.log, retries=1)
        self.assertFalse((self.dl / "missing.zip.part").exists())

    def test_file_url_works(self):
        src = self.tmp / "src dir" / "ffmpeg.zip"
        src.parent.mkdir(parents=True)
        src.write_bytes(self.BODY)
        out = base.download(src.as_uri(), sha(self.BODY), self.dl, self.log)
        self.assertEqual(out, self.dl / "ffmpeg.zip")
        self.assertEqual(out.read_bytes(), self.BODY)

    def test_urllib_fallback_without_curl(self):
        with mock.patch.object(base, "find_curl", return_value=None):
            out = base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual(out.read_bytes(), self.BODY)
        self.assertEqual(len(self.srv.hits), 1)


# --------------------------------------------------------------------------------------------- extract
class TestExtract(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name) / ARABIC_HOME
        self.tmp.mkdir()
        self.dest = self.tmp / "out"

    def tearDown(self):
        self._td.cleanup()

    def _zip(self, entries: dict) -> Path:
        z = self.tmp / "a.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return z

    def _tar(self, entries: dict, mode="w:gz", suffix=".tar.gz") -> Path:
        t = self.tmp / f"a{suffix}"
        with tarfile.open(t, mode) as tf:
            for name, data in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755
                tf.addfile(info, io.BytesIO(data))
        return t

    def test_zip_member_map(self):
        z = self._zip({"ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe": b"FF",
                       "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe": b"FP",
                       "ffmpeg-9.0.2-essentials_build/README.txt": b"readme"})
        out = base.extract(z, self.dest, {"ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe": "ffmpeg.exe",
                                          "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe": "ffprobe.exe"})
        self.assertEqual(sorted(p.name for p in out), ["ffmpeg.exe", "ffprobe.exe"])
        self.assertEqual((self.dest / "ffmpeg.exe").read_bytes(), b"FF")
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["ffmpeg.exe", "ffprobe.exe"])

    def test_missing_member_is_an_error(self):
        z = self._zip({"a/uv.exe": b"x"})
        with self.assertRaises(base.ExtractError):
            base.extract(z, self.dest, {"b/uv.exe": "uv.exe"})

    def test_tar_gz_and_tar_xz(self):
        t = self._tar({"uv-aarch64-apple-darwin/uv": b"UV", "uv-aarch64-apple-darwin/uvx": b"UVX"})
        out = base.extract(t, self.dest)
        self.assertEqual(sorted(p.relative_to(self.dest).as_posix() for p in out),
                         ["uv-aarch64-apple-darwin/uv", "uv-aarch64-apple-darwin/uvx"])
        self.assertEqual((self.dest / "uv-aarch64-apple-darwin" / "uv").read_bytes(), b"UV")
        if not IS_WIN:
            self.assertTrue(os.access(self.dest / "uv-aarch64-apple-darwin" / "uv", os.X_OK))
        x = self._tar({"./bin/tool": b"T"}, "w:xz", ".tar.xz")
        out = base.extract(x, self.tmp / "xz", {"bin/tool": "tool"})
        self.assertEqual([p.name for p in out], ["tool"])

    def test_parent_entries_are_refused(self):
        for maker in (lambda: self._zip({"ok.txt": b"1", "../evil": b"x"}),
                      lambda: self._tar({"ok.txt": b"1", "../evil": b"x"}),
                      lambda: self._zip({"/abs/evil": b"x"}),
                      lambda: self._zip({"C:/evil": b"x"})):
            with self.subTest():
                with self.assertRaises(base.ExtractError):
                    base.extract(maker(), self.dest)
                self.assertFalse((self.tmp / "evil").exists())
                self.assertFalse(self.dest.exists() and any(self.dest.iterdir()))
        z = self._zip({"a/uv.exe": b"x"})
        with self.assertRaises(base.ExtractError):
            base.extract(z, self.dest, {"a/uv.exe": "../uv.exe"})

    def test_tar_links_are_refused(self):
        t = self.tmp / "link.tar.gz"
        with tarfile.open(t, "w:gz") as tf:
            info = tarfile.TarInfo("bin/uv")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)
        with self.assertRaises(base.ExtractError):
            base.extract(t, self.dest)


# --------------------------------------------------------------------------------------------- state
class TestState(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.paths = base.Paths.from_env(str(Path(self._td.name) / ARABIC_HOME), env={})

    def tearDown(self):
        self._td.cleanup()

    def test_record_and_step_done(self):
        st = base.State(self.paths)
        st.load()
        self.assertFalse(st.step_done("ffmpeg", "fp1"))
        st.record("ffmpeg", "ok", "fp1", "ffmpeg 9.0.2")
        self.assertTrue(st.step_done("ffmpeg", "fp1"))
        self.assertFalse(st.step_done("ffmpeg", "fp2"))
        st.record("runtime", "red", "fp9", "sync failed")
        self.assertFalse(st.step_done("runtime", "fp9"))
        again = base.State(self.paths)
        again.load()
        self.assertTrue(again.step_done("ffmpeg", "fp1"))
        data = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["steps"]["ffmpeg"]["status"], "ok")
        self.assertEqual(data["steps"]["ffmpeg"]["detail"], "ffmpeg 9.0.2")
        self.assertIn("at", data["steps"]["ffmpeg"])
        self.assertTrue(data["updated_at"])
        self.assertEqual(sorted(p.name for p in self.paths.whynot.iterdir()), ["state.json"])  # no .tmp left

    def test_corrupt_state_is_set_aside(self):
        self.paths.whynot.mkdir(parents=True)
        self.paths.state_file.write_bytes(b'{"schema": 1, "steps": {')
        st = base.State(self.paths)
        st.load()
        self.assertEqual(st.data["steps"], {})
        self.assertFalse(self.paths.state_file.exists())
        kept = [p.name for p in self.paths.whynot.iterdir()]
        self.assertEqual(len(kept), 1)
        self.assertRegex(kept[0], r"^state\.json\.corrupt-\d{8}-\d{6}")
        st.record("preflight", "ok")
        self.assertTrue(self.paths.state_file.exists())

    def test_dry_run_state_writes_nothing(self):
        st = base.State(self.paths, dry_run=True)
        st.load()
        st.record("preflight", "ok", "x")
        self.assertTrue(st.step_done("preflight", "x"))
        self.assertFalse(self.paths.whynot.exists())


# --------------------------------------------------------------------------------------------- run_steps
class TestRunSteps(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.paths = base.Paths.from_env(str(Path(self._td.name) / ARABIC_HOME), env={})
        self.logf = self.paths.logs_dir / "install-test.log"
        st = base.State(self.paths)
        st.load()
        self.ctx = base.Ctx(paths=self.paths, log=Quiet(self.logf), components={}, state=st, plugin_root=SK,
                            platform="win-x64", args=argparse.Namespace(skip=[], dry_run=False))

    def tearDown(self):
        self._td.cleanup()

    def test_dependencies_and_exceptions(self):
        ran = []

        def boom(ctx):
            ran.append("runtime")
            raise RuntimeError("uv pip sync failed")

        def ok(name):
            def fn(ctx):
                ran.append(name)
                return base.StepResult(name, "ok")
            return fn

        steps = [("runtime", boom, ()), ("model", ok("model"), ("runtime",)), ("ffmpeg", ok("ffmpeg"), ()),
                 ("doctor", ok("doctor"), ("ffmpeg",))]
        res = base.run_steps(self.ctx, steps)
        by = {r.name: r for r in res}
        self.assertEqual([r.name for r in res], ["runtime", "model", "ffmpeg", "doctor"])
        self.assertEqual(by["runtime"].status, "red")
        self.assertIn("uv pip sync failed", by["runtime"].detail)
        self.assertEqual(by["model"].status, "skipped")
        self.assertIn("needs runtime", by["model"].detail)
        self.assertEqual((by["ffmpeg"].status, by["doctor"].status), ("ok", "ok"))
        self.assertEqual(ran, ["runtime", "ffmpeg", "doctor"])
        log = self.logf.read_text(encoding="utf-8")
        self.assertIn("Traceback", log)
        self.assertIn("uv pip sync failed", log)
        self.assertEqual(self.ctx.state.data["steps"]["runtime"]["status"], "red")

    def test_skip_flag_and_bad_return(self):
        self.ctx.args.skip = ["fonts"]
        steps = [("fonts", lambda c: base.StepResult("fonts", "ok"), ()),
                 ("adobe", lambda c: None, ()),
                 ("doctor", lambda c: base.StepResult("doctor", "amber", "slow", needs_you="update GPU driver"), ())]
        by = {r.name: r for r in base.run_steps(self.ctx, steps)}
        self.assertEqual(by["fonts"].status, "skipped")
        self.assertEqual(by["adobe"].status, "red")
        self.assertEqual(by["doctor"].needs_you, "update GPU driver")

    def test_ctx_defaults(self):
        self.assertIsNone(self.ctx.runtime_python)
        self.assertEqual((self.ctx.facts, self.ctx.answers), ({}, {}))


# --------------------------------------------------------------------------------------------- safe_rmtree
def make_dir_link(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if IS_WIN:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0 and link.exists()
    return False


class TestSafeRmtree(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.root = self.tmp / "home" / ".whynot-cut"
        (self.root / "runtimes" / "r-1" / "Lib").mkdir(parents=True)
        (self.root / "runtimes" / "r-1" / "Lib" / "x.py").write_text("x", encoding="utf-8")
        self.target = self.tmp / "client-data"
        self.target.mkdir()
        (self.target / "keep.mp4").write_bytes(b"precious")

    def tearDown(self):
        self._td.cleanup()

    def rm(self, p, protected=()):
        return base.safe_rmtree(p, [self.root], list(protected))

    def test_deletes_a_normal_dir_inside_the_root(self):
        ro = self.root / "runtimes" / "r-1" / "Lib" / "x.py"
        os.chmod(ro, 0o444)  # read-only files (git objects, pyc) still go
        self.assertTrue(self.rm(self.root / "runtimes" / "r-1"))
        self.assertFalse((self.root / "runtimes" / "r-1").exists())
        self.assertTrue((self.root / "runtimes").exists())

    def test_refuses_outside_the_root_and_the_root_itself(self):
        self.assertFalse(self.rm(self.target))
        self.assertFalse(self.rm(self.root))
        self.assertFalse(self.rm(self.root / ".." / ".." / "client-data"))
        self.assertTrue((self.target / "keep.mp4").exists())
        self.assertTrue(self.root.exists())

    def test_refuses_a_dir_with_a_client_marker(self):
        client = self.root / "models" / "nested" / "Dr X"
        client.mkdir(parents=True)
        (client / ".whynot-client").write_text("{}", encoding="utf-8")
        self.assertFalse(self.rm(self.root / "models"))
        self.assertTrue((client / ".whynot-client").exists())

    def test_refuses_the_parent_of_a_protected_path(self):
        clients = self.root / "cache" / "Clients"
        clients.mkdir(parents=True)
        self.assertFalse(self.rm(self.root / "cache", protected=[clients]))
        self.assertFalse(self.rm(clients, protected=[clients]))
        self.assertTrue(clients.exists())

    def test_links_are_never_followed(self):
        link = self.root / "downloads"
        if not make_dir_link(link, self.target):
            self.skipTest("cannot create a symlink or junction here")
        self.assertFalse(self.rm(link))  # the link itself is refused
        self.assertTrue((self.target / "keep.mp4").exists())
        holder = self.root / "bridge"
        holder.mkdir()
        (holder / "f.txt").write_text("x", encoding="utf-8")
        if not make_dir_link(holder / "inner", self.target):
            self.skipTest("cannot create a symlink or junction here")
        self.assertTrue(self.rm(holder))  # a link inside is removed as a link, its target untouched
        self.assertFalse(holder.exists())
        self.assertEqual((self.target / "keep.mp4").read_bytes(), b"precious")

    def test_missing_path_is_fine(self):
        self.assertTrue(self.rm(self.root / "not-there"))


# --------------------------------------------------------------------------------------------- cli
class TestPlanCommand(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.home = Path(self._td.name) / ARABIC_HOME
        self.home.mkdir()

    def tearDown(self):
        self._td.cleanup()

    def run_core(self, *args, isolated=False):
        cmd = [sys.executable, "-B"] + (["-I"] if isolated else []) + [str(CORE / "wnc_install.py"), *args]
        env = {k: v for k, v in os.environ.items() if k not in ("WHYNOT_HOME", "CLAUDE_CONFIG_DIR")}
        env["PYTHONUTF8"] = "1"
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

    def test_plan_prints_the_14_steps_in_order(self):
        for isolated in (False, True):
            with self.subTest(isolated=isolated):
                r = self.run_core("plan", "--home", str(self.home), isolated=isolated)
                self.assertEqual(r.returncode, 0, r.stderr)
                out = json.loads(r.stdout)
                self.assertEqual(out["steps"], STEP_NAMES)
        self.assertEqual(list(self.home.iterdir()), [])  # plan writes nothing

    def test_step_order_constant_and_registry(self):
        self.assertEqual(list(cli.STEP_ORDER), STEP_NAMES)
        self.assertIsInstance(cli.STEPS, list)

    def test_parser_flags(self):
        a = cli.build_parser().parse_args(["install", "--home", "h", "--skip", "fonts,gpu", "--language", "en",
                                           "--channel", "beta", "--dry-run", "--yes"])
        self.assertEqual((a.command, a.skip, a.language, a.channel, a.dry_run, a.yes),
                         ("install", ["fonts", "gpu"], "en", "beta", True, True))
        u = cli.build_parser().parse_args(["uninstall", "--remove-engine", "--remove-models"])
        self.assertTrue(u.remove_engine and u.remove_models)
        self.assertEqual(cli.default_plugin_root(), SK)

    def test_dry_run_install_in_a_sandbox(self):
        with mock.patch.object(cli, "STEPS", []):
            rc = cli.main(["install", "--home", str(self.home), "--dry-run", "--quiet"])
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
