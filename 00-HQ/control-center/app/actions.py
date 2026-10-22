"""Dashboard buttons. Each one is safe for work in progress: nothing here stops, kills or restarts a running run.

- ask_status (helper):  queues a message asking it to say what it is doing (it answers in its feed; uses its tokens).
- compact (helper):     queues a message asking it to finish its step, write a PARTIAL report and end the run, so the
                        next run starts with a fresh context. A headless run cannot take `/compact`; this is the safe
                        equivalent. (Main sessions: the page copies `/compact` for you to paste; nothing is sent.)
- start_auto (helper):  only when its loop is NOT running: Start-Helper.cmd <h> --auto (the same as its AUTO shortcut).
- open_terminals:       opens the missing Control Center terminal tabs (never a second one).
"""
import os, subprocess, sys, threading, time
from pathlib import Path

import ownermsg

ACCOUNTS = Path(r"D:\ClaudeData\accounts")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
COOLDOWN_S = 30

ASK = ("Owner asks (Control Center button): in 2-3 short lines, say what you are doing now, what is left on this "
       "card, and whether anything blocks you. Then carry on with your work.")
COMPACT = ("Owner asks (Compact button): your context is getting large. Finish the step you are on, commit what is "
           "safe, write a PARTIAL report with what is done and what is next, then end this run so the next run "
           "starts with a fresh context. Do not drop or undo work in progress.")


def _alive(h):
    r = subprocess.run([sys.executable, "-X", "utf8", str(ACCOUNTS / "helper_loop.py"), h, "--alive"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=30)
    return r.returncode == 0


def _run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                       creationflags=NO_WINDOW)
    return r.returncode, (r.stdout + r.stderr).strip()


def res(ok, msg, msg_ar):
    return {"ok": ok, "msg": msg, "msg_ar": msg_ar}


class Actions:
    def __init__(self, cfg, alive=_alive, run=_run):
        self.cfg, self.alive, self.run = cfg, alive, run
        self.last = {}
        self.lock = threading.Lock()  # the server answers clicks in parallel threads

    def helper(self, acct):
        return any(a["id"] == acct and a["kind"] == "helper" for a in self.cfg["accounts"])

    def perform(self, name, acct):
        fn = {"ask_status": self.ask_status, "compact": self.compact, "start_auto": self.start_auto,
              "open_terminals": self.open_terminals}.get(name)
        if not fn:
            return res(False, f"Unknown action '{name}'.", f"أمر غير معروف «{name}».")
        if name != "open_terminals" and not self.helper(acct):
            return res(False, "This button is for Helper 1 or Helper 2 only.", "الزرار ده للمساعد 1 أو 2 بس.")
        key = (name, "*") if name == "open_terminals" else (name, acct)  # one terminal window for all cards
        with self.lock:  # claim before running: two quick clicks never both pass
            if time.time() - self.last.get(key, 0) < COOLDOWN_S:
                return res(False, "Already done a moment ago; wait 30 seconds before repeating it.",
                           "اتعمل من ثواني؛ استنى 30 ثانية قبل ما تكرّره.")
            self.last[key] = time.time()
        try:
            out = fn(acct)
        except Exception as e:  # noqa: BLE001  a click always gets a clear answer
            out = res(False, f"It failed: {type(e).__name__}: {e}", f"فشل: {type(e).__name__}: {e}")
        if not out["ok"]:
            self.last.pop(key, None)  # a refused or failed click may be retried at once
        return out

    def ask_status(self, acct):
        ownermsg.send(self.cfg["state_dir"], acct, ASK, source="dashboard")
        return res(True, "Asked. Its answer appears in its activity feed and terminal, usually within a minute "
                         "(at its next step; an idle helper wakes up for it).",
                   "اتبعت السؤال. الرد بيظهر في نشاطه وفي التيرمنال بتاعه غالباً خلال دقيقة (في خطوته الجاية؛ "
                   "ولو فاضي بيصحى عشانه).")

    def compact(self, acct):
        ownermsg.send(self.cfg["state_dir"], acct, COMPACT, source="dashboard")
        return res(True, "Asked to wrap up this step and start the next run fresh. Nothing is stopped; it finishes "
                         "its current step first.",
                   "اتطلب منه يخلّص الخطوة اللي فيها ويبدأ الجولة الجاية بذاكرة جديدة. مفيش حاجة بتتوقف؛ "
                   "بيخلّص اللي في إيده الأول.")

    def talk_open(self, acct):
        """A chat opened from this account's terminal (/chat, /continue) is running in its worktree."""
        p = os.path.join(self.cfg["state_dir"], "consoles", f"{acct}.talk")
        try:
            pid = int(open(p).read().split()[0])
        except (OSError, ValueError, IndexError):
            return False
        import console
        return console.pid_alive(pid)

    def start_auto(self, acct):
        if self.talk_open(acct):
            return res(False, "A chat is open on this seat in its terminal (/chat). Close it first: two Claude "
                              "sessions must not work in one worktree.",
                       "في شات مفتوح على الأكونت ده من التيرمنال (/chat). اقفله الأول: مينفعش جلستين Claude في نفس الفولدر.")
        if self.alive(acct):
            return res(False, "Its AUTO loop is already running; nothing to start.",
                       "اللوب بتاعه شغّال أصلاً؛ مفيش حاجة تتشغّل.")
        rc, out = self.run(["cmd", "/c", str(ACCOUNTS / "Start-Helper.cmd"), acct, "--auto"])
        if rc == 0:
            return res(True, "AUTO started. It picks its next card from the board.",
                       "اتشغّل AUTO. هيختار المهمة الجاية بتاعته من البورد.")
        return res(False, f"Start-Helper refused (exit {rc}): {out[-300:]}",
                   f"Start-Helper رفض (كود {rc}): {out[-300:]}")

    def open_terminals(self, acct):
        rc, out = self.run([sys.executable.replace("pythonw.exe", "python.exe"), "-X", "utf8",
                            str(Path(__file__).with_name("launch.py")), "--no-browser"])
        if rc == 0:
            return res(True, "Terminals: " + (out.splitlines()[-1] if out else "opened."),
                       "التيرمنالز اتفتحت (أو كانت مفتوحة أصلاً).")
        return res(False, f"Could not open the terminals (exit {rc}): {out[-300:]}",
                   f"ماقدرتش أفتح التيرمنالز (كود {rc}): {out[-300:]}")
