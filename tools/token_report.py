#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Token report: tokens per stage and per video from Claude Code session transcripts (Addendum M, M5-T1).

Spec: docs/superpowers/specs/addendum-m/ADDENDUM-M-owner-requests-2026-10-16.md (M5.2 unit, M5.3 guard rails, M5.5).
Dev tool, not shipped in the plugin. Stdlib only. Read-only: it never writes next to the transcripts.

What it reads
  A project folder of ~/.claude/projects (CLAUDE_CONFIG_DIR/projects when that is set): <session>.jsonl is a main
  conversation; <session>/subagents/agent-<hex>.jsonl (+ agent-<hex>.meta.json: toolUseId, spawnDepth) are its
  subagents. The older layout (isSidechain records inside the main file) and `claude -p --output-format stream-json`
  traces (parent_tool_use_id) parse too. A folder made by tools/eval_transcripts.py (manifest.json) is reported per
  eval case and run.

How it counts
  * Only `assistant` records with message.usage count. Claude Code writes one API response as several records with
    the same message.id, with growing output_tokens, sometimes an all-zero tail: per id the LAST NON-ZERO record wins,
    and an id counts once across every file of the report (a resumed session replays earlier ids). Records flagged
    isApiErrorMessage are reported under `errors`, never in the stage totals.
  * Raw counts: fresh input, 5-minute cache write, 1-hour cache write (from usage.cache_creation; a total without the
    split counts as 5-minute writes and the report says so), cache read, output.
  * Weighted (M5.2 unit, per model): each category at the model's published price, divided by the lead model's fresh
    input price, so one weighted token = one fresh input token of the lead. The lead is --lead-model, else the priced
    model with the most main-conversation messages. Fast mode (usage.speed "fast") is its own key `<model>+fast`.
    An unknown model is `unpriced`: raw tokens only, excluded from every weighted number (the report says so).
    `weighted_m52` is the same with M5.2's fixed multipliers (1 / 1.25 / 2 / 0.1 / 5) for comparison with the
    provisional baseline; the published cache-read price of some models is lower than 0.1x.
  * Stage and video: the latest `reel <verb> [<ID>]` run from a Bash or PowerShell tool call of the main conversation
    (`reel`, `reel.cmd`, a path to them, `python -m reel`, `run_python.sh ... reel`, `.../reel/cli.py`), in command
    position only (not in a heredoc, an echo or a quoted string). The message that issues the command already belongs
    to the new stage. Before the first command: stage `setup`. The video is --video-id, else the first id-like
    argument after the verb, else --episode; a command without one keeps the current video. A subagent's usage goes
    to the stage current when the main conversation started it (nested subagents roll up to the top-level spawn);
    reel commands inside a subagent move nothing. A subagent whose spawn is not found: `unattributed-subagent`.
  * Lead context per turn: fresh + cache read + cache writes of each main-conversation message; median, p90 (nearest
    rank) and max against the 150,000 guard rail (M5.3).

Privacy: the output names stages, model ids, counts and anonymised video labels (item-01, ... in order of first use;
--raw-ids prints the real ids). It never prints prompt text, tool inputs, paths or folder names; a file is named by
its path below its project folder (<session>.jsonl, <session>/subagents/agent-<hex>.jsonl).

Usage
  python tools/token_report.py [PATH ...] [--project NAME ...] [--json FILE|-] [--lead-model ID] [--raw-ids]
                               [--marked-only] [--date YYYY-MM-DD]
  No PATH and no --project: every project folder under the projects folder. Exit 0, or 2 when nothing could be read.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import re
import stat
import statistics
import sys
import tempfile
from pathlib import Path

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[1]
GUARD_RAIL = 150_000
CATS = ("fresh", "write_5m", "write_1h", "read", "output")

