"""Shared foundation of the installer core: everything a step needs, nothing step-specific.

Rules every helper here keeps (global constraints of the installer track):
  * a "<release>" / null value in components.json means "not in this build": refused, never guessed;
  * every download is pinned (URL + sha256), verified before use, and deleted on a mismatch;
  * writes that other programs read (state.json, `current`, settings) are atomic (tmp + replace);
  * deletes only happen strictly inside an allowed root, never through a symlink/junction, never next to client data.
Stdlib only, Python >= 3.9.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform as _platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Literal, Mapping, Optional

PLACEHOLDER = "<release>"
PLATFORMS = ("win-x64", "mac-arm64", "mac-x64")
STATUSES = ("ok", "skipped", "amber", "red")
CLIENT_MARKER = ".whynot-client"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Unsupported(Exception):
    """This OS / CPU has no WhyNot Cut build."""


class DownloadError(Exception):
    """A pinned artefact could not be fetched or did not match its sha256 (nothing is left on disk)."""


class ExtractError(Exception):
    """An archive is unsafe (absolute / `..` / link entries), of an unknown type, or lacks a required member."""


def is_placeholder(v) -> bool:
    """None, or a string starting with "<release" (filled later by the release tool)."""
    return v is None or (isinstance(v, str) and v.startswith("<release"))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stamp() -> str:
    """Local time for file names: YYYYmmdd-HHMMSS."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# --------------------------------------------------------------------------------------------- platform and paths
def platform_id(system: Optional[str] = None, machine: Optional[str] = None, *, sandbox: bool = False,
                env: Optional[Mapping] = None) -> str:
    """win-x64 | mac-arm64 | mac-x64, else Unsupported. WNC_TEST_PLATFORM is honoured only in a sandbox (--home)."""
    env = os.environ if env is None else env
    forced = env.get("WNC_TEST_PLATFORM") if sandbox else None
    if forced:
        if forced in PLATFORMS:
            return forced
        raise Unsupported(f"WNC_TEST_PLATFORM={forced!r} is not one of {', '.join(PLATFORMS)}")
    system = system or _platform.system()
    m = (machine or _platform.machine() or "").lower()
    if system == "Windows" and m in ("amd64", "x86_64", "x64"):
        return "win-x64"
    if system == "Darwin" and m in ("arm64", "aarch64"):
        return "mac-arm64"
    if system == "Darwin" and m in ("x86_64", "amd64"):
        return "mac-x64"
    raise Unsupported(f"WhyNot Cut runs on Windows x64 and macOS (Apple silicon or Intel); this is {system} {m}")


def _abs(p) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(p))))


# --------------------------------------------------------------------------------------------- engine home
# The engine's own order (engine/reel/lib/plat.py engine_home + saved_options; mirrored, never imported): the first
# set variable, else the saved plugin option (the pointer file when it is valid, else Claude Code's settings.json
# pluginConfigs), else ~/.whynot-cut. The engine's legacy-home fallback (~/.reel-editor with a venv) is left out on
# purpose: the installer writes `current` into ~/.whynot-cut, after which the engine picks that folder too.
# bootstrap.ps1 (Resolve-WncEngineHome) and bootstrap.sh (resolve_engine_home) apply the same rules before uv and
# Python are placed, and pass the folder as --engine-home; cli.main refuses to go on when the two disagree.
ENGINE_HOME_ENV = ("WHYNOT_HOME", "CLAUDE_PLUGIN_OPTION_ENGINE_HOME", "REEL_HOME", "CLAUDE_PLUGIN_OPTION_REEL_HOME",
                   "NH_ENV_DIR")
PLUGIN_KEY = "whynot-cut@thewhynot-ai"  # Claude Code's key for the plugin in settings.json pluginConfigs
OPTIONS_FILE = "plugin-options.json"  # <home>/.whynot-cut/plugin-options.json, written by the SessionStart hook
_MSYS = re.compile(r"^/([a-zA-Z])(/|$)")


def _tilde(v: str, home: Path) -> str:
    """`~`, `~/x`, `~\\x` -> under `home` (the injected user home, not this process's); other text unchanged."""
    if v == "~" or v.startswith(("~/", "~\\")):
        return str(home) + v[1:]
    return os.path.expanduser(v) if v.startswith("~") else v


def _native(v: str, home: Path, windows: bool) -> str:
    """plat.native_path for a saved value: on Windows a Git-Bash path /d/x -> D:/x; then `~` -> the user home."""
    if windows and v:
        m = _MSYS.match(v)
        if m:
            v = f"{m.group(1).upper()}:/{v[3:]}"
    return _tilde(v, home)


def _json_object(path: Path) -> Optional[dict]:
    """The file as a JSON object, read like the engine reads it (UTF-8 without a BOM: a BOM is invalid); None when
    missing, unreadable, not JSON or not an object."""
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def _settings_options(settings: Path) -> Optional[tuple]:
    """(key, options) of settings.json pluginConfigs: whynot-cut@thewhynot-ai when it has an options object, else the
    first other whynot-cut@* entry (file order) that has one; None when there is none."""
    d = _json_object(settings)
    configs = (d or {}).get("pluginConfigs") or {}
    if not isinstance(configs, dict):
        return None
    keys = [PLUGIN_KEY] + [k for k in configs if isinstance(k, str) and k.startswith("whynot-cut@") and k != PLUGIN_KEY]
    for k in keys:
        c = configs.get(k)
        if isinstance(c, dict) and isinstance(c.get("options"), dict):
            return k, c["options"]
    return None


def resolve_engine_home(env: Mapping, home, *, windows: Optional[bool] = None) -> tuple:
    """(engine home, source) outside a sandbox, the engine's way (see ENGINE_HOME_ENV above). `env` and the user `home`
    are injected (tests never read this machine's). source: "env:<NAME>", "pointer:<file>", "settings:<file>
    <pluginConfigs key>" or "default". The path is absolute (abspath; `~` is the user home)."""
    home = Path(home)
    windows = os.name == "nt" if windows is None else windows
    for k in ENGINE_HOME_ENV:
        if env.get(k):
            return _abs(_tilde(env[k], home)), f"env:{k}"
    pointer = Path(_tilde(env["WHYNOT_OPTIONS_FILE"], home)) if env.get("WHYNOT_OPTIONS_FILE") else \
        home / ".whynot-cut" / OPTIONS_FILE
    saved, source = "", "default"
    p = _json_object(pointer)
    if p is not None and isinstance(p.get("engine_home"), str):  # a valid pointer, "" = not set
        saved, source = p["engine_home"], f"pointer:{_abs(pointer)}"
    else:
        cfg = Path(_tilde(env["CLAUDE_CONFIG_DIR"], home)) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
        found = _settings_options(cfg / "settings.json")
        if found is not None:
            key, opts = found
            saved = opts.get("engine_home") if isinstance(opts.get("engine_home"), str) else ""
            source = f"settings:{_abs(cfg / 'settings.json')} {key}"
    if saved:
        return _abs(_native(saved, home, windows)), source
    return home / ".whynot-cut", "default"


