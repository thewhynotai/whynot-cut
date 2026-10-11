"""Onboarding helpers: `reel doctor` (is this machine ready?), `reel scaffold` (a client folder ready to fill),
`reel inbox` (every raw clip in a client folder and what it needs next)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import plat
from .common import ENV_DIR, Paths, ffmpeg_exe, load_status, now_iso, read_json, slug, venv_python, write_json, write_text

MODULES = ["faster_whisper", "ctranslate2", "av", "numpy", "PIL", "fontTools", "arabic_reshaper", "bidi",
           "uharfbuzz", "freetype", "pypdf"]


# --------------------------------------------------------------------------- doctor
def bridge_info() -> dict:
    from .ppro_bridge import EXT_DIR, status
    cfg = read_json(EXT_DIR / "bridge-config.json", {}) if EXT_DIR.exists() else {}
    modes = plat.player_debug_mode()
    st = status()
    return {"installed": EXT_DIR.exists(), "folder": str(EXT_DIR), "version": cfg.get("version"),
            "queue_base": cfg.get("base"), "debug_mode": modes, "debug_mode_ok": plat.debug_mode_ok(modes),
            "alive": st["alive"], "detail": st["detail"]}


def whisper_model_state() -> dict:
    """{model: complete|partial} for faster-whisper models in the engine home. A model is complete only when its
    model.bin is there (an interrupted download leaves just the small config files, ~3 MB)."""
    out = {}
    root = ENV_DIR / "models"
    for d in sorted(root.glob("models--*")) if root.exists() else []:
        name = d.name.replace("models--Systran--faster-whisper-", "").replace("models--mobiuslabsgmbh--faster-whisper-", "")             .replace("models--", "")
        bins = [b for b in d.glob("snapshots/*/model.bin") if b.stat().st_size > 50 * 1024 * 1024]
        out[name] = "complete" if bins else "partial"
    return out


def doctor() -> dict:
    from . import settings as S
    mods = {}
    for m in MODULES + (["CoreText", "Vision"] if plat.IS_MAC else ["cv2"]):
        try:
            __import__(m)
            mods[m] = True
        except Exception as e:  # noqa: BLE001
            mods[m] = f"missing ({type(e).__name__})"
    states = whisper_model_state()
    models = sorted(k for k, v in states.items() if v == "complete")
    apps = {k: (plat.newest_app(k) or {}).get("name") for k in ("premiere", "after_effects", "photoshop", "media_encoder")}
    br = bridge_info()
    st = S.load()
    cr = plat.clients_root_setting() or (Path(st["clients_root"]).expanduser() if st.get("clients_root") else None)
    rep = {"generated": now_iso(), "system": plat.describe(), "engine_home": str(ENV_DIR),
           "venv_python": str(venv_python()), "venv_ok": venv_python().exists(), "python_modules": mods,
           "ffmpeg": ffmpeg_exe(), "whisper_models": models,
           "whisper_partial_downloads": sorted(k for k, v in states.items() if v == "partial"), "gpu": plat.gpu_info(), "adobe_apps": apps,
           "premiere_bridge": br, "settings_file": st["_file"], "settings_problems": st["_problems"],
           "clients_root": str(cr) if cr else None}
    fixes = []
    if not all(v is True for v in mods.values()):
        fixes.append({"item": "engine packages", "who": "claude", "fix": "reel setup   (re-installs the pinned packages)"})
    if not rep["ffmpeg"]:
        fixes.append({"item": "ffmpeg", "who": "claude", "fix": "reel setup   (imageio-ffmpeg provides it)"})
    if not models:
        part = [k for k, v in states.items() if v == "partial"]
        fixes.append({"item": "Whisper large-v3 (~3 GB)" + (f" (interrupted download of {', '.join(part)} found)" if part else ""),
                      "who": "editor decides",
                      "fix": "with the editor's OK: reel model-download --model large-v3   (run it in the background; it "
                             "resumes an interrupted download). Otherwise it downloads on the first transcription."})
    g = rep["gpu"]
    if g.get("cuda_devices") and g.get("cuda_libs_missing"):
        fixes.append({"item": f"GPU transcription ({g.get('name') or 'NVIDIA GPU'} found, but "
                              f"{', '.join(g['cuda_libs_missing'])} {'are' if len(g['cuda_libs_missing']) > 1 else 'is'} "
                              f"missing, so Whisper runs on the CPU)",
                      "who": "editor decides", "optional": True,
                      "fix": "with the editor's OK: reel gpu-enable   (~550 MB from PyPI; transcription and the "
                             "no-speech-cut check run about 5-10x faster). Everything works without it, just slower."})
    if not apps["premiere"]:
        fixes.append({"item": "Adobe Premiere Pro", "who": "editor",
                      "fix": "install Premiere Pro (2022 or newer) from Creative Cloud; until then WhyNot Cut builds "
                             "an importable XML and a preview MP4"})
    else:
        if not br["installed"]:
            fixes.append({"item": "Premiere bridge panel", "who": "claude", "fix": "reel setup   (installs the panel)"})
        if not br["debug_mode_ok"]:
            fixes.append({"item": "Adobe PlayerDebugMode (lets Premiere load the bridge panel)", "who": "editor",
                          "fix": "run these yourself, then restart Premiere:\n" + "\n".join(plat.debug_mode_commands())})
        if br["installed"] and br["debug_mode_ok"] and not br["alive"]:
            fixes.append({"item": "Premiere bridge not running", "who": "editor",
                          "fix": "open Premiere Pro (quit and reopen it once after setup); the bridge starts by itself"})
    if st["_problems"]:
        fixes.append({"item": "preferences file", "who": "claude", "fix": "; ".join(st["_problems"])})
    rep["ready"] = {"engine": rep["venv_ok"] and all(v is True for v in mods.values()) and bool(rep["ffmpeg"]),
                    "premiere_build": bool(apps["premiere"]) and br["installed"] and br["debug_mode_ok"] and br["alive"],
                    "preview_and_xml": rep["venv_ok"] and bool(rep["ffmpeg"])}
    rep["fixes"] = fixes
    rep["verdict"] = ("READY" if rep["ready"]["engine"] and rep["ready"]["premiere_build"] else
                      "READY (no live Premiere build yet)" if rep["ready"]["engine"] else "NEEDS SETUP")
    return rep


# --------------------------------------------------------------------------- scaffold
FOLDERS = {
    "assets/Logo": "logo files (PNG with transparency is best, plus SVG/AI if you have them)",
    "assets/Fonts": "the brand's font files (.otf / .ttf); install them on this computer too",
    "assets/Photos": "approved photos of the speaker (JPG/PNG; camera RAW works on macOS)",
    "assets/Brand": "brief / about / bio, and a colours file with HEX codes (e.g. colors.txt: #20ACAF)",
    "data/Raw": "the raw talking-head clips to edit (MP4/MOV/MXF), one file per video",
    "data/Episodes": "finished podcast episodes (16:9) to cut into reels, plus an optional <name>.md episode sheet "
                     "(guest, links, sponsor, topics to avoid)",
    "data/References": "reference edits you want to look like (videos) and any written style notes",
    "data/Broll": "licensed stock / B-roll videos you may use (optional), with a SOURCES.md or licence file",
    "data/Music": "licensed music only (optional)",
    "data/SFX": "your own sound-effects library (optional; otherwise original SFX are synthesised)",
}


def start_here(name: str) -> str:
    rows = "\n".join(f"| `{k}/` | {v} |" for k, v in FOLDERS.items())
    return f"""# {name}: drop your material here

