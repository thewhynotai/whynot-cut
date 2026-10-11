"""The file-queue protocol of the WhyNot Cut Bridge (one CEP bundle; Premiere uses ppro-queue, After Effects ae-queue).

The panel writes `bridge.heartbeat` every second, claims `<id>.job.json` by renaming it, evaluates the whitelisted script
named in the job with the job's data file, and writes `<id>.result.json`. These helpers are host-neutral: ppro_bridge
and ae_bridge pass their own queue folder and script.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .common import now_iso


def status(queue: Path, max_age_s: float = 5.0, app: str = "the Adobe app") -> dict:
    hb = Path(queue) / "bridge.heartbeat"
    if not hb.exists():
        return {"alive": False, "host": None,
                "detail": f"no heartbeat: start {app} (bridge auto-starts) or open Window > Extensions > WhyNot Cut Bridge"}
    d = None
    for _ in range(4):          # the panel rewrites the file every second (not atomically): retry a torn read
        try:
            d = json.loads(hb.read_text(encoding="utf-8"))
            break
        except Exception:
            time.sleep(0.05)
    if d is None:
        return {"alive": False, "host": None, "detail": "unreadable heartbeat"}
    age = time.time() - d["at"] / 1000
    return {"alive": age < max_age_s, "age_s": round(age, 1), "busy": d.get("busy"), "bridge_version": d.get("version"),
            "host": d.get("host"),
            "detail": "ok" if age < max_age_s else f"heartbeat {age:.0f}s old: panel closed or {app} busy/quit"}


def submit(queue: Path, script: Path, action: str, data: dict | None = None, timeout: float = 600,
           poll_s: float = 0.5, st: dict | None = None, app: str = "the Adobe app") -> dict:
    """Queue one job and wait for its result. `st` = a status already checked by the caller (else checked here)."""
    queue = Path(queue)
    st = st if st is not None else status(queue, app=app)
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    queue.mkdir(parents=True, exist_ok=True)
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    payload = dict(data or {}, action=action, job_id=jid, submitted=now_iso())
    data_file = queue / f"{jid}.data.json"
    data_file.write_text(json.dumps(payload, ensure_ascii=True), encoding="ascii")
    job = {"id": jid, "action": action, "script": str(script), "data_file": str(data_file)}
    tmp = queue / f"{jid}.tmp"
    tmp.write_text(json.dumps(job), encoding="utf-8")
    tmp.rename(queue / f"{jid}.job.json")      # atomic: the panel never sees a half-written job
    res_p = queue / f"{jid}.result.json"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if res_p.exists():
            try:
                r = json.loads(res_p.read_text(encoding="utf-8"))
            except ValueError:          # the panel is still writing it
                time.sleep(0.2)
                continue
            inner = r.get("result")
            try:
                inner = json.loads(inner) if isinstance(inner, str) else inner
            except Exception:
                pass
            return {"ok": bool(r.get("ok")) and isinstance(inner, dict) and inner.get("ok", False),
                    "bridge_ok": r.get("ok"), "response": inner, "elapsed_s": round(time.time() - t0, 1), "job": jid}
        time.sleep(poll_s)
    return {"ok": False, "error": f"timeout after {timeout}s ({app} may show a dialog)", "job": jid}
