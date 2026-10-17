"""Everything that differs between macOS and Windows lives here (stdlib only, importable by hooks too).

  * engine home (venv, Whisper models, Premiere queue) and its legacy locations
  * venv interpreter layout (bin/python vs Scripts/python.exe)
  * font folders, Adobe app discovery, CEP extension folder, PlayerDebugMode
  * Git-Bash style paths (/d/Work/...) that the Bash tool uses on Windows
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
OS_NAME = "windows" if IS_WIN else "macos" if IS_MAC else "linux"

HOME_NAME = ".whynot-cut"
LEGACY_HOMES = (".reel-editor", ".dr-nahla-editor")   # earlier releases (reel-editor 1.x, the original skill)
HOME_ENV = ("WHYNOT_HOME", "CLAUDE_PLUGIN_OPTION_ENGINE_HOME", "REEL_HOME", "CLAUDE_PLUGIN_OPTION_REEL_HOME", "NH_ENV_DIR")
CLIENTS_ENV = ("WHYNOT_CLIENTS_ROOT", "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT", "REEL_CLIENTS_ROOT")
OPTIONS_FILE = "plugin-options.json"          # ~/.whynot-cut/plugin-options.json, written by the SessionStart hook
PLUGIN_ID = "whynot-cut@thewhynot-ai"         # Claude Code's key for this plugin in settings.json pluginConfigs


def options_file() -> Path:
    """The SessionStart hook's record of the plugin options (3.0 T1.9). PowerShell commands never receive a path-valued
    variable from CLAUDE_ENV_FILE, so the engine and both wrappers read the options from here. Its place is fixed
    (~/.whynot-cut, also when engine_home points elsewhere); WHYNOT_OPTIONS_FILE overrides it."""
    return Path(os.environ.get("WHYNOT_OPTIONS_FILE") or Path.home() / HOME_NAME / OPTIONS_FILE).expanduser()


def _claude_settings_options() -> dict:
    """This plugin's options as Claude Code stores them: settings.json pluginConfigs["whynot-cut@<marketplace>"]
    .options — whynot-cut@thewhynot-ai when it has an options object, else the first other whynot-cut@* entry (file
    order) that has one."""
    cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    try:
        configs = json.loads((cfg / "settings.json").read_text(encoding="utf-8")).get("pluginConfigs") or {}
        keys = [PLUGIN_ID] + [k for k in configs if k.startswith("whynot-cut@") and k != PLUGIN_ID]
        return next((c["options"] for c in (configs.get(k) for k in keys)
                     if isinstance(c, dict) and isinstance(c.get("options"), dict)), {})
    except (OSError, ValueError, AttributeError):
        return {}


def saved_options() -> dict:
    """{engine_home, clients_root} saved for the plugin. Values are strings, "" when unset.

    Source: the pointer file when it is valid — a JSON object with an "engine_home" string, "" meaning "not set" —
    else Claude Code's settings.json (_claude_settings_options). bin/reel and bin/reel.cmd apply the same rules to the
    engine home (valid pointer = an "engine_home" string plus the closing brace; same entry preference in
    settings.json). Known differences, all outside what Claude Code and the SessionStart hook write: the wrappers read
    settings.json line by line, so a hand-minified settings.json is read only here; reel.cmd also reads the pointer
    line by line (the hook writes one key per line), so a hand-minified pointer counts as invalid there."""
    try:
        d = json.loads(options_file().read_text(encoding="utf-8"))
        if not isinstance(d, dict) or not isinstance(d.get("engine_home"), str):
            raise ValueError
    except (OSError, ValueError):
        d = _claude_settings_options()
    return {k: d.get(k) if isinstance(d.get(k), str) else "" for k in ("engine_home", "clients_root")}


USER_OPTION_KEYS = ("language", "approval", "whisper_model", "magnific_budget_credits")   # userConfig keys the engine reads
SECRET_OPTION_KEYS = ("magnific_api_key",)    # sensitive userConfig keys: environment only, never copied anywhere
USER_OPTION_ENV = tuple("CLAUDE_PLUGIN_OPTION_" + k.upper() for k in USER_OPTION_KEYS + SECRET_OPTION_KEYS)


def _option_text(v) -> str:
    """A plugin option as text: strings and numbers count, anything else (bool, list, null) and blanks are "" (unset)."""
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        return ""
    return str(v).strip()


def plugin_options(keys=USER_OPTION_KEYS) -> dict:
    """The non-secret userConfig values (language, approval, whisper_model, magnific_budget_credits) as text, "" when
    unset (3.0 T3.5). Per key: the CLAUDE_PLUGIN_OPTION_<KEY> variable (hooks and MCP servers get it), else the
    pointer file the SessionStart hook writes, else Claude Code's settings.json pluginConfigs (the same order as
    saved_options). Defaults are not applied here: the engine's own defaults sit below this layer."""
    try:
        ptr = json.loads(options_file().read_text(encoding="utf-8"))
        ptr = ptr if isinstance(ptr, dict) else {}
    except (OSError, ValueError):
        ptr = {}
    cfg = None
    out = {}
    for k in keys:
        v = _option_text(os.environ.get("CLAUDE_PLUGIN_OPTION_" + k.upper())) or _option_text(ptr.get(k))
        if not v:
            cfg = _claude_settings_options() if cfg is None else cfg
            v = _option_text(cfg.get(k))
        out[k] = v
    return out


def secret_option(key: str) -> str:
    """A sensitive userConfig value (magnific_api_key). Claude Code keeps it in the system keychain and gives it only to
    the processes the plugin starts, as CLAUDE_PLUGIN_OPTION_<KEY>; so the environment is the only source here. The
    engine never writes it to a file, the pointer, a log or a report: ask for it at the moment of use."""
    return os.environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "")


def _saved_path(v: str) -> Path:
    return Path(native_path(v)).expanduser()


