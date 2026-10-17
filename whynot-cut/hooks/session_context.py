#!/usr/bin/env python3
"""SessionStart: tell Claude when WhyNot Cut applies, and nothing otherwise (zero cost in unrelated sessions).

Speaks up when the session opens
  * inside a client folder (assets/ and data/ plus a positive marker: `.whynot-client`, `output/client_database/`, or
    lying under clients_root — see engine/reel/lib/client_marker.py): profile, engine, Premiere bridge, preferences,
    new clips; first a warning when another session holds the client's lease (output/.whynot-lock, 3.0 T1.8);
  * in the clients folder (setting `clients_root`, or a folder whose preferences file says so): which clients it holds;
  * in a folder that has a WhyNot Cut preferences file but no clients yet: point to /whynot-cut:start.
With it (3.0 T3.4): what the editor did in the Premiere panel and Claude has not acted on (approvals not built yet,
change requests), updates the installer would bring (setup/components.json vs <engine home>/state.json), and in the
clients folder the clients another session is writing in. Once per install (${CLAUDE_PLUGIN_DATA}/first-run-done) an
otherwise silent start of a machine that is not set up yet says to offer /whynot-cut:start. It writes
~/.whynot-cut/plugin-root.json {root, version, at} for the daemon shim and the panel.
CwdChanged runs this file too: the same context for the new folder, once per place (see flush_cwd).
Then it starts the panel link: `reel serve --ensure --quiet` (the engine the Premiere panel talks to) as a fully
detached child it never waits for (Addendum C2.1); skipped when the preference `panel_link` is off, under
WHYNOT_TEST_SANDBOX or without an engine runtime; a failure is one short line of context, never a failed hook.
Whenever it speaks, it first warns loudly if the guard heartbeat (${CLAUDE_PLUGIN_DATA}/guard-ok, written by
guard.py) is missing or older than a guarded tool call the previous session's transcript records since it started:
tools ran but the read-only guard did not (a session that only read or chatted is no alarm).
Stdlib only; never fails the session (any error -> silent exit 0). One JSON document is printed, at the end.
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
# Same order as discover._FOLDER_WORDS: the most specific role first ("Raw B-roll" is B-roll). Music/SFX folders are
# not listed: discovery gives them an audio role only, so a VIDEO there is judged by its path like any loose video.
FOLDER_WORDS = [("skip", {"ref", "refs", "reference", "references", "broll", "stock", "stocks"}),
                ("source", {"raw", "rushes"}), ("source", {"footage"})]
_L = r"[^\W\d_]"
_BROLL = rf"broll|(?<!{_L})b[-_ ]rolls?(?!{_L})"       # as discover._BROLL: "Jacob rolls", "Bob rolling" are not B-roll


def _camel(text: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text).lower()


def _folder_words(text: str) -> set:
    """A data folder's words, as discover.folder_kind reads them (Latin letters; camelCase is a break)."""
    words = {w for w in re.split(r"[^a-z]+", _camel(text)) if w}
    return words | ({"broll"} if re.search(_BROLL, text.lower()) else set())


def _words(text: str) -> set:
    """A path's file-name hint words, as discover's word-bounded hints read them: runs of letters in ANY script, so an
    Arabic word glued to a Latin hint (`مقابلةref`) is one word and no hint (3.0 T3.4, T2.5 carry-over)."""
    words = set(re.findall(rf"{_L}+", _camel(text)))
    return words | ({"broll"} if re.search(_BROLL, text.lower()) else set())


