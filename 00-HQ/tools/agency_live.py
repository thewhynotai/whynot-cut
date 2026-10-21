"""WhyNot Cut AGENCY LIVE: one read-only screen for Yunus (who is working, on which model and level, where each task
stands, whether the main account is stopped by a usage limit). Refreshes every 5 s; closing it changes nothing.

  python -X utf8 agency_live.py          # live screen (the Desktop shortcut "WhyNot - Agency LIVE")
  python -X utf8 agency_live.py --once   # print one screen and exit

Sources (read only): the Claude app's session files (model, effort, last activity, error, one-line summary), the
session transcripts (their write time = working now) and their sub-agents (`<session>/subagents/agent-*.jsonl` + `.meta.json`),
the app's plan-usage-history.json (main-account usage %), helper status.json + run logs, 00-HQ BOARD / intake / inbox,
`heavy.sh status` and git. This screen writes nothing; `heavy.sh status` itself does the queue's own designed cleanup
(dead tickets, day-old .peak files). English on purpose: the Windows console cannot shape Arabic.
"""
import datetime as dt, glob, json, os, re, shutil, subprocess, sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hq_status as hq  # noqa: E402  (parse_board, helper_state, open_requests, inbox_reports, intake_verdicts)

APP_SESSIONS = Path(os.environ.get("APPDATA", ""), "Claude", "claude-code-sessions")
TRANSCRIPTS = Path.home() / ".claude" / "projects"
USAGE = Path(os.environ.get("APPDATA", ""), "Claude", "plan-usage-history.json")
AGENT_WINDOW_SEC = 6 * 3600  # sub-agents started or active in the last 6 h are listed (finished ones are not)
HEAVY = "C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh"
WORKING_SEC = 180   # a transcript or run log written this recently = working now
GOAL_TAG, GOAL = "v3.0.0-p4", "finish Gate 4 -> release v3.0.0-p4"  # update both at each release

PEOPLE = [  # (session id, name, account)
    ("local_22b44953-13e2-409d-93c1-3b201b119548", "Executor (merges, Gate 4)", "info@ main"),
    ("local_b32f950e-064d-4ef3-8d7a-6138a875d045", "Builder A (ideas K+M)", "info@ main"),
    ("local_a36b6974-0281-4d5f-b70f-d0bd7c51b4ef", "Command Center (HQ)", "info@ main"),
]
HELPERS = [("h1", "Helper 1 (Mayar, engine)", "mayar@"), ("h2", "Helper 2 (marketing, product)", "marketing@")]
ROUTINES = [  # (task id, name, minutes past the hour, hours or None = every hour)
    ("whynot-cut-hq-intake", "Intake: checks helper work", [37], None),
    ("whynot-cut-primary-report-2", "Report to you", [0], [9, 13, 17, 21]),
    ("whynot-cut-auto-resume-2", "Watchdog: restarts stopped work", [13, 43], None),
]
MODELS = {"opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku", "fable": "Fable"}
COL = {"green": "32", "yellow": "33", "red": "31", "gray": "90", "bold": "1", "": ""}
CHECKING = ("checking…", "gray")


# ------------------------------------------------------------------------------------------------ pure helpers
def model_name(m):
    """'claude-opus-5-5' / 'opus' -> 'Opus 5.5' / 'Opus'."""
    m = (m or "").lower()
    for k, v in MODELS.items():
        if k in m:
            ver = re.search(rf"{k}-(\d+)-(\d+)", m)
            return f"{v} {ver.group(1)}.{ver.group(2)}" if ver else v
    return m or "?"


def ago(minutes):
    if minutes is None:
        return "?"
    if minutes < 1:
        return "now"
    if minutes < 60:
        return f"{int(minutes)} min"
    return f"{int(minutes // 60)} h {int(minutes % 60):02d} min"


def latin(text, n=200):
    """One line of mostly-Latin text (Arabic is dropped: the Windows console cannot shape it)."""
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    if arabic > len(text) * 0.3:
        return ""
    return text if len(text) <= n else text[: n - 1] + "…"