def engine_home() -> Path:
    """Machine state lives OUTSIDE the plugin (the plugin folder is replaced on every update).
    Order: explicit setting (env) > saved plugin option (pointer file, else ~/.claude/settings.json) > ~/.whynot-cut
    with an engine (a runtime `current` file or the legacy venv/) > an existing legacy home (keeps the 3 GB of models; dropped in 4.0) > ~/.whynot-cut.
    bin/reel and bin/reel.cmd resolve the same order."""
    for k in HOME_ENV:
        if os.environ.get(k):
            # absolute (Gate 2 minor): a relative value would follow the current folder, e.g. into a client folder
            return Path(os.path.abspath(Path(os.environ[k]).expanduser()))
    saved = saved_options()["engine_home"]
    if saved:
        return _saved_path(saved)
    home = Path.home()
    new = home / HOME_NAME
    if (new / "venv").exists() or (new / CURRENT_FILE).is_file():   # ~/.whynot-cut alone may only hold the pointer
        return new
    for old in LEGACY_HOMES:
        if (home / old / "venv").exists():
            return home / old
    return new


def clients_root_setting() -> Path | None:
    """The clients folder from the plugin option: env first, then the saved option (pointer file / settings.json)."""
    for k in CLIENTS_ENV:
        if os.environ.get(k):
            return Path(os.environ[k]).expanduser()
    saved = saved_options()["clients_root"]
    return _saved_path(saved) if saved else None


# --------------------------------------------------------------------------- engine runtime (3.0 T2.1)
# <home>/runtimes/<id>/ is a venv built from the platform's hash lock (no system or user site); <home>/current is a
# one-line text file naming the runtime in use (never a symlink: Windows-safe). The legacy <home>/venv/ is the fallback
# when no runtime is current. bin/reel, bin/reel.cmd and tools/test.sh resolve the same order; lib/runtime.py builds
# and checks runtimes.
RUNTIMES_DIR = "runtimes"
CURRENT_FILE = "current"
_RUNTIME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def env_python(env_dir: Path) -> Path:
    """The interpreter of a venv-style folder: Scripts/python.exe on Windows, bin/python elsewhere."""
    return env_dir / "Scripts" / "python.exe" if IS_WIN else env_dir / "bin" / "python"


def current_runtime_id(home: Path | None = None) -> str | None:
    """The id in <home>/current (whitespace stripped), or None when the file is missing, empty or not a plain id."""
    try:
        rid = ((home or engine_home()) / CURRENT_FILE).read_text(encoding="utf-8-sig").strip()
    except (OSError, ValueError):
        return None
    return rid if _RUNTIME_ID.match(rid) and ".." not in rid else None


def runtime_usable(env_dir: Path) -> bool:
    """Can this venv-style folder's interpreter start? Checked without starting it (the wrappers and the hook runner
    apply the same rule with shell builtins): the interpreter file, a pyvenv.cfg, and the base Python its `home`
    names (python.exe on Windows, python3 / python elsewhere). A runtime whose base Python under <home>/python was
    removed fails this, so the wrappers fall back and `reel setup` can rebuild it."""
    try:
        if not env_python(env_dir).is_file() or env_python(env_dir).stat().st_size == 0:
            return False
    except OSError:
        return False
    try:
        cfg = (env_dir / "pyvenv.cfg").read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return False
    base = next((ln.split("=", 1)[1].strip() for ln in cfg.splitlines()
                 if "=" in ln and ln.split("=", 1)[0].strip().lower() == "home"), "")
    if not base:
        return False
    b = Path(base)
    return (b / "python.exe").is_file() if IS_WIN else any((b / n).is_file() for n in ("python3", "python"))


def engine_runtime(home: Path | None = None) -> dict:
    """The engine interpreter, in the wrappers' order: the current runtime when it can start (runtime_usable), else
    the legacy venv. {kind: "runtime" | "venv" | None, id, dir, python, broken} (python is None when neither exists;
    broken = the id of a current runtime that cannot start, else None)."""
    home = home or engine_home()
    rid = current_runtime_id(home)
    broken = None
    if rid:
        d = home / RUNTIMES_DIR / rid
        if runtime_usable(d):
            return {"kind": "runtime", "id": rid, "dir": d, "python": env_python(d), "broken": None}
        broken = rid if d.exists() else None
    d = home / "venv"
    if env_python(d).is_file():
        return {"kind": "venv", "id": None, "dir": d, "python": env_python(d), "broken": broken}
    return {"kind": None, "id": None, "dir": None, "python": None, "broken": broken}


def venv_python(home: Path | None = None) -> Path:
    """The engine interpreter: the current runtime's python when there is one, else the legacy venv's (which may not
    exist: callers check). The name is kept for the hooks and older callers."""
    home = home or engine_home()
    rt = engine_runtime(home)
    return rt["python"] if rt["kind"] == "runtime" else env_python(home / "venv")