# --- Prices -------------------------------------------------------------------------------------------------------
# USD per million tokens: (fresh input, 5-minute cache write, 1-hour cache write, cache read, output). Only the ratios
# matter. Copied from Anthropic's published pricing page (Model pricing and Fast mode pricing tables) on the date
# below. Re-check with count_tokens and the page when the API lane resumes (Nov). Never edit from memory.
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing (Model pricing, Fast mode pricing)"
PRICES_READ_ON = "2026-10-18"
PRICES = {
    "claude-fable-5-1": (10, 12.5, 20, 0.25, 50),
    "claude-mythos-5-1": (10, 12.5, 20, 0.25, 50),
    "claude-fable-5": (10, 12.5, 20, 1, 50),
    "claude-mythos-5": (10, 12.5, 20, 1, 50),
    "claude-opus-5-5": (4, 5, 8, 0.20, 20),
    "claude-opus-5": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-8": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-7": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-6": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-5": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-1": (15, 18.75, 30, 1.50, 75),
    "claude-opus-4": (15, 18.75, 30, 1.50, 75),
    "claude-sonnet-5-5": (2, 2.5, 4, 0.10, 10),
    "claude-sonnet-5": (2, 2.5, 4, 0.20, 10),
    "claude-sonnet-4-6": (3, 3.75, 6, 0.30, 15),
    "claude-sonnet-4-5": (3, 3.75, 6, 0.30, 15),
    "claude-sonnet-4": (3, 3.75, 6, 0.30, 15),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-haiku-4-5": (1, 1.25, 2, 0.10, 5),
    "claude-3-5-haiku": (0.80, 1, 1.60, 0.08, 4),
}
# A request whose prompt (fresh + cache read + cache writes) is over the threshold pays the second row.
TIERED = {"claude-haiku-5-5": (100_000, (0.50, 0.625, 1.0, 0.05, 2.50))}
# Fast mode (input, output); the cache multipliers of the model apply on top of the fast input price.
FAST = {"claude-opus-5-5": (8, 40), "claude-opus-5": (10, 50), "claude-opus-4-8": (10, 50)}
M52_UNIT = (1.0, 1.25, 2.0, 0.1, 5.0)

ASSUMPTIONS = (
    "weighted = each category at the model's published price / the lead model's fresh input price "
    f"(prices read {PRICES_READ_ON}; re-check with count_tokens when the API resumes)",
    "plan usage limits are assumed to track the weighted number (M5.2: the limit formula is not published)",
    "stage = the latest `reel` command of the main conversation (medium confidence); subagents go to their spawn stage",
    "calls Claude Code makes without a transcript record (titles, compaction summaries) are not counted",
)

AGENT_TOOLS = ("Agent", "Task")
SHELL_TOOLS = ("Bash", "PowerShell")
ENTRY_NAMES = ("reel", "reel.cmd", "reel.bat", "reel.exe", "reel.ps1")
LAUNCHERS = ("bash", "sh", "zsh", "env", "exec", "time", "nice", "nohup", "command", "call", "cmd", "timeout",
             "py", "uv", "run", "powershell", "pwsh", ".")
VALUE_OPTS = ("--root", "--video-id", "--profile", "--episode")
ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
PY_RE = re.compile(r"python(\d+(\.\d+)*)?w?")
NUM_RE = re.compile(r"\d+[smhd]?")
VERB_RE = re.compile(r"[a-z][a-z0-9-]{1,40}")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SHA_RE = re.compile(r"[0-9a-f]{40}")
PROJECT_NAME = re.compile(r"[^\\/:*?\"<>|\x00-\x1f]{1,255}")
ESCAPABLE = " \t\n'\"\\;&|<>()#$`"


# --- Models and prices --------------------------------------------------------------------------------------------
def normalize_model(model) -> str:
    """A transcript's model id -> the price table key (drops a -YYYYMMDD snapshot suffix and a [1m] tag)."""
    if not isinstance(model, str) or not model.strip():
        return "unknown"
    m = re.sub(r"\[[^\]]*\]$", "", model.strip())
    return re.sub(r"-\d{8}$", "", m)


def price_row(model_key: str, prompt: int):
    """(fresh, write_5m, write_1h, read, output) USD/MTok for a model key (`+fast` included) and a request's prompt
    size, or None when the model is not priced."""
    fast = model_key.endswith("+fast")
    base = model_key[:-len("+fast")] if fast else model_key
    row = PRICES.get(base)
    if row is None:
        return None
    tier = TIERED.get(base)
    if tier and prompt > tier[0]:
        row = tier[1]
    if fast:
        if base not in FAST:
            return None
        fin, fout = FAST[base]
        row = (fin, fin * 1.25, fin * 2, fin * row[3] / row[0], fout)
    return row


def nearest_rank(values, p: float):
    """The p-quantile by nearest rank (no interpolation), None for no values."""
    if not values:
        return None
    s = sorted(values)
    k = max(1, math.ceil(round(p * len(s), 9)))
    return s[k - 1]