def limit_reset(error, error_at):
    """'... resets 10:20pm (Africa/Cairo)' + the error time -> the reset datetime (local), else None."""
    m = re.search(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", error or "", re.I)
    if not m or not error_at:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    reset = error_at.replace(hour=h, minute=int(m.group(2) or 0), second=0, microsecond=0)
    return reset + dt.timedelta(days=1) if reset <= error_at else reset


def account_state(errors, now):
    """errors: [(error text, error datetime)]. The newest usage-limit error decides:
    ('LIMITED', reset) while it is on; ('LIMITED', None) when its reset cannot be read and it is under 5 h old;
    else ('OK', (its time, its reset) or None)."""
    lim = sorted((at, e) for e, at in errors if at and "limit" in (e or "").lower())
    if not lim:
        return "OK", None
    at, e = lim[-1]
    reset = limit_reset(e, at)
    if reset is None:
        return ("LIMITED", None) if now - at < dt.timedelta(hours=5) else ("OK", None)
    return ("LIMITED", reset) if now < reset else ("OK", (at, reset))


def usage_line(samples, now):
    """plan-usage-history samples -> 'used 37% of the 5-hour limit (at 22:20) · weekly 17%' for the account whose
    sample is newest ('fh' = 5-hour window %, shown when under 5 h old; 'sd' = 7-day %, when under 24 h old), or ''."""
    if not samples:
        return ""
    newest = max(samples, key=lambda x: x.get("t", 0))
    mine = [x for x in samples if x.get("org") == newest.get("org")]
    fh = max((x for x in mine if "fh" in (x.get("u") or {})), key=lambda x: x["t"], default=None)
    sd = max((x for x in mine if "sd" in (x.get("u") or {})), key=lambda x: x["t"], default=None)
    parts = []
    if fh and now - dt.datetime.fromtimestamp(fh["t"] / 1000) < dt.timedelta(hours=5):
        at = dt.datetime.fromtimestamp(fh["t"] / 1000)
        parts.append(f"used {fh['u']['fh']}% of the 5-hour limit (at {at:%H:%M})")
    if sd and now - dt.datetime.fromtimestamp(sd["t"] / 1000) < dt.timedelta(hours=24):
        parts.append(f"weekly {sd['u']['sd']}%")
    return " · ".join(parts)


def subagent_state(meta, last, age_sec, parent_limited=False):
    """meta: agent-*.meta.json; last: its transcript's last line (dict); age_sec: since the transcript was written;
    parent_limited: its session hit a usage limit after the agent's last write. -> None when it finished, else
    (word, colour)."""
    msg = (last or {}).get("message") or {}
    if meta.get("finished") or (last or {}).get("type") == "assistant" and msg.get("stop_reason") == "end_turn":
        return None
    if age_sec is not None and age_sec <= WORKING_SEC:
        return "WORKING now", "green"
    if parent_limited:
        return "STOPPED: usage limit", "red"
    if (age_sec or 0) > 1800:
        return f"STOPPED? quiet {ago((age_sec or 0) / 60)}", "gray"
    return f"QUIET {ago((age_sec or 0) / 60)}", "yellow"


def next_run(minutes, hours, now):
    t = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    for _ in range(60 * 48):
        if t.minute in minutes and (hours is None or t.hour in hours):
            return t
        t += dt.timedelta(minutes=1)
    return None


def person_status(error, error_at, last_activity, transcript_age_sec, now):
    """-> (word, colour) for a Claude-app session."""
    if error and "limit" in error.lower() and error_at and (last_activity is None or error_at >= last_activity):
        reset = limit_reset(error, error_at)
        if reset and now < reset:
            return f"STOPPED: usage limit until {reset:%H:%M}", "red"
        return "STOPPED after a limit: watchdog restarts it", "yellow"
    if transcript_age_sec is not None and transcript_age_sec <= WORKING_SEC:
        return "WORKING now", "green"
    quiet = (now - last_activity).total_seconds() / 60 if last_activity else None
    if quiet is not None and quiet > 90:
        return f"IDLE {ago(quiet)}", "gray"
    return f"QUIET {ago(quiet)}", "yellow"


def parse_queue(text):
    """heavy.sh status text -> {'ram': '79' or None, 'running': {label: min}, 'waiting': {label: min}}."""
    q = {"ram": None, "running": {}, "waiting": {}}
    m = re.search(r"RAM (\d+)%", text or "")
    q["ram"] = m.group(1) if m else None
    part = None
    for line in (text or "").splitlines():
        if line.startswith("Running:"):
            part = "running"
        elif line.startswith("Waiting"):
            part = "waiting"
        elif not line.startswith("  "):
            part = None
        elif part:
            w = line.split()
            if part == "running" and len(w) >= 4 and w[3].isdigit():    # heavy-1  suite <label>  28 min ...
                q["running"][w[2]] = int(w[3])
            elif part == "waiting" and len(w) >= 3 and w[2].isdigit():  # suite <label>  74 min ...
                q["waiting"][w[1]] = int(w[2])
    return q


def queue_summary(q):
    out = f"RAM {q['ram']}%" if q["ram"] else "RAM ?"
    out += f" · test queue: {len(q['running'])} running, {len(q['waiting'])} waiting"
    return out + (f" (oldest {ago(max(q['waiting'].values()))})" if q["waiting"] else "")


def helper_tests(who, card_text, q):
    """The helper's own test job in the queue -> ('RUNNING TESTS n min' | 'IN TEST QUEUE n min', colour) or None."""
    prefixes = [f"{who}-"]
    m = re.match(r"peer review of (\S+)", card_text or "")
    if m:
        prefixes.append(f"peer-{m.group(1)}")
    for part, word, colour in (("running", "RUNNING TESTS", "green"), ("waiting", "IN TEST QUEUE", "yellow")):
        hits = [mins for label, mins in q[part].items() if label.startswith(tuple(prefixes))]
        if hits:
            return f"{word} {ago(max(hits))}", colour
    return None


def helper_status(state, loop_alive, log_age_sec, reason, until, waiting_sec=0, tests=None):
    """-> (word, colour) for a helper AUTO loop. loop_alive None = not checked yet; waiting_sec: how long its current
    tool has been waiting; tests: helper_tests() result."""
    if loop_alive is None:
        return CHECKING
    if not loop_alive:
        return "LOOP NOT RUNNING", "red"
    if state == "running":
        if tests:
            return tests
        if waiting_sec >= 120:
            return f"WAITING {ago(waiting_sec / 60)}", "yellow"
        if log_age_sec is not None and log_age_sec <= WORKING_SEC:
            return "WORKING now", "green"
        return f"QUIET {ago((log_age_sec or 0) / 60)}", "yellow"
    if state == "yielding":
        return "PAUSED: lets Gate 4 tests go first", "yellow"
    if state == "idle":
        return "IDLE: no card for it", "gray"
    if state == "waiting":
        return f"WAITING: limit until {until[-5:]}" if until else "WAITING", "yellow"
    return (state or "?").upper() + (f": {reason}" if reason else ""), "red"


def helper_card(who, log_lines, auto_log_tail, board_ids):
    """What the current run works on: 'peer review of BL-03 (H2)' from auto.log, else the last BOARD card id that its
    own commands name after `h1/` (branch) or `h1-` (test-queue label). The BOARD it reads lists every card, so
    plain file reads cannot tell."""
    for line in reversed(auto_log_tail):
        if " run " in line and " started " in line:
            continue
        m = re.search(r"peer review of (h[12])'s (\S+)", line)
        if m:
            return f"peer review of {m.group(2)} ({m.group(1).upper()})"
        break
    ids = {i.lower(): i for i in board_ids}
    card = ""
    for raw in log_lines:
        if '"tool_use"' not in raw:
            continue
        for m in re.finditer(rf"\b{who}[/-]([A-Za-z0-9-]+)", raw):
            parts = m.group(1).split("-")
            for n in range(len(parts), 0, -1):  # longest prefix that is a card id: S6b-r1 -> S6b, BL-04 -> BL-04
                if "-".join(parts[:n]).lower() in ids:
                    card = ids["-".join(parts[:n]).lower()]
                    break
    return f"card {card}" if card else ""


def helper_doing(log_lines):
    """-> (last thing the run said, seconds its current tool has been waiting; 0 when not waiting)."""
    said, waiting = "", 0
    for raw in log_lines:
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            waiting = 0
            for b in (e.get("message") or {}).get("content") or []:
                if b.get("type") == "text" and b.get("text", "").strip():
                    said = b["text"]
        elif e.get("type") == "tool_progress" and e.get("heartbeat"):
            waiting = int(e.get("elapsed_time_seconds") or 0)
    return latin(said, 160), waiting


def task_groups(rows, reports, verdicts, today, card_mtime):
    """BOARD rows -> ordered {group: [label]} in plain words."""
    g = {"Working on": [], "Waiting for review": [], "Waiting for merge": [], "Next up": [], "Blocked": [],
         "Finished today": []}
    delivered = {}
    for name, rep in reports.items():
        cid = re.search(r"((?:BL|OPS|ENV|SETUP|S|T)-?[A-Za-z0-9.]+)$", name)
        if cid and rep.get("status") == "DONE":
            v = verdicts.get(rep.get("file", ""), {}).get("verdict", "")
            if v in ("", "processing", "awaiting-peer"):
                delivered[cid.group(1)] = rep["who"].upper()
    for r in rows:
        s, who, cid = r["status"].upper(), r["owner"].split()[0] if r["owner"] else "", r["id"]
        if cid.startswith("("):
            continue
        if cid in delivered and s not in ("ACCEPTED", "MERGED", "DONE_ARCHIVED"):
            g["Waiting for review"].append(f"{cid} ({delivered[cid]})")
        elif s in ("FIX", "IN PROGRESS", "IN_PROGRESS", "RUNNING"):
            g["Working on"].append(f"{cid} ({who}{', fix' if s == 'FIX' else ''})")
        elif s == "ACCEPTED" and not re.search(r"no code|nothing to merge", r.get("status_note", ""), re.I):
            g["Waiting for merge"].append(f"{cid} ({who})")
        elif s == "READY":
            g["Next up"].append(f"{cid} ({who})")
        elif s in ("BLOCKED", "PARKED", "STOPPED"):
            g["Blocked"].append(f"{cid} ({who})")
        elif s in ("MERGED", "DONE_ARCHIVED", "DONE") and card_mtime(r.get("card", "")) == today:
            g["Finished today"].append(cid)
    return g


def recent_decisions(state, today, n=4):
    """intake/state.json -> the last n real verdicts, newest first: '22:40 BL-03 ACCEPTED' today, else
    '10-20 21:40 BL-03 FIX r1'."""
    out = []
    for path, v in state.items():
        verdict = v.get("verdict") or ""
        if verdict in ("", "noted", "processing", "awaiting-peer"):
            continue
        cid = re.search(r"((?:BL|OPS|ENV|SETUP|S|T)-?[A-Za-z0-9.]+?)(?:-r\d+)?\.md$", path.replace("\\", "/"))
        at = v.get("at") or ""
        when = at[-5:] if at[:10] == f"{today:%Y-%m-%d}" else at[5:]
        out.append((at, f"{when} {cid.group(1) if cid else path} {verdict}"))
    return [t for _, t in sorted(out, reverse=True)[:n]]


# ------------------------------------------------------------------------------------------------ readers
_cache = {}


def _cached(path, parse):
    """parse(path) once per file version (mtime + size)."""
    try:
        st = os.stat(path)
    except OSError:
        return parse(None)
    key = (st.st_mtime, st.st_size)
    hit = _cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    val = parse(path)
    _cache[path] = (key, val)
    return val


def _session(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        data = {}
    return {k: data.get(k) for k in ("sessionId", "cliSessionId", "model", "effort", "lastActivityAt", "createdAt",
                                     "scheduledTaskId", "error", "errorAt", "postTurnSummary", "lastTurnReport",
                                     "title", "cwd")}


def _lines(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines() if path else []
    except OSError:
        return []


def _ms(v):
    try:
        return dt.datetime.fromtimestamp(int(v) / 1000)
    except (TypeError, ValueError, OSError):
        return None


def app_sessions():
    return [_cached(p, _session) for p in glob.glob(str(APP_SESSIONS / "*" / "*" / "local_*.json"))]


def transcript_age(cli_id, now_ts):
    if not cli_id:
        return None
    ages = [now_ts - os.path.getmtime(p) for p in glob.glob(str(TRANSCRIPTS / "*" / f"{cli_id}.jsonl"))]
    return min(ages) if ages else None


def _run(cmd, timeout=20):
    """-> (stdout, returncode); ('', None) when it fails or times out."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.stdout, r.returncode
    except Exception:
        return "", None


_slow = {"t": 0, "queue": "", "git": ("?", "?"), "alive": {}, "agents": [], "top": []}


def _tail(path, size=262144):
    """Read only a transcript's end -> (last JSON line, model and effort of the last line that names them)."""
    last, model, effort = {}, "", ""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - size))
            raws = f.read().splitlines()
    except OSError:
        return last, model, effort
    for raw in reversed(raws):
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        last = last or e
        model = model or (e.get("message") or {}).get("model") or ""
        effort = effort or e.get("effort") or ""
        if model and effort:
            break
    return last, model, effort


def scan_agents(now_ts):
    """Unfinished sub-agents of the main account's sessions and of both helpers' runs, active in the last 6 h.
    -> [(parent cli id or helper, meta, last line, model, effort, age seconds)]."""
    roots = [(str(TRANSCRIPTS / "*" / "*" / "subagents" / "agent-*.jsonl"), None)]
    roots += [(str(hq.ACCOUNTS / h / "projects" / "*" / "*" / "subagents" / "agent-*.jsonl"), h) for h, _, _ in HELPERS]
    out = []
    for pattern, helper in roots:
        for path in glob.glob(pattern):
            try:
                age = now_ts - os.path.getmtime(path)
            except OSError:
                continue
            if age > AGENT_WINDOW_SEC:
                continue
            try:
                meta = json.loads(Path(path[:-6] + ".meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            if meta.get("finished"):
                continue
            parent = helper or Path(path).parent.parent.name
            out.append((parent, meta) + _tail(path) + (age,))
    return out


def refresh_slow():
    """Things that cost a process spawn (heavy.sh status alone takes ~7 s). The live screen runs this in a background
    thread every 15 s, so the screen itself never freezes. Each value is replaced whole (no torn reads)."""
    queue, _ = _run(["bash", HEAVY, "status"])
    repo = str(hq.REPO)
    tag = _run(["git", "-C", repo, "describe", "--tags", "--abbrev=0", "release/3.0"])[0].strip() or "?"
    ahead = _run(["git", "-C", repo, "rev-list", "--count", "origin/release/3.0..release/3.0"])[0].strip() or "?"
    alive = {}
    for h, _, _ in HELPERS:
        _, rc = _run([sys.executable, "-X", "utf8", str(hq.ACCOUNTS / "helper_loop.py"), h, "--alive"])
        alive[h] = _slow["alive"].get(h) if rc is None else rc == 0  # a timed-out check keeps the last answer
    agents = scan_agents(time.time())
    ram = hq.ram_percent() or 0
    try:
        top = top_memory() if ram >= 85 else []
    except Exception:
        top = []
    _slow.update(queue=queue, git=(tag, ahead), alive=alive, agents=agents, top=top, t=time.time())


def top_memory(n=3):
    """[(process name, MB)] of the n biggest processes by working set (Win32 API: fast even when the PC thrashes)."""
    import ctypes
    from ctypes import wintypes
    psapi, k32 = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype, k32.OpenProcess.argtypes = wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                   [(f, ctypes.c_size_t) for f in ("Peak", "WorkingSet", "QPP", "QP", "QPNP", "QNP", "Page", "PeakPage")]
    pids = (wintypes.DWORD * 4096)()
    got = wintypes.DWORD()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got)):
        return []
    sizes = {}
    for pid in pids[: got.value // ctypes.sizeof(wintypes.DWORD)]:
        h = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION: also opens protected processes
        if not h:
            continue
        try:
            pmc, name, size = PMC(), ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
            pmc.cb = ctypes.sizeof(PMC)
            if psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb) and \
                    k32.QueryFullProcessImageNameW(h, 0, name, ctypes.byref(size)):
                exe = os.path.basename(name.value).rsplit(".", 1)[0]
                sizes[exe] = sizes.get(exe, 0) + pmc.WorkingSet
        finally:
            k32.CloseHandle(h)
    return [(k, v // 2 ** 20) for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])[:n]]


def card_mtime_fn(hq_dir):
    def f(card):
        if not card:
            return None
        try:
            return dt.date.fromtimestamp(Path(hq_dir, card).stat().st_mtime)
        except OSError:
            return None
    return f


# ------------------------------------------------------------------------------------------------ screen
def build(now=None):
    now = now or dt.datetime.now()
    now_ts = time.time()
    sessions = app_sessions()
    by_id = {s.get("sessionId"): s for s in sessions if s.get("sessionId")}
    slow = dict(_slow)
    q = parse_queue(slow["queue"])
    lines = []

    def add(text="", colour=""):
        lines.append((text, colour))

    # header
    errors = [(s.get("error"), _ms(s.get("errorAt"))) for s in sessions if s.get("error") and s.get("errorAt")]
    acc, info = account_state(errors, now)
    add(f"WHYNOT CUT · AGENCY LIVE        {now:%a %d %b %Y · %H:%M:%S}        read-only, refreshes every 5 s", "bold")
    if acc == "LIMITED":
        until = f"until {info:%H:%M}" if info else "(reset time unknown)"
        add(f"Main account (info@): STOPPED by the usage limit {until}. Helpers keep working on their own accounts;"
            " the watchdog restarts the rest after the reset.", "red")
    else:
        last = f" (last usage limit ended {info[1]:%a %H:%M})" if info else ""
        add(f"Main account (info@): OK{last}", "green")
    try:
        usage = usage_line(json.loads(USAGE.read_text(encoding="utf-8")).get("samples") or [], now)
    except (OSError, ValueError):
        usage = ""
    if usage:
        lines.append(("\0   ·   " + usage, ""))
    tag, ahead = slow["git"]
    if not slow["t"]:
        add(f"Goal: {GOAL}.  (checking git…)")
    elif tag == GOAL_TAG:
        add(f"Goal reached: {tag} is tagged. Set the next goal in 00-HQ/tools/agency_live.py (GOAL).", "yellow")
    else:
        add(f"Goal: {GOAL}.  Last release: {tag}.  Merged work not on GitHub yet: {ahead} commits (pushed at the"
            " release).")
    if not slow["t"]:
        add("PC: checking…", "gray")
    else:
        old = (now_ts - slow["t"]) / 60
        add("PC: " + queue_summary(q) + (f"   (queue info {ago(old)} old)" if old > 1 else ""))
        if slow.get("top"):
            add("  RAM is high: biggest users " + ", ".join(f"{n} {mb / 1024:.1f} GB" for n, mb in slow["top"]) +
                ". New test jobs wait until RAM is under 85%.", "red")
    add()

    # who
    add(f"{'WHO':<30}{'ACCOUNT':<12}{'MODEL':<10}{'LEVEL':<8}{'STATUS':<40}WHAT IT IS DOING", "bold")
    for sid, name, account in PEOPLE:
        s = by_id.get(sid) or {}
        last = _ms(s.get("lastActivityAt"))
        word, colour = person_status(s.get("error"), _ms(s.get("errorAt")), last,
                                     transcript_age(s.get("cliSessionId"), now_ts), now)
        doing = latin((s.get("postTurnSummary") or {}).get("status_detail")) or latin(s.get("lastTurnReport"))
        add(f"{name:<30}{account:<12}{model_name(s.get('model')):<10}{(s.get('effort') or '?'):<8}")
        lines.append(("\0" + word.ljust(40), colour))
        lines.append(("\0" + (doing or "-"), ""))
    try:
        rows = hq.parse_board(Path(hq.HQ, "BOARD.md").read_text(encoding="utf-8"))
    except OSError:
        rows = []
    board_ids = [r["id"] for r in rows]
    logs_now = set()
    for h, name, account in HELPERS:
        st = hq.helper_state(hq.ACCOUNTS, h)
        try:
            raw = json.loads(Path(hq.ACCOUNTS, h, "auto", "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        log = raw.get("log") or ""
        logs_now.add(log)
        log_lines = _cached(log, _lines) if log else []
        try:
            log_age = now_ts - os.path.getmtime(log) if log else None
        except OSError:
            log_age = None
        running = st["state"] == "running"
        said, waiting = helper_doing(log_lines) if running else (latin(st["reason"]), 0)
        tail = _lines(str(Path(hq.ACCOUNTS, h, "auto", "auto.log")))[-3:]
        card = helper_card(h, log_lines, tail, board_ids) if running else ""
        tests = helper_tests(h, card, q) if running and slow["t"] else None
        alive = slow["alive"].get(h)
        word, colour = helper_status(st["state"], alive, log_age, st["reason"], raw.get("until"), waiting, tests)
        doing = (f"{card}: " if card else "") + said
        add(f"{name:<30}{account:<12}{model_name(raw.get('model')):<10}{(raw.get('effort') or '?'):<8}")
        lines.append(("\0" + word.ljust(40), colour))
        lines.append(("\0" + (doing or "-"), ""))
    for old in [k for k in _cache if k.endswith(".jsonl") and k not in logs_now]:  # finished runs' logs (MBs)
        del _cache[old]
    add()

    # agents: the sub-agents those sessions started (reviewers, builders) that have not finished
    names = {s.get("cliSessionId"): n for sid, n, _ in PEOPLE for s in [by_id.get(sid) or {}]}
    names.update({s.get("cliSessionId"): rname for s in sessions for tid, rname, _, _ in ROUTINES
                  if s.get("scheduledTaskId") == tid})
    names.update({h: n.split(" (")[0] for h, n, _ in HELPERS})
    for s in sessions:  # any other chat on the main account: its English title, else its folder
        if s.get("cliSessionId") and s["cliSessionId"] not in names:
            names[s["cliSessionId"]] = latin(s.get("title"), 26) or f"Chat in {Path(s.get('cwd') or '?').name}"
    by_cli = {s.get("cliSessionId"): s for s in sessions if s.get("cliSessionId")}
    agents = []
    for parent, meta, last, model, effort, age in slow["agents"]:
        ps = by_cli.get(parent) or {}
        err_at = _ms(ps.get("errorAt"))
        limited = bool(ps.get("error") and "limit" in ps["error"].lower() and err_at and
                       err_at.timestamp() >= now_ts - age)
        state = subagent_state(meta, last, age, limited)
        if state:
            agents.append((names.get(parent, "Other chat"), meta, model, effort, age, state))
    add(f"AGENTS working inside those sessions ({len(agents) if slow['t'] else '…'})", "bold")
    if not slow["t"]:
        add("  checking…", "gray")
    elif not agents:
        add("  none right now", "gray")
    for parent, meta, model, effort, age, (word, colour) in sorted(agents, key=lambda a: a[4])[:12]:
        add(f"  {parent[:28]:<28}{model_name(model or meta.get('model')):<10}{(effort or '?'):<8}")
        lines.append(("\0" + word.ljust(16), colour))
        lines.append(("\0" + (latin(meta.get("description"), 90) or meta.get("agentType") or "-"), ""))
    if len(agents) > 12:
        add(f"  … and {len(agents) - 12} more", "gray")
    add()

    # routines
    add("AUTOMATIC ROUTINES (main account)", "bold")
    for tid, name, minutes, hours in ROUTINES:
        runs = sorted((s for s in sessions if s.get("scheduledTaskId") == tid), key=lambda s: int(s.get("createdAt") or 0))
        nxt = next_run(minutes, hours, now)
        nxt_text = f"next {nxt:%H:%M}   " if nxt else ""
        if not runs:
            add(f"  {name:<34}no run yet", "")
            lines.append(("\0" + " " * 18 + nxt_text, "gray"))
            continue
        r = runs[-1]
        started = _ms(r.get("createdAt"))
        age = transcript_age(r.get("cliSessionId"), now_ts)
        if r.get("error"):
            res, colour = ("FAILED: usage limit" if "limit" in r["error"].lower() else "FAILED"), "red"
        elif age is not None and age <= WORKING_SEC:
            res, colour = "RUNNING", "green"
        else:
            res, colour = "done", "green"
        detail = latin((r.get("postTurnSummary") or {}).get("status_detail"), 70)
        add(f"  {name:<34}last {started:%H:%M}  " if started else f"  {name:<34}last ?      ", "")
        lines.append(("\0" + res.ljust(22), colour))
        lines.append(("\0" + nxt_text + detail, "gray"))
    add()

    # tasks
    add("TASKS (from 00-HQ/BOARD.md)", "bold")
    groups = task_groups(rows, hq.inbox_reports(hq.HQ), hq.intake_verdicts(hq.HQ), now.date(), card_mtime_fn(hq.HQ))
    for gname, items in groups.items():
        if items or gname in ("Working on", "Next up"):
            add(f"  {gname + ':':<20}" + (" · ".join(items) if items else "-"),
                "yellow" if gname == "Blocked" else "")
    try:
        state = json.loads(Path(hq.HQ, "intake", "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    decisions = recent_decisions(state, now.date())
    if decisions:
        add(f"  {'Latest decisions:':<20}" + " · ".join(decisions), "gray")
    add()

    # needs you
    asks = hq.open_requests(Path(hq.HQ, "PRIMARY_ACCOUNT_INBOX.md"))
    urgent = [a for a in asks if not re.search(r"Optional|only when|only matters", a, re.I)]
    add("NEEDS YOU: " + ("; ".join(latin(a, 90) for a in urgent) if urgent else "nothing right now"),
        "yellow" if urgent else "green")
    if len(asks) > len(urgent):
        add(f"  (optional, no rush: {', '.join(a.split(' ')[0] for a in asks if a not in urgent)}: see "
            "00-HQ/PRIMARY_ACCOUNT_INBOX.md)", "gray")
    return lines


def render(lines, width, colour=True):
    """Join the (text, colour) parts; a part starting with NUL continues the previous line."""
    def paint(t, c):
        return f"\x1b[{COL[c]}m{t}\x1b[0m" if colour and COL.get(c) else t

    rows = []
    for text, c in lines:
        if text.startswith("\0"):
            rows[-1].append((text[1:], c))
        else:
            rows.append([(text, c)])
    out = []
    for parts in rows:
        room, cur = width - 1, ""
        for t, c in parts:
            t = t[:max(room, 0)]
            room -= len(t)
            cur += paint(t, c)
        out.append(cur)
    return "\n".join(out)


def main():
    if "--once" in sys.argv:
        refresh_slow()
        print(render(build(), shutil.get_terminal_size((160, 40)).columns, colour=False))
        return

    def slow_loop():
        while True:
            try:
                refresh_slow()
            except Exception:
                pass
            time.sleep(15)
    threading.Thread(target=slow_loop, daemon=True).start()
    os.system("")  # turns on colour codes in the Windows console
    os.system("title WhyNot Cut - AGENCY LIVE")
    first = True
    while True:
        try:
            text = render(build(), shutil.get_terminal_size((160, 40)).columns)
        except Exception as e:  # a reader hiccup never closes the window
            text = f"(screen error, retrying in 5 s: {type(e).__name__}: {e})"
        sys.stdout.write(("\x1b[2J" if first else "") + "\x1b[H" + text.replace("\n", "\x1b[K\n") + "\x1b[K\x1b[J")
        sys.stdout.flush()
        first = False
        time.sleep(5)


if __name__ == "__main__":
    main()