def _is_source_clip(segs: list) -> bool:
    """segs = path segments below the client root, e.g. ['data', 'Raw', 'a.mp4']."""
    if len(segs) > 2:
        if segs[1].lower() == "episodes":
            return False                       # finished episodes are cut into reels, never edited whole
        w = _folder_words(segs[1])
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
# the tools the PreToolUse guard inspects (hooks.json matchers; a test keeps the two equal)
GUARDED_TOOLS = ("Bash", "PowerShell", "Write", "Edit", "MultiEdit", "NotebookEdit")
# 3.0 T3.4: the file tools run the guard only for a path one of these permission-rule patterns matches (hooks.json
# `if`, one handler per tool and pattern; a test keeps both equal): a client's sources (assets/, data/ at any depth, any
# case), the marker and the writer lock (`*.whynot-*`), After Effects preferences. Everything else the guard would
# allow anyway, so a Write outside them starts no process. `X/**` also matches X itself (seen live, CLI 2.1.295).
FILE_IF_TOOLS = ("Write", "Edit", "NotebookEdit")
FILE_IF_PATTERNS = ("//**/[Aa][Ss][Ss][Ee][Tt][Ss]/**", "//**/[Dd][Aa][Tt][Aa]/**", "//**/*.whynot-*/**",
                    "//**/*[Aa][Ff][Tt][Ee][Rr] [Ee][Ff][Ff][Ee][Cc][Tt][Ss]*/**")


