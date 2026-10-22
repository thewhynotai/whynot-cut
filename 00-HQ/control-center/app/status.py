"""Execution states, decided only from evidence (loop lock, status.json, log writes, heartbeats, queue, errors).

A live process is never enough for WORKING: the run log must have been written recently.
"""
import datetime as dt

import common  # noqa: F401  (puts 00-HQ\tools on the path)
from agency_live import limit_reset  # noqa: E402

# code -> (English label, Arabic label, colour class, rank: higher = more important when sessions roll up)
CODES = {
    "ERROR": ("Error", "خطأ", "red", 90),
    "DISCONNECTED": ("Disconnected", "مفصول", "red", 85),
    "STALLED": ("Stalled", "واقف من غير تقدّم", "red", 80),
    "WAITING_INPUT": ("Waiting for you", "مستنيك", "amber", 75),
    "WORKING": ("Working", "شغّال", "green", 70),
    "RUNNING_TESTS": ("Running tests", "بيشغّل الاختبارات", "green", 68),
    "WAITING_TOOL": ("Waiting on a long command", "مستني أمر طويل", "amber", 60),
    "WAITING_QUEUE": ("Waiting in the test queue", "في طابور الاختبارات", "amber", 55),
    "WAITING_DEP": ("Waiting on another task", "مستني مهمة تانية", "amber", 50),
    "WAITING_LIMIT": ("Waiting: usage limit", "مستني الليمت يرجع", "amber", 45),
    "QUIET": ("Quiet", "هادي", "amber", 40),
    "STOPPED": ("Stopped", "متوقّف", "gray", 20),
    "IDLE": ("Idle", "فاضي", "gray", 10),
    "CHECKING": ("Checking…", "بيتأكد…", "gray", 0),
}


def make(code, reason="", reason_ar="", label=None, label_ar=None):
    """One status, in English and Arabic (the screen shows the language Yunus picks)."""
    en, ar, colour, _ = CODES[code]
    return {"code": code, "label": label or en, "label_ar": label_ar or ar, "colour": colour, "reason": reason,
            "reason_ar": reason_ar}


