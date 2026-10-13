#!/usr/bin/env python3
"""Stop: the evidence gate (3.0 T3.4, optional, OFF by default; stop_gate.sh runs this only when it is on).

When Claude ends a turn saying a WhyNot Cut edit is ready or done, the turn must hold the proof: a `reel qc` (or
`reel verify`) run. A turn that ran `reel` commands and claims ready/done without it is sent back once
({"decision": "block"}) with what to do; `stop_hook_active` (a turn already continued by a stop hook) is let through,
so it can never loop. Turns that ran no `reel` command are never judged (other work in the same session).
Stdlib only, reads only the tail of the transcript; never fails the turn (any error -> exit 0, allow).
"""
import json
import re
import sys

sys.dont_write_bytecode = True
TAIL = 4 * 1024 * 1024               # the current turn lies in the last few MB of the transcript
CLAIM = re.compile(r"\b(?:is|are|it's|now|all)\s+(?:ready|done|finished|complete)\b|\bready (?:for|to) (?:review|you|"
                   r"the editor|import|open)\b|\ball set\b|جاهز|جاهزة|خلص|خلصت|خلّص|اتعمل|اكتمل", re.I)
REEL = re.compile(r"(?:^|[\s;&|(\"'/\\])reel(?:\.cmd)?\s+(?:--?\S+\s+(?:\S+\s+)?)*?([a-z][\w-]*)", re.I)
PROOF = {"qc", "verify"}


def turn_commands(transcript: str) -> list:
    """The Bash/PowerShell commands of the current turn: tool calls after the last real user message."""
    try:
        with open(transcript, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - TAIL))
            lines = fh.read().splitlines()
    except OSError:
        return []
    cmds = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        msg = rec.get("message") if isinstance(rec, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if rec.get("type") == "user" and (isinstance(content, str) or (isinstance(content, list) and any(
                isinstance(c, dict) and c.get("type") == "text" for c in content))) and not rec.get("isMeta"):
            break                                   # the editor's message that started this turn
        if rec.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Bash", "PowerShell"):
                    cmds.append(str((c.get("input") or {}).get("command") or ""))
    return cmds


def main():
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return
    if not CLAIM.search(str(data.get("last_assistant_message") or "")):
        return
    subs = {m.group(1).lower() for c in turn_commands(str(data.get("transcript_path") or "")) for m in REEL.finditer(c)}
    if not subs or subs & PROOF:
        return
    print(json.dumps({"decision": "block", "reason": (
        "WhyNot Cut evidence gate: this turn says the edit is ready/done but ran no `reel qc` (or `reel verify`). "
        "Run `reel qc` for the item and look at its frames, then report what it shows; if it is not ready, say so "
        "instead. (The editor turned this check on with `evidence_gate: on`.)")}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
