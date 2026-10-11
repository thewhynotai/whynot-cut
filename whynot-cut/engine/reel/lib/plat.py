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


def _saved_path(v: str) -> Path:
    return Path(native_path(v)).expanduser()


def engine_home() -> Path:
    """Machine state lives OUTSIDE the plugin (the plugin folder is replaced on every update).
    Order: explicit setting (env) > saved plugin option (pointer file, else ~/.claude/settings.json) > ~/.whynot-cut
    with an engine > an existing legacy home (keeps the 3 GB of models; dropped in 4.0) > ~/.whynot-cut.
    bin/reel and bin/reel.cmd resolve the same order."""
    for k in HOME_ENV:
        if os.environ.get(k):
            return Path(os.environ[k]).expanduser()
    saved = saved_options()["engine_home"]
    if saved:
        return _saved_path(saved)
    home = Path.home()
    new = home / HOME_NAME
    if (new / "venv").exists():          # ~/.whynot-cut alone may only hold the pointer file
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


def venv_python(home: Path | None = None) -> Path:
    v = (home or engine_home()) / "venv"
    return v / "Scripts" / "python.exe" if IS_WIN else v / "bin" / "python"


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
def font_dirs() -> list[Path]:
    if IS_WIN:
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        if os.environ.get("LOCALAPPDATA"):
            dirs.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    if IS_MAC:
        return [Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    return [Path.home() / ".local/share/fonts", Path.home() / ".fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]


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


# --------------------------------------------------------------------------- Adobe apps
_APPS = {
    # key: (folder prefix, macOS bundle glob, Windows exe name relative to the app folder)
    "premiere": ("Adobe Premiere Pro", "Adobe Premiere Pro*.app", "Adobe Premiere Pro.exe"),
    "after_effects": ("Adobe After Effects", "Adobe After Effects*.app", "Support Files/AfterFX.exe"),
    "photoshop": ("Adobe Photoshop", "Adobe Photoshop*.app", "Photoshop.exe"),
    "media_encoder": ("Adobe Media Encoder", "Adobe Media Encoder*.app", "Adobe Media Encoder.exe"),
}


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


def find_adobe_apps(key: str | None = None) -> list[dict]:
    """Installed Adobe apps, newest first: [{key, name, year, folder, exe}] ('exe' = what to launch/script)."""
    keys = [key] if key else list(_APPS)
    found = []
    for k in keys:
        prefix, mac_glob, win_exe = _APPS[k]
        if IS_MAC:
            for folder in sorted(Path("/Applications").glob(f"{prefix}*")):
                if "Render" in folder.name:
                    continue
                app = folder if folder.suffix == ".app" else next(iter(sorted(folder.glob(mac_glob))), None)
                if app:
                    found.append({"key": k, "name": app.stem, "year": _year(folder.name), "folder": str(folder),
                                  "exe": str(app)})
        elif IS_WIN:
            for base in _program_dirs():
                for folder in sorted((base / "Adobe").glob(f"{prefix}*")) if (base / "Adobe").is_dir() else []:
                    exe = folder / win_exe
                    if exe.exists():
                        found.append({"key": k, "name": folder.name, "year": _year(folder.name),
                                      "folder": str(folder), "exe": str(exe)})
    found.sort(key=lambda a: (a["key"], -a["year"]))
    return found


def newest_app(key: str) -> dict | None:
    apps = find_adobe_apps(key)
    return apps[0] if apps else None


def aerender_path() -> Path | None:
    ae = newest_app("after_effects")
    if not ae:
        return None
    cands = [Path(ae["folder"]) / "aerender"] if IS_MAC else [Path(ae["exe"]).parent / "aerender.exe"]
    return next((c for c in cands if c.exists()), None)


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
    (nvidia-cublas-cu12 ...) in this interpreter's site-packages."""
    sub = "bin" if IS_WIN else "lib"
    out = [cuda_home_bin()] if cuda_home_bin().is_dir() else []
    for sp in sys.path:
        root = Path(sp) / "nvidia"
        if root.is_dir():
            out += [d / sub for d in sorted(root.iterdir()) if (d / sub).is_dir()]
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
