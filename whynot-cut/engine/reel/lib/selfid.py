"""Which `reel` is this, and is it the one on PATH? (field test G66)

A Claude Code session started BEFORE WhyNot Cut was installed (or updated) keeps the bin/ folders of the plugins it
started with on PATH. `reel` then runs the old reel-editor ("environment not installed") or a previous WhyNot Cut,
and the subagents the session spawns inherit the same PATH. So:
  * every WhyNot Cut message names itself (`tag()`: "WhyNot Cut 2.2.0"), so a wrong `reel` is recognisable at once;
  * `scan_path()` (used by `reel doctor`) lists every `reel` on PATH in order, says which plugin each belongs to and
    whether the first one is this plugin's, with the fix: restart Claude Code, or call this plugin's `reel` by its
    full path until then.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .common import PLUGIN_DIR
from .plat import IS_WIN, native_path

DISPLAY = "WhyNot Cut"
NAME = "whynot-cut"


def own_bin() -> Path:
    return PLUGIN_DIR / "bin"


def _manifest(root: Path) -> dict:
    try:
        return json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def plugin_info() -> dict:
    m = _manifest(PLUGIN_DIR)
    return {"name": m.get("name") or NAME, "display_name": m.get("displayName") or DISPLAY,
            "version": m.get("version") or "?", "root": str(PLUGIN_DIR), "bin": str(own_bin())}


def tag() -> str:
    """'WhyNot Cut 2.2.0': what every error and `reel --version` starts with."""
    i = plugin_info()
    return f"{i['display_name']} {i['version']}"


def _norm(p) -> str:
    try:
        return os.path.normcase(os.path.realpath(str(p)))
    except OSError:
        return os.path.normcase(os.path.abspath(str(p)))


def _names() -> list[str]:
    if IS_WIN:
        return ["reel", *("reel" + e.lower() for e in (os.environ.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD").split(";") if e)]
    return ["reel"]


def _find_in(d: Path) -> Path | None:
    for n in _names():
        f = d / n
        if f.is_file() and (IS_WIN or os.access(f, os.X_OK)):
            return f
    return None


def scan_path(path_env: str | None = None) -> dict:
    """Every `reel` on PATH, in order. state: ok (ours is first) | foreign_first (another plugin's, or another copy
    of this one, comes first) | not_on_path (none). Windows PATH entries written Git-Bash style are understood."""
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    mine = _norm(own_bin())
    info = plugin_info()
    hits, seen = [], set()
    for raw in path_env.split(os.pathsep):
        if not raw.strip():
            continue
        d = Path(native_path(raw.strip().strip('"')))
        key = _norm(d)
        if key in seen:
            continue
        seen.add(key)
        f = _find_in(d)
        if not f:
            continue
        m = {} if key == mine else _manifest(d.parent)
        hits.append({"path": str(f), "is_this": key == mine, "plugin": m.get("name"), "version": m.get("version"),
                     "owner": (f"{info['display_name']} {info['version']} (this plugin)" if key == mine else
                               f"the {m['name']} plugin {m.get('version', '?')}" if m.get("name") else
                               "unknown (no plugin manifest next to it)")})
    first = hits[0] if hits else None
    own_full = str(own_bin() / ("reel.cmd" if IS_WIN else "reel"))
    full_path_hint = (f'"{own_full}"' if not IS_WIN else f'& "{own_full}"  (PowerShell) or "{own_bin() / "reel"}" (Git Bash)')
    out = {"ok": bool(first and first["is_this"]), "own_bin": str(own_bin()), "hits": hits, "first": first,
           "this_version": info["version"], "state": "ok" if first and first["is_this"] else
           ("foreign_first" if first else "not_on_path")}
    if out["state"] == "foreign_first":
        what = first["owner"]
        same = first["plugin"] == info["name"]
        out["message"] = (f"`reel` on PATH is {what} at {first['path']}, not {info['display_name']} {info['version']}: "
                          + ("this Claude Code session started before the update and keeps the previous version's folder first"
                             if same else "this Claude Code session started before the install and keeps the old plugin's "
                                          "folder first") + "; subagents inherit it")
    elif out["state"] == "not_on_path":
        out["message"] = (f"no `reel` on PATH: the plugin's bin/ is added to PATH only in sessions started after the "
                          f"install")
    else:
        out["message"] = f"`reel` on PATH is {info['display_name']} {info['version']}"
    out["fix"] = ("restart Claude Code (a new session puts this plugin's bin/ first on PATH). Until then call it by its "
                  f"full path: {full_path_hint}, and give subagents that full path too") if not out["ok"] else None
    return out
