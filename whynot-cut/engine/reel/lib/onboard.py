"""Onboarding helpers: `reel doctor` (is this machine ready?), `reel scaffold` (a client folder ready to fill),
`reel inbox` (every raw clip in a client folder and what it needs next)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import cep_bundle, plat
from .common import DONE_STATUSES, Paths, engine_home, ffmpeg_exe, models_dir, load_status, now_iso, read_json, venv_python, write_json, write_text

MODULES = ["faster_whisper", "ctranslate2", "av", "numpy", "PIL", "fontTools", "arabic_reshaper", "bidi",
           "uharfbuzz", "freetype", "pypdf"]


# --------------------------------------------------------------------------- doctor
def bridge_info() -> dict:
    """The WhyNot Cut CEP extension (3.0 T6.3): the installed bundle (its build.json: family, product, build, signed),
    ~/.whynot-cut/bridge/config.json (engine home, launcher) and the Premiere daemon's heartbeat. A signed bundle
    loads without PlayerDebugMode; an unsigned one (a dev build, the legacy 3.1.1) needs it."""
    from .ppro_bridge import ext_dir, queue_dir, status
    ext = ext_dir()
    inst = cep_bundle.installed(ext) or {}
    cfg = cep_bundle.read_config()
    modes = plat.player_debug_mode()
    dbg_ok = plat.debug_mode_ok(modes)
    st = status()
    beat = read_json(queue_dir() / "bridge.heartbeat", {})
    signed = bool(inst.get("signed"))
    return {"installed": bool(inst), "folder": str(ext), "family": inst.get("family"), "product": inst.get("version"),
            "version": inst.get("version"), "build": inst.get("build"), "signed": signed,
            "config": cfg, "config_file": str(cep_bundle.config_path()),
            "queue_base": (cfg or {}).get("engine_home"), "launcher": (cfg or {}).get("launcher"),
            "debug_mode": modes, "debug_mode_ok": dbg_ok, "debug_mode_needed": bool(inst) and not signed,
            "loads": bool(inst) and (signed or dbg_ok),
            "engine_start": beat.get("engine_start") if isinstance(beat, dict) else None,
            "alive": st["alive"], "detail": st["detail"]}


def _extension_fix(app: str) -> dict:
    """How the WhyNot Cut extension gets installed: from this plugin's source (a dev checkout), else the installer."""
    if cep_bundle.has_source():
        return {"item": f"WhyNot Cut extension ({app})", "who": "claude",
                "fix": "reel setup   (installs the WhyNot Cut extension; Premiere and After Effects share it)"}
    return {"item": f"WhyNot Cut extension ({app})", "who": "editor",
            "fix": "install WhyNot Cut with its installer (the signed extension comes with it)"}


def whisper_model_state() -> dict:
    """{model: complete|partial} for faster-whisper models in the engine home. A model is complete only when its
    model.bin is there (an interrupted download leaves just the small config files, ~3 MB)."""
    out = {}
    root = models_dir()
    for d in sorted(root.glob("models--*")) if root.exists() else []:
        name = d.name.replace("models--Systran--faster-whisper-", "").replace("models--mobiuslabsgmbh--faster-whisper-", "")             .replace("models--", "")
        bins = [b for b in d.glob("snapshots/*/model.bin") if b.stat().st_size > 50 * 1024 * 1024]
        out[name] = "complete" if bins else "partial"
    return out


def transcription_speed() -> dict:
    """The cached `reel bench` result (3.0 T2.12): Whisper's real-time factor on this machine, or how to measure it."""
    from .whisper_backends import read_bench
    return read_bench()


HEARTBEAT_MAX_AGE_S = 24 * 3600


def _newest_beat(name: str, now: float) -> tuple[str | None, float | None]:
    import os
    cands = [Path(os.environ["CLAUDE_PLUGIN_DATA"]) / name] if os.environ.get("CLAUDE_PLUGIN_DATA") else []
    cands += sorted((_claude_config_dir() / "plugins" / "data").glob(f"whynot-cut*/{name}"))
    found = []
    for c in cands:
        try:
            found.append((c.stat().st_mtime, c))
        except OSError:
            continue
    if not found:
        return None, None
    mtime, f = max(found)
    return str(f), now - mtime


