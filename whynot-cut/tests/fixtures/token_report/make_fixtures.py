# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Builds the synthetic Claude Code transcripts of tests/test_token_report.py (Addendum M, M5-T1).

Every record uses the key names Claude Code writes (type, uuid, parentUuid, isSidechain, sessionId, cwd, message.id,
message.model, message.usage.{input_tokens, cache_creation_input_tokens, cache_creation.{ephemeral_5m_input_tokens,
ephemeral_1h_input_tokens}, cache_read_input_tokens, output_tokens, service_tier, speed}, isApiErrorMessage, agentId,
subagents/agent-<hex>.jsonl + agent-<hex>.meta.json). The content is made up: no real transcript was copied. The
client name, path and prompt sentence planted below are fictional and exist so the anonymisation test can look for
them in the tool's output.

    python make_fixtures.py            rewrite the committed fixture files next to this script
The test suite checks that the committed files equal what this script builds (no drift).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PLANTED_CLIENT = "Zorblax Quentaro"                                   # fictional
PLANTED_PATH = "D:\\Fixture Clients\\Zorblax Quentaro\\data\\Raw"       # fictional
PLANTED_PROMPT = "Please cut the Zorblax Quentaro launch reel before the vexil meeting tonight."  # fictional
PROJECT_DIR = "D--Fixture-Clients-Zorblax-Quentaro"                     # path-mangled like Claude Code does
OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5-20251001"


class Seq:
    """Deterministic uuids and timestamps."""
    def __init__(self, tag):
        self.tag, self.n = tag, 0

    def uuid(self):
        self.n += 1
        return f"{self.tag}-{self.n:04d}-0000-4000-8000-000000000000"

    def ts(self):
        return f"2026-10-16T10:{self.n // 60:02d}:{self.n % 60:02d}.000Z"


def usage(fresh=0, w5=0, w1=0, read=0, out=0, speed="standard", split=True):
    u = {"input_tokens": fresh, "cache_creation_input_tokens": w5 + w1, "cache_read_input_tokens": read,
         "output_tokens": out, "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
         "service_tier": "standard", "inference_geo": "global", "speed": speed}
    if split:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1}
    return u


def bash(cmd, tid, name="Bash"):
    return {"type": "tool_use", "id": tid, "name": name, "input": {"command": cmd, "description": "fixture step"}}


def agent(tid):
    return {"type": "tool_use", "id": tid, "name": "Agent",
            "input": {"description": "fixture helper", "subagent_type": "general-purpose", "prompt": PLANTED_PROMPT}}


def text(s="Working on it."):
    return {"type": "text", "text": s}


def asst(seq, sid, mid, u, content=None, model=OPUS, sidechain=False, agent_id=None, error=False):
    r = {"parentUuid": None, "isSidechain": sidechain, "userType": "external", "cwd": PLANTED_PATH,
         "sessionId": sid, "version": "2.1.299", "gitBranch": "main", "type": "assistant", "uuid": seq.uuid(),
         "timestamp": seq.ts(),
         "message": {"id": mid, "type": "message", "role": "assistant", "model": model,
                     "content": content or [text()], "stop_reason": "tool_use", "stop_sequence": None,
                     "usage": u}}
    if agent_id:
        r["agentId"] = agent_id
    if error:
        r["isApiErrorMessage"] = True
        r["error"] = "rate_limit"
        r["message"]["model"] = "<synthetic>"
    return r


def user(seq, sid, content, sidechain=False, agent_id=None):
    r = {"parentUuid": None, "isSidechain": sidechain, "userType": "external", "cwd": PLANTED_PATH, "sessionId": sid,
         "type": "user", "uuid": seq.uuid(), "timestamp": seq.ts(), "message": {"role": "user", "content": content}}
    if agent_id:
        r["agentId"] = agent_id
    return r