def describe_engine_home_source(source: str) -> str:
    """The source of resolve_engine_home in words, for preflight and the log ("chosen": -EngineHome / --engine-home
    or the bootstrap's location question)."""
    kind, _, rest = (source or "").partition(":")
    if kind == "env":
        return f"{rest} is set"
    if kind == "pointer":
        return f"the plugin option engine_home in {rest}"
    if kind == "settings":
        f, _, key = rest.rpartition(" ")
        return f"the plugin option engine_home in {f} (pluginConfigs {key})"
    return {"sandbox": "sandbox", "default": "default", "chosen": "chosen"}.get(source, source or "default")


def saved_path(value: str, home, *, windows: Optional[bool] = None) -> Path:
    """A saved engine_home value as the engine reads it (plat.native_path, `~` = the user home), made absolute."""
    windows = os.name == "nt" if windows is None else windows
    return _abs(_native(value, Path(home), windows))


def same_path(a, b) -> bool:
    return _norm(a) == _norm(b)


# What WhyNot Cut itself puts in an engine home (installer.md R.1 + the engine's own folders, engine/reel/lib plat.py,
# common.py, cep_queue / ae_* and serve/: 2.x venv, the Premiere / After Effects queues and scripts, the AE probe, the
# Whisper bench, ae_render's tmp). Uninstall --remove-engine deletes ONLY these (plus models/ when asked); anything
# else is the editor's and is kept and listed. Names compare exactly (`Bin` is the editor's). The location check does
# NOT use this list (fix round 2: names can be anyone's): see occupied_entries and is_engine_home.
ENGINE_LAYOUT = ("bin", "python", "runtimes", "current", "ffmpeg", "cuda", "bridge", "state.json", "logs", "cache",
                 "downloads", "fonts", "marketplace", "marketplace.new", "marketplace.prev", ".delete-after-exit",
                 "venv", "ppro-queue", "ppro-scripts", "ae-queue", "ae-scripts", "ae-probe", "ae-capabilities.json",
                 "bench", "tmp")
ENGINE_LAYOUT_PREFIXES = ("state.json.corrupt-", ".state.json.", ".current.", ".plugin-options.json.",
                          "..delete-after-exit.", ".wnc-write-test")  # set-aside / atomic-write leftovers, the probe
ENGINE_KEPT = ("models", "library")  # models/ unless --remove-models; library/ (licensed packs) always
ENGINE_MARKS = ("state.json", "current")  # read by is_engine_home: their CONTENT must be WhyNot Cut's
_RUNTIME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")  # the engine's runtime id rule (lib/plat.py)
HOME_ROOTS = ("Desktop", "Documents", "Downloads")  # with the user folder itself: never the engine home directly
SUBFOLDER = "WhyNotCut"


def is_engine_entry(name: str) -> bool:
    """A top-level name WhyNot Cut puts in an engine home (ENGINE_LAYOUT / its prefixes), compared EXACTLY (case
    too: `Bin` is the editor's, not ours); not models/, library/ or the pointer, which have their own rules."""
    return name in ENGINE_LAYOUT or name.startswith(ENGINE_LAYOUT_PREFIXES)


def _json_file(path: Path):
    try:
        with open(path, "rb") as f:
            raw = f.read(1 << 20)
        return json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError):
        return None


def is_engine_home(path) -> bool:
    """A GENUINE WhyNot Cut engine home (fix round 2; file names alone can be anyone's): state.json is a JSON object with
    schema 1 and a `plugin` key (what the installer's State writes), or `current` names a valid runtime id whose
    runtimes/<id>/WHYNOT_RUNTIME is a JSON object with that same id (what both runtime builders write). The bootstraps
    apply the same rule (Test-WncEngineHomeMark / is_engine_home)."""
    p = Path(path)
    st = _json_file(p / "state.json")
    if isinstance(st, dict) and type(st.get("schema")) is int and st.get("schema") == 1 and "plugin" in st:
        return True
    try:
        with open(p / "current", "rb") as f:
            rid = f.read(256).decode("utf-8").strip()
    except (OSError, UnicodeError):
        return False
    if not _RUNTIME_ID.match(rid) or ".." in rid:
        return False
    stamp = _json_file(p / "runtimes" / rid / "WHYNOT_RUNTIME")
    return isinstance(stamp, dict) and stamp.get("id") == rid


def occupied_entries(path, *, pointer_ok: bool = False) -> list:
    """What makes an existing folder the editor's for the placement rule (controller ruling, fix round 2): every entry
    except the bootstraps' write probe (.wnc-write-test*), the -Source cache (a `downloads` folder holding only
    `release-*` folders) and, at the pointer's own place (`pointer_ok`: ~/.whynot-cut), the pointer
    plugin-options.json. Names compare exactly. [] when the folder is missing or empty of anything else."""
    try:
        names = os.listdir(path)
    except OSError:
        return []
    out = []
    for n in names:
        if n.startswith(".wnc-write-test") or (pointer_ok and n == OPTIONS_FILE):
            continue
        if n == "downloads" and not is_link(Path(path) / n) and os.path.isdir(Path(path) / n):
            try:
                if all(c.startswith("release-") for c in os.listdir(Path(path) / n)):
                    continue
            except OSError:
                pass
        out.append(n)
    return sorted(out)


def foreign_entries(path) -> list:
    """Children of `path` that WhyNot Cut does not put there (sorted); [] when it is missing or holds only ours."""
    try:
        names = os.listdir(path)
    except OSError:
        return []
    return sorted(n for n in names if not (is_engine_entry(n) or n in ENGINE_KEPT or n == OPTIONS_FILE))


def _is_drive_root(p: str) -> bool:
    """A drive root, a mounted volume (os.path.ismount: macOS /Volumes/<name>, a Windows volume mount point) or the
    /Volumes/<name> form itself."""
    n = _norm(p)
    if Path(n).parent == Path(n):
        return True
    if re.match(r"^/volumes/[^/]+$", n.replace("\\", "/").lower()):
        return True
    try:
        return os.path.ismount(p)
    except OSError:
        return False


def _marker_below(top: str, depth: int = 3, limit: int = 5000) -> Optional[str]:
    """A `.whynot-client` marker up to `depth` levels below `top` (bounded: a huge folder is not walked whole)."""
    seen, stack = 0, [(top, 0)]
    while stack:
        d, lvl = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    seen += 1
                    if seen > limit:
                        return None
                    if e.name == CLIENT_MARKER:
                        return d
                    if lvl < depth and not is_link(e.path) and e.is_dir(follow_symlinks=False):
                        stack.append((e.path, lvl + 1))
        except OSError:
            continue
    return None


