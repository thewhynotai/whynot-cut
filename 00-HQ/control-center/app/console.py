"""WhyNot Control Center account terminal (one per Windows Terminal tab).

    python -X utf8 console.py main    # MAIN: a real interactive Claude Code on info@, with the Control Center status line
    python -X utf8 console.py h1|h2   # HELPER: live feed of its AUTO run + a message box (+ /chat when AUTO is off)

Helper screen: a fixed header (account, status, model, task, action, context) that updates in place; below it only NEW
events of the run scroll by (nothing is repeated); the bottom line is where you type. Plain text = a message to the
helper (it reaches the running session at its next step through the profile hook). Type /help for commands.
No model is called by this screen; only what you send or a chat you open uses the account.
"""
import collections, ctypes, datetime as dt, glob, json, os, re, shutil, subprocess, sys, textwrap, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, ownermsg, runlog  # noqa: E402

ACCOUNTS_DIR = r"D:\ClaudeData\accounts"
E = "\x1b["
C = {"green": "32", "amber": "33", "red": "31", "gray": "90", "blue": "94", "bold": "1", "white": "97"}
HEADER = 6  # header rows (5 lines + separator)
HELP = [
    "Type a message and press Enter: it is delivered to the helper's running session at its next step.",
    "/task      what it is working on, with every verified step",
    "/status    status, why, loop state, sign-in, files",
    "/msgs      your recent messages and when each was delivered",
    "/chat      open a full chat on this seat (only when AUTO is off)",
    "/continue  reopen the newest conversation in its worktree (usually its last AUTO run; AUTO must be off)",
    "/start     turn AUTO mode on        /stop  turn AUTO off (asks first: it ends the current run)",
    "/log       where the full run log is            /clear  clear this feed            /quit  close this tab",
]


def paint(text, colour):
    return f"{E}{C[colour]}m{text}{E}0m" if colour in C else text


def pid_alive(pid):
    if pid <= 0:
        return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259
    finally:
        k32.CloseHandle(h)


def take_lock(cfg, acct_id):
    """One terminal per account. -> True if this one may run."""
    p = common.state_path(cfg, "consoles", f"{acct_id}.lock")
    for _ in range(2):
        try:  # O_EXCL: two tabs started at the same moment cannot both win
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time():.0f}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                pid = int(p.read_text().split()[0])
            except (OSError, ValueError, IndexError):
                pid = 0
            if pid == os.getpid():
                return True
            if pid and pid_alive(pid):
                return False
            try:
                os.remove(p)  # stale: its terminal is gone
            except OSError:
                pass
    return False


def release_lock(cfg, acct_id):
    p = common.state_path(cfg, "consoles", f"{acct_id}.lock")
    try:
        if int(p.read_text().split()[0]) == os.getpid():
            p.unlink()
    except (OSError, ValueError, IndexError):
        pass


def claude_exe():
    found = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code", "**", "claude.exe"), recursive=True)
    return max(found, key=os.path.getmtime) if found else None


