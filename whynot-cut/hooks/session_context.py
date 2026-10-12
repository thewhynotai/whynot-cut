#!/usr/bin/env python3
"""SessionStart: tell Claude when WhyNot Cut applies, and nothing otherwise (zero cost in unrelated sessions).

Speaks up when the session opens
  * inside a client folder (assets/ and data/ plus a positive marker: `.whynot-client`, `output/client_database/`, or
    lying under clients_root — see engine/reel/lib/client_marker.py): profile, engine, Premiere bridge, preferences,
    new clips; first a warning when another session holds the client's lease (output/.whynot-lock, 3.0 T1.8);
  * in the clients folder (setting `clients_root`, or a folder whose preferences file says so): which clients it holds;
  * in a folder that has a WhyNot Cut preferences file but no clients yet: point to /whynot-cut:start.
Whenever it speaks, it first warns loudly if the guard heartbeat (${CLAUDE_PLUGIN_DATA}/guard-ok, written by
guard.py) is missing or older than a guarded tool call the previous session's transcript records since it started:
tools ran but the read-only guard did not (a session that only read or chatted is no alarm).
Stdlib only; never fails the session (any error -> silent exit 0).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True        # the plugin folder stays clean of __pycache__
PLUGIN = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(PLUGIN / "engine" / "reel" / "lib"))
plat = settings = client_marker = None    # imported in main(), inside the never-fail guard

VIDEO = {".mp4", ".mov", ".mxf", ".m4v", ".avi", ".mkv"}
# the fallback scan of new_clips (engine unavailable) follows discovery's rule (lib/discover.py): the first folder under
# data/ decides (by its words), file-name hints are WORDS (camelCase and digits are word breaks)
FOLDER_WORDS = [("source", {"raw", "rushes"}), ("skip", {"ref", "refs", "reference", "references", "broll", "stock",
                                                        "stocks", "episodes", "music", "sfx"}), ("source", {"footage"})]


def _words(text: str) -> set:
    words = {w for w in re.split(r"[^a-z]+", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).lower()) if w}
    return words | ({"broll"} if re.search(r"b[-_ ]?roll", text.lower()) else set())


def _is_source_clip(segs: list) -> bool:
    """segs = path segments below the client root, e.g. ['data', 'Raw', 'a.mp4']."""
    if len(segs) > 2:
        w = _words(segs[1])
        kind = next((k for k, ws in FOLDER_WORDS if ws & w), None)
        if kind:
            return kind == "source"
    w = _words("/".join(segs[1:]))
    return not (w & {"ref", "refs", "reference", "references", "broll", "stock", "stocks"})


def is_client(p: Path, base=None) -> bool:
    return client_marker.is_client(p, base) if base is not None else client_marker.is_client(p)


def client_root(start: Path):
    return next((p for p in [start, *start.parents] if is_client(p)), None)


PREV_START: list = []   # [(time, transcript or None, its size then) of the previous SessionStart, or None]; main()
# the tools the PreToolUse guard inspects (hooks.json matcher; a test keeps the two equal)
GUARDED_TOOLS = ("Bash", "PowerShell", "Write", "Edit", "MultiEdit", "NotebookEdit")
_GUARDED_NAME = re.compile(rb'"name"\s*:\s*"(?:' + "|".join(GUARDED_TOOLS).encode() + rb')"')
_RECORD = re.compile(rb'"type"\s*:\s*"(?:assistant|user)"')      # a transcript record this code knows
_STAMP = re.compile(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)")


def note_session_start(transcript: str = ""):
    """Record this SessionStart in ${CLAUDE_PLUGIN_DATA}/last-session-start: time, this session's transcript path and
    the transcript's size now (0 when it does not exist yet; a resumed session's older turns lie before it). Returns
    the previous record as (time, transcript or None, size); None: no session recorded yet, i.e. a new install. A file
    from before T2.19 holds the time only (transcript None: the warning keeps its old rule once)."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not d:
        return None
    f = Path(d) / "last-session-start"
    try:
        lines = f.read_text(encoding="utf-8").splitlines() + ["", ""]
        prev = (float(lines[0].strip()), lines[1].strip() or None, int(lines[2].strip() or 0))
    except (OSError, ValueError, IndexError):
        prev = None
    try:
        size = os.path.getsize(transcript) if transcript else 0
    except OSError:
        size = 0
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{time.time()}\n{transcript}\n{size}\n", encoding="utf-8")
    except OSError:
        pass
    return prev


