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


def saved_client_roots(paths) -> list:
    """The saved clients folders: clients_root of the preferences file and of the pointer (absolute)."""
    from .system import read_preferences  # (at call time: system imports this module)
    roots = [read_preferences(paths).get("clients_root")]
    ptr = read_pointer(paths.options_file)
    roots.append(ptr.get("clients_root") if ptr is not None else None)
    return [saved_path(r, paths.home) for r in roots if isinstance(r, str) and r.strip()]


def _same_place(a, b) -> bool:
    """same_path, case-insensitively on macOS too (fix round 5, N5: APFS / HFS+ ignore case, normcase does not)."""
    return _fold(_norm(a)) == _fold(_norm(b))


def default_link(whynot, home) -> bool:
    """<home>/.whynot-cut is a link (a junction or symlink), whether or not its target exists."""
    return _same_place(whynot, Path(home) / ".whynot-cut") and is_link(whynot)


def bootstrap_claim(whynot) -> bool:
    """The folder's state.json is exactly the claim the bootstraps write before their downloads (schema 1, plugin
    null, no steps): only then did uv / Python / downloads in it come from the bootstrap."""
    return _json_file(Path(whynot) / "state.json") == {"schema": 1, "plugin": None, "updated_at": None, "steps": {}}


def linked_default_home(whynot, home) -> bool:
    """Addendum F (owner 2026-10-13): the DEFAULT engine home <home>/.whynot-cut may be a directory link (a junction or
    symlink, e.g. to D:\\ClaudeData\\whynot-cut-home). It is used through the link at install and uninstall; the
    link and its target folder are never removed, only WhyNot Cut's own entries inside. Any other home that is a link
    stays refused."""
    return _same_place(whynot, Path(home) / ".whynot-cut") and is_link(whynot) and os.path.isdir(whynot)


# What WhyNot Cut itself puts in an engine home (installer.md R.1 + the engine's own folders, engine/reel/lib plat.py,
# common.py, cep_queue / ae_* and serve/: 2.x venv, the Premiere / After Effects queues and scripts, the AE probe, the
# Whisper bench, ae_render's tmp; fix round 6, R5-1: `reel serve`'s job journal serve/jobs/<id>.json (serve/jobs.py)
# and the active item state/active.json (serve/engine_state.py), engine bookkeeping only - the editor's work lives in
# the client folders). Uninstall --remove-engine deletes ONLY these (plus WhyNot Cut's own models when asked); anything
# else is the editor's and is kept and listed. Names compare exactly (`Bin` is the editor's). The location check does
# NOT use this list (fix round 2: names can be anyone's): see occupied_entries and is_engine_home.
# tests/test_installer.py scans engine/reel for every top-level name it writes under its home against this list.
ENGINE_LAYOUT = ("bin", "python", "runtimes", "current", "ffmpeg", "cuda", "bridge", "state.json", "logs", "cache",
                 "downloads", "fonts", "marketplace", "marketplace.new", "marketplace.prev", ".delete-after-exit",
                 "venv", "ppro-queue", "ppro-scripts", "ae-queue", "ae-scripts", "ae-probe", "ae-capabilities.json",
                 "bench", "tmp", "serve", "state")
ENGINE_LAYOUT_PREFIXES = ("state.json.corrupt-", ".state.json.", ".current.", ".plugin-options.json.",
                          "..delete-after-exit.", ".wnc-write-test")  # set-aside / atomic-write leftovers, the probe
ENGINE_KEPT = ("models", "library")  # models/ unless --remove-models; library/ (licensed packs) always
ENGINE_MARKS = ("state.json", "current")  # read by is_engine_home: their CONTENT must be WhyNot Cut's
_RUNTIME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")  # the engine's runtime id rule (lib/plat.py)
HOME_ROOTS = ("Desktop", "Documents", "Downloads")  # with the user folder itself: never the engine home directly
SUBFOLDER = "WhyNotCut"


TRANSIENT_WAIT_S = 2.0


def transient_copy(name: str) -> bool:
    """Task F1: `<one of WhyNot Cut's own top-level names>.tmp`, case ignored (STATE.JSON.tmp) - what an antivirus or
    indexer scanning a file the uninstall has just written or deleted can leave beside it for a moment. Nothing of
    WhyNot Cut writes such a name. It is only ever waited for (wait_for_transients), never deleted."""
    low = name.lower()
    return low.endswith(".tmp") and low[:-4] in {n.lower() for n in ENGINE_LAYOUT + ENGINE_KEPT + (OPTIONS_FILE,)}


def wait_for_transients(folder, limit: float = TRANSIENT_WAIT_S) -> list:
    """The entries of `folder` (task F1: the uninstall's final "what is left" check), listed again every 0.1 s while
    one of them looks like a transient copy of one of our names (transient_copy), at most `limit` seconds. [] when
    the folder cannot be read."""
    deadline = time.monotonic() + limit
    while True:
        try:
            names = os.listdir(folder)
        except OSError:
            return []
        if not any(transient_copy(n) for n in names) or time.monotonic() >= deadline:
            return names
        time.sleep(0.1)



