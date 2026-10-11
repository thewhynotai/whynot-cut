"""Python side of the WhyNot Cut Bridge (one CEP bundle for Premiere and After Effects; this module is the Premiere side): install, status, submit jobs, wait for results.

Premiere has no scripting entry point from outside (macOS AppleScript exposes only capture/editoriginal; Windows has
no COM API), so scripts can't be sent to Premiere directly. The bridge panel (templates/premiere/cep_bridge) runs
inside Premiere on macOS and Windows and executes ONLY scripts from <engine home>/ppro-scripts. The plugin's install path changes on every
update, so `install()`/`sync_scripts()` copy the plugin's JSX there (hash-checked before every job).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .common import ENV_DIR, TEMPLATES_DIR
from . import plat

EXT_ID = "ai.thewhynot.cut.bridge"
LEGACY_EXT_IDS = ("com.nh.bridge",)          # reel-editor 1.x bridge; replaced on install
EXT_DIR = plat.cep_extensions_dir() / EXT_ID
BRIDGE_VERSION = "3.1.0"
QUEUE = ENV_DIR / "ppro-queue"
SCRIPTS = ENV_DIR / "ppro-scripts"
LIB_SRC = TEMPLATES_DIR / "premiere/nh_ppro_lib.jsx"
LIB = SCRIPTS / "nh_ppro_lib.jsx"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def sync_scripts() -> dict:
    """Copy the plugin's Premiere JSX into the bridge's whitelisted folder when it differs."""
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    try:
        SCRIPTS.chmod(0o700)
    except OSError:
        pass
    changed = _sha(LIB_SRC) != _sha(LIB)
    if changed:
        tmp = LIB.with_suffix(".tmp")
        shutil.copy2(LIB_SRC, tmp)
        tmp.replace(LIB)
    return {"scripts_dir": str(SCRIPTS), "synced": changed, "sha256": _sha(LIB)[:12]}


def install() -> dict:
    src = TEMPLATES_DIR / "premiere/cep_bridge"
    EXT_DIR.parent.mkdir(parents=True, exist_ok=True)
    if EXT_DIR.exists():
        shutil.rmtree(EXT_DIR)
    shutil.copytree(src, EXT_DIR)
    # tells the panel where the queue lives (the engine home can be a custom folder; Premiere doesn't see our env)
    (EXT_DIR / "bridge-config.json").write_text(json.dumps({"base": str(ENV_DIR.resolve()), "version": BRIDGE_VERSION}),
                                                encoding="utf-8")
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
    return cep_queue.status(QUEUE, max_age_s, app="Premiere")


def submit(action: str, data: dict | None = None, timeout: float = 600, script: Path = LIB) -> dict:
    from . import cep_queue
    st = status()          # through this module, so callers/tests that patch ppro_bridge.status keep working
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    if script == LIB:
        sync_scripts()
    return cep_queue.submit(QUEUE, script, action, data, timeout, st=st, app="Premiere")