def choose_engine_home(path, *, home, plugin_root, clients_roots: Iterable = (), sandbox_home=None) -> tuple:
    """Where the engine goes for the folder the editor chose (-EngineHome / --engine-home, or the bootstrap's location
    question): (final folder or None, note or "", problem or None). The bootstraps apply the same rules before
    anything is downloaded, plus free space and write access (Get-WncEngineHomeProblem / engine_home_problem).

    Refused: not a full path; a drive root or mounted volume (/Volumes/<name>, any mount point) or a link; a folder
    that is, holds or lies inside the plugin folder (the plugin may sit in <it>/downloads: the -Source cache); one that
    is, holds or lies inside the saved clients folder, lies inside a `.whynot-client` folder or holds one (3 levels
    deep) - unless it is already an engine home.
    Moved into <it>/WhyNotCut (controller rulings, fix rounds 1 and 2): the user folder, Desktop, Documents and
    Downloads themselves, and any existing folder with ANY entry (occupied_entries: only the write probe, the -Source
    downloads/release-* cache and, in ~/.whynot-cut, the pointer do not count; names are not trusted) that is not a
    GENUINE engine home (is_engine_home: by content) - so uninstall can never empty a folder of the editor's files. Then the final folder is checked again:
    not holding the user folder, not inside Claude's folder, not a WhyNotCut subfolder that holds other files, and in a
    sandbox strictly inside the sandbox home."""
    p = str(path or "").strip()
    if not p or not os.path.isabs(p) or (os.name == "nt" and not re.match(r"^([A-Za-z]:[\\/]|[\\/]{2})", p)):
        return None, "", f"{p or '(empty)'} is not a full path (for example C:\\WhyNotCut or /Users/you/WhyNotCut)"
    n = _norm(p)
    if _is_drive_root(p):
        return None, "", f"{p} is a drive root or a mounted volume; choose a folder on it, for example " \
                         f"{Path(p) / SUBFOLDER}"
    if is_link(p):
        return None, "", f"{p} is a link or mount point; choose a real folder"
    plug = _norm(plugin_root)
    if _within(n, plug, strict=False):
        return None, "", f"{p} is inside the plugin folder {plugin_root}, which is replaced on every update"
    existing = is_engine_home(p)
    if not existing:
        if _within(plug, n) and not _within(plug, _norm(Path(p) / "downloads")) \
                and not _within(plug, _norm(Path(p) / SUBFOLDER / "downloads")):
            return None, "", f"{p} holds the plugin folder {plugin_root}; choose a folder of its own"
        for c in clients_roots:
            if c and (_within(n, _norm(c), strict=False) or _within(_norm(c), n)):
                return None, "", f"{p} is, holds or is inside your clients folder {c}; keep the engine apart from " \
                                 "client footage"
        cur = Path(n)
        while True:
            if (cur / CLIENT_MARKER).exists():
                return None, "", f"{p} is inside a client folder ({cur} holds {CLIENT_MARKER})"
            if cur.parent == cur:
                break
            cur = cur.parent
        if os.path.isdir(p):
            below = _marker_below(p)
            if below:
                return None, "", f"{p} holds a client folder ({below} holds {CLIENT_MARKER})"
    final, note = Path(p), ""
    roots = [Path(home)] + [Path(home) / r for r in HOME_ROOTS]
    pointer_ok = _norm(Path(home) / ".whynot-cut") == n  # the SessionStart hook's pointer lives there
    if not existing and (any(_norm(r) == n for r in roots) or occupied_entries(p, pointer_ok=pointer_ok)):
        final = Path(p) / SUBFOLDER
        note = (f"{p} already holds other files, so WhyNot Cut goes into its own folder {final} (uninstall then "
                "never touches the rest)")
    f = _norm(final)
    if _within(_norm(home), f, strict=False):
        return None, "", f"{final} is your user folder or holds it; choose a folder of its own"
    if _within(f, _norm(Path(home) / ".claude"), strict=False):
        return None, "", f"{final} is inside Claude's folder {Path(home) / '.claude'}"
    if final != Path(p) and not is_engine_home(final) and occupied_entries(final):
        return None, "", f"{final} already holds other files; choose an empty folder or one of its own"
    if sandbox_home is not None and not _within(f, _norm(sandbox_home), strict=True):
        return None, "", f"{final} is outside the sandbox home {sandbox_home} (--home: nothing outside it is used)"
    return final, note, None


def engine_home_choice_problem(path, **kw) -> Optional[str]:
    """Why `path` cannot be used as (or moved into a WhyNotCut subfolder for) the engine home, else None."""
    return choose_engine_home(path, **kw)[2]


# the way out of a refused RESOLVED engine home, in the editor's words (both front ends' flags; task 9)
SELF_FIX = "run the installer again with -EngineHome <folder> / --engine-home <folder>"
SELF_FIX_AR = ("لن يستخدم WhyNot Cut هذا المجلد لملفات التشغيل. لإصلاح ذلك شغّل المثبّت مرة أخرى مع "
               "-EngineHome <folder> (على macOS: --engine-home <folder>) واختر مجلدًا خاصًا به.")


def resolved_home_problem(path, *, home, clients_roots: Iterable = ()) -> Optional[str]:
    """Why a RESOLVED engine home (named by a variable, the pointer or settings.json pluginConfigs; never chosen in
    this run) may not be used, else None (task 9, carried from the Task 8 review: controller ruling). ~/.whynot-cut
    itself is never refused here. Refused: a drive root or mount point; the user folder itself, or Desktop, Documents,
    Downloads themselves (not a folder inside them); a folder holding client data - the saved clients folder (it is
    or holds it) or a `.whynot-client` marker in it or up to 3 levels below (bounded). A genuine 2.x / 3.0 home
    anywhere else is used as it is. The bootstraps apply the same rule (Get-WncResolvedHomeProblem /
    resolved_home_problem) before anything is downloaded."""
    p, h = str(path), Path(home)
    n = _norm(p)
    if n == _norm(h / ".whynot-cut"):
        return None
    if _is_drive_root(p):
        return "a drive root or a mount point"
    if n == _norm(h):
        return "your user folder itself"
    for r in HOME_ROOTS:
        if n == _norm(h / r):
            return f"your {r} folder itself"
    for c in clients_roots:
        if c and _within(_norm(c), n, strict=False):
            return f"your clients folder {c}, or it holds it"
    if os.path.isdir(p):
        below = _marker_below(p)
        if below:
            return f"holding a client folder ({below} holds {CLIENT_MARKER})"
    return None


