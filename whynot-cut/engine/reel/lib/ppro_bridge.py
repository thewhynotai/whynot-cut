"""Python side of the WhyNot Cut Bridge (one CEP bundle for Premiere and After Effects; this module is the Premiere side): install, status, submit jobs, wait for results.

Premiere has no scripting entry point from outside (macOS AppleScript exposes only capture/editoriginal; Windows has
no COM API), so scripts can't be sent to Premiere directly. The bridge panel (templates/premiere/cep_bridge) runs
inside Premiere on macOS and Windows and executes ONLY scripts from <engine home>/ppro-scripts. The plugin's install path changes on every
update, so `install()`/`sync_scripts()` copy the plugin's JSX there (hash-checked before every job).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .common import TEMPLATES_DIR, current_context
from . import plat

EXT_ID = "ai.thewhynot.cut.bridge"
LEGACY_EXT_IDS = ("com.nh.bridge",)          # reel-editor 1.x bridge; replaced on install
BRIDGE_VERSION = "3.1.1"          # the CEP bundle (manifest + bridge.js); the running one must match
LIB_SRC = TEMPLATES_DIR / "premiere/nh_ppro_lib.jsx"


# Locations resolve on every call (3.0 T2.17, engine MI-8): an engine home changed after import is honoured.
def ext_dir() -> Path:
    """The installed CEP bundle: <CEP extensions>/ai.thewhynot.cut.bridge."""
    return plat.cep_extensions_dir() / EXT_ID


def queue_dir() -> Path:
    """<engine home>/ppro-queue; the engine home of the bound Context (`reel serve` binds one per request)."""
    return current_context().engine_home / "ppro-queue"


def scripts_dir() -> Path:
    """The bridge's whitelisted script folder (<engine home>/ppro-scripts)."""
    return current_context().engine_home / "ppro-scripts"


def lib_path() -> Path:
    return scripts_dir() / LIB_SRC.name


_LIVE = {"QUEUE": "queue_dir", "SCRIPTS": "scripts_dir", "EXT_DIR": "ext_dir", "LIB": "lib_path"}


def __getattr__(name: str):
    # Back-compat for one release (3.0): these were constants computed at import (engine MI-8). They now resolve per
    # call from the live engine home; new code calls the functions. Remove in 3.1.
    if name in _LIVE:
        return globals()[_LIVE[name]]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def sync_scripts() -> dict:
    """Copy the plugin's Premiere JSX into the bridge's whitelisted folder when it differs."""
    scripts, lib = scripts_dir(), lib_path()
    scripts.mkdir(parents=True, exist_ok=True)
    try:
        scripts.chmod(0o700)
    except OSError:
        pass
    changed = _sha(LIB_SRC) != _sha(lib)
    if changed:
        tmp = lib.with_suffix(".tmp")
        shutil.copy2(LIB_SRC, tmp)
        tmp.replace(lib)
    return {"scripts_dir": str(scripts), "synced": changed, "sha256": _sha(lib)[:12]}


def installed_version() -> str | None:
    """The installed bundle's version: bridge-config.json "version", else the manifest's ExtensionBundleVersion."""
    ext = ext_dir()
    try:
        v = json.loads((ext / "bridge-config.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        v = None
    if not v:
        try:
            m = re.search(r'ExtensionBundleVersion="([^"]+)"', (ext / "CSXS/manifest.xml").read_text(encoding="utf-8"))
            v = m.group(1) if m else None
        except OSError:
            v = None
    return v


def _ver(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])


def install(force: bool = False) -> dict:
    EXT_DIR, QUEUE = ext_dir(), queue_dir()
    refused = plat.sandbox_refusal("install the bridge", EXT_DIR, QUEUE, scripts_dir())     # G79: never in tests
    if refused:
        return refused
    cur = installed_version()
    if cur and not force and _ver(cur) > _ver(BRIDGE_VERSION):
        # an older plugin (e.g. `reel setup` from 2.1.1) must not put its bridge back over a newer one
        return {"installed": str(EXT_DIR), "skipped": True, "installed_version": cur, "version": BRIDGE_VERSION,
                "detail": f"installed bridge {cur} is newer than {BRIDGE_VERSION} (this plugin's): kept it. "
                          "`reel ppro-install --force` replaces it."}
    src = TEMPLATES_DIR / "premiere/cep_bridge"
    EXT_DIR.parent.mkdir(parents=True, exist_ok=True)
    if EXT_DIR.exists():
        shutil.rmtree(EXT_DIR)
    shutil.copytree(src, EXT_DIR)
    # tells the panel where the queue lives (the engine home can be a custom folder; Premiere doesn't see our env)
    base = str(current_context().engine_home.resolve())
    (EXT_DIR / "bridge-config.json").write_text(json.dumps({"base": base, "version": BRIDGE_VERSION}), encoding="utf-8")
    removed = []
    for old in LEGACY_EXT_IDS:          # only our own earlier bridge, never anything else in the CEP folder
        od = EXT_DIR.parent / old
        manifest = od / "CSXS/manifest.xml"
        if manifest.exists() and "Reel Editor Bridge" in manifest.read_text(encoding="utf-8", errors="replace"):
            shutil.rmtree(od)
            removed.append(str(od))
    QUEUE.mkdir(parents=True, exist_ok=True)
    try:
        QUEUE.chmod(0o700)
    except OSError:
        pass
    sync = sync_scripts()
    dbg = plat.player_debug_mode()
    ok = plat.debug_mode_ok(dbg)
    return {"installed": str(EXT_DIR), "queue": str(QUEUE), "scripts": sync, "legacy_bridges_removed": removed,
            "PlayerDebugMode": dbg, "debug_mode_ok": ok,
            "editor_must_run": [] if ok else plat.debug_mode_commands(),
            "next": ("Restart Premiere and After Effects if they were running during install (the bridge starts by itself "
                     "in both; the visible panel is Window > Extensions > WhyNot Cut Bridge).") if ok else
                    ("PlayerDebugMode is off, so Premiere will not load the bridge. The editor runs the commands in "
                     "'editor_must_run' themselves (an Adobe preference; WhyNot Cut never changes it), then restarts Premiere.")}


def status(max_age_s: float = 5.0) -> dict:
    from . import cep_queue
    return cep_queue.status(queue_dir(), max_age_s, app="Premiere")


def submit(action: str, data: dict | None = None, timeout: float = 600, script: Path | None = None) -> dict:
    """Run `action` in Premiere through the bridge; `script` defaults to the synced nh_ppro_lib.jsx. `timeout` runs from
    the moment the bridge claims the job (cep_queue.submit); a running bridge of another version is refused."""
    from . import cep_queue
    refused = plat.sandbox_refusal(f"queue the {action} job", queue_dir(), scripts_dir())   # G79: never in tests
    if refused:
        return refused
    try:
        st = status()      # through this module, so callers/tests that patch ppro_bridge.status keep working
        if not st["alive"]:
            return {"ok": False, "error": "bridge not running", "status": st}
        if script is None or Path(script) == lib_path():
            sync_scripts()
            script = lib_path()
    except BaseException as e:      # nothing is queued yet: the job cannot run (T2.15; ppro_build reads the flag)
        cep_queue._flag_claimed(e, False)
        raise
    return cep_queue.submit(queue_dir(), script, action, data, timeout, st=st, app="Premiere",
                            expect_version=BRIDGE_VERSION)


def build_lock(what: str, **kw):
    """One Premiere build at a time on this machine (ppro-build, ppro-frames): cep_queue.build_lock on ppro-queue."""
    from . import cep_queue
    return cep_queue.build_lock(queue_dir(), what, **kw)