def _glob_rx(pattern: str) -> str:
    """One `if` path pattern as a regex over a /-separated path (this code's mirror of Claude Code's matcher)."""
    p, out, i = pattern[2:] if pattern.startswith("//") else pattern, "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif p.startswith("/**", i) and i + 3 == len(p):
            out, i = out + "(?:/.*)?", i + 3
        elif p[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif p[i] == "[":
            j = p.index("]", i)
            out, i = out + p[i:j + 1], j + 1
        else:
            out, i = out + re.escape(p[i]), i + 1
    return out


_FILE_IF = re.compile("|".join(f"(?:{_glob_rx(p)})" for p in FILE_IF_PATTERNS), re.I)


def file_guarded(path) -> bool:
    """Does a Write/Edit/NotebookEdit of `path` start the guard (the hooks.json `if` filter)? Unknown path: yes."""
    if not path or not isinstance(path, str):
        return True
    return bool(_FILE_IF.fullmatch(path.replace("\\", "/").lstrip("/")))
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
    -> True: such a call; False: none (also: the transcript file was never written in its existing folder, or nothing
    was written after `offset`); None: lines were written but none is a record this code recognises (a changed
    transcript format: the caller keeps the old rule, M4), or the transcript cannot be read (a directory, no
    permission, its folder gone: Gate 2 G1 C5, also the old rule, never silence).
    Line by line, stops at the first hit; only lines naming a guarded tool are parsed."""
    after = since if beat is None else max(since, beat)
    t = Path(transcript)
    try:
        subs = [s for s in sorted((t.parent / t.stem / "subagents").glob("*.jsonl")) if s.stat().st_mtime >= after - 2]
    except OSError:
        subs = []
    lines_seen = known = unreadable = False
    for f, start in [(t, offset), *((s, 0) for s in subs)]:
        try:
            if f is t and not t.is_file() and (t.exists() or not t.parent.is_dir()):
                unreadable = True           # G1 C5: a directory, or the transcripts folder is gone (moved location)
                continue
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
                                 and c.get("type") == "tool_use" and c.get("name") in GUARDED_TOOLS
                                 and _reaches_guard(c)]
                    except (ValueError, KeyError, TypeError):
                        continue
                    when = _epoch(rec.get("timestamp"))
                    if calls and (when is None or _counts(when, since, beat)):
                        return True
        except FileNotFoundError:               # not written (a session closed before its first turn): nothing to see
            continue
        except OSError:
            unreadable = unreadable or f is t       # the session's own transcript could not be read
            continue
    return None if unreadable or (lines_seen and not known) else False


def _reaches_guard(call: dict) -> bool:
    """A file tool call outside the `if` patterns never starts the guard: no heartbeat is expected for it."""
    if call.get("name") not in FILE_IF_TOOLS:
        return True
    ti = call.get("input") if isinstance(call.get("input"), dict) else {}
    return file_guarded(ti.get("file_path") or ti.get("notebook_path"))


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


PENDING: list = []      # the context main() decided on; printed once by run(), after the panel link was started
LINK: list = []         # [(engine home, preferences)] once main() knows them: run() starts the panel link
DATA: dict = {}         # the hook input (session_id, hook_event_name, ...), once main() has read it
SCOPE: list = []        # [where the context speaks about: a client root, the clients folder, a set-up folder]
CWD_EVENT = "CwdChanged"


def emit(ctx: str):
    PENDING.append(heartbeat_warning() + ctx)


def flush_cwd():
    """CwdChanged (T3.4): the same context as SessionStart for the new folder, said once per place. Claude Code reads
    only `systemMessage` (a short note to the editor) and `watchPaths` from this event, so the context itself waits in
    ${CLAUDE_PLUGIN_DATA}/pending-context/<session> and the guard hands it to Claude with its next Bash/PowerShell call
    (PreToolUse additionalContext: no extra process). Moving inside the same client says nothing; leaving WhyNot Cut's
    folders only forgets the place."""
    sid = DATA.get("session_id")
    scope_f = session_file("scope", sid)
    new = SCOPE[0] if SCOPE else ""
    try:
        old = scope_f.read_text(encoding="utf-8") if scope_f else ""
    except OSError:
        old = ""
    text = "".join(PENDING)
    if old == new or not scope_f:
        return
    if not new:
        for f in (scope_f, session_file("pending-context", sid)):    # a context for the folder left is stale now
            try:
                f.unlink()
            except OSError:
                pass
        return
    _write(scope_f, new)
    if not text:
        return
    _write(session_file("pending-context", sid), text)
    print(json.dumps({"systemMessage": f"WhyNot Cut: {SCOPE[1] if len(SCOPE) > 1 else new}"}, ensure_ascii=False))


def flush(extra: str = ""):
    text = "".join(PENDING) + extra
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))


# ---------------------------------------------------------------------------------------- panel link (Addendum C2.1)
WINDOWS = os.name == "nt"
SERVE_MAIN = PLUGIN / "engine" / "reel" / "serve" / "__main__.py"
# Windows creation flags (literal: the subprocess constants exist only on Windows)
NO_WINDOW, DETACHED, NEW_GROUP, BREAKAWAY = 0x08000000, 0x00000008, 0x00000200, 0x01000000


def _popen(cmd, **kw):
    """subprocess.Popen for the panel-link child only (tests replace this)."""
    import subprocess
    return subprocess.Popen(cmd, **kw)


def panel_link(home: Path, st: dict) -> str:
    """Start `serve --ensure --quiet` with the engine interpreter, fully detached, and return at once (the child
    finds a running daemon, or starts one and exits; `ensure` is idempotent and single-instance). Not waited for, its
    output goes nowhere (never the hook's pipes, which Claude Code reads to EOF). Windows: no console window, its own
    process group, out of the hook runner's job when the job allows it; macOS/Linux: a new session. "" when started
    or skipped (preference `panel_link` off, the test sandbox, no engine runtime yet); otherwise one short line."""
    try:
        if os.environ.get("WHYNOT_TEST_SANDBOX"):
            return ""
        if str(st.get("panel_link", True)).strip().lower() in ("false", "off", "no", "0"):
            return ""
        py = plat.venv_python(home)
        if not py.is_file():
            return ""                  # nothing to start yet; the context already says how to install the engine
        import subprocess
        cmd = [str(py), "-s", "-B", "-P", str(SERVE_MAIN), "--ensure", "--quiet"]
        kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "close_fds": True, "cwd": str(home)}
        if WINDOWS:
            flags = NO_WINDOW | DETACHED | NEW_GROUP
            try:
                _popen(cmd, creationflags=flags | BREAKAWAY, **kw)
            except OSError:           # the hook runner's job forbids breakaway: start inside it
                _popen(cmd, creationflags=flags, **kw)
        else:
            _popen(cmd, start_new_session=True, **kw)
        return ""
    except Exception as e:  # noqa: BLE001 — the session start must never fail on this
        why = " ".join(str(e).split()) or type(e).__name__
        return f"WhyNot Cut panel link not started: {why[:160]} (the Premiere panel stays offline; `reel serve ensure` retries). "


def run():
    """The hook: the context (main), then the panel link, then one print. Never raises."""
    try:
        main()
    except Exception:  # noqa: BLE001 — as before: a context that failed says nothing
        PENDING.clear()
    if DATA.get("hook_event_name") == CWD_EVENT:
        flush_cwd()
        return
    flush(panel_link(*LINK[0]) if LINK else "")


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


def _when(at) -> str:
    """ISO time -> "14:02" today, else "2026-10-12 14:02"."""
    at = str(at or "")
    if len(at) < 16:
        return at or "?"
    return at[11:16] if at[:10] == time.strftime("%Y-%m-%d") else f"{at[:10]} {at[11:16]}"


def _read_json(f: Path):
    try:
        return json.loads(f.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


# the panel writes change requests next to the item only (Addendum C ecosystem §234: `<item>/panel-requests.json`)
REQUEST_GLOBS = ("output/projects/*/panel-requests.json",)
_DONE = ("done", "resolved", "handled", "closed")


