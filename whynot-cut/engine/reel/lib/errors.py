"""Errors and exit codes (3.0 T2.2, engine IM-7 / MI-24).

Every `reel` command prints ONE JSON document on stdout; editors and agents read it. A common authoring mistake (a
decision without `start`, a JSON file saved with a BOM or a typo, a step run before the one it needs, silent audio, a
render that never returns) must give plain-English guidance, never a Python traceback:

    {"ok": false, "error": "<what went wrong>", "where": "<the file, or engine file:line>", "how": "<what to do>",
     "log": "<pipeline.log holding the traceback>"}

Exit codes (`exit_code`):
    0  success
    1  an error, or a failed result: `ok: false`, or a status in FAILED_STATUSES
    2  a refusal: the document has `blocked` or `refused` (approval gate, stale window, writer lease, missing --extras)
A `SystemExit("message")` keeps its 2.x meaning (the message on stderr, exit 1).

Stdlib only. Raise `Guidance(error, how)` where the engine knows what the editor should do next; the CLI's top-level
handler (`report`) turns it and any other exception into the document above.
"""
from __future__ import annotations

import json
import subprocess
import sys
import traceback
from pathlib import Path

FAILED_STATUSES = frozenset({"FAILED", "REFUSED", "BLOCKED", "BRIDGE_NOT_RUNNING"})
ENGINE_DIR = Path(__file__).resolve().parents[1]            # engine/reel
GENERIC_HOW = ("Run `reel next` to see the step this one needs. If the same error comes back, it is a WhyNot Cut "
               "problem: send the log file named in `log` to The Why Not AI")


class Guidance(Exception):
    """An error the engine can explain: `error` (what went wrong) and `how` (what to do next), optionally `where`."""

    def __init__(self, error: str, how: str, where: str | None = None):
        super().__init__(error)
        self.error, self.how, self.where = error, how, where


class FileFormatError(ValueError):
    """A text file that cannot be read: not valid JSON, or not UTF-8. Names the file and the line (1-based)."""

    def __init__(self, path, line: int, column: int, reason: str):
        self.path, self.line, self.column, self.reason = str(path), int(line), int(column), reason
        super().__init__(f"{self.path}: line {self.line} column {self.column}: {reason}")


def decode_position(data: bytes, err: UnicodeDecodeError) -> tuple[int, int]:
    """(line, column), 1-based, of the first byte that is not UTF-8."""
    head = data[:err.start]
    return head.count(b"\n") + 1, err.start - (head.rfind(b"\n") + 1) + 1


def exit_code(doc) -> int:
    """The exit code a printed result means: 2 refusal, 1 error or failed result, else 0."""
    if not isinstance(doc, dict):
        return 0
    if doc.get("blocked") or doc.get("refused"):
        return 2
    st = doc.get("status")
    if doc.get("ok") is False or (isinstance(st, str) and st in FAILED_STATUSES):
        return 1
    return 0


def _with_version_warnings(doc):
    """The warnings lib/stamps.py noted on the request's Context (a compiled artefact from another minor engine version
    or without a stamp, 3.0 T2.3) go out once, as `version_warnings` of the command's document."""
    try:
        from .common import current_context
        ctx = current_context()
        notes = list(getattr(ctx, "version_warnings", None) or [])
        if notes:
            ctx.version_warnings = []
    except Exception:  # noqa: BLE001 — printing the result must never fail on this
        return doc
    if notes and isinstance(doc, dict) and "version_warnings" not in doc:
        return dict(doc, version_warnings=notes)
    return doc


def emit(doc, check: bool = True):
    """Print the command's one JSON document; then exit with its code when it is a failure or a refusal. check=False
    for documents whose `status` is a project state, not a result (`reel status`, `reel next`)."""
    doc = _with_version_warnings(doc)
    print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))
    code = exit_code(doc) if check else 0
    if code:
        sys.stdout.flush()
        raise SystemExit(code)


# --------------------------------------------------------------------------- the top-level handler
def _engine_frame(exc: BaseException) -> str | None:
    """The deepest traceback frame inside the engine: "lib/plan.py:198 (validate_decisions)"."""
    hit = None
    for fr in traceback.extract_tb(exc.__traceback__):
        try:
            rel = Path(fr.filename).resolve().relative_to(ENGINE_DIR)
        except (ValueError, OSError):
            continue
        hit = f"{rel.as_posix()}:{fr.lineno} ({fr.name})"
    return hit


def _cmd_name(cmd) -> str:
    first = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else cmd
    return Path(str(first)).stem or str(first)


