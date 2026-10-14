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
  * system.py / adobe.py / fonts.py (task 4): preflight (free space red / amber, Arabic home, OneDrive, sandbox reads no
    registry; red stops `install` with 2 before any download), questions (flags > preferences file > defaults, `ar`,
    the clients folder never created), the Adobe hook (placeholders skipped, unsigned ZXP amber, signed ZXP extracted
    with one .prev, a running host amber, UXP command recorded, no code sets Adobe's debug flag), fonts (fake
    LOCALAPPDATA + registry-fonts.json, ~/Library/Fonts, a different file kept, bad sha red), model_for and the model
    step (never spawned in tests), settings / doctor through the stub engine of make_fixture_plugin(), the checklist,
    launch, a dry run that writes nothing, and a whole sandboxed install (twice: no new download).
  * the shells (task 5, T7.2): install.ps1 / bootstrap.ps1 under Windows PowerShell and install.sh / bootstrap.sh under
    bash (Git Bash on Windows with WNC_TEST_PLATFORM=mac-arm64), end to end in a home with a space and Arabic letters:
    the uv archive downloaded and verified even with WNC_TEST_UV, one log shared with the core, the real ~/.claude and
    ~/.whynot-cut untouched, a dry run leaves the home empty, a bad sha256 exits 3 naming the file, uv at the pinned
    version is not downloaded again, the one-liner modes (-Source zip + sha256; `irm | iex` and the script-block form
    keep the session; no -Source = the H3 line in English and Arabic, exit 2; `bash -s < install.sh` does not hang),
    Git Bash without the test platform exits 2, plus static checks (ASCII .ps1, LF .sh, the step list, the README).
    Temp folders use TempDir (cleanup retried: Windows WinError 32 / 145).
  * uninstall (task 6, T7.8), after a whole sandboxed install with a signed CEP panel, the UXP command and two fonts:
    settings.json loses only our keys (the original bytes backed up; unreadable JSON = no CLI call, byte-identical),
    `claude plugin uninstall` + `marketplace remove`, the CEP folder / fonts / registry values / marketplace folder
    gone, the engine home kept; --remove-engine keeps models/, a clients folder with `.whynot-client` (also the
    preferences' clients_root) and the target of a link, and lists python/ + bin/ in .delete-after-exit;
    --remove-models; a running Adobe host keeps the panel; recorded paths outside their folders are left alone; an
    engine home that is the user folder is refused; a dry run changes nothing. install.ps1 -Uninstall -RemoveEngine
    and install.sh --uninstall --remove-engine after an install: no download, the bootstrap deletes python/ and bin/
    after the core exits (a junction inside is removed as a link). Fix round 1: a tampered .delete-after-exit
    (`<root>//`, models/, `..` paths, an outside path, an illegal name) deletes nothing but python/ and bin/ in both
    shells; a running host with --remove-engine keeps a small state.json so the next uninstall removes the panel; the
    Git Bash entry stays until --remove-engine; the UXP id recorded at install wins; a strong engine-home mark is
    required; the newest engine Python is chosen by version number in both shells.
  * task 7: tools/release.py (stub) on a temp COPY of components.json: `components --check` lists the placeholder
    paths, `--fill-artefacts` pins adobe/*.zxp|*.ccx (file + sha256) changing only those value lines (two candidates =
    exit 2, nothing written), its docstring names the T7.6 executor steps and the release index; static checks: the
    PowerShell parser on every .ps1 and `bash -n` on every .sh (never skipped when the shell exists), PSScriptAnalyzer
    (WHYNOTCUT_PSSA_PATH) without Error findings and shellcheck (WHYNOTCUT_SHELLCHECK) exit 0 (skipped when absent;
    the lint variables are never named WNC_*: other suites assert that none reaches the engine); the README's
    Verified / Not verified section; TestLiveSmoke (WNC_INSTALLER_LIVE=1 only, real network): the pinned uv, `uv python
    install --no-bin --no-registry`, the runtime step with tests/fixtures/installer/live_lock.txt (six, hashed), and
    no ~/.local/bin python or HKCU Python\\Astral key left in the real profile.
Never touches the real ~/.whynot-cut or ~/.claude: every Paths is a sandbox home in a temp folder, and no real
network is used (artefacts come from a 127.0.0.1 http.server started here, or file://) - except by TestLiveSmoke,
which runs only with WNC_INSTALLER_LIVE=1.
Run (repo root):
    bash tools/test.sh -p test_installer.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import contextlib
import hashlib
import http.server
import io
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import types
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
# what the installer's State writes (base.is_engine_home: a JSON object, schema 1, a "plugin" key); a bare {} is NOT an
# engine home any more (fix round 2: file names alone can be anyone's)
GENUINE_STATE = b'{"schema": 1, "plugin": "3.0.0", "updated_at": null, "steps": {}}\n'

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


def rmtree_retry(path, attempts: int = 8) -> bool:
    """rmtree that survives Windows' transient refusals (WinError 32 / 145 while the indexer or antivirus still holds a
    file the test just wrote): read-only entries get write permission, short doubling back-off, then give up quietly.
    True when the folder is gone."""
    def fix(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            func(p)
        except OSError:
            pass
    kw = {"onexc": fix} if sys.version_info >= (3, 12) else {"onerror": fix}
    for i in range(attempts):
        if not os.path.lexists(path):
            return True
        try:
            shutil.rmtree(path, **kw)
        except OSError:
            pass
        if not os.path.lexists(path):
            return True
        time.sleep(min(0.05 * 2 ** i, 1.0))
    return not os.path.lexists(path)


class TempDir:
    """tempfile.TemporaryDirectory for these tests: same .name / .cleanup() / `with ... as name`, but the cleanup
    retries and finally ignores what Windows still refuses to delete (a leftover in %TEMP% must not fail a test)."""

    def __init__(self):
        # WHYNOT_TEST_TMP (Addendum F2-T2, as tools/test.sh) keeps test files off the system drive; else %TEMP%
        root = os.environ.get("WHYNOT_TEST_TMP") or None
        if root:
            os.makedirs(root, exist_ok=True)
        self.name = tempfile.mkdtemp(prefix="wnc-", dir=root)

    def cleanup(self) -> None:
        rmtree_retry(self.name)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *exc) -> None:
        self.cleanup()


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
        self._td = TempDir()
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

    def test_child_env_drops_pythonpath_and_pythonhome(self):
        for sandbox in (True, False):
            with self.subTest(sandbox=sandbox):
                p = base.Paths.from_env(str(self.tmp / "h") if sandbox else None,
                                        env={"HOME": str(self.tmp), "USERPROFILE": str(self.tmp)})
                env = p.child_env({"PATH": "keep-me", "PYTHONPATH": str(self.tmp / "evil"),
                                   "PYTHONHOME": str(self.tmp / "other python"), "CLAUDE_CLI": "the real claude"})
                self.assertNotIn("PYTHONPATH", env)
                self.assertNotIn("PYTHONHOME", env)
                self.assertEqual(env["PATH"], "keep-me")
                # a sandbox never hands a developer's real Claude Code CLI to its children
                self.assertEqual("CLAUDE_CLI" in env, not sandbox)


# --------------------------------------------------------------------------------------------- engine home
ENGINE_HOME_ENV = ("WHYNOT_HOME", "CLAUDE_PLUGIN_OPTION_ENGINE_HOME", "REEL_HOME", "CLAUDE_PLUGIN_OPTION_REEL_HOME",
                   "NH_ENV_DIR")


class EngineHomeCases:
    """A fake user home (space + Arabic letters) with the pointer file and settings.json written by each case.
    Every case: (name, writer(home), extra env, expected path relative-to-home or absolute, expected source kind)."""

    @staticmethod
    def pointer(home: Path, obj, raw: bytes = None) -> None:
        touch(home / ".whynot-cut" / "plugin-options.json",
              raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8"))  # raw UTF-8 Arabic

    @staticmethod
    def settings(home: Path, configs) -> None:
        touch(home / ".claude" / "settings.json",
              json.dumps({"theme": "dark", "pluginConfigs": configs}, ensure_ascii=False).encode("utf-8"))

    @classmethod
    def cases(cls, tmp: Path) -> list:
        far = tmp / "engine far محرك"  # Arabic letters: the files carry them as raw UTF-8, never backslash-u escapes
        other = tmp / "engine other محرك"
        third = tmp / "engine third محرك"
        P, S = cls.pointer, cls.settings
        return [
            ("default", lambda h: None, {}, ".whynot-cut", "default"),
            ("pointer", lambda h: P(h, {"engine_home": str(far), "clients_root": ""}), {}, far, "pointer"),
            ("pointer wins over settings",
             lambda h: (P(h, {"engine_home": str(far)}), S(h, {"whynot-cut@thewhynot-ai": {
                 "options": {"engine_home": str(other)}}})), {}, far, "pointer"),
            ("an empty pointer value is the default, settings are not read",
             lambda h: (P(h, {"engine_home": ""}), S(h, {"whynot-cut@thewhynot-ai": {
                 "options": {"engine_home": str(other)}}})), {}, ".whynot-cut", "default"),
            ("a pointer with a BOM is invalid: settings",
             lambda h: (P(h, None, b"\xef\xbb\xbf" + json.dumps({"engine_home": str(far)},
                                                                    ensure_ascii=False).encode("utf-8")),
                        S(h, {"whynot-cut@thewhynot-ai": {"options": {"engine_home": str(other)}}})),
             {}, other, "settings"),
            ("a pointer that is not an object is invalid: settings",
             lambda h: (P(h, [{"engine_home": str(far)}]),
                        S(h, {"whynot-cut@thewhynot-ai": {"options": {"engine_home": str(other)}}})),
             {}, other, "settings"),
            ("a pointer without an engine_home string is invalid: settings",
             lambda h: (P(h, {"engine_home": 5}),
                        S(h, {"whynot-cut@thewhynot-ai": {"options": {"engine_home": str(other)}}})),
             {}, other, "settings"),
            ("settings: our key first, whatever the file order",
             lambda h: S(h, {"whynot-cut@dev": {"options": {"engine_home": str(third)}},
                             "whynot-cut@thewhynot-ai": {"options": {"engine_home": str(other)}}}),
             {}, other, "settings"),
            ("settings: else the first other whynot-cut@ entry that has options",
             lambda h: S(h, {"whynot-cut@thewhynot-ai": {"enabled": True}, "x@y": {"options": {"engine_home": "no"}},
                             "whynot-cut@dev": {"options": {"engine_home": str(third)}},
                             "whynot-cut@zzz": {"options": {"engine_home": str(far)}}}),
             {}, third, "settings"),
            ("settings: options without engine_home is the default",
             lambda h: S(h, {"whynot-cut@thewhynot-ai": {"options": {"clients_root": "x"}},
                             "whynot-cut@dev": {"options": {"engine_home": str(third)}}}),
             {}, ".whynot-cut", "default"),
            ("settings: ~ is the user home", lambda h: S(h, {"whynot-cut@thewhynot-ai": {
                "options": {"engine_home": "~/WhyNot Engine"}}}), {}, "WhyNot Engine", "settings"),
            ("WHYNOT_OPTIONS_FILE moves the pointer",
             lambda h: touch(tmp / "elsewhere" / "opts.json",
                             json.dumps({"engine_home": str(far)}, ensure_ascii=False).encode("utf-8")),
             {"WHYNOT_OPTIONS_FILE": str(tmp / "elsewhere" / "opts.json")}, far, "pointer"),
            ("CLAUDE_CONFIG_DIR moves settings.json",
             lambda h: touch(tmp / "cfg dir" / "settings.json", json.dumps({"pluginConfigs": {
                 "whynot-cut@thewhynot-ai": {"options": {"engine_home": str(other)}}}}, ensure_ascii=False)
                 .encode("utf-8")),
             {"CLAUDE_CONFIG_DIR": str(tmp / "cfg dir")}, other, "settings"),
            ("REEL_HOME beats the pointer", lambda h: P(h, {"engine_home": str(far)}),
             {"REEL_HOME": str(third)}, third, "env:REEL_HOME"),
            ("WHYNOT_HOME beats every other variable", lambda h: None,
             {"WHYNOT_HOME": str(far), "CLAUDE_PLUGIN_OPTION_ENGINE_HOME": str(other)}, far, "env:WHYNOT_HOME"),
            ("the plugin option variable", lambda h: None,
             {"CLAUDE_PLUGIN_OPTION_ENGINE_HOME": str(other), "REEL_HOME": str(third)}, other,
             "env:CLAUDE_PLUGIN_OPTION_ENGINE_HOME"),
        ]


def clean_engine_env(home: Path, **extra) -> dict:
    """os.environ without any engine-home / options / Claude config variable, the user home = `home`."""
    env = {k: v for k, v in os.environ.items()
           if k not in ENGINE_HOME_ENV + ("WHYNOT_OPTIONS_FILE", "CLAUDE_CONFIG_DIR")}
    env.update(HOME=str(home), USERPROFILE=str(home), **extra)
    return env


class TestEngineHome(unittest.TestCase):
    """Outside the sandbox the engine home is resolved exactly like the engine (engine/reel/lib/plat.py
    engine_home, minus its legacy-home fallback); always with an injected env and a temp home, never the real one."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def each_case(self):
        for i, (name, write, extra, want, kind) in enumerate(EngineHomeCases.cases(self.tmp)):
            home = self.tmp / f"case {i}" / ARABIC_HOME
            home.mkdir(parents=True)
            write(home)
            yield name, home, extra, (want if isinstance(want, Path) else home / want), kind

    def test_the_resolver_follows_the_engine_order(self):
        for name, home, extra, want, kind in self.each_case():
            with self.subTest(name):
                env = {"HOME": str(home), "USERPROFILE": str(home), **extra}
                got, src = base.resolve_engine_home(env, home)
                self.assertEqual(norm(got), norm(want), src)
                self.assertEqual(src.split(":", 1)[0] if not src.startswith("env:") else src, kind)

    def test_same_answer_as_the_engine(self):
        from lib import plat  # the engine's own resolver (tests/_isolation.py put engine/reel on sys.path)
        for name, home, extra, want, _kind in self.each_case():
            with self.subTest(name), mock.patch.dict(os.environ, clean_engine_env(home, **extra), clear=True):
                self.assertEqual(norm(base.resolve_engine_home(os.environ, home)[0]), norm(plat.engine_home()))

    @unittest.skipUnless(IS_WIN, "Git-Bash style paths are converted on Windows only")
    def test_git_bash_style_saved_path(self):
        home = self.tmp / "h"
        EngineHomeCases.pointer(home, {"engine_home": "/d/WhyNot Engine"})
        got, src = base.resolve_engine_home({"USERPROFILE": str(home)}, home)
        self.assertEqual(norm(got), norm("D:/WhyNot Engine"))

    def test_the_case_files_carry_raw_utf8_arabic(self):
        arabic = 0
        for name, home, _extra, _want, _kind in self.each_case():
            for f in (home / ".whynot-cut" / "plugin-options.json", home / ".claude" / "settings.json"):
                if f.is_file():
                    self.assertNotIn(b"\\u", f.read_bytes(), name)
                    arabic += "محرك".encode("utf-8") in f.read_bytes()
        self.assertGreaterEqual(arabic, 10)

    def test_paths_resolve_it_outside_and_inside_the_sandbox(self):
        home = self.tmp / ARABIC_HOME
        far = self.tmp / "engine far"
        EngineHomeCases.pointer(home, {"engine_home": str(far)})
        p = base.Paths.from_env(None, env={"HOME": str(home), "USERPROFILE": str(home)})
        self.assertEqual((norm(p.whynot), p.engine_home_source.split(":")[0]), (norm(far), "pointer"))
        self.assertEqual(p.child_env({})["WHYNOT_HOME"], str(p.whynot))
        # a sandbox follows its OWN pointer / settings.json (so its uninstall finds a chosen home) and never the
        # environment of the machine running it
        inner = home / "WhyNot Engine"
        EngineHomeCases.pointer(home, {"engine_home": str(inner)})
        s = base.Paths.from_env(str(home), env={"WHYNOT_HOME": str(far)})
        self.assertEqual((norm(s.whynot), s.engine_home_source.split(":")[0]), (norm(inner), "pointer"))
        (home / ".whynot-cut" / "plugin-options.json").unlink()
        s = base.Paths.from_env(str(home), env={"WHYNOT_HOME": str(far)})
        self.assertEqual((s.whynot, s.engine_home_source), (home / ".whynot-cut", "sandbox"))
        # a chosen folder (-EngineHome / the location question) wins over both
        c = base.Paths.from_env(str(home), env={}, engine_home=str(home / "Chosen"))
        self.assertEqual((c.whynot, c.engine_home_source), (home / "Chosen", "chosen"))
        c = base.Paths.from_env(None, env={"HOME": str(home), "USERPROFILE": str(home)}, engine_home=str(far))
        self.assertEqual((c.whynot, c.engine_home_source), (far, "chosen"))

    def test_a_chosen_engine_home_wins_and_is_not_cross_checked(self):
        home = self.tmp / ARABIC_HOME
        far = self.tmp / "engine far"
        chosen = self.tmp / "chosen engine محرك"
        EngineHomeCases.settings(home, {"whynot-cut@thewhynot-ai": {"options": {"engine_home": str(far)}}})
        with mock.patch.dict(os.environ, clean_engine_env(home), clear=True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["plan", "--engine-home", str(chosen), "--engine-home-chosen"])
        self.assertEqual(rc, 0)
        plan = json.loads(out.getvalue())
        self.assertEqual((norm(plan["engine_home"]), plan["engine_home_source"]), (norm(chosen), "chosen"))
        self.assertFalse(chosen.exists())  # plan writes nothing

    def test_a_chosen_engine_home_must_be_a_safe_place(self):
        home = self.tmp / "users" / ARABIC_HOME
        repo = self.tmp / "repo"
        plugin = repo / "zip root" / "whynot-cut"
        clients = self.tmp / "WhyNot Clients"
        touch(self.tmp / "marked" / ".whynot-client", b"{}")
        touch(self.tmp / "bigger" / "Dr X" / "raw" / ".whynot-client", b"{}")
        check = lambda p, **kw: base.engine_home_choice_problem(  # noqa: E731
            p, home=home, plugin_root=plugin, clients_roots=[clients], **kw)
        for path, needle in (("engine", "full path"), (Path(self.tmp.anchor), "drive root"),
                             (plugin / "engine", "plugin folder"), (plugin, "plugin folder"),
                             (repo, "plugin folder"),  # a folder holding the plugin checkout
                             (home.parent, "user folder"), (home / ".claude" / "x", "Claude"),
                             (clients, "clients folder"), (clients / "engine", "clients folder"),
                             (self.tmp, "plugin folder"),  # holds the plugin and the clients folder
                             (self.tmp / "marked", "client folder"), (self.tmp / "marked" / "sub", "client folder"),
                             (self.tmp / "bigger", "client folder")):
            with self.subTest(str(path)):
                problem = check(str(path))
                self.assertIsNotNone(problem)
                self.assertIn(needle, problem)
        work = self.tmp / "work"
        self.assertIn("clients folder", base.engine_home_choice_problem(
            str(work), home=home, plugin_root=plugin, clients_roots=[work / "Clients"]))  # it holds them
        self.assertIsNone(check(str(self.tmp / "WhyNot Engine")))
        self.assertIsNone(check(str(home / "WhyNot Engine"), sandbox_home=home))
        self.assertIn("sandbox", check(str(self.tmp / "WhyNot Engine"), sandbox_home=home))
        # the core refuses it before anything is written (exit 2)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(["plan", "--home", str(home), "--engine-home", str(self.tmp / "outside"),
                           "--engine-home-chosen"])
        self.assertEqual(rc, 2)
        self.assertIn("sandbox", err.getvalue())
        self.assertFalse(home.exists())

    def test_mounted_volumes_are_drive_roots(self):
        plugin = self.tmp / "zip root" / "whynot-cut"
        vol = self.tmp / "usb stick"
        vol.mkdir()
        real = os.path.ismount
        with mock.patch.object(os.path, "ismount", side_effect=lambda p: base._norm(p) == base._norm(vol) or real(p)):
            problem = base.engine_home_choice_problem(str(vol), home=self.tmp / "h", plugin_root=plugin)
        self.assertIn("mounted volume", problem)
        if not IS_WIN:
            self.assertIn("mounted volume", base.engine_home_choice_problem(
                "/Volumes/USB", home=self.tmp / "h", plugin_root=plugin))
        self.assertTrue(base._is_drive_root("/Volumes/My Disk") or IS_WIN)

    def test_a_folder_with_the_editors_files_gets_a_whynotcut_subfolder(self):
        # fix round 1 (CRITICAL): never an engine home that holds the editor's own files - uninstall would empty it
        home = self.tmp / ARABIC_HOME
        plugin = self.tmp / "zip root" / "whynot-cut"
        place = lambda p: base.choose_engine_home(str(p), home=home, plugin_root=plugin)  # noqa: E731
        docs = home / "Documents"
        touch(docs / "thesis.docx", b"mine")
        for chosen in (docs, home, home / "Desktop", home / "Downloads"):  # (Desktop / Downloads need not exist)
            with self.subTest(str(chosen)):
                final, note, problem = place(chosen)
                self.assertIsNone(problem)
                self.assertEqual(final, chosen / "WhyNotCut")
                self.assertIn("WhyNotCut", note)
        work = touch(self.tmp / "D Work" / "budget.xlsx", b"mine").parent
        self.assertEqual(place(work)[0], work / "WhyNotCut")
        # an existing engine home (even with something foreign in it), an empty folder or one holding only WhyNot
        # Cut's own entries stays as chosen
        eng = self.tmp / "engine home"
        touch(eng / "state.json", GENUINE_STATE)
        touch(eng / "uxp-spike" / "x.txt", b"x")
        self.assertEqual(place(eng), (eng, "", None))
        only_ours = self.tmp / "only ours"
        touch(only_ours / "downloads" / "release-1" / "a.zip", b"z")  # the -Source cache
        touch(only_ours / ".wnc-write-test-123", b"x")  # the bootstraps' write probe
        self.assertEqual(place(only_ours)[0], only_ours)
        self.assertEqual(place(self.tmp / "new folder")[0], self.tmp / "new folder")
        # fix round 2: entry NAMES are never trusted - anything else gets the subfolder (exact names, case too)
        for name, rel in (("fonts", "fonts/MyBrand.ttf"), ("downloads", "downloads/raw-footage.mov"),
                          ("logs", "logs/shoot-notes.txt"), ("Bin", "Bin/edit.prproj"), ("state", "state.json"),
                          ("pointer", "plugin-options.json"), ("models", "models/my-model.bin")):
            with self.subTest(name):
                d = self.tmp / f"user {name}"
                touch(d.joinpath(*rel.split("/")), b'{"my": "game save"}')
                self.assertEqual(place(d)[0], d / "WhyNotCut")
        # the pointer counts as ours only in ~/.whynot-cut, where the SessionStart hook keeps it
        touch(home / ".whynot-cut" / "plugin-options.json", b'{"engine_home": ""}')
        self.assertEqual(place(home / ".whynot-cut")[0], home / ".whynot-cut")
        # a home a previous install claimed (state written by WhyNot Cut) is used directly again
        prev = self.tmp / "previous install"
        touch(prev / "state.json", GENUINE_STATE)
        touch(prev / "logs" / "install-1.log", b"log")
        self.assertEqual(place(prev), (prev, "", None))
        # the -Source cache: the plugin unpacked under <engine>/downloads is fine
        cached = only_ours / "downloads" / "release-1" / "x" / "whynot-cut-marketplace" / "whynot-cut"
        self.assertIsNone(base.engine_home_choice_problem(str(only_ours), home=home, plugin_root=cached))
        # a WhyNotCut subfolder that itself holds other files is refused, not entered
        touch(work / "WhyNotCut" / "notes.txt", b"mine")
        self.assertIn("already holds other files", place(work)[2])
        # the core moves a chosen Documents into its subfolder too (the bootstraps normally did it already)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["plan", "--home", str(home), "--engine-home", str(docs), "--engine-home-chosen"])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(norm(json.loads(out.getvalue())["engine_home"]), norm(docs / "WhyNotCut"))
        self.assertIn("WhyNotCut", err.getvalue())

    def test_plan_outside_the_sandbox_and_a_disagreeing_bootstrap(self):
        home = self.tmp / ARABIC_HOME
        far = self.tmp / "engine far"
        EngineHomeCases.settings(home, {"whynot-cut@thewhynot-ai": {"options": {"engine_home": str(far)}}})
        with mock.patch.dict(os.environ, clean_engine_env(home), clear=True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["plan", "--engine-home", str(far)])
            self.assertEqual(rc, 0)
            plan = json.loads(out.getvalue())
            self.assertEqual(norm(plan["engine_home"]), norm(far))
            self.assertTrue(plan["engine_home_source"].startswith("settings"), plan)
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = cli.main(["plan", "--engine-home", str(home / ".whynot-cut")])
            self.assertEqual(rc, 2)
            self.assertIn(str(far), err.getvalue())
            # and says how the editor fixes it alone: choose the folder explicitly
            for needle in ("-EngineHome", "--engine-home", "run the installer again"):
                self.assertIn(needle, err.getvalue())
        self.assertFalse((home / ".whynot-cut").exists())
        self.assertFalse(far.exists())


class TestEngineHomeInTheShells(unittest.TestCase):
    """The bootstraps' own resolvers (they place uv and Python before the core exists) give the core's answer for
    every case. Each resolver function runs alone with an injected env and a temp home."""
    PS_FUNCS = ("Get-WncFullPath", "Read-WncJsonObject", "Get-WncMember", "ConvertTo-WncHomePath",
                "Resolve-WncEngineHome")
    SH_FUNCS = ("abs_path", "home_path", "saved_engine_home", "resolve_engine_home")

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def cases(self):
        yield from TestEngineHome.each_case(self)

    def test_powershell_resolver(self):
        if not find_powershell():
            self.skipTest("Windows PowerShell is not available")
        boot = INSTALLER / "core" / "bootstrap.ps1"
        script = self.tmp / "resolve.ps1"
        script.write_text("".join(shell_function(boot, n, True) for n in self.PS_FUNCS)
                          + "$r = Resolve-WncEngineHome $env:WNC_T_HOME\n"
                          + "[IO.File]::WriteAllText($env:WNC_T_OUT, (Get-WncFullPath $r.Path) + \"`n\" + $r.Source,"
                          + " (New-Object System.Text.UTF8Encoding $false))\n", encoding="utf-8-sig")
        for name, home, extra, want, kind in self.cases():
            with self.subTest(name):
                out = self.tmp / "out.txt"
                env = clean_engine_env(home, WNC_T_HOME=str(home), WNC_T_OUT=str(out), **extra)
                r = subprocess.run([find_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                    "-File", str(script)], capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=env, timeout=120, stdin=subprocess.DEVNULL, cwd=str(self.tmp))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                path, src = out.read_text(encoding="utf-8").split("\n", 1)
                self.assertEqual(norm(path), norm(want), src)
                self.assertEqual(src if src.startswith("env:") else src.split(":", 1)[0], kind)
                self.assertEqual(norm(path), norm(base.resolve_engine_home(env, home)[0]))

    def test_bash_resolver(self):
        bash = find_bash()
        if not bash:
            self.skipTest("bash is not available")
        boot = INSTALLER / "core" / "bootstrap.sh"
        script = self.tmp / "resolve.sh"
        script.write_bytes(('OS_NAME="$(uname -s)"\nJSON_PY="$1"\n'
                            + "".join(shell_function(boot, n, False) for n in self.SH_FUNCS)
                            + 'resolve_engine_home\n'
                            + 'if command -v cygpath >/dev/null 2>&1; then ENGINE="$(cygpath -w "$ENGINE")"; fi\n'
                            + "printf '%s\\n%s\\n' \"$ENGINE\" \"$ENGINE_SRC\"\n").encode("utf-8"))
        for name, home, extra, want, kind in self.cases():
            with self.subTest(name):
                env = clean_engine_env(home, **extra)
                r = subprocess.run([bash, script.as_posix(), Path(sys.executable).as_posix()], capture_output=True,
                                   env=env, timeout=120, stdin=subprocess.DEVNULL, cwd=str(self.tmp))
                out = r.stdout.decode("utf-8", "replace")
                self.assertEqual(r.returncode, 0, out + r.stderr.decode("utf-8", "replace"))
                path, src = out.rstrip("\n").split("\n", 1)
                self.assertEqual(norm(path), norm(want), src)
                self.assertEqual(src if src.startswith("env:") else src.split(":", 1)[0], kind)

    def test_the_sandbox_resolvers_read_only_the_sandbox_files(self):
        # -Home / --home: the sandbox's own pointer names the engine home; WHYNOT_HOME of the machine is ignored
        home = self.tmp / ARABIC_HOME
        inner = home / "WhyNot Engine محرك"
        EngineHomeCases.pointer(home, {"engine_home": str(inner), "clients_root": ""})
        env = clean_engine_env(home, WHYNOT_HOME=str(self.tmp / "machine engine"),
                               CLAUDE_CONFIG_DIR=str(self.tmp / "machine claude"))
        if find_powershell():
            boot = INSTALLER / "core" / "bootstrap.ps1"
            script = self.tmp / "resolve-sandbox.ps1"
            script.write_text("".join(shell_function(boot, n, True) for n in self.PS_FUNCS)
                              + "$r = Resolve-WncEngineHome $env:WNC_T_HOME -Sandbox\n"
                              + "[IO.File]::WriteAllText($env:WNC_T_OUT, (Get-WncFullPath $r.Path) + \"`n\" + "
                              + "$r.Source, (New-Object System.Text.UTF8Encoding $false))\n", encoding="utf-8-sig")
            out = self.tmp / "out.txt"
            r = subprocess.run([find_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-File", str(script)], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=dict(env, WNC_T_HOME=str(home), WNC_T_OUT=str(out)), timeout=120,
                               stdin=subprocess.DEVNULL, cwd=str(self.tmp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            path, src = out.read_text(encoding="utf-8").split("\n", 1)
            self.assertEqual((norm(path), src.split(":", 1)[0]), (norm(inner), "pointer"))
        bash = find_bash()
        if bash:
            boot = INSTALLER / "core" / "bootstrap.sh"
            script = self.tmp / "resolve-sandbox.sh"
            script.write_bytes(('OS_NAME="$(uname -s)"\nJSON_PY="$1"\n'
                                + "".join(shell_function(boot, n, False) for n in self.SH_FUNCS)
                                + 'resolve_engine_home sandbox\n'
                                + 'if command -v cygpath >/dev/null 2>&1; then ENGINE="$(cygpath -w "$ENGINE")"; fi\n'
                                + "printf '%s\\n%s\\n' \"$ENGINE\" \"$ENGINE_SRC\"\n").encode("utf-8"))
            r = subprocess.run([bash, script.as_posix(), Path(sys.executable).as_posix()], capture_output=True,
                               env=env, timeout=120, stdin=subprocess.DEVNULL, cwd=str(self.tmp))
            out = r.stdout.decode("utf-8", "replace")
            self.assertEqual(r.returncode, 0, out + r.stderr.decode("utf-8", "replace"))
            path, src = out.rstrip("\n").split("\n", 1)
            self.assertEqual((norm(path), src.split(":", 1)[0]), (norm(inner), "pointer"))
        if not find_powershell() and not bash:
            self.skipTest("neither PowerShell nor bash is available")

    def test_the_bootstraps_pass_the_resolved_home_to_the_core(self):
        for name, needle in (("bootstrap.ps1", "Resolve-WncEngineHome $h"), ("bootstrap.sh", "resolve_engine_home"),
                             ("bootstrap.ps1", "'--engine-home'"), ("bootstrap.sh", "--engine-home")):
            self.assertIn(needle, SHELL_FILES[name].read_text(encoding="utf-8"), name)


# --------------------------------------------------------------------------------------------- files / log
class TestFiles(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
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
        self._td = TempDir()
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

    def fake_curl(self, code: int) -> str:
        """A curl that fails like a real one behind a proxy it cannot use (exit 5 / 6 / 7)."""
        d = self.tmp / f"fake curl {code}"
        d.mkdir(parents=True, exist_ok=True)
        if IS_WIN:
            p = d / "curl.cmd"
            p.write_text(f"@echo curl: ({code}) could not connect 1>&2\r\n@exit /b {code}\r\n", encoding="ascii")
        else:
            p = d / "curl"
            p.write_text(f'#!/bin/sh\necho "curl: ({code}) could not connect" >&2\nexit {code}\n', encoding="ascii")
            os.chmod(p, 0o755)
        return str(p)

    def test_curl_proxy_resolve_connect_errors_fall_back_to_urllib(self):
        for code in (5, 6, 7):
            with self.subTest(curl_exit=code):
                log = Quiet(self.tmp / f"dl-{code}.log")
                with mock.patch.object(base, "find_curl", return_value=self.fake_curl(code)):
                    out = base.download(self.url, sha(self.BODY), self.dl, log, retries=1)
                self.assertEqual(out.read_bytes(), self.BODY)
                self.assertIn(f"curl exit {code}", log.path.read_text(encoding="utf-8"))
                out.unlink()
        self.assertEqual(len(self.srv.hits), 3)  # one urllib request per download; the fake curl made none


# --------------------------------------------------------------------------------------------- extract
class TestExtract(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
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
        self._td = TempDir()
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
        self._td = TempDir()
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
        self._td = TempDir()
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
        self._td = TempDir()
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


def make_ctx(home: Path, components: dict, plugin_root: Path, platform: str = "win-x64", engine_home=None,
             **args) -> base.Ctx:
    paths = base.Paths.from_env(str(home), env={}, engine_home=str(engine_home) if engine_home else None)
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
        self._td = TempDir()
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
        # held by a running process: this test's own (the installer's format: "<pid> <time> <who>")
        paths = self.ctx().paths
        lk = self.build_lock(paths)
        lk.parent.mkdir(parents=True)
        text = f"{os.getpid()} 2026-10-12T10:00:00+03:00 reel setup\n"
        lk.write_text(text, encoding="utf-8")
        old = time.time() - 125
        os.utime(lk, (old, old))
        ctx = self.ctx()
        r = self.rt.step_runtime(ctx)
        self.assertEqual(r.status, "amber")
        self.assertIn("another WhyNot Cut setup is building this runtime", r.detail)
        self.assertIn(str(lk), r.detail)  # where the lock is
        self.assertIn("2 min", r.detail)  # and how old
        self.assertEqual(self.uv_calls(), [])
        self.assertEqual(lk.read_text(encoding="utf-8"), text)  # not ours: left alone
        self.assertFalse(ctx.paths.current_file.exists())
        self.assertIsNone(ctx.runtime_python)

    def test_fresh_lock_of_a_running_reel_setup_is_amber(self):
        # the engine's setup_env.BuildLock writes the bare pid (no newline): a live sleeper holds it
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdin=subprocess.DEVNULL)
        self.addCleanup(sleeper.wait, 30)
        self.addCleanup(sleeper.kill)
        lk = self.build_lock(self.ctx().paths)
        lk.parent.mkdir(parents=True)
        lk.write_text(str(sleeper.pid), encoding="utf-8")
        r = self.rt.step_runtime(self.ctx())
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn(str(lk), r.detail)
        self.assertTrue(lk.exists())

    def test_fresh_lock_of_a_process_that_is_gone_is_taken_over(self):
        # the installer window was closed during `pip sync`: the lock is fresh but its process is gone
        dead = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL)
        dead.wait(30)
        for text in (f"{dead.pid} 2026-10-12T10:00:00+03:00 installer\n", str(dead.pid)):  # installer, engine
            with self.subTest(lock=text):
                ctx = self.ctx()
                rdir = ctx.paths.runtimes_dir / self.rid()
                if rdir.exists():
                    rmtree_retry(rdir)
                lk = self.build_lock(ctx.paths)
                lk.parent.mkdir(parents=True, exist_ok=True)
                lk.write_text(text, encoding="utf-8")
                r = self.rt.step_runtime(ctx)
                self.assertEqual(r.status, "ok", r.detail)
                self.assertFalse(lk.exists())
                self.assertEqual(self.rt.current_runtime(ctx.paths), self.rid())

    def test_stale_build_lock_is_taken_over(self):
        # the 2 h rule stays as the backstop (a pid the OS has given to another process looks alive)
        paths = self.ctx().paths
        lk = self.build_lock(paths)
        lk.parent.mkdir(parents=True)
        lk.write_text(f"{os.getpid()} crashed\n", encoding="utf-8")
        old = time.time() - 3 * 3600
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
        self._td = TempDir()
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
        self._td = TempDir()
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
        self._td = TempDir()
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
        # in a sandbox only the test switch counts: a CLAUDE_CLI of this machine never leads to the real CLI
        sand2 = self.cl.claude_candidates({"CLAUDE_CLI": str(FAKE_CLAUDE)}, home, "win-x64", True)
        self.assertEqual(sand2, [new, old])


class TestSettingsMerge(unittest.TestCase):
    MKT = {"thewhynot-ai": {"source": {"source": "directory", "path": "C:\\Users\\x\\.whynot-cut\\marketplace"}}}

    def setUp(self):
        self._td = TempDir()
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
        self._td = TempDir()
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

    def test_plugins_the_install_switched_off_go_back_on_only_while_still_off(self):
        d = json.loads(self.f.read_text(encoding="utf-8"))
        d["enabledPlugins"].update({"reel-editor@old": False, "reel-editor@kept": True})
        self.f.write_text(json.dumps(d), encoding="utf-8")
        r = self.cl.unmerge_claude_settings(self.f, marketplace_name="thewhynot-ai", plugin_id=PID,
                                            env_keys_if_under={}, enable=["reel-editor@old", "reel-editor@kept",
                                                                          "reel-editor@gone", PID],
                                            make_backup=False)
        self.assertEqual(r["enabled"], ["reel-editor@old"])
        self.assertIsNone(r["backup"])  # the caller keeps its own backup
        self.assertEqual(list(self.f.parent.glob("settings.json.whynot-backup-*")), [])
        plugins = json.loads(self.f.read_text(encoding="utf-8"))["enabledPlugins"]
        self.assertEqual(plugins, {"x@y": True, "reel-editor@old": True, "reel-editor@kept": True})


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
        self._td = TempDir()
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
        self._td = TempDir()
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
        self._td = TempDir()
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


# --------------------------------------------------------------------------------------------- T7.1 task 4 helpers
GB = 1024 ** 3
FONT_A, FONT_B = b"\x00\x01\x00\x00 fixture font A " * 40, b"\x00\x01\x00\x00 fixture font B " * 40
OFL = b"SIL OPEN FONT LICENSE Version 1.1 (fixture)\n"
DOCTOR_JSON = {"verdict": "ready", "ready": True, "fixes": [{"item": "x", "who": "editor", "fix": "y"}]}
ENGINE_STUB = (
    "import json, os, sys\n"
    "log = os.environ.get('WNC_TEST_ENGINE_LOG')\n"
    "if log:\n"
    "    with open(log, 'a', encoding='utf-8') as f:\n"
    "        f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
    "cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
    "if cmd == 'doctor':\n"
    "    raw = os.environ.get('WNC_TEST_DOCTOR_RAW')\n"
    f"    print(raw if raw is not None else json.dumps({DOCTOR_JSON!r}))\n"
    "else:\n"
    "    print(json.dumps({'ok': True, 'cmd': cmd}))\n"
    "sys.exit(int(os.environ.get('WNC_TEST_ENGINE_EXIT', '0')))\n")


def system_module():
    """Imported inside the tests so this file stays importable while a step module is being written."""
    from wnc_installer import system
    return system


def tgz(entries: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in entries.items():
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode = len(data), 0o755
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def fixture_fonts(base_url: str) -> tuple:
    """(components `fonts` section, {served path: bytes}) for two tiny fonts and one licence."""
    served = {"/fonts/FixA-Regular.ttf": FONT_A, "/fonts/Fix%5Bwght%5D.ttf": FONT_B, "/fonts/OFL.txt": OFL}
    section = {"version": "1", "commit": "fixture", "files": [
        {"family": "Fix Sans", "file": "FixA-Regular.ttf", "url": base_url + "/fonts/FixA-Regular.ttf",
         "sha256": sha(FONT_A), "bytes": len(FONT_A)},
        {"family": "Fix Sans", "file": "Fix[wght].ttf", "url": base_url + "/fonts/Fix%5Bwght%5D.ttf",
         "sha256": sha(FONT_B), "bytes": len(FONT_B)}],
        "licenses": [{"family": "Fix Sans", "url": base_url + "/fonts/OFL.txt", "sha256": sha(OFL), "bytes": len(OFL)}]}
    return section, served


def make_fixture_plugin(root: Path, base_url: str) -> types.SimpleNamespace:
    """A plugin tree the whole installer can run against, WITHOUT the real engine (Tasks 4, 5 and 6 use it).

    Layout: <root>/.claude-plugin/marketplace.json (the marketplace the claude step registers) and <root>/whynot-cut/
    (the plugin root) holding a copy of installer/ (the core and the GPL text), .claude-plugin/plugin.json (3.0.0),
    setup/components.json whose every URL points at `base_url` (a test http.server), setup/locks/runtime-<plat>.lock
    (LOCK_A) and engine/reel/cli.py = ENGINE_STUB (appends its argv as JSON to $WNC_TEST_ENGINE_LOG; `doctor` prints
    DOCTOR_JSON or $WNC_TEST_DOCTOR_RAW; exit $WNC_TEST_ENGINE_EXIT). The Adobe panel pins stay placeholders.
    Returns .root, .plugin_root, .components (dict), .components_path, .lock and .served ({url path: bytes}: put them
    on the server, e.g. Served.srv.files.update(fx.served)). Runtime smoke = ["json"], so the fake uv's venv passes."""
    root = Path(root)
    plugin = root / "whynot-cut"
    shutil.copytree(SK / "installer", plugin / "installer",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    touch(root / ".claude-plugin" / "marketplace.json",
          b'{"name": "thewhynot-ai", "plugins": [{"name": "whynot-cut", "source": "./whynot-cut"}]}')
    touch(plugin / ".claude-plugin" / "plugin.json", b'{"name": "whynot-cut", "version": "3.0.0"}')
    touch(plugin / "engine" / "reel" / "cli.py", ENGINE_STUB.encode("utf-8"))
    served = {}
    uv = {"win-x64": ("/uv/uv-x86_64-pc-windows-msvc.zip", ffmpeg_zip({"uv.exe": b"MZ fake uv"}), "zip", "uv.exe")}
    for plat, triple in (("mac-arm64", "uv-aarch64-apple-darwin"), ("mac-x64", "uv-x86_64-apple-darwin")):
        uv[plat] = (f"/uv/{triple}.tar.gz", tgz({f"{triple}/uv": b"#!/bin/sh\necho uv 0.0.0\n"}), "tar.gz",
                    f"{triple}/uv")
    uv_assets = {}
    for plat, (path, data, kind, member) in uv.items():
        served[path] = data
        uv_assets[plat] = {"url": base_url + path, "sha256": sha(data), "bytes": len(data), "archive": kind,
                           "member": member}
    ff_assets = {}
    for plat in sorted(PLATFORMS):
        exe = ".exe" if plat.startswith("win") else ""
        data = ffmpeg_zip({f"bin/ffmpeg{exe}": b"fake ffmpeg " + plat.encode(),
                           f"bin/ffprobe{exe}": b"fake ffprobe " + plat.encode()})
        path = f"/ffmpeg/ffmpeg-{plat}.zip"
        served[path] = data
        ff_assets[plat] = {"files": [{"url": base_url + path, "sha256": sha(data), "bytes": len(data),
                                      "archive": "zip", "members": {f"bin/ffmpeg{exe}": f"ffmpeg{exe}",
                                                                    f"bin/ffprobe{exe}": f"ffprobe{exe}"}}]}
    git = ffmpeg_zip({"bin/bash.exe": b"MZ bash", "cmd/git.exe": b"MZ git"})
    served["/git/PortableGit.zip"] = git
    fonts, font_files = fixture_fonts(base_url)
    served.update(font_files)
    locks = {}
    for plat in sorted(PLATFORMS):
        lock = touch(plugin / "setup" / "locks" / f"runtime-{plat}.lock", LOCK_A)
        locks[plat] = {"file": f"setup/locks/runtime-{plat}.lock", "id": base.PLACEHOLDER}
    comp = {
        "schema": 1, "plugin": "3.0.0", "channel": "stable", "claude_code": {"min": "2.1.224"},
        "marketplace": {"name": "thewhynot-ai", "plugin": "whynot-cut", "url": base.PLACEHOLDER},
        "release": {"index_url": base.PLACEHOLDER},
        "uv": {"version": "0.13.0", "assets": uv_assets},
        "runtime": {"python": "3.12.15", "index_url": None, "smoke": ["json"], "locks": locks},
        "ffmpeg": {"version": "9.0.2", "license": "GPL-3.0-or-later",
                   "source": "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz", "assets": ff_assets},
        "git": {"version": "2.56.0.windows.2", "assets": {"win-x64": {
            "url": base_url + "/git/PortableGit.zip", "sha256": sha(git), "bytes": len(git), "archive": "zip"}}},
        "bridge": {"protocol": 4, "min_protocol": 4,
                   "cep": {"bundle": base.PLACEHOLDER, "zxp": base.PLACEHOLDER, "sha256": base.PLACEHOLDER,
                           "hosts": {"PPRO": "[22.0,99.9]", "AEFT": "[24.0,99.9]"}},
                   "uxp": {"version": base.PLACEHOLDER, "ccx": base.PLACEHOLDER, "sha256": base.PLACEHOLDER,
                           "min_host": "26.5.0", "id": base.PLACEHOLDER}},
        "models": {"by_hardware": {"nvidia": "large-v3", "apple_silicon": "large-v3", "cpu": "large-v3-turbo"}},
        "fonts": fonts}
    comp_path = plugin / "setup" / "components.json"
    touch(comp_path, json.dumps(comp, indent=2).encode("utf-8"))
    return types.SimpleNamespace(root=root, plugin_root=plugin, components=comp, components_path=comp_path,
                                 lock=lock, served=served)


def only_the_test_log(paths: base.Paths) -> bool:
    """Nothing under the sandbox home but the log folder (and log) of make_ctx's Quiet log."""
    found = sorted(str(p.relative_to(paths.home)) for p in paths.home.rglob("*") if p.parent != paths.logs_dir)
    return found == sorted([".whynot-cut", os.path.join(".whynot-cut", "logs")])


def sandbox_env(**extra) -> dict:
    """Environment for a sandboxed core run: no engine / Claude locations of this machine, the fakes switched on."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("WHYNOT_HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_CLI", "WNC_TEST_NVIDIA", "WNC_TEST_MODEL",
                        "WNC_TEST_HOSTS_RUNNING", "WNC_TEST_ADOBE_HOSTS", "FAKE_CLAUDE_FAIL", "FAKE_UV_FAIL")}
    env.update(PYTHONUTF8="1", **extra)
    return env


# --------------------------------------------------------------------------------------------- preflight
class TestPreflight(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.sy = system_module()
        for k in ("WNC_TEST_HOSTS_RUNNING", "WNC_TEST_ADOBE_HOSTS", "WNC_TEST_NVIDIA"):
            os.environ.pop(k, None)

    def run_pre(self, free_gb, home="plain-home", plat="win-x64"):
        ctx = make_ctx(self.tmp / home, {"schema": 1}, SK, plat)
        usage = types.SimpleNamespace(total=500 * GB, used=0, free=int(free_gb * GB))
        with mock.patch.object(shutil, "disk_usage", return_value=usage):
            return ctx, self.sy.preflight(ctx)

    def test_free_space_thresholds(self):
        for free, want in ((5, "red"), (7, "amber"), (50, "ok")):
            with self.subTest(free=free):
                ctx, r = self.run_pre(free)
                self.assertEqual(r.status, want, r.detail)
                self.assertEqual(ctx.facts["free_gb"], free)
        ctx, r = self.run_pre(5)
        self.assertIn("6 GB", r.detail)

    def test_facts(self):
        ctx, r = self.run_pre(50)
        f = ctx.facts
        for key in ("os", "arch", "free_gb", "home_ascii", "home_space", "onedrive_documents", "icloud_documents",
                    "claude_found", "adobe_hosts", "nvidia", "existing", "sac"):
            self.assertIn(key, f)
        self.assertEqual((f["os"], f["arch"]), ("windows", "x64"))
        self.assertTrue(f["home_ascii"])
        self.assertFalse(f["home_space"])
        self.assertIsNone(f["sac"])  # sandbox: the registry is never read
        self.assertEqual(f["adobe_hosts"], [])
        self.assertEqual(f["existing"], {"engine": False, "legacy_reel_editor": False, "marketplace_source": None})
        self.assertEqual(only_the_test_log(ctx.paths), True)  # read-only

    def test_reports_the_engine_home_and_where_it_came_from(self):
        ctx, r = self.run_pre(50)
        self.assertEqual(ctx.facts["engine_home"], str(ctx.paths.whynot))
        self.assertEqual(ctx.facts["engine_home_source"], "sandbox")
        self.assertIn(f"engine home {ctx.paths.whynot} (sandbox)", r.detail)
        ctx.paths.engine_home_source = "pointer:" + str(self.tmp / "opts.json")
        r = self.sy.preflight(ctx)
        self.assertIn("plugin option engine_home in " + str(self.tmp / "opts.json"), r.detail)

    def test_arabic_home_with_a_space_is_amber(self):
        ctx, r = self.run_pre(50, home=ARABIC_HOME)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertFalse(ctx.facts["home_ascii"])
        self.assertTrue(ctx.facts["home_space"])
        self.assertIn("non-ASCII", r.detail)

    def test_onedrive_documents_is_amber(self):
        ctx = make_ctx(self.tmp / "plain-home", {"schema": 1}, SK, "win-x64")
        usage = types.SimpleNamespace(total=500 * GB, used=0, free=50 * GB)
        with mock.patch.object(shutil, "disk_usage", return_value=usage), \
                mock.patch.object(self.sy, "documents_dir", return_value=self.tmp / "OneDrive" / "Documents"):
            r = self.sy.preflight(ctx)
        self.assertEqual(r.status, "amber")
        self.assertTrue(ctx.facts["onedrive_documents"])
        self.assertIn("OneDrive", r.detail)

    def test_adobe_hosts_from_the_test_variables(self):
        hosts = [{"app": "premiere", "version": "26.5.2"}, {"app": "after_effects", "version": "26.1.0"}]
        with mock.patch.dict(os.environ, {"WNC_TEST_ADOBE_HOSTS": json.dumps(hosts),
                                          "WNC_TEST_HOSTS_RUNNING": "AfterFX.exe"}):
            ctx, _r = self.run_pre(50)
        got = {h["app"]: (h["version"], h["running"]) for h in ctx.facts["adobe_hosts"]}
        self.assertEqual(got, {"premiere": ("26.5.2", False), "after_effects": ("26.1.0", True)})

    def test_install_stops_with_2_before_any_download(self):
        home = self.tmp / ARABIC_HOME
        usage = types.SimpleNamespace(total=500 * GB, used=0, free=5 * GB)
        with mock.patch.object(shutil, "disk_usage", return_value=usage), \
                mock.patch.object(base, "download", side_effect=AssertionError("no download may start")):
            rc = cli.main(["install", "--home", str(home), "--yes", "--quiet"])
        self.assertEqual(rc, 2)
        paths = base.Paths.from_env(str(home), env={})
        self.assertFalse(paths.downloads_dir.exists())
        self.assertFalse(paths.runtimes_dir.exists())
        self.assertFalse(paths.claude_dir.exists())


# --------------------------------------------------------------------------------------------- questions
class TestQuestions(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        self.sy = system_module()

    def ctx(self, **args):
        a = {"clients_folder": None, "language": None}
        a.update(args)
        return make_ctx(self.home, {"schema": 1}, SK, "win-x64", **a)

    def test_yes_without_preferences_takes_the_defaults(self):
        ctx = self.ctx()
        r = self.sy.step_questions(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        want = self.home / "Documents" / "WhyNot Clients"
        self.assertEqual(ctx.answers["clients_root"], str(want))
        self.assertEqual(ctx.answers["language"], "ar")
        self.assertFalse(want.exists())  # never created
        self.assertTrue(only_the_test_log(ctx.paths))

    def test_existing_preferences_win(self):
        prefs = self.home / ".claude" / "whynot-cut.local.md"
        theirs = self.home.parent / "عملاء WhyNot"
        touch(prefs, (f'---\neditor_name: Yunus\nlanguage: en\nclients_root: "{theirs}"\n---\nnotes\n')
              .encode("utf-8"))
        ctx = self.ctx()
        self.sy.step_questions(ctx)
        self.assertEqual(ctx.answers["clients_root"], str(theirs))
        self.assertEqual(ctx.answers["language"], "en")
        self.assertFalse(theirs.exists())

    def test_flags_win_over_preferences(self):
        touch(self.home / ".claude" / "whynot-cut.local.md", b"---\nlanguage: en\nclients_root: E:/Old\n---\n")
        target = self.home.parent / "Clients Here"
        ctx = self.ctx(clients_folder=str(target), language="ar")
        self.sy.step_questions(ctx)
        self.assertEqual((ctx.answers["clients_root"], ctx.answers["language"]), (str(target), "ar"))
        self.assertFalse(target.exists())

    def test_bad_preference_values_are_ignored(self):
        touch(self.home / ".claude" / "whynot-cut.local.md", b"---\nlanguage: fr\nclients_root: ''\n---\n")
        ctx = self.ctx()
        self.sy.step_questions(ctx)
        self.assertEqual(ctx.answers["language"], "ar")
        self.assertEqual(ctx.answers["clients_root"], str(self.home / "Documents" / "WhyNot Clients"))

    def test_no_questions_with_yes(self):
        self.assertFalse(base.can_ask(argparse.Namespace(yes=True)))

    def test_documents_in_the_cloud_moves_the_default_out_of_it(self):
        for plat, fact, cloud in (("win-x64", "onedrive_documents", "OneDrive"),
                                  ("mac-arm64", "icloud_documents", "iCloud")):
            with self.subTest(plat):
                ctx = make_ctx(self.home, {"schema": 1}, SK, plat, clients_folder=None, language=None)
                ctx.facts[fact] = True
                r = self.sy.step_questions(ctx)
                want = self.home / "WhyNot Clients"
                self.assertEqual(ctx.answers["clients_root"], str(want))
                self.assertIn(cloud, r.detail)  # says why it is not in Documents
                self.assertFalse(want.exists())

    def test_cloud_documents_never_beat_a_flag_or_a_saved_preference(self):
        target = self.home.parent / "Clients Here"
        ctx = self.ctx(clients_folder=str(target))
        ctx.facts["onedrive_documents"] = True
        self.sy.step_questions(ctx)
        self.assertEqual(ctx.answers["clients_root"], str(target))
        touch(self.home / ".claude" / "whynot-cut.local.md", f"---\nclients_root: {target}\n---\n".encode("utf-8"))
        ctx = self.ctx()
        ctx.facts["onedrive_documents"] = True
        self.sy.step_questions(ctx)
        self.assertEqual(ctx.answers["clients_root"], str(target))


# --------------------------------------------------------------------------------------------- the chosen engine home
POINTER_KEYS = ["clients_root", "engine_home", "updated"]  # hooks/session_context.py write_pointer, in this order


class TestRememberEngineHome(unittest.TestCase):
    """ID-10: a chosen engine home is remembered through the engine's own mechanisms only: settings.json
    pluginConfigs["whynot-cut@thewhynot-ai"].options.engine_home (merged with every settings.json safety) and the
    pointer ~/.whynot-cut/plugin-options.json (the SessionStart hook's format). A default install writes neither."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.engine = self.home / "WhyNot Engine محرك"
        self.pointer = self.home / ".whynot-cut" / "plugin-options.json"
        self.settings = self.home / ".claude" / "settings.json"
        self.sy = system_module()

    def ctx(self, engine_home=None, **args):
        a = {"clients_folder": None, "language": None, "model": None}
        a.update(args)
        return make_ctx(self.home, {"schema": 1}, SK, "win-x64", engine_home=engine_home, **a)

    def remember(self, ctx, results=()):
        """The engine home is saved after every step (fix round 1: never before the install succeeded)."""
        return self.sy.step_location(ctx, list(results))

    def engine_sees(self) -> Path:
        """What the engine itself (engine/reel/lib/plat.py) resolves now, with no variable set."""
        from lib import plat
        with mock.patch.dict(os.environ, clean_engine_env(self.home), clear=True):
            return plat.engine_home()

    def test_the_default_home_writes_nothing(self):
        ctx = self.ctx()
        r = self.remember(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertFalse(self.pointer.exists())
        self.assertFalse(self.settings.exists())
        self.assertEqual(sorted(os.listdir(ctx.paths.whynot)), ["logs", "state.json"])  # only its own record
        ctx = self.ctx(engine_home=self.home / ".whynot-cut")  # chosen, but it is the default: still nothing
        self.assertEqual(self.remember(ctx).status, "ok")
        self.assertFalse(self.pointer.exists() or self.settings.exists())

    def test_a_chosen_home_is_remembered_in_both_places(self):
        original = json.dumps({"theme": "dark", "pluginConfigs": {
            "x@y": {"options": {"a": 1}}, PID: {"enabled": True, "options": {"clients_root": "D:/عملاء"}}},
            "zlast": True}, indent=2, ensure_ascii=False).encode("utf-8")
        touch(self.settings, original)
        touch(self.pointer, json.dumps({"clients_root": "D:/عملاء", "engine_home": "", "updated": "x"},
                                       ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
        if not IS_WIN:
            os.chmod(self.settings, 0o600)
        ctx = self.ctx(engine_home=self.engine)
        r = self.remember(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn(str(self.engine), r.detail)
        # the pointer: the hook's own format (one key per line, raw UTF-8, indent 1), clients_root kept
        raw = self.pointer.read_bytes()
        p = json.loads(raw.decode("utf-8"))
        self.assertEqual(list(p), POINTER_KEYS)
        self.assertEqual((p["engine_home"], p["clients_root"]), (str(self.engine), "D:/عملاء"))
        self.assertEqual(raw, (json.dumps(p, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        self.assertIn("محرك".encode("utf-8"), raw)
        # settings.json: only our option added, key order and the other entries kept, the original bytes backed up
        s = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(list(s), ["theme", "pluginConfigs", "zlast"])
        self.assertEqual(s["pluginConfigs"]["x@y"], {"options": {"a": 1}})
        self.assertEqual(s["pluginConfigs"][PID], {"enabled": True, "options": {"clients_root": "D:/عملاء",
                                                                                "engine_home": str(self.engine)}})
        backups = list(self.settings.parent.glob("settings.json.whynot-backup-*"))
        self.assertEqual([b.read_bytes() for b in backups], [original])
        if not IS_WIN:
            self.assertEqual(stat.S_IMODE(os.stat(self.settings).st_mode), 0o600)
        # the engine and the installer now find it without any flag
        self.assertEqual(norm(self.engine_sees()), norm(self.engine))
        self.assertEqual(norm(base.Paths.from_env(str(self.home), env={}).whynot), norm(self.engine))
        # a second run changes nothing (no second backup)
        self.assertEqual(self.remember(self.ctx()).status, "ok")
        self.assertEqual(len(list(self.settings.parent.glob("settings.json.whynot-backup-*"))), 1)
        self.assertEqual(self.pointer.read_bytes(), raw)

    def test_no_files_yet_get_both_written(self):
        ctx = self.ctx(engine_home=self.engine)
        self.assertEqual(self.remember(ctx).status, "ok")
        p = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual((list(p), p["engine_home"], p["clients_root"]), (POINTER_KEYS, str(self.engine), ""))
        s = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(s, {"pluginConfigs": {PID: {"options": {"engine_home": str(self.engine)}}}})
        self.assertEqual(set(os.listdir(self.home / ".whynot-cut")), {"plugin-options.json"})  # nothing else there

    def test_back_to_the_default_clears_a_home_named_before(self):
        old = self.home / "Old Engine"
        EngineHomeCases.pointer(self.home, {"clients_root": "", "engine_home": str(old), "updated": "x"})
        EngineHomeCases.settings(self.home, {PID: {"options": {"engine_home": str(old)}}})
        ctx = self.ctx(engine_home=self.home / ".whynot-cut")
        self.assertEqual(self.remember(ctx).status, "ok")
        self.assertEqual(json.loads(self.pointer.read_text(encoding="utf-8"))["engine_home"], "")
        s = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(s["pluginConfigs"][PID]["options"]["engine_home"], "")
        self.assertEqual(norm(self.engine_sees()), norm(self.home / ".whynot-cut"))

    def test_settings_named_another_home_alone_is_rewritten_too(self):
        # the SessionStart hook rewrites the pointer from the plugin option on every session: both must agree
        EngineHomeCases.settings(self.home, {PID: {"options": {"engine_home": str(self.home / "Old Engine")}}})
        ctx = self.ctx(engine_home=self.home / ".whynot-cut")
        self.assertEqual(self.remember(ctx).status, "ok")
        s = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(s["pluginConfigs"][PID]["options"]["engine_home"], "")

    def test_unreadable_settings_is_amber_untouched_and_the_pointer_still_written(self):
        bad = b'{"theme": "dark",, "pluginConfigs": {}}'
        touch(self.settings, bad)
        ctx = self.ctx(engine_home=self.engine)
        r = self.remember(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertEqual(self.settings.read_bytes(), bad)
        self.assertFalse(list(self.settings.parent.glob("settings.json.whynot-backup-*")))
        self.assertIn("pluginConfigs", r.needs_you)  # the JSON to merge by hand
        self.assertIn(json.dumps(str(self.engine), ensure_ascii=False), r.needs_you)
        self.assertEqual(json.loads(self.pointer.read_text(encoding="utf-8"))["engine_home"], str(self.engine))

    def test_plugin_configs_of_the_wrong_type_is_amber_and_untouched(self):
        bad = json.dumps({"pluginConfigs": {PID: {"options": ["not", "an", "object"]}}}).encode("utf-8")
        touch(self.settings, bad)
        r = self.remember(self.ctx(engine_home=self.engine))
        self.assertEqual(r.status, "amber", r.detail)
        self.assertEqual(self.settings.read_bytes(), bad)

    def test_dry_run_writes_nothing(self):
        ctx = self.ctx(engine_home=self.engine, dry_run=True)
        ctx.log = Quiet(None, dry_run=True)
        r = self.remember(ctx)
        self.assertIn("dry run", r.detail)
        self.assertFalse(self.pointer.exists() or self.settings.exists())

    def test_nothing_is_saved_before_the_install_succeeded(self):
        # the questions step no longer saves it; a red step keeps the previous location, and the checklist says so
        old = self.home / "Old Engine"
        EngineHomeCases.pointer(self.home, {"clients_root": "", "engine_home": str(old), "updated": "x"})
        before = self.pointer.read_bytes()
        ctx = self.ctx(engine_home=self.engine)
        self.sy.step_questions(ctx)
        self.assertEqual(self.pointer.read_bytes(), before)
        self.assertFalse(self.settings.exists())
        r = self.remember(ctx, [base.StepResult("runtime", "red", "pip sync failed"),
                                base.StepResult("state", "ok", "")])
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("NOT saved", r.detail)
        self.assertIn("runtime", r.detail)
        self.assertIn(f"still uses {old}", r.detail)
        self.assertEqual(self.pointer.read_bytes(), before)
        self.assertFalse(self.settings.exists())
        self.assertIn("[!!] location", self.sy.render_checklist([r], None))
        r = self.remember(ctx, [base.StepResult("runtime", "ok", ""), base.StepResult("gpu", "amber", "")])
        self.assertEqual(r.status, "ok", r.detail)  # amber steps do not stop it
        self.assertEqual(json.loads(self.pointer.read_text(encoding="utf-8"))["engine_home"], str(self.engine))

    def test_unknown_pointer_keys_are_kept(self):
        touch(self.pointer, json.dumps({"clients_root": "", "engine_home": "", "updated": "x", "future_key": "keep me"},
                                       indent=1).encode("utf-8"))
        self.assertEqual(self.remember(self.ctx(engine_home=self.engine)).status, "ok")
        p = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual(list(p), POINTER_KEYS + ["future_key"])
        self.assertEqual((p["engine_home"], p["future_key"]), (str(self.engine), "keep me"))

    def test_a_variable_that_overrides_the_choice_is_named(self):
        # outside a sandbox: WHYNOT_HOME (or another engine-home variable) beats the saved option in the engine
        other = self.tmp / "other engine"
        env = {"HOME": str(self.home), "USERPROFILE": str(self.home), "WHYNOT_HOME": str(other)}
        paths = base.Paths.from_env(None, env=env, engine_home=str(self.engine))
        claude = claude_module()
        r = claude.remember_engine_home(paths, env, Quiet(None))
        self.assertEqual(r["status"], "amber", r)
        self.assertIn("WHYNOT_HOME", r["detail"])
        self.assertIn(str(other), r["detail"])
        self.assertEqual(json.loads(self.pointer.read_text(encoding="utf-8"))["engine_home"], str(self.engine))


# --------------------------------------------------------------------------------------------- adobe
class TestAdobe(unittest.TestCase):
    SIGNED = ffmpeg_zip({"CSXS/manifest.xml": b"<ExtensionManifest/>", "index.html": b"<html>v1</html>",
                         "META-INF/signatures.xml": b"<signatures/>", "mimetype": b"application/vnd.adobe.air"})
    UNSIGNED = ffmpeg_zip({"CSXS/manifest.xml": b"<ExtensionManifest/>", "index.html": b"<html/>"})

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.plugin = self.tmp / "plugin root"
        self.comp = {"schema": 1, "bridge": {
            "cep": {"zxp": base.PLACEHOLDER, "sha256": base.PLACEHOLDER},
            "uxp": {"ccx": base.PLACEHOLDER, "sha256": base.PLACEHOLDER, "min_host": "26.5.0"}}}
        for k in ("WNC_TEST_HOSTS_RUNNING", "WNC_TEST_ADOBE_HOSTS"):
            os.environ.pop(k, None)
        self.sy = system_module()

    def ctx(self, plat="win-x64"):
        return make_ctx(self.home, self.comp, self.plugin, plat)

    def zxp(self, data, pin=True):
        touch(self.plugin / "dist" / "bridge.zxp", data)
        self.comp["bridge"]["cep"].update(zxp="dist/bridge.zxp", sha256=sha(data) if pin else base.PLACEHOLDER)

    def bundle(self, ctx):
        return self.sy.cep_extensions_dir(ctx.paths, ctx.platform) / "ai.thewhynot.cut.bridge"

    def test_cep_dir(self):
        ctx = self.ctx()
        self.assertEqual(self.sy.cep_extensions_dir(ctx.paths, "win-x64"),
                         self.home / "AppData" / "Roaming" / "Adobe" / "CEP" / "extensions")
        self.assertEqual(self.sy.cep_extensions_dir(ctx.paths, "mac-arm64"),
                         self.home / "Library" / "Application Support" / "Adobe" / "CEP" / "extensions")

    def test_no_artefacts_is_skipped(self):
        r = self.sy.step_adobe(self.ctx())
        self.assertEqual(r.status, "skipped")
        self.assertIn("Adobe panel files are not in this build yet", r.detail)
        self.comp["bridge"]["cep"]["zxp"] = "dist/missing.zxp"
        ctx = self.ctx()
        self.assertEqual(self.sy.step_adobe(ctx).status, "skipped")
        self.assertTrue(only_the_test_log(ctx.paths))

    def test_unsigned_zxp_is_amber_and_not_extracted(self):
        self.zxp(self.UNSIGNED)
        ctx = self.ctx()
        r = self.sy.step_adobe(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("unsigned panel: not installed", r.detail)
        self.assertFalse(self.sy.cep_extensions_dir(ctx.paths, ctx.platform).exists())

    def signed(self, version: bytes) -> bytes:
        return ffmpeg_zip({"CSXS/manifest.xml": b"<ExtensionManifest/>", "index.html": b"<html>" + version + b"</html>",
                           "META-INF/signatures.xml": b"<signatures/>"})

    def test_signed_zxp_is_extracted_and_each_update_keeps_one_prev(self):
        self.zxp(self.SIGNED)
        ctx = self.ctx()
        r = self.sy.step_adobe(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        b = self.bundle(ctx)
        self.assertEqual((b / "META-INF" / "signatures.xml").read_bytes(), b"<signatures/>")
        self.assertEqual(ctx.state.data["adobe"]["cep"]["path"], str(b))
        for version in (b"v2", b"v3"):
            self.zxp(self.signed(version))
            r = self.sy.step_adobe(self.ctx())
            self.assertEqual(r.status, "ok", r.detail)
        names = sorted(p.name for p in b.parent.iterdir())
        self.assertEqual(names, ["ai.thewhynot.cut.bridge", "ai.thewhynot.cut.bridge.prev"])
        self.assertEqual((b / "index.html").read_bytes(), b"<html>v3</html>")
        self.assertEqual((b.parent / "ai.thewhynot.cut.bridge.prev" / "index.html").read_bytes(), b"<html>v2</html>")

    def test_the_same_zxp_again_is_a_no_op_without_questions(self):
        self.zxp(self.SIGNED)
        self.assertEqual(self.sy.step_adobe(self.ctx()).status, "ok")
        self.zxp(self.signed(b"v2"))
        ctx = self.ctx()
        self.assertEqual(self.sy.step_adobe(ctx).status, "ok")
        prev = self.bundle(ctx).with_name("ai.thewhynot.cut.bridge.prev")
        before = (prev / "index.html").stat().st_mtime_ns, (self.bundle(ctx) / "index.html").stat().st_mtime_ns
        with mock.patch.dict(os.environ, {"WNC_TEST_HOSTS_RUNNING": "Adobe Premiere Pro.exe"}), \
                mock.patch.object(base, "can_ask", return_value=True), \
                mock.patch.object(base, "ask", side_effect=AssertionError("asked")), \
                mock.patch.object(base, "extract", side_effect=AssertionError("extracted")):
            r = self.sy.step_adobe(self.ctx())
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn("up to date", r.detail)
        self.assertEqual(((prev / "index.html").stat().st_mtime_ns,
                          (self.bundle(ctx) / "index.html").stat().st_mtime_ns), before)
        self.assertEqual((prev / "index.html").read_bytes(), b"<html>v1</html>")

    def test_a_removed_bundle_is_installed_again(self):
        self.zxp(self.SIGNED)
        ctx = self.ctx()
        self.assertEqual(self.sy.step_adobe(ctx).status, "ok")
        shutil.rmtree(self.bundle(ctx))
        self.assertEqual(self.sy.step_adobe(self.ctx()).status, "ok")
        self.assertTrue((self.bundle(ctx) / "index.html").is_file())

    def test_version_compare_pads_to_three_parts(self):
        from wnc_installer import adobe
        self.assertGreaterEqual(adobe._vt("26.5"), adobe._vt("26.5.0"))
        self.assertEqual(adobe._vt("26.5"), (26, 5, 0))
        self.assertEqual(adobe._vt("26"), (26, 0, 0))
        self.assertLess(adobe._vt("26.4.9"), adobe._vt("26.5.0"))
        self.assertEqual(adobe._vt(None), (0, 0, 0))

    def test_mac_cep_dir_is_used(self):
        self.zxp(self.SIGNED)
        ctx = self.ctx("mac-arm64")
        self.assertEqual(self.sy.step_adobe(ctx).status, "ok")
        self.assertTrue((self.home / "Library" / "Application Support" / "Adobe" / "CEP" / "extensions" /
                         "ai.thewhynot.cut.bridge" / "CSXS" / "manifest.xml").is_file())

    def test_bad_sha_is_red(self):
        self.zxp(self.SIGNED)
        self.comp["bridge"]["cep"]["sha256"] = "0" * 64
        ctx = self.ctx()
        self.assertEqual(self.sy.step_adobe(ctx).status, "red")
        self.assertFalse(self.bundle(ctx).exists())

    def test_running_host_without_questions_is_amber(self):
        self.zxp(self.SIGNED)
        with mock.patch.dict(os.environ, {"WNC_TEST_HOSTS_RUNNING": "Adobe Premiere Pro.exe"}):
            self.assertEqual(self.sy.hosts_running(True), ["Adobe Premiere Pro.exe"])
            ctx = self.ctx()
            r = self.sy.step_adobe(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("Adobe Premiere Pro.exe", r.detail)
        self.assertFalse(self.bundle(ctx).exists())

    def test_hosts_running_in_the_sandbox_never_probes(self):
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("probed")):
            self.assertEqual(self.sy.hosts_running(True), [])

    def test_uxp_command_is_recorded_in_the_sandbox(self):
        touch(self.plugin / "dist" / "bridge.ccx", b"PK ccx")
        self.comp["bridge"]["uxp"].update(ccx="dist/bridge.ccx", sha256=sha(b"PK ccx"))
        hosts = [{"app": "premiere", "version": "26.5.2"}]
        with mock.patch.dict(os.environ, {"WNC_TEST_ADOBE_HOSTS": json.dumps(hosts)}):
            ctx = self.ctx()
            r = self.sy.step_adobe(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        cmd = ctx.state.data["adobe"]["uxp"]["command"]
        self.assertEqual(cmd[1:], ["/install", str(self.plugin / "dist" / "bridge.ccx")])
        self.assertTrue(cmd[0].endswith("UnifiedPluginInstallerAgent.exe"))
        self.assertFalse(ctx.state.data["adobe"]["uxp"]["ran"])

    def test_uxp_needs_a_new_enough_premiere(self):
        touch(self.plugin / "dist" / "bridge.ccx", b"PK ccx")
        self.comp["bridge"]["uxp"].update(ccx="dist/bridge.ccx", sha256=sha(b"PK ccx"))
        with mock.patch.dict(os.environ, {"WNC_TEST_ADOBE_HOSTS": '[{"app": "premiere", "version": "25.6.0"}]'}):
            r = self.sy.step_adobe(self.ctx())
        self.assertEqual(r.status, "skipped", r.detail)
        self.assertIn("26.5.0", r.detail)

    def test_no_code_sets_the_adobe_debug_flag(self):
        flag = "Player" + "DebugMode"  # spelled in two halves so this test file is not a hit for other greps
        hits = [str(p) for p in (SK / "installer").rglob("*") if p.is_file() and flag.encode() in p.read_bytes()]
        self.assertEqual(hits, [])


# --------------------------------------------------------------------------------------------- fonts
class TestFonts(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        self.srv = Served(self, {})
        fonts, served = fixture_fonts(self.srv.base)
        self.srv.srv.files.update(served)
        self.comp = {"schema": 1, "fonts": fonts}
        self.sy = system_module()

    def ctx(self, plat="win-x64"):
        return make_ctx(self.home, self.comp, SK, plat)

    def registry(self, ctx):
        return json.loads((ctx.paths.sandbox_dir / "registry-fonts.json").read_text(encoding="utf-8"))

    def test_windows_sandbox(self):
        ctx = self.ctx()
        r = self.sy.step_fonts(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        fdir = self.home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"
        self.assertEqual(self.sy.user_font_dir(ctx.paths, "win-x64"), fdir)
        self.assertEqual((fdir / "FixA-Regular.ttf").read_bytes(), FONT_A)
        self.assertEqual((fdir / "Fix[wght].ttf").read_bytes(), FONT_B)
        self.assertEqual(self.registry(ctx), {"FixA-Regular (TrueType)": str(fdir / "FixA-Regular.ttf"),
                                              "Fix[wght] (TrueType)": str(fdir / "Fix[wght].ttf")})
        self.assertEqual((ctx.paths.fonts_dir / "1" / "Fix Sans-OFL.txt").read_bytes(), OFL)
        st = ctx.state.data["fonts"]
        self.assertEqual(sorted(st["installed"]), sorted([str(fdir / "FixA-Regular.ttf"), str(fdir / "Fix[wght].ttf")]))
        self.assertEqual(sorted(st["registry"]), ["FixA-Regular (TrueType)", "Fix[wght] (TrueType)"])
        hits = len(self.srv.srv.hits)
        ctx2 = self.ctx()
        self.assertEqual(self.sy.step_fonts(ctx2).status, "ok")
        self.assertEqual(len(self.srv.srv.hits), hits)  # cached
        self.assertEqual(sorted(ctx2.state.data["fonts"]["installed"]), sorted(st["installed"]))

    def test_font_registry_interface(self):
        ctx = self.ctx()
        reg = self.sy.FontRegistry.for_paths(ctx.paths)
        reg.set("A (TrueType)", "C:/x/A.ttf")
        self.assertEqual(reg.get("A (TrueType)"), "C:/x/A.ttf")
        reg.delete("A (TrueType)")
        reg.delete("not there")
        self.assertIsNone(reg.get("A (TrueType)"))
        self.assertEqual(self.registry(ctx), {})

    def test_mac(self):
        ctx = self.ctx("mac-arm64")
        r = self.sy.step_fonts(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual((self.home / "Library" / "Fonts" / "FixA-Regular.ttf").read_bytes(), FONT_A)
        self.assertFalse((ctx.paths.sandbox_dir / "registry-fonts.json").exists())
        self.assertEqual(ctx.state.data["fonts"]["registry"], [])

    def test_a_different_existing_file_is_left_alone(self):
        ctx = self.ctx()
        mine = touch(self.sy.user_font_dir(ctx.paths, "win-x64") / "FixA-Regular.ttf", b"the editor's own font")
        r = self.sy.step_fonts(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertIn("FixA-Regular.ttf", r.detail)
        self.assertEqual(mine.read_bytes(), b"the editor's own font")
        self.assertEqual(list(self.registry(ctx)), ["Fix[wght] (TrueType)"])
        self.assertNotIn(str(mine), ctx.state.data["fonts"]["installed"])

    def test_our_older_font_is_replaced(self):
        ctx = self.ctx()
        self.assertEqual(self.sy.step_fonts(ctx).status, "ok")
        ours = self.sy.user_font_dir(ctx.paths, "win-x64") / "FixA-Regular.ttf"
        ours.write_bytes(b"an older build of our font")  # what an earlier WhyNot Cut release installed
        ctx2 = self.ctx()
        r = self.sy.step_fonts(ctx2)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(ours.read_bytes(), FONT_A)
        self.assertIn(str(ours), ctx2.state.data["fonts"]["installed"])
        self.assertEqual(self.registry(ctx2)["FixA-Regular (TrueType)"], str(ours))

    def test_bad_sha_is_red_and_nothing_is_installed(self):
        self.comp["fonts"]["files"][1]["sha256"] = "0" * 64
        ctx = self.ctx()
        r = self.sy.step_fonts(ctx)
        self.assertEqual(r.status, "red", r.detail)
        self.assertFalse(self.sy.user_font_dir(ctx.paths, "win-x64").exists())
        self.assertFalse((ctx.paths.sandbox_dir / "registry-fonts.json").exists())

    def test_placeholder_is_skipped(self):
        self.comp["fonts"]["files"][0]["sha256"] = base.PLACEHOLDER
        r = self.sy.step_fonts(self.ctx())
        self.assertEqual(r.status, "skipped")
        self.assertEqual(self.srv.srv.hits, [])


# --------------------------------------------------------------------------------------------- model
class TestModelChoice(unittest.TestCase):
    """ID-8 / ID-9 (owner decision 2026-10-12): the installer asks which Whisper model to install; the default is
    the strongest, large-v3, on every machine; a saved preference is the default on a re-install; --model wins."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        self.sy = system_module()
        self.comp = base.load_components(COMPONENTS)

    def ctx(self, plat="win-x64", **args):
        a = {"clients_folder": None, "language": None, "model": None}
        a.update(args)
        return make_ctx(self.home, self.comp, SK, plat, **a)

    def test_the_choices_strongest_first_with_their_sizes(self):
        self.assertEqual(self.sy.MODELS, ("large-v3", "large-v3-turbo", "medium", "small"))
        self.assertEqual(self.sy.DEFAULT_MODEL, "large-v3")
        self.assertEqual(self.sy.MODEL_SIZES, {"large-v3": "2.9 GB", "large-v3-turbo": "1.6 GB", "medium": "1.5 GB",
                                               "small": "0.5 GB"})

    def test_the_default_is_large_v3_on_every_machine(self):
        for plat, nvidia in (("win-x64", True), ("win-x64", False), ("mac-arm64", False), ("mac-x64", False)):
            with self.subTest(plat=plat, nvidia=nvidia):
                ctx = self.ctx(plat)
                ctx.facts["nvidia"] = nvidia
                a = self.sy.resolve_answers(ctx)
                self.assertEqual((a["whisper_model"], a["from"]["whisper_model"]), ("large-v3", "default"))

    def test_the_flag_wins_then_the_saved_preference(self):
        prefs = touch(self.home / ".claude" / "whynot-cut.local.md", b"---\nwhisper_model: small\n---\n")
        self.assertEqual(self.sy.resolve_answers(self.ctx())["whisper_model"], "small")
        a = self.sy.resolve_answers(self.ctx(model="medium"))
        self.assertEqual((a["whisper_model"], a["from"]["whisper_model"]), ("medium", "--model"))
        prefs.write_bytes(b"---\nwhisper_model: tiny-xl\n---\n")  # not a model the engine knows: the default
        self.assertEqual(self.sy.resolve_answers(self.ctx())["whisper_model"], "large-v3")

    def test_the_question_lists_every_model_with_its_size_in_both_languages(self):
        touch(self.home / ".claude" / "whynot-cut.local.md", b"---\nwhisper_model: medium\n---\n")
        prompts = []

        def answer(replies):
            def ask(prompt, default=""):
                prompts.append(prompt)
                return replies.pop(0) if replies else default
            return ask
        for replies, want in (([""], "medium"), (["2"], "large-v3-turbo"), (["small"], "small"),
                              (["huge", "9", "1"], "large-v3")):
            with self.subTest(replies=list(replies)):
                ctx = self.ctx(yes=False, customise=True)  # (D-T1: questions only on the Customise path)
                prompts.clear()
                # the model first (task 9 order: model, language, clients folder); the other two keep their defaults
                with mock.patch.object(base, "can_ask", return_value=True), \
                        mock.patch.object(base, "ask", side_effect=answer(list(replies) + ["", ""])):
                    r = self.sy.step_questions(ctx)
                self.assertEqual(ctx.answers["whisper_model"], want, r.detail)
                self.assertIn("Whisper " + want, r.detail)
                self.assertIn("[medium]", prompts[0])  # the saved preference is the default on a re-install
        text = ctx.paths.logs_dir.joinpath("install-test.log").read_text(encoding="utf-8")
        for needle in ("large-v3", "2.9 GB", "large-v3-turbo", "1.6 GB", "medium", "1.5 GB", "small", "0.5 GB",
                       "best accuracy", "faster", "أعلى دقة", "أسرع"):
            self.assertIn(needle, text)

    def test_no_question_with_yes(self):
        ctx = self.ctx()
        with mock.patch.object(base, "ask", side_effect=AssertionError("asked with --yes")):
            self.sy.step_questions(ctx)
        self.assertEqual(ctx.answers["whisper_model"], "large-v3")


class TestModelStep(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        os.environ.pop("WNC_TEST_MODEL", None)
        self.sy = system_module()
        self.comp = base.load_components(COMPONENTS)

    def test_sandbox_is_skipped_with_the_command(self):
        ctx = make_ctx(self.home, self.comp, SK, "win-x64")
        ctx.runtime_python = Path(sys.executable)
        ctx.facts["nvidia"] = False
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no background process in tests")):
            r = self.sy.step_model(ctx)
        self.assertEqual(r.status, "skipped")
        self.assertTrue(r.detail.endswith("model-download --model large-v3"), r.detail)  # no NVIDIA: still large-v3
        self.assertFalse(ctx.paths.logs_dir.exists() and list(ctx.paths.logs_dir.glob("model-download-*")))

    def test_skip_flag_still_says_the_command(self):
        ctx = make_ctx(self.home, self.comp, SK, "win-x64", skip=["model"])
        ctx.runtime_python = Path(sys.executable)
        [r] = base.run_steps(ctx, [("model", self.sy.step_model, ())])
        self.assertEqual(r.status, "skipped")
        self.assertTrue(r.detail.endswith("model-download --model large-v3"), r.detail)

    def test_the_chosen_model_is_downloaded(self):
        ctx = make_ctx(self.home, self.comp, SK, "win-x64")
        ctx.runtime_python = Path(sys.executable)
        ctx.answers = {"clients_root": str(self.home / "C"), "language": "ar", "whisper_model": "small"}
        r = self.sy.step_model(ctx)
        self.assertTrue(r.detail.endswith("model-download --model small"), r.detail)


# --------------------------------------------------------------------------------------------- settings / doctor
class TestSettingsAndDoctor(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        tmp = Path(self._td.name)
        self.home = tmp / ARABIC_HOME
        self.fx = make_fixture_plugin(tmp / "repo", "http://127.0.0.1:9")
        self.elog = tmp / "engine-calls.jsonl"
        env = mock.patch.dict(os.environ, {"WNC_TEST_ENGINE_LOG": str(self.elog)})
        env.start()
        self.addCleanup(env.stop)
        for k in ("WNC_TEST_DOCTOR_RAW", "WNC_TEST_ENGINE_EXIT"):
            os.environ.pop(k, None)
        self.sy = system_module()

    def ctx(self):
        c = make_ctx(self.home, self.fx.components, self.fx.plugin_root, "win-x64")
        c.runtime_python = Path(sys.executable)
        c.answers = {"clients_root": str(self.home / "Documents" / "WhyNot Clients"), "language": "ar"}
        c.facts["nvidia"] = False
        return c

    def calls(self):
        return [json.loads(x) for x in self.elog.read_text(encoding="utf-8").splitlines() if x.strip()]

    def test_settings_argv(self):
        r = self.sy.step_settings(self.ctx())
        self.assertEqual(r.status, "ok", r.detail)
        [argv] = self.calls()
        self.assertEqual(argv[:4], ["settings", "--init", str(self.home), "--force"])
        sets = [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]
        self.assertEqual(sets, [f"clients_root={self.home / 'Documents' / 'WhyNot Clients'}", "language=ar",
                                "whisper_model=large-v3"])  # the strongest, also without an NVIDIA GPU

    def test_a_saved_model_choice_is_kept(self):
        touch(self.home / ".claude" / "whynot-cut.local.md",
              b"---\nlanguage: en\nwhisper_model: medium\nclients_root: ''\n---\n")
        ctx = self.ctx()
        self.assertEqual(self.sy.step_settings(ctx).status, "ok")
        [argv] = self.calls()
        self.assertIn("whisper_model=medium", argv)
        self.assertIn("language=ar", argv)  # ctx.answers (flags / questions) still go in
        r = self.sy.step_model(ctx)  # sandbox: skipped, but it names the command it would run
        self.assertEqual(r.status, "skipped")
        self.assertTrue(r.detail.endswith("model-download --model medium"), r.detail)

    def test_the_answered_model_is_written(self):
        touch(self.home / ".claude" / "whynot-cut.local.md", b"---\nwhisper_model: medium\n---\n")
        ctx = self.ctx()
        ctx.answers["whisper_model"] = "large-v3-turbo"  # --model / the question beat the saved preference
        self.assertEqual(self.sy.step_settings(ctx).status, "ok")
        [argv] = self.calls()
        self.assertIn("whisper_model=large-v3-turbo", argv)

    def test_an_unusable_saved_model_gets_the_strongest(self):
        touch(self.home / ".claude" / "whynot-cut.local.md", b"---\nwhisper_model: tiny-xl\n---\n")
        self.assertEqual(self.sy.step_settings(self.ctx()).status, "ok")
        [argv] = self.calls()
        self.assertIn("whisper_model=large-v3", argv)

    def test_settings_failure_is_amber(self):
        with mock.patch.dict(os.environ, {"WNC_TEST_ENGINE_EXIT": "2"}):
            r = self.sy.step_settings(self.ctx())
        self.assertEqual(r.status, "amber")

    def test_doctor_and_checklist(self):
        ctx = self.ctx()
        r = self.sy.step_doctor(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual([c[0] for c in self.calls()], ["doctor"])
        ld = ctx.state.data["last_doctor"]
        self.assertEqual((ld["verdict"], ld["ready"]), ("ready", True))
        results = [base.StepResult("runtime", "ok", "built"), base.StepResult("gpu", "skipped", "no NVIDIA GPU"),
                   base.StepResult("fonts", "red", "sha256 mismatch"), r]
        text = self.sy.render_checklist(results, ctx.facts["doctor"])
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("[OK] runtime"))
        self.assertTrue(lines[1].startswith("[!!] gpu") and "no NVIDIA GPU" in lines[1])
        self.assertTrue(lines[2].startswith("[XX] fonts"))
        self.assertIn("[!!] x -> y", lines)

    def test_doctor_not_json_is_amber(self):
        with mock.patch.dict(os.environ, {"WNC_TEST_DOCTOR_RAW": "Traceback: boom"}):
            ctx = self.ctx()
            r = self.sy.step_doctor(ctx)
        self.assertEqual(r.status, "amber")
        self.assertIsNone(ctx.state.data["last_doctor"]["verdict"])

    def test_real_doctor_shape(self):
        ready = {"engine": True, "premiere_build": False}
        with mock.patch.dict(os.environ, {"WNC_TEST_DOCTOR_RAW": json.dumps(
                {"verdict": "READY (no live Premiere build yet)", "ready": ready, "fixes": []})}):
            ctx = self.ctx()
            r = self.sy.step_doctor(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertTrue(ctx.state.data["last_doctor"]["ready"])


# --------------------------------------------------------------------------------------------- launch
class TestLaunch(unittest.TestCase):
    def test_sandbox_never_opens_anything(self):
        sy = system_module()
        with TempDir() as td:
            ctx = make_ctx(Path(td) / "h", {"schema": 1}, SK, "win-x64")
            with mock.patch.object(subprocess, "run", side_effect=AssertionError("ran")):
                r = sy.step_launch(ctx)
        self.assertEqual(r.status, "skipped")
        self.assertIn("/whynot-cut:start", sy.START_MESSAGE)
        self.assertIn("افتح Claude واكتب /whynot-cut:start", sy.START_MESSAGE_AR)

    def test_macos_says_to_click_allow_after_the_install(self):
        sy = system_module()
        self.assertIn("Allow", sy.MAC_ALLOW_MESSAGE)
        self.assertIn("Allow", sy.MAC_ALLOW_MESSAGE_AR)
        for plat, shown in (("mac-arm64", True), ("mac-x64", True), ("win-x64", False)):
            with self.subTest(plat), TempDir() as td:
                home = Path(td) / ARABIC_HOME
                r = subprocess.run([sys.executable, "-B", str(CORE / "wnc_install.py"), "install", "--home", str(home),
                                    "--dry-run", "--yes"], capture_output=True, text=True, encoding="utf-8",
                                   env=sandbox_env(WNC_TEST_PLATFORM=plat), timeout=120, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(sy.MAC_ALLOW_MESSAGE in r.stdout, shown)
                self.assertEqual(sy.MAC_ALLOW_MESSAGE_AR in r.stdout, shown)
                self.assertIn(sy.START_MESSAGE_AR, r.stdout)


# --------------------------------------------------------------------------------------------- whole install
class TestInstallDryRun(unittest.TestCase):
    def test_dry_run_writes_nothing_and_names_every_step(self):
        with TempDir() as td:
            home = Path(td) / ARABIC_HOME
            home.mkdir()
            r = subprocess.run([sys.executable, "-B", str(CORE / "wnc_install.py"), "install", "--home", str(home),
                                "--dry-run", "--yes"], capture_output=True, text=True, encoding="utf-8",
                               env=sandbox_env(), timeout=120, stdin=subprocess.DEVNULL)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(list(home.iterdir()), [])
        for name in STEP_NAMES:
            self.assertIn(f"== {name} ==", r.stdout)
        self.assertIn("dry run", r.stdout)


class TestInstallEndToEnd(unittest.TestCase):
    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.srv = Served(self, {})
        self.fx = make_fixture_plugin(self.tmp / "zip root", self.srv.base)
        self.srv.srv.files.update(self.fx.served)
        self.elog = self.tmp / "engine-calls.jsonl"
        self.env = sandbox_env(WNC_TEST_UV=str(FAKE_UV), WNC_CLAUDE_CLI=str(FAKE_CLAUDE),
                               FAKE_CLAUDE_LOG=str(self.tmp / "claude.jsonl"), WNC_TEST_ENGINE_LOG=str(self.elog))

    def install(self):
        core = self.fx.plugin_root / "installer" / "core" / "wnc_install.py"
        return subprocess.run([sys.executable, "-B", "-I", str(core), "install", "--home", str(self.home), "--yes",
                               "--skip", "model"], capture_output=True, text=True, encoding="utf-8", env=self.env,
                              timeout=600, stdin=subprocess.DEVNULL)

    def test_install_then_reinstall(self):
        r = self.install()
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        paths = base.Paths.from_env(str(self.home), env={})
        self.assertTrue(paths.current_file.is_file())
        st = json.loads(paths.state_file.read_text(encoding="utf-8"))
        bad = {k: v for k, v in st["steps"].items() if v["status"] not in ("ok", "skipped")}
        self.assertEqual(bad, {}, out)
        self.assertEqual(st["plugin"], "3.0.0")
        self.assertEqual(st["runtime"]["id"], "r-" + sha(LOCK_A)[:12])
        self.assertEqual(st["answers"]["language"], "ar")
        self.assertEqual(st["answers"]["clients_root"], str(self.home / "Documents" / "WhyNot Clients"))
        self.assertEqual(st["last_doctor"]["verdict"], "ready")
        for key in ("channel", "installed_at", "platform", "uv", "python"):
            self.assertIn(key, st)
        settings = json.loads(paths.settings_file.read_text(encoding="utf-8"))
        self.assertIn("thewhynot-ai", settings["extraKnownMarketplaces"])
        self.assertTrue(settings["enabledPlugins"]["whynot-cut@thewhynot-ai"])
        if IS_WIN:
            self.assertEqual(len(json.loads((paths.sandbox_dir / "registry-fonts.json").read_text("utf-8"))), 2)
        self.assertTrue(list(paths.logs_dir.glob("install-*.log")))
        self.assertTrue((paths.logs_dir / "install-checklist.json").is_file())
        self.assertIn("[!!] x -> y", r.stdout)
        self.assertIn("/whynot-cut:start", r.stdout)
        self.assertFalse((self.home / "Documents" / "WhyNot Clients").exists())
        engine = [json.loads(x)[0] for x in self.elog.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual(engine, ["settings", "doctor"])  # no model-download (skipped), no gpu-enable (no NVIDIA)
        hits = len(self.srv.srv.hits)
        r2 = self.install()
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(len(self.srv.srv.hits), hits, self.srv.srv.hits[hits:])


# --------------------------------------------------------------------------------------------- T7.2 shells
INSTALLER = SK / "installer"
SHELL_FILES = {"install.ps1": INSTALLER / "install.ps1", "install.sh": INSTALLER / "install.sh",
               "bootstrap.ps1": INSTALLER / "core" / "bootstrap.ps1", "bootstrap.sh": INSTALLER / "core" / "bootstrap.sh"}
H3_EN = "hosting is not ready yet (H3)"
H3_AR = "الاستضافة غير جاهزة بعد (H3)"


def find_powershell():
    """Windows PowerShell 5.1 (what every editor's PC has); None elsewhere."""
    return shutil.which("powershell") if IS_WIN else None


def find_bash():
    """Git Bash on Windows (never WSL's System32\\bash.exe), else bash from PATH."""
    if not IS_WIN:
        return shutil.which("bash")
    cands = []
    git = shutil.which("git")
    if git:
        root = Path(git).resolve().parents[1]
        cands += [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    cands.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe")
    return next((str(c) for c in cands if c.is_file()), None)


def real_profile() -> Path:
    """This user's REAL profile folder, from the OS rather than the (possibly sandboxed) environment."""
    if IS_WIN:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0028, None, 0, buf) == 0:  # CSIDL_PROFILE
            return Path(buf.value)
    else:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    return Path.home()


def live_snapshot() -> dict:
    """Read-only fingerprint of the real ~/.claude/settings.json and the real ~/.whynot-cut top level."""
    prof = real_profile()
    settings, engine = prof / ".claude" / "settings.json", prof / ".whynot-cut"
    st = settings.stat() if settings.is_file() else None
    return {"settings": (st.st_mtime_ns, st.st_size) if st else None,
            "engine_home": sorted(os.listdir(engine)) if engine.is_dir() else None}


def release_zip(fx: types.SimpleNamespace, dest: Path) -> str:
    """The fixture marketplace as a release zip (whynot-cut-marketplace/... like package.py); returns its sha256."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(fx.root.rglob("*")):
            if p.is_file():
                z.write(p, "whynot-cut-marketplace/" + p.relative_to(fx.root).as_posix())
    return sha(dest.read_bytes())


def shell_steps(text: str, pattern: str) -> list:
    m = re.search(pattern, text)
    return re.findall(r"[a-z]+", m.group(1)) if m else []


class TestShellScripts(unittest.TestCase):
    """Static checks of the four shell files (they run on machines this suite cannot always reach)."""

    def test_the_files_exist_ps1_are_ascii_and_sh_are_lf(self):
        for name, p in SHELL_FILES.items():
            data = p.read_bytes()
            if name.endswith(".ps1"):  # Windows PowerShell 5.1 reads a BOM-less file as ANSI: keep them ASCII
                self.assertTrue(all(b < 128 for b in data), name)
            else:
                self.assertNotIn(b"\r\n", data, name)
                self.assertTrue(data.startswith(b"#!/usr/bin/env bash\n"), name)

    def test_the_bootstraps_know_the_core_steps(self):
        ps = SHELL_FILES["bootstrap.ps1"].read_text(encoding="utf-8")
        sh = SHELL_FILES["bootstrap.sh"].read_text(encoding="utf-8")
        self.assertEqual(shell_steps(ps, r"\$WncStepNames\s*=\s*@\(([^)]*)\)"), list(cli.STEP_ORDER))
        self.assertEqual(shell_steps(sh, r'\nSTEP_NAMES="([^"]*)"'), list(cli.STEP_ORDER))
        # and the uninstall steps (a dry run without Python names them)
        un = [n for n, _f, _d in cli.UNINSTALL_STEPS]
        self.assertEqual(shell_steps(ps, r"\$WncUninstallStepNames\s*=\s*@\(([^)]*)\)"), un)
        self.assertEqual(shell_steps(sh, r'UNINSTALL_STEP_NAMES="([^"]*)"'), un)

    def test_the_bootstraps_use_the_runtime_contract(self):
        for name in ("bootstrap.ps1", "bootstrap.sh"):
            text = SHELL_FILES[name].read_text(encoding="utf-8")
            for needle in ("--no-bin", "--no-registry", "only-managed", "UV_NO_MODIFY_PATH", "UV_NO_CONFIG",
                           "UV_PYTHON_INSTALL_DIR", "UV_CACHE_DIR", "UV_PYTHON_PREFERENCE", "utf8", "wnc_install.py"):
                self.assertIn(needle, text, f"{name}: {needle}")

    def test_macos_reads_json_with_javascript_not_plutil(self):
        # plutil turns JSON into a plist, which has no null (components.json has nulls); the JXA scripts take the
        # file / JSON text and the key path as run(argv) arguments, never spliced into the script text
        for name in ("bootstrap.sh", "install.sh"):
            text = SHELL_FILES[name].read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^[^#\n]*\bplutil\b", name)  # (comments may say why not)
            self.assertIn('osascript -l JavaScript -e "$', text, name)
            self.assertIn("function run(argv)", text, name)
            self.assertIn('"$1" "$2" 2>/dev/null </dev/null', text, name)

    def test_the_readme_names_every_flag(self):
        text = (INSTALLER / "README.md").read_text(encoding="utf-8")
        for flag in ("-Home", "-DryRun", "-Yes", "-ClientsFolder", "-Language", "-Channel", "-Components", "-Skip",
                     "-Uninstall", "-RemoveEngine", "-RemoveModels", "-Source", "-SourceSha256",
                     "--home", "--dry-run", "--yes", "--clients-folder", "--language", "--channel", "--components",
                     "--skip", "--uninstall", "--remove-engine", "--remove-models", "--source", "--source-sha256",
                     "WNC_TEST_UV", "WNC_TEST_PLATFORM", "logs", "-Model", "--model", "-EngineHome",
                     "WNC_TEST_ANSWERS", "WNC_TEST_FREE_GB", "-Customise", "--customise", "WNC_TEST_KEYS",
                     "WNC_TEST_COUNTDOWN_S", "WNC_TEST_ANSWERS_AT"):
            self.assertIn(flag, text)
        # task 9 (D-T1): no questions by default, the countdown, and the resolved-home guard with its self-fix
        for needle in ("Installing everything WhyNot Cut needs (about N GB)", "Press C to customise", "answers.mode",
                       SELF_FIX):
            self.assertIn(needle, text)
        # what -RemoveEngine keeps, and where the engine home comes from
        for needle in ("library/", "plugin-options.json", "pluginConfigs", "WHYNOT_HOME", "--engine-home"):
            self.assertIn(needle, text)
        # task 8: the model choices with their sizes, the suggested plain folder, and the optional lint variables
        # (never named WNC_*: other suites assert that no WNC_* variable reaches the engine)
        for needle in ("large-v3-turbo", "2.9 GB", "1.6 GB", "1.5 GB", "0.5 GB", "C:" + chr(92) + "WhyNotCut",
                       "WHYNOTCUT_PSSA_PATH", "WHYNOTCUT_SHELLCHECK"):
            self.assertIn(needle, text)
        for old in ("WNC_PSSA_PATH", "WNC_SHELLCHECK"):
            self.assertNotIn(old, text.replace("WHYNOTCUT_", "-"))


class _ShellCase(unittest.TestCase):
    """A sandbox home with a space and Arabic letters, a fixture plugin whose pins point at a local http.server."""
    UV_PLAT = "win-x64"

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.srv = Served(self, {})
        self.fx = make_fixture_plugin(self.tmp / "zip root", self.srv.base)
        self.srv.srv.files.update(self.fx.served)
        self.paths = base.Paths.from_env(str(self.home), env={})

    def uv_asset(self, plat=None) -> dict:
        return self.fx.components["uv"]["assets"][plat or self.UV_PLAT]

    def uv_archive(self, plat=None) -> Path:
        return self.paths.downloads_dir / self.uv_asset(plat)["url"].rsplit("/", 1)[-1]

    def break_uv_sha(self, plat=None) -> None:
        comp = json.loads(self.fx.components_path.read_text(encoding="utf-8"))
        comp["uv"]["assets"][plat or self.UV_PLAT]["sha256"] = "0" * 64
        self.fx.components_path.write_text(json.dumps(comp, indent=2), encoding="utf-8")

    def uv_hits(self, plat=None) -> list:
        path = "/" + self.uv_asset(plat)["url"].split("/", 3)[-1]
        return [h for h in self.srv.srv.hits if h == path]

    def assert_installed(self, r, plat: str) -> None:
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        arc = self.uv_archive(plat)
        self.assertTrue(arc.is_file(), out)  # the uv archive was downloaded and verified, even with WNC_TEST_UV
        self.assertEqual(sha(arc.read_bytes()), self.uv_asset(plat)["sha256"])
        self.assertTrue((self.paths.bin_dir / ("uv.exe" if plat.startswith("win") else "uv")).is_file(), out)
        self.assertEqual(len(self.uv_hits(plat)), 1)
        self.assertTrue(self.paths.current_file.is_file(), out)
        settings = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        self.assertIn("thewhynot-ai", settings["extraKnownMarketplaces"])
        logs = list(self.paths.logs_dir.glob("install-*.log"))
        self.assertEqual(len(logs), 1, [p.name for p in logs])  # one log, shared by the bootstrap and the core
        text = logs[0].read_text(encoding="utf-8")
        for needle in ("== uv ==", "== python ==", "== runtime ==", "== launch =="):
            self.assertIn(needle, text)
        self.assertIn("/whynot-cut:start", r.stdout)
        self.assertFalse((self.home / "Documents" / "WhyNot Clients").exists())


@unittest.skipUnless(find_powershell(), "Windows PowerShell is not available")
class TestPowerShellFrontEnd(_ShellCase):
    def env(self, **extra) -> dict:
        env = sandbox_env(WNC_TEST_UV=str(FIXTURES / "fake_uv.cmd"), FAKE_UV_PYTHON=sys.executable,
                          WNC_CLAUDE_CLI=str(FIXTURES / "fake_claude.cmd"), FAKE_CLAUDE_PYTHON=sys.executable,
                          FAKE_CLAUDE_LOG=str(self.tmp / "claude.jsonl"),
                          WNC_TEST_ENGINE_LOG=str(self.tmp / "engine.jsonl"))
        env.pop("WNC_TEST_PLATFORM", None)
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def ps(self, script: Path, *args, env=None):
        return subprocess.run([find_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", str(script), *[str(a) for a in args]], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env or self.env(), timeout=600,
                              stdin=subprocess.DEVNULL, cwd=str(self.tmp))

    def front(self) -> Path:
        return self.fx.plugin_root / "installer" / "install.ps1"

    def test_install_in_an_arabic_home_touches_nothing_outside(self):
        before = live_snapshot()
        r = self.ps(self.front(), "-Home", self.home, "-Yes", "-Skip", "model,launch",
                    "-Components", self.fx.components_path)
        self.assert_installed(r, "win-x64")
        self.assertEqual((self.paths.bin_dir / "uv.exe").read_bytes(), b"MZ fake uv")
        self.assertEqual(live_snapshot(), before)
        self.assertLessEqual(set(os.listdir(self.tmp)), {ARABIC_HOME, "zip root", "claude.jsonl", "engine.jsonl"})

    def test_paths_ending_in_a_backslash_reach_the_core_intact(self):
        # Windows PowerShell 5.1 passes 'C:\x y\' to a native program as "C:\x y\": the program reads \" as a quote,
        # so that value is corrupted and every later flag swallowed. Tab completion produces exactly such paths.
        clients = self.tmp / "WhyNot Clients"
        r = self.ps(self.front(), "-Home", str(self.home) + "\\", "-Yes", "-Skip", "model,launch",
                    "-ClientsFolder", str(clients) + "\\", "-Language", "en")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        st = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(st["answers"]["clients_root"], str(clients), out)
        self.assertEqual(st["answers"]["language"], "en", out)
        self.assertFalse(clients.exists())

    def test_the_bootstraps_quoting_guard_doubles_trailing_backslashes(self):
        # the general guard for any native argument with whitespace and a trailing backslash (PS < 7.3)
        boot = (INSTALLER / "core" / "bootstrap.ps1").read_text(encoding="utf-8")
        m = re.search(r"(    function ConvertTo-WncNativeArgument.*?\n    }\n)", boot, re.S)
        self.assertIsNotNone(m)
        probe = self.tmp / "probe.py"
        probe.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
        script = self.tmp / "guard.ps1"
        script.write_text(m.group(1) + "\n$a = ConvertTo-WncNativeArgument @('C:\\x y\\', 'C:\\plain\\', 'a b', '--yes')\n"
                          f"& '{sys.executable}' -I '{probe}' @a\n", encoding="ascii")
        r = self.ps(script)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1]),
                         ["C:\\x y\\", "C:\\plain\\", "a b", "--yes"], r.stdout + r.stderr)

    def test_uv_already_at_the_pinned_version_is_not_downloaded(self):
        uv = self.paths.bin_dir / "uv.exe"
        uv.parent.mkdir(parents=True)
        touch(self.paths.state_file, GENUINE_STATE)  # an earlier run claimed the folder (a bare uv is not ours)
        src = ('public static class P { public static void Main() { '
               'System.Console.WriteLine("uv 0.13.0 (fixture)"); } }')
        built = self.tmp / "uv-fixture.exe"  # built in the ASCII temp root, then copied into the Arabic home
        build = self.tmp / "build-uv.ps1"
        build.write_text(f"Add-Type -TypeDefinition '{src}' -OutputAssembly '{built}' -OutputType ConsoleApplication\n",
                         encoding="utf-8-sig")
        b = self.ps(build)
        if not built.is_file():
            self.skipTest(f"cannot build a stand-in uv.exe here: {b.stdout}{b.stderr}")
        shutil.copyfile(built, uv)
        r = self.ps(self.front(), "-Home", self.home, "-Yes", "-Skip", "model,launch")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("uv 0.13.0 is installed", out)
        self.assertEqual(self.uv_hits(), [])
        self.assertFalse(self.uv_archive().exists())
        self.assertTrue(self.paths.current_file.is_file())

    def test_dry_run_leaves_the_home_empty(self):
        self.home.mkdir()
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.srv.srv.hits, [])
        for name in ("uv", "python", "preflight", "launch"):  # with WNC_TEST_UV the core's own dry run follows
            self.assertIn(f"== {name} ==", r.stdout)

    def test_dry_run_without_uv_names_the_remaining_steps(self):
        self.home.mkdir()
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes", env=self.env(WNC_TEST_UV=None))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertNotIn("== preflight ==", r.stdout)
        self.assertIn(", ".join(cli.STEP_ORDER), r.stdout)
        self.assertIn(self.uv_asset()["url"], r.stdout)

    def test_a_bad_uv_sha256_stops_with_3_and_names_the_file(self):
        self.break_uv_sha()
        r = self.ps(self.front(), "-Home", self.home, "-Yes", "-Skip", "model,launch")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 3, out)
        self.assertIn("uv-x86_64-pc-windows-msvc.zip", out)
        self.assertIn("sha256", out)
        self.assertFalse(self.uv_archive().exists())
        self.assertEqual(list(self.paths.downloads_dir.iterdir()), [])
        self.assertFalse(self.paths.current_file.exists())
        logs = list(self.paths.logs_dir.glob("install-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn(str(logs[0]), out)


@unittest.skipUnless(find_powershell(), "Windows PowerShell is not available")
class TestPowerShellOneLiner(TestPowerShellFrontEnd):
    """install.ps1 alone (as `irm | iex` gets it): the plugin comes from -Source, never from the script's folder."""

    def setUp(self):
        super().setUp()
        self.zip = self.tmp / "WhyNotCut-3.0.0.zip"
        self.zip_sha = release_zip(self.fx, self.zip)
        lone = self.tmp / "lone"
        lone.mkdir()
        self.lone = lone / "install.ps1"
        shutil.copyfile(INSTALLER / "install.ps1", self.lone)

    # the inherited local-mode tests are not repeated here
    test_install_in_an_arabic_home_touches_nothing_outside = None
    test_dry_run_leaves_the_home_empty = None
    test_dry_run_without_uv_names_the_remaining_steps = None
    test_a_bad_uv_sha256_stops_with_3_and_names_the_file = None
    test_paths_ending_in_a_backslash_reach_the_core_intact = None
    test_the_bootstraps_quoting_guard_doubles_trailing_backslashes = None
    test_uv_already_at_the_pinned_version_is_not_downloaded = None

    def test_installs_from_the_source_zip(self):
        r = self.ps(self.lone, "-Home", self.home, "-Yes", "-Skip", "model,launch", "-Source", self.zip,
                    "-SourceSha256", self.zip_sha)
        self.assert_installed(r, "win-x64")
        rel = self.paths.downloads_dir / f"release-{self.zip_sha[:8]}"
        self.assertEqual(sha((rel / self.zip.name).read_bytes()), self.zip_sha)
        plugin = rel / "x" / "whynot-cut-marketplace" / "whynot-cut"
        self.assertTrue((plugin / "installer" / "core" / "bootstrap.ps1").is_file())

    def test_the_scriptblock_one_liner_returns_to_the_session(self):
        # `& ([scriptblock]::Create((irm ...))) -Source ...`: no script path, so the script must not `exit` (that
        # would close the editor's PowerShell window); the exit code is left in $LASTEXITCODE instead
        env = self.env(WNC_T_SCRIPT=str(self.lone), WNC_T_HOME=str(self.home), WNC_T_ZIP=str(self.zip),
                       WNC_T_SHA=self.zip_sha)
        cmd = ("& ([scriptblock]::Create([IO.File]::ReadAllText($env:WNC_T_SCRIPT))) -Home $env:WNC_T_HOME -Yes "
               "-Skip model,launch -Source $env:WNC_T_ZIP -SourceSha256 $env:WNC_T_SHA; "
               "'after the one-liner: ' + $LASTEXITCODE")
        r = subprocess.run([find_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=600, stdin=subprocess.DEVNULL, cwd=str(self.tmp))
        self.assert_installed(r, "win-x64")
        self.assertIn("after the one-liner: 0", r.stdout)

    def test_the_release_zip_is_cached_under_the_chosen_engine_home(self):
        # fix round 1 (small 1): -Source caches under the engine home, here a Documents folder's WhyNotCut subfolder
        docs = self.home / "Documents"
        thesis = touch(docs / "thesis.docx", b"my thesis")
        r = self.ps(self.lone, "-Home", self.home, "-EngineHome", docs, "-Yes", "-Skip", "model,launch",
                    "-Source", self.zip, "-SourceSha256", self.zip_sha)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        engine = docs / "WhyNotCut"
        rel = engine / "downloads" / f"release-{self.zip_sha[:8]}"
        self.assertEqual(sha((rel / self.zip.name).read_bytes()), self.zip_sha)
        self.assertTrue((engine / "current").is_file(), out)
        self.assertFalse((self.home / ".whynot-cut" / "downloads").exists())
        self.assertEqual(thesis.read_bytes(), b"my thesis")

    def test_a_wrong_source_sha256_installs_nothing(self):
        r = self.ps(self.lone, "-Home", self.home, "-Yes", "-Source", self.zip, "-SourceSha256", "1" * 64)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 3, out)
        self.assertIn(self.zip.name, out)
        self.assertFalse(list(self.paths.downloads_dir.rglob("*.zip")))
        self.assertFalse(self.paths.current_file.exists())

    def test_without_source_the_placeholder_index_says_h3_in_arabic_too(self):
        r = self.ps(self.lone, "-Home", self.home, "-Yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 2, out)
        self.assertIn(H3_EN, out)
        self.assertIn(H3_AR, out)
        self.assertIn("installer\\install.ps1", out)
        self.assertFalse(self.home.exists())

    def test_plain_irm_iex_says_h3_and_keeps_the_session(self):
        # `irm ... | iex` runs the text in the caller's scope with no parameters at all (a ValidateSet on a parameter
        # breaks exactly this). No -Home is possible here, so the profile variables point into the temp folder too.
        guard = self.tmp / "guard profile"
        env = self.env(WNC_T_SCRIPT=str(self.lone), USERPROFILE=str(guard), HOME=str(guard),
                       WHYNOT_HOME=str(guard / ".whynot-cut"))
        cmd = ("$ErrorActionPreference = 'Continue'; [IO.File]::ReadAllText($env:WNC_T_SCRIPT) | iex; "
               "'after iex: ' + $LASTEXITCODE + ' ' + $ErrorActionPreference")
        r = subprocess.run([find_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=120, stdin=subprocess.DEVNULL, cwd=str(self.tmp))
        out = r.stdout + r.stderr
        self.assertIn(H3_EN, out)
        self.assertIn(H3_AR, out)
        self.assertIn("after iex: 2 Continue", r.stdout)  # the session goes on, its preferences untouched
        for name in (".whynot-cut", ".claude"):  # (PowerShell itself makes AppData\Roaming under a new profile)
            self.assertFalse((guard / name).exists(), name)


@unittest.skipUnless(find_bash(), "bash is not available")
class TestBashFrontEnd(_ShellCase):
    """install.sh with WNC_TEST_PLATFORM=mac-arm64 (on Windows: Git Bash, the core on the test interpreter)."""
    UV_PLAT = "mac-arm64"

    def env(self, **extra) -> dict:
        shim = self.tmp / "shim"
        shim.mkdir(exist_ok=True)
        py3 = shim / "python3"  # the bootstrap's JSON reader and a .py WNC_TEST_UV run on the test interpreter
        py3.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8", newline="\n")
        os.chmod(py3, 0o755)
        # Windows: the core is a Windows python, which cannot start a .sh; the .py stand-in runs on its interpreter
        fake_uv = FIXTURES / ("fake_uv.py" if IS_WIN else "fake_uv.sh")
        env = sandbox_env(WNC_TEST_PLATFORM="mac-arm64", WNC_TEST_UV=str(fake_uv), FAKE_UV_PYTHON=sys.executable,
                          WNC_CLAUDE_CLI=str(FAKE_CLAUDE), FAKE_CLAUDE_LOG=str(self.tmp / "claude.jsonl"),
                          WNC_TEST_ENGINE_LOG=str(self.tmp / "engine.jsonl"))
        env["PATH"] = str(shim) + os.pathsep + env.get("PATH", "")
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def sh(self, *args, env=None, script: bytes = None):
        """bash with stdin = /dev/null, or (script) a REAL pipe carrying the script bytes, as `curl ... | bash` does."""
        cmd = [find_bash(), *[str(a) for a in args]]
        kw = {"input": script} if script is not None else {"stdin": subprocess.DEVNULL}
        r = subprocess.run(cmd, capture_output=True, env=env or self.env(), timeout=600, cwd=str(self.tmp), **kw)
        return subprocess.CompletedProcess(cmd, r.returncode, r.stdout.decode("utf-8", "replace"),
                                           r.stderr.decode("utf-8", "replace"))

    def front(self) -> str:
        return (self.fx.plugin_root / "installer" / "install.sh").as_posix()

    def home_arg(self) -> str:
        return self.home.as_posix()

    def test_install_in_an_arabic_home_touches_nothing_outside(self):
        before = live_snapshot()
        r = self.sh(self.front(), "--home", self.home_arg(), "--yes", "--skip", "model,launch",
                    "--components", self.fx.components_path.as_posix())
        self.assert_installed(r, "mac-arm64")
        self.assertTrue((self.home / "Library" / "Fonts").is_dir())
        self.assertEqual(live_snapshot(), before)
        self.assertLessEqual(set(os.listdir(self.tmp)),
                             {ARABIC_HOME, "zip root", "claude.jsonl", "engine.jsonl", "shim"})

    def test_uv_already_at_the_pinned_version_is_not_downloaded(self):
        uv = self.paths.bin_dir / "uv"
        uv.parent.mkdir(parents=True)
        touch(self.paths.state_file, GENUINE_STATE)  # an earlier run claimed the folder (a bare uv is not ours)
        uv.write_text("#!/bin/sh\necho 'uv 0.13.0 (fixture)'\n", encoding="utf-8", newline="\n")
        os.chmod(uv, 0o755)
        r = self.sh(self.front(), "--home", self.home_arg(), "--yes", "--skip", "model,launch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.uv_hits(), [])
        self.assertFalse(self.uv_archive().exists())
        self.assertTrue(self.paths.current_file.is_file())

    def test_uv_is_found_anywhere_in_its_archive(self):
        data = tgz({"release/deeper/bin/uv": b"#!/bin/sh\necho uv nested\n"})  # not where `member` says
        self.srv.srv.files["/uv/nested.tar.gz"] = data
        comp = json.loads(self.fx.components_path.read_text(encoding="utf-8"))
        comp["uv"]["assets"]["mac-arm64"].update(url=self.srv.base + "/uv/nested.tar.gz", sha256=sha(data),
                                                 bytes=len(data), member="uv-aarch64-apple-darwin/uv")
        self.fx.components_path.write_text(json.dumps(comp, indent=2), encoding="utf-8")
        r = self.sh(self.front(), "--home", self.home_arg(), "--yes", "--skip", "model,launch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.paths.bin_dir / "uv").read_bytes(), b"#!/bin/sh\necho uv nested\n")

    def test_dry_run_leaves_the_home_empty(self):
        self.home.mkdir()
        r = self.sh(self.front(), "--home", self.home_arg(), "--dry-run", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.srv.srv.hits, [])
        for name in ("uv", "python", "preflight", "launch"):
            self.assertIn(f"== {name} ==", r.stdout)

    def test_a_bad_uv_sha256_stops_with_3_and_names_the_file(self):
        self.break_uv_sha()
        r = self.sh(self.front(), "--home", self.home_arg(), "--yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 3, out)
        self.assertIn("uv-aarch64-apple-darwin.tar.gz", out)
        self.assertFalse(self.uv_archive().exists())
        self.assertFalse(self.paths.current_file.exists())
        logs = list(self.paths.logs_dir.glob("install-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn(f"Log: {self.home_arg()}/.whynot-cut/logs/{logs[0].name}", out)

    @unittest.skipUnless(IS_WIN, "Git Bash only")
    def test_git_bash_without_test_platform_says_use_install_ps1(self):
        r = self.sh(self.front(), "--home", self.home_arg(), "--yes", env=self.env(WNC_TEST_PLATFORM=None))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("install.ps1", r.stdout + r.stderr)
        self.assertFalse(self.home.exists())

    def test_piped_script_with_yes_does_not_hang(self):
        zf = self.tmp / "WhyNotCut-3.0.0.zip"
        zsha = release_zip(self.fx, zf)
        r = self.sh("-s", "--", "--home", self.home_arg(), "--yes", "--skip", "model,launch",  # `curl ... | bash`
                    "--source", zf.as_posix(), "--source-sha256", zsha,
                    script=(INSTALLER / "install.sh").read_bytes())
        self.assert_installed(r, "mac-arm64")
        rel = self.paths.downloads_dir / f"release-{zsha[:8]}"
        self.assertTrue((rel / "x" / "whynot-cut-marketplace" / "whynot-cut" / "setup" / "components.json").is_file())

    def test_piped_without_source_says_h3_in_arabic_too(self):
        r = self.sh("-s", "--", "--home", self.home_arg(), "--yes", script=(INSTALLER / "install.sh").read_bytes())
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 2, out)
        self.assertIn(H3_EN, out)
        self.assertIn(H3_AR, out)
        self.assertFalse(self.home.exists())


# --------------------------------------------------------------------------------------------- T7.8 uninstall
UXP_ID = "ai.thewhynot.cut.uxp"
PREMIERE_26_5 = json.dumps([{"app": "premiere", "version": "26.5.0"}])
UNINSTALL_STEP_NAMES = ["plugin", "adobe", "fonts", "marketplace", "engine"]
DEFER_LIST = ".delete-after-exit"
GIT_BASH_KEY = "CLAUDE_CODE_GIT_BASH_PATH"


def shell_function(path: Path, name: str, ps: bool) -> str:
    """One function's text out of a bootstrap, to run it alone against a scratch folder."""
    text = path.read_text(encoding="utf-8")
    pat = (rf"(?ms)^(    function {re.escape(name)}\b.*?^    }}\n)" if ps
           else rf"(?ms)^({re.escape(name)}\(\) \{{.*?^\}}\n)")
    m = re.search(pat, text)
    if m is None:
        raise AssertionError(f"{name} not found in {path.name}")
    return m.group(1)


def tampered_engine(tmp: Path) -> types.SimpleNamespace:
    """An engine home with python/, bin/, models/ and a client folder, plus a folder outside it."""
    root = tmp / ARABIC_HOME / ".whynot-cut"
    ns = types.SimpleNamespace(root=root, outside=tmp / "outside")
    touch(root / "python" / "cpython-3.12.15-x" / "python.exe", b"MZ")
    touch(root / "bin" / "uv.exe", b"MZ")
    ns.model = touch(root / "models" / "large-v3" / "model.bin", b"weights")
    ns.marker = touch(root / "WhyNot Clients" / "Dr X" / ".whynot-client", b"{}")
    ns.footage = touch(root / "WhyNot Clients" / "Dr X" / "raw.mp4", b"precious")
    ns.kept = touch(ns.outside / "keep.txt", b"precious")
    return ns


def assert_only_python_and_bin_went(test: unittest.TestCase, ns: types.SimpleNamespace, out: str) -> None:
    test.assertFalse(os.path.lexists(ns.root / "python"), out)
    test.assertFalse(os.path.lexists(ns.root / "bin"), out)
    for f, data in ((ns.model, b"weights"), (ns.marker, b"{}"), (ns.footage, b"precious"), (ns.kept, b"precious")):
        test.assertEqual(f.read_bytes(), data, out)
    test.assertTrue(ns.root.is_dir(), out)  # listed, but not empty: kept
    test.assertFalse((ns.root / DEFER_LIST).exists(), out)
    test.assertIn("refused", out)


def uninstall_module():
    """Imported inside the tests so this file stays importable while the module is being written."""
    from wnc_installer import uninstall
    return uninstall


def add_adobe_panels(fx: types.SimpleNamespace) -> None:
    """A signed ZXP and a .ccx inside the fixture plugin, pinned in its components.json: the install puts the CEP panel
    in the fake CEP folder and (sandbox) records the UPIA command for the UXP one."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("META-INF/signatures.xml", "<signatures/>")
        z.writestr("index.html", "<html>panel</html>")
    zxp, ccx = buf.getvalue(), b"PK fixture ccx"
    touch(fx.plugin_root / "bridge" / "cep.zxp", zxp)
    touch(fx.plugin_root / "bridge" / "uxp.ccx", ccx)
    comp = json.loads(fx.components_path.read_text(encoding="utf-8"))
    comp["bridge"]["cep"].update(zxp="bridge/cep.zxp", sha256=sha(zxp))
    comp["bridge"]["uxp"].update(ccx="bridge/uxp.ccx", sha256=sha(ccx), version="1.0.0", id=UXP_ID)
    fx.components_path.write_text(json.dumps(comp, indent=2), encoding="utf-8")
    fx.components = comp


def tree(root: Path) -> list:
    """Every path under root (relative, sorted), with the bytes of each file: proof that nothing changed."""
    out = []
    for p in sorted(root.rglob("*")):
        out.append((str(p.relative_to(root)), p.read_bytes() if p.is_file() else None))
    return out


class _InstalledHome(unittest.TestCase):
    """A sandboxed install (the core, fake uv / claude / engine, a signed CEP panel, the UXP command, two fonts) in a
    home with a space and Arabic letters whose settings.json already holds the editor's own keys."""
    EDITOR_SETTINGS = {"theme": "dark", "enabledPlugins": {"x@y": True}}

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.home = self.tmp / ARABIC_HOME
        self.srv = Served(self, {})
        self.fx = make_fixture_plugin(self.tmp / "zip root", self.srv.base)
        self.srv.srv.files.update(self.fx.served)
        add_adobe_panels(self.fx)
        self.paths = base.Paths.from_env(str(self.home), env={})
        self.claude_log = self.tmp / "claude.jsonl"
        self.env = sandbox_env(WNC_TEST_UV=str(FAKE_UV), WNC_CLAUDE_CLI=str(FAKE_CLAUDE),
                               FAKE_CLAUDE_LOG=str(self.claude_log), WNC_TEST_ENGINE_LOG=str(self.tmp / "engine.jsonl"),
                               WNC_TEST_ADOBE_HOSTS=PREMIERE_26_5)
        touch(self.paths.settings_file, json.dumps(self.EDITOR_SETTINGS, indent=2).encode("utf-8"))

    def core(self, *args, env=None):
        core = self.fx.plugin_root / "installer" / "core" / "wnc_install.py"
        return subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(core), *args, "--home", str(self.home),
                               "--yes"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=env or self.env, timeout=600, stdin=subprocess.DEVNULL)

    def install(self) -> dict:
        r = self.core("install", "--skip", "model")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(self.paths.state_file.read_text(encoding="utf-8"))

    def claude_calls(self) -> list:
        if not self.claude_log.is_file():
            return []
        return [json.loads(x)["argv"] for x in self.claude_log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def bootstrap_leftovers(self) -> tuple:
        """What the bootstrap puts in the engine home before the core runs: python-build-standalone and uv."""
        pbs = self.paths.python_dir / "cpython-3.12.15-windows-x86_64-none"
        touch(pbs / "python.exe", b"MZ python")
        touch(self.paths.bin_dir / "uv.exe", b"MZ uv")
        return pbs, self.paths.bin_dir

    def managed_bash(self) -> Path:
        return self.paths.localappdata / "WhyNotCut" / "git" / "bin" / "bash.exe"

    def deferred(self) -> list:
        return (self.paths.whynot / DEFER_LIST).read_text(encoding="utf-8").splitlines()


class TestUninstall(_InstalledHome):
    def test_default_uninstall_removes_ours_and_keeps_the_engine(self):
        st = self.install()
        cep = Path(st["adobe"]["cep"]["path"])
        fonts = [Path(p) for p in st["fonts"]["installed"]]
        self.assertTrue(cep.is_dir())
        self.assertEqual(len(fonts), 2)
        self.assertTrue(all(f.is_file() for f in fonts))
        before = self.paths.settings_file.read_bytes()
        n_calls = len(self.claude_calls())
        model = touch(self.paths.models_dir / "large-v3" / "model.bin", b"weights")
        prefs = touch(self.paths.claude_dir / "whynot-cut.local.md", b"---\nlanguage: ar\n---\n")
        r = self.core("uninstall")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        # settings.json: only our keys gone, the editor's intact, the original bytes backed up
        settings = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        env = settings.pop("env", None)
        self.assertEqual(settings, self.EDITOR_SETTINGS)
        if IS_WIN:  # the Git Bash entry stays while the managed Git folder stays (it goes with --remove-engine)
            self.assertEqual(env, {GIT_BASH_KEY: str(self.managed_bash())})
        else:
            self.assertIsNone(env)
        self.assertEqual(st["adobe"]["uxp"]["id"], UXP_ID)  # the install records the id uninstall uses
        backups = [p.read_bytes() for p in self.paths.claude_dir.glob("settings.json.whynot-backup-*")]
        self.assertIn(before, backups)
        argv = self.claude_calls()[n_calls:]
        self.assertIn(["plugin", "uninstall", PID, "--scope", "user"], argv)
        self.assertIn(["plugin", "marketplace", "remove", "thewhynot-ai"], argv)
        # Adobe panel, fonts (files + registry values), the marketplace folder
        self.assertFalse(cep.exists())
        self.assertTrue(cep.parent.is_dir())
        self.assertIn(UXP_ID, out)  # the UPIA remove command (recorded only in a sandbox)
        self.assertFalse(any(f.exists() for f in fonts))
        if IS_WIN:
            self.assertEqual(json.loads((self.paths.sandbox_dir / "registry-fonts.json").read_text("utf-8")), {})
            self.assertTrue((self.paths.localappdata / "WhyNotCut" / "git").is_dir())  # only with --remove-engine
        self.assertFalse(self.paths.marketplace_dir.exists())
        # the engine home stays: runtimes, current, models, the uninstall log
        self.assertTrue(self.paths.runtimes_dir.is_dir())
        self.assertTrue(self.paths.current_file.is_file())
        self.assertEqual(model.read_bytes(), b"weights")
        self.assertTrue(list(self.paths.logs_dir.glob("uninstall-*.log")))
        self.assertTrue(prefs.is_file())
        self.assertIn("whynot-cut.local.md", r.stdout)  # kept and reported
        for name in UNINSTALL_STEP_NAMES:
            self.assertIn(f"== {name} ==", r.stdout)
        st2 = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        for key in ("adobe", "fonts", "claude"):
            self.assertNotIn(key, st2)
        self.assertIn("uninstalled", st2)
        self.assertFalse((self.paths.whynot / DEFER_LIST).exists())
        # a second uninstall finds nothing more to do and still exits 0
        r2 = self.core("uninstall")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_remove_engine_keeps_models_client_folders_and_link_targets(self):
        self.install()
        clients = self.paths.whynot / "WhyNot Clients"
        touch(clients / "Dr X" / ".whynot-client", b"{}")
        footage = touch(clients / "Dr X" / "raw" / "C0239.mp4", b"precious footage")
        touch(self.paths.claude_dir / "whynot-cut.local.md",
              f"---\nclients_root: {clients}\nlanguage: ar\n---\n".encode("utf-8"))
        model = touch(self.paths.models_dir / "large-v3" / "model.bin", b"weights")
        outside = self.tmp / "client elsewhere"
        kept = touch(outside / "keep.mp4", b"precious")
        linked = make_dir_link(self.paths.whynot / "linked clients", outside)
        pbs, bin_dir = self.bootstrap_leftovers()
        r = self.core("uninstall", "--remove-engine")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        left = set(os.listdir(self.paths.whynot))
        # fix round 1: only WhyNot Cut's own entries go; "WhyNot Clients" and the link are not ours: kept and listed
        self.assertEqual(left, {"models", "WhyNot Clients", "python", "bin", DEFER_LIST}
                         | ({"linked clients"} if linked else set()), out)
        self.assertEqual(model.read_bytes(), b"weights")
        self.assertEqual(footage.read_bytes(), b"precious footage")
        self.assertTrue((clients / "Dr X" / ".whynot-client").is_file())
        self.assertEqual(kept.read_bytes(), b"precious")  # never followed: its target is untouched
        if linked:
            self.assertIn("linked clients", out)
        # python/ and bin/ are left to the bootstrap (Windows locks the running python.exe): listed, not deleted
        self.assertEqual(self.deferred(), [str(self.paths.python_dir), str(bin_dir)])
        self.assertTrue((pbs / "python.exe").is_file())
        if IS_WIN:
            self.assertFalse((self.paths.localappdata / "WhyNotCut").exists())
        self.assertIn("WhyNot Clients", out)  # reported as kept
        settings = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        self.assertNotIn("env", settings)  # the Git Bash entry went together with the managed Git folder
        self.assertEqual(settings, self.EDITOR_SETTINGS)

    def test_remove_models_too(self):
        self.install()
        touch(self.paths.models_dir / "large-v3" / "model.bin", b"weights")
        self.bootstrap_leftovers()
        r = self.core("uninstall", "--remove-engine", "--remove-models")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(set(os.listdir(self.paths.whynot)), {"python", "bin", DEFER_LIST}, out)
        # nothing else is left, so the engine home itself goes too, once the bootstrap removed python/ and bin/
        self.assertEqual(self.deferred(), [str(self.paths.python_dir), str(self.paths.bin_dir),
                                           str(self.paths.whynot)])

    def test_a_running_adobe_host_keeps_the_panel_and_the_rest_goes(self):
        st = self.install()
        cep = Path(st["adobe"]["cep"]["path"])
        env = dict(self.env, WNC_TEST_HOSTS_RUNNING="Adobe Premiere Pro.exe")
        r = self.core("uninstall", env=env)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertTrue((cep / "index.html").is_file())
        self.assertIn("[!!] adobe", r.stdout)
        self.assertIn("Adobe Premiere Pro.exe", r.stdout)
        st2 = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(st2["adobe"]["cep"]["path"], str(cep))  # still recorded: the next uninstall removes it
        self.assertNotIn("fonts", st2)
        r2 = self.core("uninstall")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertFalse(cep.exists())

    def test_a_running_host_with_remove_engine_keeps_what_is_left_to_retry(self):
        st = self.install()
        cep = Path(st["adobe"]["cep"]["path"])
        touch(self.paths.models_dir / "large-v3" / "model.bin", b"weights")
        env = dict(self.env, WNC_TEST_HOSTS_RUNNING="Adobe Premiere Pro.exe")
        r = self.core("uninstall", "--remove-engine", env=env)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertTrue((cep / "index.html").is_file())
        st2 = json.loads(self.paths.state_file.read_text(encoding="utf-8"))  # a small state.json is kept
        self.assertEqual(st2["adobe"]["cep"]["path"], str(cep))
        self.assertNotIn("fonts", st2)
        self.assertFalse(self.paths.runtimes_dir.exists())
        self.assertIn("state.json", r.stdout)
        # the host is closed: the next uninstall finds the panel and removes it, then the rest of the engine home
        r2 = self.core("uninstall", "--remove-engine")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertFalse(cep.exists())
        self.assertFalse(self.paths.state_file.exists())
        self.assertEqual(os.listdir(self.paths.whynot), ["models"])

    def test_unknown_entries_of_the_engine_home_survive_remove_engine(self):
        # fix round 1 (CRITICAL): --remove-engine deletes only what WhyNot Cut puts there, in ~/.whynot-cut too
        self.install()
        mine = touch(self.paths.whynot / "my notes.txt", b"mine")
        project = touch(self.paths.whynot / "Old Project" / "edit.prproj", b"mine")
        self.bootstrap_leftovers()
        r = self.core("uninstall", "--remove-engine", "--remove-models")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual((mine.read_bytes(), project.read_bytes()), (b"mine", b"mine"))
        self.assertEqual(set(os.listdir(self.paths.whynot)), {"my notes.txt", "Old Project", "python", "bin",
                                                              DEFER_LIST}, out)
        self.assertIn("my notes.txt", r.stdout)  # listed as kept
        self.assertIn("Old Project", r.stdout)
        # the engine home is not empty: it is not listed for the bootstrap's final delete
        self.assertEqual(self.deferred(), [str(self.paths.python_dir), str(self.paths.bin_dir)])

    def test_a_chosen_documents_folder_installs_into_its_own_subfolder(self):
        # fix round 1 (CRITICAL): the reviewer's case - Documents with the editor's files as the engine home
        docs = self.home / "Documents"
        thesis = touch(docs / "thesis.docx", b"my thesis")
        taxes = touch(docs / "Taxes" / "2025.pdf", b"my taxes")
        r = self.core("install", "--skip", "model", "--engine-home", str(docs), "--engine-home-chosen")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        engine = docs / "WhyNotCut"
        self.assertTrue((engine / "current").is_file(), out)
        self.assertTrue((engine / "state.json").is_file(), out)
        self.assertEqual(sorted(os.listdir(docs)), ["Taxes", "WhyNotCut", "thesis.docx"])
        p = json.loads(self.paths.options_file.read_text(encoding="utf-8"))
        self.assertEqual(norm(p["engine_home"]), norm(engine))
        # uninstall --remove-engine (found through the pointer) leaves every file of the editor where it was
        touch(engine / "python" / "cpython-3.12.15-x" / "python.exe", b"MZ")
        r = self.core("uninstall", "--remove-engine", "--remove-models")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((thesis.read_bytes(), taxes.read_bytes()), (b"my thesis", b"my taxes"))
        self.assertEqual(sorted(os.listdir(engine)), sorted(["python", DEFER_LIST]))  # the bootstrap's, next

    def install_into(self, folder: Path) -> Path:
        r = self.core("install", "--skip", "model", "--engine-home", str(folder), "--engine-home-chosen")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return Path(json.loads(self.paths.options_file.read_text(encoding="utf-8"))["engine_home"])

    def uninstall_all(self, engine: Path) -> None:
        touch(engine / "python" / "cpython-3.12.15-x" / "python.exe", b"MZ")
        r = self.core("uninstall", "--remove-engine", "--remove-models")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_folder_of_engine_named_user_folders_gets_its_own_subfolder(self):
        # fix round 2, the reviewer's repro 1: names like fonts / downloads / logs are the editor's too
        work = self.home / "Work"
        files = {touch(work / "fonts" / "MyBrand.ttf", b"user font"): b"user font",
                 touch(work / "downloads" / "raw-footage.mov", b"user video"): b"user video",
                 touch(work / "logs" / "shoot-notes.txt", b"user notes"): b"user notes"}
        engine = self.install_into(work)
        self.assertEqual(norm(engine), norm(work / "WhyNotCut"))
        self.uninstall_all(engine)
        for f, data in files.items():
            self.assertEqual(f.read_bytes(), data, f)
        self.assertEqual(sorted(os.listdir(work)), ["WhyNotCut", "downloads", "fonts", "logs"])

    def test_a_users_state_json_is_not_an_engine_home(self):
        # fix round 2, the reviewer's repro 2: a state.json that WhyNot Cut did not write
        proj = self.home / "Proj"
        state = touch(proj / "state.json", b'{"my": "game save"}')
        log = touch(proj / "logs" / "app.log", b"user log")
        notes = touch(proj / "notes.txt", b"notes")
        engine = self.install_into(proj)
        self.assertEqual(norm(engine), norm(proj / "WhyNotCut"))
        self.assertEqual(state.read_bytes(), b'{"my": "game save"}')  # never overwritten
        self.uninstall_all(engine)
        self.assertEqual((state.read_bytes(), log.read_bytes(), notes.read_bytes()),
                         (b'{"my": "game save"}', b"user log", b"notes"))

    def test_a_2x_home_is_upgraded_in_place(self):
        # fix round 3: the core uses a resolved home (default or pointer-saved) directly, like both shells
        for engine in (self.home / ".whynot-cut", self.home / "Old Engine"):
            with self.subTest(str(engine)):
                model = make_2x_home(self.home, engine)
                r = self.core("install", "--skip", "model")
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 0, out)
                assert_2x_home_upgraded_in_place(self, self.home, engine, model, out)
        # while an explicitly chosen folder with something in it still gets its own subfolder
        chosen = self.home / "Chosen"
        touch(chosen / "notes.txt", b"mine")
        self.assertEqual(norm(self.install_into(chosen)), norm(chosen / "WhyNotCut"))

    def test_a_genuine_engine_home_is_used_directly_on_a_reinstall(self):
        first = self.install_into(self.home / "Engine Here")
        self.assertEqual(norm(first), norm(self.home / "Engine Here"))  # an empty / new folder: as chosen
        again = self.install_into(self.home / "Engine Here")  # it holds our state.json, logs ... now
        self.assertEqual(norm(again), norm(first))

    def test_unreadable_settings_runs_no_cli_and_stays_byte_identical(self):
        self.install()
        bad = b'{"theme": "dark",, "enabledPlugins": {"whynot-cut@thewhynot-ai": true}}'
        self.paths.settings_file.write_bytes(bad)
        n_calls = len(self.claude_calls())
        r = self.core("uninstall")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(self.paths.settings_file.read_bytes(), bad)
        self.assertEqual(self.claude_calls()[n_calls:], [])
        self.assertIn("[!!] plugin", r.stdout)
        self.assertIn("extraKnownMarketplaces", r.stdout)  # what to remove by hand
        self.assertIn(PID, r.stdout)


class TestUninstallSteps(unittest.TestCase):
    """The steps one by one, in-process, against hand-made state."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.un = uninstall_module()
        os.environ.pop("WNC_TEST_HOSTS_RUNNING", None)

    def ctx(self, plat="win-x64", **args):
        args.setdefault("remove_engine", False)
        args.setdefault("remove_models", False)
        return make_ctx(self.tmp / ARABIC_HOME, {"schema": 1}, SK, plat, **args)

    def test_registered_in_order(self):
        self.assertEqual([n for n, _f, _d in cli.UNINSTALL_STEPS], UNINSTALL_STEP_NAMES)
        self.assertTrue(all(d == () for _n, _f, d in cli.UNINSTALL_STEPS))

    def test_a_recorded_cep_path_outside_the_cep_folder_is_not_deleted(self):
        ctx = self.ctx()
        elsewhere = self.tmp / "elsewhere" / "ai.thewhynot.cut.bridge"
        touch(elsewhere / "index.html", b"x")
        ctx.state.data["adobe"] = {"cep": {"path": str(elsewhere), "signed": True}}
        r = self.un.step_adobe(ctx)
        self.assertNotEqual(r.status, "red", r.detail)
        self.assertTrue((elsewhere / "index.html").is_file())

    def test_fonts_only_recorded_files_inside_the_font_dir_and_their_own_values(self):
        fx = fonts_module()
        ctx = self.ctx()
        fdir = fx.user_font_dir(ctx.paths, "win-x64")
        ours = touch(fdir / "A.ttf", b"a")
        theirs = touch(fdir / "Theirs.ttf", b"t")
        outside = touch(self.tmp / "other" / "B.ttf", b"b")
        reg = fx.FontRegistry.for_paths(ctx.paths)
        reg.set("A (TrueType)", str(ours))
        reg.set("C (TrueType)", str(self.tmp / "someone" / "C.ttf"))  # recorded name, but now someone else's value
        reg.set("Theirs (TrueType)", str(theirs))
        ctx.state.data["fonts"] = {"installed": [str(ours), str(outside)],
                                   "registry": ["A (TrueType)", "C (TrueType)"]}
        r = self.un.step_fonts(ctx)
        self.assertNotEqual(r.status, "red", r.detail)
        self.assertFalse(ours.exists())
        self.assertTrue(outside.is_file())
        self.assertTrue(theirs.is_file())
        self.assertEqual(sorted(reg.names()), ["C (TrueType)", "Theirs (TrueType)"])

    def test_remove_models_alone_keeps_the_rest_of_the_engine(self):
        ctx = self.ctx(remove_models=True)
        touch(ctx.paths.state_file, GENUINE_STATE)
        touch(ctx.paths.models_dir / "large-v3" / "model.bin", b"w")
        rt = touch(ctx.paths.runtimes_dir / "r-1" / "pyvenv.cfg", b"x")
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertFalse(ctx.paths.models_dir.exists())
        self.assertTrue(rt.is_file())

    def test_remove_engine_keeps_the_motion_library_even_with_remove_models(self):
        ctx = self.ctx(remove_engine=True, remove_models=True)
        touch(ctx.paths.state_file, GENUINE_STATE)
        pack = touch(ctx.paths.whynot / "library" / "motion" / "licensed-pack" / "hand.png", b"paid illustration")
        touch(ctx.paths.models_dir / "large-v3" / "model.bin", b"w")
        touch(ctx.paths.runtimes_dir / "r-1" / "pyvenv.cfg", b"x")
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(pack.read_bytes(), b"paid illustration")
        self.assertIn("library", r.detail)  # reported as kept
        self.assertFalse(ctx.paths.models_dir.exists())
        self.assertFalse(ctx.paths.runtimes_dir.exists())
        self.assertEqual(sorted(os.listdir(ctx.paths.whynot)), ["library"])

    def test_locked_files_during_a_model_download_name_the_download(self):
        ctx = self.ctx(remove_engine=True)
        touch(ctx.paths.state_file, GENUINE_STATE)
        touch(ctx.paths.runtimes_dir / "r-1" / "pyvenv.cfg", b"x")
        mlog = ctx.paths.logs_dir / "model-download-20261012-100000.log"
        ctx.state.data["models"] = {"model": "large-v3", "pid": os.getpid(), "log": str(mlog)}  # a live pid
        real = base.safe_rmtree

        def locked(p, *a, **kw):
            if Path(p).name == "runtimes":
                raise PermissionError(13, "The process cannot access the file", str(p))
            return real(p, *a, **kw)
        with mock.patch.object(base, "safe_rmtree", side_effect=locked):
            r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        said = r.detail + " " + (r.needs_you or "")
        self.assertIn("model download", said)
        self.assertIn(str(mlog), said)
        # a download that is over is not blamed
        ctx = self.ctx(remove_engine=True)
        touch(ctx.paths.state_file, GENUINE_STATE)
        touch(ctx.paths.runtimes_dir / "r-1" / "pyvenv.cfg", b"x")
        gone = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL)
        gone.wait(30)
        ctx.state.data["models"] = {"model": "large-v3", "pid": gone.pid, "log": str(mlog)}
        with mock.patch.object(base, "safe_rmtree", side_effect=locked):
            r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "amber", r.detail)
        self.assertNotIn("model download", r.detail + " " + (r.needs_you or ""))

    def chosen_home(self, pointer_clients_root: str = "") -> types.SimpleNamespace:
        """A sandbox whose pointer and settings.json name a chosen engine home inside it, with an install in it and a
        client folder inside the engine home."""
        home = self.tmp / ARABIC_HOME
        ns = types.SimpleNamespace(home=home, engine=home / "WhyNot Engine محرك",
                                   pointer=home / ".whynot-cut" / "plugin-options.json",
                                   settings=home / ".claude" / "settings.json")
        EngineHomeCases.pointer(home, {"clients_root": pointer_clients_root, "engine_home": str(ns.engine),
                                       "updated": "x"})
        EngineHomeCases.settings(home, {PID: {"options": {"engine_home": str(ns.engine), "clients_root": "C"}},
                                        "x@y": {"options": {}}})
        touch(ns.engine / "state.json", GENUINE_STATE)
        touch(ns.engine / "runtimes" / "r-1" / "pyvenv.cfg", b"x")
        ns.model = touch(ns.engine / "models" / "large-v3" / "model.bin", b"weights")
        ns.client = touch(ns.engine / "WhyNot Clients" / "Dr X" / ".whynot-client", b"{}")
        return ns

    def test_remove_engine_of_a_chosen_home_forgets_it(self):
        ns = self.chosen_home()
        ctx = self.ctx(remove_engine=True)
        self.assertEqual(norm(ctx.paths.whynot), norm(ns.engine))  # found through the sandbox's own pointer
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(sorted(os.listdir(ns.engine)), ["WhyNot Clients", "models"])  # never a client folder
        self.assertEqual((ns.client.read_bytes(), ns.model.read_bytes()), (b"{}", b"weights"))
        # the pointer held nothing else: it goes, and ~/.whynot-cut with it (it held only the pointer)
        self.assertFalse(ns.pointer.exists())
        self.assertFalse((ns.home / ".whynot-cut").exists())
        s = json.loads(ns.settings.read_text(encoding="utf-8"))
        self.assertEqual(s["pluginConfigs"][PID], {"options": {"clients_root": "C"}})  # only engine_home went
        self.assertEqual(s["pluginConfigs"]["x@y"], {"options": {}})
        self.assertTrue(list(ns.settings.parent.glob("settings.json.whynot-backup-*")))
        self.assertIn("-EngineHome", r.detail)  # how to use the kept models again
        self.assertEqual(norm(base.Paths.from_env(str(ns.home), env={}).whynot), norm(ns.home / ".whynot-cut"))

    def test_a_pointer_that_still_names_a_clients_folder_keeps_it(self):
        ns = self.chosen_home(pointer_clients_root="D:/عملاء")
        r = self.un.step_engine(self.ctx(remove_engine=True))
        self.assertEqual(r.status, "ok", r.detail)
        p = json.loads(ns.pointer.read_text(encoding="utf-8"))
        self.assertEqual((list(p), p["engine_home"], p["clients_root"]), (POINTER_KEYS, "", "D:/عملاء"))

    def test_a_failed_delete_keeps_the_pointer_and_the_option(self):
        ns = self.chosen_home()
        before = (ns.pointer.read_bytes(), ns.settings.read_bytes())
        real = base.safe_rmtree

        def locked(p, *a, **kw):
            if Path(p).name == "runtimes":
                raise PermissionError(13, "The process cannot access the file", str(p))
            return real(p, *a, **kw)
        with mock.patch.object(base, "safe_rmtree", side_effect=locked):
            r = self.un.step_engine(self.ctx(remove_engine=True))
        self.assertEqual(r.status, "amber", r.detail)
        self.assertEqual((ns.pointer.read_bytes(), ns.settings.read_bytes()), before)  # the next uninstall finds it

    def test_without_remove_engine_the_pointer_stays(self):
        ns = self.chosen_home()
        before = (ns.pointer.read_bytes(), ns.settings.read_bytes())
        r = self.un.step_engine(self.ctx())
        self.assertEqual(r.status, "skipped", r.detail)
        self.assertEqual((ns.pointer.read_bytes(), ns.settings.read_bytes()), before)

    def test_an_engine_home_that_is_the_user_home_is_refused(self):
        h = self.tmp / "profile"
        touch(h / "Documents" / "thesis.docx", b"mine")
        touch(h / "state.json", GENUINE_STATE)
        paths = base.Paths(home=h, whynot=h, claude_dir=h / ".claude", appdata=h / "AppData" / "Roaming",
                           localappdata=h / "AppData" / "Local", sandbox=True)
        ns = argparse.Namespace(skip=[], dry_run=False, yes=True, remove_engine=True, remove_models=True)
        ctx = base.Ctx(paths=paths, log=Quiet(None), components={"schema": 1}, state=base.State(paths), plugin_root=SK,
                       platform="win-x64", args=ns)
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "red", r.detail)
        self.assertEqual((h / "Documents" / "thesis.docx").read_bytes(), b"mine")

    def test_a_folder_without_a_strong_engine_mark_is_refused(self):
        ctx = self.ctx(remove_engine=True, remove_models=True)
        for name in ("bin", "python", "models", "runtimes", "ffmpeg", "marketplace"):  # common names only
            touch(ctx.paths.whynot / name / "x.bin", b"x")
        before = tree(ctx.paths.whynot)
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "red", r.detail)
        self.assertEqual(tree(ctx.paths.whynot), before)
        # fix round 2: names can be anyone's - only WhyNot Cut's own CONTENT makes an engine home
        w = ctx.paths.whynot
        for fake in ((w / "bin" / "uv.exe", b"MZ"), (w / "state.json", b'{"my": "game save"}'),
                     (w / "state.json", b'{"schema": 1}'), (w / "state.json", b'{"schema": true, "plugin": "x"}'),
                     (w / "current", b"r-123\n"), (w / "runtimes" / "r-123" / "WHYNOT_RUNTIME", b'{"id": "r-999"}'),
                     (w / "current", b"../evil\n")):
            touch(*fake)
            with self.subTest(str(fake)):
                self.assertFalse(base.is_engine_home(w))
                self.assertIsNotNone(self.un.engine_home_problem(ctx.paths))
        touch(w / "current", b"r-123\n")
        touch(w / "runtimes" / "r-123" / "WHYNOT_RUNTIME", b'{"id": "r-123", "python": "3.12.15"}')  # a builder's stamp
        self.assertTrue(base.is_engine_home(w))
        self.assertIsNone(self.un.engine_home_problem(ctx.paths))
        (w / "current").unlink()
        touch(w / "state.json", GENUINE_STATE)  # what the installer's State writes
        self.assertIsNone(self.un.engine_home_problem(ctx.paths))

    def test_only_exact_names_are_ours(self):
        # fix round 2: the editor's `Bin` / `Models` (case-insensitive disks) are never deleted nor deferred
        ctx = self.ctx(remove_engine=True)
        touch(ctx.paths.state_file, GENUINE_STATE)
        theirs = touch(ctx.paths.whynot / "Bin" / "edit.prproj", b"mine")
        models = touch(ctx.paths.whynot / "Models" / "rig.blend", b"mine")
        tmp_leftover = touch(ctx.paths.whynot / "..delete-after-exit.123.tmp", b"x")
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual((theirs.read_bytes(), models.read_bytes()), (b"mine", b"mine"))
        self.assertFalse(tmp_leftover.exists())  # ours: an atomic-write leftover of the deferred list
        self.assertFalse((ctx.paths.whynot / DEFER_LIST).exists())  # `Bin` is not bin/: nothing for the bootstrap
        self.assertIn("Bin", r.detail)
        self.assertTrue(base.is_engine_entry("..delete-after-exit.123.tmp"))
        self.assertFalse(base.is_engine_entry("Bin"))
        ctx = self.ctx(remove_models=True)  # --remove-models alone: `Models` is not models/
        touch(ctx.paths.state_file, GENUINE_STATE)
        r = self.un.step_engine(ctx)
        self.assertEqual(r.status, "skipped", r.detail)  # "no Whisper models to delete"
        self.assertEqual(models.read_bytes(), b"mine", r.detail)

    def test_uxp_remove_uses_the_id_recorded_at_install(self):
        ctx = self.ctx()
        ctx.components = {"schema": 1, "bridge": {"uxp": {"id": "ai.thewhynot.cut.newer"}}}
        ctx.state.data["adobe"] = {"uxp": {"id": "ai.thewhynot.cut.recorded", "ran": False}}
        r = self.un.step_adobe(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn("/remove ai.thewhynot.cut.recorded", r.detail)
        self.assertNotIn("newer", r.detail)
        ctx.state.data["adobe"] = {"uxp": {"ran": False}}  # an install from before the id was recorded
        self.assertIn("/remove ai.thewhynot.cut.newer", self.un.step_adobe(ctx).detail)

    def test_dry_run_changes_nothing_and_runs_nothing(self):
        ctx = self.ctx(dry_run=True, remove_engine=True, remove_models=True)
        ctx.log = Quiet(None, dry_run=True)
        touch(ctx.paths.settings_file, json.dumps({"enabledPlugins": {PID: True}}).encode("utf-8"))
        touch(ctx.paths.runtimes_dir / "r-1" / "pyvenv.cfg", b"x")
        touch(ctx.paths.state_file, GENUINE_STATE)
        touch(ctx.paths.marketplace_dir / ".claude-plugin" / "marketplace.json", b"{}")
        touch(ctx.paths.models_dir / "m.bin", b"w")
        before = tree(ctx.paths.home)
        with mock.patch.object(base, "run_cmd", side_effect=AssertionError("no process in a dry run")):
            results = self.un.uninstall(ctx, remove_engine=True, remove_models=True)
        self.assertEqual([r.name for r in results], UNINSTALL_STEP_NAMES)
        self.assertEqual(tree(ctx.paths.home), before)


def fonts_module():
    from wnc_installer import fonts
    return fonts


@unittest.skipUnless(find_powershell(), "Windows PowerShell is not available")
class TestPowerShellUninstall(TestPowerShellFrontEnd):
    """install.ps1 -Uninstall after an install.ps1 install: no download, the deferred python/ and bin/ removed after the
    core exits (a junction inside them removed as a link), and the engine home gone."""
    test_install_in_an_arabic_home_touches_nothing_outside = None
    test_dry_run_leaves_the_home_empty = None
    test_dry_run_without_uv_names_the_remaining_steps = None
    test_a_bad_uv_sha256_stops_with_3_and_names_the_file = None
    test_paths_ending_in_a_backslash_reach_the_core_intact = None
    test_the_bootstraps_quoting_guard_doubles_trailing_backslashes = None
    test_uv_already_at_the_pinned_version_is_not_downloaded = None

    def run_functions(self, names: list, call: str, **env):
        boot = INSTALLER / "core" / "bootstrap.ps1"
        body = ("$S = @{ Utf8 = (New-Object System.Text.UTF8Encoding $false) }\n"
                + "".join(shell_function(boot, n, True) for n in names) + call + "\n")
        script = self.tmp / "functions.ps1"
        script.write_text(body, encoding="utf-8-sig")
        return self.ps(script, env=self.env(**env))

    def test_a_tampered_list_deletes_only_python_and_bin(self):
        ns = tampered_engine(self.tmp)
        root = str(ns.root)
        lines = [root + "\\\\", root + "\\models", root + "\\python\\..\\WhyNot Clients",
                 root + "\\python\\..\\..\\..\\outside", str(ns.outside), root + "\\bad|name", "",
                 root + "/python/", root + "\\\\bin"]
        (ns.root / DEFER_LIST).write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = self.run_functions(["Test-WncReparse", "Invoke-WncDeleteTree", "Invoke-WncDeferredDelete"],
                               "Invoke-WncDeferredDelete $env:WNC_T_ENGINE", WNC_T_ENGINE=root)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        assert_only_python_and_bin_went(self, ns, out)
        self.assertEqual(out.count("refused"), 5, out)  # models, the two `..` paths, outside, the illegal name

    def test_the_newest_engine_python_is_chosen_by_version_number(self):
        d = self.tmp / "py"
        for v in ("3.12.9", "3.12.15", "3.11.20"):
            (d / f"cpython-{v}-windows-x86_64-none").mkdir(parents=True)
        r = self.run_functions(["Get-WncPythonDirNewestFirst"], "(Get-WncPythonDirNewestFirst -Dirs @(Get-ChildItem -LiteralPath "
                               "$env:WNC_T_DIR -Directory) | ForEach-Object { $_.Name }) -join ','", WNC_T_DIR=str(d))
        self.assertEqual(r.stdout.strip().splitlines()[-1],
                         "cpython-3.12.15-windows-x86_64-none,cpython-3.12.9-windows-x86_64-none,"
                         "cpython-3.11.20-windows-x86_64-none", r.stdout + r.stderr)

    def test_dry_run_uninstall_without_python_names_the_uninstall_steps(self):
        self.home.mkdir()
        r = self.ps(self.front(), "-Home", self.home, "-Uninstall", "-RemoveEngine", "-DryRun", "-Yes",
                    env=self.env(WNC_TEST_UV=None))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(", ".join(UNINSTALL_STEP_NAMES), r.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.srv.srv.hits, [])

    def test_uninstall_remove_engine_after_an_install(self):
        r = self.ps(self.front(), "-Home", self.home, "-Yes", "-Skip", "model,launch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hits = len(self.srv.srv.hits)
        pbs = self.paths.python_dir / "cpython-3.12.15-windows-x86_64-none"
        touch(pbs / "python.exe", b"MZ python")
        outside = self.tmp / "outside"
        kept = touch(outside / "keep.txt", b"precious")
        linked = make_dir_link(pbs / "Lib", outside)
        before = live_snapshot()
        r = self.ps(self.front(), "-Home", self.home, "-Uninstall", "-RemoveEngine", "-Yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(len(self.srv.srv.hits), hits, self.srv.srv.hits[hits:])  # no uv / Python download
        self.assertTrue(linked)  # mklink /J needs no admin rights
        self.assertEqual(kept.read_bytes(), b"precious")  # junction python/.../Lib -> outside: removed as a link
        self.assertIn("uv and Python are not downloaded", r.stdout)
        for p in (self.paths.python_dir, self.paths.bin_dir, self.paths.whynot):  # by the bootstrap, after the core
            self.assertIn(f"deleted {p}", r.stdout)
        # (the bootstrap waits until the name is gone before it says "deleted"; under a loaded full run an antivirus
        # or indexer holding the folder kept it listed for a moment once: give Windows the same short grace here)
        for _ in range(50):
            if not os.path.lexists(self.paths.whynot):
                break
            time.sleep(0.1)
        self.assertFalse(self.paths.whynot.exists(), sorted(os.listdir(self.paths.whynot))
                         if self.paths.whynot.exists() else out)
        settings = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        self.assertNotIn("thewhynot-ai", settings.get("extraKnownMarketplaces", {}))
        self.assertEqual(live_snapshot(), before)


@unittest.skipUnless(find_bash(), "bash is not available")
class TestBashUninstall(TestBashFrontEnd):
    """install.sh --uninstall after an install.sh install, run on the engine's own Python (found by its path, without
    uv): no download, python/ and bin/ removed after the core exits, models kept."""
    test_install_in_an_arabic_home_touches_nothing_outside = None
    test_uv_already_at_the_pinned_version_is_not_downloaded = None
    test_uv_is_found_anywhere_in_its_archive = None
    test_dry_run_leaves_the_home_empty = None
    test_a_bad_uv_sha256_stops_with_3_and_names_the_file = None
    test_git_bash_without_test_platform_says_use_install_ps1 = None
    test_piped_script_with_yes_does_not_hang = None
    test_piped_without_source_says_h3_in_arabic_too = None

    def test_a_tampered_list_deletes_only_python_and_bin(self):
        ns = tampered_engine(self.tmp)
        root = ns.root.as_posix()
        lines = [root + "//", root + "/models", root + "/python/../WhyNot Clients", root + "/python/../../../outside",
                 ns.outside.as_posix(), root + "/./models/", "", root + "/python/.", root + "//bin/"]
        (ns.root / DEFER_LIST).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        boot = INSTALLER / "core" / "bootstrap.sh"
        script = self.tmp / "functions.sh"
        script.write_bytes(('OS_NAME="$(uname -s)"\nENGINE="$1"\n' + shell_function(boot, "norm_path", False)
                            + shell_function(boot, "exact_child", False) + shell_function(boot, "delete_deferred", False)
                            + "delete_deferred\n").encode("utf-8"))
        r = self.sh(script.as_posix(), root)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        assert_only_python_and_bin_went(self, ns, out)
        self.assertEqual(out.count("refused"), 5, out)  # models twice, the two `..` paths, outside

    def test_uninstall_remove_engine_on_the_engine_python(self):
        r = self.sh(self.front(), "--home", self.home_arg(), "--yes", "--skip", "model,launch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hits = len(self.srv.srv.hits)
        # two engine Pythons: the newer version number must win (3.12.15 after 3.12.9; text order says otherwise)
        comp = json.loads(self.fx.components_path.read_text(encoding="utf-8"))
        comp["runtime"]["python"] = "3.12"
        self.fx.components_path.write_text(json.dumps(comp, indent=2), encoding="utf-8")
        for v in ("3.12.9", "3.12.15"):
            pbs = self.paths.python_dir / f"cpython-{v}-macos-aarch64-none" / "bin" / "python3"
            pbs.parent.mkdir(parents=True)
            pbs.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8",
                           newline="\n")
            os.chmod(pbs, 0o755)
        model = touch(self.paths.models_dir / "large-v3" / "model.bin", b"weights")
        r = self.sh(self.front(), "--home", self.home_arg(), "--uninstall", "--remove-engine", "--yes",
                    env=self.env(WNC_TEST_UV=None))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(len(self.srv.srv.hits), hits, self.srv.srv.hits[hits:])
        self.assertIn(f"at {pbs.as_posix()}", r.stdout)
        self.assertIn("uv and Python are not downloaded", r.stdout)
        self.assertIn(f"deleted {self.paths.whynot.as_posix()}/python", r.stdout)  # by the bootstrap, after the core
        self.assertEqual(os.listdir(self.paths.whynot), ["models"], out)
        self.assertEqual(model.read_bytes(), b"weights")


# --------------------------------------------------------------------------------------------- task 8: the location
def make_2x_home(home: Path, engine: Path) -> Path:
    """A WhyNot Cut 2.2.1 engine home (no 3.0 state.json: not a genuine 3.0 home by content) at `engine`, with the
    pointer the 2.x SessionStart hook wrote (engine_home "" for ~/.whynot-cut, else the folder). Returns its model."""
    model = touch(engine / "models" / "large-v3" / "model.bin", b"2.x weights")
    for d in ("venv/Scripts/python.exe", "marketplace/.claude-plugin/marketplace.json", "cuda/bin/cublas.dll",
              "ppro-queue/job-1.json"):
        touch(engine.joinpath(*d.split("/")), b"2.x")
    value = "" if norm(engine) == norm(home / ".whynot-cut") else str(engine)
    EngineHomeCases.pointer(home, {"clients_root": "", "engine_home": value, "updated": "2026-10-11T10:00:00+0300"})
    return model


def assert_2x_home_upgraded_in_place(test: unittest.TestCase, home: Path, engine: Path, model: Path, out: str) -> None:
    """Fix round 3: the resolved 2.x home is used directly - no WhyNotCut subfolder, models kept, the pointer still
    names it (or "" for ~/.whynot-cut)."""
    test.assertFalse((engine / "WhyNotCut").exists(), out)
    test.assertTrue((engine / "current").is_file(), out)
    test.assertTrue(base.is_engine_home(engine), out)
    test.assertEqual(model.read_bytes(), b"2.x weights")
    p = json.loads((home / ".whynot-cut" / "plugin-options.json").read_text(encoding="utf-8"))
    want = "" if norm(engine) == norm(home / ".whynot-cut") else str(engine)
    test.assertEqual(norm(p["engine_home"]) if p["engine_home"] else "", norm(want) if want else "", out)


def assert_chosen_home_installed(test: "_ShellCase", r, engine: Path, plat: str) -> None:
    """Everything of a chosen engine home landed there (uv, the runtime, state, the one log); ~/.whynot-cut keeps only
    the pointer; settings.json and the pointer name the folder."""
    out = r.stdout + r.stderr
    test.assertEqual(r.returncode, 0, out)
    custom = base.Paths.from_env(str(test.home), env={}, engine_home=str(engine))
    test.assertTrue((custom.bin_dir / ("uv.exe" if plat.startswith("win") else "uv")).is_file(), out)
    test.assertTrue((custom.downloads_dir / test.uv_asset(plat)["url"].rsplit("/", 1)[-1]).is_file(), out)
    test.assertTrue(custom.current_file.is_file(), out)
    test.assertTrue(custom.runtimes_dir.is_dir(), out)
    st = json.loads(custom.state_file.read_text(encoding="utf-8"))
    test.assertEqual(st["answers"]["whisper_model"], "large-v3")
    test.assertEqual(len(list(custom.logs_dir.glob("install-*.log"))), 1, out)
    default = test.home / ".whynot-cut"
    test.assertEqual(os.listdir(default), ["plugin-options.json"], out)
    p = json.loads((default / "plugin-options.json").read_text(encoding="utf-8"))
    test.assertEqual((list(p), norm(p["engine_home"])), (POINTER_KEYS, norm(engine)))
    s = json.loads(test.paths.settings_file.read_text(encoding="utf-8"))
    test.assertEqual(norm(s["pluginConfigs"][PID]["options"]["engine_home"]), norm(engine))
    test.assertIn("thewhynot-ai", s["extraKnownMarketplaces"])


@unittest.skipUnless(find_powershell(), "Windows PowerShell is not available")
class TestPowerShellEngineHome(TestPowerShellFrontEnd):
    """-EngineHome / the location question / -Model through install.ps1 and bootstrap.ps1, under the sandbox home."""
    run_functions = TestPowerShellUninstall.run_functions  # one bootstrap function run alone
    test_install_in_an_arabic_home_touches_nothing_outside = None
    test_dry_run_leaves_the_home_empty = None
    test_dry_run_without_uv_names_the_remaining_steps = None
    test_a_bad_uv_sha256_stops_with_3_and_names_the_file = None
    test_paths_ending_in_a_backslash_reach_the_core_intact = None
    test_the_bootstraps_quoting_guard_doubles_trailing_backslashes = None
    test_uv_already_at_the_pinned_version_is_not_downloaded = None

    def test_a_chosen_engine_home_installs_there_and_uninstalls_from_there(self):
        engine = self.home / "WhyNot Engine"
        before = live_snapshot()
        r = self.ps(self.front(), "-Home", self.home, "-EngineHome", engine, "-Yes", "-Skip", "model,launch")
        assert_chosen_home_installed(self, r, engine, "win-x64")
        out = r.stdout + r.stderr
        self.assertIn("C:\\WhyNotCut", out)  # the sandbox home has Arabic letters: warned, and kept with -Yes
        self.assertIn("حروف", out)
        # a second run without -EngineHome finds it through the pointer: nothing downloaded again
        hits = len(self.srv.srv.hits)
        r2 = self.ps(self.front(), "-Home", self.home, "-Yes", "-Skip", "model,launch")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(len(self.srv.srv.hits), hits, self.srv.srv.hits[hits:])
        self.assertEqual(os.listdir(self.home / ".whynot-cut"), ["plugin-options.json"])
        # uninstall -RemoveEngine, again without -EngineHome: that folder goes, never the client folder inside it
        client = touch(engine / "WhyNot Clients" / "Dr X" / ".whynot-client", b"{}")
        r3 = self.ps(self.front(), "-Home", self.home, "-Uninstall", "-RemoveEngine", "-Yes")
        out3 = r3.stdout + r3.stderr
        self.assertEqual(r3.returncode, 0, out3)
        self.assertEqual(os.listdir(engine), ["WhyNot Clients"], out3)
        self.assertEqual(client.read_bytes(), b"{}")
        self.assertFalse((self.home / ".whynot-cut").exists(), out3)  # it held only the pointer
        s = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
        self.assertNotIn("engine_home", (s.get("pluginConfigs") or {}).get(PID, {}).get("options", {}))
        self.assertEqual(live_snapshot(), before)

    def test_the_location_question(self):
        # -Customise: the bootstrap asks (answers from the sandbox-only test hook WNC_TEST_ANSWERS, one per line)
        answers = self.tmp / "answers.txt"
        answers.write_text("\n".join(["engine", str(self.home / "Engine Y"), ""]) + "\n", encoding="utf-8")
        self.home.mkdir()
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Customise",
                    env=self.env(WNC_TEST_ANSWERS=str(answers)))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn(str(self.home / ".whynot-cut"), out)  # the default offered first
        self.assertIn("full path", out)  # "engine" is refused: asked again
        self.assertIn("حروف", out)  # Engine Y has Arabic letters: warned (EN + AR), asked again
        suggestion = self.home / "WhyNotCut"  # (C:\WhyNotCut outside a sandbox)
        self.assertIn(f"engine home {suggestion} (chosen)", out)  # Enter took the suggestion
        self.assertEqual(list(self.home.iterdir()), [])  # a dry run creates nothing

    def test_free_space_on_the_chosen_drive(self):
        self.home.mkdir()
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes", env=self.env(WNC_TEST_FREE_GB="7"))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 2, out)  # 6 GB + 3 GB for the model
        self.assertIn("9 GB", out)
        self.assertEqual(self.srv.srv.hits, [])
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes", "-Skip", "model",
                    env=self.env(WNC_TEST_FREE_GB="7"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # without the model 6 GB are enough
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes", env=self.env(WNC_TEST_FREE_GB="5"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_unsafe_engine_homes_stop_before_any_download(self):
        touch(self.home / "Clients" / ".whynot-client", b"{}")
        for bad, needle in ((self.home / "Clients" / "engine", "client folder"),
                            (self.fx.plugin_root / "engine home", "plugin folder"),
                            (self.tmp / "outside the sandbox", "sandbox")):
            with self.subTest(str(bad)):
                r = self.ps(self.front(), "-Home", self.home, "-EngineHome", bad, "-Yes", "-Skip", "model,launch")
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 2, out)
                self.assertIn(needle, out)
                self.assertFalse(os.path.lexists(bad), out)
        self.assertEqual(self.srv.srv.hits, [])

    def test_a_chosen_documents_folder_gets_its_own_subfolder(self):
        # fix round 1 (CRITICAL): Documents with the editor's files; install and uninstall never touch them
        docs = self.home / "Documents"
        thesis = touch(docs / "thesis.docx", b"my thesis")
        taxes = touch(docs / "Taxes" / "2025.pdf", b"my taxes")
        r = self.ps(self.front(), "-Home", self.home, "-EngineHome", docs, "-Yes", "-Skip", "model,launch")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        engine = docs / "WhyNotCut"
        self.assertIn(f"goes into its own folder {engine}", out)
        self.assertIn("مجلد خاص", out)
        self.assertTrue((engine / "current").is_file(), out)
        self.assertEqual(sorted(os.listdir(docs)), ["Taxes", "WhyNotCut", "thesis.docx"])
        r = self.ps(self.front(), "-Home", self.home, "-Uninstall", "-RemoveEngine", "-Yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual((thesis.read_bytes(), taxes.read_bytes()), (b"my thesis", b"my taxes"))
        for _ in range(50):
            if not engine.exists():
                break
            time.sleep(0.1)
        self.assertFalse(engine.exists(), out)  # only WhyNot Cut's own entries were in it
        self.assertEqual(sorted(os.listdir(docs)), ["Taxes", "thesis.docx"])

    def test_a_folder_with_the_editors_bin_gets_its_own_subfolder(self):
        # fix round 2: `Bin` is not bin/ (PowerShell's -contains ignored case; NTFS opens `bin` as `Bin`)
        edit = self.home / "Edit"
        project = touch(edit / "Bin" / "edit.prproj", b"my project")
        r = self.ps(self.front(), "-Home", self.home, "-EngineHome", edit, "-Yes", "-Skip", "model,launch")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        engine = edit / "WhyNotCut"
        self.assertTrue((engine / "bin" / "uv.exe").is_file(), out)
        self.assertEqual(sorted(os.listdir(edit / "Bin")), ["edit.prproj"])
        r = self.ps(self.front(), "-Home", self.home, "-Uninstall", "-RemoveEngine", "-Yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(project.read_bytes(), b"my project")
        self.assertEqual(sorted(os.listdir(edit)), ["Bin"])

    def test_the_deferred_delete_never_takes_a_case_variant(self):
        root = self.home / ".whynot-cut"
        theirs = touch(root / "Bin" / "edit.prproj", b"my project")
        touch(root / "python" / "cpython-3.12.15-x" / "python.exe", b"MZ")
        (root / DEFER_LIST).write_text(f"{root / 'python'}\n{root / 'bin'}\n{root}\n", encoding="utf-8")
        r = self.run_functions(["Test-WncReparse", "Invoke-WncDeleteTree", "Invoke-WncDeferredDelete"],
                               "Invoke-WncDeferredDelete $env:WNC_T_ENGINE", WNC_T_ENGINE=str(root))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(theirs.read_bytes(), b"my project", out)
        self.assertFalse((root / "python").exists(), out)
        self.assertIn("not named exactly bin", out)
        self.assertTrue(root.is_dir())  # not empty: kept

    def test_a_failed_download_leaves_a_claimed_engine_home(self):
        # fix round 2: the bootstrap writes WhyNot Cut's state.json before any download, so a retry reuses the folder
        fresh = self.home / "Fresh"
        self.break_uv_sha()
        r = self.ps(self.front(), "-Home", self.home, "-EngineHome", fresh, "-Yes", "-Skip", "model,launch")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertTrue(base.is_engine_home(fresh))
        self.assertEqual(base.choose_engine_home(str(fresh), home=self.home, plugin_root=self.fx.plugin_root)[0],
                         fresh)

    def test_a_2x_home_is_upgraded_in_place(self):
        # fix round 3: the resolved home (default, or saved in the pointer) is never moved into a subfolder
        for engine in (self.home / ".whynot-cut", self.home / "Old Engine"):
            with self.subTest(str(engine)):
                model = make_2x_home(self.home, engine)
                r = self.ps(self.front(), "-Home", self.home, "-Yes", "-Skip", "model,launch")
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 0, out)
                self.assertNotIn("goes into its own folder", out)
                self.assertNotIn("(chosen)", out)
                assert_2x_home_upgraded_in_place(self, self.home, engine, model, out)

    def test_choosing_away_from_a_2x_home_says_it_stays_behind(self):
        make_2x_home(self.home, self.home / ".whynot-cut")
        r = self.ps(self.front(), "-Home", self.home, "-EngineHome", self.home / "Other", "-DryRun", "-Yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("stays there and is no longer used", out)

    def test_enter_on_a_reinstall_keeps_the_existing_install(self):
        # fix round 1 (IMPORTANT 1): an Arabic-letter home with an install: no non-ASCII re-ask, no move
        touch(self.home / ".whynot-cut" / "state.json", GENUINE_STATE)
        answers = self.tmp / "answers.txt"
        answers.write_text("\n", encoding="utf-8")  # Enter, once: a second question would end the answers (exit 2)
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Customise",
                    env=self.env(WNC_TEST_ANSWERS=str(answers)))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("already installed there, so it stays there", out)
        self.assertIn(f"engine home {self.home / '.whynot-cut'} (default)", out)
        self.assertNotIn("stays there and is no longer used", out)

    def test_another_folder_says_the_old_install_stays_behind(self):
        touch(self.home / ".whynot-cut" / "state.json", GENUINE_STATE)
        r = self.ps(self.front(), "-Home", self.home, "-EngineHome", self.home / "Other", "-DryRun", "-Yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn(f"already installed in {self.home / '.whynot-cut'} stays there and is no longer used", out)
        self.assertIn("التثبيت القديم سيبقى", out)

    def test_links_and_folders_holding_the_plugin_are_refused(self):
        target = self.tmp / "target"
        target.mkdir()
        junction = self.home / "junction"
        self.home.mkdir()
        cases = [(self.fx.root, "holds the plugin folder")]
        if make_dir_link(junction, target):
            cases.append((junction, "link or mount point"))
        for bad, needle in cases:
            with self.subTest(str(bad)):
                r = self.ps(self.front(), "-Home", self.home, "-EngineHome", bad, "-Yes", "-Skip", "model,launch")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(needle, r.stdout + r.stderr)
        self.assertEqual(os.listdir(target), [])
        self.assertEqual(self.srv.srv.hits, [])

    def test_the_model_flag(self):
        self.home.mkdir()
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes", "-Model", "medium")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("model-download --model medium", r.stdout)
        r = self.ps(self.front(), "-Home", self.home, "-DryRun", "-Yes", "-Model", "huge")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("large-v3-turbo", r.stdout + r.stderr)  # names the choices
        self.assertEqual(self.srv.srv.hits, [])


@unittest.skipUnless(find_bash(), "bash is not available")
class TestBashEngineHome(TestBashFrontEnd):
    """--engine-home / the location question / --model through install.sh and bootstrap.sh, under the sandbox home."""
    test_install_in_an_arabic_home_touches_nothing_outside = None
    test_uv_already_at_the_pinned_version_is_not_downloaded = None
    test_uv_is_found_anywhere_in_its_archive = None
    test_dry_run_leaves_the_home_empty = None
    test_a_bad_uv_sha256_stops_with_3_and_names_the_file = None
    test_git_bash_without_test_platform_says_use_install_ps1 = None
    test_piped_script_with_yes_does_not_hang = None
    test_piped_without_source_says_h3_in_arabic_too = None

    def test_a_chosen_engine_home_installs_there_and_uninstalls_from_there(self):
        engine = self.home / "WhyNot Engine"
        r = self.sh(self.front(), "--home", self.home_arg(), "--engine-home", engine.as_posix(), "--yes",
                    "--skip", "model,launch")
        assert_chosen_home_installed(self, r, engine, "mac-arm64")
        client = touch(engine / "WhyNot Clients" / "Dr X" / ".whynot-client", b"{}")
        r3 = self.sh(self.front(), "--home", self.home_arg(), "--uninstall", "--remove-engine", "--yes")
        out3 = r3.stdout + r3.stderr
        self.assertEqual(r3.returncode, 0, out3)
        self.assertEqual(os.listdir(engine), ["WhyNot Clients"], out3)
        self.assertEqual(client.read_bytes(), b"{}")
        self.assertFalse((self.home / ".whynot-cut").exists(), out3)

    def test_the_location_question(self):
        answers = self.tmp / "answers.txt"
        answers.write_text("engine\n" + (self.home / "Engine Z").as_posix() + "\n", encoding="utf-8", newline="\n")
        self.home.mkdir()
        r = self.sh(self.front(), "--home", self.home_arg(), "--dry-run", "--customise",
                    env=self.env(WNC_TEST_ANSWERS=answers.as_posix()))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("full path", out)
        self.assertIn(f"engine home {(self.home / 'Engine Z').as_posix()} (chosen)", out)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_a_chosen_documents_folder_gets_its_own_subfolder(self):
        docs = self.home / "Documents"
        thesis = touch(docs / "thesis.docx", b"my thesis")
        r = self.sh(self.front(), "--home", self.home_arg(), "--engine-home", docs.as_posix(), "--yes",
                    "--skip", "model,launch")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        engine = docs / "WhyNotCut"
        self.assertIn(f"goes into its own folder {docs.as_posix()}/WhyNotCut", out)
        self.assertIn("مجلد خاص", out)
        self.assertTrue((engine / "current").is_file(), out)
        r = self.sh(self.front(), "--home", self.home_arg(), "--uninstall", "--remove-engine", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(thesis.read_bytes(), b"my thesis")
        self.assertEqual(sorted(os.listdir(docs)), ["thesis.docx"], r.stdout + r.stderr)

    def test_a_2x_home_is_upgraded_in_place(self):
        # fix round 3: the resolved home (default, or saved in the pointer) is never moved into a subfolder
        for engine in (self.home / ".whynot-cut", self.home / "Old Engine"):
            with self.subTest(str(engine)):
                model = make_2x_home(self.home, engine)
                r = self.sh(self.front(), "--home", self.home_arg(), "--yes", "--skip", "model,launch")
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 0, out)
                self.assertNotIn("goes into its own folder", out)
                self.assertNotIn("(chosen)", out)
                assert_2x_home_upgraded_in_place(self, self.home, engine, model, out)
        make_2x_home(self.home, self.home / ".whynot-cut")
        r = self.sh(self.front(), "--home", self.home_arg(), "--engine-home", (self.home / "Other").as_posix(),
                    "--dry-run", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("stays there and is no longer used", r.stdout + r.stderr)

    def test_engine_named_user_folders_and_a_fake_state_get_a_subfolder(self):
        # fix round 2: names and a foreign state.json never make a folder ours
        for name, rel, data in (("Work", "logs/shoot-notes.txt", b"user notes"),
                                ("Edit", "Bin/edit.prproj", b"my project"),
                                ("Proj", "state.json", b'{"my": "game save"}')):
            with self.subTest(name):
                folder = self.home / name
                f = touch(folder.joinpath(*rel.split("/")), data)
                r = self.sh(self.front(), "--home", self.home_arg(), "--engine-home", folder.as_posix(), "--dry-run",
                            "--yes")
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 0, out)
                self.assertIn(f"engine home {folder.as_posix()}/WhyNotCut (chosen)", out)
                self.assertEqual(f.read_bytes(), data)

    def test_the_deferred_delete_never_takes_a_case_variant(self):
        root = self.home / ".whynot-cut"
        theirs = touch(root / "Bin" / "edit.prproj", b"my project")
        touch(root / "python" / "x", b"x")
        (root / DEFER_LIST).write_text(f"{root.as_posix()}/python\n{root.as_posix()}/bin\n{root.as_posix()}\n",
                                       encoding="utf-8", newline="\n")
        boot = INSTALLER / "core" / "bootstrap.sh"
        script = self.tmp / "functions.sh"
        script.write_bytes(('OS_NAME="$(uname -s)"\nENGINE="$1"\n' + shell_function(boot, "norm_path", False)
                            + shell_function(boot, "exact_child", False) + shell_function(boot, "delete_deferred", False)
                            + "delete_deferred\n").encode("utf-8"))
        r = self.sh(script.as_posix(), root.as_posix())
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(theirs.read_bytes(), b"my project", out)
        self.assertFalse((root / "python").exists(), out)
        if (root / "bin").exists():  # a case-insensitive disk (NTFS, APFS) opens `Bin` as `bin`
            self.assertIn("not named exactly bin", out)

    def test_piped_source_is_cached_under_the_chosen_engine_home(self):
        zf = self.tmp / "WhyNotCut-3.0.0.zip"
        zsha = release_zip(self.fx, zf)
        engine = self.home / "WhyNot Engine"
        r = self.sh("-s", "--", "--home", self.home_arg(), "--engine-home", engine.as_posix(), "--yes",
                    "--skip", "model,launch", "--source", zf.as_posix(), "--source-sha256", zsha,
                    script=(INSTALLER / "install.sh").read_bytes())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((engine / "downloads" / f"release-{zsha[:8]}" / zf.name).is_file())
        self.assertTrue((engine / "current").is_file())
        self.assertFalse((self.home / ".whynot-cut" / "downloads").exists())

    def test_another_folder_says_the_old_install_stays_behind(self):
        touch(self.home / ".whynot-cut" / "state.json", GENUINE_STATE)
        r = self.sh(self.front(), "--home", self.home_arg(), "--engine-home", (self.home / "Other").as_posix(),
                    "--dry-run", "--yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("stays there and is no longer used", out)
        self.assertIn("التثبيت القديم سيبقى", out)
        r = self.sh(self.front(), "--home", self.home_arg(), "--engine-home", self.fx.root.as_posix(), "--yes")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("holds the plugin folder", r.stdout + r.stderr)

    def test_free_space_and_the_model_flag(self):
        self.home.mkdir()
        r = self.sh(self.front(), "--home", self.home_arg(), "--dry-run", "--yes", env=self.env(WNC_TEST_FREE_GB="7"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("9 GB", r.stdout + r.stderr)
        r = self.sh(self.front(), "--home", self.home_arg(), "--dry-run", "--yes", "--model", "small")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("model-download --model small", r.stdout)
        r = self.sh(self.front(), "--home", self.home_arg(), "--dry-run", "--yes", "--model", "huge")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.srv.srv.hits, [])


# --------------------------------------------------------------------------------------------- task 9 (Addendum D, D-T1)
SIZE_EN = "Installing everything WhyNot Cut needs (about {} GB)"
SIZE_AR = "جارٍ تثبيت كل ما يحتاجه WhyNot Cut (حوالي {} جيجابايت)"
COUNTDOWN_EN = "Press C to customise (10)" + chr(0x2026)
COUNTDOWN_AR = "اضغط C للتخصيص"
SELF_FIX = "run the installer again with -EngineHome <folder> / --engine-home <folder>"
SELF_FIX_AR = "شغّل المثبّت مرة أخرى"
QUESTION_NEEDLES = ("Folder / ", "Model / ", "Language / ", "client folders / ")  # bootstrap location + the core's


def comparable_state(path: Path, home: Path) -> dict:
    """state.json without what differs between two equal runs in two sandbox homes: timestamps, free space, the home."""
    homes = sorted({str(home), home.as_posix(), json.dumps(str(home))[1:-1]}, key=len, reverse=True)

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items() if not (k == "at" or k.endswith("_at") or k == "free_gb")}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            for h in homes:
                v = v.replace(h, "<HOME>")
            v = re.sub(r"\d{8}-\d{6}", "<T>", v)
            return re.sub(r"[\d.]+ GB free", "<N> GB free", v)
        return v
    return walk(json.loads(path.read_text(encoding="utf-8")))


# the reviewer's repro (fix round 3): a Documents folder holding the editor's own files under WhyNot Cut's layout names,
# plus the genuine state.json an install through a link would have written
REPRO_DOCUMENTS = ("cache/c.bin", "logs/my.log", "tmp/t.txt", "fonts/MyFont.ttf", "bench/b.txt", "downloads/d.zip",
                   "current", "bin/tool.exe", "python/p.txt", "thesis.docx")


def make_repro_documents(docs: Path) -> dict:
    for rel in REPRO_DOCUMENTS:
        touch(docs.joinpath(*rel.split("/")), b"mine " + rel.encode())
    touch(docs / "state.json", GENUINE_STATE)
    return snapshot_tree(docs)


def snapshot_tree(root: Path) -> dict:
    """{relative path: bytes or None for a folder} of everything below `root` (links not entered)."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not base.is_link(os.path.join(dirpath, x))]
        for x in dirs:
            out[os.path.relpath(os.path.join(dirpath, x), root)] = None
        for x in files:
            f = os.path.join(dirpath, x)
            with open(f, "rb") as fh:
                out[os.path.relpath(f, root)] = fh.read()
    return out


def drop_dir_link(link: Path) -> None:
    """Remove a directory link made by make_dir_link (the link only, never its target)."""
    if os.path.lexists(link):
        try:
            os.rmdir(link)  # a junction / a Windows directory symlink
        except OSError:
            os.unlink(link)


class TestNoQuestionsByDefault(unittest.TestCase):
    """D-T1: the core asks nothing unless --customise; answers.mode records which; the install size estimate."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        self.sy = system_module()

    def ctx(self, **args):
        a = {"clients_folder": None, "language": None, "model": None, "yes": False, "customise": False}
        a.update(args)
        return make_ctx(self.home, {"schema": 1}, SK, "win-x64", **a)

    def test_the_default_mode_asks_nothing_even_with_a_terminal(self):
        ctx = self.ctx()
        with mock.patch.object(base, "can_ask", return_value=True), \
                mock.patch.object(base, "ask", side_effect=AssertionError("asked without --customise")):
            r = self.sy.step_questions(ctx)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertEqual(ctx.answers["mode"], "default")
        self.assertEqual(self.sy.answer_mode(ctx), "default")
        self.assertEqual(self.sy.answer_mode(self.ctx(yes=True)), "default")

    def test_customise_asks_model_language_then_clients_folder_each_preselected(self):
        prompts = []
        replies = ["2", "en", str(self.home.parent / "My Clients")]

        def ask(prompt, default=""):
            prompts.append(prompt)
            return replies.pop(0) if replies else default
        ctx = self.ctx(customise=True)
        with mock.patch.object(base, "can_ask", return_value=True), mock.patch.object(base, "ask", side_effect=ask):
            self.sy.step_questions(ctx)
        self.assertEqual(len(prompts), 3, prompts)
        self.assertIn("Model / ", prompts[0])
        self.assertIn("[large-v3]", prompts[0])
        self.assertIn("Language / ", prompts[1])
        self.assertIn("[ar]", prompts[1])
        self.assertIn("client folders / ", prompts[2])
        self.assertIn(str(self.home / "Documents" / "WhyNot Clients"), prompts[2])
        a = ctx.answers
        self.assertEqual((a["whisper_model"], a["language"], a["clients_root"], a["mode"]),
                         ("large-v3-turbo", "en", str(self.home.parent / "My Clients"), "customise"))

    def test_customise_without_a_terminal_keeps_every_default(self):
        # fix round 1: nothing could be asked, so the mode is "default" (the state then equals a --yes run's)
        ctx = self.ctx(customise=True)
        with mock.patch.object(base, "can_ask", return_value=False), \
                mock.patch.object(base, "ask", side_effect=AssertionError("asked")):
            self.sy.step_questions(ctx)
        self.assertEqual((ctx.answers["whisper_model"], ctx.answers["mode"]), ("large-v3", "default"))
        with mock.patch.object(base, "can_ask", return_value=False):
            self.assertEqual(self.sy.answer_mode(self.ctx(customise=True)), "default")

    def test_state_records_the_mode(self):
        for customise, want in ((False, "default"), (True, "customise")):
            with self.subTest(customise=customise):
                ctx = self.ctx(customise=customise, channel=None)
                with mock.patch.object(base, "can_ask", return_value=True), \
                        mock.patch.object(base, "ask", side_effect=lambda prompt, default="": default):
                    self.sy.step_questions(ctx)
                    self.sy.step_state(ctx)
                st = json.loads(ctx.paths.state_file.read_text(encoding="utf-8"))
                self.assertEqual(st["answers"]["mode"], want)

    def test_yes_and_customise_cannot_be_used_together(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(err):
            cli.main(["install", "--home", str(self.home), "--yes", "--customise"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--customise", err.getvalue())
        self.assertFalse(self.home.exists())

    def test_the_answers_hook_is_honoured_only_in_a_sandbox_and_after_the_bootstraps_lines(self):
        answers = touch(self.home.parent / "answers.txt", "\n".join(["loc", "2", "en"]).encode("utf-8"))
        env = {"WNC_TEST_ANSWERS": str(answers), "WNC_TEST_ANSWERS_AT": "1"}
        self.assertEqual(cli.test_answers(argparse.Namespace(home=str(self.home)), env), ["2", "en"])
        self.assertIsNone(cli.test_answers(argparse.Namespace(home=None), env))
        self.assertIsNone(cli.test_answers(argparse.Namespace(home=str(self.home)), {}))
        try:
            base.set_test_answers(["medium"])
            self.assertTrue(base.can_ask(argparse.Namespace(yes=False)))
            self.assertFalse(base.can_ask(argparse.Namespace(yes=True)))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(base.ask("Model / النموذج [large-v3]: ", ""), "medium")
                self.assertEqual(base.ask("Language [ar]: ", "ar"), "ar")  # no lines left: the default
            self.assertIn("Model / ", out.getvalue())
        finally:
            base.set_test_answers(None)

    def test_the_install_size(self):
        sy = self.sy
        comp = base.load_components(COMPONENTS)
        g = 1024 ** 3
        ff = sum(f["bytes"] for f in comp["ffmpeg"]["assets"]["win-x64"]["files"]) / g
        fonts = sum(f["bytes"] for f in comp["fonts"]["files"] + comp["fonts"].get("licenses", [])) / g
        git = 0.4  # fix round 1: PortableGit unpacked, not its 60 MB self-extractor

        def up(x):
            return math.ceil(round(x * 10, 6)) / 10
        self.assertEqual(sy.install_size_gb(comp, "win-x64", git_missing=True), up(0.5 + ff + fonts + 2.9 + git))
        self.assertEqual(sy.install_size_gb(comp, "win-x64", git_missing=False), up(0.5 + ff + fonts + 2.9))
        mac_ff = sum(f["bytes"] for f in comp["ffmpeg"]["assets"]["mac-arm64"]["files"]) / g
        self.assertEqual(sy.install_size_gb(comp, "mac-arm64", git_missing=True), up(0.5 + mac_ff + fonts + 2.9))
        self.assertEqual(sy.install_size_gb(comp, "win-x64", model="small", skip=("ffmpeg", "fonts")),
                         up(0.5 + 0.5))
        self.assertEqual(sy.install_size_gb(comp, "win-x64", skip=("model",)), up(0.5 + ff + fonts))
        # without sizes in components.json: the constants (runtime 0.5, ffmpeg 0.1, fonts 0.01, Git 0.4)
        self.assertEqual(sy.install_size_gb({"schema": 1}, "win-x64", git_missing=True), up(0.5 + 0.1 + 0.01 + 2.9 + 0.4))
        # an NVIDIA GPU on Windows adds the CUDA libraries (about 1 GB); never on a Mac; not with --skip gpu
        self.assertEqual(sy.install_size_gb(comp, "win-x64", nvidia=True), up(0.5 + ff + fonts + 2.9 + 1.0))
        self.assertEqual(sy.install_size_gb(comp, "mac-arm64", nvidia=True), up(0.5 + mac_ff + fonts + 2.9))
        self.assertEqual(sy.install_size_gb(comp, "win-x64", nvidia=True, skip=("gpu",)), up(0.5 + ff + fonts + 2.9))
        self.assertEqual(sy.format_gb(3.5), "3.5")
        self.assertEqual(sy.format_gb(4.0), "4.0")


class TestResolvedHomeGuard(unittest.TestCase):
    """Task 8 review carry (controller ruling): a RESOLVED engine home other than ~/.whynot-cut that is a drive root /
    mount point, the user folder, Desktop / Documents / Downloads themselves, or holds client data is refused."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.home = Path(self._td.name) / ARABIC_HOME
        self.home.mkdir()

    def problem(self, path, clients=()):
        return base.resolved_home_problem(path, home=self.home, clients_roots=clients)

    def test_the_refused_places(self):
        h = self.home
        touch(h / "Work" / "Clinic" / "Dr X" / ".whynot-client", b"{}")  # 3 levels below Work
        touch(h / "Deep" / "a" / "b" / "c" / "d" / ".whynot-client", b"{}")  # 4 levels: not looked at
        touch(h / "Shoot" / ".whynot-client", b"{}")  # the folder itself is a client folder
        for bad, needle in ((Path(h.anchor), "drive root"), (h, "your user folder"), (h / "Desktop", "Desktop"),
                            (h / "Documents", "Documents"), (h / "Downloads", "Downloads"),
                            (h / "Work", "client folder"), (h / "Shoot", "client folder"),
                            (h / "Clients Base", "clients folder")):
            with self.subTest(str(bad)):
                p = self.problem(bad, clients=[h / "Clients Base" / "WhyNot Clients"])
                self.assertIsNotNone(p)
                self.assertIn(needle, p)
        with mock.patch.object(base.os.path, "ismount", side_effect=lambda p: norm(p) == norm(h / "USB")):
            self.assertIn("mount point", self.problem(h / "USB"))
        for fine in (h / ".whynot-cut", h / "Documents" / "WhyNot Engine", h / "Deep", h / "Old Engine"):
            with self.subTest(fine=str(fine)):
                self.assertIsNone(self.problem(fine, clients=[h / "Clients Base" / "WhyNot Clients"]))
        # ~/.whynot-cut itself is never refused by this rule, whatever it holds
        touch(h / ".whynot-cut" / "Clients" / ".whynot-client", b"{}")
        self.assertIsNone(self.problem(h / ".whynot-cut"))

    def test_spelling_variants_of_a_refused_place(self):
        # fix round 1: a trailing separator, `..` and (where the disk ignores case) another case are the same folder
        h = self.home
        (h / "Documents").mkdir()
        variants = [str(h / "Documents") + os.sep, str(h / "x" / ".." / "Documents"), h / "Documents" / "."]
        if IS_WIN:
            variants.append(str(h / "Documents").upper())
        for v in variants:
            with self.subTest(str(v)):
                self.assertIn("Documents", self.problem(v) or "")

    def test_links_are_refused_and_resolved(self):
        # fix round 1 (controller ruling): a link itself is refused; through a linked parent the real folder counts
        h = self.home
        (h / "Documents").mkdir()
        cases = []
        if make_dir_link(h / "lnk", h / "Documents"):
            cases.append((h / "lnk", "link or mount point"))
        if make_dir_link(h / "eng", h):
            cases.append((h / "eng" / "Documents", "Documents"))
        stand_in = h.parent / "drive stand-in"  # (never a link to a real drive root: cleanup must stay in temp)
        stand_in.mkdir()
        if make_dir_link(h / "root", stand_in):
            cases.append((h / "root", "link or mount point"))
        if not cases:
            self.skipTest("cannot make a directory link here")
        for path, needle in cases:
            with self.subTest(str(path)):
                self.assertIn(needle, self.problem(path) or "")
        # a real folder inside Documents is still fine, also reached through the linked parent
        (h / "Documents" / "Engine").mkdir()
        self.assertIsNone(self.problem(h / "Documents" / "Engine"))
        if (h / "eng").exists():
            self.assertIsNone(self.problem(h / "eng" / "Documents" / "Engine"))

    def test_a_folder_too_big_to_check_is_refused(self):
        # fix round 1: past MARKER_SCAN_LIMIT entries within 3 levels the scan stops - and the guard refuses
        big = self.home / "Footage"
        big.mkdir()
        for i in range(base.MARKER_SCAN_LIMIT + 1):
            open(big / f"clip{i:05d}.mov", "wb").close()
        touch(big / "a" / "b" / "c" / "d" / ".whynot-client", b"{}")  # deeper than 3 levels: never seen
        p = self.problem(big)
        self.assertIn("too big to check", p or "")
        self.assertIn("-EngineHome", p)
        # the chosen-folder rule of Task 8 is unchanged: past the limit it finds no marker
        self.assertIsNone(base._marker_below(str(big)))

    def test_macos_compares_names_case_insensitively(self):
        # fix round 1: normcase does not fold case on Darwin, but APFS / HFS+ do; the guard folds it there
        h = self.home
        (h / "Documents").mkdir()
        lower = str(h / "documents")
        with mock.patch("os.path.normcase", side_effect=lambda s: s), \
                mock.patch("os.path.realpath", side_effect=lambda s, **kw: os.path.abspath(s)):
            with mock.patch.object(base.sys, "platform", "darwin"):
                self.assertIn("Documents", self.problem(lower) or "")
            with mock.patch.object(base.sys, "platform", "linux"):  # a case-sensitive disk: another folder
                self.assertIsNone(self.problem(lower))

    def test_device_and_network_paths(self):
        # fix round 2: \\?\C:\x is C:\x; any other device path and every network share (also \\localhost\C$) is refused
        docs = self.home / "Documents"
        docs.mkdir()
        if IS_WIN:
            self.assertIn("Documents", self.problem("\\\\?\\" + str(docs)) or "")
        for bad in ("\\\\localhost\\C$\\Users\\x", "\\\\?\\UNC\\server\\share\\x", "\\\\.\\pipe\\x",
                    "//server/share/x"):
            with self.subTest(bad):
                self.assertIn("network share or device path", self.problem(bad) or "")
        self.assertEqual(base.strip_long_prefix("\\\\?\\C:\\x"), "C:\\x")
        self.assertEqual(base.strip_long_prefix("\\\\?\\UNC\\s\\x"), "\\\\?\\UNC\\s\\x")

    def test_a_linked_default_home_is_accepted_any_other_link_is_not(self):
        # Addendum F (owner 2026-10-13): ~/.whynot-cut may be a junction / symlink to a folder (D:\ClaudeData\...)
        target = self.home.parent / "data drive" / "whynot-cut-home"
        target.mkdir(parents=True)
        if not make_dir_link(self.home / ".whynot-cut", target):
            self.skipTest("cannot make a directory link here")
        make_dir_link(self.home / "Other", target)
        self.assertTrue(base.linked_default_home(self.home / ".whynot-cut", self.home))
        self.assertFalse(base.linked_default_home(self.home / "Other", self.home))
        self.assertIsNone(self.problem(self.home / ".whynot-cut"))
        self.assertIn("link", self.problem(self.home / "Other") or "")
        touch(target / "state.json", GENUINE_STATE)
        un = uninstall_module()
        self.assertIsNone(un.engine_home_problem(base.Paths.from_env(str(self.home), env={})))
        other = base.Paths.from_env(str(self.home), env={}, engine_home=str(self.home / "Other"))
        self.assertIn("is a link", un.engine_home_problem(other) or "")

    def test_a_linked_default_home_is_checked_by_where_it_points(self):
        # fix round 3 (CRITICAL): ~/.whynot-cut that is a link is checked by its real target: install and uninstall
        h = self.home
        link = h / ".whynot-cut"
        docs = h / "Documents"
        docs.mkdir()
        marked = h / "Shoots"
        touch(marked / "Dr X" / ".whynot-client", b"{}")
        safe = h.parent / "data drive" / "WhyNotCut"
        safe.mkdir(parents=True)
        stand_in = h.parent / "drive stand-in"
        stand_in.mkdir()
        un = uninstall_module()
        cases = [(docs, "Documents"), (h, "your user folder"), (marked, "client folder"), (stand_in, "drive root")]
        for target, needle in cases:
            with self.subTest(str(target)):
                if not make_dir_link(link, target):
                    self.skipTest("cannot make a directory link here")
                self.addCleanup(drop_dir_link, link)
                try:
                    real_root = base._real(stand_in)
                    with mock.patch.object(base, "_is_drive_root",
                                           side_effect=lambda q, _o=base._is_drive_root: _o(q) or q == real_root):
                        why = self.problem(link)
                        self.assertIn(needle, why or "")
                        self.assertIn("a link to", why)
                        self.assertIn("remove the link", why)
                        touch(target / "state.json", GENUINE_STATE) if target != h else None
                        problem = un.engine_home_problem(base.Paths.from_env(str(h), env={}))
                        self.assertIn(needle, problem or "")
                finally:
                    drop_dir_link(link)
        # a link to a plain folder of its own (Addendum F) keeps working
        self.assertTrue(make_dir_link(link, safe))
        self.assertIsNone(self.problem(link))
        touch(safe / "state.json", GENUINE_STATE)
        self.assertIsNone(un.engine_home_problem(base.Paths.from_env(str(h), env={})))

    def test_the_reviewers_repro_uninstall_deletes_nothing(self):
        # fix round 3: ~/.whynot-cut -> Documents holding layout-named folders of the editor and a genuine state.json
        docs = self.home / "Documents"
        before = make_repro_documents(docs)
        if not make_dir_link(self.home / ".whynot-cut", docs):
            self.skipTest("cannot make a directory link here")
        self.addCleanup(drop_dir_link, self.home / ".whynot-cut")
        rc, out = self.run_core("uninstall", "--home", str(self.home), "--remove-engine", "--remove-models", "--yes",
                                "--quiet")
        self.assertEqual(rc, 2, out)  # refused before any step: not even state.json is written through the link
        self.assertIn("remove the link", out)
        self.assertEqual(snapshot_tree(docs), before, out)  # nothing deleted, no .delete-after-exit
        self.assertFalse((docs / ".delete-after-exit").exists())
        rc, out = self.run_core("install", "--home", str(self.home), "--yes", "--quiet")
        self.assertEqual(rc, 2, out)
        self.assertIn("Documents", out)
        self.assertEqual(snapshot_tree(docs), before, out)

    def test_the_core_says_what_the_bootstrap_left(self):
        # fix round 2: the exit-2 message is true - "No install step ran", and names bin/ / python/ when they are there
        docs = self.home / "Documents"
        EngineHomeCases.pointer(self.home, {"clients_root": "", "engine_home": str(docs)})
        rc, out = self.run_core("install", "--home", str(self.home), "--yes", "--quiet")
        self.assertEqual(rc, 2, out)
        self.assertIn("No install step ran.", out)
        self.assertNotIn("Nothing was changed", out)
        touch(docs / "bin" / "uv.exe", b"MZ")
        rc, out = self.run_core("install", "--home", str(self.home), "--yes", "--quiet")
        self.assertEqual(rc, 2, out)
        self.assertIn("bin/ already in that folder came from the bootstrap", out)

    def test_windows_shell_folders_count(self):
        # fix round 1: Known Folder Move (OneDrive) puts Documents elsewhere; the core and the bootstrap both read it
        moved = self.home.parent / "OneDrive" / "Documents"
        moved.mkdir(parents=True)
        self.assertIn("Documents", base.resolved_home_problem(moved, home=self.home,
                                                              known=[("Documents", moved)]) or "")
        self.assertIsNone(base.resolved_home_problem(moved, home=self.home))
        names = [n for n, _f in base.shell_folders(self.home, sandbox=True)]
        self.assertEqual(names, ["Desktop", "Documents", "Downloads"])  # a sandbox never reads the registry

    def run_core(self, *args):
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = cli.main(list(args))
        return rc, out.getvalue() + err.getvalue()

    def test_the_core_refuses_a_resolved_home_with_the_self_fix(self):
        mine = touch(self.home / "Documents" / "thesis.docx", b"mine")
        EngineHomeCases.pointer(self.home, {"clients_root": "", "engine_home": str(self.home / "Documents")})
        rc, out = self.run_core("install", "--home", str(self.home), "--yes", "--quiet")
        self.assertEqual(rc, 2, out)
        self.assertIn(SELF_FIX, out)
        self.assertIn(SELF_FIX_AR, out)
        self.assertEqual(os.listdir(self.home / "Documents"), ["thesis.docx"])
        self.assertEqual(mine.read_bytes(), b"mine")
        # the clients folder saved in the pointer counts too
        EngineHomeCases.pointer(self.home, {"clients_root": str(self.home / "Media" / "Clients"),
                                            "engine_home": str(self.home / "Media")})
        rc, out = self.run_core("install", "--home", str(self.home), "--yes", "--quiet")
        self.assertEqual(rc, 2, out)
        self.assertIn("clients folder", out)
        # plan says the same; a chosen folder is placed by the Task 8 rules instead (Documents -> its subfolder)
        rc, out = self.run_core("plan", "--home", str(self.home))
        self.assertEqual(rc, 2, out)
        rc, out = self.run_core("plan", "--home", str(self.home), "--engine-home", str(self.home / "Documents"),
                                "--engine-home-chosen")
        self.assertEqual(rc, 0, out)


def _install_size_text(fx, plat: str, skip=("model", "launch"), git_missing=None) -> str:
    sy = system_module()
    gm = plat.startswith("win") if git_missing is None else git_missing
    return SIZE_EN.format(sy.format_gb(sy.install_size_gb(fx.components, plat, skip=skip, git_missing=gm)))


class _CountdownCases:
    """The same D-T1 cases for both shells: inst(home, *flags, env=) -> CompletedProcess, PLAT, flag(name)."""

    def keys_env(self, keys, **extra):
        return self.env(WNC_TEST_KEYS=keys, WNC_TEST_COUNTDOWN_S="0", **extra)

    def assert_no_question(self, out: str) -> None:
        for needle in QUESTION_NEEDLES:
            self.assertNotIn(needle, out)

    def test_the_default_run_asks_nothing_and_writes_the_same_state_as_yes(self):
        r = self.inst(self.home, "skip", env=self.keys_env("none"))  # a fake console; nobody presses a key
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn(_install_size_text(self.fx, self.PLAT), out)
        self.assertIn(SIZE_AR.split("(")[0].strip(), out)
        self.assertIn(COUNTDOWN_EN, out)
        self.assertIn(COUNTDOWN_AR, out)
        self.assert_no_question(out)
        default_state = comparable_state(self.paths.state_file, self.home)
        self.assertEqual(default_state["answers"]["mode"], "default")
        yes_home = self.tmp / "y" / ARABIC_HOME  # the same name: the same preflight facts
        r2 = self.inst(yes_home, "yes", "skip")
        out2 = r2.stdout + r2.stderr
        self.assertEqual(r2.returncode, 0, out2)
        self.assertNotIn("Press C", out2)  # -Yes: no countdown
        yes_paths = base.Paths.from_env(str(yes_home), env={})
        self.assertEqual(comparable_state(yes_paths.state_file, yes_home), default_state)

    def test_any_other_key_continues_at_once(self):
        r = self.inst(self.home, "dry", env=self.keys_env("x"))
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn(COUNTDOWN_EN, out)
        self.assert_no_question(out)

    def customise_answers(self, location: list) -> Path:
        clients = self.tmp / "My Clients"
        answers = self.tmp / "answers.txt"
        answers.write_text("\n".join(location + ["2", "en", str(clients) if self.PLAT.startswith("win")
                                                  else clients.as_posix()]) + "\n", encoding="utf-8", newline="\n")
        return answers

    def assert_customised(self, r) -> None:
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        for needle in QUESTION_NEEDLES:
            self.assertIn(needle, out)
        st = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        a = st["answers"]
        self.assertEqual((a["whisper_model"], a["language"], a["mode"]), ("large-v3-turbo", "en", "customise"), out)
        self.assertEqual(norm(a["clients_root"]), norm(self.tmp / "My Clients"))
        self.assertFalse((self.tmp / "My Clients").exists())

    def test_c_opens_the_customise_questions(self):
        answers = self.customise_answers(self.LOCATION_ENTER)
        r = self.inst(self.home, "skip", env=self.keys_env("C", WNC_TEST_ANSWERS=self.answers_path(answers)))
        self.assertIn(COUNTDOWN_EN, r.stdout + r.stderr)
        self.assert_customised(r)

    def test_the_customise_flag_opens_them_without_a_countdown(self):
        answers = self.customise_answers(self.LOCATION_ENTER)
        r = self.inst(self.home, "customise", "skip", env=self.env(WNC_TEST_ANSWERS=self.answers_path(answers)))
        self.assertNotIn("Press C", r.stdout + r.stderr)
        self.assert_customised(r)
        r = self.inst(self.tmp / "both", "customise", "yes", "dry")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("cannot be used together", r.stdout + r.stderr)

    def test_without_a_keyboard_there_is_no_countdown_and_no_wait(self):
        t0 = time.monotonic()
        r = self.inst(self.home, "skip")  # stdin redirected, no test hook: like -Yes
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertNotIn("Press C", out)
        self.assert_no_question(out)
        self.assertIn(_install_size_text(self.fx, self.PLAT), out)
        st = json.loads(self.paths.state_file.read_text(encoding="utf-8"))
        self.assertEqual(st["answers"]["mode"], "default")
        self.assertLess(time.monotonic() - t0, 300)

    def test_a_resolved_home_in_an_unsafe_place_is_refused_before_any_download(self):
        h = self.home
        mine = touch(h / "Documents" / "thesis.docx", b"mine")
        touch(h / "Work" / "Clinic" / "Dr X" / ".whynot-client", b"{}")
        big = h / "Footage"  # more than 5000 entries within 3 levels (and a marker deeper than that): too big to check
        big.mkdir()
        for i in range(5001):
            open(big / f"clip{i:05d}.mov", "wb").close()
        touch(big / "a" / "b" / "c" / "d" / ".whynot-client", b"{}")
        drive = Path(self.tmp.anchor)
        before = (drive / "state.json").exists(), (drive / "logs").exists()
        docs = h / "Documents"
        cases = [(docs, "Documents"), (h / "Work", "client folder"), (drive, "drive root"),
                 (big, "too big to check"),
                 # fix round 1: spelling variants of the same folder
                 (self.native(docs) + self.SEP, "Documents"), (self.native(h / "x") + self.SEP + ".." + self.SEP +
                                                               "Documents", "Documents")]
        if IS_WIN:  # NTFS ignores case (macOS: see the Darwin case of the guard)
            cases.append((self.native(docs).upper(), "Documents"))
        stand_in = self.tmp / "drive stand-in"  # (a link to a real drive root would be unsafe to clean up)
        stand_in.mkdir()
        if make_dir_link(h / "lnk", docs):  # fix round 1: a link itself, and a linked parent (real path compared)
            cases.append((h / "lnk", "link or mount point"))
        if make_dir_link(h / "eng", h):
            cases.append((h / "eng" / "Documents", "Documents"))
        if make_dir_link(h / "root", stand_in):
            cases.append((h / "root", "link or mount point"))
        for bad, needle in cases:
            with self.subTest(str(bad)):
                EngineHomeCases.pointer(h, {"clients_root": "", "engine_home": self.native(bad)})
                r = self.inst(h, "skip", env=self.keys_env("none"))  # a fake console: the guard comes first
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 2, out)
                self.assertIn(needle, out)
                self.assertIn(SELF_FIX, out)
                self.assertIn(SELF_FIX_AR, out)
                self.assertNotIn("Press C", out)  # refused before the countdown (no 10 s wait)
        self.assertEqual(self.srv.srv.hits, [])
        self.assertEqual(os.listdir(h / "Documents"), ["thesis.docx"])
        self.assertEqual(mine.read_bytes(), b"mine")
        self.assertEqual(sorted(os.listdir(h / "Work")), ["Clinic"])
        self.assertEqual(os.listdir(stand_in), [])
        self.assertEqual(((drive / "state.json").exists(), (drive / "logs").exists()), before)
        self.assertEqual([n for n in os.listdir(drive) if n.startswith(".wnc-write-test")], [])
        # a genuine home elsewhere, also reached through a link on the way, is used (dry run)
        if (h / "eng").exists():
            touch(h / "Engine" / "state.json", GENUINE_STATE)
            EngineHomeCases.pointer(h, {"clients_root": "", "engine_home": self.native(h / "eng" / "Engine")})
            r = self.inst(h, "yes", "dry")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_engine_home_naming_the_saved_home_is_guarded_too(self):
        # fix round 2 (the reviewer's repro): -EngineHome equal to the saved home is that home: refused before any
        # download, nothing written under Documents
        h = self.home
        docs = h / "Documents"
        mine = touch(docs / "thesis.docx", b"mine")
        EngineHomeCases.pointer(h, {"clients_root": "", "engine_home": self.native(docs)})
        for value in (self.native(docs), self.native(docs) + self.SEP):
            with self.subTest(value):
                r = self.inst(h, "yes", "skip", extra=(self.ENGINE_FLAG, value))
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 2, out)
                self.assertIn("Documents", out)
                self.assertIn(SELF_FIX, out)
        self.assertEqual(self.srv.srv.hits, [])
        self.assertEqual(os.listdir(docs), ["thesis.docx"])
        self.assertEqual(mine.read_bytes(), b"mine")

    def test_device_and_network_paths_are_refused_cleanly(self):
        h = self.home
        h.mkdir()
        for value, needle in self.device_paths():
            with self.subTest(value):
                EngineHomeCases.pointer(h, {"clients_root": "", "engine_home": value})
                r = self.inst(h, "yes", "skip")
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 2, out)  # never 3 (a PowerShell exception)
                self.assertIn(needle, out)
                self.assertIn(SELF_FIX, out)
        self.assertEqual(self.srv.srv.hits, [])

    def test_a_linked_default_home_installs_and_uninstalls_through_the_link(self):
        # Addendum F (owner 2026-10-13): ~/.whynot-cut as a junction / symlink to a folder on another drive
        target = self.tmp / "data drive" / "whynot-cut-home"
        target.mkdir(parents=True)
        self.home.mkdir()
        link = self.home / ".whynot-cut"
        if not make_dir_link(link, target):
            self.skipTest("cannot make a directory link here")
        r = self.inst(self.home, "yes", "skip")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        for name in ("current", "state.json", "bin", "runtimes"):
            self.assertTrue((target / name).exists(), (name, sorted(os.listdir(target)), out))
        self.assertTrue(base.is_link(link))
        mine = touch(target / "my notes.txt", b"mine")
        r = self.inst(self.home, "uninstall", "remove-engine", "yes")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        for _ in range(50):  # (the bootstrap deletes python/ and bin/ right after the core exits)
            if not (target / "bin").exists():
                break
            time.sleep(0.1)
        self.assertEqual(sorted(os.listdir(target)), ["my notes.txt"], out)
        self.assertEqual(mine.read_bytes(), b"mine")
        self.assertTrue(base.is_link(link), out)  # the link and its target folder stay
        self.assertTrue(target.is_dir())

    def test_a_linked_default_home_pointing_somewhere_unsafe_is_refused(self):
        # fix round 3 (CRITICAL): install AND uninstall refuse before any download or delete
        h = self.home
        link = h / ".whynot-cut"
        docs = h / "Documents"
        before_docs = make_repro_documents(docs)
        marked = h / "Shoots"
        touch(marked / "Dr X" / ".whynot-client", b"{}")
        before_marked = snapshot_tree(marked)
        cases = [(docs, "Documents", before_docs), (h, "your user folder", None), (marked, "client folder", before_marked)]
        for target, needle, before in cases:
            with self.subTest(str(target)):
                if not make_dir_link(link, target):
                    self.skipTest("cannot make a directory link here")
                self.addCleanup(drop_dir_link, link)
                try:
                    for flags in (("yes", "skip"), ("uninstall", "remove-engine", "yes")):
                        r = self.inst(h, *flags)
                        out = r.stdout + r.stderr
                        self.assertEqual(r.returncode, 2, (flags, out))
                        self.assertIn(needle, out)
                        self.assertIn("remove the link", out)
                        self.assertIn(SELF_FIX, out)
                        self.assertIn(SELF_FIX_AR, out)
                        if before is not None:
                            self.assertEqual(snapshot_tree(target), before, out)
                finally:
                    drop_dir_link(link)
        self.assertEqual(self.srv.srv.hits, [])
        self.assertEqual(snapshot_tree(docs), before_docs)
        self.assertEqual(sorted(os.listdir(h)), ["Documents", "Shoots"])
        # a link to the drive root itself: refused (dry run, so that nothing could ever be written there)
        drive = Path(self.tmp.anchor)
        if make_dir_link(link, drive):
            self.addCleanup(drop_dir_link, link)
            try:
                r = self.inst(h, "yes", "dry")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("drive root", r.stdout + r.stderr)
            finally:
                drop_dir_link(link)

    def test_the_deferred_delete_checks_a_linked_default_home_again(self):
        # fix round 3: even when the list is there, python/ and bin/ of a link to Documents are never deleted
        h = self.home
        docs = h / "Documents"
        before = make_repro_documents(docs)
        if not make_dir_link(h / ".whynot-cut", docs):
            self.skipTest("cannot make a directory link here")
        self.addCleanup(drop_dir_link, h / ".whynot-cut")
        listed = self.native(h / ".whynot-cut")
        (docs / DEFER_LIST).write_text(listed + self.SEP + "python\n" + listed + self.SEP + "bin\n", encoding="utf-8")
        before[DEFER_LIST] = (docs / DEFER_LIST).read_bytes()
        r = self.run_deferred(h)
        out = r.stdout + r.stderr
        self.assertIn("left alone", out)
        self.assertEqual(snapshot_tree(docs), before, out)

    def test_a_bad_countdown_hook_value_is_ignored(self):
        r = self.inst(self.home, "dry", env=self.env(WNC_TEST_KEYS="x", WNC_TEST_COUNTDOWN_S="soon"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(COUNTDOWN_EN, r.stdout + r.stderr)


@unittest.skipUnless(find_powershell(), "Windows PowerShell is not available")
class TestPowerShellCountdown(_CountdownCases, _ShellCase):
    PLAT = "win-x64"
    # Enter keeps the default; the Arabic sandbox home is warned about and asked once more: its path again keeps it
    env = TestPowerShellFrontEnd.env
    ps = TestPowerShellFrontEnd.ps
    front = TestPowerShellFrontEnd.front

    @property
    def LOCATION_ENTER(self):
        return ["", str(self.home / ".whynot-cut")]

    SEP = "\\"

    def answers_path(self, p: Path) -> str:
        return str(p)

    def native(self, p) -> str:
        return str(p)

    ENGINE_FLAG = "-EngineHome"

    def run_deferred(self, h: Path):
        names = ["Test-WncReparse", "Invoke-WncDeleteTree", "Invoke-WncDeferredDelete", "Get-WncResolvedHomeProblem",
                 "Get-WncPlaceProblem", "Get-WncNormPath", "Get-WncRealPath", "Get-WncLinkTarget",
                 "Get-WncKnownFolderList", "Test-WncWithin", "Find-WncMarkerScan", "Get-WncClientRootList",
                 "Read-WncJsonObject", "Get-WncMember", "ConvertTo-WncHomePath"]
        boot = INSTALLER / "core" / "bootstrap.ps1"
        body = ("$S = @{ Utf8 = (New-Object System.Text.UTF8Encoding $false) }\n"
                + "".join(shell_function(boot, n, True) for n in names)
                + "Invoke-WncDeferredDelete -Engine $env:WNC_T_ENGINE -UserHome $env:WNC_T_HOME "
                  "-Pointer (Join-Path $env:WNC_T_HOME '.whynot-cut\\plugin-options.json') -Sandbox $true\n")
        script = self.tmp / "deferred.ps1"
        script.write_text(body, encoding="utf-8-sig")
        return self.ps(script, env=self.env(WNC_T_ENGINE=str(h / ".whynot-cut"), WNC_T_HOME=str(h)))

    def device_paths(self) -> list:
        return [("\\\\?\\" + str(self.home / "Documents"), "Documents"),
                ("\\\\localhost\\C$\\Users\\x", "network share"), ("\\\\.\\pipe\\x", "network share"),
                ("\\\\?\\UNC\\server\\share\\x", "network share")]

    def inst(self, home: Path, *flags, env=None, extra=()):
        args = ["-Home", home]
        names = {"yes": ["-Yes"], "customise": ["-Customise"], "dry": ["-DryRun"], "skip": ["-Skip", "model,launch"],
                 "uninstall": ["-Uninstall"], "remove-engine": ["-RemoveEngine"]}
        for f in flags:
            args += names[f]
        return self.ps(self.front(), *args, *extra, env=env)

    def test_the_size_line_counts_git_only_when_it_is_missing(self):
        touch(self.home / "AppData" / "Local" / "WhyNotCut" / "git" / "bin" / "bash.exe", b"MZ bash")
        r = self.inst(self.home, "dry", "skip", env=self.keys_env("x"))
        self.assertIn(_install_size_text(self.fx, self.PLAT, git_missing=False), r.stdout + r.stderr)


@unittest.skipUnless(find_bash(), "bash is not available")
class TestBashCountdown(_CountdownCases, _ShellCase):
    PLAT = "mac-arm64"
    LOCATION_ENTER = [""]
    env = TestBashFrontEnd.env
    sh = TestBashFrontEnd.sh
    front = TestBashFrontEnd.front
    home_arg = TestBashFrontEnd.home_arg

    SEP = "/"

    def answers_path(self, p: Path) -> str:
        return p.as_posix()

    def native(self, p) -> str:
        return Path(p).as_posix() if not isinstance(p, str) else p.replace("\\", "/")

    ENGINE_FLAG = "--engine-home"

    def run_deferred(self, h: Path):
        boot = INSTALLER / "core" / "bootstrap.sh"
        names = ["norm_path", "within", "is_mount", "guard_norm", "real_path", "place_keys", "place_problem",
                 "resolved_home_problem", "client_roots", "home_path", "abs_path", "json_get", "exact_child",
                 "delete_deferred"]
        script = self.tmp / "deferred.sh"
        script.write_text("".join(shell_function(boot, n, False) for n in names)
                          + 'OS_NAME="$(uname -s)"; JSON_PY=""; HOME="$1"; ENGINE="$1/.whynot-cut"\n'
                          'POINTER="$1/.whynot-cut/plugin-options.json"\ndelete_deferred\n',
                          encoding="utf-8", newline="\n")
        r = subprocess.run([find_bash(), str(script), h.as_posix()], capture_output=True, env=self.env(), timeout=120)
        return subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                           r.stderr.decode("utf-8", "replace"))

    def device_paths(self) -> list:
        return [("//server/share/x", "network share")]

    def inst(self, home: Path, *flags, env=None, extra=()):
        args = ["--home", home.as_posix()]
        names = {"yes": ["--yes"], "customise": ["--customise"], "dry": ["--dry-run"],
                 "skip": ["--skip", "model,launch"], "uninstall": ["--uninstall"], "remove-engine": ["--remove-engine"]}
        for f in flags:
            args += names[f]
        return self.sh(self.front(), *args, *extra, env=env)

    def test_piped_without_a_terminal_has_no_countdown(self):
        zf = self.tmp / "WhyNotCut-3.0.0.zip"
        zsha = release_zip(self.fx, zf)
        r = self.sh("-s", "--", "--home", self.home_arg(), "--skip", "model,launch", "--source", zf.as_posix(),
                    "--source-sha256", zsha, script=(INSTALLER / "install.sh").read_bytes())
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertNotIn("Press C", out)
        self.assert_no_question(out)

    def test_the_countdown_reads_only_the_terminal(self):
        boot = INSTALLER / "core" / "bootstrap.sh"
        body = shell_function(boot, "read_key", ps=False)
        self.assertIn('read -r -s -n 1 -t "$1"', body)
        self.assertIn("</dev/tty", body)
        self.assertIn("read_key", shell_function(boot, "countdown", ps=False))
        # fix round 1: /dev/tty only when stdout or stderr is a terminal too, and only in the foreground
        kb = shell_function(boot, "has_keyboard", ps=False)
        self.assertIn("[ -t 1 ] || [ -t 2 ]", kb)
        self.assertIn("in_foreground", kb)
        self.assertIn("ps -o stat=", shell_function(boot, "in_foreground", ps=False))

    def test_the_guard_folds_case_on_macos(self):
        # fix round 1: APFS / HFS+ ignore case; the bash guard folds it on Darwin (run alone, OS_NAME=Darwin)
        boot = INSTALLER / "core" / "bootstrap.sh"
        funcs = "".join(shell_function(boot, n, ps=False) for n in (
            "norm_path", "within", "is_mount", "guard_norm", "real_path", "place_keys", "place_problem",
            "resolved_home_problem"))
        (self.home / "Documents").mkdir(parents=True)
        script = self.tmp / "guard.sh"
        script.write_text(funcs + 'OS_NAME="$2"; HOME="$(cygpath -u "$1" 2>/dev/null || printf %s "$1")"\n'
                          'CLIENT_ROOTS=""\nresolved_home_problem "$HOME/documents"\nprintf "WHY=%s\\n" "$WHY"\n',
                          encoding="utf-8", newline="\n")
        r = subprocess.run([find_bash(), str(script), str(self.home), "Darwin"], capture_output=True,
                           env=self.env(), timeout=60)
        out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
        self.assertIn("WHY=your Documents folder itself", out)


# --------------------------------------------------------------------------------------------- task 7: release stub
RELEASE = SK.parent / "tools" / "release.py"
LIVE_LOCK = FIXTURES / "live_lock.txt"


def run_release(*args):
    return subprocess.run([sys.executable, "-B", str(RELEASE), *[str(a) for a in args]], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL)


def placeholder_paths(obj) -> set:
    return {p for p, v in leaves(obj) if base.is_placeholder(v)}


class TestReleaseStub(unittest.TestCase):
    """tools/release.py components --check / --fill-artefacts, always on a temp COPY of components.json."""

    def setUp(self):
        self.real = COMPONENTS.read_bytes()
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.plugin = Path(self._td.name) / "plugin root"
        self.comp = self.plugin / "setup" / "components.json"
        self.comp.parent.mkdir(parents=True)
        self.comp.write_bytes(self.real)
        self.adobe = self.plugin / "adobe"
        self.adobe.mkdir()

    def tearDown(self):
        self.assertEqual(COMPONENTS.read_bytes(), self.real)  # the real file is only ever read

    def fill(self):
        return run_release("components", "--fill-artefacts", "--plugin", self.plugin)

    def changed_lines(self) -> list:
        old, new = self.real.decode("utf-8").split("\n"), self.comp.read_bytes().decode("utf-8").split("\n")
        self.assertEqual(len(old), len(new))
        return [(a.strip(), b.strip()) for a, b in zip(old, new) if a != b]

    def test_check_lists_the_placeholder_paths(self):
        r = run_release("components", "--check", "--components", self.comp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        listed = set(r.stdout.split())
        self.assertIn("bridge.cep.sha256", listed)
        self.assertEqual(listed, placeholder_paths(json.loads(self.real)))
        r = run_release("components", "--check", "--plugin", self.plugin)  # the plugin's own setup/components.json
        self.assertEqual((r.returncode, set(r.stdout.split())), (0, listed), r.stderr)
        r = run_release("components", "--check")  # default: this checkout's file, read only
        self.assertEqual((r.returncode, set(r.stdout.split())), (0, placeholder_paths(json.loads(self.real))))

    def test_fill_writes_the_zxp_sha256_and_name_and_nothing_else(self):
        zxp = self.adobe / "WhyNotCut-Bridge-3.0.0.zxp"
        zxp.write_bytes(b"PK fixture zxp")
        r = self.fill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = json.loads(self.comp.read_text(encoding="utf-8"))
        self.assertEqual(c["bridge"]["cep"]["zxp"], "adobe/WhyNotCut-Bridge-3.0.0.zxp")
        self.assertEqual(c["bridge"]["cep"]["sha256"], sha(b"PK fixture zxp"))
        self.assertEqual(placeholder_paths(c),
                         placeholder_paths(json.loads(self.real)) - {"bridge.cep.zxp", "bridge.cep.sha256"})
        # the formatting is kept: the same lines, only the two values changed, still one trailing LF
        self.assertEqual(self.changed_lines(), [
            ('"zxp": "<release>",', '"zxp": "adobe/WhyNotCut-Bridge-3.0.0.zxp",'),
            ('"sha256": "<release>",', f'"sha256": "{sha(b"PK fixture zxp")}",')])
        self.assertEqual(self.comp.read_bytes().endswith(b"\n"), self.real.endswith(b"\n"))
        # and the installer's adobe step finds it from the plugin root
        from wnc_installer import adobe
        ctx = make_ctx(Path(self._td.name) / "home", base.load_components(self.comp), self.plugin)
        self.assertEqual(adobe._artefact(ctx, "bridge.cep.zxp"), zxp)

    def test_the_zxp_sign_zxp_builds_is_pinned_and_installed_as_the_signed_bundle(self):
        """3.0 T6.3 Task 6: the ZXP tools/sign_zxp.py builds (here with its test fakes: no real ZXPSignCmd) lands in
        <plugin>/adobe under the name --fill-artefacts pins; the installer's adobe step extracts it, and the engine reads
        that as the signed bundle 3.0.0, file for file what cep_bundle.install_zxp makes of the same ZXP."""
        if str(SK.parent / "tools") not in sys.path:
            sys.path.insert(0, str(SK.parent / "tools"))
        import sign_zxp
        from lib import cep_bundle
        from test_sign_zxp import TEST_PIN, TOOL_BYTES, FakeStore, FakeZXPSignCmd
        tmp = Path(self._td.name)
        tool = tmp / "downloads" / "ZXPSignCmd.exe"
        tool.parent.mkdir()
        tool.write_bytes(TOOL_BYTES)
        store, runner, quiet = FakeStore(), FakeZXPSignCmd(), (lambda m: None)
        with mock.patch.dict(sign_zxp.PINS, {"test-x64": TEST_PIN}):
            sign_zxp.setup(src=tool, home=tmp / "signing", runner=runner, store=store, key="test-x64", log=quiet)
            built = sign_zxp.build(home=tmp / "signing", out_dir=self.adobe, runner=runner, store=store,
                                   key="test-x64", log=quiet)
        self.assertEqual([p.name for p in self.adobe.iterdir()], ["WhyNotCut-Bridge-3.0.0.zxp"])
        r = self.fill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = json.loads(self.comp.read_text(encoding="utf-8"))
        self.assertEqual((c["bridge"]["cep"]["zxp"], c["bridge"]["cep"]["sha256"]),
                         ("adobe/WhyNotCut-Bridge-3.0.0.zxp", built["sha256"]))
        ctx = make_ctx(tmp / "home", base.load_components(self.comp), self.plugin)
        res = system_module().step_adobe(ctx)
        self.assertEqual(res.status, "ok", res.detail)
        ext = Path(ctx.state.data["adobe"]["cep"]["path"])
        got = cep_bundle.installed(ext)
        self.assertEqual((got["id"], got["family"], got["version"], got["signed"]),
                         ("ai.thewhynot.cut.bridge", "bundle", "3.0.0", True))
        engine = cep_bundle.install_zxp(Path(built["zxp"]), tmp / "engine" / "cep" / cep_bundle.EXT_ID)["installed"]
        files = lambda root: {p.relative_to(root).as_posix(): sha(p.read_bytes())  # noqa: E731
                              for p in Path(root).rglob("*") if p.is_file()}
        self.assertEqual(files(engine["path"]), files(ext))

    def test_fill_both_panels_keeps_the_other_placeholders(self):
        (self.adobe / "WhyNotCut-Bridge-3.0.0.zxp").write_bytes(b"zxp")
        (self.adobe / "WhyNotCut-Premiere-3.0.0.ccx").write_bytes(b"ccx")
        r = self.fill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = json.loads(self.comp.read_text(encoding="utf-8"))
        self.assertEqual((c["bridge"]["uxp"]["ccx"], c["bridge"]["uxp"]["sha256"]),
                         ("adobe/WhyNotCut-Premiere-3.0.0.ccx", sha(b"ccx")))
        self.assertEqual(c["bridge"]["cep"]["sha256"], sha(b"zxp"))
        for still in ("bridge.cep.bundle", "bridge.uxp.version", "bridge.uxp.id", "marketplace.url"):
            self.assertTrue(base.is_placeholder(base.cget(c, still)), still)
        self.assertEqual(len(self.changed_lines()), 4)

    def test_a_rebuilt_artefact_is_filled_again(self):
        zxp = self.adobe / "WhyNotCut-Bridge-3.0.0.zxp"
        zxp.write_bytes(b"one")
        self.assertEqual(self.fill().returncode, 0)
        zxp.write_bytes(b"two")
        r = self.fill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(self.comp.read_text(encoding="utf-8"))["bridge"]["cep"]["sha256"], sha(b"two"))

    def test_no_artefacts_changes_nothing(self):
        r = self.fill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.comp.read_bytes(), self.real)

    def test_two_candidates_are_refused(self):
        (self.adobe / "a.zxp").write_bytes(b"a")
        (self.adobe / "b.zxp").write_bytes(b"b")
        r = self.fill()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("a.zxp", r.stderr)
        self.assertEqual(self.comp.read_bytes(), self.real)

    def test_the_docstring_hands_the_pipeline_to_the_executor_and_names_the_index(self):
        import ast
        doc = ast.get_docstring(ast.parse(RELEASE.read_text(encoding="utf-8")))
        for needle in ("T7.6", "executor", '"stable"', '"beta"', '"url"', '"sha256"', "release.index_url",
                       "--check", "--fill-artefacts", "stdlib"):
            self.assertIn(needle, doc)


# --------------------------------------------------------------------------------------------- task 7: static checks
PS1_FILES = sorted(INSTALLER.rglob("*.ps1"))
SH_FILES = sorted(INSTALLER.rglob("*.sh"))


class TestStaticChecks(unittest.TestCase):
    """Parsers always run when the shell exists; PSScriptAnalyzer (WHYNOTCUT_PSSA_PATH = its .psd1, or the PS module
    path) and shellcheck (WHYNOTCUT_SHELLCHECK, or PATH) are skipped cleanly when they are not on this machine."""

    def setUp(self):
        self._td = TempDir()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def test_the_one_liners_use_the_dl_host(self):
        # Addendum F: the scripts are served from dl.thewhynot.ai, never from the root site
        files = PS1_FILES + SH_FILES + [INSTALLER / "README.md", SK / "CHANGELOG.md"]
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("https://thewhynot.ai/install", text, f)
        for f in (INSTALLER / "install.ps1", INSTALLER / "install.sh", INSTALLER / "README.md"):
            self.assertIn("https://dl.thewhynot.ai/install.", f.read_text(encoding="utf-8"), f)

    def test_the_file_lists(self):
        self.assertEqual([p.name for p in PS1_FILES], ["bootstrap.ps1", "install.ps1"])
        self.assertEqual([p.name for p in SH_FILES], ["bootstrap.sh", "install.sh"])

    def ps(self, body: str, files: list):
        if not find_powershell():
            self.skipTest("Windows PowerShell is not available")
        script = self.tmp / "check.ps1"
        script.write_text(body, encoding="ascii")
        env = dict(os.environ, WNC_PS_FILES="|".join(str(f) for f in files))
        return subprocess.run([find_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", str(script)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=600, stdin=subprocess.DEVNULL)

    PARSE = ("$ErrorActionPreference = 'Stop'\n"
             "$files = $env:WNC_PS_FILES -split '\\|'\n"
             "foreach ($f in $files) {\n"
             "    $tokens = $null; $errors = $null\n"
             "    [void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$tokens, [ref]$errors)\n"
             "    foreach ($e in $errors) { Write-Output ('ERR {0}:{1}: {2}' -f $f, $e.Extent.StartLineNumber, "
             "$e.Message) }\n"
             "}\n"
             "Write-Output ('parsed ' + $files.Count)\n")

    def test_powershell_parses_every_ps1(self):
        r = self.ps(self.PARSE, PS1_FILES)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x for x in r.stdout.splitlines() if x.startswith("ERR")], [], r.stdout)
        self.assertIn(f"parsed {len(PS1_FILES)}", r.stdout.splitlines(), r.stdout + r.stderr)

    def test_the_readme_says_what_was_verified_and_what_was_not(self):
        text = (INSTALLER / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Verified / Not verified", text)
        verified, _, rest = text.partition("## Verified / Not verified")[2].partition("### Not verified")
        for needle in ("0.13.0", "3.12.15", "--no-bin --no-registry", "PortableGit", "WNC_TEST_PLATFORM",
                       "PowerShell 5.1"):
            self.assertIn(needle, verified)
        for needle in ("Mac", "JXA", "HKCU", "UPIA", "Claude Code CLI", "Phase 6", "Gate 7", "H10", "SAC"):
            self.assertIn(needle, rest)

    def test_the_parser_check_catches_a_broken_file(self):
        bad = self.tmp / "bad.ps1"
        bad.write_text("function Broken {\n  if ($x) {\n", encoding="ascii")
        r = self.ps(self.PARSE, [bad])
        self.assertIn(f"ERR {bad}:", r.stdout, r.stderr)

    def bash_n(self, path: Path):
        if not find_bash():
            self.skipTest("bash is not available")
        return subprocess.run([find_bash(), "-n", path.as_posix()], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, stdin=subprocess.DEVNULL)

    def test_bash_n_on_every_sh(self):
        for f in SH_FILES:
            r = self.bash_n(f)
            self.assertEqual((r.returncode, r.stderr), (0, ""), f.name)

    def test_bash_n_catches_a_broken_file(self):
        bad = self.tmp / "bad.sh"
        bad.write_bytes(b"#!/usr/bin/env bash\nif true; then\n  echo x\n")
        self.assertNotEqual(self.bash_n(bad).returncode, 0)

    def test_psscriptanalyzer_finds_no_errors(self):
        body = ("$p = $env:WHYNOTCUT_PSSA_PATH\n"
                "try {\n"
                "    if ($p) { Import-Module $p -ErrorAction Stop } else { Import-Module PSScriptAnalyzer -ErrorAction Stop }\n"
                "} catch { Write-Output ('NOPSSA ' + $_); exit 7 }\n"
                "$files = $env:WNC_PS_FILES -split '\\|'\n"
                "foreach ($f in $files) {\n"
                "    foreach ($d in @(Invoke-ScriptAnalyzer -Path $f -Severity Error, ParseError)) {\n"
                "        Write-Output ('ERR {0}:{1}: {2} {3}' -f $d.ScriptName, $d.Line, $d.RuleName, $d.Message)\n"
                "    }\n"
                "}\n"
                "Write-Output ('analyzed ' + $files.Count + ' with PSScriptAnalyzer ' + "
                "(Get-Module PSScriptAnalyzer).Version)\n")
        r = self.ps(body, PS1_FILES)
        if r.returncode == 7:
            self.skipTest("PSScriptAnalyzer is not importable (set WHYNOTCUT_PSSA_PATH to its .psd1)")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x for x in r.stdout.splitlines() if x.startswith("ERR")], [], r.stdout)
        self.assertIn(f"analyzed {len(PS1_FILES)} with PSScriptAnalyzer", r.stdout, r.stdout + r.stderr)

    def test_shellcheck_is_clean(self):
        sc = os.environ.get("WHYNOTCUT_SHELLCHECK") or shutil.which("shellcheck")
        if not sc or not Path(sc).is_file() and not shutil.which(sc):
            self.skipTest("shellcheck is not available (set WHYNOTCUT_SHELLCHECK to the executable)")
        r = subprocess.run([sc, "--shell=bash", *[str(f) for f in SH_FILES]], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --------------------------------------------------------------------------------------------- task 7: live smoke
def real_side_effects() -> dict:
    """Read-only: what a bare `uv python install` would leave in the REAL profile (installer.md: never)."""
    out = {"local_bin": sorted(p.name for p in (real_profile() / ".local" / "bin").glob("python3*"))}
    if IS_WIN:
        import winreg
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Python\Astral"))
            out["astral_key"] = True
        except OSError:
            out["astral_key"] = False
    return out


@unittest.skipUnless(os.environ.get("WNC_INSTALLER_LIVE") == "1", "live network smoke: set WNC_INSTALLER_LIVE=1")
class TestLiveSmoke(unittest.TestCase):
    """The real thing, once per release: uv from the PINNED components.json URL + sha256, `uv python install
    <pinned> --no-bin --no-registry`, `uv venv`, `uv pip sync --require-hashes` of tests/fixtures/installer/
    live_lock.txt (six, hashed), all through the core's runtime step, in a temp home with Arabic letters."""

    def test_real_uv_python_and_a_hashed_lock_build_a_runtime(self):
        try:
            plat = base.platform_id()
        except base.Unsupported as e:
            self.skipTest(str(e))
        real = base.load_components(COMPONENTS)
        before, side = live_snapshot(), real_side_effects()
        with TempDir() as d, mock.patch.dict(os.environ):
            os.environ.pop("WNC_TEST_UV", None)
            tmp = Path(d)
            plugin = tmp / "plugin root"
            rel = f"setup/locks/runtime-{plat}.lock"
            (plugin / rel).parent.mkdir(parents=True)
            shutil.copyfile(LIVE_LOCK, plugin / rel)
            comp = {"schema": 1, "uv": real["uv"], "runtime": {
                "python": real["runtime"]["python"], "index_url": None, "smoke": ["six"],
                "locks": {plat: {"file": rel, "id": base.PLACEHOLDER}}}}
            ctx = make_ctx(tmp / ARABIC_HOME, comp, plugin, plat)
            asset = comp["uv"]["assets"][plat]
            arc = base.download(asset["url"], asset["sha256"], ctx.paths.downloads_dir, ctx.log)
            uv = ctx.paths.bin_dir / ("uv.exe" if plat.startswith("win") else "uv")
            base.extract(arc, ctx.paths.bin_dir, {asset["member"]: uv.name})
            ver = subprocess.run([str(uv), "--version"], capture_output=True, text=True, timeout=60,
                                 env=ctx.paths.child_env(), stdin=subprocess.DEVNULL)
            self.assertTrue(ver.stdout.startswith(f"uv {real['uv']['version']}"), ver.stdout + ver.stderr)

            res = runtime_module().step_runtime(ctx)
            log = (ctx.paths.logs_dir / "install-test.log").read_text(encoding="utf-8")
            self.assertEqual(res.status, "ok", res.detail + "\n" + log[-4000:])
            self.assertIn("--no-bin --no-registry", log)
            rid = ctx.paths.current_file.read_text(encoding="utf-8").strip()
            self.assertEqual(rid, "r-" + sha(LIVE_LOCK.read_bytes())[:12])
            py = runtime_module().runtime_python(ctx.paths, rid, plat)
            probe = subprocess.run([str(py), "-s", "-I", "-c",
                                    "import json, platform, sys, six; print(json.dumps([six.__version__, "
                                    "platform.python_version(), sys.base_prefix]))"],
                                   capture_output=True, text=True, encoding="utf-8", timeout=120,
                                   env=ctx.paths.child_env(), stdin=subprocess.DEVNULL)
            self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
            six_ver, py_ver, base_prefix = json.loads(probe.stdout.strip().splitlines()[-1])
            self.assertEqual((six_ver, py_ver), ("1.17.0", real["runtime"]["python"]))
            self.assertTrue(Path(base_prefix).resolve().is_relative_to(ctx.paths.python_dir.resolve()), base_prefix)
            self.assertTrue((ctx.paths.runtimes_dir / rid / runtime_module().STAMP).is_file())
        self.assertEqual(live_snapshot(), before)
        self.assertEqual(real_side_effects(), side)  # no ~/.local/bin/python3.12(.exe), no HKCU Python\Astral key


if __name__ == "__main__":
    unittest.main()