# --------------------------------------------------------------------------------------------- the pointer file
def pointer_file(env: Mapping, home) -> Path:
    """The SessionStart hook's record of the plugin options (engine plat.options_file): WHYNOT_OPTIONS_FILE, else
    <home>/.whynot-cut/plugin-options.json. It stays there also when the engine home is elsewhere."""
    home = Path(home)
    if env.get("WHYNOT_OPTIONS_FILE"):
        return _abs(_tilde(env["WHYNOT_OPTIONS_FILE"], home))
    return home / ".whynot-cut" / OPTIONS_FILE


def read_pointer(path) -> Optional[dict]:
    """The pointer as the engine reads it (a JSON object, UTF-8 without a BOM), else None."""
    return _json_object(Path(path))


POINTER_KEYS = ("clients_root", "engine_home", "updated")


def pointer_bytes(clients_root: str, engine_home: str, extra: Optional[Mapping] = None) -> bytes:
    """Exactly what hooks/session_context.py write_pointer writes: the keys clients_root, engine_home, updated, one
    per line (indent 1; bin/reel.cmd reads it line by line), raw UTF-8 (ensure_ascii=False), a final newline. `extra`:
    other keys already in the file, kept after those three (never dropped)."""
    body = {"clients_root": clients_root, "engine_home": engine_home, "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    body.update({k: v for k, v in (extra or {}).items() if k not in POINTER_KEYS})
    return (json.dumps(body, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


@dataclass
class Paths:
    """Every location the installer touches. A --home override is a sandbox: nothing outside that folder is used."""
    home: Path
    whynot: Path
    claude_dir: Path
    appdata: Path
    localappdata: Path
    sandbox: bool
    engine_home_source: str = "default"  # resolve_engine_home's source; "sandbox" (its default) under --home;
    #                                      "chosen" for --engine-home with --engine-home-chosen
    pointer: Optional[Path] = None  # the plugin options pointer file (pointer_file); None = <home>/.whynot-cut/...

    @classmethod
    def from_env(cls, home_override: Optional[str] = None, env: Mapping = os.environ,
                 engine_home: Optional[str] = None) -> "Paths":
        """`engine_home`: the folder the editor chose (bootstrap -EngineHome / --engine-home or its location
        question); it wins over the resolver. A sandbox (--home) resolves the engine's way too, but only from its own
        files (<dir>/.whynot-cut/plugin-options.json, <dir>/.claude/settings.json), never from the environment."""
        if home_override:
            home = _abs(home_override)
            if engine_home:
                whynot, source = _abs(engine_home), "chosen"
            else:
                whynot, source = resolve_engine_home({}, home)
                source = "sandbox" if source == "default" else source
            return cls(home=home, whynot=whynot, claude_dir=home / ".claude",
                       appdata=home / "AppData" / "Roaming", localappdata=home / "AppData" / "Local", sandbox=True,
                       engine_home_source=source, pointer=home / ".whynot-cut" / OPTIONS_FILE)
        order = ("USERPROFILE", "HOME") if os.name == "nt" else ("HOME", "USERPROFILE")
        raw = next((env[k] for k in order if env.get(k)), None)
        home = _abs(raw) if raw else Path.home()
        whynot, source = (_abs(engine_home), "chosen") if engine_home else resolve_engine_home(env, home)
        claude = _abs(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
        appdata = _abs(env["APPDATA"]) if env.get("APPDATA") else home / "AppData" / "Roaming"
        local = _abs(env["LOCALAPPDATA"]) if env.get("LOCALAPPDATA") else home / "AppData" / "Local"
        return cls(home=home, whynot=whynot, claude_dir=claude, appdata=appdata, localappdata=local, sandbox=False,
                   engine_home_source=source, pointer=pointer_file(env, home))

    @property
    def options_file(self) -> Path:
        """The pointer ~/.whynot-cut/plugin-options.json (or WHYNOT_OPTIONS_FILE outside a sandbox)."""
        return self.pointer or self.home / ".whynot-cut" / OPTIONS_FILE

    @property
    def default_whynot(self) -> Path:
        """~/.whynot-cut: the engine home when nothing names another one (where the pointer always lives)."""
        return self.home / ".whynot-cut"

    # engine home layout (installer.md R.1)
    bin_dir = property(lambda s: s.whynot / "bin")
    python_dir = property(lambda s: s.whynot / "python")
    runtimes_dir = property(lambda s: s.whynot / "runtimes")
    current_file = property(lambda s: s.whynot / "current")
    ffmpeg_dir = property(lambda s: s.whynot / "ffmpeg")
    models_dir = property(lambda s: s.whynot / "models")
    logs_dir = property(lambda s: s.whynot / "logs")
    state_file = property(lambda s: s.whynot / "state.json")
    cache_dir = property(lambda s: s.whynot / "cache")
    downloads_dir = property(lambda s: s.whynot / "downloads")
    fonts_dir = property(lambda s: s.whynot / "fonts")
    marketplace_dir = property(lambda s: s.whynot / "marketplace")
    bridge_dir = property(lambda s: s.whynot / "bridge")
    settings_file = property(lambda s: s.claude_dir / "settings.json")
    sandbox_dir = property(lambda s: s.home / ".wnc-sandbox")

    def child_env(self, base_env: Optional[Mapping] = None) -> dict:
        """Environment for every child process (uv, the runtime, claude, reel). PYTHONPATH / PYTHONHOME are dropped:
        an editor's (or another tool's) value would put foreign packages, or another Python's stdlib, under the
        runtime and the engine. A sandbox also drops CLAUDE_CLI: a developer's would lead a child to the real Claude
        Code CLI and the real ~/.claude (the sandbox's own stand-in is WNC_CLAUDE_CLI)."""
        env = dict(os.environ if base_env is None else base_env)
        for k in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(k, None)
        if self.sandbox:
            env.pop("CLAUDE_CLI", None)
            env.update(HOME=str(self.home), USERPROFILE=str(self.home), APPDATA=str(self.appdata),
                       LOCALAPPDATA=str(self.localappdata), CLAUDE_CONFIG_DIR=str(self.claude_dir))
        # uv: our own python and cache folders, no uv.toml / pyproject config (same as setup/setup_env.py uv_env)
        env.update(WHYNOT_HOME=str(self.whynot), UV_PYTHON_INSTALL_DIR=str(self.python_dir),
                   UV_CACHE_DIR=str(self.cache_dir / "uv"), UV_NO_CONFIG="1", UV_HTTP_TIMEOUT="60",
                   UV_HTTP_RETRIES="5", PYTHONUTF8="1")
        return env


# --------------------------------------------------------------------------------------------- log
def _console(text: str) -> None:
    out = sys.stdout
    if out is None:
        return
    try:
        out.write(text + "\n")
    except UnicodeEncodeError:
        enc = out.encoding or "ascii"
        out.write(text.encode(enc, "backslashreplace").decode(enc, "replace") + "\n")
    out.flush()


class Log:
    """UTF-8 log lines `<ISO time> <LEVEL> <message>` in logs/install-YYYYmmdd-HHMMSS.log, echoed to the console.
    The bootstrap passes the path (--log) so its own lines and the core's share one file; dry-run = console only."""

    def __init__(self, path: Optional[Path], dry_run: bool = False, *, console: bool = True):
        self.dry_run = dry_run
        self.console = console
        self.path = None if (dry_run or path is None) else Path(path)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, msg: str, extra: str = "") -> None:
        if self.path:
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"{now_iso()} {level} {msg}\n{extra}")
        if self.console:
            _console(msg if level in ("INFO", "STEP") else f"{level}: {msg}")

    def info(self, msg: str) -> None:
        self._write("INFO", msg)

    def warn(self, msg: str) -> None:
        self._write("WARN", msg)

    def error(self, msg: str) -> None:
        self._write("ERROR", msg)

    def step(self, name: str) -> None:
        self._write("STEP", f"== {name} ==")

    def exception(self, msg: str) -> None:
        """ERROR line plus the current traceback (file only; the console gets the one-line message)."""
        self._write("ERROR", msg, traceback.format_exc())


# --------------------------------------------------------------------------------------------- questions
def _terminal():
    """(reader, must_close) for the editor's keyboard, or None. stdin when it is a terminal; on POSIX /dev/tty when
    stdin is a pipe (`curl ... | bash` hands the script to bash on stdin, but the terminal is still there)."""
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return sys.stdin, False
    except (AttributeError, ValueError):
        pass
    if os.name != "nt":
        try:
            return open("/dev/tty", "r", encoding="utf-8", errors="replace"), True
        except OSError:
            return None
    return None


_TEST_ANSWERS: Optional[list] = None  # sandbox only: WNC_TEST_ANSWERS lines read instead of the keyboard (cli)


def set_test_answers(lines) -> None:
    """cli.main: the answer lines of the sandbox-only test hook (None = the keyboard), used in order by ask()."""
    global _TEST_ANSWERS
    _TEST_ANSWERS = list(lines) if lines is not None else None


def can_ask(args) -> bool:
    """Questions only without --yes / --quiet and with a terminal to read the answer from (or the sandbox-only
    WNC_TEST_ANSWERS lines)."""
    if getattr(args, "yes", False) or getattr(args, "quiet", False):
        return False
    if _TEST_ANSWERS is not None:
        return True
    t = _terminal()
    if t is not None and t[1]:
        t[0].close()
    return t is not None


def _write_prompt(text: str) -> None:
    out = sys.stdout
    if out is None:
        return
    try:
        out.write(text)
    except UnicodeEncodeError:
        enc = out.encoding or "ascii"
        out.write(text.encode(enc, "backslashreplace").decode(enc, "replace"))
    out.flush()


def ask(prompt: str, default: str = "") -> str:
    """One line from the editor; Enter, end of input or no terminal keeps `default`."""
    if _TEST_ANSWERS is not None:  # (sandbox test hook: the line is shown as if typed)
        line = _TEST_ANSWERS.pop(0) if _TEST_ANSWERS else ""
        _write_prompt(prompt + line + "\n")
        return line.strip() or default
    t = _terminal()
    if t is None:
        return default
    reader, close = t
    try:
        _write_prompt(prompt)
        line = reader.readline()
    except (OSError, ValueError, KeyboardInterrupt):
        line = ""
    finally:
        if close:
            reader.close()
    return line.strip() or default


# --------------------------------------------------------------------------------------------- components / files
def load_components(path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        c = json.load(f)
    if not isinstance(c, dict) or c.get("schema") != 1:
        raise ValueError(f"{path}: not a schema-1 components.json")
    return c


def cget(c: dict, dotted: str, default=None):
    """components value by dotted path (`ffmpeg.assets.win-x64.files.0.url`); default when any part is missing."""
    cur = c
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return default
    return cur


def _replace(src: Path, dst: Path, tries: int = 6) -> None:
    """os.replace, retried briefly: on Windows an antivirus or indexer can hold the target for a moment."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.1 * (i + 1))


def atomic_write_text(path, text: str) -> None:
    """UTF-8, LF kept as written, no BOM; readers see the old or the new file, never half of one."""
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_bytes(path, data: bytes, mode: Optional[int] = None) -> None:
    """Readers see the old or the new file, never half of one. `mode` (permission bits) is set on the new file before
    it replaces the old one (keeps e.g. a 0600 settings.json at 0600)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        _replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_write_json(path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------------- state.json
def _empty_state() -> dict:
    return {"schema": 1, "plugin": None, "updated_at": None, "steps": {}}


class State:
    """~/.whynot-cut/state.json: what is actually installed. Steps add their own sections (runtime, ffmpeg, ...);
    `steps` holds {name: {status, fingerprint, detail, at}} so a re-run skips work whose fingerprint still matches."""

    def __init__(self, paths: Paths, *, dry_run: bool = False):
        self.paths = paths
        self.dry_run = dry_run
        self.data = _empty_state()
        self.set_aside: Optional[Path] = None  # where an unreadable state.json was moved

    def load(self) -> "State":
        f = self.paths.state_file
        try:
            raw = f.read_bytes()
        except FileNotFoundError:
            self.data = _empty_state()
            return self
        # any other OSError (antivirus lock, permissions, a folder in its place) propagates: the file may be fine,
        # so it is never renamed or overwritten after a read error
        try:
            d = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(d, dict) or not isinstance(d.get("steps", {}), dict):
                raise ValueError("not a state object")
        except ValueError:  # JSON / UTF-8 decode error, or not a state object: the file is corrupt
            self.data = _empty_state()
            if not self.dry_run:
                dest = f.with_name(f"{f.name}.corrupt-{stamp()}")
                n = 1
                while dest.exists():
                    dest = f.with_name(f"{f.name}.corrupt-{stamp()}-{n}")
                    n += 1
                try:
                    _replace(f, dest)
                    self.set_aside = dest
                except OSError:
                    pass
            return self
        d.setdefault("schema", 1)
        d.setdefault("plugin", None)
        d.setdefault("updated_at", None)
        d.setdefault("steps", {})
        self.data = d
        return self

    def save(self) -> None:
        if self.dry_run:
            return
        self.data["updated_at"] = now_iso()
        atomic_write_json(self.paths.state_file, self.data)

    def step_done(self, name: str, fingerprint) -> bool:
        s = self.data.get("steps", {}).get(name)
        return isinstance(s, dict) and s.get("status") == "ok" and s.get("fingerprint") == fingerprint

    def record(self, name: str, status: str, fingerprint=None, detail: str = "") -> None:
        self.data.setdefault("steps", {})[name] = {"status": status, "fingerprint": fingerprint, "detail": detail,
                                                   "at": now_iso()}
        self.save()


# --------------------------------------------------------------------------------------------- processes
def pid_alive(pid) -> bool:
    """Is this process id running? Read-only on every OS (never os.kill on Windows: it terminates the process).
    A non-int or non-positive pid is False. Shared by the model step, the runtime build lock and uninstall."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            try:
                code = wintypes.DWORD()
                return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
            finally:
                k32.CloseHandle(h)
        except (OSError, AttributeError):
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------------------------- download
class _Fatal(Exception):
    """A request another try cannot fix (HTTP 4xx): fail at once."""


class _CurlUnusable(OSError):
    """curl cannot do this request here (missing, TLS / certificate / revocation trouble, old build): use urllib."""


class _CurlNoRoute(OSError):
    """curl could not resolve the proxy / the host or could not connect (exit 5 / 6 / 7). On Windows that is often a
    proxy curl does not know about: urllib reads the system (registry) proxy settings, so it gets one go."""


# curl exit codes meaning "this curl cannot do it" rather than "the transfer broke": switch to urllib for good.
# 1 protocol, 2 init, 4 feature not built in; 35 51 53 54 58 59 60 66 77 80 82 83 90 91 TLS and certificates.
_CURL_UNUSABLE = {1, 2, 4, 35, 51, 53, 54, 58, 59, 60, 66, 77, 80, 82, 83, 90, 91}
_CURL_NO_ROUTE = {5, 6, 7}  # could not resolve proxy, could not resolve host, failed to connect
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _sleep(seconds: float) -> None:  # the retry back-off, in one place (tests patch it)
    time.sleep(seconds)


def find_curl() -> Optional[str]:
    """The OS curl first (Windows 10+ System32, macOS /usr/bin: they use the system certificate store)."""
    if os.name == "nt":
        sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
        if sys32.is_file():
            return str(sys32)
    elif Path("/usr/bin/curl").is_file():
        return "/usr/bin/curl"
    return shutil.which("curl")


def _fetch_curl(curl: str, url: str, part: Path, loopback: bool) -> None:
    """curl writes to stdout into a file Python opened, so no non-ASCII path reaches curl's argv. A body shorter than
    its Content-Length is curl exit 18 (OSError: retried); HTTP 4xx is _Fatal; a TLS-type failure is _CurlUnusable."""
    cmd = [curl, "--fail", "--location", "--silent", "--show-error", "--proto", "=http,https",
           "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "60"]
    if loopback:
        cmd += ["--noproxy", "*"]  # a proxy in the environment must never sit between us and 127.0.0.1
    try:
        with open(part, "wb") as fh:
            r = subprocess.run(cmd + [url], stdout=fh, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise _CurlUnusable(f"curl cannot start: {e}") from None
    if r.returncode == 0:
        return
    lines = r.stderr.decode("utf-8", "replace").strip().splitlines()
    last = lines[-1] if lines else ""
    msg = f"curl exit {r.returncode}: {last}"
    if r.returncode == 22:
        m = re.search(r"error:? (\d{3})", last)
        if m and 400 <= int(m.group(1)) < 500:
            raise _Fatal(f"HTTP {m.group(1)}")
    if r.returncode in _CURL_UNUSABLE:
        raise _CurlUnusable(msg)
    if r.returncode in _CURL_NO_ROUTE:
        raise _CurlNoRoute(msg)
    raise OSError(msg)


def _fetch_urllib(url: str, part: Path, loopback: bool) -> None:
    """Python's downloader, self-checking: a body shorter than its Content-Length raises OSError (retried)."""
    req = urllib.request.Request(url, headers={"User-Agent": "whynot-cut-installer"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if loopback else None
    try:
        resp = opener.open(req, timeout=60) if opener else urllib.request.urlopen(req, timeout=60)
        with resp, open(part, "wb") as fh:
            expected = resp.headers.get("Content-Length")
            written = 0
            for chunk in iter(lambda: resp.read(1 << 20), b""):
                fh.write(chunk)
                written += len(chunk)
            if expected is not None and expected.strip().isdigit() and written != int(expected):
                raise OSError(f"transfer interrupted: got {written} of {expected.strip()} bytes")
    except urllib.error.HTTPError as e:
        e.close()  # it holds the response body: an unclosed one is a ResourceWarning
        if 400 <= e.code < 500:
            raise _Fatal(f"HTTP {e.code} {e.reason}") from None
        raise OSError(f"HTTP {e.code} {e.reason}") from None
    except http.client.HTTPException as e:  # IncompleteRead, RemoteDisconnected ... are not OSError
        raise OSError(f"transfer interrupted: {type(e).__name__}: {e}") from None


def download(url, sha256, dest_dir, log: Log, *, name: Optional[str] = None, retries: int = 3) -> Path:
    """Fetch a pinned artefact into dest_dir (normally ~/.whynot-cut/downloads) and return its path.

    A cached file with the right sha256 is reused (a stale `.part` beside it is removed); a wrong one is replaced.
    The transfer goes to `<name>.part` (a stale one from an interrupted run is discarded), is checked for
    completeness, verified, then renamed. Transfer errors (connection drop, short body, timeout, 5xx) are retried up to
    `retries` tries and the final failure says it was the transfer; HTTP 4xx fails at once. A complete file whose
    sha256 does not match is deleted and raises DownloadError (not retried: the pin or the server is wrong). curl goes
    first; urllib takes over for good when curl is missing or cannot do the request (TLS, certificates), and for that
    attempt when curl cannot reach the server (exit 5 / 6 / 7: urllib reads the system proxy settings). Placeholder pins
    are refused before any request. http(s):// and file:// only."""
    if is_placeholder(url) or is_placeholder(sha256):
        raise DownloadError(f"not available in this build (placeholder pin): {url!r} sha256={sha256!r}")
    if not isinstance(sha256, str) or not _HEX64.match(sha256):
        raise DownloadError(f"invalid sha256 pin {sha256!r} for {url}")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("https", "http", "file"):
        raise DownloadError(f"unsupported URL scheme: {url}")
    name = name or urllib.parse.unquote(parsed.path).rsplit("/", 1)[-1]
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise DownloadError(f"cannot name the download for {url!r}")
    dest_dir = Path(dest_dir)
    dest = dest_dir / name
    part = dest_dir / (name + ".part")
    if dest.is_file():
        if file_sha256(dest) == sha256:
            if part.exists():
                part.unlink()
            log.info(f"cached {dest.name} (sha256 ok)")
            return dest
        log.warn(f"cached {dest.name} has the wrong sha256; fetching it again")
        dest.unlink()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if part.exists():
        part.unlink()
    log.info(f"download {url}")
    loopback = (parsed.hostname or "").lower() in _LOOPBACK
    curl = None if parsed.scheme == "file" else find_curl()
    tries = max(1, retries)
    last: Optional[Exception] = None
    for attempt in range(tries):
        try:
            if parsed.scheme == "file":
                src = Path(urllib.request.url2pathname(parsed.path))
                if parsed.netloc and parsed.netloc != "localhost":
                    src = Path(f"//{parsed.netloc}{src}")
                shutil.copyfile(src, part)
            elif curl:
                try:
                    _fetch_curl(curl, url, part, loopback)
                except _CurlUnusable as e:
                    log.warn(f"curl cannot do this here ({e}); using Python's downloader from now on")
                    curl = None
                    _fetch_urllib(url, part, loopback)
                except _CurlNoRoute as e:  # this attempt only: the next one tries curl again
                    log.warn(f"curl could not reach the server ({e}); trying Python's downloader, which uses the "
                             "system proxy settings")
                    _fetch_urllib(url, part, loopback)
            else:
                _fetch_urllib(url, part, loopback)
            last = None
            break
        except _Fatal as e:
            if part.exists():
                part.unlink()
            raise DownloadError(f"could not download {url}: {e}") from None
        except (OSError, ValueError) as e:  # URLError is an OSError
            last = e
            if part.exists():
                part.unlink()
            if attempt < tries - 1:
                log.warn(f"download interrupted ({e}); retrying ({attempt + 2}/{tries})")
                _sleep(min(2 ** attempt, 5))
    if last is not None:
        raise DownloadError(f"could not download {url}: transfer failed after {tries} tries ({last}); "
                            "nothing was kept, run the installer again")
    got = file_sha256(part)
    if got != sha256:
        part.unlink()
        raise DownloadError(f"sha256 mismatch for {url}: expected {sha256}, got {got}; the file was deleted")
    _replace(part, dest)
    log.info(f"verified {dest.name} (sha256 ok)")
    return dest


# --------------------------------------------------------------------------------------------- extract
def _safe_rel(name: str) -> Optional[str]:
    """Archive entry → clean relative posix path ('' for the root); None when absolute or escaping with `..`."""
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _archive_kind(archive: Path) -> str:
    n = archive.name.lower()
    if n.endswith(".zip"):
        return "zip"
    if n.endswith((".tar.gz", ".tgz")):
        return "r:gz"
    if n.endswith((".tar.xz", ".txz")):
        return "r:xz"
    if zipfile.is_zipfile(archive):
        return "zip"
    if tarfile.is_tarfile(archive):
        return "r:*"
    raise ExtractError(f"unknown archive type: {archive.name}")


def extract(archive, dest, members: Optional[dict] = None) -> list:
    """Unpack a zip / tar.gz / tar.xz into dest and return the files written.

    `members` maps archive path → output path under dest (e.g. {"ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe":
    "ffmpeg.exe"}); only those are written, and on macOS they are made executable. Without it everything is written,
    keeping the archive's exec bits. Every entry is checked first: an absolute path, a `..` or a link refuses the whole
    archive before anything is written."""
    archive, dest = Path(archive), Path(dest)
    kind = _archive_kind(archive)
    entries = []  # (clean relative name, is_dir, mode, opener)
    try:
        zf = zipfile.ZipFile(archive) if kind == "zip" else tarfile.open(archive, kind)
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        raise ExtractError(f"cannot read {archive.name}: {e}") from None
    with zf:
        if kind == "zip":
            for zi in zf.infolist():
                rel = _safe_rel(zi.filename)
                mode = (zi.external_attr >> 16) & 0o177777 if zi.create_system == 3 else 0  # 3 = made on unix
                if rel is None or stat.S_ISLNK(mode):
                    raise ExtractError(f"unsafe entry in {archive.name}: {zi.filename!r}")
                entries.append((rel, zi.is_dir(), mode & 0o777, (lambda zi=zi: zf.open(zi))))
        else:
            for ti in zf.getmembers():
                rel = _safe_rel(ti.name)
                if rel is None or not (ti.isfile() or ti.isdir()):
                    raise ExtractError(f"unsafe entry in {archive.name}: {ti.name!r}")
                entries.append((rel, ti.isdir(), ti.mode & 0o777, (lambda ti=ti: zf.extractfile(ti))))
        files = {rel: (mode, opener) for rel, is_dir, mode, opener in entries if rel and not is_dir}
        if members is not None:
            plan = []
            for src, out in members.items():
                s, o = _safe_rel(src), _safe_rel(out)
                if not s or not o:
                    raise ExtractError(f"unsafe member mapping {src!r} -> {out!r}")
                if s not in files:
                    raise ExtractError(f"{archive.name} has no {src!r}")
                plan.append((o, 0o755, files[s][1]))
        else:
            plan = [(rel, mode, opener) for rel, (mode, opener) in files.items()]
        dest.mkdir(parents=True, exist_ok=True)
        root = os.path.abspath(dest)
        written = []
        for rel, mode, opener in plan:
            out = dest.joinpath(*rel.split("/"))
            if not os.path.abspath(out).startswith(root + os.sep):
                raise ExtractError(f"entry escapes the destination: {rel!r}")
            out.parent.mkdir(parents=True, exist_ok=True)
            with opener() as src_f, open(out, "wb") as dst_f:
                shutil.copyfileobj(src_f, dst_f, 1 << 20)
            if os.name != "nt" and mode & 0o111:
                os.chmod(out, 0o755)
            written.append(out)
    return written


# --------------------------------------------------------------------------------------------- safe delete
def is_link(p) -> bool:
    """Symlink, or any Windows reparse point (junction, mount point, ...)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _norm(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _real(p) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def _within(child: str, parent: str, strict: bool = True) -> bool:
    if child == parent:
        return not strict
    return child.startswith(parent.rstrip("\\/") + os.sep)


def _has_marker(top: str) -> bool:
    stack = [top]
    while stack:
        with os.scandir(stack.pop()) as it:
            for e in it:
                if e.name == CLIENT_MARKER:
                    return True
                if not is_link(e.path) and e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
    return False


def _unlink(p: str) -> None:
    try:
        os.unlink(p)  # on Windows this also removes a directory symlink / junction (not its target)
    except PermissionError:
        if is_link(p):
            os.rmdir(p)
        else:
            os.chmod(p, stat.S_IWRITE)  # read-only file (git objects, some wheels)
            os.unlink(p)
    except IsADirectoryError:
        os.rmdir(p)


def _delete(top: str) -> None:
    with os.scandir(top) as it:
        entries = [(e.path, e.is_dir(follow_symlinks=False)) for e in it]
    for path, is_dir in entries:
        if is_link(path) or not is_dir:
            _unlink(path)
        else:
            _delete(path)
    os.rmdir(top)


def safe_rmtree(path, allowed_roots: Iterable, protected: Iterable = ()) -> bool:
    """Delete `path` only when that is certainly safe; False (nothing deleted) when refused, True when gone.

    Refused when: `path` is a symlink/junction; it is not strictly inside one of `allowed_roots` (checked both as
    written and with links resolved, so a junction above it cannot lead outside); it is, contains or lies inside a
    `protected` path (clients folder, models, Claude's folder ...); or a `.whynot-client` marker sits anywhere below
    it. Links found inside are removed as links; their targets are never entered. OS errors while deleting raise."""
    p = str(path)
    if not os.path.lexists(p):
        return True
    if is_link(p):
        return False
    lex, real = _norm(p), _real(p)
    if not any(_within(lex, _norm(r)) and _within(real, _real(r)) for r in allowed_roots):
        return False
    for pr in protected:
        for mine, theirs in ((lex, _norm(pr)), (real, _real(pr))):
            if _within(theirs, mine, strict=False) or _within(mine, theirs, strict=False):
                return False
    if os.path.isdir(p):
        if _has_marker(p):
            return False
        _delete(p)
    else:
        if os.path.basename(p) == CLIENT_MARKER:
            return False
        _unlink(p)
    return True


# --------------------------------------------------------------------------------------------- child processes
def log_output(log: Log, text: str) -> None:
    """A child's output goes to the log file only (indented), never to the console."""
    if log.path and text.strip():
        with open(log.path, "a", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"    | {line}\n" for line in text.rstrip().splitlines()))


def run_cmd(ctx: "Ctx", cmd: list, timeout: int, cwd: Optional[Path] = None, *, split: bool = False) -> tuple:
    """Run a child with the engine environment, no stdin, output captured into the log. (exit code, output);
    124 = timed out, 127 = could not start. split=True returns stdout alone (stderr still goes to the log)."""
    cmd = [str(c) for c in cmd]
    ctx.log.info("run " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    err = ""
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE if split else subprocess.STDOUT,
                           env=ctx.paths.child_env(), cwd=str(cwd) if cwd else None, timeout=timeout)
        out, rc = r.stdout.decode("utf-8", "replace"), r.returncode
        err = (r.stderr or b"").decode("utf-8", "replace") if split else ""
    except subprocess.TimeoutExpired as e:
        out = (e.output or b"").decode("utf-8", "replace") + f"\n(timed out after {timeout} s)"
        rc = 124
    except OSError as e:
        out, rc = f"cannot start {cmd[0]}: {e}", 127
    log_output(ctx.log, out + ("\n" + err if err.strip() else ""))
    return rc, out


def tail(out: str) -> str:
    lines = [x for x in out.strip().splitlines() if x.strip()]
    return lines[-1].strip()[:300] if lines else ""


def move_aside_and_replace(staged: Path, final: Path, root: Path) -> None:
    """Rename `staged` to `final`; an existing `final` is moved aside first, put back if the rename fails, and deleted
    (safe_rmtree inside `root`) once the new one is in place."""
    old = None
    if os.path.lexists(final):
        old = final.with_name(f"{final.name}.old-{os.getpid()}")
        if os.path.lexists(old) and not safe_rmtree(old, [root]):
            raise OSError(f"cannot clear {old}")
        _replace(final, old)
    try:
        _replace(staged, final)
    except OSError:
        if old is not None:
            _replace(old, final)
        raise
    if old is not None and not safe_rmtree(old, [root]):
        raise OSError(f"cannot remove the replaced {old}")


# --------------------------------------------------------------------------------------------- steps
@dataclass
class StepResult:
    name: str
    status: Literal["ok", "skipped", "amber", "red"]
    detail: str = ""
    needs_you: Optional[str] = None  # one line the editor must act on (shown in the final summary)


@dataclass
class Ctx:
    paths: Paths
    log: Log
    components: dict
    state: State
    plugin_root: Path
    platform: str
    args: argparse.Namespace
    runtime_python: Optional[Path] = None  # set by the runtime step
    facts: dict = field(default_factory=dict)  # what preflight / gpu / adobe found
    answers: dict = field(default_factory=dict)  # the editor's answers (questions step)


StepFn = Callable[[Ctx], StepResult]


def run_steps(ctx: Ctx, steps, status: Optional[dict] = None) -> list:
    """Run (name, fn, needs) in order. A step whose `needs` are not all `ok` is skipped ("needs <name>"); a name in
    --skip is skipped (unless the step function has `handles_skip = True`: then it is called and says itself what was
    skipped); an exception is `red` (traceback in the log) and later independent steps still run. In a dry run a need
    that was only `skipped` (it said what it would do) does not stop the step, so every step says what it would do.
    A red step is recorded in state.json so the next run does it again; ok steps record their own fingerprint.
    `status` may carry the outcome of steps run before (a second batch of the same install)."""
    skip = set(getattr(ctx.args, "skip", None) or ())
    dry = bool(getattr(ctx.args, "dry_run", False))
    results, status = [], dict(status or {})
    for name, fn, needs in steps:
        ctx.log.step(name)
        missing = [n for n in needs if status.get(n) != "ok" and not (dry and status.get(n) == "skipped")]
        if name in skip and not getattr(fn, "handles_skip", False):
            r = StepResult(name, "skipped", "skipped with --skip")
        elif missing:
            r = StepResult(name, "skipped", "needs " + ", ".join(missing))
        else:
            try:
                r = fn(ctx)
                if not isinstance(r, StepResult) or r.status not in STATUSES:
                    r = StepResult(name, "red", f"internal error: step returned {r!r}")
                elif r.name != name:
                    r = StepResult(name, r.status, r.detail, r.needs_you)
            except Exception as e:  # noqa: BLE001 - one broken step must not stop the others
                ctx.log.exception(f"{name} failed: {type(e).__name__}: {e}")
                r = StepResult(name, "red", f"{type(e).__name__}: {e}")
        if r.status == "red":
            try:
                ctx.state.record(name, "red", None, r.detail)
            except OSError as e:
                ctx.log.warn(f"could not update state.json: {e}")
        line = f"{name}: {r.status}" + (f" - {r.detail}" if r.detail else "")
        {"red": ctx.log.error, "amber": ctx.log.warn}.get(r.status, ctx.log.info)(line)
        if r.needs_you:
            ctx.log.warn(f"{name}: you need to: {r.needs_you}")
        status[name] = r.status
        results.append(r)
    return results
