#!/usr/bin/env python3
"""Stop: the evidence gate (3.0 T3.4, optional, OFF by default; stop_gate.sh runs this only when it is on).

When Claude ends a turn saying a WhyNot Cut edit is ready or done, the turn must hold the proof: a `reel qc` (or
`reel verify`) run. A turn that ran `reel` commands and claims ready/done without it is sent back once
({"decision": "block"}) with what to do; `stop_hook_active` (a turn already continued by a stop hook) is let through,
so it can never loop. Turns that ran no `reel` command are never judged (other work in the same session).
Proof (fix round 1): a `reel qc`/`reel verify` of this turn, by the lead or by a subagent whose transcript
(<transcript>/subagents/*.jsonl) changed this turn; or, when this turn only looked (`reel status`, `reel next`, ...),
an earlier turn's qc/verify of the same item with nothing changed for that item since. Commands are split with shlex
(quoted or Arabic `--root`, `"$WHYNOT_HOME/bin/reel"`, `reel.cmd`); only the global options that take a value are
skipped before the subcommand.
Stdlib only, reads only the tail of the transcripts; never fails the turn (any error -> exit 0, allow).
"""
import json
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
TAIL = 4 * 1024 * 1024               # the current turn lies in the last few MB of the transcript
CLAIM = re.compile(r"\b(?:is|are|it's|now|all)\s+(?:ready|done|finished|complete)\b|\bready (?:for|to) (?:review|you|"
                   r"the editor|import|open)\b|\ball set\b|جاهز|جاهزة|خلص|خلصت|خلّص|اتعمل|اكتمل", re.I)
PROOF = {"qc", "verify"}
REEL_NAMES = {"reel", "reel.cmd", "reel.exe", "reel.ps1", "reel.bat"}
VALUE_OPTS = {"--root", "--video-id", "--profile", "--episode"}          # reel's global options that take a value
PREFIX = {"exec", "time", "command", "nohup", "call", "&", "."}            # words before a command name
TIMEOUT_VALUE_OPTS = {"-s", "--signal", "-k", "--kill-after"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}                              # <shell> -c / -lc "<command>"
SEPARATORS = set(";&|()\n") | {"&&", "||", ";;", "|&"}
# commands that only look: alone they need no fresh proof, and they do not make an earlier proof stale
LOOK = {"status", "next", "lock", "doctor", "validate", "ppro-status", "ppro-probe", "ae-status", "ae-probe", "settings",
        "inbox", "episodes", "episode-next", "music", "motion-icons", "motion-library", "serve", "setup", "py", "bench",
        "profile", "handoff", "publish-check", "ppro-frames", "range"} | PROOF