def _claude_config_dir() -> Path:
    import os
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def silent_guards() -> list[dict]:
    """Installed WhyNot Cut plugins whose guard writes no guard-ok heartbeat (2.x: the heartbeat came with 3.0), from
    <claude config>/plugins/installed_plugins.json: [{"version", "path"}]. Such a guard may well be running; doctor
    just cannot see it (Gate 2 live check: the installed 2.2.1 guard was active, doctor said "not confirmed")."""
    import json
    try:
        reg = json.loads((_claude_config_dir() / "plugins/installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for name, entries in ((reg or {}).get("plugins") or {}).items() if isinstance(reg, dict) else ():
        if not str(name).startswith("whynot-cut@") or not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict) or not e.get("installPath"):
                continue
            guard = Path(e["installPath"]) / "hooks/guard.py"
            try:
                writes = "guard-ok" in guard.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue            # not on disk: no guard of it can run
            if not writes and not any(o["path"] == str(guard.parent.parent) for o in out):
                out.append({"version": str(e.get("version") or "?"), "path": str(guard.parent.parent)})
    return out


def guard_heartbeat(now: float | None = None) -> dict:
    """Is the PreToolUse guard running? guard.py touches <plugin data>/guard-ok on every tool call it inspects, and
    hooks/run_python.sh touches hooks-ok whenever it found Python (the runner). No fresh guard-ok (< 24 h) means the
    guard never ran: no Git Bash on Windows, no Python, or the plugin is not enabled. Looks at ${CLAUDE_PLUGIN_DATA}
    and every <claude config>/plugins/data/whynot-cut*/."""
    now = now or time.time()
    f, age = _newest_beat("guard-ok", now)
    rf, rage = _newest_beat("hooks-ok", now)
    active = age is not None and age < HEARTBEAT_MAX_AGE_S
    fix, silent = None, ([] if active else silent_guards())
    if silent:                  # an older plugin's guard writes no heartbeat: unknown, not "not running"
        vers = ", ".join(sorted({g["version"] for g in silent}))
        active = None
        fix = (f"the installed WhyNot Cut {vers} guard writes no heartbeat (that check came with 3.0), so `reel "
               "doctor` cannot see it run: type /hooks in Claude Code - when WhyNot Cut's PreToolUse hook is listed, "
               "the guard is on. Updating the plugin to 3.0 makes this check automatic.")
    elif not active:
        fix = ("install Git for Windows (https://git-scm.com/download/win), then restart Claude Code: WhyNot Cut's "
               "guard hooks run through Git Bash. Then run /hooks to check they are listed, and `reel doctor` again."
               if plat.IS_WIN else
               "restart Claude Code and run /hooks to check WhyNot Cut's hooks are listed; make sure `python3 --version` "
               "works (macOS: xcode-select --install), then `reel doctor` again.")
    return {"active": active, "file": f, "age_h": round(age / 3600, 1) if age is not None else None,
            "runner_file": rf, "runner_age_h": round(rage / 3600, 1) if rage is not None else None, "fix": fix,
            "silent_guards": silent}


def own_marker_roots(root: str | None) -> list[Path]:
    """The client `reel doctor --fix` may mark (G70): --root, else the current folder when it has assets/ and data/
    and WhyNot Cut has worked there (output/ or START_HERE.md: a Hugo site is not a client). Never the other clients
    of clients_root: those need `--all-clients --yes`."""
    from .client_marker import has_layout
    cwd = Path.cwd()
    cands = [Path(root).expanduser()] if root else \
        [cwd] if (cwd / "output").is_dir() or (cwd / "START_HERE.md").is_file() else []
    return [c.resolve() for c in cands if has_layout(c.resolve())]


def marker_roots(root: str | None) -> list[Path]:
    """Client folders `reel doctor` looks at for the `.whynot-client` marker: own_marker_roots plus every client
    folder in clients_root (reported; written only with `--fix --all-clients --yes`)."""
    from .client_marker import has_layout
    from .common import client_folders, clients_root
    out = list(own_marker_roots(root))
    for c in client_folders(clients_root()):
        c = c.resolve()
        if has_layout(c) and c not in out:
            out.append(c)
    return out


def client_markers(roots: list[Path], fix_roots=()) -> dict:
    """{written, present, missing, unprotected} for `roots`; the marker is written only into `fix_roots`.
    `unprotected` = no sign at all that it is a client folder (the guard leaves it alone until the marker exists)."""
    from .client_marker import MARKER, is_client, write_marker
    rep = {"written": [], "present": [], "missing": [], "unprotected": []}
    fix_roots = {Path(r).resolve() for r in fix_roots}
    for r in roots:
        if (r / MARKER).is_file():
            rep["present"].append(str(r / MARKER))
            continue
        if r.resolve() in fix_roots:
            try:
                write_marker(r)
                rep["written"].append(str(r / MARKER))
                continue
            except ValueError:            # inside another client's assets/ or data/: never write there
                continue
        rep["missing"].append(str(r))
        if not is_client(r):
            rep["unprotected"].append(str(r))
    return rep


def runtime_report(home: Path | None = None) -> dict:
    """The engine runtime as the wrappers resolve it (current runtime, else the legacy venv), whether it was built from
    this plugin's lock, and whether THIS process is isolated in it: every engine module loads from inside the runtime
    at the locked version, no system or user site (3.0 T2.1, IM-1). {kind, id, dir, python, expected_id,
    up_to_date, isolated, problems, modules, ...}."""
    from . import runtime as R
    home = home or engine_home()
    st = R.status(home)
    try:
        lock = R.parse_lock(Path(st["lock_file"]).read_text(encoding="utf-8")) if st["lock_file"] else {}
    except (OSError, ValueError):
        lock = {}
    iso = R.isolation(plat.engine_runtime(home), lock)
    st.update(isolated=iso["isolated"], problems=iso["problems"], modules=iso["modules"])
    return st


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
    found = plat.adobe_report()      # T2.11: name + version + path + source per app; a bad WHYNOT_*_APP is a problem, not a crash
    apps = found["names"]
    br = bridge_info()
    st = S.load()
    cr = plat.clients_root_setting() or (Path(st["clients_root"]).expanduser() if st.get("clients_root") else None)
    from . import selfid
    rc = selfid.scan_path()
    rep = {"generated": now_iso(), "plugin": selfid.plugin_info(), "reel_command": rc,
           "system": plat.describe(), "engine_home": str(engine_home()),
           "venv_python": str(venv_python()), "venv_ok": venv_python().exists(), "python_modules": mods,
           "running_python": sys.executable,
           "ffmpeg": ffmpeg_exe(), "whisper_models": models,
           "whisper_partial_downloads": sorted(k for k, v in states.items() if v == "partial"), "gpu": plat.gpu_info(), "adobe_apps": apps,
           "adobe_found": found["found"], "aerender": found["aerender"],
           "premiere_bridge": br, "settings_file": st["_file"], "settings_problems": st["_problems"],
           "clients_root": str(cr) if cr else None}
    rt = rep["runtime"] = runtime_report()
    rep["isolated"] = rt["isolated"]
    gh = guard_heartbeat()
    rep["guard_active"], rep["guard_heartbeat"] = gh["active"], gh
    rep["transcription_speed"] = transcription_speed()
    fixes = []
    if not rc["ok"]:      # G66: a session started before the install keeps another plugin's `reel` first on PATH
        fixes.append({"item": "wrong `reel` first on PATH: " + rc["message"], "who": "editor", "fix": rc["fix"]})
    if not all(v is True for v in mods.values()):
        fixes.append({"item": "engine packages", "who": "claude",
                      "fix": "reel setup   (re-installs the packages from the hash lock)"})
    if rt["kind"] != "runtime":
        fixes.append({"item": "engine runtime not isolated: " + "; ".join(rt["problems"][:3]), "who": "claude",
                      "fix": "reel setup   (builds the isolated runtime side by side from the hash lock; the old "
                             "venv/ is kept)"})
    elif not rt["up_to_date"]:
        fixes.append({"item": f"engine runtime {rt['id']} was not built from this plugin's lock "
                              f"(expected {rt['expected_id']})", "who": "claude",
                      "fix": "reel setup   (builds the new runtime side by side, then switches to it)"})
    elif not rt["isolated"]:
        fixes.append({"item": "engine runtime not isolated: " + "; ".join(rt["problems"][:3]), "who": "claude",
                      "fix": "reel setup --force   (re-installs the runtime from the hash lock)"})
    if not rep["ffmpeg"]:
        fixes.append({"item": "ffmpeg", "who": "claude",
                      "fix": "reel setup   (the engine runtime's imageio-ffmpeg provides one; the WhyNot Cut "
                             "installer adds the pinned ffmpeg)"})
    from .portability import doctor_checks        # T2.15: non-ASCII engine home, OpenCV face model, ffmpeg filters
    rep["portability"], more = doctor_checks(engine_home())
    fixes += more
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
                             "no-speech-cut check run about 5-10x faster). Everything works without it, just slower. "
                             "It was enabled before? An engine update (reel setup re-syncs the runtime) removes the "
                             "cuBLAS wheels: run reel gpu-enable again."})
    prem_var_bad = any("WHYNOT_PREMIERE_APP" in pr["error"] for pr in found["problems"])
    if not apps["premiere"]:
        if not prem_var_bad:        # a bad WHYNOT_PREMIERE_APP hides a real install: the variable fix below is the fix
            fixes.append({"item": "Adobe Premiere Pro", "who": "editor",
                          "fix": "install Premiere Pro (2022 or newer) from Creative Cloud; until then WhyNot Cut "
                                 "builds an importable XML and a preview MP4"})
        if apps["after_effects"] and not br["installed"]:      # T2.11: the same bundle serves After Effects
            fixes.append(_extension_fix("After Effects"))
    else:
        if not br["installed"]:
            fixes.append(_extension_fix("Premiere"))
        if br["debug_mode_needed"] and not br["debug_mode_ok"]:  # a signed extension loads without it
            fixes.append({"item": "Adobe PlayerDebugMode (lets Premiere load this unsigned WhyNot Cut extension)",
                          "who": "editor",
                          "fix": "run these yourself, then restart Premiere:\n" + "\n".join(plat.debug_mode_commands())})
        if br["loads"] and not br["alive"]:
            fixes.append({"item": "WhyNot Cut is not running in Premiere", "who": "editor",
                          "fix": "open Premiere Pro (quit and reopen it once after installing); WhyNot Cut starts by "
                                 "itself"})
    if br["family"] == "legacy":                                # decision 15: works during 3.0, shown amber
        fixes.append(dict(_extension_fix("Premiere"), optional=True, level="amber",
                          item=f"WhyNot Cut extension {br['product'] or '?'} is the older bridge (it still works in "
                               "3.0; the update replaces it)"))
    elif br["family"] == "unknown":
        fixes.append({"item": f"WhyNot Cut extension {br['product'] or '?'} is a version this engine does not know",
                      "who": "editor", "fix": "install WhyNot Cut with its installer (the signed extension comes with it)"})
    elif br["installed"] and not br["signed"] and not cep_bundle.has_source():   # decision 8
        fixes.append({"item": "the installed WhyNot Cut extension is an unsigned build", "who": "editor",
                      "optional": True, "level": "amber",
                      "fix": "install WhyNot Cut with its installer (the signed extension comes with it)"})
    for pr in found["problems"]:                                # a WHYNOT_PREMIERE_APP / _AE_APP / _AERENDER that points nowhere
        fixes.append({"item": pr["error"], "who": "editor", "fix": pr["how"]})
    if st["_problems"]:
        fixes.append({"item": "preferences file", "who": "claude", "fix": "; ".join(st["_problems"])})
    if gh["active"] is None:      # only an older plugin's guard, which writes no heartbeat: say exactly that
        fixes.append({"item": "WhyNot Cut guard not checkable from here: the installed plugin "
                              f"{', '.join(sorted({g['version'] for g in gh['silent_guards']}))} predates the guard "
                              "heartbeat", "who": "editor", "fix": gh["fix"]})
    elif not gh["active"]:
        fixes.append({"item": "WhyNot Cut guard hooks not confirmed running (no guard-ok heartbeat in the last 24 h): "
                              "assets/ and data/ may not be protected", "who": "editor", "fix": gh["fix"]})
    rep["ready"] = {"engine": rep["venv_ok"] and all(v is True for v in mods.values()) and bool(rep["ffmpeg"]),
                    "premiere_build": bool(apps["premiere"]) and br["loads"] and br["alive"],
                    "preview_and_xml": rep["venv_ok"] and bool(rep["ffmpeg"]), "reel_command": rc["ok"]}
    rep["fixes"] = fixes
    rep["verdict"] = ("READY" if rep["ready"]["engine"] and rep["ready"]["premiere_build"] else
                      "READY (no live Premiere build yet)" if rep["ready"]["engine"] else "NEEDS SETUP")
    if not rc["ok"]:
        rep["verdict"] += " — but plain `reel` does not run WhyNot Cut in this session (see fixes)"
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
    from .client_marker import MARKER, write_marker
    from .common import derived_prefix
    prefix = derived_prefix(root)         # stored now (T3.10 review I2): renaming the folder later never changes it
    write_marker(root, prefix)            # the guard and the session hook recognise the folder by it
    from .claude_perms import inherit_for_new_client
    perms = inherit_for_new_client(root)  # T3.9: the clients folder's `reel *` rules, when the editor accepted them
    return {"status": "CREATED", "root": str(root), "folders": made, "guide": str(guide), "marker": str(root / MARKER),
            "prefix": prefix,
            **({"allow_reel": perms} if perms else {}),
            "next": "Add the files (see START_HERE.md), then run `reel inbox --root \"<this folder>\"`."}


