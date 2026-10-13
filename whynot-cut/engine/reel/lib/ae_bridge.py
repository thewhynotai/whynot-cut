"""After Effects side of the WhyNot Cut Bridge (the same CEP bundle as Premiere; in AE it watches <engine home>/ae-queue).

Bundle 3.0.0 carries the AE libraries in its own jsx/ folder (jobs name `lib`). The legacy 3.1.1 bridge evaluates only
scripts inside <engine home>/ae-scripts, so for it `sync_scripts()` copies the plugin's AE libraries there (hash-checked
before every job; removed with the legacy family in 3.1). ExtendScript in these libraries never writes files: the panel's Node side writes
each job's result, so AE's "Allow Scripts to Write Files and Access Network" preference is never needed.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .common import TEMPLATES_DIR, current_context
from . import cep_queue, plat

SRC = TEMPLATES_DIR / "after_effects"
LIBS = ("wnc_ae_lib.jsx", "wnc_motion_lib.jsx", "wnc_ae_bridge.jsx")
ENTRY_NAME = "wnc_ae_bridge.jsx"


# Locations resolve on every call (3.0 T2.17, engine MI-8): an engine home changed after import is honoured.
def queue_dir() -> Path:
    """<engine home>/ae-queue; the engine home of the bound Context (`reel serve` binds one per request)."""
    return current_context().engine_home / "ae-queue"


def scripts_dir() -> Path:
    """The bridge's whitelisted AE script folder (<engine home>/ae-scripts)."""
    return current_context().engine_home / "ae-scripts"


def entry_path() -> Path:
    return scripts_dir() / ENTRY_NAME


_LIVE = {"QUEUE": "queue_dir", "SCRIPTS": "scripts_dir", "ENTRY": "entry_path"}


def __getattr__(name: str):
    # Back-compat for one release (3.0): these were constants computed at import (engine MI-8). They now resolve per
    # call from the live engine home; new code calls the functions. Remove in 3.1.
    if name in _LIVE:
        return globals()[_LIVE[name]]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def sync_scripts() -> dict:
    """Copy the AE libraries into the bridge's whitelisted folder when they differ (atomic replace)."""
    SCRIPTS = scripts_dir()
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    try:
        SCRIPTS.chmod(0o700)
    except OSError:
        pass
    synced, shas = [], {}
    for name in LIBS:
        src, dst = SRC / name, SCRIPTS / name
        if _sha(src) != _sha(dst):
            tmp = dst.with_suffix(".tmp")
            shutil.copy2(src, tmp)
            tmp.replace(dst)
            synced.append(name)
        shas[name] = _sha(dst)[:12]
    return {"scripts_dir": str(SCRIPTS), "synced": synced, "sha256": shas}


def status(max_age_s: float = 5.0) -> dict:
    st = cep_queue.status(queue_dir(), max_age_s, app="After Effects")
    if st.get("alive") and st.get("host") != "AEFT":
        st = dict(st, alive=False, detail=f"the heartbeat in ae-queue comes from host {st.get('host')!r}, not After "
                                         "Effects: reinstall the bridge (`reel ppro-install`) and restart After Effects")
    return st


def submit(action: str, data: dict | None = None, timeout: float = 900) -> dict:
    refused = plat.sandbox_refusal(f"queue the {action} job", queue_dir(), scripts_dir())   # G79: never in tests
    if refused:
        return refused
    st = status()
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    from .ppro_bridge import BRIDGE_VERSION          # one bundle for both hosts
    # the same modes as ppro_bridge.submit: the bundle runs its own `lib`, the legacy 3.1.1 the synced `script`
    mode = cep_queue.job_mode(st, BRIDGE_VERSION, "After Effects")
    if isinstance(mode, dict):
        return mode                                   # refused: nothing is queued
    if mode == "lib":
        return cep_queue.submit(queue_dir(), None, action, data, timeout, st=st, app="After Effects",
                                expect_version=BRIDGE_VERSION, lib=ENTRY_NAME)
    sync_scripts()
    return cep_queue.submit(queue_dir(), entry_path(), action, data, timeout, st=st, app="After Effects",
                            expect_version=BRIDGE_VERSION)


def build_lock(what: str, **kw):
    """One After Effects build at a time on this machine (motion-build): cep_queue.build_lock on ae-queue."""
    return cep_queue.build_lock(queue_dir(), what, **kw)
