"""Owner -> account messages that reach a RUNNING helper session without stopping it.

The console writes `<state>\\mailbox\\<acct>\\pending\\*.json`. A Claude Code hook in that account's own profile
(PostToolUse + UserPromptSubmit) runs `python ownermsg.py hook <acct>`: it moves the pending messages to
`delivered\\` (an atomic rename, so a message is delivered once) and prints them as `additionalContext`, which the
session reads at its next step. The state folder is outside every helper's writable folders.

    python -X utf8 ownermsg.py hook h1        # the hook (reads the hook JSON on stdin; never fails, never blocks)
"""
import datetime as dt, json, os, re, secrets, sys

ACCT_RE = re.compile(r"^[a-z0-9]{1,12}$")


def _dir(state, acct, sub):
    if not ACCT_RE.match(acct or ""):
        raise ValueError(f"bad account id {acct!r}")
    return os.path.join(state, "mailbox", acct, sub)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def send(state, acct, text, source="terminal"):
    text = (text or "").strip()
    if not text:
        raise ValueError("empty message")
    now = dt.datetime.now()
    mid = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    _write(os.path.join(_dir(state, acct, "pending"), mid + ".json"),
           {"id": mid, "account": acct, "text": text[:4000], "at": now.isoformat(timespec="seconds"), "source": source})
    return mid


def _jsons(folder):
    try:
        return sorted(n for n in os.listdir(folder) if n.endswith(".json"))
    except OSError:
        return []


def counts(state, acct):
    return {"pending": len(_jsons(_dir(state, acct, "pending"))), "delivered": len(_jsons(_dir(state, acct, "delivered")))}


def deliver(state, acct, session_id):
    """Move every pending message to delivered/ and return them (oldest first)."""
    pend, done = _dir(state, acct, "pending"), _dir(state, acct, "delivered")
    out = []
    for name in _jsons(pend):
        src, dst = os.path.join(pend, name), os.path.join(done, name)
        try:
            os.makedirs(done, exist_ok=True)
            os.replace(src, dst)  # the claim: whoever renames it delivers it
        except OSError:
            continue
        try:
            with open(dst, encoding="utf-8") as f:
                msg = json.load(f)
            msg.update(delivered_to=session_id, delivered_at=dt.datetime.now().isoformat(timespec="seconds"))
            _write(dst, msg)
        except (OSError, ValueError):  # unreadable or the mark could not be written: not delivered
            _move_back(pend, dst, name)
            continue
        out.append(msg)
    return out


def _move_back(pend, dst, name):
    try:
        os.replace(dst, os.path.join(pend, name))
    except OSError:
        pass


def undeliver(state, acct, msgs):
    """The session never got them (the hook could not print): back to pending, delivery marks removed."""
    pend, done = _dir(state, acct, "pending"), _dir(state, acct, "delivered")
    for m in msgs:
        name = m["id"] + ".json"
        m = {k: v for k, v in m.items() if k not in ("delivered_to", "delivered_at")}
        try:
            _write(os.path.join(pend, name), m)
            os.remove(os.path.join(done, name))
        except OSError:
            pass


def recent(state, acct, n=10):
    """Newest first, pending and delivered."""
    msgs = []
    for sub in ("pending", "delivered"):
        folder = _dir(state, acct, sub)
        for name in _jsons(folder):
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    msgs.append(json.load(f))
            except (OSError, ValueError):
                pass
    return sorted(msgs, key=lambda m: m.get("id", ""), reverse=True)[:n]


def hook_text(msgs):
    lines = ["[WhyNot Control Center] Message(s) from Yunus, the owner, typed in this account's own terminal:"]
    for m in msgs:
        lines.append(f"- ({m.get('at', '?')[11:16]}) {m.get('text', '')}")
    lines.append("This is the owner's own channel (a hook in this profile). Follow it within your role and PLAYBOOK "
                 "rules; if it changes the scope of your card, say so in your report. Answer briefly in your next "
                 "text so the owner sees it in the terminal.")
    return "\n".join(lines)


def hook_main(argv, stdin_text, out, state=None):
    try:
        acct = argv[0]
        if state is None:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import common
            state = common.load_config()["state_dir"]
        if not _jsons(_dir(state, acct, "pending")):
            return 0
        try:
            data = json.loads(stdin_text or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if data.get("agent_id") or data.get("agent_type"):
            return 0  # a sub-agent's tool call: the message is for the main thread (Claude Code 2.1.304 sends these)
        msgs = deliver(state, acct, data.get("session_id") or "?")
        if msgs:
            event = data.get("hook_event_name") or "PostToolUse"
            text = json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": hook_text(msgs)}},
                              ensure_ascii=False)
            try:
                out.write(text)
                out.flush()
            except Exception:  # noqa: BLE001
                undeliver(state, acct, msgs)
    except Exception:  # noqa: BLE001  a hook must never break the session
        pass
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "hook":
        stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ""
        sys.exit(hook_main(sys.argv[2:], stdin_text, sys.stdout))
    print(__doc__)
