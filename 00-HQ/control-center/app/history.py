"""Execution history: one line per real state change (never a repeated status). Kept in <state>\\history.jsonl."""
import datetime as dt, json, os


def transitions(prev, cur):
    if not prev:
        return []
    now = dt.datetime.now().isoformat(timespec="seconds")
    out = []

    def add(kind, account, task, text):
        out.append({"at": now, "kind": kind, "account": account, "task": task, "text": text})

    old = {a["id"]: a for a in prev.get("accounts", [])}
    titles = {t["id"]: t.get("title", "") for t in cur.get("tasks", [])}
    for a in cur.get("accounts", []):
        p = old.get(a["id"])
        if not p:
            continue
        if p["status"]["code"] != a["status"]["code"] and "CHECKING" not in (p["status"]["code"], a["status"]["code"]):
            add("status", a["id"], a.get("task_id"),
                f"{a['name']}: {p['status']['label']} → {a['status']['label']}. {a['status']['reason']}".strip())
        if p.get("task_id") != a.get("task_id") and a.get("task_id"):
            add("task", a["id"], a["task_id"], f"{a['name']} is now on {a['task_id']} — {titles.get(a['task_id'], '')}")
        ps, cs = (p.get("session") or {}).get("id"), (a.get("session") or {}).get("id")
        if cs and ps != cs:
            add("run", a["id"], a.get("task_id"), f"{a['name']}: new session {cs[:8]}")
    prev_tasks = {t["id"]: t for t in prev.get("tasks", [])}
    for t in cur.get("tasks", []):
        p = prev_tasks.get(t["id"])
        if p and p["display"] != t["display"]:
            add("task_state", t.get("owner", ""), t["id"], f"{t['id']} — {t['title']}: {p['display']} → {t['display']}")
    seen = {x.get("key") or x["text"] for x in prev.get("alerts", [])}
    for x in cur.get("alerts", []):
        if (x.get("key") or x["text"]) not in seen and x["level"] == "red":
            add("alert", "", "", f"{x['who']}: {x['text']}")
    return out


def append(path, events, max_bytes=5_000_000):
    if not events:
        return
    try:
        if os.path.getsize(path) > max_bytes:
            os.replace(path, path + ".1")
    except OSError:
        pass
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def search(path, q="", account="", task="", limit=200):
    """Newest first."""
    q = (q or "").lower()
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    for raw in reversed(lines):
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if account and e.get("account") != account:
            continue
        if task and (e.get("task") or "").lower() != task.lower():
            continue
        if q and q not in json.dumps(e, ensure_ascii=False).lower():
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out