def wait_gone(path, limit: float = TRANSIENT_WAIT_S) -> bool:
    """Task F1: after a delete that succeeded, Windows keeps listing the name until the last program holding it (an
    antivirus or indexer scanning what was just deleted) lets go. Wait for that, at most `limit` seconds; True once
    the name is gone."""
    deadline = time.monotonic() + limit
    while os.path.lexists(path):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


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


# Fix round 5 (N1) / round 6 (R5-2, R5-3): what `uninstall --remove-engine` keeps of an engine home by default (models/)
# is still WhyNot Cut's - recognised by content, never by the name `models` alone. The model step writes the engine's
# Hugging Face store there (engine/reel/lib/whisper_backends.py _repo_dir): one folder "models--<repo with / as -->"
# per repo. The names come from ONE source, components.json `models.<m>.repo`: every model the installer can offer
# (large-v3, large-v3-turbo, medium, small), their MLX twins and the engine's own fallback repo (tests/test_installer.py
# pins it against whisper_backends.py CT2_REPOS / MLX_REPOS and faster-whisper's table). The bootstraps read the same
# names from the same file (Get-WncModelStoreList / model_stores); they keep no list of their own.
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_MODEL_STORES: Optional[frozenset] = None
# What huggingface_hub itself writes at the top of its cache folder beside the stores (huggingface_hub 1.33, pinned in
# setup/locks: file_download.py .locks, _local_folder.py CACHEDIR.TAG, utils/_shared_blobs.py the Xet shared store
# blobs/ - only with its marker file), and the OS's folder-view files its own cache scan ignores
# (utils/_cache_manager.py FILES_TO_IGNORE). Names compare exactly; a link is never ours. The bootstraps use the same.
HF_DIRS = (".locks",)
HF_FILES = ("CACHEDIR.TAG", ".DS_Store", "Thumbs.db", "desktop.ini")
VIEW_FILES = HF_FILES[1:]
HF_BLOBS, HF_BLOBS_MARKER = "blobs", ".huggingface-shared-blobs"
# library/ (engine/reel/lib/motion_library.py): licensed packs the editor adds, library/motion/<pack>/pack.json - the
# pack manifest is its marker. Kept by every uninstall, never deleted by WhyNot Cut.
LIBRARY, MOTION, PACK_MARK = "library", "motion", "pack.json"


def model_store_names(components) -> frozenset:
    """The store folder names of every `models.<m>.repo` in components.json; a placeholder or a malformed repo
    (anything but owner/name) is left out."""
    models = components.get("models") if isinstance(components, dict) else None
    out = set()
    for v in (models.values() if isinstance(models, dict) else ()):
        repo = v.get("repo") if isinstance(v, dict) else None
        if isinstance(repo, str) and not is_placeholder(repo) and _REPO.match(repo) and ".." not in repo:
            out.add("models--" + repo.replace("/", "--"))
    return frozenset(out)


def use_model_stores(components_path) -> None:
    """The core names its components.json (cli.main, before any guard): the store names come from that file (one that
    cannot be read names none, so nothing is recognised as a leftover)."""
    global _MODEL_STORES
    _MODEL_STORES = model_store_names(_json_file(Path(components_path)))


def model_stores() -> frozenset:
    """The store names in use: the core's components.json, else the plugin's own (<plugin>/setup/components.json)."""
    global _MODEL_STORES
    if _MODEL_STORES is None:
        _MODEL_STORES = model_store_names(_json_file(Path(__file__).resolve().parents[3] / "setup" / "components.json"))
    return _MODEL_STORES


def _real_dir(p) -> bool:
    return not is_link(p) and os.path.isdir(p)


def _real_file(p) -> bool:
    return not is_link(p) and os.path.isfile(p)


def model_entry_kind(models_dir, name: str) -> Optional[str]:
    """What one entry of <engine home>/models is (fix round 6, R5-2): "store" (a model store of WhyNot Cut's: a real
    folder named exactly as in model_stores()), "bookkeeping" (Hugging Face's own .locks / CACHEDIR.TAG / marked blobs/
    store, or an OS folder-view file), or None - the editor's, or a link: never ours, never entered, never deleted."""
    p = Path(models_dir) / name
    if name in model_stores():
        return "store" if _real_dir(p) else None
    if name in HF_DIRS:
        return "bookkeeping" if _real_dir(p) else None
    if name in HF_FILES:
        return "bookkeeping" if _real_file(p) else None
    if name == HF_BLOBS:
        return "bookkeeping" if _real_dir(p) and _real_file(p / HF_BLOBS_MARKER) else None
    return None


def is_our_models(models_dir) -> bool:
    """<engine home>/models is WhyNot Cut's (fix round 6, R5-2): a real folder, EVERY entry of it is one of our stores
    or Hugging Face's own bookkeeping (model_entry_kind), and at least one is a store - or (fix round 7, M6-1) it is
    empty (models_empty: what `reel setup` makes before any model is downloaded; an empty folder cannot lose data). One
    entry of the editor's (their own Hugging Face model beside ours, a note) or any link inside makes the whole folder
    the editor's."""
    if not _real_dir(models_dir):
        return False
    try:
        names = os.listdir(models_dir)
    except OSError:
        return False
    kinds = [model_entry_kind(models_dir, n) for n in names]
    return None not in kinds and ("store" in kinds or all(is_view_file(Path(models_dir) / n) for n in names))


def is_view_file(p) -> bool:
    """An OS folder-view file (.DS_Store, Thumbs.db, desktop.ini) that is a real file (never a folder or a link)."""
    p = Path(p)
    return p.name in VIEW_FILES and _real_file(p)


_view_file = is_view_file


def models_empty(models_dir) -> bool:
    """<engine home>/models is a real folder holding nothing, or only OS folder-view files (fix round 7, M6-1: what
    `reel setup` makes before any model is downloaded; an empty folder cannot lose data, so it counts as ours)."""
    if not _real_dir(models_dir):
        return False
    try:
        return all(is_view_file(Path(models_dir) / n) for n in os.listdir(models_dir))
    except OSError:
        return False


_LINK_HOPS = 40


def _inside(key: str, root_key: str) -> bool:
    return key == root_key or key.startswith(root_key.rstrip("\\/") + os.sep)


def resolve_inside(root, link) -> tuple:
    """Where the link `link` (inside `root`) leads, resolved one path component at a time WITHOUT ever leaving `root`
    (fix round 7, R6-1: nothing outside models/ is ever followed): (the final path, [every link passed]), or (None,
    [the links so far]) when that is not known for sure - a link that cannot be read, a step out of `root`, a loop
    (more than 40 links), or a final that does not exist."""
    root_s = os.path.normpath(os.path.abspath(str(root)))
    root_key = _fold(os.path.normcase(root_s))
    passed: list = []
    start = os.path.normpath(os.path.abspath(str(link)))
    if not _inside(_fold(os.path.normcase(start)), root_key) or start == root_s:
        return None, passed
    parts = os.path.relpath(start, root_s).split(os.sep)
    cur = root_s
    while parts:
        part = parts.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if _fold(os.path.normcase(cur)) == root_key:
                return None, passed  # out of root
            cur = os.path.dirname(cur)
            continue
        nxt = os.path.join(cur, part)
        if not is_link(nxt):
            cur = nxt
            continue
        passed.append(nxt)
        if len(passed) > _LINK_HOPS:
            return None, passed  # a loop
        try:
            t = strip_long_prefix(os.readlink(nxt))
        except (OSError, ValueError):
            return None, passed
        if not t:
            return None, passed
        drive, rest = os.path.splitdrive(t)
        if drive or rest.startswith(("/", "\\")):  # absolute (a junction's target always is)
            t = os.path.normpath(t if drive else os.path.splitdrive(nxt)[0] + t)
            if not _inside(_fold(os.path.normcase(t)), root_key):
                return None, passed
            rel = os.path.relpath(t, root_s)
            parts = ([] if rel == "." else rel.split(os.sep)) + parts
            cur = root_s
        else:
            parts = t.replace("/", os.sep).split(os.sep) + parts  # relative to the link's own folder (cur)
    if not os.path.lexists(cur) or is_link(cur):
        return None, passed
    return cur, passed


_WALK_LIMIT = 200000


def _links_below(top: str) -> tuple:
    """([every link at or below `top`, never entered], complete?) - incomplete when a folder cannot be read or the
    walk passes _WALK_LIMIT entries."""
    if is_link(top):
        return [top], True
    out, seen, ok = [], 0, [True]

    def err(_e):
        ok[0] = False

    for dirpath, dirs, files in os.walk(top, onerror=err):
        seen += len(dirs) + len(files)
        if seen > _WALK_LIMIT:
            return out, False
        for n in list(dirs):
            q = os.path.join(dirpath, n)
            if is_link(q):
                out.append(q)
                dirs.remove(n)  # never entered
        out.extend(q for q in (os.path.join(dirpath, n) for n in files) if is_link(q))
    return out, ok[0]


def models_usage(models_dir, ours: Iterable, theirs: Iterable) -> dict:
    """What the editor's own entries of <engine home>/models use of ours, and which files of Hugging Face's shared Xet
    store (models/blobs/<2 hex>/<hash>, huggingface_hub 1.33 utils/_shared_blobs.py: the REAL bytes; a repo's
    blobs/<etag> and snapshots/<file> are relative symlinks to them) only our stores use (fix round 7, R6-1). Every link
    is resolved inside models/ only (resolve_inside); nothing outside it is ever followed.
    {"blobs": [shared-store files that ONLY `ours` link to - empty when anything of the editor's is ambiguous],
     "used": {our store names a link of the editor's leads into or through}, "ambiguous": bool}."""
    models = os.path.normpath(os.path.abspath(str(models_dir)))
    blobs = os.path.join(models, HF_BLOBS)
    shared = model_entry_kind(models, HF_BLOBS) == "bookkeeping"
    blobs_key = _fold(os.path.normcase(blobs))
    ours = list(ours)
    store_keys = {n: _fold(os.path.normcase(os.path.join(models, n))) for n in ours}

    def in_blobs(p: str) -> bool:
        k = _fold(os.path.normcase(p))
        return shared and k != blobs_key and _inside(k, blobs_key)

    their_blobs, used, ambiguous = set(), set(), False
    for name in theirs:
        links, complete = _links_below(os.path.join(models, name))
        ambiguous = ambiguous or not complete
        for q in links:
            final, passed = resolve_inside(models, q)
            for p in passed[1:] + ([final] if final else []):
                k = _fold(os.path.normcase(p))
                used.update(n for n, sk in store_keys.items() if _inside(k, sk))
            if final is None:
                ambiguous = True
            elif os.path.isdir(final):  # a link to a folder: ambiguous when the shared store is, or is in, it
                k = _fold(os.path.normcase(final))
                ambiguous = ambiguous or (shared and (_inside(k, blobs_key) or _inside(blobs_key, k)))
            elif in_blobs(final):
                their_blobs.add(_fold(os.path.normcase(final)))
    our_blobs = {}
    for name in ours:
        if name in used:
            continue
        links, _complete = _links_below(os.path.join(models, name))
        for q in links:
            final, _passed = resolve_inside(models, q)
            if final and in_blobs(final) and os.path.isfile(final) and not is_link(final):
                our_blobs.setdefault(_fold(os.path.normcase(final)), final)
    out = [] if ambiguous else sorted(p for k, p in our_blobs.items() if k not in their_blobs)
    return {"blobs": out, "used": used, "ambiguous": ambiguous}


def library_state(lib) -> Optional[str]:
    """<engine home>/library (fix round 6): "packs" when it holds only motion/, which holds only pack folders that each
    carry their pack.json (the engine's pack manifest: recognised by content), at least one; "empty" when it holds
    nothing, or only an empty motion/; None otherwise (anything else, any link: the editor's). OS folder-view files
    are ignored at both levels."""
    lib = Path(lib)
    if not _real_dir(lib):
        return None
    try:
        top = [n for n in os.listdir(lib) if not _view_file(lib / n)]
        if not top:
            return "empty"
        if top != [MOTION] or not _real_dir(lib / MOTION):
            return None
        packs = [n for n in os.listdir(lib / MOTION) if not _view_file(lib / MOTION / n)]
    except OSError:
        return None
    if not packs:
        return "empty"
    ok = all(_real_dir(lib / MOTION / n) and _real_file(lib / MOTION / n / PACK_MARK) for n in packs)
    return "packs" if ok else None


def is_kept_leftover(path, *, pointer_ok: bool = False) -> bool:
    """What `uninstall --remove-engine` keeps of an engine home, still WhyNot Cut's own folder for placement at install
    and uninstall (fix round 5, N1; round 6, R5-2 and library/): its only entries (occupied_entries: the write probe,
    the -Source cache and, with `pointer_ok`, the pointer do not count) are the kept names - models/ that is ours
    (is_our_models) and/or library/. library/ counts by its own content (pack manifests: library_state "packs"); an
    empty one only beside our models/, never alone. Never by the names alone, and a link is never ours."""
    occupied = occupied_entries(path, pointer_ok=pointer_ok)
    if not occupied or not set(occupied) <= set(ENGINE_KEPT):
        return False
    p = Path(path)
    models = "models" in occupied and is_our_models(p / "models")
    if "models" in occupied and not models:
        return False
    if LIBRARY not in occupied:
        return models
    lib = library_state(p / LIBRARY)
    return lib == "packs" or (lib == "empty" and models)


def is_our_home(path, *, pointer_ok: bool = False) -> bool:
    """A genuine engine home (is_engine_home) or the recognised leftover of one (is_kept_leftover): WhyNot Cut's own
    folder for placement, at install and at uninstall (fix round 5, N1; round 6)."""
    return is_engine_home(path) or is_kept_leftover(path, pointer_ok=pointer_ok)


def occupied_entries(path, *, pointer_ok: bool = False) -> list:
    """What makes an existing folder the editor's for the placement rule (controller ruling, fix round 2): every entry
    except the bootstraps' write probe (.wnc-write-test*), the -Source cache (a `downloads` folder holding only
    `release-*` folders) and, at the pointer's own place (`pointer_ok`: ~/.whynot-cut), the pointer
    plugin-options.json, and (fix round 7, M6-2) the OS folder-view files .DS_Store / Thumbs.db / desktop.ini when they are
    real files. Names compare exactly. [] when the folder is missing or empty of anything else."""
    try:
        names = os.listdir(path)
    except OSError:
        return []
    out = []
    for n in names:
        if n.startswith(".wnc-write-test") or (pointer_ok and n == OPTIONS_FILE):
            continue
        if is_view_file(Path(path) / n):  # (fix round 7, M6-2) Finder's / Explorer's own file, a real file only
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


MARKER_SCAN_LIMIT = 5000  # entries looked at within 3 levels (bootstrap.ps1 / bootstrap.sh use the same number)


def _marker_scan(top: str, depth: int = 3, limit: int = MARKER_SCAN_LIMIT) -> tuple:
    """(folder holding a `.whynot-client` marker up to `depth` levels below `top`, or None; True when more than
    `limit` entries were met before the walk ended - a huge folder is not walked whole). Links are never entered."""
    seen, stack = 0, [(top, 0)]
    while stack:
        d, lvl = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    seen += 1
                    if seen > limit:
                        return None, True
                    if e.name == CLIENT_MARKER:
                        return d, False
                    if lvl < depth and not is_link(e.path) and e.is_dir(follow_symlinks=False):
                        stack.append((e.path, lvl + 1))
        except OSError:
            continue
    return None, False


def _marker_below(top: str, depth: int = 3, limit: int = MARKER_SCAN_LIMIT) -> Optional[str]:
    """A `.whynot-client` marker up to `depth` levels below `top` (the chosen-folder rule: past the limit, None)."""
    return _marker_scan(top, depth, limit)[0]


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
    pointer_ok = _norm(Path(home) / ".whynot-cut") == n  # the SessionStart hook's pointer lives there
    existing = is_our_home(p, pointer_ok=pointer_ok)  # (fix round 5, N1: also the leftover of an uninstall)
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
    if not existing and (any(_norm(r) == n for r in roots) or occupied_entries(p, pointer_ok=pointer_ok)):
        final = Path(p) / SUBFOLDER
        note = (f"{p} already holds other files, so WhyNot Cut goes into its own folder {final} (uninstall then "
                "never touches the rest)")
    f = _norm(final)
    if _within(_norm(home), f, strict=False):
        return None, "", f"{final} is your user folder or holds it; choose a folder of its own"
    if _within(f, _norm(Path(home) / ".claude"), strict=False):
        return None, "", f"{final} is inside Claude's folder {Path(home) / '.claude'}"
    if final != Path(p) and not is_our_home(final) and occupied_entries(final):
        return None, "", f"{final} already holds other files; choose an empty folder or one of its own"
    if sandbox_home is not None and not _within(f, _norm(sandbox_home), strict=True):
        return None, "", f"{final} is outside the sandbox home {sandbox_home} (--home: nothing outside it is used)"
    return final, note, None


def engine_home_choice_problem(path, **kw) -> Optional[str]:
    """Why `path` cannot be used as (or moved into a WhyNotCut subfolder for) the engine home, else None."""
    return choose_engine_home(path, **kw)[2]


def uninstall_engine_home(path, *, home, plugin_root, clients_roots: Iterable = (), known: Iterable = (),
                          sandbox_home=None) -> tuple:
    """Fix round 5 (N3): the folder an uninstall was given (-EngineHome / --engine-home): (final folder or None, note
    or "", problem or None). The bootstraps apply the same rule (Get-WncUninstallPlace / uninstall_place) before they
    write anything (log, uv, Python), so the log, the deferred list and the core all use the one final folder.

    The folder must be a full path, exist, not be a link (the linked ~/.whynot-cut that is the resolved home is passed
    as the resolved home, not as a chosen folder: N2), not be a drive root / mount point or inside the plugin folder.
    It must be WhyNot Cut's own (is_our_home: a genuine engine home or the leftover of an uninstall). When it is not,
    but install would have put WhyNot Cut into its WhyNotCut subfolder (the user folder, Desktop, Documents, Downloads,
    or a folder holding the editor's files) and <it>/WhyNotCut is WhyNot Cut's own, that subfolder is used (the note
    says so). The final folder must not be or hold the user folder, lie inside Claude's folder or (sandbox) outside the
    sandbox home, and must pass the resolved-home guard in uninstall mode (resolved_home_problem: drive root, the user
    folder, Desktop / Documents / Downloads themselves, a link)."""
    p = str(path or "").strip()
    if not p or not os.path.isabs(p) or (os.name == "nt" and not re.match(r"^([A-Za-z]:[\\/]|[\\/]{2})", p)):
        return None, "", f"{p or '(empty)'} is not a full path (for example C:\\WhyNotCut or /Users/you/WhyNotCut)"
    p = strip_long_prefix(p)
    if re.match(r"^[\\/]{2}", p):
        return None, "", f"{p} is a network share or device path; name a folder on a local drive"
    if _is_drive_root(p):
        return None, "", f"{p} is a drive root or a mounted volume, never a WhyNot Cut engine folder"
    if is_link(p):
        return None, "", (f"{p} is a link or mount point; name the real folder (leave -EngineHome / --engine-home out "
                          "when it is your ~/.whynot-cut)")
    if not os.path.isdir(p):
        return None, "", f"{p} does not exist; name the folder WhyNot Cut was installed in"
    n, h = _norm(p), Path(home)
    if _within(n, _norm(plugin_root), strict=False):
        return None, "", f"{p} is inside the plugin folder {plugin_root}, never a WhyNot Cut engine folder"
    pointer_ok = n == _norm(h / ".whynot-cut")
    final, note = Path(p), ""
    if not is_our_home(p, pointer_ok=pointer_ok):
        sub = Path(p) / SUBFOLDER
        roots = [h] + [h / r for r in HOME_ROOTS] + [f for _name, f in known]
        moved_in = any(_norm(r) == n for r in roots) or bool(occupied_entries(p, pointer_ok=pointer_ok))
        if not (moved_in and not is_link(sub) and os.path.isdir(sub) and is_our_home(sub)):
            return None, "", (f"{p} is not a WhyNot Cut engine folder (no state.json or `current` of WhyNot Cut's, no "
                              f"Whisper models of its own) and has no {SUBFOLDER} folder of WhyNot Cut's in it; name "
                              "the folder WhyNot Cut was installed in")
        final = sub
        note = (f"{p} is not a WhyNot Cut engine folder, but {sub} is (an install named {p} put WhyNot Cut there): "
                f"uninstalling from {sub}")
    f = _norm(final)
    if _within(_norm(h), f, strict=False):
        return None, "", f"{final} is your user folder or holds it"
    if _within(f, _norm(h / ".claude"), strict=False):
        return None, "", f"{final} is inside Claude's folder {h / '.claude'}"
    if sandbox_home is not None and not _within(f, _norm(sandbox_home), strict=True):
        return None, "", f"{final} is outside the sandbox home {sandbox_home} (--home: nothing outside it is used)"
    why = resolved_home_problem(final, home=h, clients_roots=clients_roots, known=known, mode="uninstall")
    if why:
        return None, "", f"{final} is {why}"
    return final, note, None


# the way out of a refused RESOLVED engine home, in the editor's words (both front ends' flags; task 9)
SELF_FIX = "run the installer again with -EngineHome <folder> / --engine-home <folder>"
# a link ~/.whynot-cut that cannot be used (fix round 4): the extra way out, in Arabic
# (fix round 5, N1: never "point it at your old WhyNot Cut folder" - the link may already name that one)
LINK_FIX_AR = ("الرابط ~/.whynot-cut يشير إلى مجلد لا يصلح أو غير موجود: أعد توصيل القرص، أو احذف الرابط، أو وجّهه "
               "إلى مجلد فارغ خاص به، أو شغّل المثبّت مرة أخرى مع -EngineHome <folder>. وإن كان هو مجلد WhyNot Cut "
               "القديم نفسه وفيه ملفات أخرى لك، فانقلها خارجه ثم شغّل المثبّت مرة أخرى.")
LINK_FIX = ("remove the link, or point ~/.whynot-cut at an empty folder of its own, or run again with -EngineHome "
            "<folder> / --engine-home <folder>")
# fix round 5 (N3): an uninstall given a folder that is not WhyNot Cut's
UNINSTALL_FIX = ("name the folder WhyNot Cut was installed in with -EngineHome <folder> / --engine-home <folder>, or "
                 "leave it out to use the saved one")
UNINSTALL_FIX_AR = ("لا يمكن إلغاء التثبيت من هذا المجلد. اكتب بعد -EngineHome <folder> (على macOS: --engine-home "
                    "<folder>) المجلد الذي ثُبّت فيه WhyNot Cut، أو احذف هذا الخيار ليُستخدم المجلد المحفوظ.")
UNINSTALL_SUBFOLDER_AR = ("هذا المجلد ليس مجلد WhyNot Cut، لكن المجلد WhyNotCut داخله هو مجلده (ثبّته هناك تثبيت "
                          "سابق)، لذلك سيُلغى التثبيت منه.")
# fix round 6 (R5-2): --remove-models deleted only WhyNot Cut's own models; models/ stays for the editor's own files
MODELS_KEPT_AR = ("حُذفت نماذج WhyNot Cut وحدها. بقي المجلد models لأن فيه ملفات ليست من WhyNot Cut (نماذجك أنت "
                  "مثلًا)، ولم يُلمس منها شيء.")
# fix round 7 (R6-1): the editor's model beside ours uses Hugging Face's shared files (blobs/, .locks, CACHEDIR.TAG)
MODELS_SHARED_KEPT_AR = ("بقيت ملفات Hugging Face المشتركة في المجلد models (مثل blobs و.locks وCACHEDIR.TAG) لأن "
                         "نماذجك تستخدمها، ولم يُحذف منها إلا ما كانت تستخدمه نماذج WhyNot Cut وحدها.")
MODELS_STORE_USED_AR = "وبقي أيضًا نموذج من نماذج WhyNot Cut لأن ملفًا من ملفاتك يشير إليه."
# fix round 7 (M6-4): --remove-models on a models/ that is itself a link
MODELS_LINK_AR = "كان المجلد models رابطًا: حُذف الرابط وحده، ولم يُلمس المجلد الذي يشير إليه."
# fix round 7 (M6-3): the -Source release could not be kept in the engine home (the bootstraps print the same line)
CACHE_FAIL_AR = ("تعذّر حفظ ملفات WhyNot Cut في مجلد المحرك (غالبًا لأن القرص ممتلئ)، فلم يُثبَّت شيء. وفّر مساحة ثم "
                 "شغّل المثبّت مرة أخرى.")