WhyNot Cut (by The Why Not AI) edits everything from these two folders. Just add files; you never need to rename them.

| Folder | Put here |
|---|---|
{rows}

Then, in Claude Code, say **"edit the new videos"** (or run `/whynot-cut:autopilot`).
You get, per clip: a native Premiere Pro project with animated graphics and captions, cleaned dialogue with pauses removed,
a watchable preview MP4, and a QC report. Results appear in `output/` (WhyNot Cut never changes `assets/` or `data/`).

## بالعربي
ضع ملفات الهوية في `assets/` (الشعار، الخطوط، الصور، ملف الألوان والتعريف) والفيديوهات الخام في `data/Raw/`
وأمثلة المونتاج المرجعية في `data/References/`، ثم قل لـ Claude: **"عدّل الفيديوهات الجديدة"**.
حلقات البودكاست الكاملة (16:9) في `data/Episodes/` (ومعاها اختياري ملف `<اسم الحلقة>.md` فيه الضيف واللينكات)، ثم قل:
**"طلّع ريلز من الحلقة"**، فتوصلك خطة ريلز بالتايم كود ونوع المحتوى، وتختار منها اللي يتعمل.
النتائج تظهر في مجلد `output/` ولا يتم تعديل الملفات الأصلية أبداً.

Created {now_iso()}.
"""


def scaffold(root: Path, name: str | None = None) -> dict:
    root = Path(plat.native_path(str(root))).expanduser().resolve()
    name = name or root.name
    existing = [str(p.relative_to(root).as_posix()) for top in ("assets", "data") if (root / top).is_dir()
                for p in (root / top).rglob("*") if p.is_file()]
    if existing:
        return {"status": "EXISTS", "root": str(root), "files_already_there": len(existing),
                "detail": "this client folder already has material; nothing was changed (assets/ and data/ are the "
                          "client's own files). Run `reel inbox` to see what's there."}
    made = []
    for rel in FOLDERS:
        d = root / rel
        if not d.is_dir():
            d.mkdir(parents=True)
            made.append(rel)
    (root / "output").mkdir(exist_ok=True)
    guide = root / "START_HERE.md"
    if not guide.exists():
        write_text(guide, start_here(name))
    return {"status": "CREATED", "root": str(root), "folders": made, "guide": str(guide),
            "next": "Add the files (see START_HERE.md), then run `reel inbox --root \"<this folder>\"`."}


# --------------------------------------------------------------------------- inbox
def inbox(root: Path, refresh: bool = True) -> dict:
    from .discover import run_discovery
    p = Paths(root)
    if refresh:
        run_discovery(p)
    inv = read_json(p.output / "discovery/input-inventory.json", {"files": [], "warnings": []})
    by = inv.get("by_role", {})
    clips = []
    for f in inv["files"]:
        if f["role"] != "source_footage":
            continue
        vid = slug(Path(f["path"]).stem)
        pp = Paths(root, vid)
        # discovery/preflight alone don't start an edit; the transcript does
        started = pp.project.exists() and pp.p("02_transcription/transcript.json").exists()
        st = load_status(pp) if started else {"status": "NEW"}
        done = (pp.p("09_handoff/README.md").exists() and st.get("status") in ("QC_PASSED", "READY_FOR_HUMAN_EDITOR"))
        prev = pp.p(f"08_quality_control/preview/{vid}_preview.mp4") if started else None
        clips.append({"video_id": vid, "file": f["rel"], "size_mb": round(f["size_bytes"] / 1e6, 1),
                      "status": st.get("status"), "state": "done" if done else ("in progress" if started else "new"),
                      "preview": str(prev) if prev and prev.exists() else None})
    need = []
    if not by.get("logo"):
        need.append("a logo in assets/Logo")
    if not [x for x in inv["files"] if x["kind"] == "font"]:
        need.append("the brand fonts in assets/Fonts")
    if not (by.get("brand_colors") or by.get("branding_doc") or by.get("client_brief")):
        need.append("a brief and/or a colours file (HEX codes) in assets/Brand")
    if not (by.get("editing_reference_video") or by.get("editing_reference_doc")):
        need.append("optional: 1-3 reference edits in data/References (gives the style to copy)")
    from .episode import list_episodes, podcast_cfg
    episodes = list_episodes(p.root)
    hints = []
    long_min = podcast_cfg().get("raw_episode_hint_min", 10)
    # probing every Raw clip on every call is slow on big folders: reuse the last probe while path, mtime and size match
    cache_f = p.output / "discovery/raw-probe-cache.json"
    cache, seen = read_json(cache_f, {}) or {}, {}
    for c in clips:   # a whole episode dropped into Raw would be edited as ONE clip: point to data/Episodes
        try:
            f = p.root / c["file"]
            st = f.stat()
            key = [st.st_mtime_ns, st.st_size]
            info = cache.get(c["file"])
            if not info or info.get("stat") != key:
                from .media import probe
                pr = probe(f)
                v = pr.get("video") or {}
                info = {"stat": key, "duration_s": pr.get("duration_s") or 0, "width": v.get("display_width", 0),
                        "height": v.get("display_height", 0)}
            seen[c["file"]] = info
            if info["duration_s"] >= long_min * 60 and info["width"] > info["height"]:
                hints.append(f"{c['file']} is {info['duration_s'] / 60:.0f} min and 16:9: if it is a podcast episode to cut "
                             f"into reels, move it to data/Episodes/ (the editor moves it; data/ is read-only for WhyNot Cut)")
        except Exception:  # noqa: BLE001  (a hint only)
            pass
    if seen != cache:
        write_json(cache_f, seen)
    return {"root": str(p.root), "profile": read_json(p.output / "client_database/reel-profile/profile.json", {}).get("id"),
            "episodes": episodes, "episode_hints": hints,
            "clips": clips, "new": [c["video_id"] for c in clips if c["state"] == "new"],
            "in_progress": [c["video_id"] for c in clips if c["state"] == "in progress"],
            "done": [c["video_id"] for c in clips if c["state"] == "done"],
            "missing_material": need, "discovery_warnings": inv.get("warnings", [])}
