#!/usr/bin/env python3
"""SessionStart: tell Claude when WhyNot Cut applies, and nothing otherwise (zero cost in unrelated sessions).

Speaks up when the session opens
  * inside a client folder (assets/ and data/ plus a positive marker: `.whynot-client`, `output/client_database/`, or
    lying under clients_root — see engine/reel/lib/client_marker.py): profile, engine, Premiere bridge, preferences,
    new clips; first a warning when another session's writing command holds output/.whynot-lock (3.0 T1.8);
  * in the clients folder (setting `clients_root`, or a folder whose preferences file says so): which clients it holds;
  * in a folder that has a WhyNot Cut preferences file but no clients yet: point to /whynot-cut:start.
Whenever it speaks, it first warns loudly if the hooks heartbeat (${CLAUDE_PLUGIN_DATA}/hooks-ok, written by
run_python.sh) is missing or older than 24 h: the read-only guard may not be running.
Stdlib only; never fails the session (any error -> silent exit 0).
"""
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True        # the plugin folder stays clean of __pycache__
PLUGIN = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(PLUGIN / "engine" / "reel" / "lib"))
plat = settings = client_marker = None    # imported in main(), inside the never-fail guard

VIDEO = {".mp4", ".mov", ".mxf", ".m4v", ".avi", ".mkv"}
HEARTBEAT_MAX_AGE_S = 24 * 3600


def is_client(p: Path, base=None) -> bool:
    return client_marker.is_client(p, base) if base is not None else client_marker.is_client(p)


def client_root(start: Path):
    return next((p for p in [start, *start.parents] if is_client(p)), None)


def heartbeat_warning() -> str:
    """Loud first sentence when ${CLAUDE_PLUGIN_DATA}/hooks-ok is missing or stale (no CLAUDE_PLUGIN_DATA: silent)."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not d:
        return ""
    f = Path(d) / "hooks-ok"
    try:
        age = time.time() - f.stat().st_mtime
    except OSError:
        age = None
    if age is not None and age < HEARTBEAT_MAX_AGE_S:
        return ""
    state = "is missing" if age is None else f"is {age / 3600:.0f} h old"
    return (f"WARNING: WhyNot Cut protection may be OFF: the hooks heartbeat {state} ({f}), so the guard that keeps "
            f"assets/ and data/ read-only may not be running. Run `reel doctor` and tell the editor before editing. ")


def emit(ctx: str):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": heartbeat_warning() + ctx}}))


def bridge_state(home: Path) -> str:
    try:
        hb = json.loads((home / "ppro-queue/bridge.heartbeat").read_text(encoding="utf-8"))
        age = time.time() - hb["at"] / 1000
        return "alive" if age < 5 else f"not responding ({age:.0f}s old heartbeat: start Premiere)"
    except Exception:
        return "not running (open Premiere Pro)"


def new_clips(root: Path) -> list:
    files = [f for f in sorted((root / "data").rglob("*")) if f.is_file()]
    try:      # the clips and ids `reel inbox` hands out (discovery's classifier, output/discovery/clip-ids.json);
        sys.path.insert(0, str(PLUGIN / "engine" / "reel"))       # read-only here: nothing is written
        from lib import clip_ids
        from lib.discover import classify, is_junk
        rels = [r for f, r in ((f, f.relative_to(root).as_posix()) for f in files)
                if not is_junk(f) and classify(f, r)["role"] == "source_footage"]
        ids = clip_ids.assign(root, rels, clip_ids.load(root))
        vids = [clip_ids.id_of(ids, r) for r in rels]
    except Exception:
        vids = []
        for f in files:
            low = f.relative_to(root).as_posix().lower()
            if f.suffix.lower() in VIDEO and not f.name.startswith(".") and "ref" not in low \
                    and not low.startswith("data/episodes/"):       # episodes are cut into reels (podcast mode)
                vids.append("".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in f.stem).strip("_").upper()
                            or "VIDEO")
    return [v for v in vids if not (root / "output/projects" / v / "02_transcription/transcript.json").exists()][:12]


def episodes(root: Path) -> list:
    """Podcast episodes waiting in data/Episodes (file names)."""
    d = root / "data" / "Episodes"
    audio = {".mp3", ".wav", ".m4a", ".aac", ".flac"}
    return [f.stem + (" (audio)" if f.suffix.lower() in audio else "") for f in sorted(d.glob("*"))
            if f.suffix.lower() in VIDEO | audio and not f.name.startswith(".")][:8] if d.is_dir() else []


def reference_style_line(root: Path, has_profile: bool) -> str:
    """The client reference style is written once per client; say so when the reference edits changed since (stale),
    or when references exist but no client style was recorded yet."""
    try:
        sys.path.insert(0, str(PLUGIN / "engine" / "reel"))
        from lib import ref_style
        st = ref_style.state(root)
    except Exception:
        return ""
    if st["state"] == "stale" or (has_profile and st["references"] and st["state"] in ("missing", "unrecorded")):
        return f"Reference style: {st['message']}. "
    return ""


def writer_line(root: Path, session) -> str:
    """One writer per client folder (3.0 T1.8): warn when another session's writing command holds the lock now."""
    try:
        import writer_lock
        rec = writer_lock.other_writer(root, session)
    except Exception:
        return ""
    if not rec:
        return ""
    return (f"WARNING: another session is working in this client ({writer_lock.describe(rec)}). Its writing commands "
            f"hold output/.whynot-lock; yours are refused until it finishes, so do not start an edit here in "
            f"parallel: tell the editor. `reel lock --status` shows it; only if the editor says that session is "
            f"finished or stuck, the lead runs `reel lock --release`. ")


