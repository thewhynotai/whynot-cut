"""OPS-01: deterministic project status for the WhyNot Cut Command Center (no AI tokens).

Reads BOARD, cards, intake state, helper loops, git and the API budget file, then (with --write) writes
TASK_QUEUE.yaml, a dated Arabic report, a PRIMARY inbox entry and the auto block of PROJECT_PLAN_AR.md; with --sync it
also mirrors 00-HQ to the branch ops/hq and verifies the remote SHA.

  python -X utf8 hq_status.py                      # print the Arabic report, write nothing
  python -X utf8 hq_status.py --write --sync       # what the scheduled report task runs
"""
import argparse, ctypes, datetime, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

HQ = Path(__file__).resolve().parent.parent
EP = HQ.parent
REPO = EP / "WhyNotCut"
ACCOUNTS = Path(r"D:\ClaudeData\accounts")
API_DIR = Path(r"D:\ClaudeData\claude-api-lane")
OPS_WT = Path(r"D:\WNC-work\ops")
SEATS = {"h1": "mayar@", "h2": "marketing@"}  # helper seat -> Claude account (Start-Helper.cmd profiles)
START, END = "<!-- AUTO:STATUS START -->", "<!-- AUTO:STATUS END -->"
# Task lifecycle (AI-infra restart Phase 5); BOARD keeps its own words (the helper loops read them), mapped here.
LIFECYCLE = ("BACKLOG", "READY", "IN_PROGRESS", "IN_REVIEW", "IN_TESTING", "DONE", "ARCHIVED")
CHARTER = {"NOT READY": "BACKLOG", "READY": "READY", "IN PROGRESS": "IN_PROGRESS", "FIX": "IN_PROGRESS",
           "BLOCKED": "BLOCKED", "PARKED": "BLOCKED", "ACCEPTED": "IN_TESTING", "MERGED": "DONE",
           "RUNNING": "IN_PROGRESS", "STOPPED": "BLOCKED", "DONE": "IN_REVIEW", "IN_PROGRESS": "IN_PROGRESS",
           "IN_REVIEW": "IN_REVIEW", "IN_TESTING": "IN_TESTING", "DONE_ARCHIVED": "ARCHIVED", "ARCHIVED": "ARCHIVED",
           "BACKLOG": "BACKLOG", "PLANNED_NOT_AUTHORIZED": "BACKLOG"}
SLOTS = {9: "تقرير الصبح", 13: "تقرير الضهر", 17: "تقرير العصر", 21: "تقرير الليل"}