def _tokens(cmd: str) -> list:
    """Shell words and separators. Backslashes become slashes first (Windows paths; nothing judged here needs one)."""
    lex = shlex.shlex(cmd.replace("\\", "/"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:                                  # unbalanced quotes: plain words
        return cmd.replace("\\", "/").split()


def reel_calls(cmd: str, depth: int = 0) -> list:
    """[(subcommand, video id or None)] of every `reel` the command runs (at a command position). One level of
    launcher is unwrapped (fix round 2, m3): `bash -lc "reel ... qc"`, `cmd /c reel ...`, `powershell -Command "..."`,
    `timeout 60 reel qc`."""
    out, seg = [], []
    for tok in _tokens(cmd) + [";"]:
        if tok in SEPARATORS or (tok and set(tok) <= set(";&|()")):
            if seg:
                out += _one(seg, depth)
            seg = []
        else:
            seg.append(tok)
    return out


def _unwrap(name: str, args: list):
    """The command string a shell / cmd / PowerShell launcher runs, or None."""
    if name in SHELLS:
        for k, a in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a):
                return args[k + 1] if k + 1 < len(args) else None
    elif name == "cmd":
        for k, a in enumerate(args):
            if a.lower() in ("/c", "/k"):
                return " ".join(args[k + 1:])
    elif name in ("powershell", "pwsh"):
        for k, a in enumerate(args):
            if re.fullmatch(r"-c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?", a, re.I):
                return " ".join(args[k + 1:])
    return None


def _one(seg: list, depth: int = 0) -> list:
    i = 0
    while i < len(seg):
        if seg[i] == "timeout":                         # timeout [-s SIG] [-k DUR] [--opt] DURATION command
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 2 if seg[i] in TIMEOUT_VALUE_OPTS else 1
            if i < len(seg) and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", seg[i]):
                i += 1
        elif seg[i] in PREFIX or re.fullmatch(r"[A-Za-z_]\w*=.*", seg[i]):
            i += 1
        else:
            break
    if i >= len(seg):
        return []
    name = seg[i].rsplit("/", 1)[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if depth < 1:
        inner = _unwrap(name, seg[i + 1:])
        if inner:
            return reel_calls(inner, depth + 1)
    if seg[i].rsplit("/", 1)[-1].lower() not in REEL_NAMES:
        return []
    sub, item, args = None, None, seg[i + 1:]
    j = 0
    while j < len(args):
        a = args[j]
        if a.startswith("-"):
            name, eq, val = a.partition("=")
            if name in VALUE_OPTS and not eq:
                val = args[j + 1] if j + 1 < len(args) else ""
                j += 1
            if name == "--video-id" and val:
                item = val
        elif sub is None and re.fullmatch(r"[a-z][\w-]*", a, re.I):
            sub = a.lower()
        j += 1
    return [(sub, item)] if sub else []


def _real_user(rec: dict) -> bool:
    msg = rec.get("message") if isinstance(rec, dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    return rec.get("type") == "user" and not rec.get("isMeta") and (isinstance(content, str) or (
        isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "text" for c in content)))


def _records(path) -> list:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - TAIL))
            lines = fh.read().splitlines()
    except OSError:
        return []
    recs = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            recs.append(rec)
    return recs


def _calls(recs: list) -> list:
    out = []
    for rec in recs:
        content = (rec.get("message") or {}).get("content") if isinstance(rec.get("message"), dict) else None
        if rec.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Bash", "PowerShell"):
                    out += reel_calls(str((c.get("input") or {}).get("command") or ""))
    return out


def _epoch(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def turn_calls(transcript: str):
    """(this turn's reel calls: the lead's and its subagents' since the turn began, the earlier turns' calls in order)."""
    recs = _records(transcript)
    start = max((k for k, r in enumerate(recs) if _real_user(r)), default=-1)
    now, earlier = _calls(recs[start + 1:]), _calls(recs[:max(start, 0)])
    began = _epoch(recs[start].get("timestamp")) if start >= 0 else None
    subs = Path(transcript).with_suffix("") / "subagents" if transcript else None
    files = []
    try:
        for f in (subs.glob("*.jsonl") if subs and subs.is_dir() else []):
            try:
                files.append((f.stat().st_mtime, f))
            except OSError:
                pass
    except OSError:
        pass
    for mtime, f in sorted(files)[-50:]:
        if began is None or mtime >= began - 1:     # else last written before this turn began
            now += _calls(_records(f))
    return now, earlier


def proven(now: list, earlier: list) -> bool:
    if any(s in PROOF for s, _ in now):
        return True
    if any(s not in LOOK for s, _ in now):
        return False                                # this turn changed something: it needs its own proof
    items = {i for _, i in now if i} or {next((i for _, i in reversed(earlier) if i), None)}
    for item in items:
        last = next(((s, i) for s, i in reversed(earlier)
                     if (i is None or item is None or i == item) and (s in PROOF or s not in LOOK)), None)
        if not last or last[0] not in PROOF:
            return False
    return True


def main():
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return
    if not CLAIM.search(str(data.get("last_assistant_message") or "")):
        return
    now, earlier = turn_calls(str(data.get("transcript_path") or ""))
    if not now or proven(now, earlier):
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
