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
  * runtime.py (steps runtime / ffmpeg / gpu): the runtime id, an in-place build with
    tests/fixtures/installer/fake_uv.py (only-managed python, --no-bin --no-registry, UV_NO_CONFIG=1,
    stamps, `current`, `pip sync --require-hashes`), no uv call on a re-run, a failed sync or smoke never moves
    `current` and leaves no stamps, the shared build lock (held = amber, stale = taken over, always released),
    an unstamped runtime is repaired with `pip sync` alone, a missing lock is skipped, a deleted runtime is
    rebuilt; ffmpeg from a local zip with the GPL text and SOURCE.txt, a bad sha256 installs nothing, a placeholder
    is skipped; gpu-enable only on win-x64 with an NVIDIA GPU (WNC_TEST_NVIDIA in the sandbox).
  * claude.py (steps gitbash / claude): the CLI search matches tools/find_claude.py (a sandbox never looks at PATH),
    the settings.json merge (BOM, key order, one exact backup only on change, invalid JSON byte-identical with the JSON
    to paste, reel-editor@* switched off, env key by key) and its undo, the marketplace entry and the managed
    marketplace folder, the claude step with tests/fixtures/installer/fake_claude.py (marketplace add -> plugin
    install / update, a legacy marketplace removed first, an old CLI amber, no CLI = settings only), and the per-user
    Git Bash (found / unpacked from a local zip / placeholder amber; the 7z SFX command checked without running one).
