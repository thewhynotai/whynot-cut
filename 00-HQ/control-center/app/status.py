"""Execution states, decided only from evidence (loop lock, status.json, log writes, heartbeats, queue, errors).

A live process is never enough for WORKING: the run log must have been written recently.
"""
import datetime as dt

import common  # noqa: F401  (puts 00-HQ\tools on the path)
from agency_live import limit_reset  # noqa: E402

# code -> (plain label, colour class, rank: higher = more important when several sessions roll up into one account)
CODES = {
    "ERROR": ("Error", "red", 90),
    "DISCONNECTED": ("Disconnected", "red", 85),
    "STALLED": ("Stalled", "red", 80),
    "WAITING_INPUT": ("Waiting for you", "amber", 75),
    "WORKING": ("Working", "green", 70),
    "RUNNING_TESTS": ("Running tests", "green", 68),
    "WAITING_TOOL": ("Waiting on a long command", "amber", 60),
    "WAITING_QUEUE": ("Waiting in the test queue", "amber", 55),
    "WAITING_DEP": ("Waiting on another task", "amber", 50),
    "WAITING_LIMIT": ("Waiting: usage limit", "amber", 45),
    "QUIET": ("Quiet", "amber", 40),
    "STOPPED": ("Stopped", "gray", 20),
    "IDLE": ("Idle", "gray", 10),
    "CHECKING": ("Checking…", "gray", 0),
}


def make(code, reason="", label=None):
    lab, colour, _ = CODES[code]
    return {"code": code, "label": label or lab, "colour": colour, "reason": reason}


def mins(sec):
    m = int((sec or 0) // 60)
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


def helper_status(h, th):
    """h: loop_alive (None = not checked yet), auto_on, stop_file, state, reason, until, log_age_sec, tool_wait_sec,
    tests (None | ('running'|'waiting', minutes)), report_blocked, action."""
    if h.get("loop_alive") is None:
        return make("CHECKING")
    state, reason, until = h.get("state") or "?", h.get("reason") or "", h.get("until") or ""
    if not h["loop_alive"]:
        if state == "stalled":
            return make("ERROR", "AUTO mode switched itself off after 3 quick failures in a row (see auto.log). "
                                 "Fix the cause, then start AUTO again.")
        if h.get("stop_file") or not h.get("auto_on"):
            return make("STOPPED", "AUTO mode is off (stopped by its STOP shortcut or the console).")
        return make("DISCONNECTED", "AUTO mode is on but its loop is not running. The keepalive task restarts it "
                                    "within 30 min, or start it from the console.")
    if state == "running":
        tests = h.get("tests")
        if tests and tests[0] == "running":
            return make("RUNNING_TESTS", f"Its test suite has been running for {tests[1]} min in the heavy queue.")
        if tests and tests[0] == "waiting":
            return make("WAITING_QUEUE", f"Its test suite has waited {tests[1]} min for a free heavy-queue slot.")
        wait = h.get("tool_wait_sec") or 0
        if wait >= th["tool_wait_warn_minutes"] * 60:
            return make("WAITING_TOOL", f"'{h.get('action') or 'a command'}' has been running for {mins(wait)}.")
        age = h.get("log_age_sec")
        if age is None or age <= th["working_seconds"]:
            return make("WORKING", "Its run log was written in the last few minutes.")
        if age >= th["stalled_minutes"] * 60:
            return make("STALLED", f"The process is alive but has written nothing for {mins(age)}. The loop kills a "
                                   "run silent for 5 h 10 min; check the run log before acting.")
        if age >= th["quiet_warn_minutes"] * 60:
            return make("QUIET", f"Nothing written for {mins(age)}.")
        return make("WORKING", f"Last output {mins(age)} ago.")
    if state == "waiting":
        at = until[-5:] if until else "?"
        if "limit" in reason:
            return make("WAITING_LIMIT", f"This account hit its usage limit; the loop resumes by itself at {at}.",
                        f"Waiting: usage limit until {at}")
        return make("ERROR", f"The last run failed quickly ({reason}); the loop retries at {at}.")
    if state == "yielding":
        return make("WAITING_DEP", reason or "Letting Gate 4 critical-path jobs use the test queue first.")
    if state == "idle":
        if h.get("report_blocked"):
            return make("WAITING_INPUT", "Its newest report is BLOCKED: it needs a decision or an answer on the card.")
        return make("IDLE", "No card is left for it on BOARD.md; it wakes when the board or a card changes.")
    if state == "stopped":
        return make("STOPPED", reason)
    return make("ERROR", f"Unknown loop state '{state}'. {reason}".strip())


def session_status(s, th, now):
    """s: error, error_at, last_activity (datetimes), transcript_age_sec, awaiting_person."""
    err, err_at, last = s.get("error"), s.get("error_at"), s.get("last_activity")
    fresh_error = bool(err and err_at and (last is None or err_at >= last - dt.timedelta(seconds=5)))
    if fresh_error and "limit" in err.lower():
        reset = limit_reset(err, err_at)
        if reset and now < reset:
            return make("WAITING_LIMIT", "The main account hit its usage limit; the watchdog resumes it after the reset.",
                        f"Waiting: usage limit until {reset:%H:%M}")
        return make("STOPPED", "Stopped by a usage limit that has now reset; the watchdog resumes it.")
    if fresh_error:
        return make("ERROR", str(err)[:200])
    if s.get("awaiting_person"):
        return make("WAITING_INPUT", "It stopped to ask you something in the desktop app.")
    age = s.get("transcript_age_sec")
    if age is not None and age <= th["working_seconds"]:
        return make("WORKING", "Its transcript was written in the last few minutes.")
    quiet = (now - last).total_seconds() if last else None
    if quiet is not None and quiet > 90 * 60:
        return make("IDLE", f"No activity for {mins(quiet)}.")
    return make("QUIET", f"No activity for {mins(quiet)}." if quiet is not None else "")


def rollup(codes):
    codes = [c for c in codes if c in CODES]
    return max(codes, key=lambda c: CODES[c][2]) if codes else "IDLE"


def context_view(tokens, window, at, warn, danger):
    """tokens in use + the learned window ({'size','source','at'} or None) -> what the card shows."""
    if tokens is None:
        return {"tokens": None, "window": (window or {}).get("size"), "percent": None, "remaining": None,
                "level": "none", "at": at, "window_source": (window or {}).get("source")}
    size = (window or {}).get("size")
    if not size:
        return {"tokens": tokens, "window": None, "percent": None, "remaining": None, "level": "unknown", "at": at,
                "window_source": None}
    pct = round(tokens * 100 / size)
    level = "danger" if pct >= danger else "warn" if pct >= warn else "ok"
    return {"tokens": tokens, "window": size, "percent": pct, "remaining": max(size - tokens, 0), "level": level,
            "at": at, "window_source": window.get("source")}
