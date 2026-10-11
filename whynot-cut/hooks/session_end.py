#!/usr/bin/env python3
"""SessionEnd: give back the ending session's own client lease (output/.whynot-lock, 3.0 T1.8).

Looks at the client folder the session ran in (the cwd or a folder above it) and at the client folders right below
the cwd (a session opened in the clients folder works with --root "<name>"). Removes a lease only when its
session_id is the ending session's; another session's lease is never touched. Without this hook a lease still ends
when the session's Claude Code process exits (stale) or after 2 h without a writing command.
Stdlib only, fast; never fails the session (any error -> silent exit 0).
"""
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True        # the plugin folder stays clean of __pycache__
PLUGIN = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(PLUGIN / "engine" / "reel" / "lib"))


def candidates(cwd: Path) -> list:
    up = [p for p in [cwd, *cwd.parents] if (p / "output" / ".whynot-lock").is_file()][:1]
    try:
        below = [p for p in cwd.iterdir() if (p / "output" / ".whynot-lock").is_file()]
    except OSError:
        below = []
    return up + [p for p in below if p not in up]


def main():
    import writer_lock
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    sid = data.get("session_id") or writer_lock.session_id()
    for root in candidates(Path(data.get("cwd") or os.getcwd())):
        writer_lock.release_own(root, sid)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