Never touches the real ~/.whynot-cut or ~/.claude: every Paths is a sandbox home in a temp folder, and no real
network is used (artefacts come from a 127.0.0.1 http.server started here, or file://).
Run (repo root):
    bash tools/test.sh -p test_installer.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import argparse
import contextlib
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
        if srv.truncate.get(self.path, 0) > 0:  # announce the whole body, send 5000 bytes, drop the connection
            srv.truncate[self.path] -= 1
            self.wfile.write(body[:5000])
            self.close_connection = True
            return
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def curl_or_urllib(use_curl: bool):
    """The real curl, or no curl at all (so the urllib downloader is used)."""
    return contextlib.nullcontext() if use_curl else mock.patch.object(base, "find_curl", return_value=None)


class TestDownload(unittest.TestCase):
    BODY = b"pinned artefact " * 1000

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name) / ARABIC_HOME
        self.dl = self.tmp / ".whynot-cut" / "downloads"
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.srv.hits, self.srv.files = [], {"/a/tool.zip": self.BODY, "/a/Syne%5Bwght%5D.ttf": b"font"}
        self.srv.truncate = {}  # path -> how many more responses to cut short
        no_wait = mock.patch.object(base, "_sleep")  # retry back-off without the wait
        no_wait.start()
        self.addCleanup(no_wait.stop)
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

    def test_http_4xx_fails_fast(self):
        missing = self.url.replace("tool.zip", "missing.zip")
        for curl in (True, False):  # curl alone, then urllib alone: one request each, no retries
            with self.subTest(curl=curl), curl_or_urllib(curl):
                self.srv.hits.clear()
                with self.assertRaises(base.DownloadError) as cm:
                    base.download(missing, sha(b"x"), self.dl, self.log, retries=3)
                self.assertIn("404", str(cm.exception))
                self.assertEqual(len(self.srv.hits), 1)
                self.assertFalse((self.dl / "missing.zip.part").exists())

    def _assert_nothing_left(self):
        self.assertEqual([p.name for p in self.dl.iterdir()], [])

    def test_interrupted_transfer_is_retried(self):
        for curl in (True, False):
            with self.subTest(curl=curl), curl_or_urllib(curl):
                self.srv.hits.clear()
                self.srv.truncate["/a/tool.zip"] = 1  # first response cut short, second complete
                out = base.download(self.url, sha(self.BODY), self.dl, self.log, retries=3)
                self.assertEqual(out.read_bytes(), self.BODY)
                self.assertEqual(len(self.srv.hits), 2)
                self.assertFalse((self.dl / "tool.zip.part").exists())
                out.unlink()

    def test_always_interrupted_is_a_transfer_error_not_a_bad_pin(self):
        for curl in (True, False):
            with self.subTest(curl=curl), curl_or_urllib(curl):
                self.srv.hits.clear()
                self.srv.truncate["/a/tool.zip"] = 99
                with self.assertRaises(base.DownloadError) as cm:
                    base.download(self.url, sha(self.BODY), self.dl, self.log, retries=3)
                msg = str(cm.exception)
                self.assertIn("transfer failed after 3 tries", msg)
                self.assertNotIn("sha256 mismatch", msg)
                self.assertEqual(len(self.srv.hits), 3)  # one request per try, no same-try double request
                self._assert_nothing_left()

    def test_cached_hit_removes_a_stale_part(self):
        base.download(self.url, sha(self.BODY), self.dl, self.log)
        (self.dl / "tool.zip.part").write_bytes(b"left over")
        base.download(self.url, sha(self.BODY), self.dl, self.log)
        self.assertEqual([p.name for p in self.dl.iterdir()], ["tool.zip"])
        self.assertEqual(len(self.srv.hits), 1)

    def test_loopback_never_goes_through_a_proxy(self):
        dead = "http://127.0.0.1:9"  # nothing listens there: going through it would fail
        env = {k: dead for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")}
        with mock.patch.dict(os.environ, env):
            for k in ("no_proxy", "NO_PROXY"):
                os.environ.pop(k, None)
            for curl in (True, False):
                with self.subTest(curl=curl), curl_or_urllib(curl):
                    out = base.download(self.url, sha(self.BODY), self.dl, self.log, retries=1)
                    self.assertEqual(out.read_bytes(), self.BODY)
                    out.unlink()

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

    def test_unreadable_state_is_not_renamed(self):
        # a read error (antivirus lock, permissions; here a folder in its place) is not corruption
        self.paths.state_file.mkdir(parents=True)
        with self.assertRaises(OSError):
            base.State(self.paths).load()
        self.assertTrue(self.paths.state_file.is_dir())
        self.assertEqual([p.name for p in self.paths.whynot.iterdir()], ["state.json"])
        with mock.patch.object(cli, "STEPS", []):
            rc = cli.main(["install", "--home", str(self.paths.home), "--quiet"])
        self.assertEqual(rc, 2)
        self.assertTrue(self.paths.state_file.is_dir())
        self.assertFalse([p for p in self.paths.whynot.iterdir() if "corrupt" in p.name])

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

    def test_runtime_ffmpeg_gpu_are_registered(self):
        r = self.run_core("plan", "--home", str(self.home), isolated=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        reg = json.loads(r.stdout)["registered"]
        for name in ("runtime", "ffmpeg", "gpu"):
            self.assertIn(name, reg)
        self.assertLess(reg.index("runtime"), reg.index("ffmpeg"))
        self.assertLess(reg.index("ffmpeg"), reg.index("gpu"))
        needs = {n: d for n, _f, d in cli.STEPS}
        self.assertEqual(needs["gpu"], ("runtime",))
        self.assertEqual((needs["runtime"], needs["ffmpeg"]), ((), ()))


# --------------------------------------------------------------------------------------------- T7.1 step helpers
FIXTURES = SK / "tests" / "fixtures" / "installer"
FAKE_UV = FIXTURES / "fake_uv.py"
LOCK_A = b"# fixture lock A\nanyio==4.15.1 \\\n    --hash=sha256:" + b"a" * 64 + b"\n"
LOCK_B = b"# fixture lock B\nanyio==4.15.2 \\\n    --hash=sha256:" + b"b" * 64 + b"\n"


def runtime_module():
    """Imported inside the tests so this file stays importable while a step module is being written."""
    from wnc_installer import runtime
    return runtime


def make_ctx(home: Path, components: dict, plugin_root: Path, platform: str = "win-x64", **args) -> base.Ctx:
    paths = base.Paths.from_env(str(home), env={})
    st = base.State(paths)
    st.load()
    ns = argparse.Namespace(skip=[], dry_run=False, uv=None, python=None, yes=True)
    for k, v in args.items():
        setattr(ns, k, v)
    return base.Ctx(paths=paths, log=Quiet(paths.logs_dir / "install-test.log"), components=components, state=st,
                    plugin_root=plugin_root, platform=platform, args=ns)


class Served:
    """A 127.0.0.1 http.server (the _Handler above) for one test; stopped and closed by addCleanup."""

    def __init__(self, test: unittest.TestCase, files: dict):
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.srv.hits, self.srv.files, self.srv.truncate = [], dict(files), {}
        self.thread = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        test.addCleanup(self.stop)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(5)


# --------------------------------------------------------------------------------------------- runtime step
class TestRuntime(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        tmp = Path(self._td.name)
        self.home = tmp / ARABIC_HOME
        self.plugin = tmp / "plugin root"
        self.lock = self.plugin / "setup" / "locks" / "runtime-win-x64.lock"
        self.lock.parent.mkdir(parents=True)
        self.lock.write_bytes(LOCK_A)
        self.uv_log = tmp / "uv-calls.jsonl"
        self.comp = {"schema": 1, "runtime": {
            "python": "3.12.15", "index_url": None, "smoke": ["json", "sqlite3"],
            "locks": {"win-x64": {"file": "setup/locks/runtime-win-x64.lock", "id": base.PLACEHOLDER}}}}
        env = mock.patch.dict(os.environ, {"WNC_TEST_UV": str(FAKE_UV), "FAKE_UV_LOG": str(self.uv_log)})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("FAKE_UV_FAIL", None)
        self.rt = runtime_module()

    def ctx(self):
        return make_ctx(self.home, self.comp, self.plugin)

    def uv_log_lines(self):
        if not self.uv_log.exists():
            return []
        return [json.loads(x) for x in self.uv_log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def uv_calls(self, *prefix):
        """argv of every uv call (those starting with `prefix` when given)."""
        return [c["argv"] for c in self.uv_log_lines() if c["argv"][:len(prefix)] == list(prefix)]

    def rid(self, lock=LOCK_A):
        return "r-" + sha(lock)[:12]

    def build_lock(self, paths, rid=None):
        return paths.runtimes_dir / f".{rid or self.rid()}.building"

    def assert_unstamped(self, rdir):
        self.assertFalse((rdir / "WHYNOT_RUNTIME").exists())
        self.assertFalse((rdir / ".whynot-lock.sha256").exists())

    def test_a_runtime_id(self):
        rid = self.rt.runtime_id(self.comp, "win-x64", self.lock)
        self.assertEqual(rid, "r-" + sha(LOCK_A)[:12])
        self.comp["runtime"]["locks"]["win-x64"]["id"] = None
        self.assertEqual(self.rt.runtime_id(self.comp, "win-x64", self.lock), rid)
        self.comp["runtime"]["locks"]["win-x64"]["id"] = "rt-2026.10.1"
        self.assertEqual(self.rt.runtime_id(self.comp, "win-x64", self.lock), "rt-2026.10.1")
        self.comp["runtime"]["locks"]["win-x64"]["id"] = "../escape"
        with self.assertRaises(ValueError):
            self.rt.runtime_id(self.comp, "win-x64", self.lock)

    def test_b_fresh_build_in_place_then_c_no_uv_call(self):
        ctx = self.ctx()
        r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        rid = self.rid()
        paths = ctx.paths
        self.assertEqual(paths.current_file.read_bytes(), (rid + "\n").encode())  # one line, no BOM
        self.assertEqual(self.rt.current_runtime(paths), rid)
        rdir = paths.runtimes_dir / rid
        self.assertEqual((rdir / ".whynot-lock.sha256").read_text(encoding="utf-8").strip(), sha(LOCK_A))
        stamp = json.loads((rdir / "WHYNOT_RUNTIME").read_text(encoding="utf-8"))
        self.assertEqual((stamp["id"], stamp["platform"], stamp["lock_sha256"]), (rid, "win-x64", sha(LOCK_A)))
        for k in ("python", "lock_file", "created_at", "by"):
            self.assertTrue(stamp[k], k)
        self.assertEqual(ctx.runtime_python, self.rt.runtime_python(paths, rid))
        self.assertTrue(ctx.runtime_python.is_file())
        # built in place: no `<id>.building` folder ever, and the build lock file is released
        self.assertEqual(sorted(p.name for p in paths.runtimes_dir.iterdir()), [rid])
        venv = self.uv_calls("venv")
        self.assertEqual(len(venv), 1)
        self.assertEqual(Path(venv[0][1]), rdir)
        self.assertNotIn("--relocatable", venv[0])
        self.assertEqual(venv[0][venv[0].index("--python-preference") + 1], "only-managed")
        # `uv python find` printed a warning on stderr: only its stdout (the interpreter) reached `uv venv`
        self.assertEqual(venv[0][venv[0].index("--python") + 1], sys.executable)
        find = self.uv_calls("python", "find")
        self.assertEqual(find[0][find[0].index("--python-preference") + 1], "only-managed")
        self.assertEqual(self.uv_calls("python", "install"), [])
        sync = self.uv_calls("pip", "sync")
        self.assertEqual(len(sync), 1)
        self.assertIn("--require-hashes", sync[0])
        self.assertIn(str(self.lock), sync[0])
        self.assertNotIn("--index-url", sync[0])
        self.assertTrue(all(c["UV_NO_CONFIG"] == "1" for c in self.uv_log_lines()))  # uv never reads uv.toml
        self.assertEqual(ctx.state.data["runtime"]["id"], rid)
        # (c) a second run finds the stamped runtime and its smoke import passing: no uv call at all
        self.uv_log.unlink()
        ctx2 = self.ctx()
        r2 = self.rt.step_runtime(ctx2)
        self.assertEqual(r2.status, "ok", r2.detail)
        self.assertEqual(self.uv_calls(), [])
        self.assertEqual(ctx2.runtime_python, ctx.runtime_python)

    def test_python_install_without_bin_and_registry(self):
        with mock.patch.dict(os.environ, {"FAKE_UV_FIND_FAIL_ONCE": str(self.uv_log.with_name("find-failed"))}):
            self.assertEqual(self.rt.step_runtime(self.ctx()).status, "ok")
        inst = self.uv_calls("python", "install")
        self.assertEqual(len(inst), 1)
        self.assertEqual(inst[0][2], "3.12.15")
        self.assertIn("--no-bin", inst[0])
        self.assertIn("--no-registry", inst[0])
        self.assertEqual(len(self.uv_calls("python", "find")), 2)

    def test_uv_child_env(self):
        env = base.Paths.from_env(str(self.home), env={}).child_env({})
        self.assertEqual((env["UV_NO_CONFIG"], env["UV_HTTP_TIMEOUT"], env["UV_HTTP_RETRIES"]), ("1", "60", "5"))

    def test_index_url_is_passed_when_pinned(self):
        self.comp["runtime"]["index_url"] = "https://mirror.example/simple"
        self.assertEqual(self.rt.step_runtime(self.ctx()).status, "ok")
        sync = self.uv_calls("pip", "sync")[0]
        self.assertEqual(sync[sync.index("--index-url") + 1], "https://mirror.example/simple")

    def test_fresh_build_lock_held_elsewhere_is_amber(self):
        paths = self.ctx().paths
        lk = self.build_lock(paths)
        lk.parent.mkdir(parents=True)
        lk.write_text("4242 reel setup\n", encoding="utf-8")
        ctx = self.ctx()
        r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "amber")
        self.assertIn("another WhyNot Cut setup is building this runtime", r.detail)
        self.assertEqual(self.uv_calls(), [])
        self.assertEqual(lk.read_text(encoding="utf-8"), "4242 reel setup\n")  # not ours: left alone
        self.assertFalse(ctx.paths.current_file.exists())
        self.assertIsNone(ctx.runtime_python)

    def test_stale_build_lock_is_taken_over(self):
        paths = self.ctx().paths
        lk = self.build_lock(paths)
        lk.parent.mkdir(parents=True)
        lk.write_text("4242 crashed\n", encoding="utf-8")
        old = __import__("time").time() - 3 * 3600
        os.utime(lk, (old, old))
        ctx = self.ctx()
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        self.assertFalse(lk.exists())
        self.assertEqual(self.rt.current_runtime(ctx.paths), self.rid())

    def test_d_failed_sync_keeps_the_old_runtime(self):
        self.assertEqual(self.rt.step_runtime(self.ctx()).status, "ok")
        old, new = self.rid(LOCK_A), self.rid(LOCK_B)
        self.lock.write_bytes(LOCK_B)
        with mock.patch.dict(os.environ, {"FAKE_UV_FAIL": "sync"}):
            ctx = self.ctx()
            r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "red")
        self.assertIn("sync", r.detail)
        self.assertEqual(self.rt.current_runtime(ctx.paths), old)
        # the unfinished new runtime stays in place without stamps (never trusted); the lock file is released
        self.assertEqual(sorted(p.name for p in ctx.paths.runtimes_dir.iterdir()), sorted([old, new]))
        self.assert_unstamped(ctx.paths.runtimes_dir / new)
        self.assertIsNone(ctx.runtime_python)
        # the next run repairs it (its python works: only `pip sync`, no `venv`) and `current` switches; old kept
        self.uv_log.unlink()
        ctx = self.ctx()
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        self.assertEqual(self.uv_calls("venv"), [])
        self.assertEqual(len(self.uv_calls("pip", "sync")), 1)
        self.assertEqual(self.rt.current_runtime(ctx.paths), new)
        self.assertEqual(sorted(p.name for p in ctx.paths.runtimes_dir.iterdir()), sorted([old, new]))

    def test_repair_of_an_unstamped_runtime_only_syncs(self):
        ctx = self.ctx()
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        rdir = ctx.paths.runtimes_dir / self.rid()
        (rdir / "WHYNOT_RUNTIME").unlink()
        (rdir / ".whynot-lock.sha256").unlink()  # an interrupted earlier build
        self.uv_log.unlink()
        ctx = self.ctx()
        r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn("repaired", r.detail)
        self.assertEqual([c[:2] for c in self.uv_calls()], [["pip", "sync"]])
        self.assertTrue((rdir / ".whynot-lock.sha256").is_file())

    def test_failed_repair_leaves_no_stamps_and_current_unchanged(self):
        ctx = self.ctx()
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        rdir = ctx.paths.runtimes_dir / self.rid()
        (rdir / ".whynot-lock.sha256").write_text("0" * 64 + "\n", encoding="utf-8")  # stamped for another lock
        with mock.patch.dict(os.environ, {"FAKE_UV_FAIL": "sync"}):
            ctx = self.ctx()
            r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "red")
        self.assert_unstamped(rdir)  # the stamps went first: the next run never trusts this runtime
        self.assertEqual(ctx.paths.current_file.read_text(encoding="utf-8"), self.rid() + "\n")
        self.assertFalse(self.build_lock(ctx.paths).exists())
        self.assertEqual(self.uv_calls("venv")[1:], [])  # the repair did not recreate the venv

    def test_e_no_lock_is_skipped(self):
        self.lock.unlink()
        ctx = self.ctx()
        r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "skipped")
        self.assertIn("T2.1", r.detail)
        self.assertEqual(self.uv_calls(), [])
        self.assertFalse(ctx.paths.current_file.exists())

    def test_f_current_naming_a_deleted_runtime_rebuilds(self):
        ctx = self.ctx()
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        rid = self.rt.current_runtime(ctx.paths)
        import shutil
        shutil.rmtree(ctx.paths.runtimes_dir / rid)
        self.assertIsNone(self.rt.current_runtime(ctx.paths))
        self.uv_log.unlink()
        ctx = self.ctx()
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        self.assertEqual(self.rt.current_runtime(ctx.paths), rid)
        self.assertTrue(self.uv_calls("pip", "sync"))

    def test_leftover_without_python_is_removed_and_rebuilt(self):
        ctx = self.ctx()
        rid = self.rid()
        leftover = ctx.paths.runtimes_dir / rid
        (leftover / "Lib").mkdir(parents=True)
        (leftover / "Lib" / "half.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.rt.step_runtime(ctx).status, "ok")
        self.assertFalse((leftover / "Lib" / "half.py").exists())
        self.assertEqual(len(self.uv_calls("venv")), 1)
        self.assertTrue((leftover / ".whynot-lock.sha256").is_file())
        self.assertEqual(sorted(p.name for p in ctx.paths.runtimes_dir.iterdir()), [rid])

    def test_failed_smoke_is_red_and_current_unchanged(self):
        self.comp["runtime"]["smoke"] = ["json", "no_such_module_wnc"]
        ctx = self.ctx()
        r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "red")
        self.assertIn("no_such_module_wnc", r.detail + ctx.log.path.read_text(encoding="utf-8"))
        self.assertFalse(ctx.paths.current_file.exists())
        self.assert_unstamped(ctx.paths.runtimes_dir / self.rid())
        self.assertFalse(self.build_lock(ctx.paths).exists())

    def test_runtime_python_prefers_the_layout_that_exists(self):
        paths = base.Paths.from_env(str(self.home), env={})
        d = paths.runtimes_dir / "r-x"
        win, posix = d / "Scripts" / "python.exe", d / "bin" / "python"
        self.assertEqual(self.rt.runtime_python(paths, "r-x"), win if IS_WIN else posix)
        other = posix if IS_WIN else win
        other.parent.mkdir(parents=True)
        other.write_bytes(b"")
        self.assertEqual(self.rt.runtime_python(paths, "r-x"), other)
        self.assertIsNone(self.rt.current_runtime(paths))  # no `current` file
        paths.current_file.write_text("r-x\n", encoding="utf-8")
        self.assertEqual(self.rt.current_runtime(paths), "r-x")
        paths.current_file.write_text("../evil\n", encoding="utf-8")
        self.assertIsNone(self.rt.current_runtime(paths))

    def test_test_uv_is_ignored_outside_the_sandbox(self):
        ctx = self.ctx()
        ctx.paths.sandbox = False
        ctx.args.uv = str(self.home / "bin" / "uv.exe")
        self.assertEqual(self.rt.uv_command(ctx), [ctx.args.uv])
        ctx.paths.sandbox = True
        self.assertEqual(self.rt.uv_command(ctx), [sys.executable, "-B", str(FAKE_UV)])

    @unittest.skipUnless(IS_WIN, "the .cmd wrapper is for Windows")
    def test_cmd_wrapper_runs_fake_uv(self):
        with mock.patch.dict(os.environ, {"WNC_TEST_UV": str(FIXTURES / "fake_uv.cmd"),
                                          "FAKE_UV_PYTHON": sys.executable, "FAKE_UV_VERSION": "9.9.9"}):
            ctx = self.ctx()
            rc, out = base.run_cmd(ctx, self.rt.uv_command(ctx) + ["--version"], 60)
        self.assertEqual((rc, out.strip()), (0, "uv 9.9.9"))