def panel_line(root: Path) -> str:
    """What the editor did in the Premiere panel and Claude has not acted on yet (Addendum C §5.2, T6.6 text): plan
    approvals given in the panel (01_analysis/plan-approval.json `via: panel`) of items not built since, and change
    requests (<item>/panel-requests.json: a list, or {"requests": [...]}, entries {text, at, editor_name} not marked
    done/resolved/handled). Read only when present (Phase 6 writes them); one listing of output/projects, never a
    tree walk."""
    approvals, requests = [], []
    for f in sorted(root.glob("output/projects/*/01_analysis/plan-approval.json"))[:300]:
        rec = _read_json(f)
        if not isinstance(rec, dict) or rec.get("via") != "panel" or rec.get("approved") is False or rec.get("stale"):
            continue
        item = f.parents[1]
        try:
            at = f.stat().st_mtime
            if any((item / b).stat().st_mtime >= at for b in ("07_premiere/ppro-build-result.json",
                                                             "04_after_effects/ae-build-result.json")
                   if (item / b).is_file()):
                continue                                    # built after the approval: nothing pending
        except OSError:
            pass
        approvals.append(f"{rec.get('editor_name') or 'the editor'} approved {item.name} in Premiere at {_when(rec.get('at'))}")
    seen = set()
    for pat in REQUEST_GLOBS:
        for f in sorted(root.glob(pat))[:100]:
            if f in seen:
                continue
            seen.add(f)
            rec = _read_json(f)
            items = rec.get("requests") if isinstance(rec, dict) else rec
            todo = [e for e in items if isinstance(e, dict) and not any(e.get(k) for k in _DONE)
                    and str(e.get("status") or "").lower() not in _DONE] if isinstance(items, list) else []
            if todo:
                last = " ".join(str(todo[-1].get("text") or "").split())[:120]
                requests.append(f"{f.parent.name} ({len(todo)}{', latest: “' + last + '”' if last else ''})")
    out = ""
    if approvals:
        # "Panel approvals not built yet" read as "the panel's approval feature is not built yet" (3.0 G3 evals): say
        # what happened, that it counts, and what comes next
        out += ("Plans approved in the Premiere panel, waiting for their build: " + "; ".join(approvals[:6])
                + ". The approval is recorded: don't ask for it again; next is the build (`reel next` shows it). ")
    if requests:
        out += ("Change requests from the Premiere panel waiting: " + "; ".join(requests[:6])
                + " (/whynot-cut:revise; `reel next` shows them). ")
    return out


def _platform_key() -> str:
    import platform
    if os.name == "nt":
        return "win-x64"
    return "mac-arm64" if platform.machine().lower() in ("arm64", "aarch64") else "mac-x64"


def updates_line(home: Path) -> str:
    """Pending updates (Phase 7): what this plugin's setup/components.json pins versus what the installer recorded in
    <engine home>/state.json. Silent without state.json (2.x / `reel setup` installs) or for "<release>" values."""
    st = _read_json(home / "state.json")
    comp = _read_json(PLUGIN / "setup" / "components.json")
    if not isinstance(st, dict) or not isinstance(comp, dict):
        return ""

    def ver(d, *keys):
        for k in keys:
            d = d.get(k) if isinstance(d, dict) else None
        return str(d) if isinstance(d, (str, int)) and str(d) and str(d) != "<release>" else None
    pend = []
    for name, have, want in (("plugin", ver(st, "plugin"), ver(comp, "plugin")),
                             ("engine runtime", ver(st, "runtime", "id"),
                              ver(comp, "runtime", "locks", _platform_key(), "id")),
                             ("ffmpeg", ver(st, "ffmpeg", "version"), ver(comp, "ffmpeg", "version")),
                             ("fonts", ver(st, "fonts", "version"), ver(comp, "fonts", "version"))):
        if have and want and have != want:
            pend.append(f"{name} {have} → {want}")
    return (f"Updates pending ({', '.join(pend)}): the WhyNot Cut installer brings them; ask the editor before "
            f"running it. ") if pend else ""