def mins(sec):
    m = int((sec or 0) // 60)
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


def mins_ar(sec):
    m = int((sec or 0) // 60)
    return f"{m} دقيقة" if m < 60 else f"{m // 60} ساعة و{m % 60} دقيقة"


def helper_status(h, th):
    """h: loop_alive (None = not checked yet), auto_on, stop_file, state, reason, until, log_age_sec, tool_wait_sec,
    tests (None | ('running'|'waiting', minutes)), report_blocked, action."""
    if h.get("loop_alive") is None:
        return make("CHECKING")
    state, reason, until = h.get("state") or "?", h.get("reason") or "", h.get("until") or ""
    if not h["loop_alive"]:
        if state == "stalled":
            return make("ERROR", "AUTO mode switched itself off after 3 quick failures in a row (see auto.log). "
                                 "Fix the cause, then start AUTO again.",
                        "وضع AUTO قفل نفسه بعد 3 محاولات فشلت ورا بعض (شوف auto.log). صلّح السبب وبعدين شغّل AUTO تاني.")
        if h.get("stop_file") or not h.get("auto_on"):
            return make("STOPPED", "AUTO mode is off (stopped by its STOP shortcut or the console).",
                        "وضع AUTO مقفول (اتوقف من اختصار STOP أو من التيرمنال).")
        return make("DISCONNECTED", "AUTO mode is on but its loop is not running. The keepalive task restarts it "
                                    "within 30 min, or start it from the console.",
                    "وضع AUTO مفتوح بس اللوب مش شغّال. الـ keepalive بيرجّعه خلال 30 دقيقة، أو شغّله من الزرار أو التيرمنال.")
    if state == "running":
        tests = h.get("tests")
        if tests and tests[0] == "running":
            return make("RUNNING_TESTS", f"Its test suite has been running for {tests[1]} min in the heavy queue.",
                        f"الاختبارات بتاعته شغّالة بقالها {tests[1]} دقيقة في طابور الاختبارات.")
        if tests and tests[0] == "waiting":
            return make("WAITING_QUEUE", f"Its test suite has waited {tests[1]} min for a free heavy-queue slot.",
                        f"اختباراته مستنية مكان فاضي في الطابور بقالها {tests[1]} دقيقة.")
        wait = h.get("tool_wait_sec") or 0
        if wait >= th["tool_wait_warn_minutes"] * 60:
            act = h.get("action") or "a command"
            return make("WAITING_TOOL", f"'{act}' has been running for {mins(wait)}.",
                        f"الأمر «{act}» شغّال بقاله {mins_ar(wait)}.")
        age = h.get("log_age_sec")
        if age is None:
            return make("QUIET", "The loop says a run is going, but its run log has no output yet (or cannot be read).",
                        "اللوب بيقول إن في شغل ماشي، بس سجل الشغل لسه فاضي (أو مش مقروء).")
        if age <= th["working_seconds"]:
            return make("WORKING", "Its run log was written in the last few minutes.",
                        "سجل شغله اتكتب فيه في آخر كام دقيقة.")
        if age >= th["stalled_minutes"] * 60:
            return make("STALLED", f"The process is alive but has written nothing for {mins(age)}. The loop kills a "
                                   "run silent for 5 h 10 min; check the run log before acting.",
                        f"البرنامج شغّال بس ما كتبش حاجة بقاله {mins_ar(age)}. اللوب بيقفل أي شغل ساكت 5 ساعات و10 دقايق؛ "
                        "بص على السجل قبل ما تعمل حاجة.")
        if age >= th["quiet_warn_minutes"] * 60:
            return make("QUIET", f"Nothing written for {mins(age)}.", f"ما كتبش حاجة بقاله {mins_ar(age)}.")
        return make("WORKING", f"Last output {mins(age)} ago.", f"آخر حاجة كتبها من {mins_ar(age)}.")
    if state == "waiting":
        at = until[-5:] if until else "?"
        if "limit" in reason:
            return make("WAITING_LIMIT", f"This account hit its usage limit; the loop resumes by itself at {at}.",
                        f"الأكونت ده خلّص الليمت؛ هيكمّل لوحده الساعة {at}.",
                        f"Waiting: usage limit until {at}", f"مستني الليمت لحد {at}")
        return make("ERROR", f"The last run failed quickly ({reason}); the loop retries at {at}.",
                    f"آخر محاولة فشلت بسرعة ({reason})؛ هيحاول تاني الساعة {at}.")
    if state == "yielding":
        return make("WAITING_DEP", reason or "Letting Gate 4 critical-path jobs use the test queue first.",
                    "سايب اختبارات Gate 4 المهمة تشتغل الأول في الطابور، وبعدها يكمّل لوحده.")
    if state == "idle":
        if h.get("report_blocked"):
            return make("WAITING_INPUT", "Its newest report is BLOCKED: it needs a decision or an answer on the card.",
                        "آخر تقرير ليه BLOCKED: محتاج قرار أو إجابة في كارت المهمة.")
        return make("IDLE", "No card is left for it on BOARD.md; it wakes when the board or a card changes.",
                    "مفيش مهمة متبقية ليه على البورد؛ بيصحى لوحده لما البورد أو كارت يتغيّر، أو لما تبعتله رسالة.")
    if state == "stopped":
        return make("STOPPED", reason, "اللوب اتوقف." if reason else "")
    return make("ERROR", f"Unknown loop state '{state}'. {reason}".strip(), f"حالة لوب غير معروفة «{state}».")


def session_status(s, th, now):
    """s: error, error_at, last_activity (datetimes), transcript_age_sec, awaiting_person."""
    err, err_at, last = s.get("error"), s.get("error_at"), s.get("last_activity")
    fresh_error = bool(err and err_at and (last is None or err_at >= last - dt.timedelta(seconds=5)))
    if fresh_error and "limit" in err.lower():
        reset = limit_reset(err, err_at)
        if reset and now < reset:
            return make("WAITING_LIMIT", "The main account hit its usage limit; the watchdog resumes it after the reset.",
                        "الأكونت الرئيسي خلّص الليمت؛ الـ watchdog بيرجّعه بعد ما الليمت يرجع.",
                        f"Waiting: usage limit until {reset:%H:%M}", f"مستني الليمت لحد {reset:%H:%M}")
        return make("STOPPED", "Stopped by a usage limit that has now reset; the watchdog resumes it.",
                    "وقف بسبب الليمت، والليمت رجع خلاص؛ الـ watchdog هيكمّله.")
    if fresh_error:
        return make("ERROR", str(err)[:200], "حصل خطأ في الجلسة: " + str(err)[:160])
    if s.get("awaiting_person"):
        return make("WAITING_INPUT", "It stopped to ask you something in the desktop app.",
                    "وقف عشان يسألك حاجة في برنامج Claude.")
    age = s.get("transcript_age_sec")
    if age is not None and age <= th["working_seconds"]:
        return make("WORKING", "Its transcript was written in the last few minutes.",
                    "بيكتب في المحادثة في آخر كام دقيقة.")
    quiet = (now - last).total_seconds() if last else None
    if quiet is not None and quiet > 90 * 60:
        return make("IDLE", f"No activity for {mins(quiet)}.", f"مفيش نشاط بقاله {mins_ar(quiet)}.")
    return make("QUIET", f"No activity for {mins(quiet)}." if quiet is not None else "",
                f"مفيش نشاط بقاله {mins_ar(quiet)}." if quiet is not None else "")


def rollup(codes):
    codes = [c for c in codes if c in CODES]
    return max(codes, key=lambda c: CODES[c][3]) if codes else "IDLE"


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