# --------------------------------------------------------------------------- inbox
def inbox(root: Path, refresh: bool = True) -> dict:
    from .discover import run_discovery
    p = Paths(root)
    if refresh:
        run_discovery(p, audit=False)          # T2.14: the environment audit is for `reel discover` / doctor, not every inbox
    inv = read_json(p.output / "discovery/input-inventory.json", {"files": [], "warnings": []})
    by = inv.get("by_role", {})
    clips = []
    from .clip_ids import clip_ids, index, key
    ids = clip_ids(p.root, inv)
    by_rel = index(ids)                       # one reverse map, dict lookups (T3.10 review I1)
    for f in inv["files"]:
        if f["role"] != "source_footage":
            continue
        vid = by_rel.get(key(f["rel"]))
        pp = Paths(root, vid)
        # discovery/preflight alone don't start an edit; the transcript does
        started = pp.project.exists() and pp.p("02_transcription/transcript.json").exists()
        st = load_status(pp) if started else {"status": "NEW"}
        done = pp.p("09_handoff/README.md").exists() and st.get("status") in DONE_STATUSES      # T2.15: + DELIVERED
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
    from .ref_style import state as ref_state
    rs = ref_state(p.root)
    from .episode import list_episodes, podcast_cfg
    episodes = list_episodes(p.root)
    hints = []
    long_min = podcast_cfg().get("raw_episode_hint_min", 10)
    # probing every Raw clip on every call is slow on big folders: reuse the last probe while path, mtime and size match
    cache_f = p.output / "discovery/raw-probe-cache.json"
    try:
        cache = read_json(cache_f, {})
    except (OSError, ValueError):          # a broken cache is rebuilt; it never stops the inbox
        cache = {}
    cache, seen = cache if isinstance(cache, dict) else {}, {}
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
            "missing_material": need, "discovery_warnings": inv.get("warnings", []),
            "reference_style": {"state": rs["state"], "message": rs["message"]}, **orphan_projects(p, ids)}