def noise(seq, sid):
    """Non-assistant records Claude Code writes; the tool must ignore every one of them."""
    return [
        {"type": "queue-operation", "operation": "enqueue", "timestamp": seq.ts(), "sessionId": sid,
         "content": PLANTED_PROMPT},
        {"type": "attachment", "uuid": seq.uuid(), "sessionId": sid, "cwd": PLANTED_PATH,
         "attachment": {"type": "environment", "snapshot": {"workingDirectory": PLANTED_PATH}}},
        {"type": "file-history-snapshot", "messageId": "file-snap-1", "isSnapshotUpdate": False,
         "snapshot": {"trackedFileBackups": {}}},
        {"type": "system", "subtype": "local_command", "uuid": seq.uuid(), "sessionId": sid, "level": "info",
         "content": PLANTED_CLIENT},
        {"type": "custom-title", "customTitle": PLANTED_CLIENT, "sessionId": sid},
        {"type": "cost-state", "sessionId": sid, "modelUsage": {OPUS: {"inputTokens": 999999, "outputTokens": 999999,
                                                                       "costUSD": 99.0}}},
    ]


HEREDOC = "cat > notes.md <<'EOF'\nreel qc EP09_C0909\nreel plan EP09_C0909\nEOF\necho \"reel plan EP09_C0909\""


def main_records(sid, seq, inline_subagents=False):
    """The main session s1. With inline_subagents the subagents' records sit in the main file (older layout)."""
    R = [user(seq, sid, PLANTED_PROMPT)] + noise(seq, sid)
    # m1: setup, 5 streamed records with identical usage (counted once)
    for _ in range(5):
        R.append(asst(seq, sid, "msg_m1", usage(fresh=1000, w5=2000, out=100)))
    # m2: `reel previews` -> previews / EP02; progressive output (50 then 200), then an all-zero tail record
    R.append(asst(seq, sid, "msg_m2", usage(fresh=10, w1=1000, read=3000, out=50), [text("Rendering previews.")]))
    R.append(asst(seq, sid, "msg_m2", usage(fresh=10, w1=1000, read=3000, out=200),
                  [bash('reel previews EP02_C0238 --root "' + PLANTED_PATH + '"', "toolu_m2")]))
    R.append(asst(seq, sid, "msg_m2", usage()))
    R.append(user(seq, sid, [{"type": "tool_result", "tool_use_id": "toolu_m2", "content": PLANTED_PATH}]))
    # m3: spawns subagent aa11 (Agent tool_use toolu_A1) during previews
    R.append(asst(seq, sid, "msg_m3", usage(fresh=5, w5=100, read=4000, out=300), [agent("toolu_A1")]))
    if inline_subagents:
        R += sub_aa11(sid, seq, sidechain_inline=True) + sub_bb22(sid, seq, sidechain_inline=True)
    R.append(user(seq, sid, [{"type": "tool_result", "tool_use_id": "toolu_A1", "content": "done"}]))
    # m4: run_python.sh form -> plan / EP02
    R.append(asst(seq, sid, "msg_m4", usage(fresh=20, w1=500, read=5000, out=400),
                  [bash('cd "' + PLANTED_PATH + '" && bash "$CLAUDE_PLUGIN_ROOT/bin/run_python.sh" -s reel plan '
                        'EP02_C0238 2>&1 | tail -5', "toolu_m4")]))
    # m5: python -m reel -> qc / EP03 (a second item, interleaved)
    R.append(asst(seq, sid, "msg_m5", usage(fresh=30, read=6000, out=100),
                  [bash("python -m reel qc EP03_C0101", "toolu_m5")]))
    # m6: heredoc and echo hold the word reel: not stage markers; still qc / EP03
    R.append(asst(seq, sid, "msg_m6", usage(fresh=1, read=7000, out=50), [bash(HEREDOC, "toolu_m6")]))
    # m7: reel.cmd from the PowerShell tool -> ppro-build / EP02
    R.append(asst(seq, sid, "msg_m7", usage(fresh=2, read=8000, out=60),
                  [bash('& "C:\\Users\\fixture\\.whynot-cut\\bin\\reel.cmd" ppro-build EP02_C0238', "toolu_m7",
                        name="PowerShell")]))
    # m8: an API error record (synthetic model): reported under errors only
    R.append(asst(seq, sid, "msg_m8", usage(out=7), [text("API Error: rate limited")], error=True))
    # m9: fast mode -> its own model key
    R.append(asst(seq, sid, "msg_m9", usage(fresh=100, out=10, speed="fast")))
    return R


