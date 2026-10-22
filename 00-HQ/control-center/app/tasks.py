"""Human-readable tasks: every BOARD id with its title, objective, owner, lifecycle and evidence.

Source of truth stays 00-HQ (BOARD.md, tasks/, inbox/, reviews/, intake/state.json) plus git branches and the heavy
queue. Nothing here writes. Progress is counted in verified lifecycle steps, never as an invented percentage.
"""
import datetime as dt, json, re
from pathlib import Path

import common  # noqa: F401
import hq_status as hq  # noqa: E402  (parse_board)

KNOWN = {"NOT READY", "READY", "IN PROGRESS", "FIX", "ACCEPTED", "MERGED", "DONE_ARCHIVED", "DONE", "BLOCKED",
         "PARKED", "STOPPED", "RUNNING"}
STEPS = [("ready", "Card ready"), ("started", "Work started"), ("delivered", "Delivered"),
         ("peer", "Peer review"), ("decision", "Master's decision"), ("merged", "Merged")]
REPORT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(?:\d{4}-)?(.+?)(?:-r\d+)?\.md$")
PARENS_RE = re.compile(r"\s*\(([^()]*)\)\s*$")


def report_task(name):
    m = REPORT_RE.match(name)
    return m.group(1) if m else None


def _read(p, n=None):
    try:
        t = Path(p).read_text(encoding="utf-8", errors="replace")
        return t[:n] if n else t
    except OSError:
        return ""


def _field(text, name):
    m = re.search(rf"\*\*{name}:\*\*\s*(.+?)(?:\s{{2,}}\*\*|\n|$)", text)
    return m.group(1).strip() if m else ""