# fix round 5 (N6): ~/.whynot-cut was pointed elsewhere while the uninstall ran
LINK_MOVED_AR = ("تغيّر المجلد الذي يشير إليه الرابط ~/.whynot-cut أثناء الإلغاء، لذلك لم يُحذف شيء آخر. تحقّق من "
                 "الرابط ثم شغّل الإلغاء مرة أخرى.")
SELF_FIX_AR = ("لن يستخدم WhyNot Cut هذا المجلد لملفات التشغيل. لإصلاح ذلك شغّل المثبّت مرة أخرى مع "
               "-EngineHome <folder> (على macOS: --engine-home <folder>) واختر مجلدًا خاصًا به.")


# Windows shell folders that Known Folder Move (OneDrive) or the user may have moved: (name, User Shell Folders value)
SHELL_FOLDERS = (("Desktop", "Desktop"), ("Documents", "Personal"),
                 ("Downloads", "{374DE290-123F-4565-9164-39C4925E467B}"))


def shell_folders(home, sandbox: bool) -> list:
    """(name, folder) of the user's Desktop / Documents / Downloads: <home>/<name>, and on real Windows (never in a
    sandbox) also where HKCU User Shell Folders puts them (OneDrive Known Folder Move, a moved Documents)."""
    out = [(n, Path(home) / n) for n in HOME_ROOTS]
    if sandbox or os.name != "nt":
        return out
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            for name, value in SHELL_FOLDERS:
                try:
                    v = winreg.QueryValueEx(k, value)[0]
                except OSError:
                    continue
                if isinstance(v, str) and v.strip():
                    out.append((name, Path(os.path.expandvars(v.strip()))))
    except OSError:
        pass
    return out


def strip_long_prefix(p: str) -> str:
    """\\\\?\\C:\\x (the long-path prefix) is C:\\x; any other \\\\?\\ / \\\\.\\ form is kept (and refused)."""
    m = re.match(r"^[\\/]{2}[?.][\\/]([A-Za-z]:([\\/].*)?)$", p)
    return m.group(1) if m else p


def _fold(key: str) -> str:
    """macOS disks (APFS / HFS+) compare names case-insensitively, but normcase does not fold there: fold it here."""
    return key.lower() if sys.platform == "darwin" else key


def _place_keys(p) -> set:
    """The ways one folder is named: as written (normalised) and with every link on the way resolved."""
    keys = {_fold(_norm(p))}
    try:
        keys.add(_fold(_real(p)))
    except (OSError, ValueError):
        pass
    return keys


def resolved_home_problem(path, *, home, clients_roots: Iterable = (), known: Iterable = (),
                          mode: str = "install") -> Optional[str]:
    """Why a RESOLVED engine home (named by a variable, the pointer or settings.json pluginConfigs; never chosen in
    this run) may not be used, else None (task 9, carried from the Task 8 review: controller rulings). ~/.whynot-cut
    itself is never refused here. Refused: a link or reparse point itself (a junction, symlink or folder mount point);
    a drive root or mount point; the user folder itself, or Desktop, Documents, Downloads themselves (`known`: also
    where Windows' shell folders put them; a folder inside them is fine); a folder holding client data - the saved
    clients folder (it is or holds it) or a `.whynot-client` marker in it or up to 3 levels below - and a folder too
    big to check for that (more than MARKER_SCAN_LIMIT entries within 3 levels). Every comparison is made both as
    written and with links resolved (realpath), and case-insensitively on macOS too. A genuine 2.x / 3.0 home anywhere
    else is used as it is. ~/.whynot-cut that is a LINK (Addendum F) is checked by where it points (fix round 3): the
    same rules on its real target, so a link to Documents, the user folder, a drive root or a client folder is refused
    at install and uninstall alike. The bootstraps apply the same rule (Get-WncResolvedHomeProblem /
    resolved_home_problem) before anything is downloaded, and again before their deferred delete.

    Fix round 4 (controller rulings): a linked ~/.whynot-cut is also placed like a CHOSEN folder - its target must not
    hold the user folder, lie inside a client folder (below a `.whynot-client` marker or under the saved clients
    folder), nor hold anything while not being a genuine engine home (`occupied_entries` / `is_engine_home`); a dangling
    link is refused. `mode`: "install" (every rule), "uninstall" (a genuine engine home is not refused for client data
    inside it: uninstall deletes only WhyNot Cut's own entries by exact name), "deferred" (the bootstraps' re-check
    before deleting python/ and bin/: no "occupied" rule, what is left there after the uninstall is ours)."""
    p, h = strip_long_prefix(str(path)), Path(home)
    if re.match(r"^[\\/]{2}", p):  # \\.\..., \\?\UNC\..., \\server\share, \\localhost\C$ (fix round 2)
        return "a network share or device path; name a folder on a local drive"
    default = _fold(_norm(p)) == _fold(_norm(h / ".whynot-cut"))
    if default and not is_link(p):
        return None
    if not default and is_link(p):
        return "a link or mount point (a junction, symlink or mounted folder); name the real folder instead"
    clients_roots = [c for c in clients_roots if c]
    if default and not os.path.isdir(p):
        return (f"a link to a folder that does not exist ({os.path.realpath(p)}) - reconnect the drive or remove the "
                "link")
    genuine = os.path.isdir(p) and is_our_home(p, pointer_ok=default)  # (fix round 5, N1: the leftover too)
    # (a linked ~/.whynot-cut keeps every client rule at uninstall too: its target may be anyone's folder)
    why = _place_problem(p, h, clients_roots, known,
                         client_checks=not (mode == "uninstall" and genuine and not default))
    if not why and default:
        why = _linked_target_problem(os.path.realpath(p), h, clients_roots, genuine, mode)
    if why and default:
        return f"a link to {os.path.realpath(p)}, which is {why.removeprefix('a link to ')} - {LINK_FIX}"
    return why


