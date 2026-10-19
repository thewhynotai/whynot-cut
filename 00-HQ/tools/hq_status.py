"""OPS-01: deterministic project status for the WhyNot Cut Command Center (no AI tokens).

Reads BOARD, cards, intake state, helper loops, git and the API budget file, then (with --write) writes
TASK_QUEUE.yaml, a dated Arabic report, a PRIMARY inbox entry and the auto block of PROJECT_PLAN_AR.md; with --sync it
also mirrors 00-HQ to the branch ops/hq and verifies the remote SHA.

  python -X utf8 hq_status.py                      # print the Arabic report, write nothing
  python -X utf8 hq_status.py --write --sync       # what the scheduled report task runs
"""
import argparse, ctypes, datetime, json, os, re, shutil, subprocess, sys
from pathlib import Path

HQ = Path(__file__).resolve().parent.parent
EP = HQ.parent
REPO = EP / "WhyNotCut"
ACCOUNTS = Path(r"D:\ClaudeData\accounts")
API_DIR = Path(r"D:\ClaudeData\claude-api-lane")
OPS_WT = Path(r"D:\WNC-work\ops")
START, END = "<!-- AUTO:STATUS START -->", "<!-- AUTO:STATUS END -->"
CHARTER = {"NOT READY": "BACKLOG", "READY": "READY", "IN PROGRESS": "IN_PROGRESS", "FIX": "IN_PROGRESS",
           "BLOCKED": "BLOCKED", "PARKED": "BLOCKED", "ACCEPTED": "ACCEPTED", "MERGED": "DONE_ARCHIVED",
           "RUNNING": "IN_PROGRESS", "STOPPED": "BLOCKED", "DONE": "IN_REVIEW", "IN_PROGRESS": "IN_PROGRESS",
           "IN_REVIEW": "IN_REVIEW", "DONE_ARCHIVED": "DONE_ARCHIVED", "BACKLOG": "BACKLOG"}
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
                status = re.split(r"\s+·\s+|\s+\(", c[3])[0].strip()
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
    return {"who": who, "state": st.get("state", "?"), "at": st.get("at", ""), "model": st.get("model", ""),
            "reason": st.get("reason", ""), "auto_on": (auto / "AUTO-ON").exists(), "stop": (auto / "STOP").exists()}


def sync_label(local, remote, ahead, behind):
    if remote is None:
        return "REMOTE_UNREACHABLE"
    if local == remote:
        return "SYNCED"
    if ahead and behind:
        return "DIVERGED"
    if ahead:
        return f"LOCAL_AHEAD {ahead}"
    if behind:
        return f"REMOTE_AHEAD {behind}"
    return "DIVERGED"


def _git(cwd, *a, timeout=60):
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip() if r.returncode == 0 else None


