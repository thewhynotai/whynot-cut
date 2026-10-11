"""User preferences: `.claude/whynot-cut.local.md` (YAML frontmatter + free-text notes). Stdlib only (hooks import it).

Looked up nearest first: <dir>/.claude/whynot-cut.local.md for the current folder and its parents, then the clients
folder, then ~/.claude/whynot-cut.local.md (machine-wide). The first file found wins; missing keys take DEFAULTS.
Created by /whynot-cut:start or /whynot-cut:preferences. Never committed (add `.claude/*.local.md` to .gitignore).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

FILE = "whynot-cut.local.md"
DEFAULTS = {
    "editor_name": "",            # how to address the editor
    "language": "en",             # chat language: en | ar
    "approval": "ask",            # ask = stop at Gate 1 every time | auto = proceed after showing the plan (delegated)
    "whisper_model": "large-v3",  # large-v3 (best) | large-v3-turbo (faster) | medium
    "preview_video": True,        # render a watchable MP4 of the plan before approval
    "clients_root": "",           # folder holding the client folders
    "notify_done": True,          # say clearly when a long run finishes
}
CHOICES = {"language": {"en", "ar"}, "approval": {"ask", "auto"},
           "whisper_model": {"large-v3", "large-v3-turbo", "medium", "small"}}


def _parse_scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v.split(" #", 1)[0].strip()


def parse(text: str) -> tuple[dict, str]:
    """Frontmatter (flat key: value) and body. Unknown keys are kept; bad values fall back to defaults."""
    m = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = _parse_scalar(v)
    return fm, m.group(2)


def find(start: Path | None = None) -> Path | None:
    start = Path(start or os.getcwd()).resolve()
    cands = [d / ".claude" / FILE for d in [start, *start.parents]]
    from importlib import import_module      # plat as `lib.plat` (engine) or top-level `plat` (hooks)
    plat = import_module(".plat", __package__) if __package__ else import_module("plat")
    base = plat.clients_root_setting()        # plugin option: env, else the saved option (pointer / settings.json)
    if base:
        cands.append(base / ".claude" / FILE)
    cands.append(Path.home() / ".claude" / FILE)
    return next((c for c in cands if c.is_file()), None)


def load(start: Path | None = None) -> dict:
    """Effective settings + where they came from (`_file`, `_problems`)."""
    f = find(start)
    out = dict(DEFAULTS)
    problems = []
    if f:
        try:
            fm, body = parse(f.read_text(encoding="utf-8"))
        except OSError as e:
            fm, body = {}, ""
            problems.append(f"unreadable: {e}")
        for k, v in fm.items():
            if k in CHOICES and str(v) not in CHOICES[k]:
                problems.append(f"{k}: {v!r} is not one of {sorted(CHOICES[k])}; using {DEFAULTS[k]!r}")
                continue
            out[k] = v
        out["_notes"] = body.strip()
    out["_file"] = str(f) if f else None
    out["_problems"] = problems
    return out


def render(values: dict, notes: str = "") -> str:
    v = dict(DEFAULTS, **{k: val for k, val in values.items() if not k.startswith("_")})

    def fmt(x):
        if isinstance(x, bool):
            return "true" if x else "false"
        if isinstance(x, int):
            return str(x)
        s = str(x).replace('"', '\\"')
        return f'"{s}"'
    lines = ["---"] + [f"{k}: {fmt(val)}" for k, val in v.items()] + ["---", "", notes.strip() or
             "# WhyNot Cut preferences\n\nEdit the values above (or run /whynot-cut:preferences). "
             "Changes apply from the next message; hooks pick them up in the next session."]
    return "\n".join(lines) + "\n"


def save(path: Path, values: dict, notes: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(values, notes), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
