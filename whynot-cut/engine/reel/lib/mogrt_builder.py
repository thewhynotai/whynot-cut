"""Author the client's Essential Graphics templates (.mogrt) in After Effects, once per client.

They live in client_database/templates/mogrt/ and are reused for every video: Premiere places
them (via the WhyNot Cut Bridge) and the editor edits text/timing directly in Premiere. Rebuild only
when the brand or a template design changes.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .common import TEMPLATES_DIR, Paths, load_config, now_iso, run, write_json, write_text
from .ae_builder import brand_controls, comp_fps, fonts_map

MOGRTS = ["hook_title", "term_callout", "glass_card", "name_card", "cta", "checklist"]


def mogrt_dir(paths: Paths) -> Path:
    return paths.client_db / "templates/mogrt"


def generate(paths: Paths) -> Path:
    d = mogrt_dir(paths)
    d.mkdir(parents=True, exist_ok=True)
    fps = comp_fps()
    data = {"fps": fps, "brand": brand_controls(paths.client_db), "fonts": fonts_map(paths.client_db),
            "templates": load_config("graphics-templates.json")["templates"], "events": [], "captions": None,
            "mogrt_dir": str(d), "mogrt_frames": round(4 * fps),   # 4.0 s at any rate (96 only at 24 fps)
            "aep_path": str(d / "NH_MOGRT_TEMPLATES.aep"),
            "new_project": True, "render_template": "High Quality with Alpha", "render_dir": str(d), "logo": None}
    lib = (TEMPLATES_DIR / "after_effects/nh_ae_lib.jsx").read_text(encoding="utf-8")
    js = ("// AUTO-GENERATED MOGRT build — " + now_iso() + "\nvar NH_DATA = " + json.dumps(data, ensure_ascii=True) +
          ";\n" + lib + "\nNH.buildMogrts();\n")
    p = d / "build_mogrts.jsx"
    write_text(p, js)
    return p


def valid_mogrt(p: Path, since: float = 0) -> bool:
    """A real .mogrt is a single zip FILE (with a definition JSON) written during this run.
    (AE can also produce folders or truncated names — existence alone proved nothing.)"""
    import zipfile
    if not p.is_file() or p.stat().st_mtime < since - 1:
        return False
    try:
        with zipfile.ZipFile(p) as z:
            return any(n.endswith(".json") for n in z.namelist())
    except zipfile.BadZipFile:
        return False


def build(paths: Paths, timeout: int = 600) -> dict:
    jsx = generate(paths)
    from .adobe_run import run_after_effects
    t0 = time.time()
    d0 = mogrt_dir(paths)
    p = run_after_effects(jsx, timeout, done=lambda: all(valid_mogrt(d0 / f"NH_{k}.mogrt", t0) for k in MOGRTS))
    if p.get("status") == "UNSUPPORTED":
        return {"status": "UNSUPPORTED", "ok": False, "msg": "After Effects not installed", "jsx": str(jsx)}   # T2.16
    if p.get("status") == "REFUSED":
        return dict(p, ok=False, jsx=str(jsx))
    d = mogrt_dir(paths)
    fresh = {k: valid_mogrt(d / f"NH_{k}.mogrt", t0) for k in MOGRTS}
    res = {"jsx": str(jsx), "returncode": p.get("returncode"), "stderr": (p.get("stderr") or "")[:500],
           "mogrts_written_this_run": fresh, "missing": [k for k, v in fresh.items() if not v],
           "status": "MOGRTS_CREATED" if all(fresh.values()) else ("PARTIAL" if any(fresh.values()) else "FAILED"),
           "elapsed_s": round(time.time() - t0, 1), "at": now_iso()}
    write_json(d / "mogrt-build-result.json", res)
    return res