def started_inside_claude():
    return bool(os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_SESSION_ID"))


def read_snapshot(cfg):
    p = common.state_path(cfg, "snapshot.json")
    try:
        snap = json.loads(p.read_text(encoding="utf-8"))
        return snap, common.snapshot_age_min(snap)
    except (OSError, ValueError):
        return None, None


def kfmt(n):
    if n is None:
        return "?"
    return f"{n / 1e6:.1f}M".replace(".0M", "M") if n >= 1e6 else f"{round(n / 1e3)}K"


def ctx_text(c):
    if not c or c.get("level") == "none":
        last = (c or {}).get("last_run")
        return "Context: not measured yet" + (f" (last run ended at {kfmt(last['tokens'])})" if last else "")
    if c.get("level") == "unknown":
        return f"Context: {kfmt(c['tokens'])} / window not reported yet"
    filled = round(c["percent"] / 10)
    return f"Context: {kfmt(c['tokens'])} / {kfmt(c['window'])} ({c['percent']}%) [{'█' * filled}{'░' * (10 - filled)}]"


def local_hhmm(iso):
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (d.astimezone() if d.tzinfo else d).strftime("%H:%M")
    except ValueError:
        return "--:--"


def others_line(snap, me):
    out = []
    for a in (snap or {}).get("accounts", []):
        if a["id"] != me:
            out.append(paint(f"{a['name']}: {a['status']['label']}" + (f" {a['task_id']}" if a.get("task_id") else ""),
                             a["status"].get("colour", "gray")))
    return "   ".join(out)


# ---------------------------------------------------------------------------------------------- MAIN account
def run_main(cfg, acct):
    exe = claude_exe()
    settings = common.state_path(cfg, "statusline-main.json")
    py = sys.executable.replace("pythonw.exe", "python.exe")
    settings.write_text(json.dumps({"statusLine": {"type": "command", "padding": 0, "command":
                        f'"{py}" -X utf8 "{os.path.abspath(__file__).replace("console.py", "statusline.py")}" main'}}),
                        encoding="utf-8")
    cont = False
    while True:
        os.system("cls")
        snap, age = read_snapshot(cfg)
        print(paint(f" MAIN ACCOUNT · {acct['email']} · {acct['role']}", "bold"))
        mine = next((a for a in (snap or {}).get("accounts", []) if a["id"] == "main"), None)
        if mine:
            print(f" Desktop app: {mine['status']['label']} · {len(mine.get('sessions') or [])} sessions in the last day · "
                  f"{mine['connection']['detail']}")
            print(" Others: " + others_line(snap, "main"))
        else:
            print(paint(" (monitor not running: start it from the WhyNot - Control Center shortcut)", "gray"))
        print()
        print(" This is a real Claude Code chat on the main account, in the Editing Plugin folder. It is separate from")
        print(" the desktop app's sessions (they keep coordinating as before). The bottom status line shows this chat's")
        print(" model and context and the helpers' state. /exit ends the chat; this tab stays open.")
        print()
        if not exe:
            print(paint(" claude.exe not found under %APPDATA%\\Claude\\claude-code. Is the Claude desktop app installed?", "red"))
            input(" Press Enter to retry… ")
            exe = claude_exe()
            continue
        cmd = [exe, "--settings", str(settings)] + (["--continue"] if cont else [])
        subprocess.call(cmd, cwd=acct["work_dir"])
        print()
        ans = input(paint(" Chat ended. Enter = new chat · c = continue the last chat · q = close this tab: ", "amber")).strip().lower()
        if ans == "q":
            return
        cont = ans == "c"


# ---------------------------------------------------------------------------------------------- HELPER account
class HelperConsole:
    def __init__(self, cfg, acct):
        self.cfg, self.acct, self.h = cfg, acct, acct["id"]
        self.auto = os.path.join(acct["profile"], "auto")
        self.state = cfg["state_dir"]
        self.feed, self.log_path = None, None
        self.buf = ""
        self.history = collections.deque(maxlen=400)  # (text, colour) lines already shown, for redraws
        self.size = None
        self.header_cache = None
        self.delivered = {m["id"] for m in ownermsg.recent(self.state, self.h, 200) if m.get("delivered_at")}
        self.confirm_stop = False
        self.snap, self.snap_age, self.snap_mtime = None, None, 0

    # -------------------------------------------------------------- screen
    def rows(self):
        return shutil.get_terminal_size((120, 32))

    def w(self, s):
        sys.stdout.write(s)

    def setup(self):
        size = self.rows()
        self.size = size
        self.w(f"{E}?1049h{E}2J{E}H")  # own screen buffer, so the tab's earlier text is not mixed in
        bottom = max(HEADER + 2, size.lines - 2)
        self.w(f"{E}{HEADER + 1};{bottom}r")
        self.header_cache = None
        self.draw_header(force=True)
        for text, colour in list(self.history)[-(bottom - HEADER):]:
            self._emit(text, colour)
        self.draw_footer()
        sys.stdout.flush()

    def teardown(self):
        self.w(f"{E}r{E}?1049l")
        sys.stdout.flush()

    def _emit(self, text, colour):
        bottom = max(HEADER + 2, self.size.lines - 2)
        self.w(f"{E}{bottom};1H\n{paint(text, colour)}{E}K")

    def add(self, text, colour="", stamp=None):
        width = max(20, self.size.columns - 1)
        prefix = f"{stamp or dt.datetime.now().strftime('%H:%M')} "
        lines = textwrap.wrap(text, width - len(prefix), break_long_words=True, replace_whitespace=True) or [""]
        for i, part in enumerate(lines):
            line = (prefix if i == 0 else " " * len(prefix)) + part
            self.history.append((line, colour))
            self._emit(line, colour)
        self.draw_footer()
        sys.stdout.flush()

    def draw_footer(self):
        size = self.size
        hint = " type a message + Enter · /help · /chat · /stop · /quit "
        self.w(f"{E}{size.lines - 1};1H{paint(('─' * 2 + hint).ljust(size.columns - 1, '─')[: size.columns - 1], 'gray')}")
        room = size.columns - 8
        shown = self.buf[-room:] if len(self.buf) > room else self.buf
        self.w(f"{E}{size.lines};1H{E}2K{paint('you › ', 'blue')}{shown}")
        sys.stdout.flush()

    def header(self):
        a = self.mine() or {}
        st = a.get("status") or {"label": "monitor offline", "colour": "gray", "reason": ""}
        sess = a.get("session") or {}
        task = a.get("task")
        cols = self.size.columns - 1
        fresh = "" if self.snap_age is None or self.snap_age < self.cfg["refresh"]["stale_minutes"] else \
            f"  (monitor data {int(self.snap_age)} min old)"
        conn = a.get("connection") or {}
        l1 = (paint(f" {self.acct['name'].upper()} · {self.acct['email']} · {self.acct['role']}", "bold"),
              paint(f"● {st['label']}", st.get("colour", "gray")) + paint(fresh, "amber"))
        model = f" Model {a.get('model_name', '?')}" + (f" · effort {a['effort']}" if a.get("effort") else "")
        run = f" · session {str(sess.get('id') or '-')[:8]} · run {sess.get('run') or '-'}"
        since = f" since {sess['started'][11:16]}" if sess.get("started") else ""
        loop = f" · AUTO {'on' if conn.get('auto_on') else 'off'}, loop {conn.get('loop', '?')}"
        l2 = model + run + since + loop
        if task:
            l3 = f" Task {task['id']} — {task['title']} · {task['display']} · {task['progress']['done']}/{task['progress']['total']} steps"
        else:
            l3 = " Task: " + ("none identified for the current run" if st.get("label") else "-")
        why = st.get("reason") or ""
        l4 = " Now: " + (a.get("action") or why or "-")
        usage = a.get("usage") or "plan usage not reported yet"
        mb = a.get("mailbox") or {}
        l5 = f" {ctx_text(a.get('context'))} · {usage} · messages waiting {mb.get('pending', 0)}"
        return [l1, l2, l3, l4, l5]

    def draw_header(self, force=False):
        lines = self.header()
        if not force and lines == self.header_cache:
            return
        self.header_cache = lines
        cols = self.size.columns - 1
        self.w(f"{E}s")
        for i, line in enumerate(lines):
            if isinstance(line, tuple):  # (left, right) with colour codes: pad on plain text length
                left, right = line
                plain = len(re.sub(r"\x1b\[[0-9;]*m", "", left)) + len(re.sub(r"\x1b\[[0-9;]*m", "", right))
                text = left + " " * max(1, cols - plain) + right
            else:
                text = line[:cols]
            self.w(f"{E}{i + 1};1H{E}2K{text}")
        self.w(f"{E}{HEADER};1H{E}2K{paint('─' * cols, 'gray')}")
        self.w(f"{E}u")
        self.draw_footer()

    # -------------------------------------------------------------- data
    def mine(self):
        return next((a for a in (self.snap or {}).get("accounts", []) if a["id"] == self.h), None)

    def refresh_snapshot(self):
        p = common.state_path(self.cfg, "snapshot.json")
        try:
            m = os.path.getmtime(p)
        except OSError:
            self.snap, self.snap_age = None, None
            return
        if m != self.snap_mtime:
            self.snap, _ = read_snapshot(self.cfg)
            self.snap_mtime = m
        self.snap_age = common.snapshot_age_min(self.snap)

    def status_json(self):
        try:
            with open(os.path.join(self.auto, "status.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def follow_run(self, first=False):
        log = runlog.run_log(self.status_json(), self.auto)
        if log and log != self.log_path:
            self.log_path, self.feed = log, runlog.RunFeed(log)
            events = self.feed.poll()
            if first:
                self.add(f"Attached to run log {os.path.basename(log)} — showing its last steps:", "gray")
                events = events[-15:]
            else:
                self.add(f"New run started ({os.path.basename(log)}).", "blue")
            self.show(events)
        elif self.feed:
            self.show(self.feed.poll())

    def show(self, events):
        for e in events:
            colour = {"say": "white", "tool": "gray", "error": "red", "denied": "red", "start": "blue",
                      "end": "green"}.get(e["kind"], "")
            text = ("  · " + e["text"]) if e["kind"] == "tool" else e["text"]
            if e["kind"] == "end" and self.feed and self.feed.result and not self.feed.result["ok"]:
                colour = "red"
            self.add(text, colour, local_hhmm(e["at"]) if e.get("at") else None)

    def check_delivery(self):
        for m in ownermsg.recent(self.state, self.h, 30):
            if m.get("delivered_at") and m["id"] not in self.delivered:
                self.delivered.add(m["id"])
                self.add(f"✓ Your message was delivered to session {str(m.get('delivered_to'))[:8]} at "
                         f"{m['delivered_at'][11:16]}: “{m['text'][:80]}”", "green")

    # -------------------------------------------------------------- input
    def key(self):
        import msvcrt
        while msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()  # arrows/function keys: ignored
            elif ch == "\r":
                text, self.buf = self.buf.strip(), ""
                self.draw_footer()
                if text:
                    if self.submit(text) == "quit":
                        return "quit"
            elif ch == "\x08":
                self.buf = self.buf[:-1]
            elif ch == "\x1b":
                self.buf = ""
            elif ch == "\x03":
                return "quit"
            elif ch.isprintable():
                self.buf += ch
            self.draw_footer()
        return None

    def loop_alive(self):
        a = self.mine()
        if a and self.snap_age is not None and self.snap_age < 3:
            return a["connection"].get("loop") == "running"
        r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(ACCOUNTS_DIR, "helper_loop.py"), self.h, "--alive"],
                           capture_output=True)
        return r.returncode == 0

    def run_cmd(self, args, interactive=False):
        script = os.path.join(ACCOUNTS_DIR, args[0])
        if interactive:
            self.teardown()
            os.system("cls")
            talk = common.state_path(self.cfg, "consoles", f"{self.h}.talk")
            proc = subprocess.Popen(["cmd", "/c", script] + args[1:])
            talk.write_text(str(proc.pid))  # the dashboard's Start AUTO refuses while this chat is open
            try:
                proc.wait()
            finally:
                try:
                    talk.unlink()
                except OSError:
                    pass
            input("\n(chat closed) Press Enter to return to the helper terminal… ")
            self.setup()
            return
        r = subprocess.run(["cmd", "/c", script] + args[1:], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        for line in (r.stdout + r.stderr).splitlines():
            if line.strip():
                self.add(line.strip(), "gray")

    def submit(self, text):
        if not text.startswith("/"):
            self.confirm_stop = False
            mid = ownermsg.send(self.state, self.h, text)
            alive = self.loop_alive()
            st = self.status_json().get("state")
            self.add(f"you → {self.acct['name']}: {text}", "blue")
            if not alive:
                self.add("Queued. AUTO is off, so nobody reads it yet: /start turns AUTO on, or /chat opens a chat.", "amber")
            elif st == "running":
                self.add("Queued; it reaches the running session at its next step (usually within a minute).", "gray")
            elif st == "idle":
                self.add("Queued; the idle loop wakes for it and starts a run (within ~2 min).", "gray")
            else:
                self.add(f"Queued; the loop is '{st}', so it is read when the next run starts.", "amber")
            return None
        cmd, _, rest = text.partition(" ")
        cmd = cmd.lower()
        if cmd != "/stop":
            self.confirm_stop = False
        if cmd in ("/quit", "/exit"):
            return "quit"
        if cmd == "/help":
            for line in HELP:
                self.add(line, "gray")
        elif cmd == "/clear":
            self.history.clear()
            self.setup()
        elif cmd == "/status":
            a = self.mine() or {}
            st = a.get("status") or {}
            self.add(f"Status: {st.get('label', '?')} — {st.get('reason', '')}", st.get("colour", ""))
            c = a.get("connection") or {}
            self.add(f"Sign-in: {c.get('detail', '?')} · AUTO {'on' if c.get('auto_on') else 'off'} · loop {c.get('loop', '?')}")
            self.add(f"Run log: {self.log_path or '-'} · profile {self.acct['profile']} · worktree {self.acct['work_dir']}", "gray")
        elif cmd == "/task":
            a = self.mine() or {}
            tid = a.get("task_id")
            t = next((x for x in (self.snap or {}).get("tasks", []) if x["id"] == tid), None)
            if not t:
                self.add("No task identified for the current run.", "amber")
            else:
                self.add(f"{t['id']} — {t['title']} · {t['display']}", "bold")
                if t["summary"]:
                    self.add(t["summary"])
                for s in t["steps"]:
                    mark = {"done": "✓", "current": "●", "failed": "✕", "skipped": "–"}.get(s["state"], "○")
                    self.add(f"  {mark} {s['label']}: {s['evidence']}", "green" if s["state"] == "done" else "gray")
                if t["blocker"]:
                    self.add(f"Blocker: {t['blocker']}", "red")
                if t["depends"]:
                    self.add(f"Depends on: {t['depends']}", "gray")
        elif cmd == "/msgs":
            msgs = ownermsg.recent(self.state, self.h, 8)
            if not msgs:
                self.add("No messages sent from this terminal yet.", "gray")
            for m in reversed(msgs):
                state = f"delivered {m['delivered_at'][11:16]} to {str(m.get('delivered_to'))[:8]}" if m.get("delivered_at") else "waiting"
                self.add(f"{m['at'][11:16]} [{state}] {m['text']}", "green" if m.get("delivered_at") else "amber")
        elif cmd == "/log":
            self.add(f"Full run log: {self.log_path or '-'}", "gray")
            self.add(f"Loop log: {os.path.join(self.auto, 'auto.log')} · raw steps: python -X utf8 "
                     f"{ACCOUNTS_DIR}\\helper_peek.py {self.h}", "gray")
        elif cmd in ("/chat", "/continue"):
            if os.path.exists(os.path.join(self.auto, "AUTO-ON")) and not self.loop_alive():
                self.add("AUTO is switched on but its loop is not running: the keepalive would start it during your "
                         "chat (two sessions in one worktree). Type /stop first, then /chat.", "amber")
            elif self.loop_alive():
                self.add("AUTO is running in this worktree, and two Claude sessions must not work in one worktree. "
                         "Your messages still reach the running session. For a full chat: /stop first.", "amber")
            else:
                self.run_cmd(["Start-Helper.cmd", self.h, "--talk"] + (["--continue"] if cmd == "/continue" else []),
                             interactive=True)
        elif cmd == "/start":
            if self.loop_alive():
                self.add("AUTO is already running.", "gray")
            else:
                self.run_cmd(["Start-Helper.cmd", self.h, "--auto"])
        elif cmd == "/stop":
            if rest.strip().lower() == "yes" or self.confirm_stop:
                self.confirm_stop = False
                self.run_cmd(["Stop-Helper-Auto.cmd", self.h])
            else:
                self.confirm_stop = True
                self.add("Stopping AUTO ends the CURRENT run within about a minute (committed work is kept, the rest of "
                         "this run is lost) and the keepalive will not restart it. Type /stop again to confirm.", "amber")
        else:
            self.add(f"Unknown command {cmd}. /help lists them.", "amber")
        return None

    def run(self):
        os.system("")  # VT codes on
        os.system(f"title {self.acct['name']} · {self.acct['email']}")
        self.refresh_snapshot()
        self.size = self.rows()
        self.setup()
        self.add("Helper terminal ready. Type a message, or /help. This screen only reads files; it calls no model.", "gray")
        self.follow_run(first=True)
        last_poll = 0.0
        try:
            while True:
                if self.key() == "quit":
                    return
                now = time.time()
                if now - last_poll >= 1.0:
                    last_poll = now
                    if self.rows() != self.size:
                        self.setup()
                    self.refresh_snapshot()
                    self.follow_run()
                    self.check_delivery()
                    self.draw_header()
                time.sleep(0.05)
        finally:
            self.teardown()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cfg = common.load_config()
    acct = common.account(cfg, sys.argv[1])
    if started_inside_claude():
        print("Open the Control Center from its desktop shortcut, not from inside a Claude session "
              "(the session's own login would leak into this terminal).")
        return 6
    if not take_lock(cfg, acct["id"]):
        print(f"The {acct['name']} terminal is already open in another tab. This tab closes in 8 s.")
        time.sleep(8)
        return 0
    try:
        if acct["kind"] == "desktop":
            run_main(cfg, acct)
        else:
            HelperConsole(cfg, acct).run()
    except KeyboardInterrupt:
        pass
    finally:
        release_lock(cfg, acct["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