def orphan_projects(p: Paths, ids: dict) -> dict:
    """Project folders under output/projects/ that match no clip id and are no reel/motion/range project (no
    00_inputs/source.json), e.g. the shared 2.x `VIDEO` folder of two Arabic clips (gate G6)."""
    known = {str(k).upper() for k in ids}
    try:
        dirs = sorted(d for d in (p.output / "projects").iterdir() if d.is_dir())
    except OSError:
        dirs = []
    from .reels import unfinished_reel
    cand = [d.name for d in dirs if d.name.upper() not in known and not (d / "00_inputs/source.json").exists()]
    half = [u for u in (unfinished_reel(p.root, n) for n in cand) if u]     # T2.16: a Gate 0 that stopped half-way
    orphans = [n for n in cand if n not in {u["video_id"] for u in half}]
    hint = None
    if orphans:
        hint = (f"output/projects/{', '.join(orphans)} match no clip in data/ (an older or renamed project). Ask the "
                "editor which clip it belongs to: continue it with `--video-id <folder> --footage <the raw file>`, or "
                "leave it; never delete it yourself.")
    res = {"orphan_projects": orphans, "orphan_hint": hint}
    if half:
        res["unfinished_reels"] = [{k: u[k] for k in ("video_id", "episode", "pick", "as", "how")} for u in half]
    return res