CLIENT_SCAN_BUDGET_S = 1.0      # the clients-folder lists share this (a NAS with many clients must not eat the 10 s)


def clients_lists(base: Path, names: list, budget: float = CLIENT_SCAN_BUDGET_S) -> str:
    """Clients folder: which clients another session is writing in right now (their live writer lease, T1.8), and
    the clients with panel approvals or change requests waiting (panel_line per client).
    Fix round 2 (m1): two passes. First every client's lease (the SessionStart clear/resume re-key and the busy list:
    one small file per client, cheap, never skipped: a session must not be locked out of its own client by a time
    budget). Then the panel scan under one time budget (a NAS with many clients must not eat the 10 s); when it runs
    out the rest is not checked and the line says so, counting all clients."""
    try:
        import writer_lock
    except Exception:
        writer_lock = None
    busy, hits, checked = [], [], 0
    if writer_lock is not None:
        for n in names:
            try:
                continue_lease(base / n)
                rec = writer_lock.other_writer(base / n, DATA.get("session_id") or writer_lock.session_id())
            except Exception:
                rec = None
            if rec:
                busy.append(f"{n} ({writer_lock.describe(rec)})")
    deadline = time.monotonic() + budget
    for n in names:
        if checked and time.monotonic() >= deadline:
            break
        checked += 1
        try:
            line = panel_line(base / n)
        except Exception:
            line = ""
        if line:
            hits.append(f"[{n}] {line.strip()}")
    out = (f"Busy (another session holds the client, do not write there): {'; '.join(busy[:8])}. " if busy else "")
    out += ("Premiere panel: " + " ".join(hits[:8]) + " ") if hits else ""
    if checked < len(names):
        out += (f"(scan cut short: {len(names) - checked} of {len(names)} clients not checked for panel approvals "
                f"or change requests) ")
    return out


