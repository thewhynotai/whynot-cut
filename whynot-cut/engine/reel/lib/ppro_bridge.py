"""Python side of the WhyNot Cut Bridge (one CEP bundle for Premiere and After Effects; this module is the Premiere side): install, status, submit jobs, wait for results.

Premiere has no scripting entry point from outside (macOS AppleScript exposes only capture/editoriginal; Windows has
no COM API), so scripts can't be sent to Premiere directly. The CEP bundle (adobe/cep-bridge, assembled by
lib/cep_bundle.py) runs a hidden daemon inside Premiere on macOS and Windows. Bundle 3.0.0 carries the libraries itself
(jobs name `lib`); the legacy 3.1.1 bridge executes ONLY scripts from <engine home>/ppro-scripts, so for it
`sync_scripts()` copies the plugin's JSX there before every job (removed with the legacy family in 3.1).
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .common import TEMPLATES_DIR, current_context
from . import cep_bundle, plat

EXT_ID = "ai.thewhynot.cut.bridge"
LEGACY_EXT_IDS = ("com.nh.bridge",)          # reel-editor 1.x bridge; replaced on install
BRIDGE_VERSION = cep_bundle.PRODUCT   # "3.0.0": the CEP bundle (manifest + bridge.js BUNDLE + build.json product)
LIB_SRC = TEMPLATES_DIR / "premiere/wnc_ppro_lib.jsx"


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
    """The installed bundle's version (either family): cep_bundle.installed()."""
    return (cep_bundle.installed(ext_dir()) or {}).get("version")


def install(force: bool = False) -> dict:
    """Install the CEP bundle from `cep_bundle.source_dir()` by the install rule (cep_bundle.decide_install) and write
    ~/.whynot-cut/bridge/config.json (never a file inside the extension). A plugin build without that source (a shipped
    plugin) returns ok:false with a `how` and leaves the installed extension as it is."""
    EXT_DIR, QUEUE = ext_dir(), queue_dir()
    refused = plat.sandbox_refusal("install the bridge", EXT_DIR, QUEUE, cep_bundle.config_path())   # G79: never in tests
    if refused:
        return refused
    if not cep_bundle.has_source():                                    # before anything is removed
        return {"ok": False, "error": "this plugin build carries no WhyNot Cut extension",
                "how": "install WhyNot Cut with its installer (the signed extension comes with it)"}
    done = cep_bundle.install_source(EXT_DIR, force=force)
    cfg = cep_bundle.write_config(current_context().engine_home, written_by="engine")
    if done["action"] == "keep":
        # an older plugin (e.g. `reel setup` from 2.2.1) must not put its extension back over a newer or signed one
        cur = done["installed"] or {}
        return {"installed": str(EXT_DIR), "skipped": True, "installed_version": cur.get("version"),
                "version": BRIDGE_VERSION, "config": str(cfg),
                "detail": f"{done['reason']}: kept it. `reel ppro-install --force` replaces it."}
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
    dbg = plat.player_debug_mode()
    ok = plat.debug_mode_ok(dbg)
    inst = done["installed"] or {}
    return {"installed": str(EXT_DIR), "action": done["action"], "reason": done["reason"],
            "version": inst.get("version"), "build": inst.get("build"), "config": str(cfg), "queue": str(QUEUE),
            "legacy_bridges_removed": removed, "PlayerDebugMode": dbg, "debug_mode_ok": ok,
            "editor_must_run": [] if ok else plat.debug_mode_commands(),
            "next": ("Restart Premiere and After Effects if they were running during install (WhyNot Cut starts by itself "
                     "in both; in After Effects its panel is Window > Extensions (Legacy) > WhyNot Cut).") if ok else
                    ("PlayerDebugMode is off, so Premiere will not load WhyNot Cut. The editor runs the commands in "
                     "'editor_must_run' themselves (an Adobe preference; WhyNot Cut never changes it), then restarts Premiere.")}


def status(max_age_s: float = 5.0) -> dict:
    from . import cep_queue
    return cep_queue.status(queue_dir(), max_age_s, app="Premiere")


def submit(action: str, data: dict | None = None, timeout: float = 600, script: Path | None = None) -> dict:
    """Run `action` in Premiere through the bridge. `timeout` runs from the moment the bridge claims the job
    (cep_queue.submit). The mode follows the running bridge (cep_queue.job_mode): the bundle with this engine's
    libraries runs its own `lib=wnc_ppro_lib.jsx`; the legacy 3.1.1 (and a dev bundle of another build with
    WHYNOT_BRIDGE_DEV=1) gets the synced library as `script=`; anything else is refused. A `script` other than the
    library is always sent as `script=`."""
    from . import cep_queue
    refused = plat.sandbox_refusal(f"queue the {action} job", queue_dir(), scripts_dir())   # G79: never in tests
    if refused:
        return refused
    lib = None
    try:
        st = status()      # through this module, so callers/tests that patch ppro_bridge.status keep working
        if not st["alive"]:
            return {"ok": False, "error": "bridge not running", "status": st}
        mode = cep_queue.job_mode(st, BRIDGE_VERSION, "Premiere")
        if isinstance(mode, dict):
            return mode                                         # refused: nothing is queued
        if script is None or Path(script) == lib_path():
            if mode == "lib":
                lib, script = LIB_SRC.name, None
            else:
                sync_scripts()
                script = lib_path()
    except BaseException as e:      # nothing is queued yet: the job cannot run (T2.15; ppro_build reads the flag)
        cep_queue._flag_claimed(e, False)
        raise
    return cep_queue.submit(queue_dir(), script, action, data, timeout, st=st, app="Premiere",
                            expect_version=BRIDGE_VERSION, lib=lib)


def build_lock(what: str, **kw):
    """One Premiere build at a time on this machine (ppro-build, ppro-frames): cep_queue.build_lock on ppro-queue."""
    from . import cep_queue
    return cep_queue.build_lock(queue_dir(), what, **kw)