def _linked_target_problem(real: str, h: Path, clients_roots: list, genuine: bool, mode: str) -> Optional[str]:
    """The chosen-folder placement rules for the target of a linked ~/.whynot-cut (fix round 4): it may not hold the
    user folder, lie inside a client folder or the saved clients folder, nor (install / uninstall) hold anything while
    not being a genuine engine home - a WhyNotCut subfolder cannot be made there, the link name is ours."""
    r = _fold(_norm(real))
    if any(_within(k, r) for k in _place_keys(h)):
        return "a folder that holds your user folder"
    cur = Path(real)
    while cur.parent != cur:
        cur = cur.parent
        if (cur / CLIENT_MARKER).exists():
            return f"inside a client folder ({cur} holds {CLIENT_MARKER})"
    for c in clients_roots:
        if any(_within(r, ck) for ck in _place_keys(c)):
            return f"inside your clients folder {c}"
    if mode != "deferred" and not genuine:
        occupied = occupied_entries(real, pointer_ok=True)
        if occupied:
            return (f"a folder that already holds other files ({', '.join(occupied[:3])}"
                    + (", ..." if len(occupied) > 3 else "") + ") and is not a WhyNot Cut engine folder (if it is "
                    "your old WhyNot Cut folder, move your own files out of it and run again)")
    return None


def _place_problem(p: str, h: Path, clients_roots: Iterable, known: Iterable,
                   client_checks: bool = True) -> Optional[str]:
    """resolved_home_problem's checks of where `p` really is (as written and with links resolved)."""
    keys = _place_keys(p)
    if _is_drive_root(p) or any(_is_drive_root(k) for k in keys):
        return "a drive root or a mount point"
    if keys & _place_keys(h):
        return "your user folder itself"
    for name, folder in list(shell_folders(h, True)) + list(known):
        if keys & _place_keys(folder):
            return f"your {name} folder itself"
    if not client_checks:  # (uninstall of a genuine engine home: client folders inside it are never deleted)
        return None
    for c in clients_roots:
        if c and any(_within(ck, k, strict=False) for ck in _place_keys(c) for k in keys):
            return f"your clients folder {c}, or it holds it"
    if os.path.isdir(p):
        below, too_big = _marker_scan(os.path.realpath(p))
        if below:
            return f"holding a client folder ({below} holds {CLIENT_MARKER})"
        if too_big:
            return (f"too big to check for client folders (more than {MARKER_SCAN_LIMIT} entries within 3 levels); "
                    "choose an engine folder of its own with -EngineHome / --engine-home")
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
        _drop_tmp(tmp)


def _drop_tmp(tmp: Path, tries: int = 6) -> None:
    """Remove a leftover atomic-write tmp, retried briefly like _replace (task F1: an antivirus or indexer can hold a
    fresh file for a moment); a last failure is ignored (the writer's own error, if any, matters more)."""
    for i in range(tries):
        if not os.path.lexists(tmp):
            return
        try:
            os.unlink(tmp)
            return
        except PermissionError:
            if i < tries - 1:
                time.sleep(0.1 * (i + 1))
        except OSError:
            return


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


def stand_in_command(path) -> list:
    """A command list for a program given by path, test stand-ins included: a `.py` runs on this interpreter, a `.sh`
    runs with `bash` (the way bootstrap.sh runs a .sh WNC_TEST_UV), anything else is started as itself. A stand-in is
    never exec'd as a script: git keeps the fixtures 100644, so exec'ing one fails with EACCES on macOS/Linux
    (Windows never checks the bit)."""
    p = str(path)
    low = p.lower()
    if low.endswith(".py"):
        return [sys.executable, "-B", p]
    if low.endswith(".sh"):
        return ["bash", p]
    return [p]


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