def _section(text, *names):
    """First prose paragraph under the first heading that starts with one of names."""
    for name in names:
        m = re.search(rf"^## {re.escape(name)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m:
            para = _first_prose(m.group(1))
            if para:
                return para
    return ""


def _first_prose(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for block in re.split(r"\n\s*\n", text):
        lines = [l.strip() for l in block.strip().splitlines()]
        if not lines or lines[0].startswith(("#", "- ", "* ", "|", "```", "`tasks/")):
            continue
        return " ".join(lines)
    return ""


def _short(t, n=300):
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def parse_card(path):
    text = _read(path)
    out = {"summary": "", "tier": "", "stage": "", "depends": "", "acceptance": (0, 0), "fix_at": None,
           "fix_round": None, "text": bool(text)}
    if not text:
        return out
    out["tier"] = _field(text, "Tier").split(" ")[0]
    out["stage"] = re.split(r"\s*\(", _field(text, "Stage / gate"))[0].strip()
    out["depends"] = _field(text, "Depends on")
    spec = Path(path).with_name(Path(path).stem + "-spec.md")
    out["summary"] = _short(_section(text, "Goal", "Decision for this card", "Why")
                            or _first_prose(re.sub(r"^#.*$", "", _read(spec), flags=re.M))
                            or _section(text, "Spec"))
    ticks = re.findall(r"^\s*- \[( |x|X)\]", text, re.M)
    out["acceptance"] = (sum(1 for t in ticks if t.lower() == "x"), len(ticks))
    fixes = re.findall(r"^## FIX round (\d+) \((\d{4}-\d{2}-\d{2} \d{2}:\d{2})\)", text, re.M)
    if fixes:
        out["fix_round"], out["fix_at"] = int(fixes[-1][0]), fixes[-1][1]
    return out


def reports_by_task(hq_dir):
    """{task id: [report dicts, oldest first]} from inbox/h1|h2."""
    out = {}
    for who in ("h1", "h2"):
        for f in Path(hq_dir, "inbox", who).glob("*.md"):
            cid = report_task(f.name)
            if not cid:
                continue
            head = _read(f, 3000)
            st = re.search(r"\*\*Status:\*\*\s*([A-Z]+)\s*(.*)", head)
            title_time = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", head.splitlines()[0] if head else "")
            out.setdefault(cid, []).append({
                "who": who, "file": f"inbox/{who}/{f.name}", "mtime": f.stat().st_mtime,
                "status": st.group(1) if st else "?", "note": _short(st.group(2), 240) if st else "",
                "at": title_time.group(1) if title_time else dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    for v in out.values():
        v.sort(key=lambda r: r["mtime"])
    return out


def peer_reviews(hq_dir):
    """{task id: [{'file','report_mtime','verdict','suite','reviewer','mtime'}]}."""
    out = {}
    for f in Path(hq_dir, "reviews").glob("*-peer-*.md"):
        cid = f.name.split("-peer-")[0]
        head = dict(re.findall(r"^([a-z-]+):\s*(.*)$", _read(f, 2000), re.M))
        out.setdefault(cid, []).append({"file": f"reviews/{f.name}", "report_mtime": head.get("report-mtime", ""),
                                        "verdict": head.get("verdict", "?"), "suite": _short(head.get("suite", ""), 80),
                                        "reviewer": head.get("reviewer", "").split(" ")[0], "mtime": f.stat().st_mtime})
    return out


def owner_id(owner):
    o = (owner or "").upper()
    if o.startswith("H1"):
        return "h1"
    if o.startswith("H2"):
        return "h2"
    if o.startswith(("MASTER", "EXECUTOR")):
        return "main"
    if o.startswith("LANE"):
        return "lane"
    return ""


def clean_title(title):
    m = PARENS_RE.search(title)
    if m and re.search(r"gate|stage|light|high|tier|\bS\b|\bM\b", m.group(1), re.I):
        return title[: m.start()].strip()
    return title


def _same_mtime(written, mtime):
    """helper_loop writes the report mtime rounded to whole seconds."""
    try:
        return abs(float(written) - mtime) < 1.5
    except (TypeError, ValueError):
        return False


def _ts(at):
    try:
        return dt.datetime.strptime(at, "%Y-%m-%d %H:%M").timestamp()
    except (TypeError, ValueError):
        return None


def build_tasks(hq_dir, branches=None, queue=None, verdicts=None, current=None):
    """branches: {'h1/BL-17': iso date}; queue: parse_queue() dict; current: {task id: {'account','action','run_started'}}."""
    hq_dir = Path(hq_dir)
    rows = hq.parse_board(_read(hq_dir / "BOARD.md"))
    reps, peers = reports_by_task(hq_dir), peer_reviews(hq_dir)
    if verdicts is None:
        try:
            verdicts = {k.replace("\\", "/"): v for k, v in
                        json.loads(_read(hq_dir / "intake" / "state.json") or "{}").items()}
        except ValueError:
            verdicts = {}
    branches, queue, current = branches or {}, queue or {"running": {}, "waiting": {}}, current or {}
    out = []
    for r in rows:
        cid = r["id"]
        if cid.startswith("(") or not re.match(r"^[A-Za-z]", cid):
            continue
        out.append(_task(hq_dir, r, reps.get(cid, []), peers.get(cid, []), verdicts, branches, queue,
                         current.get(cid)))
    return out


def _task(hq_dir, r, reports, peers, verdicts, branches, queue, cur):
    cid, status = r["id"], r["status"].upper()
    owner = owner_id(r["owner"])
    card = parse_card(hq_dir / r["card"]) if r["card"] else parse_card(Path("-"))
    newest = reports[-1] if reports else None
    fix_ts = _ts(card["fix_at"])
    # A FIX round is open until a report newer than its header arrives (BOARD can lag behind the helper).
    if fix_ts:
        fixing = not newest or newest["mtime"] < fix_ts
    else:
        fixing = status == "FIX"
    branch = next((b for b in branches if b.lower() == f"{owner}/{cid}".lower()), None)
    verdict = (verdicts.get(newest["file"]) or {}) if newest else {}
    v_word = (verdict.get("verdict") or "").upper()
    peer = None
    if newest:
        same = [p for p in peers if _same_mtime(p["report_mtime"], newest["mtime"])]
        peer = max(same, key=lambda p: p["mtime"]) if same else None
    merged = status in ("MERGED", "DONE_ARCHIVED")
    accepted = merged or status == "ACCEPTED"
    no_code = bool(re.search(r"no code|nothing to merge", r["status_note"], re.I))
    known = status in KNOWN

    steps = {k: {"key": k, "label": lab, "state": "pending", "evidence": "", "at": None} for k, lab in STEPS}

    def put(k, state, evidence="", at=None):
        steps[k].update(state=state, evidence=evidence, at=at)

    if status == "NOT READY" or not known:
        put("ready", "current", r["status_note"])
    else:
        put("ready", "done", f"card {r['card'] or '(none)'}")
    if branch or reports or status in ("IN PROGRESS", "FIX", "RUNNING") or accepted or cur:
        ev = f"branch {branch}" if branch else (f"first report {reports[0]['file']}" if reports else
                                                 "running now" if cur else f"BOARD: {r['status_note']}")
        put("started", "done", ev, reports[0]["at"] if reports else None)
    if accepted:
        put("delivered", "done", newest["file"] if newest else "accepted on BOARD", newest["at"] if newest else None)
    elif newest and newest["status"] == "BLOCKED":
        put("delivered", "failed", f"BLOCKED: {newest['note']}", newest["at"])
    elif fixing:
        put("delivered", "current", f"fix round {card['fix_round'] or '?'} asked at {card['fix_at'] or '?'}")
    elif newest and newest["status"] == "DONE":
        put("delivered", "done", newest["file"], newest["at"])
    elif newest:
        put("delivered", "current", f"{newest['status']} report {newest['file']}", newest["at"])
    elif steps["started"]["state"] == "done":
        put("delivered", "current", "working on it")
    delivered = steps["delivered"]["state"] == "done"
    if peer and delivered:
        put("peer", "failed" if peer["verdict"].startswith("FAIL") else "done",
            f"{peer['reviewer']}: {peer['verdict']}", dt.datetime.fromtimestamp(peer["mtime"]).strftime("%Y-%m-%d %H:%M"))
    elif accepted:
        put("peer", "done", "decided without a recorded peer review")
    elif delivered:
        put("peer", "current", "waiting for the other helper's peer review")
    if accepted:
        put("decision", "done", f"ACCEPTED ({r['status_note']})")
    elif fixing:
        put("decision", "failed", f"FIX round {card['fix_round'] or '?'}", card["fix_at"])
    elif delivered:
        put("decision", "current", f"intake: {verdict.get('verdict') or 'not seen yet'}", verdict.get("at"))
    if merged:
        put("merged", "done", r["status_note"])
    elif accepted and no_code:
        put("merged", "skipped", "closed without code: nothing to merge")
    elif accepted:
        put("merged", "current", "in MERGE-QUEUE.md; the executor merges")

    blocker = ""
    if status in ("BLOCKED", "PARKED", "STOPPED"):
        blocker = (newest["note"] if newest and newest["status"] == "BLOCKED" else "") or r["status_note"]
    elif newest and newest["status"] == "BLOCKED" and not accepted:
        blocker = newest["note"]

    if status == "NOT READY":
        display = "Not ready yet"
    elif not known:
        display = status.replace("_", " ").capitalize().replace(" not ", ", not ")
    elif status == "DONE_ARCHIVED":
        display = "Done (archived)"
    elif merged:
        display = "Merged"
    elif status == "ACCEPTED":
        display = "Accepted (nothing to merge)" if no_code else "Accepted, waiting for merge"
    elif status in ("BLOCKED", "PARKED", "STOPPED") or blocker:
        display = "Blocked" if status != "PARKED" else "Parked"
    elif fixing:
        display = f"Fixing (round {card['fix_round'] or '?'})"
    elif steps["decision"]["state"] == "current" and steps["peer"]["state"] == "done":
        display = "Peer review passed, waiting for the master's decision"
    elif steps["peer"]["state"] == "current":
        display = "Delivered, waiting for peer review"
    elif steps["started"]["state"] == "done":
        display = "In progress"
    else:
        display = "Ready (queued)"

    jobs = []
    pat = re.compile(rf"(^|[-_/]){re.escape(cid.lower())}($|[-_/])")
    for part, word in (("running", "running"), ("waiting", "waiting")):
        for label, m in queue.get(part, {}).items():
            if pat.search(label.lower()):
                jobs.append(f"{label} {word} {m} min")
    verification = ""
    if peer:
        verification = f"Peer {peer['reviewer']}: {peer['verdict']}" + (f" · suite: {peer['suite']}" if peer["suite"] else "")
    mtimes = [x["mtime"] for x in reports] + [p["mtime"] for p in peers]
    last = max(mtimes) if mtimes else None
    done = sum(1 for s in steps.values() if s["state"] == "done")
    return {
        "id": cid, "title": clean_title(r["title"]), "summary": card["summary"], "owner": owner,
        "owner_text": r["owner"], "board_status": r["status_note"], "status": status, "display": display,
        "parent": card["stage"] or "", "tier": card["tier"], "depends": card["depends"], "blocker": blocker,
        "steps": [steps[k] for k, _ in STEPS], "progress": {"done": done, "total": len(STEPS)},
        "acceptance": {"ticked": card["acceptance"][0], "total": card["acceptance"][1]},
        "branch": branch, "jobs": jobs, "card": r["card"], "latest_report": newest,
        "result": (newest["status"] + " " + newest["note"]).strip() if newest else "",
        "verification": verification, "started_at": reports[0]["at"] if reports else (cur or {}).get("run_started"),
        "last_activity": dt.datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M") if last else None,
        "current_action": (cur or {}).get("action", ""), "active_on": (cur or {}).get("account", ""),
    }