# ----------------------------------------------------------------------------------------------------- readers
def parse_board(text):
    """Rows of the BOARD task table (the one whose header starts with `| ID |`)."""
    rows, in_table = [], False
    for line in text.splitlines():
        if line.startswith("| ID |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) >= 5:
                status = re.split(r"\s+[·—–]\s+|\s+\(", c[3].replace("**", ""))[0].strip()
                rows.append({"id": c[0], "title": c[1], "owner": c[2], "status": status,
                             "status_note": c[3], "card": c[4].strip("`").strip() if c[4] not in ("—", "") else ""})
            continue
        in_table = False
    return rows


def charter_status(word):
    return CHARTER.get(word.strip().upper(), "UNKNOWN")


def helper_state(accounts, who):
    auto = Path(accounts, who, "auto")
    try:
        st = json.loads((auto / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {"state": "missing"}
    beat = ""  # heartbeat = last write to the current run log (status.json only changes with the state)
    log = st.get("log")
    if log and os.path.exists(log):
        beat = datetime.datetime.fromtimestamp(os.path.getmtime(log)).strftime("%Y-%m-%d %H:%M:%S")
    return {"who": who, "state": st.get("state", "?"), "at": st.get("at", ""), "beat": beat, "model": st.get("model", ""),
            "reason": st.get("reason", ""), "auto_on": (auto / "AUTO-ON").exists(), "stop": (auto / "STOP").exists()}


def beat_age_min(h, now=None):
    t = h.get("beat") or h.get("at")
    try:
        return int(((now or datetime.datetime.now()) - datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
    except (TypeError, ValueError):
        return None


def sync_label(local, remote, ahead, behind):
    if remote is None:
        return "REMOTE_UNREACHABLE"
    if local == remote:
        return "SYNCED"
    if ahead is None:
        return "REMOTE_MOVED (not fetched here)"
    if ahead and behind:
        return "DIVERGED"
    if ahead:
        return f"LOCAL_AHEAD {ahead}"
    if behind:
        return f"REMOTE_AHEAD {behind}"
    return "DIVERGED"


def _git(cwd, *a, timeout=60):
    try:
        r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _remote_tip(cwd, branch, pause=5):
    """ls-remote, asked twice: this PC's DNS sometimes fails one lookup of github.com and answers the next
    (2026-10-23 05:30: 'Could not resolve host' between two good calls), which painted REMOTE_UNREACHABLE."""
    for attempt in (1, 2):
        out = _git(cwd, "ls-remote", "origin", f"refs/heads/{branch}", timeout=90)
        if out:
            return out.split()[0]
        if attempt == 1:
            time.sleep(pause)
    return None


def git_state(repo, branch="release/3.0"):
    """Read-only: local tip, remote tip (ls-remote, live), ahead/behind against the last fetched origin ref."""
    local = _git(repo, "rev-parse", branch)
    remote = _remote_tip(repo, branch)
    ahead = behind = 0
    if local and remote:
        counts = _git(repo, "rev-list", "--left-right", "--count", f"{local}...{remote}")
        if counts:
            ahead, behind = (int(x) for x in counts.split())
        else:  # the remote tip is not fetched here: no count can be known
            ahead = behind = None
    dirty = _git(repo, "--no-optional-locks", "status", "--porcelain")
    return {"branch": branch, "local": local, "remote": remote, "ahead": ahead, "behind": behind,
            "label": sync_label(local, remote, ahead, behind), "dirty_files": len(dirty.splitlines()) if dirty else 0}


def api_state(budget_md):
    try:
        t = Path(budget_md).read_text(encoding="utf-8")
    except OSError:
        return "UNKNOWN"
    m = re.search(r"API-500[^|\n]*\|\s*\*\*([A-Z_]+)\*\*", t)
    return m.group(1) if m else "UNKNOWN"


def api_month_estimate(api_dir):
    try:
        st = json.loads(Path(api_dir, "budget_status.json").read_text(encoding="utf-8"))
        return {"month": st.get("month"), "spent_est": st.get("spent_est"), "left_est": st.get("left_est"),
                "mode": st.get("mode"), "time": st.get("time")}
    except (OSError, ValueError):
        return {}


PREVIEW_DIR = Path(r"D:\ClaudeData\release-preview")
PREVIEW_LABEL = EP / "خد دا كوبي للويندوز" / "LABEL.txt"
WNC_QUEUE = REPO / "tools" / "wnc-queue"


def preview_label(path):
    try:
        t = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {}
    return {k: v.strip() for k, v in re.findall(r"^(label|commit|date):\s*(.+)$", t, re.M)}


def should_queue_refresh(check_exit, locked, jobs):
    """OPS-03 (was lane-watch 0f): queue one zero-token rebuild only when the folders are behind origin (exit 10),
    no refresh holds the lock, the queue state is known (`wnc-queue list --json` rows) and no refresh waits or runs."""
    if check_exit != 10 or locked or jobs is None:
        return False
    return not any(j.get("title") == "release preview refresh" and j.get("state") != "done" for j in jobs)


def refresh_failure(log):
    """The refresher's last log line when it says FAILED (lane-watch 0f reported it), else ''."""
    try:
        lines = [l for l in Path(log).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    except OSError:
        return ""
    return lines[-1][:300] if lines and "FAILED" in lines[-1] else ""


def _run(cmd, timeout):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None


def preview_state(queue=False):
    """Check the «خد دا كوبي» folders against origin/release/3.0 (refresh.py --check) and optionally queue one
    rebuild through wnc-queue. Never builds here; never raises."""
    st = {"label": preview_label(PREVIEW_LABEL), "check": None, "queued": False,
          "failed": refresh_failure(PREVIEW_DIR / "refresh.log")}
    r = _run([sys.executable, "-X", "utf8", str(PREVIEW_DIR / "refresh.py"), "--check"], 180)
    if r is None:
        return st
    st["check"] = r.returncode
    if queue and r.returncode == 10:
        ls = _run(["bash", str(WNC_QUEUE), "list", "--owner", "release", "--json"], 60)
        try:
            jobs = json.loads(ls.stdout) if ls is not None and ls.returncode == 0 else None
        except ValueError:
            jobs = None
        if should_queue_refresh(st["check"], (PREVIEW_DIR / "refresh.lock").exists(), jobs):
            q = _run(["bash", str(WNC_QUEUE), "add", "--title", "release preview refresh", "--class", "none",
                      "--timeout", "6h", "--owner", "release", "--cwd", str(PREVIEW_DIR), "--", "python", "-X", "utf8",
                      str(PREVIEW_DIR / "refresh.py")], 60)
            st["queued"] = q is not None and q.returncode == 0
    return st


def ram_percent():
    if os.name != "nt":
        return None

    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in
                                                                       ("a", "b", "c", "d", "e", "f", "g")]
    m = MS()
    m.l = ctypes.sizeof(MS)
    return m.load if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None


def intake_verdicts(hq):
    """{report path (as intake/state.json keys it): {verdict, at}}."""
    try:
        st = json.loads(Path(hq, "intake", "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k.replace("\\", "/"): {"verdict": v.get("verdict", ""), "at": v.get("at", "")} for k, v in st.items()}


def report_verdict(hq, rep):
    """The intake verdict of exactly this report file ('' when the intake has not recorded it)."""
    return intake_verdicts(hq).get(rep.get("file", ""), {}).get("verdict", "") if rep else ""


def open_requests(inbox):
    try:
        t = Path(inbox).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in t.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 5 and re.fullmatch(r"Q-\d+", c[0]) and c[4].upper().startswith("OPEN"):
            out.append(f"{c[0]} — {c[2]}")
    return out


def inbox_reports(hq):
    """Newest report per task from inbox/h1|h2 with its Status word."""
    out = {}
    for who in ("h1", "h2"):
        for f in sorted(Path(hq, "inbox", who).glob("*.md")):
            m = re.match(r"\d{4}-\d{2}-\d{2}-(?:\d{4}-)?(.+?)(?:-r\d+)?\.md$", f.name)  # H2 names carry HHMM
            if not m:
                continue
            head = f.read_text(encoding="utf-8", errors="replace")[:2000]
            s = re.search(r"\*\*Status:\*\*\s*([A-Z]+)", head)
            prev = out.get(m.group(1))
            if prev is None or f.stat().st_mtime >= prev["mtime"]:
                out[m.group(1)] = {"who": who, "file": f"inbox/{who}/{f.name}", "status": s.group(1) if s else "?",
                                   "mtime": f.stat().st_mtime}
    return out


def current_milestone(plan_md):
    """First milestone of PROJECT_PLAN_AR.md §3 not yet ticked '[x]' ('' if none or no file)."""
    try:
        t = Path(plan_md).read_text(encoding="utf-8")
    except (OSError, ValueError):  # a missing or mis-saved plan must not stop the scheduled report
        return ""
    m = re.search(r"^- \[ \] \*\*(M\d+ — .+?)\*\*", t, re.M)
    return m.group(1) if m else ""


# ----------------------------------------------------------------------------------------------------- writers
def status_changes(prev, now):
    if not prev:
        return []
    a, b = prev.get("tasks", {}), now.get("tasks", {})
    return [(k, a.get(k), b[k]) for k in b if a.get(k) != b[k]] + [(k, a[k], None) for k in a if k not in b]


def _read(p):
    with open(p, encoding="utf-8", newline="") as fh:  # keep the file's own line endings
        return fh.read()


def _write(p, text):
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def replace_block(text, block):
    i, j = text.find(START), text.find(END)
    if i < 0 or j < 0 or j < i:
        raise ValueError("auto-status markers missing in PROJECT_PLAN_AR.md")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text[:i + len(START)] + nl + block.rstrip("\n").replace("\n", nl) + nl + text[j:]


def write_block(path, block):
    _write(path, replace_block(_read(path), block))


def append_inbox(path, msg_id, summary, link):
    p = Path(path)
    t = _read(p) if p.exists() else "# PRIMARY_ACCOUNT_INBOX\n"
    if f"| {msg_id} |" in t:
        return False
    nl = "\r\n" if "\r\n" in t else "\n"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    row = f"| {msg_id} | {now} | hq_status | PRIMARY | FILED | {summary} | `{link}` |{nl}"
    _write(p, t + ("" if t.endswith("\n") else nl) + row)
    return True


def mark_sent(path, msg_id, session_id):
    """FILED → SENT on exactly one inbox row; the session id of the delivering run is the receipt."""
    t = _read(path)
    lines = t.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith(f"| {msg_id} |") and "| FILED |" in line:
            lines[i] = line.replace("| FILED |", f"| SENT (session {session_id}) |", 1)
            _write(path, "".join(lines))
            return True
    return False


def _q(v):
    return json.dumps("" if v is None else str(v), ensure_ascii=False)


def render_queue_yaml(rows, verdicts, stamp, reports=None):
    """verdicts: {report path: {verdict}} (intake_verdicts); a task's verdict is its newest report's own one."""
    reports = reports or {}
    out = [f"# GENERATED by 00-HQ/tools/hq_status.py at {stamp}. Do not edit: the source is BOARD.md + tasks/ + "
           "intake/state.json + inbox/.", "tasks:"]
    for r in rows:
        rep = reports.get(r["id"], {})
        owner = (r["owner"].split() or [""])[0]
        out += [f"  - task_id: {_q(r['id'])}", f"    title: {_q(r['title'])}", f"    owner: {_q(r['owner'])}",
                f"    status: {_q(r['status'])}", f"    charter_status: {_q(charter_status(r['status']))}",
                f"    status_note: {_q(r['status_note'])}", f"    card: {_q(r['card'])}",
                f"    worktree: {_q({'H1': 'D:/WNC-work/h1', 'H2': 'D:/WNC-work/h2'}.get(owner, ''))}",
                f"    latest_report: {_q(rep.get('file'))}", f"    report_status: {_q(rep.get('status'))}",
                f"    intake_verdict: {_q(verdicts.get(rep.get('file', ''), {}).get('verdict'))}"]
    return "\n".join(out) + "\n"


MAX_MIRROR_BYTES = 1_000_000  # no large artefacts in the mirror


def sync_mirror(worktree, files, message, branch="ops/hq"):
    """Copy files (dest-relative path -> source) into the worktree, drop mirrored files that no longer exist, commit
    if changed, push ONLY `branch`, verify the remote SHA. Never raises: failures come back as the state."""
    wt = Path(worktree)
    res = {"state": "PUSH_FAILED", "local": None, "remote": None, "committed": False, "error": ""}
    if _git(wt, "symbolic-ref", "--short", "HEAD") != branch:  # shares .git with the product repo: never another branch
        res.update(state="WRONG_BRANCH", error=f"worktree {wt} is not on {branch}")
        return res
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        for rel, src in files.items():
            dst = wt / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        ls = subprocess.run(["git", "-C", str(wt), "-c", "core.quotepath=off", "ls-files", "-z"],
                            capture_output=True, check=True, env=env).stdout.decode("utf-8")
        gone = [t for t in ls.split("\0") if t and t not in files]
        if gone:
            subprocess.run(["git", "-C", str(wt), "rm", "-q", "-f", "--", *gone], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(wt), "add", "--", *files.keys()], check=True, capture_output=True, env=env)
        res["committed"] = subprocess.run(["git", "-C", str(wt), "diff", "--cached", "--quiet"]).returncode != 0
        if res["committed"]:
            subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", message], check=True, capture_output=True, env=env)
        res["local"] = _git(wt, "rev-parse", "HEAD")
        push = subprocess.run(["git", "-C", str(wt), "push", "-q", "origin", f"HEAD:refs/heads/{branch}"],
                              capture_output=True, text=True, timeout=180, env=env)
        if push.returncode != 0:
            res["error"] = push.stderr.strip()[-300:]
            return res
        res["remote"] = _remote_tip(wt, branch)
        res["state"] = "SYNCED" if res["remote"] and res["remote"] == res["local"] else "PUSH_FAILED"
    except (subprocess.SubprocessError, OSError) as e:
        err = getattr(e, "stderr", b"") or b""
        err = err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
        res["error"] = f"{type(e).__name__}: {e} {err.strip()}"[-300:]
    return res


def mirror_files(hq, ep):
    skip_dirs = {"intake", "__pycache__"}
    files = {}
    for p in Path(hq).rglob("*"):
        rel = p.relative_to(hq)
        if p.is_file() and not (set(rel.parts) & skip_dirs) and p.stat().st_size <= MAX_MIRROR_BYTES \
                and p.suffix in (".md", ".py", ".yaml", ".jsonl", ".txt", ".patch"):
            files[f"00-HQ/{rel.as_posix()}"] = p
    for name in ("PROJECT_PLAN_AR.md", "CLAUDE.md"):
        files[name] = Path(ep, name)
    return files


# ----------------------------------------------------------------------------------------------------- report
def snapshot(hq=HQ, repo=REPO, accounts=ACCOUNTS, api_dir=API_DIR):
    rows = parse_board(Path(hq, "BOARD.md").read_text(encoding="utf-8"))
    return {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "rows": rows,
            "tasks": {r["id"]: r["status"] for r in rows}, "verdicts": intake_verdicts(hq), "reports": inbox_reports(hq),
            "helpers": [helper_state(accounts, h) for h in ("h1", "h2")], "git": git_state(repo),
            "tag": _git(repo, "describe", "--tags", "--abbrev=0", "release/3.0"),
            "api": api_state(Path(hq, "BUDGET-API.md")), "api_month": api_month_estimate(api_dir), "ram": ram_percent(),
            "requests": open_requests(Path(hq, "PRIMARY_ACCOUNT_INBOX.md")),
            "milestone": current_milestone(Path(hq).parent / "PROJECT_PLAN_AR.md")}


def preview_line(p):
    if not p:
        return "- فولدرات «خد دا كوبي»: مش متشيّكة في التشغيل ده."
    lab = p.get("label", {})
    state = {0: "متحدّثة مع GitHub", 10: "متأخرة عن GitHub"}.get(p.get("check"), "الفحص ما اشتغلش")
    return (f"- فولدرات «خد دا كوبي» (المصدر LABEL.txt + refresh.py --check): {lab.get('label', '—')} @ "
            f"{lab.get('commit', '—')[:8]} ({lab.get('date', '—')}) — {state}"
            + (" — **اتحط rebuild في الطابور**" if p.get("queued") else ""))


STALE_MIN = 330  # a run silent this long is killed by helper_loop (5 h 10 min + slack)


def render_report(s, prev, slot_title, sync=None):
    g, ch = s["git"], status_changes(prev, s)
    L = [f"# {slot_title} — {s['time']} (Africa/Cairo)", "",
         "> مولّد أوتوماتيك من الملفات و git (مش من كلام أي session). المصدر مكتوب جنب كل معلومة.", "",
         "## 1. اللي اتعمل من آخر تقرير"]
    if prev is None:
        L.append("- أول تقرير: مفيش تقرير قبله للمقارنة.")
    else:
        L += [f"- {k}: {a or 'جديد'} ← **{b or 'اتشال من الـ BOARD'}**" for k, a, b in ch] \
            or ["- مفيش تغيير في حالة أي تاسك على الـ BOARD."]
        try:  # same minute as the last report counts again: a repeat beats a missed handoff
            since = datetime.datetime.strptime(prev.get("time", ""), "%Y-%m-%d %H:%M").timestamp()
        except (ValueError, TypeError):
            since = None
        if since is None:
            L.append("- التسليمات الجديدة: مش معروفة (وقت آخر تقرير مش مقروء من `.last-snapshot.json`).")
        else:
            new = sorted((v["mtime"], k, v) for k, v in s["reports"].items() if v["mtime"] >= since)
            L += [f"- تسليم جديد (inbox): {k} ({v['status']}) من {v['who'].upper()}: `{v['file']}`" for _, k, v in new] \
                or ["- مفيش تسليم جديد في الـ inbox من آخر تقرير."]
    L += ["", "## 2. شغالين على إيه (المصدر: helper status.json + آخر كتابة في run log)",
          "- PRIMARY (info@): الماستر (استلام ومراجعة وقبول في 00-HQ) + الـ executor (الـ merge على release/3.0) + "
          "الـ routines (المصدر `AGENT_ROUTING_RULES.md`)."]
    for h in s.get("helpers", []):
        flags = ("AUTO-ON" if h["auto_on"] else "AUTO off") + (" · STOP" if h["stop"] else "")
        age = beat_age_min(h)
        state = h["state"] + (" (STALE)" if h["state"] == "running" and age is not None and age > STALE_MIN else "")
        age_txt = "—" if age is None else f"{age} دقيقة"
        L.append(f"- {h['who'].upper()} ({SEATS.get(h['who'], '—')}): {state} — آخر heartbeat {h.get('beat') or h['at'] or '—'}"
                 f" ({age_txt}), {h['model'] or '—'}, {flags} {h['reason']}".rstrip())
    L += [f"- {r['id']} — {r['owner']} — {r['status']}" for r in s["rows"]
          if charter_status(r["status"]) in ("IN_PROGRESS", "IN_REVIEW", "IN_TESTING")]
    tag, prev_tag = s.get("tag"), (prev or {}).get("tag")
    new_tag = bool(prev_tag and tag and tag != prev_tag)  # no earlier tag on record = nothing to compare
    L += ["", "## 3. حالة المنتج (المصدر: git tags + `PROJECT_PLAN_AR.md` §5)",
          f"- الـ milestone الحالي (`PROJECT_PLAN_AR.md` §3، أول واحد مش مقفول): "
          f"**{s.get('milestone') or 'مش متحدد (مفيش milestone مفتوح أو الملف مش مقروء)'}**",
          f"- آخر tag على release/3.0: {tag or '—'}"
          + (" — **tag جديد من آخر تقرير** (محتاج تأكيد التجربة في Premiere قبل ما يتسمّى verified)"
             if new_tag else " — **NO NEW VERIFIED BUILD**"),
          "- آخر نسخة متجرّبة جوه Premiere وجدول النسخ: `PROJECT_PLAN_AR.md` §5 (بيتحدّث مع كل release متجرّبة).",
          preview_line(s.get("preview")),
          "", "## 4. حالة Git (المصدر: git rev-parse + ls-remote)",
          f"- `{g['branch']}` محلي {(g['local'] or '—')[:8]} / GitHub {(g['remote'] or '—')[:8]} → **{g['label']}** "
          f"(ملفات مش متعملها commit في شجرة الـ executor: {g['dirty_files']})"]
    if sync:
        L.append(f"- مرآة الـ HQ (`ops/hq`) قبل كتابة التقرير ده: **{sync['state']}** {(sync['local'] or '')[:8]}"
                 + (f" — {sync['error']}" if sync.get("error") else ""))
    L += ["", "## 5. الأخطاء والعوائق"]
    n = len(L)
    L += [f"- {r['id']}: {r['status_note']}" for r in s["rows"] if charter_status(r["status"]) == "BLOCKED"]
    L += [f"- {r['id']}: حالة مش مفهومة على الـ BOARD «{r['status_note']}»" for r in s["rows"]
          if charter_status(r["status"]) == "UNKNOWN"]
    for k, v in s["reports"].items():
        verdict = (s["verdicts"].get(v["file"], {}).get("verdict") or "").strip()
        if v["status"] in ("DONE", "BLOCKED") and verdict.split(" ")[0] not in ("ACCEPTED", "FIX", "answered", "noted"):
            extra = f" (intake: {verdict})" if verdict else ""
            L.append(f"- تقرير {k} ({v['status']}) من {v['who'].upper()} مستني الاستلام{extra}: `{v['file']}`")
    if (s.get("preview") or {}).get("failed"):
        L.append(f"- آخر rebuild لفولدرات «خد دا كوبي» فشل (refresh.log): {s['preview']['failed']}")
    if s["ram"] is not None and s["ram"] >= 85:
        L.append(f"- RAM {s['ram']}%: مفيش heavy job جديد يبدأ (الفرامل 85%).")
    if len(L) == n:
        L.append("- مفيش.")
    L += ["", "## 6. المطلوب من PRIMARY (المصدر: `00-HQ/PRIMARY_ACCOUNT_INBOX.md`، الطلبات OPEN)"]
    L += [f"- {q}" for q in s.get("requests", [])] or ["- لا يوجد."]
    L += ["", "## 7. الخطوات التالية (المصدر: BOARD، الكروت READY بالترتيب)"]
    ready = [r for r in s["rows"] if charter_status(r["status"]) == "READY"]
    L += [f"- {r['id']} — {r['owner']} — {r['title']}" for r in ready[:8]] or ["- مفيش كروت READY: الـ intake يملا الطابور."]
    m = s["api_month"]
    spend = ("مفيش صرف مسموح عليها لحد التفعيل" if s["api"] == "PLANNED_NOT_AUTHORIZED"
             else "الصرف الفعلي في الـ ledger جوه `BUDGET-API.md`")
    L += ["", "## 8. الـ API",
          f"- خطة الـ 500$: **{s['api']}** (المصدر `00-HQ/BUDGET-API.md`) — {spend}.",
          f"- الشهر الحالي (تقدير الـ lanes في budget_status.json، مش الـ Console): صرف {m.get('spent_est', '—')}"
          f" / باقي {m.get('left_est', '—')} — {m.get('mode', '—')} ({m.get('time', '—')})",
          "", f"RAM الآن: {s['ram'] if s['ram'] is not None else '—'}%"]
    return "\n".join(L) + "\n"


def plan_block(s, sync=None):
    g = s["git"]
    run = "RUNNING" if any(h["state"] == "running" for h in s["helpers"]) else "IDLE"
    sync_txt = ("UNVERIFIED" if not sync else "LOCAL+GITHUB_VERIFIED" if sync["state"] == "SYNCED"
                else f"LOCAL_ONLY ({sync['state']})")
    rows = "\n".join(f"| {r['id']} | {r['owner']} | {r['status']} |" for r in s["rows"])
    return (f"> آخر تحديث فعلي: {s['time']} — Africa/Cairo\n"
            f"> مصدر التحديث: hq_status.py / info@ / release/3.0 @ {(g['local'] or '—')[:8]}\n"
            f"> حالة التشغيل: {run}\n"
            f"> حالة المزامنة: HQ = {sync_txt} · release/3.0 = {g['label']}\n\n"
            f"| Task | Owner | Status (BOARD) |\n|---|---|---|\n{rows}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--mark-sent", nargs=2, metavar=("REPORT_ID", "SESSION_ID"))
    a = ap.parse_args(argv)
    inbox = Path(HQ, "PRIMARY_ACCOUNT_INBOX.md")
    if a.mark_sent:
        ok = mark_sent(inbox, *a.mark_sent)
        if ok:
            sync = sync_mirror(OPS_WT, mirror_files(HQ, EP), f"ops: {a.mark_sent[0]} SENT")
            print(f"{a.mark_sent[0]}: SENT · ops/hq {sync['state']}")
        else:
            print(f"{a.mark_sent[0]}: no FILED row found")
        return 0 if ok else 4
    s = snapshot()
    s["preview"] = preview_state(queue=a.write)
    last = Path(HQ, "reports", ".last-snapshot.json")
    prev = json.loads(last.read_text(encoding="utf-8")) if last.exists() else None
    slot = SLOTS.get(datetime.datetime.now().hour, "تقرير حالة")
    if not a.write:
        print(render_report(s, prev, slot))
        return 0
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    rid, rep_rel = f"R-{stamp}", f"reports/{stamp}.md"
    _write(Path(HQ, "TASK_QUEUE.yaml"), render_queue_yaml(s["rows"], s["verdicts"], s["time"], s["reports"]))
    sync = sync_mirror(OPS_WT, mirror_files(HQ, EP), f"ops: HQ snapshot {stamp}") if a.sync else None
    rep = Path(HQ, rep_rel)
    _write(rep, render_report(s, prev, slot, sync))
    write_block(Path(EP, "PROJECT_PLAN_AR.md"), plan_block(s, sync))
    append_inbox(inbox, rid, f"{slot}: {len(status_changes(prev, s))} تغيير", rep_rel)
    _write(last, json.dumps({"time": s["time"], "tasks": s["tasks"], "tag": s["tag"]}, ensure_ascii=False))
    if a.sync:  # second pass: the report, plan block and inbox row themselves
        sync2 = sync_mirror(OPS_WT, mirror_files(HQ, EP), f"ops: HQ report {stamp}")
        if sync2["state"] != "SYNCED":  # never leave a "verified" claim that the second push did not earn
            _write(rep, _read(rep) + f"\n- تحديث: push التقرير نفسه فشل ({sync2['state']}) → LOCAL_ONLY. {sync2['error']}\n")
            write_block(Path(EP, "PROJECT_PLAN_AR.md"), plan_block(s, sync2))
        sync = sync2
    print(_read(rep))
    print(f"report id: {rid}")
    if sync:
        print(f"ops/hq: {sync['state']} local={sync['local']} remote={sync['remote']} {sync['error']}")
    return 0 if not sync or sync["state"] == "SYNCED" else 3


if __name__ == "__main__":
    sys.exit(main())