# ------------------------------------------------- per-session state in ${CLAUDE_PLUGIN_DATA} (T3.4; SessionEnd cleans)
def session_file(kind: str, sid):
    """${CLAUDE_PLUGIN_DATA}/<kind>/<session id>: scope (where this session was last told it is), pending-context (a
    CwdChanged context the guard hands Claude at its next Bash/PowerShell call), evidence-gate (the Stop gate is on)."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(sid or ""))[:100]
    return Path(d) / kind / sid if d and sid else None


def _write(f, text: str):
    if f is None:
        return
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass


def first_run() -> bool:
    """True once per install: ${CLAUDE_PLUGIN_DATA}/first-run-done did not exist (it does now). No data folder: False
    (nothing to remember with, so never nudge)."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not d:
        return False
    f = Path(d) / "first-run-done"
    if f.exists():
        return False
    _write(f, time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n")
    return True


def plugin_root_file() -> Path:
    """~/.whynot-cut/plugin-root.json, next to the options pointer (WHYNOT_OPTIONS_FILE moves both)."""
    return plat.options_file().with_name("plugin-root.json")


def write_plugin_root():
    """Addendum C §3.2: {root, version, at} for the daemon shim and the panel, which must not depend on PATH or the
    versioned plugin cache path. Written by a real SessionStart only (CLAUDE_PLUGIN_ROOT, CLAUDE_ENV_FILE and
    CLAUDE_PLUGIN_DATA set, the rule of export_options: a bare run never creates ~/.whynot-cut) and only when the root
    or version changed."""
    if not all(os.environ.get(k) for k in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_ENV_FILE", "CLAUDE_PLUGIN_DATA")):
        return
    version = str((_read_json(PLUGIN / ".claude-plugin" / "plugin.json") or {}).get("version") or "")
    f = plugin_root_file()
    old = _read_json(f)
    if isinstance(old, dict) and old.get("root") == str(PLUGIN) and old.get("version") == version:
        return
    body = {"root": str(PLUGIN), "version": version, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    _write(f, json.dumps(body, ensure_ascii=False, indent=1) + "\n")


def continue_lease(root: Path):
    """SessionStart after /clear or /resume (fix round 1, M3): the lease this Claude Code process (CLAUDE_PID) held
    under the previous session id is this session's now (SessionEnd's 1.5 s may have missed releasing it). The only
    takeover of a live lease: a new session id at any other time is another writer (T1.8).
    `fork` (a branched conversation) deliberately does not rekey: a fork is a different conversation, not the same
    one continued (fix round 2, m4)."""
    if DATA.get("hook_event_name") != "SessionStart" or DATA.get("source") not in ("clear", "resume"):
        return
    sid = DATA.get("session_id")
    if sid:
        import writer_lock
        writer_lock.rekey(root, str(sid))


def writer_line(root: Path, session) -> str:
    """One writer per client folder (3.0 T1.8): warn when another session holds the client's lease."""
    try:
        import writer_lock
        continue_lease(root)
        rec = writer_lock.other_writer(root, session or writer_lock.session_id())
    except Exception:
        return ""
    if not rec:
        return ""
    return (f"WARNING: another session is working in this client ({writer_lock.describe(rec)}). It holds the "
            f"client (output/.whynot-lock), so your writing commands are refused: do not edit here in parallel, "
            f"tell the editor and never release its lock yourself. `reel lock --status` shows it; only if the "
            f"editor says that session is finished or stuck, the lead runs `reel lock --release`. ")


# Every WhyNot Cut context (client folder, clients folder, set up here) says it (G3 review M1): editors are told to
# start Claude in the clients folder, and the output style is opt-in.
READ_ONLY_RULE = ("Every client folder's assets/ and data/ are read-only: never offer to rename, move, convert, "
                  "overwrite or delete anything inside them (e.g. the footage in data/Raw), not even once the editor "
                  "confirms; offer a copy under output/ or the reel command that leaves the sources untouched.")


# G3 review I1 (approval consent): a standing `approval: auto` is the editor's own choice, so "stop asking" / "just go"
# is answered with a question and a stop, in every session context (the preferences skill may not be loaded yet).
CONSENT_RULE = (" \"Stop asking\" / \"just go\" never switches approval by itself: ask \"this clip only, or from now "
                "on?\", end your turn, and write approval=auto only after the editor answers \"from now on\".")


def prefs_line(st: dict) -> str:
    """The values in effect: from the preferences files, or (no file) from the plugin options (3.0 T3.5)."""
    opts = "userConfig" in set((st.get("_sources") or {}).values())
    if not st.get("_file") and not opts:
        return "Preferences: none yet (/whynot-cut:preferences)." + CONSENT_RULE
    who = f" Editor: {st['editor_name']}." if st.get("editor_name") else ""
    lang = " Talk to the editor in Arabic." if st.get("language") == "ar" else ""
    src = (st.get("_where") or {}).get("approval")
    src = src if src and src != "default" else (st.get("_file") or "plugin option")
    appr = (" Approval: auto (standing preference in " + src + ": show the plan and preview, then record "
            "`reel auto-approve` without waiting; medical and religious approvals are never automatic: "
            "they stay on `output/NEEDS-YOU.md` (`reel needs-you --write`))." if st.get("approval") == "auto"
            else " Approval: ask (stop for the editor's OK on every plan).")
    return (f"Preferences: {st['_file'] or 'the WhyNot Cut plugin options'}.{who}{lang}{appr}{CONSENT_RULE} "
            f"Whisper: {st.get('whisper_model')}.")


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
    pointer = dict(opts)      # + the other non-secret options (language, approval, ...): the engine's preference layer
    for k in plat.USER_OPTION_KEYS:     # (never the sensitive ones: the API key is not written to any file)
        pointer[k] = os.environ.get("CLAUDE_PLUGIN_OPTION_" + k.upper()) or ""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        import shlex
        pairs = [("WHYNOT_HOME", opts["engine_home"]), ("WHYNOT_CLIENTS_ROOT", opts["clients_root"])]
        lines = [f"export {k}={shlex.quote(v)}\n" for k, v in pairs if v and not os.environ.get(k)]
        if lines:
            with open(env_file, "a", encoding="utf-8", newline="\n") as f:
                f.writelines(lines)
    if env_file and os.environ.get("CLAUDE_PLUGIN_DATA"):
        write_pointer(pointer)


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
            **{k: v for k, v in opts.items() if k not in ("clients_root", "engine_home")},
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
    DATA.update(data)
    cwd_event = data.get("hook_event_name") == CWD_EVENT
    if not cwd_event:
        PREV_START.append(note_session_start(str(data.get("transcript_path") or "")))
    try:
        export_options()
    except OSError:
        pass
    if not cwd_event:
        try:
            write_plugin_root()
        except Exception:  # noqa: BLE001 — the daemon falls back to installed_plugins.json
            pass
    first = first_run() if not cwd_event else False
    cwd = Path(plat.native_path((data.get("new_cwd") if cwd_event else None) or data.get("cwd") or os.getcwd()))
    st = settings.load(cwd)
    home = plat.engine_home()
    if not cwd_event:
        LINK.append((home, st))
    env_ok = plat.venv_python(home).exists()
    speak(cwd, st, home, env_ok, data)
    sid = data.get("session_id")
    gate = ("evidence-gate", bool(SCOPE) and st.get("evidence_gate") in (True, "on") and st.get("approval") != "auto")
    # CwdChanged: flush_cwd keeps the scope file; the evidence-gate flag follows the new folder (fix round 1, M4)
    for kind, on in ((gate,) if cwd_event else (("scope", bool(SCOPE)), gate)):
        f = session_file(kind, sid)
        if f is not None and on:
            _write(f, SCOPE[0] if kind == "scope" else "on\n")
        elif f is not None:
            try:
                f.unlink()          # an unrelated folder leaves nothing behind
            except OSError:
                pass
    if cwd_event:
        return
    if first and not PENDING and not (env_ok and st.get("_file")):
        emit("WhyNot Cut was just installed and is not set up yet. Say so once, briefly, in the editor's language, and "
             "offer /whynot-cut:start (it sets everything up step by step); then carry on with what they asked.")


def speak(cwd: Path, st: dict, home: Path, env_ok: bool, data: dict):
    """The context for a folder (SessionStart and CwdChanged): emit() it and record the place in SCOPE."""
    root = client_root(cwd)
    if root:
        SCOPE[:] = [str(root), f"client folder {root.name}"]
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
             + panel_line(root)
             + reference_style_line(root, bool(prof))
             + updates_line(home)
             + f"{prefs_line(st)} "
             f"Use /whynot-cut:autopilot (edit every new clip), /whynot-cut:edit <clip>, /whynot-cut:revise, "
             f"/whynot-cut:status. " + READ_ONLY_RULE)
        return
    legacy = cwd if client_marker.has_layout(cwd) and (cwd / "output").is_dir() and any(
        (cwd / x).exists() for x in ("START_HERE.md", "output/projects", "output/discovery")) else None
    if legacy:            # an unmarked 2.x client opened at its root (WhyNot Cut output there), not under clients_root
        SCOPE[:] = [str(legacy), f"{legacy.name} looks like a client folder without a marker"]
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
        SCOPE[:] = [str(cwd), "the clients folder"]
        emit(f"WhyNot Cut: this is the clients folder ({cwd}). Client folders: {', '.join(names) or 'none yet'}. "
             f"Pass one to reel as --root \"<name>\", or say 'edit the new videos' (/whynot-cut:autopilot). "
             f"New client: /whynot-cut:new-client. Engine: {'ok' if env_ok else 'not installed (/whynot-cut:start)'}. "
             + clients_lists(cwd, names) + updates_line(home)
             + f"{prefs_line(st)} " + READ_ONLY_RULE)
    elif st.get("_file") and Path(st["_file"]).parent.parent == cwd.resolve():
        SCOPE[:] = [str(cwd), "set up here, no client folder open"]
        emit(f"WhyNot Cut is set up here ({prefs_line(st)}) but no client folder is open. "
             + updates_line(home)
             + "Run /whynot-cut:start to continue onboarding or /whynot-cut:new-client to add a client. "
             + READ_ONLY_RULE)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        pass
    sys.exit(0)