def _epoch(stamp):
    """Transcript timestamp `2026-10-11T20:51:15.355Z` (UTC) -> seconds; None when absent or unreadable."""
    m = _STAMP.match(str(stamp))                  # not strptime: its first call imports _strptime (slow at startup)
    try:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc).timestamp() if m else None
    except ValueError:
        return None


def guarded_calls_since(transcript: str, since: float, offset: int = 0, beat=None):
    """Did the previous session make a guarded tool call that the guard did not see? Reads the session's transcript
    from `offset` (its size when the session started: only that session's own turns, fix round 1 I1; from 0 when the
    file shrank) and its subagents' transcripts (<transcript stem>/subagents/*.jsonl) changed since then. A call counts
    when it was made at or after `since` (the session's start) and more than 2 s after the guard's last heartbeat
    `beat` (None: missing), so a guard that stopped in the middle of a session is caught too (M2).
    -> True: such a call; False: none (also: no transcript, or nothing written after `offset`); None: lines were
    written but none is a record this code recognises (a changed transcript format: the caller keeps the old rule, M4).
    Line by line, stops at the first hit; only lines naming a guarded tool are parsed."""
    after = since if beat is None else max(since, beat)
    t = Path(transcript)
    try:
        subs = [s for s in sorted((t.parent / t.stem / "subagents").glob("*.jsonl")) if s.stat().st_mtime >= after - 2]
    except OSError:
        subs = []
    lines_seen = known = False
    for f, start in [(t, offset), *((s, 0) for s in subs)]:
        try:
            with open(f, "rb") as fh:
                if start > os.fstat(fh.fileno()).st_size:
                    start = 0
                fh.seek(start)
                for line in fh:
                    if not line.strip():
                        continue
                    lines_seen = True
                    known = known or bool(_RECORD.search(line))
                    if b'"tool_use"' not in line or not _GUARDED_NAME.search(line):
                        continue
                    k = line.rfind(b'"timestamp":"')     # the record's own stamp (its last key): calls before
                    early = _epoch(line[k + 13:k + 32].decode("ascii", "replace")) if k >= 0 else None
                    if early is not None and not _counts(early, since, beat):    # `after` skip without parsing
                        continue
                    try:
                        rec = json.loads(line)
                        calls = [c for c in rec["message"]["content"] if isinstance(c, dict)
                                 and c.get("type") == "tool_use" and c.get("name") in GUARDED_TOOLS]
                    except (ValueError, KeyError, TypeError):
                        continue
                    when = _epoch(rec.get("timestamp"))
                    if calls and (when is None or _counts(when, since, beat)):
                        return True
        except OSError:
            continue
    return None if lines_seen and not known else False


def _counts(when: float, since: float, beat) -> bool:
    return when >= since - 2 and (beat is None or when > beat + 2)


