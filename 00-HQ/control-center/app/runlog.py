"""Read-only parsers for Claude Code logs: helper run logs (stream-json) and desktop-app transcripts.

Nothing here calls a model. Context in use = input + cache read + cache creation tokens of the newest main-thread
assistant line (the same number Claude Code shows); the window size comes only from a CLI report
(`modelUsage.<model>.contextWindow` in a run's final line), learned in WindowRegistry.
"""
import collections, json, os, re, time

TEXT_MAX = 400


def context_tokens(usage):
    if not usage:
        return None
    keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    if not any(k in usage for k in keys):
        return None
    return sum(int(usage.get(k) or 0) for k in keys)


def short_path(p, keep=2):
    parts = [x for x in re.split(r"[\\/]+", str(p or "")) if x]
    return "/".join(parts[-keep:]) if parts else "?"


def one_line(text, n=TEXT_MAX):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def human_tool(name, inp):
    """A tool call in plain words."""
    inp = inp or {}
    if name == "Bash":
        cmd = inp.get("command") or ""
        m = re.search(r"heavy\.sh\"?\s+(suite|job|gpu)\s+(\S+)", cmd)
        if m:
            kind = {"suite": "Full test suite", "job": "Heavy job", "gpu": "GPU job"}[m.group(1)]
            return f"{kind} '{m.group(2)}' (heavy queue)"
        if re.search(r"heavy\.sh\"?\s+status", cmd):
            return "Checking the heavy test queue"
        first = cmd.strip().splitlines()[0] if cmd.strip() else ""
        return one_line(inp.get("description") or (f"Shell: {first}" if first else "Shell command"), 120)
    if name in ("Edit", "NotebookEdit"):
        return f"Editing {short_path(inp.get('file_path') or inp.get('notebook_path'))}"
    if name == "Write":
        return f"Writing {short_path(inp.get('file_path'))}"
    if name == "Read":
        return f"Reading {short_path(inp.get('file_path'))}"
    if name in ("Grep", "Glob"):
        return one_line(f"Searching for {inp.get('pattern')!r}", 100)
    if name in ("Task", "Agent"):
        return one_line("Sub-agent: " + (inp.get("description") or inp.get("subagent_type") or "?"), 120)
    if name == "TodoWrite":
        return "Updating its to-do list"
    if name in ("WebSearch", "WebFetch"):
        return one_line(f"Web: {inp.get('query') or inp.get('url') or ''}", 100)
    if name == "Skill":
        return f"Using skill {inp.get('skill') or inp.get('name') or '?'}"
    return name or "?"


