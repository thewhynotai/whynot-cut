"""After Effects side of the WhyNot Cut Bridge (the same CEP bundle as Premiere; in AE it watches <engine home>/ae-queue).

The panel evaluates only scripts inside <engine home>/ae-scripts, so `sync_scripts()` copies the plugin's AE libraries
there (hash-checked before every job). ExtendScript in these libraries never writes files: the panel's Node side writes
each job's result, so AE's "Allow Scripts to Write Files and Access Network" preference is never needed.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .common import ENV_DIR, TEMPLATES_DIR
from . import cep_queue

QUEUE = ENV_DIR / "ae-queue"
SCRIPTS = ENV_DIR / "ae-scripts"
SRC = TEMPLATES_DIR / "after_effects"
LIBS = ("nh_ae_lib.jsx", "nh_motion_lib.jsx", "nh_ae_bridge.jsx")
ENTRY_NAME = "nh_ae_bridge.jsx"
ENTRY = SCRIPTS / ENTRY_NAME


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def sync_scripts() -> dict:
    """Copy the AE libraries into the bridge's whitelisted folder when they differ (atomic replace)."""
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
    st = cep_queue.status(QUEUE, max_age_s, app="After Effects")
    if st.get("alive") and st.get("host") != "AEFT":
        st = dict(st, alive=False, detail=f"the heartbeat in ae-queue comes from host {st.get('host')!r}, not After "
                                         "Effects: reinstall the bridge (`reel ppro-install`) and restart After Effects")
    return st


def submit(action: str, data: dict | None = None, timeout: float = 900) -> dict:
    st = status()
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    sync_scripts()
    return cep_queue.submit(QUEUE, SCRIPTS / ENTRY_NAME, action, data, timeout, st=st, app="After Effects")