def prefs_line(st: dict) -> str:
    if not st.get("_file"):
        return "Preferences: none yet (/whynot-cut:preferences)."
    who = f" Editor: {st['editor_name']}." if st.get("editor_name") else ""
    lang = " Talk to the editor in Arabic." if st.get("language") == "ar" else ""
    appr = (" Approval: auto (show the plan and preview, then record `approve-plan --by delegated --note "
            "\"standing preference in " + st["_file"] + "\"` without waiting)." if st.get("approval") == "auto"
            else " Approval: ask (stop at Gate 1).")
    return f"Preferences: {st['_file']}.{who}{lang}{appr} Whisper: {st.get('whisper_model')}."


def export_options():
    """Plugin options (engine_home, clients_root) are given to hooks; pass them on to the Bash/PowerShell tool
    environment so `reel` sees them too (the wrappers read WHYNOT_HOME / WHYNOT_CLIENTS_ROOT)."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    pairs = [("WHYNOT_HOME", os.environ.get("CLAUDE_PLUGIN_OPTION_ENGINE_HOME")),
             ("WHYNOT_CLIENTS_ROOT", os.environ.get("CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT"))]
    lines = [f"export {k}={json.dumps(v)}" + "\n" for k, v in pairs if v and not os.environ.get(k)]
    if lines:
        with open(env_file, "a", encoding="utf-8") as f:
            f.writelines(lines)


def main():
    global plat, settings, client_marker
    if sys.version_info < (3, 8):     # run_python.sh no longer probes the version
        emit("WhyNot Cut protection is OFF: Python %d.%d is too old (3.8+ needed) — run reel doctor"
             % sys.version_info[:2])
        return
    import plat as _plat
    import settings as _settings
    import client_marker as _client_marker
    plat, settings, client_marker = _plat, _settings, _client_marker
    try:
        export_options()
    except OSError:
        pass
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    cwd = Path(plat.native_path(data.get("cwd") or os.getcwd()))
    st = settings.load(cwd)
    home = plat.engine_home()
    env_ok = plat.venv_python(home).exists()
    root = client_root(cwd)
    if root:
        prof = None
        try:
            prof = json.loads((root / "output/client_database/reel-profile/profile.json").read_text(encoding="utf-8")).get("id")
        except Exception:
            pass
        clips = new_clips(root)
        eps = episodes(root)
        emit(writer_line(root, data.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID"))
             + f"WhyNot Cut: this is a client folder ({root}). Profile: {prof or 'NONE (run /whynot-cut:new-client)'}. "
             f"Engine: {'ok' if env_ok else 'not installed (run /whynot-cut:start)'}. "
             f"Premiere bridge: {bridge_state(home)}. "
             f"New clips not started yet: {', '.join(clips) if clips else 'none'}. "
             + (f"Podcast episodes in data/Episodes: {', '.join(eps)} (reels plan + publish package: /whynot-cut:podcast; "
                f"animated motion videos from a window's audio, built in After Effects: /whynot-cut:motion; "
                f"`reel episodes` shows their state). " if eps else "")
             + reference_style_line(root, bool(prof))
             + f"{prefs_line(st)} "
             f"Use /whynot-cut:autopilot (edit every new clip), /whynot-cut:edit <clip>, /whynot-cut:revise, "
             f"/whynot-cut:status. assets/ and data/ are read-only.")
        return
    legacy = cwd if client_marker.has_layout(cwd) and (cwd / "output").is_dir() and any(
        (cwd / x).exists() for x in ("START_HERE.md", "output/projects", "output/discovery")) else None
    if legacy:            # an unmarked 2.x client opened at its root (WhyNot Cut output there), not under clients_root
        emit(f"WhyNot Cut: {legacy} looks like a WhyNot Cut client without a marker (no .whynot-client), so its "
             f"assets/ and data/ are NOT protected by the guard yet. Run `reel doctor --fix --root \"{legacy}\"` "
             f"(it only writes the marker at the client root), then continue.")
        return
    base = plat.clients_root_setting() or (Path(st["clients_root"]).expanduser() if st.get("clients_root") else None)
    try:
        at_base = bool(base) and cwd.resolve() == Path(plat.native_path(str(base))).resolve()
        names = sorted(p.name for p in cwd.iterdir() if p.is_dir() and is_client(p, base)) if at_base else []
    except OSError:
        at_base, names = False, []
    if at_base:
        emit(f"WhyNot Cut: this is the clients folder ({cwd}). Client folders: {', '.join(names) or 'none yet'}. "
             f"Pass one to reel as --root \"<name>\", or say 'edit the new videos' (/whynot-cut:autopilot). "
             f"New client: /whynot-cut:new-client. Engine: {'ok' if env_ok else 'not installed (/whynot-cut:start)'}. "
             f"{prefs_line(st)}")
    elif st.get("_file") and Path(st["_file"]).parent.parent == cwd.resolve():
        emit(f"WhyNot Cut is set up here ({prefs_line(st)}) but no client folder is open. "
             f"Run /whynot-cut:start to continue onboarding or /whynot-cut:new-client to add a client.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