class RunFeed:
    """Incremental reader of one stream-json run log. poll() returns only events it has not returned before."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self._rest = b""
        self.session_id = self.model = self.cwd = ""
        self.started_at = None      # first timestamp seen
        self.context = None         # tokens in context at the newest main-thread reply
        self.context_at = None
        self.window = None          # from the run's final line only
        self.last_text = ""
        self.last_text_at = None
        self.action = ""            # the newest tool call in plain words
        self.action_at = None
        self.tool_wait = 0          # seconds the current tool has been running (heartbeats)
        self.rate = None
        self.result = None
        self.denials = 0
        self.last_event_at = None
        self.tool_inputs = collections.deque(maxlen=400)  # raw tool inputs (JSON), to find which card a run is on

    def poll(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size < self.offset:  # replaced: start again
            self.__init__(self.path)
        if size == self.offset:
            return []
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read(size - self.offset)
        self.offset = size
        raws = (self._rest + data).split(b"\n")
        self._rest = raws.pop()
        out = []
        for raw in raws:
            try:
                e = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(e, dict):
                self._take(e, out)
        return out

    def _event(self, out, kind, text, ts=None):
        ts = ts or self.last_event_at
        out.append({"kind": kind, "text": one_line(text), "at": ts})

    def _take(self, e, out):
        t, ts = e.get("type"), e.get("timestamp")
        if ts:
            self.last_event_at = ts
            self.started_at = self.started_at or ts
        if t == "system" and e.get("subtype") == "init":
            self.session_id = e.get("session_id") or self.session_id
            self.model = e.get("model") or self.model
            self.cwd = e.get("cwd") or self.cwd
            self._event(out, "start", f"Session started on {self.model}")
        elif t == "assistant":
            msg = e.get("message") or {}
            if e.get("parent_tool_use_id"):
                return  # a sub-agent's line: its context is its own
            m = msg.get("model") or ""
            if m and not m.startswith("<"):
                self.model = m
            c = context_tokens(msg.get("usage"))
            if c is not None:
                self.context, self.context_at = c, ts
            self.tool_wait = 0
            for b in msg.get("content") or []:
                if b.get("type") == "text" and (b.get("text") or "").strip():
                    self.last_text, self.last_text_at = one_line(b["text"]), ts
                    self._event(out, "say", b["text"], ts)
                elif b.get("type") == "tool_use":
                    self.action, self.action_at = human_tool(b.get("name"), b.get("input")), ts
                    self.tool_inputs.append(json.dumps(b.get("input"), ensure_ascii=False))
                    self._event(out, "tool", self.action, ts)
        elif t == "tool_progress" and e.get("heartbeat") and not e.get("parent_tool_use_id"):
            self.tool_wait = int(e.get("elapsed_time_seconds") or 0)
        elif t == "user":
            if not e.get("parent_tool_use_id"):
                self.tool_wait = 0
            content = (e.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    c = b.get("content")
                    c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                    self._event(out, "error", "Tool error: " + c, ts)
        elif t == "rate_limit_event":
            info = e.get("rate_limit_info") or {}
            five = (info.get("unifiedWindows") or {}).get("five_hour") or {}
            util = five.get("utilization")
            self.rate = {"five_hour_pct": round(util * 100) if isinstance(util, (int, float)) else None,
                         "resets_at": five.get("resetsAt") or info.get("resetsAt"), "status": info.get("status")}
        elif t == "system" and e.get("subtype") == "permission_denied":
            self.denials += 1
            self._event(out, "denied", e.get("message") or "permission denied")
        elif t == "result":
            self.tool_wait = 0
            usage = e.get("modelUsage") or {}
            mu = usage.get(self.model) or (next(iter(usage.values())) if usage else {})
            self.window = mu.get("contextWindow") or self.window
            ok = not e.get("is_error")
            self.result = {"ok": ok, "subtype": e.get("subtype"), "text": one_line(e.get("result"), 300),
                           "turns": e.get("num_turns")}
            self._event(out, "end", ("Run finished: " if ok else "Run ended with an error: ") + str(e.get("result") or ""))


def transcript_context(path, tail_bytes=1_048_576):
    """Newest main-thread context of a desktop-app transcript: {'tokens','at','model'} or None. Reads only the end."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail_bytes))
            raws = f.read().splitlines()
    except OSError:
        return None
    for raw in reversed(raws):
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        msg = e.get("message") or {}
        if (msg.get("model") or "").startswith("<"):
            continue  # an app-written error line
        c = context_tokens(msg.get("usage"))
        if c is not None:
            return {"tokens": c, "at": e.get("timestamp"), "model": msg.get("model")}
    return None


def base_model(m):
    return re.sub(r"\[.*?\]$", "", (m or "").strip().lower())


class WindowRegistry:
    """Context window sizes as Claude Code reported them, per model, with where and when they were seen."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def get(self, model):
        return self.data.get(base_model(model))

    def learn(self, model, size, source):
        key = base_model(model)
        if not key or not size:
            return
        old = self.data.get(key) or {}
        if old.get("size") == size and old.get("source") == source:
            return
        self.data[key] = {"size": int(size), "source": source, "at": time.strftime("%Y-%m-%d %H:%M")}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass
