#!/usr/bin/env python3
"""WhyNot Cut subagent status line (3.0 T3.6): one row per running WhyNot Cut subagent in Claude Code's agent panel,
"agent · stage · clip · state · time" (time only while the agent is running).

Claude Code runs the plugin's `subagentStatusLine` command about every 5 s and whenever a subagent's token count
changes. It writes ONE JSON object to this script's stdin:
  {..., "columns": N, "tasks": [{"id", "name", "type", "agentType", "status", "description", "label", "startTime",
                                 "model", "effort", "tokenCount", "cwd", ...}, ...]}
and reads stdout as JSON lines `{"id": <task id>, "content": <row text>}`. A task with no line keeps Claude Code's own
row, so only `whynot-cut:*` agents get a line here.

Fast and never fails: stdlib only (json, re, sys, time), no engine import, no file or network access; any error or odd
input prints nothing and exits 0. Plain ASCII labels (RTL safe in a terminal row); the clip id is the only text taken
from the task, and only when it looks like a clip id.
"""
import json
import re
import sys
import time

# agent -> what the editor calls this part of the work (user-facing words; no stage or gate numbers)
STAGE = {
    "intake-inspector": "intake check",
    "client-researcher": "client profile",
    "transcript-editor": "transcript",
    "segment-proofreader": "transcript check",
    "audio-engineer": "audio",
    "story-editor": "story and plan",
    "medical-reviewer": "sensitive-claims check",
    "claim-checker": "sensitive-claims check",
    "motion-designer": "graphics",
    "graphic-checker": "graphics check",
    "premiere-builder": "Premiere build",
    "qc-reviewer": "proof check",
    "frame-inspector": "proof check",
    "episode-analyst": "episode plan",
    "moment-scout": "moment search",
    "motion-director": "motion script",
    "ae-builder": "After Effects build",
    "publish-writer": "publish copy",
    "setup-doctor": "setup check",
}
# A clip id as the engine writes it (clip_ids.py / common.slug: capitals, digits and underscores; C0239, FOO_BAR_INTRO,
# CLIP_6EB37C, EP02_R02_MO). Two ways to find it in the Agent description:
#   1. the convention: the description starts with the id and a colon ("C0239: verify frames"), taken as is;
#   2. otherwise the LAST id-looking token that has a digit or an underscore (a bare capital word is not an id here).
# Codec and format words that look like ids are never taken.
_ID = r"[A-Z0-9][A-Z0-9_]*"
LEAD = re.compile(r"^\s*(" + _ID + r")\s*:")
CLIP = re.compile(r"(?<![A-Za-z0-9_])[A-Z0-9]+(?:_[A-Z0-9]+)*(?![A-Za-z0-9_])")
NOT_CLIP = {"H264", "H265", "X264", "X265", "HEVC", "AVC1", "UTF8", "UTF16", "MP3", "MP4", "M4A", "MOV", "WAV", "AAC",
            "AC3", "MKV", "SRT", "JSON", "XML", "PDF", "PNG", "JPG", "JPEG", "GIF", "NOTE", "TODO", "STEP", "QC", "PPRO",
            "UXP", "RTL", "LTR", "RGB", "RGBA", "CMYK", "HDR", "SDR", "FPS", "LUFS", "NVENC", "CUDA", "GPU", "CPU"}
STATE = {"completed": "done", "failed": "failed", "killed": "stopped", "stopped": "stopped", "error": "failed"}


def _clip(task):
    fields = [task.get(k) for k in ("description", "label", "name")]
    fields = [v for v in fields if isinstance(v, str)]
    for v in fields:                                   # the convention: "C0239: verify frames"
        m = LEAD.match(v)
        if m and len(m.group(1)) >= 3 and m.group(1) not in NOT_CLIP:
            return m.group(1)
    for v in fields:                                   # else the last id-looking token
        for tok in reversed([m.group(0) for m in CLIP.finditer(v)]):
            if len(tok) >= 4 and tok not in NOT_CLIP and (any(c.isdigit() for c in tok) or "_" in tok):
                return tok
    return ""


def _elapsed(start, now):
    try:
        s = float(start)
    except (TypeError, ValueError):
        return ""
    if s > 1e11:          # milliseconds
        s /= 1000.0
    n = int(now - s)
    if n < 0 or n > 86400:
        return ""
    return f"{n // 60}m{n % 60:02d}s" if n >= 60 else f"{n}s"


def row(task, now):
    """The row for one task, or None when it is not a WhyNot Cut agent."""
    kind = task.get("agentType")
    if not isinstance(kind, str) or not kind.startswith("whynot-cut:"):
        return None
    agent = kind.split(":", 1)[1]
    parts = [agent, STAGE.get(agent, "working"), _clip(task) or "-"]
    state = STATE.get(str(task.get("status") or ""), "")
    if state:
        parts.append(state)
    if not state:       # a running timer only while it runs: the payload has no end time, so a finished row would keep growing
        t = _elapsed(task.get("startTime"), now)
        if t:
            parts.append(t)
    return " | ".join(parts)


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        tasks = data.get("tasks") or []
        cols = data.get("columns")
        width = cols if isinstance(cols, int) and cols >= 20 else 100
        now = time.time()
        out = []
        for t in tasks:
            if not isinstance(t, dict) or not isinstance(t.get("id"), str):
                continue
            text = row(t, now)
            if text:
                out.append(json.dumps({"id": t["id"], "content": text[:width]}, ensure_ascii=True))
        if out:
            sys.stdout.write("\n".join(out) + "\n")
    except Exception:       # a status line must never break or slow the panel
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