# --------------------------------------------------------------------------------------------- ffmpeg step
def ffmpeg_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


class TestFfmpeg(unittest.TestCase):
    WIN_ZIP = ffmpeg_zip({"ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe": b"MZ ffmpeg",
                          "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe": b"MZ ffprobe",
                          "ffmpeg-9.0.2-essentials_build/README.txt": b"readme"})
    MAC_FF = ffmpeg_zip({"ffmpeg": b"\xcf\xfa ffmpeg"})
    MAC_FP = ffmpeg_zip({"ffprobe": b"\xcf\xfa ffprobe"})

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        self.srv = Served(self, {"/win/ff.zip": self.WIN_ZIP, "/mac/ffmpeg.zip": self.MAC_FF,
                                 "/mac/ffprobe.zip": self.MAC_FP})
        self.comp = {"schema": 1, "ffmpeg": {
            "version": "9.0.2", "license": "GPL-3.0-or-later", "source": "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz",
            "assets": {
                "win-x64": {"files": [{"url": self.srv.base + "/win/ff.zip", "sha256": sha(self.WIN_ZIP),
                                       "archive": "zip", "members": {
                                           "ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe": "ffmpeg.exe",
                                           "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe": "ffprobe.exe"}}]},
                "mac-arm64": {"files": [
                    {"url": self.srv.base + "/mac/ffmpeg.zip", "sha256": sha(self.MAC_FF), "archive": "zip",
                     "members": {"ffmpeg": "ffmpeg"}},
                    {"url": self.srv.base + "/mac/ffprobe.zip", "sha256": sha(self.MAC_FP), "archive": "zip",
                     "members": {"ffprobe": "ffprobe"}}]}}}}
        self.rt = runtime_module()

    def test_win_install_with_licence_and_source(self):
        ctx = make_ctx(self.home, self.comp, SK, "win-x64")
        r = self.rt.step_ffmpeg(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        d = ctx.paths.ffmpeg_dir / "9.0.2"
        self.assertEqual(sorted(p.name for p in d.iterdir()),
                         ["LICENSE.GPL-3.0.txt", "SOURCE.txt", "ffmpeg.exe", "ffprobe.exe"])
        self.assertEqual((d / "ffmpeg.exe").read_bytes(), b"MZ ffmpeg")
        self.assertEqual((d / "LICENSE.GPL-3.0.txt").read_bytes(),
                         (SK / "installer" / "licenses" / "GPL-3.0.txt").read_bytes())
        src = (d / "SOURCE.txt").read_text(encoding="utf-8")
        for needle in ("9.0.2", "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz", self.srv.base + "/win/ff.zip",
                       sha(self.WIN_ZIP)):
            self.assertIn(needle, src)
        self.assertEqual(ctx.state.data["ffmpeg"], {"version": "9.0.2", "path": str(d / "ffmpeg.exe"),
                                                    "sha256": sha(b"MZ ffmpeg")})
        self.assertEqual(sorted(p.name for p in ctx.paths.ffmpeg_dir.iterdir()), ["9.0.2"])  # no staging left
        # already there with the same fingerprint: ok without a download
        hits = len(self.srv.srv.hits)
        ctx2 = make_ctx(self.home, self.comp, SK, "win-x64")
        for p in list(ctx2.paths.downloads_dir.iterdir()):  # not even the cached archive is needed
            p.unlink()
        self.assertEqual(self.rt.step_ffmpeg(ctx2).status, "ok")
        self.assertEqual(len(self.srv.srv.hits), hits)

    def test_mac_two_archives_and_exec_bits(self):
        ctx = make_ctx(self.home, self.comp, SK, "mac-arm64")
        r = self.rt.step_ffmpeg(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        d = ctx.paths.ffmpeg_dir / "9.0.2"
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["LICENSE.GPL-3.0.txt", "SOURCE.txt", "ffmpeg", "ffprobe"])
        src = (d / "SOURCE.txt").read_text(encoding="utf-8")
        self.assertIn(sha(self.MAC_FF), src)
        self.assertIn(sha(self.MAC_FP), src)
        if not IS_WIN:
            for b in ("ffmpeg", "ffprobe"):
                self.assertEqual(os.stat(d / b).st_mode & 0o777, 0o755)

    def test_wrong_sha_is_red_and_installs_nothing(self):
        self.comp["ffmpeg"]["assets"]["win-x64"]["files"][0]["sha256"] = "0" * 64
        ctx = make_ctx(self.home, self.comp, SK, "win-x64")
        r = self.rt.step_ffmpeg(ctx)
        self.assertEqual(r.status, "red")
        self.assertIn("sha256", r.detail)
        self.assertFalse((ctx.paths.ffmpeg_dir / "9.0.2").exists())
        self.assertFalse(ctx.paths.ffmpeg_dir.exists() and any(ctx.paths.ffmpeg_dir.iterdir()))
        self.assertNotIn("ffmpeg", ctx.state.data)

    def test_placeholder_is_skipped(self):
        for where in ("url", "sha256"):
            with self.subTest(where=where):
                comp = json.loads(json.dumps(self.comp))
                comp["ffmpeg"]["assets"]["win-x64"]["files"][0][where] = base.PLACEHOLDER
                ctx = make_ctx(self.home, comp, SK, "win-x64")
                r = self.rt.step_ffmpeg(ctx)
                self.assertEqual(r.status, "skipped")
                self.assertIn("not in this build", r.detail)
        self.assertEqual(self.srv.srv.hits, [])
        self.assertFalse((self.home / ".whynot-cut" / "ffmpeg").exists())


# --------------------------------------------------------------------------------------------- gpu step
class TestGpu(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        tmp = Path(self._td.name)
        self.home = tmp / ARABIC_HOME
        self.plugin = tmp / "plugin root"
        cli_py = self.plugin / "engine" / "reel" / "cli.py"
        cli_py.parent.mkdir(parents=True)
        self.argv_file = tmp / "argv.json"
        cli_py.write_text("import json, os, sys\n"
                          "with open(os.environ['WNC_TEST_ARGV'], 'w', encoding='utf-8') as f:\n"
                          "    json.dump({'argv': sys.argv, 'home': os.environ.get('WHYNOT_HOME'),\n"
                          "               'utf8': os.environ.get('PYTHONUTF8')}, f)\n"
                          "sys.exit(int(os.environ.get('WNC_TEST_EXIT', '0')))\n", encoding="utf-8")
        env = mock.patch.dict(os.environ, {"WNC_TEST_ARGV": str(self.argv_file)})
        env.start()
        self.addCleanup(env.stop)
        for k in ("WNC_TEST_NVIDIA", "WNC_TEST_EXIT"):
            os.environ.pop(k, None)
        self.rt = runtime_module()

    def ctx(self, plat="win-x64"):
        c = make_ctx(self.home, {"schema": 1}, self.plugin, plat)
        c.runtime_python = Path(sys.executable)
        return c

    def test_mac_is_skipped(self):
        r = self.rt.step_gpu(self.ctx("mac-arm64"))
        self.assertEqual(r.status, "skipped")
        self.assertIn("MLX comes with the mac-arm64 lock", r.detail)
        self.assertEqual(self.rt.step_gpu(self.ctx("mac-x64")).status, "skipped")
        self.assertFalse(self.argv_file.exists())

    def test_win_sandbox_without_nvidia_is_skipped(self):
        ctx = self.ctx()
        r = self.rt.step_gpu(ctx)
        self.assertEqual(r.status, "skipped")
        self.assertIn("NVIDIA", r.detail)
        self.assertFalse(self.argv_file.exists())
        self.assertFalse(ctx.facts["nvidia"])

    def test_win_with_nvidia_runs_gpu_enable(self):
        with mock.patch.dict(os.environ, {"WNC_TEST_NVIDIA": "1"}):
            ctx = self.ctx()
            r = self.rt.step_gpu(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        rec = json.loads(self.argv_file.read_text(encoding="utf-8"))
        self.assertEqual(rec["argv"][-1], "gpu-enable")
        self.assertEqual(Path(rec["argv"][0]), self.plugin / "engine" / "reel" / "cli.py")
        self.assertEqual((rec["home"], rec["utf8"]), (str(ctx.paths.whynot), "1"))
        self.assertTrue(ctx.facts["nvidia"])

    def test_gpu_enable_failure_is_amber(self):
        with mock.patch.dict(os.environ, {"WNC_TEST_NVIDIA": "1", "WNC_TEST_EXIT": "3"}):
            r = self.rt.step_gpu(self.ctx())
        self.assertEqual(r.status, "amber")
        self.assertIn("Whisper keeps using the CPU", r.detail)


# ------------------------------------------------------------------------------------------ T7.1/T7.3 claude, gitbash
FAKE_CLAUDE = FIXTURES / "fake_claude.py"
FIND_CLAUDE = SK.parent / "tools" / "find_claude.py"
PID = "whynot-cut@thewhynot-ai"
CLAUDE_COMP = {"schema": 1, "claude_code": {"min": "2.1.224"},
               "marketplace": {"name": "thewhynot-ai", "plugin": "whynot-cut", "url": base.PLACEHOLDER}}


def claude_module():
    """Imported inside the tests so this file stays importable while a step module is being written."""
    from wnc_installer import claude
    return claude


def touch(p: Path, data: bytes = b"") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


class TestFindClaudeParity(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.empty = self.tmp / "empty path"
        self.empty.mkdir()
        self.cl = claude_module()

    def bundles(self, home: Path, win: bool) -> list:
        exe = "claude.exe" if win else "claude"
        root = (home / "AppData" / "Roaming" if win else home / "Library" / "Application Support") / "Claude"
        made = [touch(root / "claude-code" / v / "a1b2c3" / exe) for v in ("2.1.9", "2.1.300")]
        touch(home / ".local" / "bin" / exe)
        if win:
            touch(home / "AppData" / "Local" / "Programs" / "claude" / exe)
        return made

    def test_same_order_as_tools_find_claude(self):
        if not FIND_CLAUDE.is_file():
            self.skipTest("tools/find_claude.py is not in this checkout")
        import importlib.util
        spec = importlib.util.spec_from_file_location("wnc_test_find_claude", FIND_CLAUDE)
        fc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fc)
        for plat in ("win32", "darwin"):
            with self.subTest(platform=plat):
                home = self.tmp / plat / ARABIC_HOME
                old, new = self.bundles(home, plat == "win32")
                env = {"PATH": str(self.empty)}  # no claude on PATH, no CLAUDE_CLI, AppData from the home
                with mock.patch.dict(os.environ, {"PATH": str(self.empty)}):
                    want = fc.candidates(env, home, plat)
                    got = self.cl.claude_candidates(env, home, plat, False)
                self.assertEqual(got, want)
                self.assertGreaterEqual(len(got), 3)
                self.assertLess(got.index(new), got.index(old))  # the newest bundle first

    def test_sandbox_ignores_path_and_takes_the_env_cli(self):
        home = self.tmp / ARABIC_HOME
        old, new = self.bundles(home, True)
        on_path = touch(self.tmp / "on path" / ("claude.exe" if IS_WIN else "claude"))
        if not IS_WIN:
            os.chmod(on_path, 0o755)
        env = {"PATH": str(on_path.parent), "WNC_CLAUDE_CLI": str(FAKE_CLAUDE)}
        with mock.patch.dict(os.environ, {"PATH": str(on_path.parent)}):
            real = self.cl.claude_candidates(env, home, "win32", False)
            sand = self.cl.claude_candidates(env, home, "win32", True)
        self.assertIn(norm(on_path), [norm(p) for p in real])  # the test machine's PATH search does work
        self.assertNotIn(str(FAKE_CLAUDE), [str(p) for p in real])  # WNC_CLAUDE_CLI is a sandbox-only switch
        self.assertEqual(sand, [FAKE_CLAUDE, new, old])  # env CLI, then the bundles only: no PATH, no fixed paths
        sand2 = self.cl.claude_candidates({"CLAUDE_CLI": str(FAKE_CLAUDE)}, home, "win-x64", True)
        self.assertEqual(sand2[0], FAKE_CLAUDE)


class TestSettingsMerge(unittest.TestCase):
    MKT = {"thewhynot-ai": {"source": {"source": "directory", "path": "C:\\Users\\x\\.whynot-cut\\marketplace"}}}

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.f = Path(self._td.name) / ARABIC_HOME / ".claude" / "settings.json"
        self.cl = claude_module()

    def backups(self):
        return sorted(self.f.parent.glob("settings.json.whynot-backup-*")) if self.f.parent.is_dir() else []

    def read(self):
        return json.loads(self.f.read_text(encoding="utf-8"))

    def merge(self, **kw):
        kw.setdefault("marketplace", self.MKT)
        kw.setdefault("plugin_id", PID)
        return self.cl.merge_claude_settings(self.f, **kw)

    def test_absent_file_is_created_without_a_backup(self):
        r = self.merge()
        self.assertTrue(r["changed"])
        self.assertIsNone(r["backup"])
        self.assertEqual(self.read(), {"extraKnownMarketplaces": self.MKT, "enabledPlugins": {PID: True}})
        raw = self.f.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertIn(b'\n  "extraKnownMarketplaces": {', raw)  # indent 2
        self.assertEqual(self.backups(), [])

    def test_bom_and_unusual_keys_kept_with_one_exact_backup(self):
        orig = ("\ufeff" + '{"theme":"dark","enabledPlugins":{"x@y":true},"zeta":{"عربي":"نص"}}').encode("utf-8")
        touch(self.f, orig)
        r = self.merge(env={"A": "1"})
        self.assertTrue(r["changed"])
        self.assertEqual(self.backups(), [Path(r["backup"])])
        self.assertEqual(Path(r["backup"]).read_bytes(), orig)
        d = self.read()
        self.assertEqual(list(d), ["theme", "enabledPlugins", "zeta", "extraKnownMarketplaces", "env"])
        self.assertEqual(d["enabledPlugins"], {"x@y": True, PID: True})
        self.assertEqual((d["theme"], d["zeta"], d["env"]), ("dark", {"عربي": "نص"}, {"A": "1"}))
        self.assertIn("عربي".encode("utf-8"), self.f.read_bytes())  # ensure_ascii=False
        before = self.f.read_bytes()
        r2 = self.merge(env={"A": "1"})
        self.assertEqual((r2["changed"], r2["backup"]), (False, None))
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.f.read_bytes(), before)

    def test_invalid_json_is_left_byte_identical(self):
        for orig in (b'{"a":1,}', b'[1, 2]', b'{"enabledPlugins": ["not", "an", "object"]}', b'\xff\xfe{'):
            with self.subTest(orig=orig):
                touch(self.f, orig)
                with self.assertRaises(self.cl.SettingsUnreadable) as cm:
                    self.merge(env={"CLAUDE_CODE_GIT_BASH_PATH": "C:\\g\\bin\\bash.exe"})
                self.assertEqual(self.f.read_bytes(), orig)
                self.assertEqual(self.backups(), [])
                snip = json.loads(cm.exception.snippet)
                self.assertEqual(snip, {"extraKnownMarketplaces": self.MKT, "enabledPlugins": {PID: True},
                                        "env": {"CLAUDE_CODE_GIT_BASH_PATH": "C:\\g\\bin\\bash.exe"}})
                self.assertTrue(cm.exception.reason)

    def test_reel_editor_is_switched_off_only_when_present(self):
        touch(self.f, json.dumps({"enabledPlugins": {"reel-editor@local-desktop-app-uploads": True,
                                                     "other@m": True}}).encode())
        r = self.merge(disable=["reel-editor@*"])
        self.assertEqual(r["disabled"], ["reel-editor@local-desktop-app-uploads"])
        self.assertEqual(self.read()["enabledPlugins"], {"reel-editor@local-desktop-app-uploads": False,
                                                         "other@m": True, PID: True})
        self.assertEqual(self.merge(disable=["reel-editor@*"])["disabled"], [])  # already off: nothing to do
        self.f.unlink()
        r = self.merge(disable=["reel-editor@*"])
        self.assertEqual(r["disabled"], [])
        self.assertEqual(self.read()["enabledPlugins"], {PID: True})  # never added when absent

    def test_env_merged_key_by_key_and_our_marketplace_replaces_theirs(self):
        other = {"source": {"source": "github", "repo": "someone/else"}}
        touch(self.f, json.dumps({"env": {"KEEP": "1", "CLAUDE_CODE_GIT_BASH_PATH": "old"},
                                  "extraKnownMarketplaces": {"thewhynot-ai": {"source": {"source": "github",
                                                                                         "repo": "x/y"}},
                                                             "other": other}}).encode())
        self.merge(plugin_id=None, env={"CLAUDE_CODE_GIT_BASH_PATH": "new"})
        d = self.read()
        self.assertEqual(d["env"], {"KEEP": "1", "CLAUDE_CODE_GIT_BASH_PATH": "new"})
        self.assertEqual(d["extraKnownMarketplaces"], {"thewhynot-ai": self.MKT["thewhynot-ai"], "other": other})
        self.assertNotIn("enabledPlugins", d)

    def test_dry_run_writes_nothing(self):
        self.assertTrue(self.merge(dry_run=True)["changed"])
        self.assertFalse(self.f.exists())

    def test_lone_surrogate_leaves_the_file_and_no_backup(self):
        orig = b'{"x": "\\ud800"}'  # parses to a lone surrogate, which UTF-8 cannot encode
        touch(self.f, orig)
        with self.assertRaises(self.cl.SettingsUnreadable):
            self.merge()
        self.assertEqual(self.f.read_bytes(), orig)
        self.assertEqual(self.backups(), [])
        self.assertEqual(sorted(p.name for p in self.f.parent.iterdir()), ["settings.json"])  # no temp file either

    def test_file_mode_is_kept_on_the_file_and_its_backup(self):
        touch(self.f, b'{"theme": "dark"}')
        if not IS_WIN:
            os.chmod(self.f, 0o600)
        want = os.stat(self.f).st_mode & 0o777
        with mock.patch("os.chmod", wraps=os.chmod) as ch:
            r = self.merge()
        modes = {Path(c.args[0]).name.startswith((".settings.json", "settings.json.whynot-backup-")): c.args[1]
                 for c in ch.call_args_list}
        self.assertEqual(modes, {True: want})  # the temp file (before the replace) and the backup
        self.assertEqual(len(ch.call_args_list), 2)
        if not IS_WIN:
            self.assertEqual(os.stat(self.f).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(r["backup"]).st_mode & 0o777, 0o600)


class TestUnmerge(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        tmp = Path(self._td.name)
        self.f = tmp / ARABIC_HOME / ".claude" / "settings.json"
        self.git = tmp / ARABIC_HOME / "AppData" / "Local" / "WhyNotCut" / "git"
        self.other = {"source": {"source": "github", "repo": "someone/else"}}
        self.elsewhere = str(tmp / "Program Files" / "Git" / "bin" / "bash.exe")
        touch(self.f, json.dumps({
            "theme": "dark",
            "extraKnownMarketplaces": {"thewhynot-ai": {"source": {"source": "directory", "path": "x"}},
                                       "other": self.other},
            "enabledPlugins": {PID: True, "x@y": True},
            "env": {"CLAUDE_CODE_GIT_BASH_PATH": str(self.git / "bin" / "bash.exe"), "ELSEWHERE": self.elsewhere,
                    "PLAIN": "1"}}, ensure_ascii=False).encode("utf-8"))
        self.cl = claude_module()

    def unmerge(self):
        return self.cl.unmerge_claude_settings(self.f, marketplace_name="thewhynot-ai", plugin_id=PID,
                                               env_keys_if_under={"CLAUDE_CODE_GIT_BASH_PATH": self.git,
                                                                  "ELSEWHERE": self.git})

    def test_removes_only_ours(self):
        orig = self.f.read_bytes()
        r = self.unmerge()
        self.assertTrue(r["changed"])
        self.assertEqual(Path(r["backup"]).read_bytes(), orig)
        d = json.loads(self.f.read_text(encoding="utf-8"))
        self.assertEqual(d, {"theme": "dark", "extraKnownMarketplaces": {"other": self.other},
                             "enabledPlugins": {"x@y": True}, "env": {"ELSEWHERE": self.elsewhere, "PLAIN": "1"}})
        r2 = self.unmerge()
        self.assertEqual((r2["changed"], r2["backup"]), (False, None))

    def test_absent_file_is_left_absent(self):
        self.f.unlink()
        self.assertEqual(self.unmerge()["changed"], False)
        self.assertFalse(self.f.exists())


class TestMarketplaceEntry(unittest.TestCase):
    def test_placeholder_is_the_managed_directory_and_a_pin_is_the_url(self):
        cl = claude_module()
        paths = base.Paths.from_env(str(Path(tempfile.gettempdir()) / ARABIC_HOME), env={})
        for url in (base.PLACEHOLDER, None):
            comp = json.loads(json.dumps(CLAUDE_COMP))
            comp["marketplace"]["url"] = url
            self.assertEqual(cl.marketplace_entry(comp, paths),
                             {"source": {"source": "directory", "path": str(paths.marketplace_dir)}})
        comp = json.loads(json.dumps(CLAUDE_COMP))
        comp["marketplace"]["url"] = "https://dl.example/claude/marketplace.json"
        self.assertEqual(cl.marketplace_entry(comp, paths),
                         {"source": {"source": "url", "url": "https://dl.example/claude/marketplace.json"},
                          "autoUpdate": True})


def make_marketplace_src(root: Path, version: bytes = b"v1") -> Path:
    """A folder shaped like the installer zip / the repo: .claude-plugin/marketplace.json + whynot-cut/."""
    touch(root / ".claude-plugin" / "marketplace.json", b'{"name": "thewhynot-ai", "plugins": []}')
    touch(root / "whynot-cut" / ".claude-plugin" / "plugin.json", b'{"name": "whynot-cut"}')
    touch(root / "whynot-cut" / "engine" / "x.py", version)
    touch(root / "whynot-cut" / "engine" / "__pycache__" / "x.cpython-312.pyc", b"pyc")
    touch(root / "whynot-cut" / "engine" / "y.pyc", b"pyc")
    touch(root / "whynot-cut" / ".claude" / "whynot-cut.local.md", b"editor prefs")
    touch(root / "whynot-cut" / ".git" / "HEAD", b"ref")
    touch(root / "docs" / "notes.md", b"not part of the marketplace")
    return root / "whynot-cut"


class TestRefreshMarketplace(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        tmp = Path(self._td.name)
        self.src = tmp / "zip root"
        make_marketplace_src(self.src)
        self.paths = base.Paths.from_env(str(tmp / ARABIC_HOME), env={})
        self.cl = claude_module()

    def test_copies_the_two_entries_and_keeps_one_prev(self):
        m = self.paths.marketplace_dir
        self.assertTrue(self.cl.refresh_marketplace_dir(self.src, self.paths))
        self.assertEqual(sorted(p.name for p in m.iterdir()), [".claude-plugin", "whynot-cut"])
        self.assertTrue((m / ".claude-plugin" / "marketplace.json").is_file())
        self.assertEqual((m / "whynot-cut" / "engine" / "x.py").read_bytes(), b"v1")
        for gone in ("engine/__pycache__", "engine/y.pyc", ".claude/whynot-cut.local.md", ".git"):
            self.assertFalse((m / "whynot-cut" / gone).exists(), gone)
        touch(self.src / "whynot-cut" / "engine" / "x.py", b"v2")
        self.assertTrue(self.cl.refresh_marketplace_dir(self.src, self.paths))
        self.assertEqual((m / "whynot-cut" / "engine" / "x.py").read_bytes(), b"v2")
        prev = self.paths.whynot / "marketplace.prev"
        self.assertEqual((prev / "whynot-cut" / "engine" / "x.py").read_bytes(), b"v1")
        touch(self.src / "whynot-cut" / "engine" / "x.py", b"v3")
        self.assertTrue(self.cl.refresh_marketplace_dir(self.src, self.paths))
        self.assertEqual((prev / "whynot-cut" / "engine" / "x.py").read_bytes(), b"v2")
        self.assertEqual(sorted(p.name for p in self.paths.whynot.iterdir()), ["marketplace", "marketplace.prev"])

    def test_no_op_when_the_source_is_the_managed_dir(self):
        self.assertTrue(self.cl.refresh_marketplace_dir(self.src, self.paths))
        self.assertFalse(self.cl.refresh_marketplace_dir(self.paths.marketplace_dir, self.paths))
        self.assertEqual(sorted(p.name for p in self.paths.whynot.iterdir()), ["marketplace"])


class TestStepClaude(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.plugin = make_marketplace_src(self.tmp / "zip root")
        self.comp = json.loads(json.dumps(CLAUDE_COMP))
        self.log = self.tmp / "claude-calls.jsonl"
        env = mock.patch.dict(os.environ, {"WNC_CLAUDE_CLI": str(FAKE_CLAUDE), "FAKE_CLAUDE_LOG": str(self.log)})
        env.start()
        self.addCleanup(env.stop)
        for k in ("CLAUDE_CLI", "FAKE_CLAUDE_VERSION", "FAKE_CLAUDE_FAIL", "FAKE_CLAUDE_INSTALLED"):
            os.environ.pop(k, None)
        self.cl = claude_module()

    def ctx(self, **args):
        return make_ctx(self.home, self.comp, self.plugin, "win-x64", **args)

    def records(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def calls(self):
        """Every CLI call except `--version`."""
        return [r["argv"] for r in self.records() if r["argv"] != ["--version"]]

    def settings(self, ctx):
        return json.loads(ctx.paths.settings_file.read_text(encoding="utf-8"))

    def backups(self, ctx):
        return sorted(ctx.paths.claude_dir.glob("settings.json.whynot-backup-*"))

    def add(self, ctx):
        return ["plugin", "marketplace", "add", str(ctx.paths.marketplace_dir)]

    INSTALL = ["plugin", "install", PID, "--scope", "user"]

    def test_fresh_install_with_the_cli_then_update_on_a_rerun(self):
        ctx = self.ctx()
        r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(self.calls(), [self.add(ctx), self.INSTALL])
        self.assertTrue(all(x["CLAUDE_CONFIG_DIR"] == str(ctx.paths.claude_dir) for x in self.records()))
        s = self.settings(ctx)
        self.assertEqual(s["extraKnownMarketplaces"]["thewhynot-ai"],
                         {"source": {"source": "directory", "path": str(ctx.paths.marketplace_dir)}})
        self.assertEqual(s["enabledPlugins"], {PID: True})
        self.assertTrue((ctx.paths.marketplace_dir / ".claude-plugin" / "marketplace.json").is_file())
        rec = ctx.state.data["claude"]
        self.assertEqual((rec["method"], rec["settings_backup"]), ("cli", None))
        self.assertEqual(rec["marketplace"], s["extraKnownMarketplaces"]["thewhynot-ai"])
        saved = json.loads(ctx.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["claude"]["method"], "cli")
        self.assertEqual(saved["steps"]["claude"]["status"], "ok")
        # re-run: the plugin is listed in installed_plugins.json -> `plugin update`; settings unchanged, no backup
        self.log.unlink()
        ctx2 = self.ctx()
        r2 = self.cl.step_claude(ctx2)
        self.assertEqual(r2.status, "ok", r2.detail)
        self.assertEqual(self.calls(), [self.add(ctx2), ["plugin", "update", PID]])
        self.assertEqual(self.backups(ctx2), [])
        self.assertIsNone(ctx2.state.data["claude"]["settings_backup"])

    def test_already_installed_is_updated(self):
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_INSTALLED": "1"}):
            ctx = self.ctx()
            r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(self.calls(), [self.add(ctx), ["plugin", "update", PID]])

    def test_legacy_marketplace_is_removed_first_and_reel_editor_switched_off(self):
        ctx = self.ctx()
        old_dir = str(self.tmp / "old dev" / "WhyNotCut")
        touch(ctx.paths.claude_dir / "plugins" / "known_marketplaces.json", json.dumps({"thewhynot-ai": {
            "source": {"source": "directory", "path": old_dir}, "installLocation": old_dir,
            "lastUpdated": "2026-01-01T00:00:00.000Z"}}).encode())
        orig = json.dumps({"enabledPlugins": {"reel-editor@local-desktop-app-uploads": True, PID: True},
                           "extraKnownMarketplaces": {"thewhynot-ai": {"source": {"source": "directory",
                                                                                  "path": old_dir}}}}).encode()
        touch(ctx.paths.settings_file, orig)
        r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(self.calls(), [["plugin", "marketplace", "remove", "thewhynot-ai"], self.add(ctx),
                                        self.INSTALL])
        s = self.settings(ctx)
        self.assertEqual(s["enabledPlugins"], {"reel-editor@local-desktop-app-uploads": False, PID: True})
        self.assertEqual(s["extraKnownMarketplaces"]["thewhynot-ai"]["source"]["path"], str(ctx.paths.marketplace_dir))
        [bk] = self.backups(ctx)
        self.assertEqual(bk.read_bytes(), orig)
        self.assertEqual(ctx.state.data["claude"]["settings_backup"], str(bk))
        self.assertEqual(ctx.state.data["claude"]["disabled"], ["reel-editor@local-desktop-app-uploads"])

    def test_legacy_without_a_cli_is_amber(self):
        os.environ.pop("WNC_CLAUDE_CLI")
        ctx = self.ctx()
        touch(ctx.paths.claude_dir / "plugins" / "known_marketplaces.json", json.dumps({"thewhynot-ai": {
            "source": {"source": "github", "repo": "someone/whynot"}}}).encode())
        r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("marketplace remove thewhynot-ai", r.needs_you)
        self.assertEqual(self.settings(ctx)["enabledPlugins"], {PID: True})  # (b) still ran

    @unittest.skipUnless(IS_WIN, "paths compare case-insensitively on Windows only")
    def test_same_directory_in_another_case_is_not_legacy(self):
        ctx = self.ctx()
        touch(ctx.paths.claude_dir / "plugins" / "known_marketplaces.json", json.dumps({"thewhynot-ai": {
            "source": {"source": "directory", "path": str(ctx.paths.marketplace_dir).upper() + "\\"}}}).encode())
        self.assertEqual(self.cl.step_claude(ctx).status, "ok")
        self.assertEqual(self.calls(), [self.add(ctx), self.INSTALL])

    def test_old_claude_is_amber_and_settings_still_merged(self):
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_VERSION": "2.1.100"}):
            ctx = self.ctx()
            r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("update Claude", r.detail)
        self.assertIn("2.1.224", r.needs_you)
        self.assertEqual(self.calls(), [])  # no plugin command on a CLI older than claude_code.min
        self.assertEqual(self.settings(ctx)["enabledPlugins"], {PID: True})

    def test_no_cli_merges_the_settings_only(self):
        os.environ.pop("WNC_CLAUDE_CLI")
        ctx = self.ctx()
        r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(self.records(), [])
        self.assertEqual(self.settings(ctx)["enabledPlugins"], {PID: True})
        self.assertEqual(ctx.state.data["claude"]["method"], "settings")
        self.assertTrue((ctx.paths.marketplace_dir / ".claude-plugin" / "marketplace.json").is_file())

    def test_cli_failure_is_amber_and_settings_still_merged(self):
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_FAIL": "install"}):
            ctx = self.ctx()
            r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("install", r.detail)
        self.assertEqual(self.settings(ctx)["enabledPlugins"], {PID: True})
        self.assertEqual(ctx.state.data["claude"]["method"], "settings")

    def test_unreadable_settings_is_amber_with_the_json_to_paste_and_no_cli_call(self):
        # fake_claude REPLACES a settings.json it cannot parse on `plugin install` / `marketplace add`: the file
        # staying byte-identical proves the CLI was never let near it
        for orig in (b'{"a":1,}', b'{"x": "\\ud800"}'):  # invalid JSON; a lone surrogate (parses, cannot be written)
            with self.subTest(orig=orig):
                if self.log.exists():
                    self.log.unlink()
                ctx = self.ctx()
                touch(ctx.paths.settings_file, orig)
                r = self.cl.step_claude(ctx)
                self.assertEqual(r.status, "amber", r.detail)
                self.assertIn("not valid JSON", r.detail)
                self.assertIn("CLI was not run", r.detail)
                snip = json.loads(r.needs_you)
                self.assertEqual(snip["enabledPlugins"], {PID: True})
                self.assertIn("thewhynot-ai", snip["extraKnownMarketplaces"])
                self.assertEqual(ctx.paths.settings_file.read_bytes(), orig)
                self.assertEqual(self.backups(ctx), [])
                self.assertEqual(self.records(), [])  # not even `--version`; above all no `plugin install`

    def test_first_install_keeps_exactly_one_backup_of_the_original(self):
        """The CLI writes settings.json too (fake_claude does, like the real one): the one backup must hold the
        editor's bytes from before the step, not what the CLI left."""
        ctx = self.ctx()
        orig = ("﻿" + '{"theme": "dark",\n "enabledPlugins": {"x@y": true}}').encode("utf-8")
        touch(ctx.paths.settings_file, orig)
        r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(self.calls(), [self.add(ctx), self.INSTALL])
        [bk] = self.backups(ctx)
        self.assertEqual(bk.read_bytes(), orig)
        self.assertEqual(ctx.state.data["claude"]["settings_backup"], str(bk))
        s = self.settings(ctx)
        self.assertEqual((s["theme"], s["enabledPlugins"]), ("dark", {"x@y": True, PID: True}))
        # a re-run that changes nothing leaves no backup behind
        ctx2 = self.ctx()
        self.assertEqual(self.cl.step_claude(ctx2).status, "ok")
        self.assertEqual(self.backups(ctx2), [bk])
        self.assertIsNone(ctx2.state.data["claude"]["settings_backup"])

    def test_cli_that_cannot_start_is_not_used(self):
        broken = touch(self.tmp / "broken cli" / ("claude.exe" if IS_WIN else "claude"), b"not a program")
        with mock.patch.dict(os.environ, {"WNC_CLAUDE_CLI": str(broken)}):
            ctx = self.ctx()
            r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("did not answer (`--version` exit 127", r.detail)
        self.assertEqual(self.settings(ctx)["enabledPlugins"], {PID: True})
        self.assertEqual(ctx.state.data["claude"]["method"], "settings")

    def test_cli_that_times_out_gets_no_further_call(self):
        seen = []

        def fake_run(ctx, cmd, timeout, cwd=None, *, split=False):
            seen.append([str(c) for c in cmd][-1:])
            return 124, "(timed out after 300 s)"

        old_dir = str(self.tmp / "old dev")
        ctx = self.ctx()
        touch(ctx.paths.claude_dir / "plugins" / "known_marketplaces.json", json.dumps({"thewhynot-ai": {
            "source": {"source": "directory", "path": old_dir}}}).encode())
        with mock.patch.object(base, "run_cmd", side_effect=fake_run):
            r = self.cl.step_claude(ctx)
        self.assertEqual(seen, [["--version"]])  # no remove / add / install
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("exit 124", r.detail)
        self.assertIn("marketplace remove thewhynot-ai", r.needs_you)
        self.assertEqual(self.settings(ctx)["enabledPlugins"], {PID: True})

    def test_url_pin_adds_the_url_and_needs_no_marketplace_dir(self):
        url = "https://dl.example/claude/marketplace.json"
        self.comp["marketplace"]["url"] = url
        ctx = self.ctx()
        self.assertEqual(self.cl.step_claude(ctx).status, "ok")
        self.assertEqual(self.calls(), [["plugin", "marketplace", "add", url], self.INSTALL])
        self.assertEqual(self.settings(ctx)["extraKnownMarketplaces"]["thewhynot-ai"],
                         {"source": {"source": "url", "url": url}, "autoUpdate": True})
        self.assertFalse(ctx.paths.marketplace_dir.exists())

    def test_dry_run_writes_and_runs_nothing(self):
        ctx = self.ctx(dry_run=True)
        r = self.cl.step_claude(ctx)
        self.assertEqual(r.status, "skipped", r.detail)
        self.assertEqual(self.records(), [])
        self.assertFalse(ctx.paths.claude_dir.exists())
        self.assertFalse(ctx.paths.marketplace_dir.exists())
        self.assertFalse(ctx.paths.state_file.exists())

    @unittest.skipUnless(IS_WIN, "the .cmd wrapper is for Windows")
    def test_cmd_wrapper_runs_fake_claude(self):
        with mock.patch.dict(os.environ, {"WNC_CLAUDE_CLI": str(FIXTURES / "fake_claude.cmd"),
                                          "FAKE_CLAUDE_PYTHON": sys.executable, "FAKE_CLAUDE_VERSION": "2.1.999"}):
            ctx = self.ctx()
            [cli_path] = self.cl.claude_candidates(os.environ, ctx.paths.home, "win-x64", True)
            rc, out = base.run_cmd(ctx, self.cl.claude_command(cli_path) + ["--version"], 60)
        self.assertEqual((rc, out.strip()), (0, "2.1.999 (Claude Code)"))

    def test_registered_without_needs(self):
        needs = {n: d for n, _f, d in cli.STEPS}
        self.assertEqual((needs["gitbash"], needs["claude"]), ((), ()))


class TestGitBash(unittest.TestCase):
    ZIP = ffmpeg_zip({"bin/bash.exe": b"MZ bash", "cmd/git.exe": b"MZ git"})

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.srv = Served(self, {"/git/PortableGit.zip": self.ZIP})
        self.comp = {"schema": 1, "git": {"version": "2.56.0.windows.2", "assets": {"win-x64": {
            "url": self.srv.base + "/git/PortableGit.zip", "sha256": sha(self.ZIP), "archive": "zip"}}}}
        self.cl = claude_module()

    def ctx(self, plat="win-x64", **args):
        return make_ctx(self.home, self.comp, SK, plat, **args)

    def managed(self, ctx):
        return ctx.paths.localappdata / "WhyNotCut" / "git" / "bin" / "bash.exe"

    def env_of(self, ctx):
        return json.loads(ctx.paths.settings_file.read_text(encoding="utf-8")).get("env", {})

    def test_mac_is_skipped(self):
        for plat in ("mac-arm64", "mac-x64"):
            ctx = self.ctx(plat)
            self.assertEqual(self.cl.step_gitbash(ctx).status, "skipped")
            self.assertFalse(ctx.paths.settings_file.exists())
        self.assertEqual(self.srv.srv.hits, [])

    def test_managed_bash_already_present(self):
        ctx = self.ctx()
        touch(self.managed(ctx), b"MZ bash")
        r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(self.env_of(ctx), {"CLAUDE_CODE_GIT_BASH_PATH": str(self.managed(ctx))})
        self.assertEqual(self.srv.srv.hits, [])

    def test_missing_is_downloaded_extracted_and_set(self):
        ctx = self.ctx()
        r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        bash = self.managed(ctx)
        self.assertEqual(bash.read_bytes(), b"MZ bash")
        self.assertEqual(self.env_of(ctx), {"CLAUDE_CODE_GIT_BASH_PATH": str(bash)})
        self.assertEqual(sorted(p.name for p in bash.parents[2].iterdir()), ["git"])  # no staging left
        self.assertEqual((ctx.state.data["gitbash"]["path"], ctx.state.data["gitbash"]["managed"]), (str(bash), True))
        hits = len(self.srv.srv.hits)
        ctx2 = self.ctx()
        self.assertEqual(self.cl.step_gitbash(ctx2).status, "ok")
        self.assertEqual(len(self.srv.srv.hits), hits)
        self.assertEqual(ctx2.state.data["gitbash"], {"path": str(bash), "managed": True,
                                                      "version": "2.56.0.windows.2"})
        self.assertEqual(sorted(ctx2.paths.claude_dir.glob("settings.json.whynot-backup-*")), [])

    def test_settings_value_elsewhere_is_kept(self):
        ctx = self.ctx()
        mine = touch(self.tmp / "Portable Git" / "bin" / "bash.exe", b"MZ")
        orig = json.dumps({"env": {"CLAUDE_CODE_GIT_BASH_PATH": str(mine)}}).encode()
        touch(ctx.paths.settings_file, orig)
        r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(ctx.paths.settings_file.read_bytes(), orig)
        self.assertEqual(self.srv.srv.hits, [])
        self.assertFalse(self.managed(ctx).exists())

    def test_find_git_bash_in_the_sandbox(self):
        ctx = self.ctx()
        pf = touch(self.tmp / "Program Files" / "Git" / "bin" / "bash.exe")
        with mock.patch.dict(os.environ, {"ProgramFiles": str(self.tmp / "Program Files")}):
            self.assertEqual(self.cl.find_git_bash(ctx.paths, {}, True), (None, False))
            user = touch(ctx.paths.localappdata / "Programs" / "Git" / "bin" / "bash.exe")
            self.assertEqual(self.cl.find_git_bash(ctx.paths, {}, True), (user, False))
            self.assertEqual(self.cl.find_git_bash(ctx.paths, {"CLAUDE_CODE_GIT_BASH_PATH": str(pf)}, True),
                             (pf, True))
            # a settings value that does not exist is ignored
            self.assertEqual(self.cl.find_git_bash(ctx.paths, {"CLAUDE_CODE_GIT_BASH_PATH": str(self.tmp / "no")},
                                                   True), (user, False))

    def test_placeholder_pin_is_amber(self):
        self.comp["git"]["assets"]["win-x64"]["url"] = base.PLACEHOLDER
        ctx = self.ctx()
        r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("install Git for Windows", r.needs_you)
        self.assertEqual(self.srv.srv.hits, [])
        self.assertFalse(ctx.paths.settings_file.exists())

    def test_wrong_sha_is_red_and_installs_nothing(self):
        self.comp["git"]["assets"]["win-x64"]["sha256"] = "0" * 64
        ctx = self.ctx()
        r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "red")
        self.assertIn("sha256", r.detail)
        self.assertFalse((ctx.paths.localappdata / "WhyNotCut").exists())
        self.assertFalse(ctx.paths.settings_file.exists())

    def test_7z_sfx_is_run_into_a_staging_folder(self):
        """No real SFX ever runs in a test: run_cmd is replaced by a stand-in that 'extracts' bin/bash.exe."""
        self.comp["git"]["assets"]["win-x64"]["archive"] = "7z-sfx"
        seen = []

        def fake_run(ctx, cmd, timeout, cwd=None, *, split=False):
            seen.append(([str(c) for c in cmd], timeout))
            out = Path(str(cmd[1])[2:])
            touch(out / "bin" / "bash.exe", b"MZ sfx bash")
            return 0, "Everything is Ok"

        ctx = self.ctx()
        with mock.patch.object(base, "run_cmd", side_effect=fake_run):
            r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        [(cmd, timeout)] = seen
        self.assertEqual(timeout, 900)
        self.assertEqual(Path(cmd[0]).parent, ctx.paths.downloads_dir)
        self.assertTrue(cmd[1].startswith("-o"))
        self.assertNotEqual(Path(cmd[1][2:]), self.managed(ctx).parents[1])  # staged, then renamed into place
        self.assertEqual(cmd[2:], ["-y"])
        self.assertEqual(self.managed(ctx).read_bytes(), b"MZ sfx bash")
        self.assertEqual(self.env_of(ctx), {"CLAUDE_CODE_GIT_BASH_PATH": str(self.managed(ctx))})

    def test_sfx_partial_extraction_is_amber_and_cleaned(self):
        """The real PortableGit SFX exits 1 after a PARTIAL extraction under a long base path (MAX_PATH)."""
        self.comp["git"]["assets"]["win-x64"]["archive"] = "7z-sfx"
        staged = []

        def fake_run(ctx, cmd, timeout, cwd=None, *, split=False):
            out = Path(str(cmd[1])[2:])
            staged.append(out)
            touch(out / "usr" / "share" / "deep" / "partial.txt", b"partial")
            return 1, "ERROR: Can not open output file : The filename or extension is too long."

        ctx = self.ctx()
        with mock.patch.object(base, "run_cmd", side_effect=fake_run):
            r = self.cl.step_gitbash(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("Git for Windows could not be set up; install it from https://git-scm.com/download/win",
                      r.detail)
        self.assertIn("https://git-scm.com/download/win", r.needs_you)
        [out] = staged
        self.assertFalse(out.exists())  # the partial staging tree is removed
        self.assertFalse(self.managed(ctx).parents[1].exists())
        self.assertFalse(ctx.paths.settings_file.exists())  # no env merged

    def test_dry_run_writes_nothing(self):
        ctx = self.ctx(dry_run=True)
        self.assertEqual(self.cl.step_gitbash(ctx).status, "skipped")
        self.assertFalse(ctx.paths.claude_dir.exists())
        self.assertFalse((ctx.paths.localappdata / "WhyNotCut").exists())
        self.assertEqual(self.srv.srv.hits, [])


if __name__ == "__main__":
    unittest.main()
