"""Builds one snapshot of the three accounts, their tasks and the PC. Read-only; no model is ever called.

Fast part (every watch tick, only when a watched file changed): sessions, helper run logs, BOARD and reports.
Slow part (background, every `slow_seconds`): heavy queue, git, helper loop liveness, sub-agents, processes.
"""
import collections, datetime as dt, glob, json, os, re, threading, time
from pathlib import Path

import common
import agency_live as al  # noqa: E402  (session readers, queue parser, card finder, usage line, agent scan)
import hq_status as hq  # noqa: E402
import ownermsg, runlog, status as S, tasks as T

MAIN_CONFIG = Path.home() / ".claude.json"


def iso(ts):
    return dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None


def ms_iso(v):
    d = al._ms(v)
    return d.isoformat(timespec="seconds") if d else None


def identity(path):
    """Signed-in account of a Claude profile: {'email','org'} (nothing else is read out of the file)."""
    try:
        with open(path, encoding="utf-8") as f:
            a = (json.load(f).get("oauthAccount") or {})
        return {"email": a.get("emailAddress"), "org": a.get("organizationName")}
    except (OSError, ValueError):
        return {"email": None, "org": None}


def process_names():
    """Lower-case image names of running processes (Win32, no spawn)."""
    if os.name != "nt":
        return set()
    import ctypes
    from ctypes import wintypes
    psapi, k32 = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    pids, got = (wintypes.DWORD * 4096)(), wintypes.DWORD()
    if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got)):
        return set()
    names = set()
    for pid in pids[: got.value // ctypes.sizeof(wintypes.DWORD)]:
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        try:
            buf, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                names.add(os.path.basename(buf.value).lower())
        finally:
            k32.CloseHandle(h)
    return names


class Collector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.th = cfg["thresholds"]
        self.windows = runlog.WindowRegistry(str(common.state_path(cfg, "model_windows.json")))
        self.feeds = {}                       # run log path -> RunFeed
        self.recent = {}                      # helper id -> deque of readable events
        self.tctx = {}                        # transcript path -> ((mtime, size), context)
        self.slow = {"t": 0, "queue": "", "git": ("?", "?"), "branches": {}, "alive": {}, "agents": [],
                     "top": [], "procs": set(), "errors": {}}
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ slow sources
    def refresh_slow(self):
        errors = {}
        queue = ""
        try:
            queue, _ = al._run(["bash", al.HEAVY, "status"])
        except Exception as e:  # noqa: BLE001
            errors["queue"] = str(e)
        repo = str(hq.REPO)
        tag = al._run(["git", "-C", repo, "describe", "--tags", "--abbrev=0", "release/3.0"])[0].strip() or "?"
        ahead = al._run(["git", "-C", repo, "rev-list", "--count", "origin/release/3.0..release/3.0"])[0].strip() or "?"
        out, rc = al._run(["git", "-C", repo, "for-each-ref", "--format=%(refname:short)|%(committerdate:iso-strict)",
                           "refs/heads/h1", "refs/heads/h2"])
        branches = dict(l.split("|", 1) for l in out.splitlines() if "|" in l)
        if rc != 0:
            errors["git"] = "git for-each-ref failed"
        alive = {}
        for a in self.helpers():
            _, rc = al._run([al.sys.executable, "-X", "utf8", str(hq.ACCOUNTS / "helper_loop.py"), a["id"], "--alive"])
            alive[a["id"]] = self.slow["alive"].get(a["id"]) if rc is None else rc == 0
        try:
            agents = al.scan_agents(time.time())
        except Exception as e:  # noqa: BLE001
            agents, errors["agents"] = [], str(e)
        ram = hq.ram_percent() or 0
        try:
            top = al.top_memory() if ram >= 85 else []
        except Exception:  # noqa: BLE001
            top = []
        try:
            procs = process_names()
        except Exception:  # noqa: BLE001
            procs = set()
        with self.lock:
            self.slow.update(queue=queue, git=(tag, ahead), branches=branches, alive=alive, agents=agents, top=top,
                             procs=procs, errors=errors, t=time.time())

    def helpers(self):
        return [a for a in self.cfg["accounts"] if a["kind"] == "helper"]

    # ------------------------------------------------------------------ readers
    def transcript(self, cli_id):
        if not cli_id:
            return None, None
        paths = glob.glob(str(al.TRANSCRIPTS / "*" / f"{cli_id}.jsonl"))
        if not paths:
            return None, None
        p = max(paths, key=os.path.getmtime)
        st = os.stat(p)
        key = (st.st_mtime, st.st_size)
        hit = self.tctx.get(p)
        if not hit or hit[0] != key:
            hit = (key, runlog.transcript_context(p))
            self.tctx[p] = hit
        return hit[1], time.time() - st.st_mtime

    def feed(self, path):
        f = self.feeds.get(path)
        if f is None:
            f = self.feeds[path] = runlog.RunFeed(path)
        return f, f.poll()

    # ------------------------------------------------------------------ build
    def build(self):
        now, now_ts = dt.datetime.now(), time.time()
        with self.lock:
            slow = dict(self.slow)
        q = al.parse_queue(slow["queue"])
        sessions = al.app_sessions()
        sources = {"slow": {"ok": bool(slow["t"]), "at": iso(slow["t"]), "errors": slow["errors"]}}
        rows = hq.parse_board(T._read(common.HQ / "BOARD.md"))
        board_ids = [r["id"] for r in rows]
        reps = T.reports_by_task(common.HQ)

        accounts, current = [], {}
        for a in self.cfg["accounts"]:
            if a["kind"] == "desktop":
                accounts.append(self.main_account(a, sessions, slow, now, now_ts))
            else:
                acc = self.helper_account(a, slow, q, board_ids, reps, now)
                accounts.append(acc)
                if acc["task_id"]:
                    current[acc["task_id"]] = {"account": a["id"], "action": acc["action"],
                                               "run_started": acc["session"]["started"]}
        task_list = T.build_tasks(common.HQ, slow["branches"], q, current=current)
        by_id = {t["id"]: t for t in task_list}
        for acc in accounts:
            t = by_id.get(acc.get("task_id") or "")
            acc["task"] = {"id": t["id"], "title": t["title"], "summary": t["summary"], "display": t["display"],
                           "progress": t["progress"]} if t else None

        snap = {
            "generated_at": now.isoformat(timespec="seconds"),
            "accounts": accounts,
            "tasks": task_list,
            "agents": self.agents(sessions, slow, now_ts),
            "routines": self.routines(sessions, now, now_ts),
            "pc": {"ram": hq.ram_percent(), "queue": {"running": q["running"], "waiting": q["waiting"]},
                   "top_memory": slow["top"], "queue_at": iso(slow["t"])},
            "goal": self.goal(slow),
            "needs_you": [r for r in hq.open_requests(common.HQ / "PRIMARY_ACCOUNT_INBOX.md")],
            "sources": sources,
            "monitoring": {"llm_calls": 0, "method": "local files, process list, git, heavy-queue status"},
        }
        snap["alerts"] = alerts(snap, self.th)
        return snap

    def main_account(self, a, sessions, slow, now, now_ts):
        names = a.get("session_names") or {}
        window_h = self.th["main_session_window_hours"]
        rows = []
        for s in sessions:
            sid = s.get("sessionId")
            if not sid or s.get("scheduledTaskId"):
                continue
            last = al._ms(s.get("lastActivityAt"))
            if sid not in names and (not last or now - last > dt.timedelta(hours=window_h)):
                continue
            ctx, age = self.transcript(s.get("cliSessionId"))
            st = S.session_status({"error": s.get("error"), "error_at": al._ms(s.get("errorAt")), "last_activity": last,
                                   "transcript_age_sec": age, "awaiting_person": bool(s.get("interruptedAwaitingPerson"))},
                                  self.th, now)
            model = (ctx or {}).get("model") or s.get("model")
            doing = ((s.get("postTurnSummary") or {}).get("status_detail") or (s.get("turnWrapUp") or {}).get("description")
                     or s.get("lastTurnReport") or "")
            rows.append({
                "id": sid, "name": names.get(sid) or (s.get("title") if isinstance(s.get("title"), str) else "") or
                Path(s.get("cwd") or "?").name, "model": model, "model_name": al.model_name(model),
                "effort": s.get("effort"), "status": st, "started": ms_iso(s.get("createdAt")),
                "last_activity": last.isoformat(timespec="seconds") if last else None,
                "context": S.context_view((ctx or {}).get("tokens"), self.windows.get(model), (ctx or {}).get("at"),
                                          self.th["context_warn_percent"], self.th["context_danger_percent"]),
                "doing": runlog.one_line(doing, 300), "primary": sid == a.get("primary_session"),
                "folder": Path(s.get("cwd") or "").name,
            })
        rows.sort(key=lambda r: (not r["primary"], -(S.CODES[r["status"]["code"]][2]), r["last_activity"] or ""))
        primary = next((r for r in rows if r["primary"]), rows[0] if rows else None)
        ident = identity(MAIN_CONFIG)
        app_up = any(n == "claude.exe" for n in slow["procs"]) if slow["t"] else None
        code = S.rollup([r["status"]["code"] for r in rows])
        reason = next((f"{r['name']}: {r['status']['reason']}" for r in rows if r["status"]["code"] == code), "")
        if app_up is False and code in ("WORKING", "QUIET"):
            code, reason = "DISCONNECTED", "The Claude desktop app is not running."
        try:
            usage = al.usage_line(json.loads(al.USAGE.read_text(encoding="utf-8")).get("samples") or [], now)
        except (OSError, ValueError):
            usage = ""
        return {
            "id": a["id"], "name": a["name"], "role": a["role"], "email": a["email"], "kind": "desktop",
            "connection": {"signed_in": ident["email"], "org": ident["org"],
                           "ok": ident["email"] == a["email"] and app_up is not False,
                           "detail": ("Desktop app running" if app_up else "Desktop app not running" if app_up is False
                                      else "checking…") + (f" · signed in as {ident['email']}" if ident["email"] else "")},
            "status": S.make(code, reason) if code != "CHECKING" else S.make("CHECKING"),
            "model": primary["model"] if primary else None, "model_name": primary["model_name"] if primary else "?",
            "effort": primary["effort"] if primary else None,
            "session": {"id": primary["id"] if primary else None, "name": primary["name"] if primary else None,
                        "started": primary["started"] if primary else None,
                        "last_activity": max((r["last_activity"] or "" for r in rows), default=None) or None},
            "context": primary["context"] if primary else S.context_view(None, None, None, 0, 0),
            "usage": usage, "sessions": rows, "task_id": None, "action": primary["doing"] if primary else "",
            "recent": [],
        }

    def helper_account(self, a, slow, q, board_ids, reps, now):
        h = a["id"]
        auto = Path(a["profile"], "auto")
        try:
            raw = json.loads((auto / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        state = raw.get("state", "missing")
        log = raw.get("log") or ""
        feed, new = self.feed(log) if log else (None, [])
        rec = self.recent.setdefault(h, collections.deque(maxlen=12))
        rec.extend(e for e in new if e["kind"] in ("say", "tool", "error", "end", "start", "denied"))
        if feed and feed.window and feed.model:
            self.windows.learn(feed.model, feed.window, f"{h} run {Path(log).name}")
        try:
            log_age = time.time() - os.path.getmtime(log) if log else None
        except OSError:
            log_age = None
        running = state == "running"
        tail = T._read(auto / "auto.log")[-4000:].splitlines()[-3:]
        card_text = al.helper_card(h, ['"tool_use" ' + s for s in feed.tool_inputs], tail, board_ids) \
            if running and feed else ""
        tests_word = al.helper_tests(h, card_text, q) if running and slow["t"] else None
        tests = None
        if tests_word:
            mins_ = re.search(r"(\d+) h (\d+) min|(\d+) min", tests_word[0])
            m = (int(mins_.group(1)) * 60 + int(mins_.group(2))) if mins_ and mins_.group(1) else \
                int(mins_.group(3)) if mins_ and mins_.group(3) else 0
            tests = ("running" if tests_word[0].startswith("RUNNING") else "waiting", m)
        task_id = None
        m = re.match(r"(?:card|peer review of) (\S+)", card_text or "")
        if m:
            task_id = board_id(m.group(1), board_ids)
        newest = max((r for v in reps.values() for r in v if r["who"] == h), key=lambda r: r["mtime"], default=None)
        st = S.helper_status({
            "loop_alive": slow["alive"].get(h) if slow["t"] else None, "auto_on": (auto / "AUTO-ON").exists(),
            "stop_file": (auto / "STOP").exists(), "state": state, "reason": raw.get("reason", ""),
            "until": raw.get("until", ""), "log_age_sec": log_age, "tool_wait_sec": feed.tool_wait if feed else 0,
            "tests": tests, "report_blocked": bool(newest and newest["status"] == "BLOCKED"),
            "action": feed.action if feed else ""}, self.th)
        ident = identity(Path(a["profile"]) / ".claude.json")
        ok_ident = ident["email"] == a["email"] and ident["org"] == "thewhynot.ai org"
        model = (feed.model if feed and feed.model else None) or raw.get("model")
        ctx = S.context_view(feed.context if feed and running else None, self.windows.get(model),
                             feed.context_at if feed else None, self.th["context_warn_percent"],
                             self.th["context_danger_percent"])
        if feed and not running and feed.context is not None:
            ctx["last_run"] = {"tokens": feed.context, "at": feed.context_at}
        doing_kind = "peer review" if (card_text or "").startswith("peer review") else "card"
        return {
            "id": h, "name": a["name"], "role": a["role"], "email": a["email"], "kind": "helper",
            "connection": {"signed_in": ident["email"], "org": ident["org"], "ok": ok_ident,
                           "detail": (f"Signed in as {ident['email']} ({ident['org']})" if ident["email"] else
                                      "Not signed in") + ("" if ok_ident else f" · expected {a['email']}"),
                           "loop": "running" if slow["alive"].get(h) else "not running" if slow["t"] else "checking…",
                           "auto_on": (auto / "AUTO-ON").exists()},
            "status": st, "model": model, "model_name": al.model_name(model), "effort": raw.get("effort"),
            "session": {"id": feed.session_id if feed else None, "run": raw.get("run"), "log": log,
                        "started": raw.get("at") if running else None, "state_since": raw.get("at"),
                        "last_activity": iso(time.time() - log_age) if log_age is not None else None},
            "context": ctx,
            "usage": (f"5-hour window {feed.rate['five_hour_pct']}% used" if feed and feed.rate and
                      feed.rate.get("five_hour_pct") is not None else ""),
            "usage_resets": iso(feed.rate.get("resets_at")) if feed and feed.rate and feed.rate.get("resets_at") else None,
            "task_id": task_id, "task_kind": doing_kind if task_id else None,
            "action": (feed.action if feed and running else "") or "",
            "said": feed.last_text if feed else "", "result": feed.result if feed else None,
            "denials": feed.denials if feed else 0, "recent": list(rec)[-8:],
            "mailbox": ownermsg.counts(self.cfg["state_dir"], h),
        }

    def agents(self, sessions, slow, now_ts):
        by_cli = {s.get("cliSessionId"): s for s in sessions if s.get("cliSessionId")}
        names = {}
        for a in self.cfg["accounts"]:
            for sid, n in (a.get("session_names") or {}).items():
                for s in sessions:
                    if s.get("sessionId") == sid:
                        names[s.get("cliSessionId")] = n
            if a["kind"] == "helper":
                names[a["id"]] = a["name"]
        out = []
        for parent, meta, last, model, effort, age in slow["agents"]:
            ps = by_cli.get(parent) or {}
            err_at = al._ms(ps.get("errorAt"))
            limited = bool(ps.get("error") and "limit" in ps["error"].lower() and err_at and err_at.timestamp() >= now_ts - age)
            st = al.subagent_state(meta, last, age, limited)
            if st:
                title = ps.get("title") if isinstance(ps.get("title"), str) else ""
                out.append({"parent": names.get(parent) or title or "Other chat", "model_name": al.model_name(model or meta.get("model")),
                            "effort": effort, "state": st[0], "colour": st[1],
                            "task": runlog.one_line(meta.get("description") or meta.get("agentType") or "", 140),
                            "account": parent if parent in ("h1", "h2") else "main", "age_min": int(age // 60)})
        return sorted(out, key=lambda x: x["age_min"])

    def routines(self, sessions, now, now_ts):
        out = []
        for r in self.cfg["routines"]:
            runs = sorted((s for s in sessions if s.get("scheduledTaskId") == r["id"]), key=lambda s: int(s.get("createdAt") or 0))
            nxt = al.next_run(r.get("minutes", []), r.get("hours"), now) if r.get("minutes") else None
            item = {"id": r["id"], "name": r["name"], "next": nxt.isoformat(timespec="minutes") if nxt else None}
            if not runs:
                out.append({**item, "last": None, "result": "no run yet", "colour": "gray"})
                continue
            s = runs[-1]
            age = al.transcript_age(s.get("cliSessionId"), now_ts)
            if s.get("error"):
                res, col = ("Failed: usage limit" if "limit" in s["error"].lower() else "Failed"), "red"
            elif age is not None and age <= self.th["working_seconds"]:
                res, col = "Running", "green"
            else:
                res, col = "Done", "green"
            out.append({**item, "last": ms_iso(s.get("createdAt")), "result": res, "colour": col,
                        "detail": runlog.one_line((s.get("postTurnSummary") or {}).get("status_detail"), 200)})
        return out

    def goal(self, slow):
        tag, ahead = slow["git"]
        g = self.cfg.get("goal") or {}
        return {"text": g.get("text"), "tag": g.get("tag"), "reached": tag == g.get("tag"), "last_tag": tag,
                "unpushed": ahead}


def board_id(ref, board_ids):
    """'S6b-r3' -> 'S6b': the longest BOARD id that the reference starts with."""
    ids = {i.lower(): i for i in board_ids}
    parts = ref.split("-")
    for n in range(len(parts), 0, -1):
        hit = ids.get("-".join(parts[:n]).lower())
        if hit:
            return hit
    return None


def alerts(snap, th):
    """Plain-language list of what needs attention, most serious first. Pure (only reads the snapshot)."""
    out = []
    def add(level, who, text, action=""):
        out.append({"level": level, "who": who, "text": text, "action": action})
    for a in snap["accounts"]:
        code = a["status"]["code"]
        if code in ("ERROR", "STALLED", "DISCONNECTED"):
            add("red", a["name"], f"{a['status']['label']}: {a['status']['reason']}",
                "Open its terminal to see the run, then decide; nothing is stopped automatically.")
        elif code == "WAITING_INPUT":
            add("amber", a["name"], a["status"]["reason"], "Answer in its card or its terminal.")
        if not a["connection"]["ok"] and a["connection"].get("signed_in") is not None:
            add("red", a["name"], f"Account check failed: {a['connection']['detail']}",
                "Sign this profile in with its own seat (see README, troubleshooting).")
        c = a["context"]
        if c.get("level") == "danger":
            add("amber", a["name"], f"Context {c['percent']}% full ({c['tokens']:,} of {c['window']:,} tokens).",
                "Expect an automatic compaction soon; long sessions lose detail when that happens.")
        for s in a.get("sessions") or []:
            if s["status"]["code"] in ("ERROR",) and s["id"] != (a["session"] or {}).get("id"):
                add("red", a["name"], f"{s['name']}: {s['status']['reason']}")
    for t in snap["tasks"]:
        if t["display"] in ("Blocked",):
            add("amber", t["id"], f"{t['id']} — {t['title']}: blocked. {t['blocker']}")
    ram = snap["pc"].get("ram")
    if ram and ram >= 85:
        add("amber", "PC", f"RAM {ram}%: new heavy jobs wait until it is under 85%.")
    for r in snap["routines"]:
        if r["colour"] == "red":
            add("amber", "Routine", f"{r['name']}: {r['result']} (last run {r['last'] or '?'}).")
    for q in snap["needs_you"]:
        if not re.search(r"Optional|only when|only matters", q, re.I):
            add("amber", "You", q)
    if snap["sources"]["slow"]["errors"]:
        add("gray", "Monitor", "Some sources failed: " + ", ".join(snap["sources"]["slow"]["errors"]))
    rank = {"red": 0, "amber": 1, "gray": 2}
    return sorted(out, key=lambda x: rank[x["level"]])