# --------------------------------------------------------------------------- ffmpeg (3.0 T2.1, installer contract)
def _plugin_components() -> dict:
    try:
        return json.loads((Path(__file__).resolve().parents[3] / "setup" / "components.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def engine_ffmpeg(home: Path | None = None, tool: str = "ffmpeg") -> Path | None:
    """The pinned ffmpeg (or ffprobe) the installer put in the engine home: state.json `ffmpeg.path` (the ffmpeg
    binary or its folder), else <home>/ffmpeg/<components.json ffmpeg.version>/. None when neither is there."""
    home = home or engine_home()
    exe = tool + (".exe" if IS_WIN else "")
    try:
        p = (json.loads((home / "state.json").read_text(encoding="utf-8")).get("ffmpeg") or {}).get("path")
    except (OSError, ValueError, AttributeError):
        p = None
    cands = []
    if isinstance(p, str) and p:
        p = Path(native_path(p)).expanduser()
        cands.append(p / exe if p.is_dir() else p.with_name(exe))
    ver = (_plugin_components().get("ffmpeg") or {}).get("version")
    if isinstance(ver, str) and ver and "/" not in ver and "\\" not in ver:
        cands.append(home / "ffmpeg" / ver / exe)
    return next((c for c in cands if c.is_file()), None)


# --------------------------------------------------------------------------- paths
_MSYS = re.compile(r"^/([a-zA-Z])(/|$)")


def native_path(s: str) -> str:
    """On Windows, turn a Git-Bash path (/d/Work/x, /c/Users) into D:/Work/x. Elsewhere unchanged."""
    if IS_WIN and s:
        m = _MSYS.match(s)
        if m:
            return f"{m.group(1).upper()}:/{s[3:]}"
        if s.startswith("~"):
            return str(Path(s).expanduser())
    return s


# --------------------------------------------------------------------------- fonts
def font_dirs(system: str | None = None, env=None, home: Path | None = None) -> list[Path]:
    """The installed-font folders (lib/fonts.py reads them recursively), including the Adobe Fonts (Creative Cloud)
    livetype folder, whose files have obfuscated names. system ("windows" | "darwin" | "linux"), env and home are
    injectable for tests (default: this machine)."""
    system = system or ("windows" if IS_WIN else "darwin" if IS_MAC else "linux")
    env = os.environ if env is None else env
    home = Path(home) if home else Path.home()
    if system == "windows":
        dirs = [Path(env.get("WINDIR", r"C:\Windows")) / "Fonts"]
        if env.get("LOCALAPPDATA"):
            dirs.append(Path(env["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts")
        if env.get("APPDATA"):
            dirs.append(Path(env["APPDATA"]) / "Adobe" / "CoreSync" / "plugins" / "livetype")
        return dirs
    if system == "darwin":
        return [home / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
                home / "Library/Application Support/Adobe/CoreSync/plugins/livetype"]
    return [home / ".local/share/fonts", home / ".fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]


FONT_DIRS_ENV = "WHYNOT_FONT_DIRS"
_font_dirs = font_dirs


def font_search_dirs() -> list[Path]:
    """The folders font discovery (lib/fonts.py) reads: font_dirs(), or the folders WHYNOT_FONT_DIRS names
    (os.pathsep-separated; the test sandbox, tests/_isolation.py, points it at an empty folder so no test reads the
    machine's fonts). The variable is honoured only inside the test sandbox (WHYNOT_TEST_SANDBOX set); anywhere else
    it is ignored, so a stray or empty value can never hide the machine's fonts. A test that replaced font_dirs
    (mock.patch) still gets its own folders."""
    v = os.environ.get(FONT_DIRS_ENV) if os.environ.get(SANDBOX_ENV) else None
    if v is None or font_dirs is not _font_dirs:
        return font_dirs()
    return [Path(p) for p in v.split(os.pathsep) if p]


def font_dirs_stamp(dirs: list[Path] | None = None) -> tuple:
    """Identity of the font folders' contents: (folder, mtime) of each folder and its direct sub-folders. A font
    installed or removed changes it, so caches keyed on it stay right in a long-lived process (3.0 T2.17)."""
    out = []
    for d in (font_dirs() if dirs is None else dirs):
        try:
            out.append((str(d), d.stat().st_mtime_ns))
            with os.scandir(d) as it:          # closed also when a stat() raises
                out += [(e.path, e.stat().st_mtime_ns) for e in it if e.is_dir()]
        except OSError:
            out.append((str(d), None))
    return tuple(out)


def font_install_hint() -> str:
    if IS_WIN:
        return "right-click each font file > Install (or 'Install for all users')"
    if IS_MAC:
        return "double-click each font file > Install Font"
    return "copy the font files to ~/.local/share/fonts and run fc-cache -f"


# --------------------------------------------------------------------------- Adobe apps (3.0 T2.11)
# ONE place finds Adobe apps; every caller (doctor, setup, discover, After Effects / Photoshop runners, aerender,
# motion) asks here. Windows: registry (HKLM\SOFTWARE\Adobe\<app>\<version>), App Paths, then the Program Files
# scan. macOS: Spotlight (mdfind, by bundle id), then /Applications and ~/Applications. A "(Beta)" build is found but
# never preferred to a release. The newest is picked deterministically: release before beta, then year, then version.
# Overrides: WHYNOT_PREMIERE_APP, WHYNOT_AE_APP (the app: .app / .exe / its folder), WHYNOT_AERENDER (the executable);
# a wrong one is Guidance naming the variable. The registry reader, the file-version reader and the mdfind runner are
# injectable (AdobeSources), so tests never read the real registry. `version` is the app's own (the exe's file version
# on Windows, CFBundleShortVersionString on macOS). The registry KEY name is not a version (Photoshop 2026 is
# "200.0", Premiere 26.5 is "26.0"), so it is kept apart as `reg_version` and only ranks an install whose file
# version cannot be read; `version` is then None (unknown), never a wrong number.
_ADOBE = {
    # key: label, folder prefix, Windows exe relative to the app folder, mdfind bundle ids, HKLM keys, App Paths exe,
    # override variable, year_base (marketing year = base + major version: Premiere 26.5 = 2026, Photoshop 27 = 2026)
    "premiere": dict(label="Premiere Pro", prefix="Adobe Premiere Pro", win_exe="Adobe Premiere Pro.exe",
                     mac_ids=("com.adobe.PremierePro*",),
                     reg=("SOFTWARE\\Adobe\\Premiere Pro", "SOFTWARE\\Adobe\\Adobe Premiere Pro"),
                     app_path="Adobe Premiere Pro.exe", override="WHYNOT_PREMIERE_APP", year_base=2000),
    "after_effects": dict(label="After Effects", prefix="Adobe After Effects", win_exe="Support Files/AfterFX.exe",
                          mac_ids=("com.adobe.AfterEffects*",),
                          reg=("SOFTWARE\\Adobe\\After Effects", "SOFTWARE\\Adobe\\Adobe After Effects"),
                          app_path="AfterFX.exe", override="WHYNOT_AE_APP", year_base=2000),
    "photoshop": dict(label="Photoshop", prefix="Adobe Photoshop", win_exe="Photoshop.exe",
                      mac_ids=("com.adobe.Photoshop*",),
                      reg=("SOFTWARE\\Adobe\\Photoshop", "SOFTWARE\\Adobe\\Adobe Photoshop"),
                      app_path="Photoshop.exe", override=None, year_base=1999),
    "media_encoder": dict(label="Media Encoder", prefix="Adobe Media Encoder", win_exe="Adobe Media Encoder.exe",
                          mac_ids=("com.adobe.ame.application*",),
                          reg=("SOFTWARE\\Adobe\\Adobe Media Encoder", "SOFTWARE\\Adobe\\Media Encoder"),
                          app_path="Adobe Media Encoder.exe", override=None, year_base=2000),
}
AERENDER_ENV = "WHYNOT_AERENDER"
APP_PATHS_KEY = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"
# registry values that hold the install folder (Photoshop, After Effects), or a folder at most two levels below it
# (Premiere Pro 26 has no InstallPath: only its presets and plug-in folders)
_REG_FOLDER_VALUES = ("installpath", "installdir", "applicationpath", "sequencepresetspath",
                      "sequencepreviewpresetspath", "plugininstallpath", "pluginpath")


def _program_dirs() -> list[Path]:
    out = []
    for k in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        v = os.environ.get(k)
        if v and Path(v) not in out:
            out.append(Path(v))
    return out or [Path(r"C:\Program Files")]


def _year(name: str) -> int:
    m = re.search(r"(20\d\d)", name)
    return int(m.group(1)) if m else 0


def _vtuple(v) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def _guidance(error: str, how: str, where: str | None = None):
    """errors.Guidance. plat is also imported as a top-level module (hooks, setup_env), where lib/ is on sys.path."""
    try:
        from .errors import Guidance
    except ImportError:
        from errors import Guidance
    return Guidance(error, how, where)


class WinRegistry:
    """HKLM, read-only, the 64-bit view first and then the 32-bit one. A missing key (or no winreg: macOS) is empty."""

    def _views(self, path: str):
        try:
            import winreg
        except ImportError:
            return
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with key:
                yield winreg, key

    def subkeys(self, path: str) -> list[str]:
        out: list[str] = []
        for winreg, key in self._views(path):
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                if name not in out:
                    out.append(name)
        return out

    def values(self, path: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for winreg, key in self._views(path):
            i = 0
            while True:
                try:
                    name, val, _t = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if isinstance(val, str):
                    out.setdefault(name, os.path.expandvars(val))
        return out


def _fmt_version(parts) -> str | None:
    """(26, 5, 2, 5) -> "26.5.2.5"; trailing zero parts go ("26.5.0.0" -> "26.5"); all zero -> None."""
    parts = [int(x) for x in parts]
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return ".".join(map(str, parts)) if any(parts) else None


def _win_file_version(path) -> str | None:
    """The exe's own version (VS_FIXEDFILEINFO: the file version, else the product version when that one is empty),
    read through version.dll. None when the file has no version resource or this is not Windows. Never raises."""
    try:
        import ctypes
        from ctypes import wintypes
        dll = ctypes.WinDLL("version", use_last_error=True)
        dll.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        dll.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        dll.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        dll.GetFileVersionInfoW.restype = wintypes.BOOL
        dll.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(wintypes.UINT)]
        dll.VerQueryValueW.restype = wintypes.BOOL
        size = dll.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not dll.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not dll.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)) or length.value < 24:
            return None

        class _Fixed(ctypes.Structure):
            _fields_ = [(n, wintypes.DWORD) for n in ("sig", "struc", "fvms", "fvls", "pvms", "pvls")]
        fi = ctypes.cast(ptr, ctypes.POINTER(_Fixed)).contents
        if fi.sig != 0xFEEF04BD:
            return None
        for ms, ls in ((fi.fvms, fi.fvls), (fi.pvms, fi.pvls)):
            v = _fmt_version((ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF))
            if v:
                return v
    except Exception:  # noqa: BLE001  (no dll, odd file, locked: the version is only for ranking and the report)
        pass
    return None


_MDFIND_TTL = 30.0
_MDFIND_CACHE: dict[str, tuple[float, list[str]]] = {}


def _run_mdfind(query: str) -> list[str]:
    """Spotlight, cached for 30 s per process: doctor / setup / discover ask for several apps in one command, and a
    stalled Spotlight would otherwise cost 15 s every time."""
    import time
    hit = _MDFIND_CACHE.get(query)
    if hit and time.monotonic() - hit[0] < _MDFIND_TTL:
        return list(hit[1])
    try:
        r = subprocess.run(["mdfind", query], capture_output=True, text=True, timeout=15)
        lines = r.stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        lines = []                                    # a failure is cached too: no second 15 s wait
    _MDFIND_CACHE[query] = (time.monotonic(), lines)
    return list(lines)


class AdobeSources:
    """Where discovery looks. Each part defaults to the real machine, read when asked (never at import); tests pass
    fakes: env (a mapping), registry (.subkeys(path) / .values(path)), mdfind (query -> [paths]), os_name
    ("windows" | "macos" | "linux"), program_dirs, mac_app_dirs, file_version (exe path -> "26.5.2.5" | None)."""

    def __init__(self, env=None, registry=None, mdfind=None, os_name=None, program_dirs=None, mac_app_dirs=None,
                 file_version=None):
        self._env, self._registry, self._mdfind, self._os = env, registry, mdfind, os_name
        self._program_dirs, self._mac_app_dirs = program_dirs, mac_app_dirs
        self._file_version = file_version

    def file_version(self, exe) -> str | None:
        """The exe's own version (Windows). None when it cannot be read; never raises."""
        try:
            if self._file_version is not None:
                v = self._file_version(str(exe))
            else:
                v = _win_file_version(exe) if self.os_name == "windows" and IS_WIN else None
            return str(v) if v else None
        except Exception:  # noqa: BLE001
            return None

    @property
    def env(self):
        return os.environ if self._env is None else self._env

    @property
    def os_name(self) -> str:
        return self._os or ("windows" if IS_WIN else "macos" if IS_MAC else "linux")

    @property
    def registry(self):
        return WinRegistry() if self._registry is None else self._registry

    @property
    def program_dirs(self) -> list[Path]:
        return _program_dirs() if self._program_dirs is None else [Path(d) for d in self._program_dirs]

    @property
    def mac_app_dirs(self) -> list[Path]:
        if self._mac_app_dirs is not None:
            return [Path(d) for d in self._mac_app_dirs]
        return [Path("/Applications"), Path.home() / "Applications"]

    def mdfind(self, query: str) -> list[str]:
        try:
            return list((self._mdfind or _run_mdfind)(query))
        except (OSError, subprocess.SubprocessError):
            return []


def _app_record(key: str, name: str, folder, exe, source: str, version=None, reg_version=None) -> dict:
    return {"key": key, "name": name, "year": _year(name) or _year(Path(folder).name), "version": version,
            "reg_version": reg_version, "beta": "beta" in name.lower() or "beta" in Path(folder).name.lower(),
            "folder": str(folder), "exe": str(exe), "source": source, "sources": [source]}


def _win_app_at(key: str, path) -> tuple[Path, Path] | None:
    """(app folder, exe) when the app is at `path` or at most two folders above it (a presets folder, the exe itself)."""
    rel = Path(_ADOBE[key]["win_exe"])
    p = Path(str(path).strip().strip('"'))
    if p.suffix.lower() == ".exe":
        p = p.parent
    for d in (p, p.parent, p.parent.parent):
        if (d / rel).is_file():
            return d, d / rel
        if rel.parent != Path(".") and (d / rel.name).is_file():          # AfterFX.exe sits in "Support Files"
            return d.parent, d / rel.name
    return None


def _win_candidates(key: str, src: AdobeSources) -> list[dict]:
    spec, reg, out = _ADOBE[key], src.registry, []
    for base in spec["reg"]:
        for ver in reg.subkeys(base):
            if not ver[:1].isdigit():                                       # "CurrentVersion"
                continue
            vals = {k.lower(): v for k, v in reg.values(f"{base}\\{ver}").items()}
            for name in _REG_FOLDER_VALUES:
                hit = _win_app_at(key, vals[name]) if vals.get(name) else None
                if hit:
                    out.append(_app_record(key, hit[0].name, hit[0], hit[1], "registry", reg_version=ver))
                    break
    vals = reg.values(APP_PATHS_KEY + spec["app_path"])
    for raw in (vals.get(""), vals.get("Path")):
        hit = _win_app_at(key, raw) if raw else None
        if hit:
            out.append(_app_record(key, hit[0].name, hit[0], hit[1], "app-paths"))
            break
    for base in src.program_dirs:
        adobe = base / "Adobe"
        for folder in sorted(adobe.glob(spec["prefix"] + "*")) if adobe.is_dir() else []:
            hit = _win_app_at(key, folder)
            if hit:
                out.append(_app_record(key, hit[0].name, hit[0], hit[1], "scan"))
    return out


def _mac_ok(app: Path, prefix: str) -> bool:
    parts = [x.lower() for x in app.parts[:-1]]
    return (app.suffix == ".app" and app.name.startswith(prefix) and "Render" not in app.name
            and "Helper" not in app.name and not any(x.endswith(".app") for x in parts)
            and ".trash" not in parts and "backups.backupdb" not in parts and app.is_dir())


def _mac_version(app: Path) -> str | None:
    try:
        import plistlib
        with open(app / "Contents" / "Info.plist", "rb") as f:
            v = plistlib.load(f).get("CFBundleShortVersionString")
        return str(v) if v else None
    except Exception:  # noqa: BLE001  (no plist, binary garbage: the version is only for ranking and the report)
        return None


def _mac_record(key: str, app: Path, source: str) -> dict:
    prefix = _ADOBE[key]["prefix"]
    folder = app.parent if app.parent.name.startswith(prefix) else app
    return _app_record(key, app.stem, folder, app, source, _mac_version(app))


def _mac_candidates(key: str, src: AdobeSources) -> list[dict]:
    spec, out = _ADOBE[key], []
    for bid in spec["mac_ids"]:
        for line in src.mdfind(f"kMDItemCFBundleIdentifier == '{bid}'"):
            app = Path(line.strip())
            if line.strip() and _mac_ok(app, spec["prefix"]):
                out.append(_mac_record(key, app, "mdfind"))
    for base in src.mac_app_dirs:
        for folder in sorted(base.glob(spec["prefix"] + "*")) if base.is_dir() else []:
            apps = [folder] if folder.suffix == ".app" else sorted(folder.glob(spec["prefix"] + "*.app"))
            out += [_mac_record(key, a, "scan") for a in apps if _mac_ok(a, spec["prefix"])]
    return out


def _override_app(key: str, src: AdobeSources) -> dict | None:
    spec = _ADOBE[key]
    var = spec["override"]
    raw = str(src.env.get(var) or "").strip().strip('"') if var else ""
    if not raw:
        return None
    p = Path(raw).expanduser()
    what = "the .app bundle" if src.os_name == "macos" else f"Adobe {spec['label']}'s .exe or its install folder"
    how = f"Set {var} to {what}, or remove the variable and WhyNot Cut finds {spec['label']} by itself."
    if not p.exists():
        raise _guidance(f"{var} is set to {raw}, but nothing is there.", how, var)
    if src.os_name == "macos":
        apps = [p] if p.suffix == ".app" else sorted(p.glob(spec["prefix"] + "*.app")) if p.is_dir() else []
        apps = [a for a in apps if _mac_ok(a, spec["prefix"])]
        if not apps:
            raise _guidance(f"{var} is set to {raw}, but that is not an Adobe {spec['label']} app.", how, var)
        return _mac_record(key, apps[-1], "override")
    hit = _win_app_at(key, p)
    if p.is_file():
        want = Path(spec["win_exe"]).name
        if p.name.lower() != want.lower():                       # notepad.exe, or aerender.exe given as After Effects
            raise _guidance(f"{var} is set to {raw}, but that file is not Adobe {spec['label']}'s {want}.", how, var)
        folder, exe = hit if hit and hit[1] == p else (p.parent, p)
    elif hit:
        folder, exe = hit
    else:
        raise _guidance(f"{var} is set to {raw}, but {Path(spec['win_exe']).name} is not in it.", how, var)
    return _app_record(key, folder.name, folder, exe, "override")


def _merge(found: list[dict]) -> list[dict]:
    """One record per executable: the first source in priority order names it, later ones add `sources`/`version`."""
    by: dict[str, dict] = {}
    for rec in found:
        k = os.path.normcase(os.path.normpath(rec["exe"]))
        cur = by.get(k)
        if not cur:
            by[k] = rec
            continue
        if rec["source"] not in cur["sources"]:
            cur["sources"].append(rec["source"])
        for f in ("version", "reg_version"):
            if not cur[f] and rec[f]:
                cur[f] = rec[f]
    return list(by.values())


def _finish(rec: dict, src: AdobeSources) -> dict:
    """Windows: the real version from the exe. Then the year when the folder name has none (a custom folder): the
    marketing year follows the major version, so a newer app in D:/PPro still beats an older stock install."""
    if src.os_name == "windows":
        rec["version"] = src.file_version(rec["exe"])
    if not rec["year"]:
        major = (_vtuple(rec["version"] or rec["reg_version"]) or (0,))[0]
        if 20 <= major <= 39:
            rec["year"] = _ADOBE[rec["key"]]["year_base"] + major
    return rec


def _rank(a: dict) -> tuple:
    return (not a["beta"], a["year"], _vtuple(a["version"] or a["reg_version"]), a["exe"].lower())


def find_adobe_apps(key: str | None = None, sources: AdobeSources | None = None) -> list[dict]:
    """Installed Adobe apps, best first: [{key, name, year, version, beta, folder, exe, source, sources}]. 'exe' is
    what to launch/script; 'source' is where it was found first (override, registry, app-paths, mdfind, scan). An
    override variable that points nowhere is Guidance naming the variable."""
    src = sources or AdobeSources()
    found = []
    for k in [key] if key else sorted(_ADOBE):
        over = _override_app(k, src)
        cands = (_win_candidates(k, src) if src.os_name == "windows" else
                 _mac_candidates(k, src) if src.os_name == "macos" else [])
        apps = sorted((_finish(a, src) for a in _merge(cands)), key=_rank, reverse=True)
        if over:
            over = _finish(over, src)
            same = os.path.normcase(os.path.normpath(over["exe"]))
            apps = [over] + [a for a in apps if os.path.normcase(os.path.normpath(a["exe"])) != same]
        found += apps
    return found


def newest_app(key: str, sources: AdobeSources | None = None) -> dict | None:
    apps = find_adobe_apps(key, sources)
    return apps[0] if apps else None


def aerender_info(sources: AdobeSources | None = None) -> dict | None:
    """{path, source} of aerender: WHYNOT_AERENDER (checked), else the one beside the newest After Effects that has
    one (a broken newest install does not hide a whole older one)."""
    src = sources or AdobeSources()
    raw = str(src.env.get(AERENDER_ENV) or "").strip().strip('"')
    if raw:
        how = (f"Set {AERENDER_ENV} to aerender (aerender.exe on Windows, in the After Effects folder), or "
               "remove the variable and WhyNot Cut finds it beside After Effects.")
        p = Path(raw).expanduser()
        if not p.is_file():
            raise _guidance(f"{AERENDER_ENV} is set to {raw}, but that is not a file.", how, AERENDER_ENV)
        want = "aerender.exe" if src.os_name == "windows" else "aerender"
        if p.name.lower() != want:
            raise _guidance(f"{AERENDER_ENV} is set to {raw}, but that file is not After Effects' {want}.", how,
                            AERENDER_ENV)
        return {"path": str(Path(raw).expanduser()), "source": "override"}
    for ae in find_adobe_apps("after_effects", src):
        cand = (Path(ae["folder"]) / "aerender") if src.os_name == "macos" else Path(ae["exe"]).parent / "aerender.exe"
        if cand.exists():
            return {"path": str(cand), "source": ae["source"]}
    return None


def aerender_path(sources: AdobeSources | None = None) -> Path | None:
    info = aerender_info(sources)
    return Path(info["path"]) if info else None


def adobe_report(sources: AdobeSources | None = None) -> dict:
    """What `reel doctor` shows; never raises (a bad override or a failing lookup becomes a problem). found[key] = the newest install {name, version, year,
    path, folder, source, sources, beta, others} or None; names[key] = its name; all = every install found;
    aerender = {path, source} or None; problems = [{error, how}] for override variables that point nowhere
    or a lookup that failed."""
    src = sources or AdobeSources()
    rep = {"found": {}, "names": {}, "all": [], "aerender": None, "problems": []}

    def attempt(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  (doctor is the diagnostic that must survive: nothing escapes)
            if hasattr(e, "how") and hasattr(e, "error"):                      # Guidance, whichever way errors was imported
                err, how = e.error, e.how
            else:
                err = f"Adobe app lookup failed: {type(e).__name__}: {e}"
                how = "run reel doctor again; if it repeats, send this report to the WhyNot Cut team"
            if not any(x["error"] == err for x in rep["problems"]):
                rep["problems"].append({"error": err, "how": how})
            return None
    for k in sorted(_ADOBE):
        apps = attempt(lambda k=k: find_adobe_apps(k, src)) or []
        rep["all"] += apps
        top = apps[0] if apps else None
        rep["names"][k] = top["name"] if top else None
        rep["found"][k] = {"name": top["name"], "version": top["version"], "year": top["year"], "path": top["exe"],
                           "folder": top["folder"], "source": top["source"], "sources": top["sources"],
                           "beta": top["beta"], "others": [a["exe"] for a in apps[1:]]} if top else None
    rep["aerender"] = attempt(lambda: aerender_info(src))
    return rep


# --------------------------------------------------------------------------- CEP (Premiere bridge)
CSXS_VERSIONS = (11, 12, 13, 14)


def cep_extensions_dir() -> Path:
    if IS_WIN:
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Adobe" / "CEP" / "extensions"
    return Path.home() / "Library/Application Support/Adobe/CEP/extensions"


def cep_log_dir() -> Path:
    if IS_WIN:
        return Path(os.environ.get("TEMP", Path.home() / "AppData/Local/Temp"))
    return Path.home() / "Library/Logs/CSXS"


def player_debug_mode() -> dict:
    """PlayerDebugMode per CSXS version ('1' = unsigned panels allowed). Read-only: never changed by the plugin."""
    out = {}
    for v in CSXS_VERSIONS:
        val = ""
        try:
            if IS_WIN:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Adobe\CSXS.{v}") as k:
                    val = str(winreg.QueryValueEx(k, "PlayerDebugMode")[0])
            elif IS_MAC:
                val = subprocess.run(["defaults", "read", f"com.adobe.CSXS.{v}", "PlayerDebugMode"],
                                     capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            val = ""
        out[str(v)] = val
    return out


def debug_mode_ok(modes: dict | None = None) -> bool:
    modes = modes if modes is not None else player_debug_mode()
    return any(v == "1" for v in modes.values())


def debug_mode_commands() -> list[str]:
    """Commands the EDITOR runs themselves (an Adobe preference that allows unsigned panels; we only report it)."""
    if IS_WIN:
        return [f'reg add "HKCU\\Software\\Adobe\\CSXS.{v}" /v PlayerDebugMode /t REG_SZ /d 1 /f' for v in CSXS_VERSIONS]
    return [f"defaults write com.adobe.CSXS.{v} PlayerDebugMode 1" for v in CSXS_VERSIONS]


# --------------------------------------------------------------------------- test sandbox (3.0 G79)
# A unit test once queued real build_project jobs that a running Premiere executed. tests/_isolation.py runs every test
# process with WHYNOT_TEST_SANDBOX set (a temp folder) and records the machine's real locations in
# WHYNOT_TEST_LIVE_ROOTS before it redirects HOME / WHYNOT_HOME. Under that flag the engine refuses to write into a live
# root (job queues, bridge scripts, the CEP bundle) and to launch After Effects / Photoshop / aerender, unless a
# deliberate live run sets WHYNOT_TEST_ALLOW_LIVE_BRIDGE=1. Outside tests the flag is never set: nothing changes.
SANDBOX_ENV = "WHYNOT_TEST_SANDBOX"
LIVE_ROOTS_ENV = "WHYNOT_TEST_LIVE_ROOTS"
ALLOW_LIVE_ENV = "WHYNOT_TEST_ALLOW_LIVE_BRIDGE"


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def live_roots() -> list[Path]:
    """The real machine's engine home(s) and CEP folder as tests/_isolation.py recorded them; without that record,
    ~/.whynot-cut, the legacy homes and the CEP folder as the environment gives them now."""
    rec = [Path(p) for p in os.environ.get(LIVE_ROOTS_ENV, "").split(os.pathsep) if p]
    return rec or [Path.home() / HOME_NAME, *(Path.home() / h for h in LEGACY_HOMES), cep_extensions_dir()]


def sandbox_refusal(what: str, *targets) -> dict | None:
    """None, except inside a test sandbox without the live opt-in, when a target lies in a live root — or when there
    is no target at all (launching an Adobe app is always refused there). The refusal is an engine error document."""
    if not os.environ.get(SANDBOX_ENV) or os.environ.get(ALLOW_LIVE_ENV) == "1":
        return None
    hit = None
    if targets:
        roots = [_norm(r) for r in live_roots()]
        hit = next((t for t in targets if any(_norm(t) == r or _norm(t).startswith(r.rstrip("\\/") + os.sep)
                                              for r in roots)), None)
        if hit is None:
            return None
    where = f" ({hit} is the real machine's)" if hit is not None else ""
    return {"ok": False, "refused": "test-sandbox",
            "error": f"test sandbox: refused to {what}{where} - a unit test must never reach the real engine home or a "
                     "running Adobe app",
            "how": "mock the bridge (ppro_bridge.status/submit, ae_bridge.status/submit) or the launcher in the test, "
                   f"or point WHYNOT_HOME at a temp folder; set {ALLOW_LIVE_ENV}=1 only for a deliberate live run"}


# --------------------------------------------------------------------------- misc
# CTranslate2 (Whisper) needs NVIDIA's cuBLAS 12 at run time; its Windows wheel already carries cuDNN 9.
# Missing -> "Library cublas64_12.dll is not found" at the first inference and a silent CPU fallback (5-10x slower).
CUDA_LIBS = {"windows": ["cublas64_12.dll", "cublasLt64_12.dll"], "linux": ["libcublasLt.so.12", "libcublas.so.12"]}
CUDA_PIP = {"windows": ["nvidia-cublas-cu12"], "linux": ["nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*"]}


def cuda_home_bin() -> Path:
    """cuBLAS installed by `reel gpu-enable` from NVIDIA's redistributable (Windows): <engine home>/cuda/bin."""
    return engine_home() / "cuda" / "bin"


def cuda_lib_dirs() -> list:
    """Folders with CUDA libraries for CTranslate2: the engine's own cuda/bin (NVIDIA redist), then NVIDIA's pip wheels
    (nvidia-cublas-cu12 ...) in this interpreter's site-packages, then torch/lib when it holds cuBLAS (T4.12: the cuda
    class runtime's one CUDA library set, no separate download)."""
    sub = "bin" if IS_WIN else "lib"
    out = [cuda_home_bin()] if cuda_home_bin().is_dir() else []
    blas = "cublas64_12.dll" if IS_WIN else "libcublas.so.12"
    for sp in sys.path:
        root = Path(sp) / "nvidia"
        if root.is_dir():
            out += [d / sub for d in sorted(root.iterdir()) if (d / sub).is_dir()]
        tl = Path(sp) / "torch" / "lib"
        if (tl / blas).is_file() and tl not in out:
            out.append(tl)
    return out


CUDA_REDIST = "https://developer.download.nvidia.com/compute/cuda/redist/"
CUDA_REDIST_MANIFEST = "redistrib_12.9.1.json"   # cuBLAS 12.x: what CTranslate2 4.x for CUDA 12 loads


def install_cuda_redist(log=print) -> dict:
    """Windows: cuBLAS 12 from NVIDIA's official redistributable (developer.download.nvidia.com), checked against the
    sha256 in NVIDIA's manifest; only cublas64_12.dll + cublasLt64_12.dll are kept, in <engine home>/cuda/bin.
    Measured on a real install: 2.4 MB/s from NVIDIA's CDN vs 40 KB/s for the same library from PyPI."""
    import hashlib
    import json
    import shutil
    import urllib.request
    import zipfile
    if not IS_WIN:
        raise RuntimeError("the NVIDIA redistributable path is for Windows; Linux uses the pip wheels")
    with urllib.request.urlopen(CUDA_REDIST + CUDA_REDIST_MANIFEST, timeout=60) as r:
        entry = json.load(r)["libcublas"]["windows-x86_64"]
    dest = cuda_home_bin()
    dest.mkdir(parents=True, exist_ok=True)
    part = dest.parent / (Path(entry["relative_path"]).name + ".part")
    h = hashlib.sha256()
    log(f"downloading {entry['relative_path']} ({int(entry['size']) // (1 << 20)} MB) from NVIDIA")
    with urllib.request.urlopen(CUDA_REDIST + entry["relative_path"], timeout=120) as r, open(part, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            h.update(b)
    if h.hexdigest() != entry["sha256"]:
        part.unlink(missing_ok=True)
        raise RuntimeError("cuBLAS download failed its sha256 check; nothing was installed")
    wanted = {"cublas64_12.dll", "cublaslt64_12.dll"}
    got = []
    with zipfile.ZipFile(part) as z:
        for m in z.infolist():
            name = Path(m.filename).name
            if name.lower() in wanted:
                with z.open(m) as src, open(dest / name, "wb") as out:
                    shutil.copyfileobj(src, out)
                got.append(name)
    part.unlink(missing_ok=True)
    if {g.lower() for g in got} != wanted:
        raise RuntimeError(f"cuBLAS archive did not contain {sorted(wanted)} (found {got})")
    return {"source": CUDA_REDIST + entry["relative_path"], "version": entry.get("version"), "sha256": entry["sha256"],
            "installed": [str(dest / g) for g in got]}


def enable_cuda_libs() -> list:
    """Make pip-installed CUDA libraries loadable by CTranslate2 in this process. Returns the folders added."""
    if IS_MAC:
        return []
    dirs = cuda_lib_dirs()
    if not dirs:
        return []
    os.environ["PATH"] = os.pathsep.join([str(d) for d in dirs] + [os.environ.get("PATH", "")])
    if IS_WIN:
        for d in dirs:
            try:
                os.add_dll_directory(str(d))
            except OSError:
                pass
    else:   # LD_LIBRARY_PATH is read only at process start: preload by full path so dlopen("libcublas.so.12") finds it
        import ctypes
        for name in CUDA_LIBS["linux"]:
            for d in dirs:
                if (d / name).exists():
                    try:
                        ctypes.CDLL(str(d / name), mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass
                    break
    return [str(d) for d in dirs]


def cuda_libs_missing() -> list:
    if IS_MAC:
        return []
    import ctypes
    enable_cuda_libs()
    missing = []
    for name in CUDA_LIBS["windows" if IS_WIN else "linux"]:
        try:
            (ctypes.WinDLL if IS_WIN else ctypes.CDLL)(name)
        except OSError:
            missing.append(name)
    return missing


def gpu_info() -> dict:
    """NVIDIA GPU usable by Whisper (CTranslate2) on Windows/Linux; macOS always runs Whisper on the CPU."""
    if IS_MAC:
        return {"cuda_devices": 0, "whisper_device": "cpu", "note": "macOS: Whisper runs on the CPU"}
    try:
        import ctranslate2  # type: ignore
        n = ctranslate2.get_cuda_device_count()
    except Exception as e:  # noqa: BLE001
        return {"cuda_devices": 0, "whisper_device": "cpu", "note": type(e).__name__}
    info = {"cuda_devices": n}
    if n:
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                               capture_output=True, text=True, timeout=10)
            info["name"] = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None
        except Exception:  # noqa: BLE001
            info["name"] = None
        info["cuda_libs_missing"] = cuda_libs_missing()
    info["whisper_device"] = "cuda" if n and not info.get("cuda_libs_missing") else "cpu"
    return info


def describe() -> dict:
    import platform
    return {"os": OS_NAME, "release": platform.release(), "version": platform.version(),
            "machine": platform.machine(), "python": sys.version.split()[0],
            "macos": platform.mac_ver()[0] or None}