def describe(exc: BaseException) -> dict:
    """{"ok": False, "error", "where", "how"} for an exception, in plain English."""
    where = _engine_frame(exc) or "engine"
    if isinstance(exc, Guidance):
        doc = {"ok": False, "error": exc.error, "where": exc.where or where, "how": exc.how}
        if getattr(exc, "blocked", False):      # a "busy, try again" refusal (lib/file_lock.LockTimeout): exit 2
            doc["blocked"] = exc.error
        return doc
    if isinstance(exc, FileFormatError):
        return {"ok": False, "error": f"{Path(exc.path).name} cannot be read: {exc.reason} (line {exc.line}, "
                                      f"column {exc.column})",
                "where": f"{exc.path}:{exc.line}",
                "how": f"Open {exc.path}, fix line {exc.line} (a missing comma, quote or bracket is the usual cause; "
                       "save it as UTF-8 text), then run the command again"}
    if isinstance(exc, json.JSONDecodeError):          # JSON parsed outside read_json: the file is not known here
        return {"ok": False, "error": f"a JSON file is not valid: {exc.msg} (line {exc.lineno}, column {exc.colno})",
                "where": where, "how": "Fix the JSON file the command reads (see `where`), then run it again. "
                                       + GENERIC_HOW}
    if isinstance(exc, UnicodeDecodeError):
        return {"ok": False, "error": f"a text file is not UTF-8 ({exc.reason})", "where": where,
                "how": "Save the file as UTF-8 text (in Notepad: Save As, Encoding UTF-8), then run the command again"}
    if isinstance(exc, subprocess.TimeoutExpired):
        name = _cmd_name(exc.cmd)
        if name.lower().startswith(("ffmpeg", "ffprobe")):       # T2.15: the ffmpeg timeouts are 10 s + 3 x the media
            return {"ok": False, "error": f"{name} did not finish within {exc.timeout:g} s and was stopped",
                    "where": where,
                    "how": "Check that the media file plays and is fully copied or synced (a file on a network share or "
                           "cloud folder that is still downloading stalls ffmpeg); then run the command again. For a "
                           "very long file or a slow share, allow more time: set WHYNOT_FFMPEG_TIMEOUT_SCALE=3 (3x the "
                           "normal time) and run it again"}
        return {"ok": False, "error": f"{name} did not finish within {exc.timeout:g} s and was stopped", "where": where,
                "how": f"Check that {name} is not waiting on a dialog (close any open dialog in After Effects or "
                       "Premiere) and that the media plays; then run the command again"}
    if isinstance(exc, PermissionError):
        f = exc.filename or "a file"
        return {"ok": False, "error": f"no permission to use {f}", "where": str(exc.filename or where),
                "how": "Close the program that has it open (Premiere, After Effects, a media player, Excel), check the "
                       "folder is not read-only or still syncing, then run the command again"}
    if isinstance(exc, FileNotFoundError):
        f = exc.filename or str(exc)
        return {"ok": False, "error": f"not found: {f}", "where": str(exc.filename or where),
                "how": "Run the earlier step that writes it (`reel next` shows the next step), or check the path "
                       "(was the file moved or renamed?), then run the command again"}
    if isinstance(exc, KeyError):
        return {"ok": False, "error": f"a required field is missing: {exc.args[0]!r}" if exc.args else
                "a required field is missing", "where": where,
                "how": "An input file lacks a field this step needs. Re-run the step that writes it (`reel next`), or "
                       "add the field, then run the command again. " + GENERIC_HOW}
    if isinstance(exc, (ValueError, IndexError)):
        return {"ok": False, "error": str(exc) or type(exc).__name__, "where": where,
                "how": "Check the value or file the message names, fix it, then run the command again. " + GENERIC_HOW}
    if isinstance(exc, OSError):
        return {"ok": False, "error": f"{exc.strerror or exc}" + (f": {exc.filename}" if exc.filename else ""),
                "where": str(exc.filename or where),
                "how": "Check the disk has free space and the folder is reachable (a network or cloud drive may be "
                       "offline), then run the command again"}
    return {"ok": False, "error": f"unexpected {type(exc).__name__}: {exc}", "where": where, "how": GENERIC_HOW}


def log_traceback(log_file: Path, exc: BaseException, command: str) -> Path | None:
    """Append the traceback to log_file (never to stdout or stderr). None when the log cannot be written."""
    import datetime as _dt
    now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{now}] {command}: {type(exc).__name__}: {exc}\n{text}\n")
        return log_file
    except OSError:
        return None


def report(exc: BaseException, log_file: Path, command: str) -> dict:
    """The guidance document for an exception that reached the top level, its traceback in log_file. A log that
    cannot be written (a read-only folder, a cloud placeholder) falls back to the engine home's logs/pipeline.log, so
    the traceback is never lost (3.0 T2.16). WHYNOT_DEBUG=1 also prints it on stderr, for developers."""
    import os
    doc = describe(exc)
    written = log_traceback(log_file, exc, command)
    if written is None:
        try:
            from .common import engine_home
            fallback = engine_home() / "logs" / "pipeline.log"
        except Exception:  # noqa: BLE001 — the handler itself must never raise
            fallback = None
        if fallback is not None and Path(fallback) != Path(log_file):
            written = log_traceback(fallback, exc, command)
    doc["log"] = str(written) if written else None
    if os.environ.get("WHYNOT_DEBUG") == "1":
        sys.stderr.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return doc