def sub_aa11(sid, seq, sidechain_inline=False):
    aid = "aa11"
    R = [user(seq, sid, PLANTED_PROMPT, sidechain=True, agent_id=aid)]
    R.append(asst(seq, sid, "msg_a1", usage(fresh=100, w5=1000, out=500), model=SONNET, sidechain=True, agent_id=aid))
    # a nested spawn (toolu_B2) and a reel command inside a subagent: subagent markers never move the stage
    R.append(asst(seq, sid, "msg_a2", usage(fresh=10, read=2000, out=100),
                  [agent("toolu_B2"), bash("reel plan EP77_C7777", "toolu_a2")], model=SONNET, sidechain=True,
                  agent_id=aid))
    return R


def sub_bb22(sid, seq, sidechain_inline=False):
    aid = "bb22"
    return [user(seq, sid, PLANTED_PROMPT, sidechain=True, agent_id=aid),
            asst(seq, sid, "msg_b1", usage(fresh=400, out=200), model=HAIKU, sidechain=True, agent_id=aid)]


def sub_cc33(sid, seq):
    aid = "cc33"
    return [asst(seq, sid, "msg_c1", usage(fresh=10, out=10), model=SONNET, sidechain=True, agent_id=aid)]


def meta(tool_use_id, depth, model=None):
    m = {"agentType": "general-purpose", "description": "fixture helper", "toolUseId": tool_use_id,
         "spawnDepth": depth, "requestShape": "default", "requestNonInteractive": False}
    if model:
        m["model"] = model
    return m


def resumed_records(sid, seq, s1):
    """s2: a resumed session replays m4 and m5 of s1 (same message ids), then one new message m10."""
    R = [user(seq, sid, PLANTED_PROMPT)]
    R += [dict(r, sessionId=sid) for r in s1 if r.get("type") == "assistant"
          and r["message"]["id"] in ("msg_m4", "msg_m5")]
    R.append(asst(seq, sid, "msg_m10", usage(fresh=50, read=1000, out=20)))
    return R


def dumps(records):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)


def build() -> dict:
    """{relative path: file text} of every fixture file."""
    out = {}
    s1 = main_records("s1", Seq("a1"))
    p = PROJECT_DIR + "/"
    out[p + "s1.jsonl"] = dumps(s1)
    seq = Seq("a2")
    out[p + "s1/subagents/agent-aa11.jsonl"] = dumps(sub_aa11("s1", seq))
    out[p + "s1/subagents/agent-aa11.meta.json"] = json.dumps(meta("toolu_A1", 1, SONNET), sort_keys=True) + "\n"
    out[p + "s1/subagents/agent-bb22.jsonl"] = dumps(sub_bb22("s1", seq))
    out[p + "s1/subagents/agent-bb22.meta.json"] = json.dumps(meta("toolu_B2", 2), sort_keys=True) + "\n"
    out[p + "s1/subagents/agent-cc33.jsonl"] = dumps(sub_cc33("s1", seq))          # no meta.json
    out[p + "s2.jsonl"] = dumps(resumed_records("s2", Seq("a3"), s1))
    # twins: the same session in the folder layout and in the older in-file sidechain layout (no cc33)
    out["twin_folder/t1.jsonl"] = dumps(main_records("t1", Seq("b1")))
    seq = Seq("b2")
    out["twin_folder/t1/subagents/agent-aa11.jsonl"] = dumps(sub_aa11("t1", seq))
    out["twin_folder/t1/subagents/agent-aa11.meta.json"] = json.dumps(meta("toolu_A1", 1), sort_keys=True) + "\n"
    out["twin_folder/t1/subagents/agent-bb22.jsonl"] = dumps(sub_bb22("t1", seq))
    out["twin_folder/t1/subagents/agent-bb22.meta.json"] = json.dumps(meta("toolu_B2", 2), sort_keys=True) + "\n"
    out["twin_infile/t1.jsonl"] = dumps(main_records("t1", Seq("c1"), inline_subagents=True))
    return out


def write(root: Path = HERE) -> list:
    written = []
    for rel, body in sorted(build().items()):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        written.append(rel)
    return written


if __name__ == "__main__":
    for rel in write():
        print(rel)
    sys.exit(0)