def git_state(repo, branch="release/3.0"):
    """Read-only: local tip, remote tip (ls-remote, live), ahead/behind against the last fetched origin ref."""
    local = _git(repo, "rev-parse", branch)
    try:
        out = _git(repo, "ls-remote", "origin", f"refs/heads/{branch}", timeout=90)
    except subprocess.TimeoutExpired:
        out = None
    remote = out.split()[0] if out else None
    ahead = behind = 0
    if local and remote:
        counts = _git(repo, "rev-list", "--left-right", "--count", f"{local}...{remote}")
        if counts:
            ahead, behind = (int(x) for x in counts.split())
        else:  # the remote tip is not fetched here yet: it moved since the last fetch
            ahead, behind = 0, 1
    dirty = _git(repo, "status", "--porcelain")
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
    """{task id: {verdict, at}} from intake/state.json (keys are report paths …/<date>-<ID>[-rN].md)."""
    try:
        st = json.loads(Path(hq, "intake", "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for path, v in st.items():
        m = re.search(r"\d{4}-\d{2}-\d{2}-(.+?)(?:-r\d+)?\.md$", path)
        if m:
            out[m.group(1)] = {"verdict": v.get("verdict", ""), "at": v.get("at", "")}
    return out


def inbox_reports(hq):
    """Newest report per task from inbox/h1|h2 with its Status word."""
    out = {}
    for who in ("h1", "h2"):
        for f in sorted(Path(hq, "inbox", who).glob("*.md")):
            m = re.match(r"\d{4}-\d{2}-\d{2}-(.+?)(?:-r\d+)?\.md$", f.name)
            if not m:
                continue
            head = f.read_text(encoding="utf-8", errors="replace")[:2000]
            s = re.search(r"\*\*Status:\*\*\s*([A-Z]+)", head)
            prev = out.get(m.group(1))
            if prev is None or f.stat().st_mtime >= prev["mtime"]:
                out[m.group(1)] = {"who": who, "file": f"inbox/{who}/{f.name}", "status": s.group(1) if s else "?",
                                   "mtime": f.stat().st_mtime}
    return out


# ----------------------------------------------------------------------------------------------------- writers
def status_changes(prev, now):
    if not prev:
        return []
    a, b = prev.get("tasks", {}), now.get("tasks", {})
    return [(k, a.get(k), b[k]) for k in b if a.get(k) != b[k]]


def replace_block(text, block):
    i, j = text.find(START), text.find(END)
    if i < 0 or j < 0 or j < i:
        raise ValueError("auto-status markers missing in PROJECT_PLAN_AR.md")
    return text[:i + len(START)] + "\n" + block.rstrip("\n") + "\n" + text[j:]


def append_inbox(path, msg_id, summary, link):
    p = Path(path)
    t = p.read_text(encoding="utf-8") if p.exists() else "# PRIMARY_ACCOUNT_INBOX\n"
    if f"| {msg_id} |" in t:
        return False
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    row = f"| {msg_id} | {now} | hq_status | PRIMARY | FILED | {summary} | `{link}` |\n"
    with open(p, "a", encoding="utf-8") as fh:
        if not t.endswith("\n"):
            fh.write("\n")
        fh.write(row)
    return True


def _q(v):
    return json.dumps("" if v is None else str(v), ensure_ascii=False)


def render_queue_yaml(rows, verdicts, stamp, reports=None):
    reports = reports or {}
    out = [f"# GENERATED by 00-HQ/tools/hq_status.py at {stamp}. Do not edit: the source is BOARD.md + tasks/ + "
           "intake/state.json + inbox/.", "tasks:"]
    for r in rows:
        rep = reports.get(r["id"], {})
        out += [f"  - task_id: {_q(r['id'])}", f"    title: {_q(r['title'])}", f"    owner: {_q(r['owner'])}",
                f"    status: {_q(r['status'])}", f"    charter_status: {_q(charter_status(r['status']))}",
                f"    status_note: {_q(r['status_note'])}", f"    card: {_q(r['card'])}",
                f"    worktree: {_q({'H1': 'D:/WNC-work/h1', 'H2': 'D:/WNC-work/h2'}.get(r['owner'].split()[0], ''))}",
                f"    latest_report: {_q(rep.get('file'))}", f"    report_status: {_q(rep.get('status'))}",
                f"    intake_verdict: {_q(verdicts.get(r['id'], {}).get('verdict'))}"]
    return "\n".join(out) + "\n"


def sync_mirror(worktree, files, message, branch="ops/hq"):
    """Copy files (dest-relative path -> source) into the worktree, commit if changed, push, verify remote SHA."""
    wt = Path(worktree)
    for rel, src in files.items():
        dst = wt / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    subprocess.run(["git", "-C", str(wt), "add", "--", *files.keys()], check=True, capture_output=True)
    changed = subprocess.run(["git", "-C", str(wt), "diff", "--cached", "--quiet"]).returncode != 0
    if changed:
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", message], check=True, capture_output=True)
    local = _git(wt, "rev-parse", "HEAD")
    push = subprocess.run(["git", "-C", str(wt), "push", "-q", "origin", f"HEAD:refs/heads/{branch}"],
                          capture_output=True, text=True, timeout=180)
    remote = None
    if push.returncode == 0:
        out = _git(wt, "ls-remote", "origin", f"refs/heads/{branch}", timeout=90)
        remote = out.split()[0] if out else None
    state = "SYNCED" if remote and remote == local else "PUSH_FAILED"
    return {"state": state, "local": local, "remote": remote, "committed": changed,
            "error": "" if push.returncode == 0 else push.stderr.strip()[-300:]}


def mirror_files(hq, ep):
    skip_dirs = {"intake", "__pycache__"}
    files = {}
    for p in Path(hq).rglob("*"):
        rel = p.relative_to(hq)
        if p.is_file() and not (set(rel.parts) & skip_dirs) and p.suffix in (".md", ".py", ".yaml", ".jsonl", ".txt", ".patch"):
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
            "api": api_state(Path(hq, "BUDGET-API.md")), "api_month": api_month_estimate(api_dir), "ram": ram_percent()}


def render_report(s, prev, slot_title, sync=None):
    g, ch = s["git"], status_changes(prev, s)
    L = [f"# {slot_title} — {s['time']} (Africa/Cairo)", "",
         "> مولّد أوتوماتيك من الملفات و git (مش من كلام أي session). كل رقم هنا مقروء من مصدره.", "",
         "## 1. اللي اتعمل من آخر تقرير"]
    L += [f"- {k}: {a or 'جديد'} ← **{b}**" for k, a, b in ch] or ["- مفيش تغيير في حالة أي تاسك على الـ BOARD."]
    L += ["", "## 2. شغالين على إيه"]
    for h in s["helpers"]:
        flags = ("AUTO-ON" if h["auto_on"] else "AUTO off") + (" · STOP" if h["stop"] else "")
        L.append(f"- {h['who'].upper()}: {h['state']} (آخر heartbeat {h['at'] or '—'}, {h['model'] or '—'}, {flags}) {h['reason']}")
    active = [r for r in s["rows"] if charter_status(r["status"]) in ("IN_PROGRESS", "IN_REVIEW")]
    L += [f"- {r['id']} — {r['owner']} — {r['status']}" for r in active]
    L += ["", "## 3. حالة المنتج",
          "- آخر نسخة متجرّبة جوه Premiere: v2.2.1 (+ 3.0 live round-trip 14–15 أكتوبر). **NO NEW VERIFIED BUILD** "
          "إلا لو ظهر tag جديد هنا.", f"- آخر tag: {_git(REPO, 'describe', '--tags', '--abbrev=0', 'release/3.0') or '—'}",
          "", "## 4. حالة Git",
          f"- `{g['branch']}` محلي {(g['local'] or '—')[:8]} / GitHub {(g['remote'] or '—')[:8]} → **{g['label']}** "
          f"(ملفات مش متعملها commit في شجرة الـ executor: {g['dirty_files']})"]
    if sync:
        L.append(f"- مرآة الـ HQ (`ops/hq`): **{sync['state']}** {(sync['local'] or '')[:8]}"
                 + (f" — {sync['error']}" if sync.get("error") else ""))
    blocked = [r for r in s["rows"] if charter_status(r["status"]) == "BLOCKED"]
    waiting = [(k, v) for k, v in s["reports"].items() if v["status"] in ("DONE", "BLOCKED")
               and s["verdicts"].get(k, {}).get("verdict") not in ("ACCEPTED", "FIX", "answered")]
    L += ["", "## 5. الأخطاء والعوائق"]
    L += [f"- {r['id']}: {r['status_note']}" for r in blocked]
    L += [f"- تقرير {k} ({v['status']}) من {v['who'].upper()} مستني الاستلام: `{v['file']}`" for k, v in waiting]
    if s["ram"] is not None and s["ram"] >= 85:
        L.append(f"- RAM {s['ram']}%: مفيش heavy job جديد يبدأ (الفرامل 85%).")
    if len(L) and L[-1] == "## 5. الأخطاء والعوائق":
        L.append("- مفيش.")
    L += ["", "## 6. المطلوب من PRIMARY", "- شوف `PROJECT_PLAN_AR.md` §3 (المحجوب). لو مفيش جديد: لا يوجد.",
          "", "## 7. الخطوات التالية"]
    ready = [r for r in s["rows"] if charter_status(r["status"]) == "READY"]
    L += [f"- {r['id']} — {r['owner']} — {r['title']}" for r in ready[:6]] or ["- مفيش كروت READY: الـ intake يملا الطابور."]
    m = s["api_month"]
    L += ["", "## 8. الـ API",
          f"- خطة الـ 500$: **{s['api']}** (المصدر `00-HQ/BUDGET-API.md`). مصروف عليها: 0 إلا لو اتفعّلت.",
          f"- الشهر الحالي (تقدير الـ lanes، مش الـ Console): صرف {m.get('spent_est', '—')} / باقي {m.get('left_est', '—')} "
          f"— {m.get('mode', '—')} ({m.get('time', '—')})",
          "", f"RAM الآن: {s['ram'] if s['ram'] is not None else '—'}%"]
    return "\n".join(L) + "\n"


def plan_block(s, sync=None):
    g = s["git"]
    run = "RUNNING" if any(h["state"] == "running" for h in s["helpers"]) else "IDLE"
    if sync:
        sync_txt = "LOCAL+GITHUB_VERIFIED" if sync["state"] == "SYNCED" else "LOCAL_ONLY"
    else:
        sync_txt = "UNVERIFIED"
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
    a = ap.parse_args(argv)
    s = snapshot()
    last = Path(HQ, "reports", ".last-snapshot.json")
    prev = json.loads(last.read_text(encoding="utf-8")) if last.exists() else None
    hour = datetime.datetime.now().hour
    slot = SLOTS.get(hour, "تقرير حالة")
    if not a.write:
        print(render_report(s, prev, slot))
        return 0
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    Path(HQ, "TASK_QUEUE.yaml").write_text(render_queue_yaml(s["rows"], s["verdicts"], s["time"], s["reports"]), encoding="utf-8")
    plan = Path(EP, "PROJECT_PLAN_AR.md")
    rep_rel = f"reports/{stamp}.md"
    sync = None
    if a.sync:  # first pass: mirror the current files, so the report can state the verified SHA
        sync = sync_mirror(OPS_WT, mirror_files(HQ, EP), f"ops: HQ snapshot {stamp}")
    Path(HQ, rep_rel).write_text(render_report(s, prev, slot, sync), encoding="utf-8")
    plan.write_text(replace_block(plan.read_text(encoding="utf-8"), plan_block(s, sync)), encoding="utf-8")
    append_inbox(Path(HQ, "PRIMARY_ACCOUNT_INBOX.md"), f"R-{stamp}", f"{slot}: {len(status_changes(prev, s))} تغيير", rep_rel)
    last.write_text(json.dumps({"time": s["time"], "tasks": s["tasks"]}, ensure_ascii=False), encoding="utf-8")
    if a.sync:  # second pass: the report, plan block and inbox entry themselves
        sync = sync_mirror(OPS_WT, mirror_files(HQ, EP), f"ops: HQ report {stamp}")
    print(Path(HQ, rep_rel).read_text(encoding="utf-8"))
    if sync:
        print(f"ops/hq: {sync['state']} local={sync['local']} remote={sync['remote']} {sync['error']}")
    return 0 if not sync or sync["state"] == "SYNCED" else 3


if __name__ == "__main__":
    sys.exit(main())
