"""OPS-08: find sub-agents that are still being continued with a huge context (they burned ~75% of the main
account's limit on 2026-10-21/22: each pause over 5 minutes re-writes the whole context at full price).
PLAYBOOK §4 "Sub-agents stay small": never continue a sub-agent over 250k tokens; get a handoff, start a fresh one.

  python -X utf8 big_agents.py          print "BIG <app session id> <k>k <description>" per newly flagged agent, else "none"
  python -X utf8 big_agents.py --all    print every big unfinished agent (no flag file read or written)

Read only, except the flag file `00-HQ/intake/big-agents-flagged.json` ({agent file: ISO time flagged}): an agent is
printed again only after FLAG_AGAIN_SEC, so the watchdog messages a session once per agent per 2 h.
Main account only on purpose: the helpers' seats have their own limits and their runs start fresh each time.
"""
import datetime as dt, glob, json, os, sys, time
from pathlib import Path

TRANSCRIPTS = Path.home() / ".claude" / "projects"
APP_SESSIONS = Path(os.environ.get("APPDATA", ""), "Claude", "claude-code-sessions")
FLAGS = Path(__file__).resolve().parent.parent / "intake" / "big-agents-flagged.json"
LIMIT = 250_000          # tokens of context (PLAYBOOK §4)
ACTIVE_SEC = 35 * 60     # written this recently = still being continued (the watchdog runs every 30 min)
FLAG_AGAIN_SEC = 2 * 3600


def context_tokens(usage):
    """One API call's context size: everything it read, cached or not."""
    u = usage or {}
    return u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)


def last_context(raw_lines):
    """Context size of the newest real call (bytes or str lines, junk skipped), else 0. App-written "<synthetic>"
    error lines carry all-zero usage and are skipped (review OPS-08-r1 #5)."""
    return last_info(raw_lines)[0]


def last_info(raw_lines):
    """-> (context of the newest real call or 0, epoch of the newest line's timestamp or None,
    the cli session id the newest lines belong to or None)."""
    ctx, newest, owner = 0, None, None
    for raw in reversed(raw_lines):
        try:
            e = json.loads(raw)
            u = (e.get("message") or {}).get("usage")
            c = context_tokens(u) if u else 0
        except (ValueError, AttributeError, TypeError):
            continue
        owner = owner or e.get("sessionId")
        if newest is None and e.get("timestamp"):
            try:
                newest = dt.datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError, AttributeError):
                pass
        ctx = ctx or c
        if ctx and newest is not None and owner:
            break
    return ctx, newest, owner


def is_big(meta, ctx, age_sec):
    return not meta.get("finished") and ctx > LIMIT and age_sec <= ACTIVE_SEC


def to_flag(found, flags, now_ts):
    """found: [(agent path, ...)]; flags: {path: epoch flagged}. -> the entries not flagged in the last 2 h."""
    return [f for f in found if f[0] not in flags or now_ts - flags[f[0]] >= FLAG_AGAIN_SEC]


def _tail_lines(path, size=2097152):
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - size))
        return f.read().splitlines()


def _app_ids():
    """cli session id -> app session id (local_…), from the app's session files."""
    out = {}
    for p in glob.glob(str(APP_SESSIONS / "*" / "*" / "local_*.json")):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("cliSessionId"):
            out[d["cliSessionId"]] = d.get("sessionId") or Path(p).stem
    return out


def scan(now_ts):
    """-> [(agent path, app session id or cli id, context tokens, description)] for big agents still being continued."""
    ids, out = None, []
    for path in glob.glob(str(TRANSCRIPTS / "*" / "*" / "subagents" / "agent-*.jsonl")):
        try:
            if now_ts - os.path.getmtime(path) > ACTIVE_SEC:  # quick pre-filter only: the app can rewrite old files
                continue
            ctx, newest, owner = last_info(_tail_lines(path))
        except OSError:
            continue
        cli = Path(path).parent.parent.name
        if newest is None or (owner and owner != cli):  # a fork copies its parent's agents: not this chat's work (r2 #1)
            continue
        age = now_ts - newest  # the newest line's own time = when the agent last worked (review OPS-08-r1 #1)
        try:
            meta = json.loads(Path(path[:-6] + ".meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if not is_big(meta, ctx, age):
            continue
        ids = ids if ids is not None else _app_ids()
        out.append((path, ids.get(cli, cli), ctx, (meta.get("description") or meta.get("agentType") or "-")[:70]))
    return out


def main(argv):
    now = time.time()
    found = scan(now)
    if "--all" not in argv:
        try:
            flags = {k: dt.datetime.fromisoformat(v).timestamp()
                     for k, v in json.loads(FLAGS.read_text(encoding="utf-8")).items()}
        except (OSError, ValueError, AttributeError, TypeError):
            flags = {}
        found = to_flag(found, flags, now)
    for _, sid, ctx, desc in found:
        print(f"BIG {sid} {ctx // 1000}k {desc}")
    if not found:
        print("none")
    if found and "--all" not in argv:  # print first: a failed write must not hide the BIG lines (review #3)
        stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        keep = {k: dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")
                for k, t in flags.items() if now - t < 86400}
        keep.update({f[0]: stamp for f in found})
        try:
            tmp = FLAGS.with_suffix(".tmp")
            tmp.write_text(json.dumps(keep, indent=1), encoding="utf-8")
            os.replace(tmp, FLAGS)
        except OSError as e:
            print(f"(flag file not written: {e})")


if __name__ == "__main__":
    main(sys.argv[1:])
