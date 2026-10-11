#!/usr/bin/env python3
"""Find a Claude Code CLI on this machine, even when `claude` is not on PATH.

    python tools/find_claude.py            -> prints the path (exit 1 if none)
    python tools/find_claude.py --json     -> {"path": ..., "version": ..., "candidates": [...]}

Search order: $CLAUDE_CLI, `claude` on PATH, the CLI bundled with the Claude desktop app
(Windows: %APPDATA%\\Claude\\claude-code\\<ver>\\<hash>\\claude.exe; macOS:
~/Library/Application Support/Claude/claude-code/<ver>/<hash>/claude), then common npm/native install folders.
The newest version wins. The installer (installer/core) uses the same rules.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _ver_key(p: Path):
    for part in reversed(p.parts):
        if re.fullmatch(r"\d+(\.\d+)+", part):
            return tuple(int(x) for x in part.split("."))
    return (0,)


def candidates(env=None, home=None, platform=None):
    env = os.environ if env is None else env
    home = Path(home or Path.home())
    platform = platform or sys.platform
    out = []
    if env.get("CLAUDE_CLI"):
        out.append(Path(env["CLAUDE_CLI"]))
    which = shutil.which("claude")
    if which:
        out.append(Path(which))
    exe = "claude.exe" if platform == "win32" else "claude"
    bundles = []
    if platform == "win32":
        appdata = Path(env.get("APPDATA") or home / "AppData" / "Roaming")
        bundles.append(appdata / "Claude" / "claude-code")
        local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
        out += [local / "Programs" / "claude" / exe, home / ".local" / "bin" / exe,
                appdata / "npm" / "claude.cmd"]
    else:
        bundles.append(home / "Library" / "Application Support" / "Claude" / "claude-code")
        out += [home / ".local" / "bin" / exe, home / ".claude" / "local" / exe,
                Path("/usr/local/bin") / exe, Path("/opt/homebrew/bin") / exe]
    found = []
    for b in bundles:
        if b.is_dir():
            found += [p for p in b.glob(f"*/*/{exe}") if p.is_file()]
            found += [p for p in b.glob(f"*/{exe}") if p.is_file()]
    found.sort(key=_ver_key, reverse=True)
    return [p for p in out if p.is_file()] + found


def find_claude(env=None, home=None, platform=None):
    c = candidates(env, home, platform)
    return c[0] if c else None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    c = candidates()
    path = c[0] if c else None
    if "--json" in argv:
        version = None
        if path:
            try:
                version = subprocess.run([str(path), "--version"], capture_output=True, text=True,
                                         timeout=60).stdout.strip() or None
            except (OSError, subprocess.TimeoutExpired):
                version = None
        print(json.dumps({"path": str(path) if path else None, "version": version,
                          "candidates": [str(p) for p in c]}, indent=2))
    elif path:
        print(path)
    else:
        print("Claude Code CLI not found (install the Claude desktop app or set CLAUDE_CLI)", file=sys.stderr)
    return 0 if path else 1


if __name__ == "__main__":
    sys.exit(main())