# --- Shell parsing: `reel` commands in command position ------------------------------------------------------------
def _segments(cmd: str) -> list:
    """Simple commands of a shell line as token lists. Quotes, escapes, comments, heredoc bodies and redirection
    targets never produce command words; ; & | && || newlines and parentheses separate commands."""
    segs, toks, cur = [], [], None
    heredocs = []
    skip_word = False
    i, n = 0, len(cmd)

    def end_tok():
        nonlocal cur, skip_word
        if cur is not None:
            if skip_word:
                skip_word = False
            else:
                toks.append("".join(cur))
        cur = None

    def end_seg():
        nonlocal toks
        end_tok()
        if toks:
            segs.append(toks)
        toks = []

    while i < n:
        c = cmd[i]
        if c == "'" or c == '"':
            cur = cur if cur is not None else []
            j = i + 1
            while j < n and cmd[j] != c:
                if c == '"' and cmd[j] == "\\" and j + 1 < n and cmd[j + 1] in '"\\$`':
                    j += 1
                cur.append(cmd[j])
                j += 1
            if j >= n:                     # unterminated quote: the rest is not a command
                return segs
            i = j + 1
        elif c == "\\":
            if i + 1 < n and cmd[i + 1] == "\n":
                i += 2
                continue
            cur = cur if cur is not None else []
            if i + 1 < n and cmd[i + 1] in ESCAPABLE:
                cur.append(cmd[i + 1])
                i += 2
            else:
                cur.append(c)
                i += 1
        elif c in " \t\r":
            end_tok()
            i += 1
        elif c == "\n":
            end_seg()
            i += 1
            for delim, dash in heredocs:
                while i < n:
                    j = cmd.find("\n", i)
                    line = cmd[i:] if j < 0 else cmd[i:j]
                    i = n if j < 0 else j + 1
                    if (line.lstrip("\t") if dash else line) == delim:
                        break
            heredocs = []
        elif c == "#" and cur is None:
            j = cmd.find("\n", i)
            i = n if j < 0 else j
        elif c in ";&|()":
            end_seg()
            i += 2 if cmd[i:i + 2] in ("&&", "||") else 1
        elif c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            end_tok()
            i += 2
            dash = i < n and cmd[i] == "-"
            i += 1 if dash else 0
            while i < n and cmd[i] in " \t":
                i += 1
            word = []
            while i < n and cmd[i] not in " \t\n;&|<>()":
                if cmd[i] not in "'\"\\":
                    word.append(cmd[i])
                i += 1
            heredocs.append(("".join(word), dash))
        elif c in "<>":
            if cur is not None and "".join(cur).isdigit():
                cur = None                 # a file descriptor number (2>&1)
            end_tok()
            while i < n and cmd[i] in "<>&":
                i += 1
            if i < n and cmd[i].isdigit():
                while i < n and cmd[i].isdigit():
                    i += 1
            else:
                skip_word = True
        else:
            cur = cur if cur is not None else []
            cur.append(c)
            i += 1
    end_seg()
    return segs


def _base(tok: str) -> str:
    return tok.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()


def _is_launcher(tok: str) -> bool:
    b = _base(tok)
    b = b[:-4] if b.endswith(".exe") else b
    return b in LAUNCHERS or bool(PY_RE.fullmatch(b)) or bool(NUM_RE.fullmatch(tok)) or tok.startswith("-") \
        or tok.lower() in ("/c", "/k")


def _is_entry(tok: str) -> bool:
    return _base(tok) in ENTRY_NAMES or tok.replace("\\", "/").lower().endswith("reel/cli.py")


def _parse_after(rest: list):
    """(verb, ID or None) from the words after the entry point, or None when there is no verb."""
    verb = item = vid = ep = None
    j = 0
    while j < len(rest):
        t = rest[j]
        name, eq, val = t.partition("=")
        if name in VALUE_OPTS:
            if not eq:
                val = rest[j + 1] if j + 1 < len(rest) else ""
                j += 1
            if name == "--video-id":
                vid = val
            elif name == "--episode":
                ep = val
        elif t.startswith("-"):
            pass
        elif verb is None:
            if not VERB_RE.fullmatch(t):
                return None
            verb = t
        elif item is None and ID_RE.fullmatch(t) and any(ch.isdigit() or ch == "_" for ch in t):
            item = t
        j += 1
    if verb is None:
        return None
    for cand in (vid, item, ep):
        if cand and ID_RE.fullmatch(cand):
            return verb, cand.upper()
    return verb, None


