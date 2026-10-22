"""Claude Code status line for a Control Center terminal: who this account is, its model, its context, and one line
on the other two accounts. Reads the status-line JSON on stdin and <state>\\snapshot.json. No model call, < 50 ms.

    statusLine: {"type": "command", "command": "\"C:/Python313/python.exe\" -X utf8 \"<cc>/app/statusline.py\" h1"}
"""
import datetime as dt, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, runlog  # noqa: E402

ESC = "\x1b["
COL = {"green": "32", "amber": "33", "red": "31", "gray": "90"}


def paint(text, colour):
    return f"{ESC}{COL[colour]}m{text}{ESC}0m" if colour in COL else text


def context_part(data, cfg):
    cw = data.get("context_window") or {}
    used = runlog.context_tokens(cw.get("current_usage") or {})
    size = cw.get("context_window_size")
    if used is None and data.get("transcript_path"):
        c = runlog.transcript_context(data["transcript_path"], 262144)
        used = c["tokens"] if c else None
    if not size:
        w = runlog.WindowRegistry(str(common.state_path(cfg, "model_windows.json"))).get((data.get("model") or {}).get("id"))
        size = w["size"] if w else None
    if used is None:
        return "ctx —"
    if not size:
        return f"ctx {kfmt(used)} / window ?"
    pct = round(used * 100 / size)
    th = cfg["thresholds"]
    colour = "red" if pct >= th["context_danger_percent"] else "amber" if pct >= th["context_warn_percent"] else "green"
    return paint(f"ctx {kfmt(used)}/{kfmt(size)} {pct}%", colour)


def kfmt(n):
    return f"{n / 1e6:.1f}M".replace(".0M", "M") if n >= 1e6 else f"{round(n / 1e3)}K"


def others(snap, me):
    parts = []
    for a in snap.get("accounts", []):
        if a["id"] == me:
            continue
        label = a["status"]["label"]
        task = f" {a['task_id']}" if a.get("task_id") else ""
        parts.append(paint(f"{a['name']}: {label}{task}", a["status"].get("colour", "gray")))
    return " · ".join(parts)


def line(acct_id, data, cfg, now=None):
    now = now or dt.datetime.now()
    acct = common.account(cfg, acct_id)
    model = (data.get("model") or {}).get("display_name") or "?"
    head = paint(f"{acct['name'].upper()} {acct['email'].split('@')[0]}@", "green")
    out = [head, model, context_part(data, cfg)]
    try:
        p = common.state_path(cfg, "snapshot.json")
        snap = json.loads(p.read_text(encoding="utf-8"))
        age = common.snapshot_age_min(snap, now) or 0
        mine = next((a for a in snap["accounts"] if a["id"] == acct_id), {})
        if mine.get("kind") == "helper":
            out.append(f"AUTO {'on' if mine['connection'].get('auto_on') else 'off'} · msgs waiting {mine['mailbox']['pending']}")
        out.append(others(snap, acct_id))
        if age > cfg["refresh"]["stale_minutes"]:
            out.append(paint(f"monitor data {int(age)} min old", "amber"))
    except (OSError, ValueError, KeyError, StopIteration):
        out.append(paint("monitor offline", "gray"))
    return " · ".join(x for x in out if x)


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    try:
        print(line(sys.argv[1] if len(sys.argv) > 1 else "main", data, common.load_config()))
    except Exception as e:  # noqa: BLE001  never break the terminal
        print(f"status line error: {type(e).__name__}")


if __name__ == "__main__":
    main()
