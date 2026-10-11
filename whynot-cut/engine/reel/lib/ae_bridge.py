"""After Effects side of the WhyNot Cut Bridge (the same CEP bundle as Premiere; in AE it watches <engine home>/ae-queue).

The panel evaluates only scripts inside <engine home>/ae-scripts, so `sync_scripts()` copies the plugin's AE libraries
there (hash-checked before every job). ExtendScript in these libraries never writes files: the panel's Node side writes
each job's result, so AE's "Allow Scripts to Write Files and Access Network" preference is never needed.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .common import TEMPLATES_DIR, engine_home
from . import cep_queue

SRC = TEMPLATES_DIR / "after_effects"
LIBS = ("nh_ae_lib.jsx", "nh_motion_lib.jsx", "nh_ae_bridge.jsx")
ENTRY_NAME = "nh_ae_bridge.jsx"


# Locations resolve on every call (3.0 T2.17, engine MI-8): an engine home changed after import is honoured.
def queue_dir() -> Path:
    return engine_home() / "ae-queue"


def scripts_dir() -> Path:
    """The bridge's whitelisted AE script folder (<engine home>/ae-scripts)."""
    return engine_home() / "ae-scripts"


def entry_path() -> Path:
    return scripts_dir() / ENTRY_NAME


_LIVE = {"QUEUE": "queue_dir", "SCRIPTS": "scripts_dir", "EXT_DIR": "ext_dir", "LIB": "lib_path", "ENTRY": "entry_path"}


def __getattr__(name: str):
    # Back-compat for one release (3.0): these were constants computed at import (engine MI-8). They now resolve per
    # call from the live engine home; new code calls the functions. Remove in 3.1.
    if name in _LIVE and _LIVE[name] in globals():
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
    st = status()
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    sync_scripts()
    return cep_queue.submit(queue_dir(), entry_path(), action, data, timeout, st=st, app="After Effects")