def _segment_markers(toks: list) -> list:
    i = 0
    while i < len(toks) and ENV_RE.match(toks[i]):
        i += 1
    run_py = False
    while i < len(toks):
        t = toks[i]
        if _is_entry(t):
            m = _parse_after(toks[i + 1:])
            return [m] if m else []
        if _base(t) == "run_python.sh":
            run_py = True
        elif run_py:
            pass
        elif t in ("-c", "-Command") and i + 1 < len(toks):
            return reel_markers(toks[i + 1])
        elif not _is_launcher(t):
            return []
        i += 1
    return []


def reel_markers(command) -> list:
    """Every `reel <verb> [ID]` run by a shell command line, in order: [(verb, ID or None), ...]."""
    if not isinstance(command, str) or not command:
        return []
    out = []
    for seg in _segments(command):
        out += _segment_markers(seg)
    return out


# --- Paths --------------------------------------------------------------------------------------------------------
def default_projects_dir(env=None, platform=None) -> Path:
    """CLAUDE_CONFIG_DIR/projects when set, else <home>/.claude/projects (Windows USERPROFILE or HOMEDRIVE+HOMEPATH,
    other systems HOME)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    cfg = env.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return Path(cfg) / "projects"
    if platform.startswith("win"):
        home = env.get("USERPROFILE") or ((env.get("HOMEDRIVE") or "") + (env.get("HOMEPATH") or ""))
    else:
        home = env.get("HOME")
    return Path(home or Path.home()) / ".claude" / "projects"


def _is_link(path) -> bool:
    """A symlink or any Windows reparse point (junction): never walked into or read through."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _walk_jsonl(root: Path) -> list:
    out = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            p = Path(e.path)
            if _is_link(p):
                continue
            if e.is_dir(follow_symlinks=False):
                stack.append(p)
            elif e.name.endswith(".jsonl"):
                out.append(p)
    return sorted(out)


def discover(paths) -> list:
    """[(main file or None, [subagent files])] for every session under the given files or folders."""
    files = []
    for p in paths:
        p = Path(p)
        if p.is_file() and p.suffix == ".jsonl":
            files.append(p)
            sub = p.with_suffix("") / "subagents"
            if sub.is_dir() and not _is_link(sub):
                files += _walk_jsonl(sub)
        elif p.is_dir():
            files += _walk_jsonl(p)
    sessions, subs = {}, {}
    for f in sorted(set(files)):
        if f.parent.name == "subagents":
            subs.setdefault(f.parent.parent, []).append(f)
        else:
            sessions[f.with_suffix("")] = f
    out = []
    for key in sorted(set(sessions) | set(subs), key=str):
        out.append((sessions.get(key), sorted(subs.get(key, []))))
    return out


def _label(f: Path) -> str:
    """A file's name below its project folder: <session>.jsonl or <session>/subagents/agent-<hex>.jsonl."""
    if f.parent.name == "subagents":
        return f"{f.parent.parent.name}/subagents/{f.name}"
    return f.name


def repo_commit(root: Path):
    """The checked-out commit, read from the .git files (no git process). None when it cannot be read."""
    try:
        g = Path(root) / ".git"
        if g.is_file():
            line = g.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir:"):
                return None
            g = Path(line[len("gitdir:"):].strip())
            if not g.is_absolute():
                g = Path(root) / g
        common = g
        if (g / "commondir").is_file():
            common = (g / (g / "commondir").read_text(encoding="utf-8").strip()).resolve()
        head = (g / "HEAD").read_text(encoding="utf-8").strip()
        if SHA_RE.fullmatch(head):
            return head
        if not head.startswith("ref:"):
            return None
        ref = head[len("ref:"):].strip()
        for base in (g, common):
            f = base / ref
            if f.is_file():
                sha = f.read_text(encoding="utf-8").strip()
                return sha if SHA_RE.fullmatch(sha) else None
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref and SHA_RE.fullmatch(parts[0]):
                    return parts[0]
    except OSError:
        return None
    return None