def heartbeat_warning() -> str:
    """Loud first sentence when the guard missed tool calls of the previous session: ${CLAUDE_PLUGIN_DATA}/guard-ok
    (written by guard.py on every tool call it inspects) is missing or older than a guarded tool call that session's
    transcript records since it started (T2.19; fix round 1: only the part of the transcript written since then is
    read, and a call after the last heartbeat counts even when the guard ran earlier in that session). A session that
    only read or chatted, then /clear or a new session, is no alarm: the guard had nothing to inspect. Not hooks-ok:
    run_python.sh touches that right before running this hook (gate G1). Not a fixed age either: a weekend without
    sessions is no alarm (N4). Without a usable transcript (none recorded, or an unknown format) the old rule applies:
    guard-ok missing or older than the previous start. No previous session recorded, or no CLAUDE_PLUGIN_DATA: silent."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    prev, transcript, offset = (PREV_START[0] if PREV_START and PREV_START[0] else (None, None, 0))
    if not d or prev is None:
        return ""
    f = Path(d) / "guard-ok"
    try:
        beat = f.stat().st_mtime
    except OSError:
        beat = None
    hit = guarded_calls_since(transcript, prev, offset, beat) if transcript else None
    if hit is False or (hit is None and beat is not None and beat >= prev):
        return ""
    state = "is missing" if beat is None else (
        f"was last written {(time.time() - beat) / 3600:.1f} h ago, before "
        + ("a Bash/PowerShell/Write/Edit call of the previous session" if hit else "the previous session started"))
    return (f"WARNING: WhyNot Cut protection may be OFF: the guard heartbeat {state} ({f}), so the guard that keeps "
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
        vids = []        # fallback when the engine cannot be imported: same rule, on path SEGMENTS (never substrings)
        for f in files:
            segs = f.relative_to(root).as_posix().split("/")
            if f.suffix.lower() in VIDEO and not f.name.startswith(".") and _is_source_clip(segs):
                vids.append("".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in f.stem).strip("_").upper() or "VIDEO")
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
    """One writer per client folder (3.0 T1.8): warn when another session holds the client's lease."""
    try:
        import writer_lock
        rec = writer_lock.other_writer(root, session or writer_lock.session_id())
    except Exception:
        return ""
    if not rec:
        return ""
    return (f"WARNING: another session is working in this client ({writer_lock.describe(rec)}). It holds the "
            f"client (output/.whynot-lock), so your writing commands are refused: do not edit here in parallel, "
            f"tell the editor and never release its lock yourself. `reel lock --status` shows it; only if the "
            f"editor says that session is finished or stuck, the lead runs `reel lock --release`. ")


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
    """Plugin options (engine_home, clients_root) are given to hooks; pass them on so `reel` sees them too:
      * CLAUDE_ENV_FILE (Bash tool): `export WHYNOT_HOME='…'`, shell-quoted so Arabic paths stay literal;
      * the pointer file ~/.whynot-cut/plugin-options.json (plat.options_file()): PowerShell commands never receive
        a path-valued variable from the env file, so plat and both wrappers read the options from it (3.0 T1.9).
        Written only by a real SessionStart of the installed plugin (CLAUDE_ENV_FILE and CLAUDE_PLUGIN_DATA both set:
        a bare run, e.g. a test, never touches ~/.whynot-cut) and only when the options changed; one key per line,
        UTF-8, so reel.cmd can read it without Python."""
    opts = {"engine_home": os.environ.get("CLAUDE_PLUGIN_OPTION_ENGINE_HOME") or "",
            "clients_root": os.environ.get("CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT") or ""}
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        import shlex
        pairs = [("WHYNOT_HOME", opts["engine_home"]), ("WHYNOT_CLIENTS_ROOT", opts["clients_root"])]
        lines = [f"export {k}={shlex.quote(v)}\n" for k, v in pairs if v and not os.environ.get(k)]
        if lines:
            with open(env_file, "a", encoding="utf-8", newline="\n") as f:
                f.writelines(lines)
    if env_file and os.environ.get("CLAUDE_PLUGIN_DATA"):
        write_pointer(opts)


def write_pointer(opts: dict):
    f = plat.options_file()
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
        if all(old.get(k) == v for k, v in opts.items()):
            return
    except (OSError, ValueError, AttributeError):
        pass
    f.parent.mkdir(parents=True, exist_ok=True)
    body = {"clients_root": opts["clients_root"], "engine_home": opts["engine_home"],
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    tmp = f.with_name(f.name + f".{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(body, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, f)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


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
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    PREV_START.append(note_session_start(str(data.get("transcript_path") or "")))
    try:
        export_options()
    except OSError:
        pass
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
        emit(writer_line(root, data.get("session_id"))
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