# --- Reading transcripts ------------------------------------------------------------------------------------------
def _int(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0


def _raw(usage: dict):
    """(raw counts dict, split_missing) of one usage object."""
    total_w = _int(usage.get("cache_creation_input_tokens"))
    split = usage.get("cache_creation")
    if isinstance(split, dict):
        w1 = min(_int(split.get("ephemeral_1h_input_tokens")), total_w)
        missing = False
    else:
        w1 = 0
        missing = total_w > 0
    return {"fresh": _int(usage.get("input_tokens")), "write_5m": total_w - w1, "write_1h": w1,
            "read": _int(usage.get("cache_read_input_tokens")), "output": _int(usage.get("output_tokens"))}, missing


class Msg:
    __slots__ = ("group", "model", "raw", "split_missing", "error", "kind", "ctx", "first_file", "session", "order")

    def __init__(self, group, session, first_file, order):
        self.group, self.session, self.first_file, self.order = group, session, first_file, order
        self.model, self.raw, self.split_missing, self.error = "unknown", dict.fromkeys(CATS, 0), False, False
        self.kind, self.ctx = "main", ("setup", None)


class Reader:
    def __init__(self):
        self.msgs = {}
        self.skipped = []
        self.sessions = 0
        self.order = 0

    def _records(self, f: Path, quiet=False):
        label = _label(f)
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            if not quiet:
                self.skipped.append({"file": label, "line": 0})
            return
        with fh:
            for n, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    if not quiet:
                        self.skipped.append({"file": label, "line": n})
                    continue
                if isinstance(r, dict):
                    yield n, r

    def _take(self, group, session, label, r, kind, ctx, key_fallback):
        """Register one assistant record; ctx is a (stage, ID) tuple or a deferred ("@", ref). Returns the Msg."""
        m = r.get("message")
        usage = m.get("usage") if isinstance(m, dict) else None
        if not isinstance(usage, dict):
            return None
        mid = m.get("id")
        key = (group, mid if isinstance(mid, str) and mid else key_fallback)
        msg = self.msgs.get(key)
        if msg is None:
            self.order += 1
            msg = self.msgs[key] = Msg(group, session, label, self.order)
            msg.kind = kind
        if msg.first_file == label:
            msg.ctx = ctx
        raw, missing = _raw(usage)
        model = normalize_model(m.get("model")) + ("+fast" if usage.get("speed") == "fast" else "")
        if any(raw.values()):
            msg.raw, msg.split_missing, msg.model = raw, missing, model
        elif msg.model == "unknown":
            msg.model = model
        if r.get("isApiErrorMessage") is True:
            msg.error = True
        return msg

    @staticmethod
    def _blocks(r):
        """("marker", (verb, ID)) and ("spawn", tool_use id) events of one assistant record, in block order."""
        content = r["message"].get("content")
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            if b.get("name") in SHELL_TOOLS:
                inp = b.get("input")
                for mk in reel_markers(inp.get("command") if isinstance(inp, dict) else None):
                    yield "marker", mk
            elif b.get("name") in AGENT_TOOLS and isinstance(b.get("id"), str):
                yield "spawn", b["id"]

    def _assistant(self, f, quiet=False):
        for n, r in self._records(f, quiet):
            if r.get("type") == "assistant" and isinstance(r.get("message"), dict):
                yield n, r

    def _has_marker(self, main) -> bool:
        """Does the main conversation run a reel command (for --marked-only)?"""
        for _, r in self._assistant(main, quiet=True):
            if r.get("isSidechain") is not True and not isinstance(r.get("parent_tool_use_id"), str) \
                    and any(kind == "marker" for kind, _ in self._blocks(r)):
                return True
        return False

    def read_session(self, group, main, subs, marked_only=False):
        """Read one session (main file + subagent files); False when --marked-only drops it."""
        if marked_only and not (main and self._has_marker(main)):
            return False
        session = _label(main) if main else _label(subs[0])
        spawn, owner, meta_tid, pending = {}, {}, {}, []
        ctx = ("setup", None)
        for f in ([main] if main else []):
            label = _label(f)
            for n, r in self._assistant(f):
                side = r.get("isSidechain") is True
                parent = r.get("parent_tool_use_id")
                parent = parent if isinstance(parent, str) else None
                for kind, val in self._blocks(r):
                    if kind == "marker":
                        if not side and parent is None:
                            ctx = (val[0], val[1] or ctx[1])
                    elif parent is not None:
                        owner[val] = ("tool", parent)
                    else:
                        spawn[val] = ctx
                if parent is not None:
                    pending.append(self._take(group, session, label, r, "subagent", ("@", ("tool", parent)),
                                              f"{label}:{n}"))
                else:
                    self._take(group, session, label, r, "sidechain" if side else "main", ctx, f"{label}:{n}")
        for f in subs:
            label = _label(f)
            meta = f.with_name(f.name[:-len(".jsonl")] + ".meta.json")
            try:
                with open(meta, encoding="utf-8") as fh:
                    tid = json.load(fh).get("toolUseId")
            except (OSError, ValueError, AttributeError):
                tid = None
            meta_tid[label] = tid
            for n, r in self._assistant(f):
                for kind, val in self._blocks(r):
                    if kind == "spawn":
                        owner[val] = ("agent", label)
                pending.append(self._take(group, session, label, r, "subagent", ("@", ("agent", label)),
                                          f"{label}:{n}"))

        def resolve(ref, seen):
            if ref in seen:
                return ("unattributed-subagent", None)
            seen.add(ref)
            kind, val = ref
            tid = meta_tid.get(val) if kind == "agent" else val
            if not isinstance(tid, str):
                return ("unattributed-subagent", None)
            if tid in spawn:
                return spawn[tid]
            if tid in owner:
                return resolve(owner[tid], seen)
            return ("unattributed-subagent", None)

        for msg in pending:
            if msg is not None and msg.ctx[0] == "@":
                msg.ctx = resolve(msg.ctx[1], set())
        self.sessions += 1
        return True


# --- The report ---------------------------------------------------------------------------------------------------
def _zero():
    return dict.fromkeys(CATS, 0)


def _add(acc, raw):
    for c in CATS:
        acc[c] += raw[c]


def _prompt(raw):
    return raw["fresh"] + raw["read"] + raw["write_5m"] + raw["write_1h"]


def _weights(msg, lead_in):
    """(weighted, weighted_m52) of one message, or (None, None) when it or the lead is unpriced."""
    row = price_row(msg.model, _prompt(msg.raw))
    if row is None or not lead_in:
        return None, None
    w = sum(msg.raw[c] * row[k] for k, c in enumerate(CATS)) / lead_in
    w52 = sum(msg.raw[c] * M52_UNIT[k] for k, c in enumerate(CATS)) * row[0] / lead_in
    return w, w52


def _bucket():
    return {"raw": _zero(), "weighted": 0.0, "weighted_m52": 0.0, "messages": 0}


def _fill(b, msg, w, w52):
    _add(b["raw"], msg.raw)
    b["messages"] += 1
    if w is not None:
        b["weighted"] += w
        b["weighted_m52"] += w52


def _lead_context(msgs):
    turns, over = [], []
    per_session = {}
    for msg in msgs:
        if msg.kind != "main" or msg.error:
            continue
        n = per_session[msg.session] = per_session.get(msg.session, 0) + 1
        c = _prompt(msg.raw)
        turns.append(c)
        if c > GUARD_RAIL:
            over.append({"session": msg.session, "turn": n, "context": c})
    return {"turns": len(turns), "median": statistics.median(turns) if turns else None,
            "p90": nearest_rank(turns, 0.9), "max": max(turns) if turns else None,
            "guard_rail": GUARD_RAIL, "over": len(over), "over_turns": over}


def _choose_lead(msgs, lead_model):
    if lead_model:
        return normalize_model(lead_model)
    counts = {}
    for msg in msgs:
        if msg.kind == "main" and not msg.error:
            counts[msg.model] = counts.get(msg.model, 0) + 1
    ranked = sorted(counts, key=lambda k: (price_row(k, 0) is None, -counts[k], k))
    return ranked[0] if ranked else None


def _summarise(msgs, lead_in, item_label):
    """The aggregate part of a report over a list of messages."""
    totals, errors = _bucket(), {"count": 0, "raw": _zero()}
    by_stage, by_item, by_model, unpriced = {}, {}, {}, {}
    subs = {"messages": 0, "weighted": 0.0, "unattributed_messages": 0}
    split_missing = 0
    for msg in msgs:
        if msg.error:
            errors["count"] += 1
            _add(errors["raw"], msg.raw)
            continue
        w, w52 = _weights(msg, lead_in)
        stage, item = msg.ctx
        label = item_label(item)
        _fill(totals, msg, w, w52)
        _fill(by_stage.setdefault(stage, _bucket()), msg, w, w52)
        it = by_item.setdefault(label, dict(_bucket(), by_stage={}))
        _fill(it, msg, w, w52)
        _fill(it["by_stage"].setdefault(stage, _bucket()), msg, w, w52)
        bm = by_model.setdefault(msg.model, {"raw": _zero(), "weighted": 0.0 if w is not None else None,
                                             "messages": 0})
        _add(bm["raw"], msg.raw)
        bm["messages"] += 1
        if w is None:
            if any(msg.raw.values()):          # a zero-usage placeholder (<synthetic>) is no API call
                _add(unpriced.setdefault(msg.model, _zero()), msg.raw)
        else:
            bm["weighted"] += w
        if msg.kind != "main":
            subs["messages"] += 1
            subs["weighted"] += w or 0.0
            subs["unattributed_messages"] += stage == "unattributed-subagent"
        split_missing += msg.split_missing
    tw = totals["weighted"]
    mix = {k: v["weighted"] / tw for k, v in sorted(by_model.items()) if v["weighted"] is not None and tw > 0}
    subs["share_weighted"] = subs.pop("weighted") / tw if tw > 0 else 0.0
    if not lead_in:
        totals["weighted"] = totals["weighted_m52"] = None
        for b in list(by_stage.values()) + list(by_item.values()) + \
                [s for it in by_item.values() for s in it["by_stage"].values()]:
            b["weighted"] = b["weighted_m52"] = None
        for bm in by_model.values():
            bm["weighted"] = None
        mix = {}
    totals["weighted_excludes_unpriced"] = bool(unpriced)
    return {"totals": totals, "errors": errors, "by_stage": by_stage, "by_item": by_item, "by_model": by_model,
            "unpriced": unpriced, "subagents": subs, "models": {"seen": sorted(by_model), "mix": mix},
            "lead_context": _lead_context(msgs)}, split_missing


def _manifest_runs(root: Path):
    """[(run key, run folder)] and [missing keys] of an eval_transcripts folder, or None without a manifest."""
    mf = root / "manifest.json"
    if not mf.is_file():
        return None
    try:
        with open(mf, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("tool") != "eval_transcripts" or not isinstance(doc.get("runs"), list):
        return None
    runs, missing = [], []
    for r in doc["runs"]:
        if not isinstance(r, dict):
            continue
        case, run = r.get("case"), r.get("run")
        if not (isinstance(case, str) and isinstance(run, str) and SAFE_NAME.fullmatch(case)
                and SAFE_NAME.fullmatch(run) and ".." not in case + run):
            continue
        key = f"{case}/{run}"
        if r.get("status") == "collected" and (root / case / run).is_dir():
            runs.append((key, root / case / run))
        else:
            missing.append(key)
    return runs, missing


def build_report(paths, *, lead_model=None, raw_ids=False, marked_only=False, date=None, commit=None) -> dict:
    """The full report (a JSON-ready dict) over transcript files or folders."""
    reader = Reader()
    run_keys, runs_missing = [], []
    plain = []
    for p in paths:
        mr = _manifest_runs(Path(p)) if Path(p).is_dir() else None
        if mr is None:
            plain.append(p)
            continue
        runs, missing = mr
        runs_missing += missing
        for key, folder in runs:
            run_keys.append(key)
            for main, subs in discover([folder]):
                reader.read_session(key, main, subs, marked_only)
    for main, subs in discover(plain):
        reader.read_session("", main, subs, marked_only)
    msgs = list(reader.msgs.values())
    lead = _choose_lead(msgs, lead_model)
    lead_row = price_row(lead, 0) if lead else None
    lead_in = lead_row[0] if lead_row else None
    labels = {}

    def item_label(item):
        if item is None:
            return "unattributed"
        if raw_ids:
            return item
        if item not in labels:
            labels[item] = f"item-{len(labels) + 1:02d}"
        return labels[item]

    body, split_missing = _summarise(msgs, lead_in, item_label)
    assumptions = list(ASSUMPTIONS)
    if split_missing:
        assumptions.append(f"cache writes without the 5m/1h split counted as 5-minute writes "
                           f"({split_missing} message{'s' if split_missing != 1 else ''})")
    if lead and not lead_in:
        assumptions.append(f"the lead model {lead} is not in the price table: no weighted numbers")
    rep = {"tool": "token_report", "version": VERSION, "report_date": date or _dt.date.today().isoformat(),
           "commit": commit if commit is not None else repo_commit(ROOT),
           "prices": {"source": PRICES_SOURCE, "read_on": PRICES_READ_ON, "lead_model": lead,
                      "unit": "lead-model fresh input token equivalents"},
           "anonymised": not raw_ids, "assumptions": assumptions, "sessions": reader.sessions,
           "partial": bool(reader.skipped), "skipped": reader.skipped}
    rep.update(body)
    if run_keys or runs_missing:
        rep["runs"] = {}
        for key in sorted(set(run_keys)):
            part, _ = _summarise([m for m in msgs if m.group == key], lead_in, item_label)
            t = part["totals"]
            rep["runs"][key] = {"raw": t["raw"], "weighted": t["weighted"], "weighted_m52": t["weighted_m52"],
                                "messages": t["messages"], "by_stage": part["by_stage"],
                                "lead_context": part["lead_context"], "errors": part["errors"]}
        rep["runs_missing"] = sorted(runs_missing)
    return rep


# --- Output -------------------------------------------------------------------------------------------------------
def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:,.0f}"


def render_summary(rep: dict, json_path=None) -> str:
    t, lc = rep["totals"], rep["lead_context"]
    lines = [f"token_report {rep['version']}  commit {(rep['commit'] or 'unknown')[:12]}  {rep['report_date']}",
             f"sessions {rep['sessions']}  messages {t['messages']}  lead {rep['prices']['lead_model'] or 'n/a'}",
             f"weighted {_fmt(t['weighted'])} (lead-input equivalents; M5.2 unit {_fmt(t['weighted_m52'])})"
             + ("  excludes unpriced: " + ", ".join(sorted(rep["unpriced"])) if t["weighted_excludes_unpriced"]
                else "")]
    stages = sorted(rep["by_stage"].items(), key=lambda kv: (-(kv[1]["weighted"] or 0), kv[0]))
    lines.append("stages: " + ", ".join(f"{k} {_fmt(v['weighted'])}" for k, v in stages[:8]))
    items = sorted(rep["by_item"].items(), key=lambda kv: (-(kv[1]["weighted"] or 0), kv[0]))
    lines.append("videos: " + ", ".join(f"{k} {_fmt(v['weighted'])}" for k, v in items[:8]))
    if "runs" in rep:
        lines.append(f"eval runs: {len(rep['runs'])} reported, {len(rep['runs_missing'])} missing")
    lines.append(f"lead context per turn: median {_fmt(lc['median'])}, p90 {_fmt(lc['p90'])}, max {_fmt(lc['max'])}"
                 f"; {lc['over']} turn(s) over the {GUARD_RAIL:,} guard rail")
    if rep["errors"]["count"]:
        lines.append(f"API error records: {rep['errors']['count']} (reported apart, not in the totals)")
    if rep["partial"]:
        lines.append(f"PARTIAL: {len(rep['skipped'])} line(s) or file(s) could not be read (see skipped)")
    lines.append(f"full report: {json_path}" if json_path else "full report: add --json FILE (or --json -)")
    return "\n".join(lines)


def _write_json(rep: dict, path: str) -> None:
    """Atomic: a temp file in the same folder, then replace; nothing is left behind on failure."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".token_report-", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="token_report", description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*", help="transcript files or folders (default: the projects folder)")
    ap.add_argument("--project", action="append", default=[], help="a project folder name under the projects folder")
    ap.add_argument("--json", dest="json_path", help="write the full report here (- for stdout)")
    ap.add_argument("--lead-model", help="the model whose fresh input price is the weighted unit")
    ap.add_argument("--raw-ids", action="store_true", help="print real video ids instead of item-NN labels")
    ap.add_argument("--marked-only", action="store_true", help="only sessions that ran a reel command")
    ap.add_argument("--date", help="report date YYYY-MM-DD (default: today)")
    a = ap.parse_args(argv)

    def refuse(msg):
        print(f"token_report: {msg}", file=sys.stderr)
        return 2

    if a.date and not DATE_RE.fullmatch(a.date):
        return refuse("--date must be YYYY-MM-DD")
    paths = [Path(p) for p in a.paths]
    base = default_projects_dir()
    for name in a.project:
        if not PROJECT_NAME.fullmatch(name) or not name.strip("."):
            return refuse(f"bad --project name (one folder name under the projects folder): {name!r}")
        paths.append(base / name)
    if not paths:
        paths = [base]
    for p in paths:
        if not p.exists():
            return refuse(f"cannot read {p}: not found")
    if not any(discover([p]) or _manifest_runs(p) for p in paths if p.is_dir() or p.is_file()):
        return refuse("no Claude Code transcripts (*.jsonl) found under the given folder(s)")
    rep = build_report(paths, lead_model=a.lead_model, raw_ids=a.raw_ids, marked_only=a.marked_only, date=a.date)
    if a.json_path == "-":
        print(json.dumps(rep, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if a.json_path:
        try:
            _write_json(rep, a.json_path)
        except OSError as e:
            return refuse(f"cannot write the JSON report: {e.strerror or e}")
    print(render_summary(rep, a.json_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
