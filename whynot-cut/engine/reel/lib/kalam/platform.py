# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (kalam/platform.py); see adobe/tools/README.md. Changes to the upstream file
# (portability audit §3.1/§5), everything else is unchanged:
#   * claude_candidates: the POSIX strings are built with PurePosixPath (upstream built them with Path, which renders
#     "\Users\x\.local\bin\claude" on Windows); the Windows list is unchanged;
#   * new: claude_install_candidates / runnable / claude_command, the WhyNot Cut Claude Code discovery rules ported with a
#     parity test against installer/core/wnc_installer/claude.py (the engine never imports the installer: see the note
#     above claude_install_candidates).
"""What differs between macOS and Windows: which speech backend runs, and where Claude Code lives."""
import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

SANDBOX_ENV = "WHYNOT_TEST_SANDBOX"          # tests/_isolation.py sets it (lib/plat.py SANDBOX_ENV)


def is_windows() -> bool:
    return sys.platform == "win32"


def backend() -> str:
    """"mlx" on a Mac with MLX installed, else "portable" (faster-whisper / ONNX / torch). KALAM_BACKEND overrides."""
    forced = os.environ.get("KALAM_BACKEND")
    if forced in ("mlx", "portable"):
        return forced
    if sys.platform == "darwin" and importlib.util.find_spec("mlx_whisper") is not None:
        return "mlx"
    return "portable"


def claude_candidates(env: dict, home: Path, windows: bool) -> list:
    """places the Claude Code CLI is installed by its native installer, npm or Homebrew"""
    if windows:
        out = [str(home / ".local" / "bin" / "claude.exe")]
        if env.get("APPDATA"):
            out.append(str(Path(env["APPDATA"]) / "npm" / "claude.cmd"))
        return out
    h = PurePosixPath(Path(home).as_posix())          # a POSIX string on every host (Path would use "\" on Windows)
    return [str(h / ".local" / "bin" / "claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]


# ---- WhyNot Cut's Claude Code discovery (3.0 T7.1): the same order and rules as installer/core/wnc_installer/claude.py
# `claude_candidates` and tools/find_claude.py. Ported, not imported: the engine runs without installer/core on its path
# (nothing under engine/reel imports wnc_installer, which pulls in the 1900-line installer base), the installer is another
# track's code, and the engine home may sit away from the plugin folder. tests/test_kalam_engine_correct.py pins the
# parity (same input tree -> same list) against wnc_installer when it can be imported.
def _ver_key(p: Path):
    for part in reversed(p.parts):
        if re.fullmatch(r"\d+(\.\d+)+", part):
            return tuple(int(x) for x in part.split("."))
    return (0,)


def in_sandbox(env=None) -> bool:
    return bool((os.environ if env is None else env).get(SANDBOX_ENV))


def claude_install_candidates(env, home, windows: bool, sandbox: bool = False) -> list:
    """Every Claude Code CLI file on this machine, best first: $CLAUDE_CLI, `claude` on PATH, the fixed native / npm
    install paths, then the CLIs bundled with the desktop app (newest version first). In a sandbox only $WNC_CLAUDE_CLI
    (the test switch) and the bundles under the (fake) home are searched."""
    home = Path(home)
    exe = "claude.exe" if windows else "claude"
    out = []
    if sandbox:
        if env.get("WNC_CLAUDE_CLI"):
            out.append(Path(env["WNC_CLAUDE_CLI"]))
        appdata = home / "AppData" / "Roaming"
    else:
        if env.get("CLAUDE_CLI"):
            out.append(Path(env["CLAUDE_CLI"]))
        which = shutil.which("claude", path=env.get("PATH"))
        if which:
            out.append(Path(which))
        appdata = Path(env.get("APPDATA") or home / "AppData" / "Roaming")
        if windows:
            local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
            out += [local / "Programs" / "claude" / exe, home / ".local" / "bin" / exe, appdata / "npm" / "claude.cmd"]
        else:
            out += [home / ".local" / "bin" / exe, home / ".claude" / "local" / exe, Path("/usr/local/bin") / exe,
                    Path("/opt/homebrew/bin") / exe]
    bundle = (appdata if windows else home / "Library" / "Application Support") / "Claude" / "claude-code"
    found = []
    if bundle.is_dir():
        found += [p for p in bundle.glob(f"*/*/{exe}") if p.is_file()]
        found += [p for p in bundle.glob(f"*/{exe}") if p.is_file()]
    found.sort(key=_ver_key, reverse=True)
    return [p for p in out if p.is_file()] + found


def is_batch(path) -> bool:
    """a Windows batch file (the npm `claude.cmd` shim): started through cmd.exe, so never with caption text on argv"""
    return str(path).lower().endswith((".cmd", ".bat"))


def runnable(path, env=None, windows=None) -> bool:
    """can this file be started? Windows: a file whose extension is in PATHEXT (os.access(X_OK) is true for any file
    there, even a .txt or an extensionless one); elsewhere a file with the execute bit."""
    windows = is_windows() if windows is None else windows
    p = Path(path)
    if not p.is_file():
        return False
    if windows:
        env = os.environ if env is None else env
        exts = [e.strip().lower() for e in (env.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD").split(";") if e.strip()]
        return p.suffix.lower() in exts
    return os.access(str(p), os.X_OK)


CMD_REFUSED = ("Claude Code is installed as a .cmd shim (npm). Windows would start it through cmd.exe, which is not safe "
               "with the caption text on the command line, and its cli.js / claude.exe was not found next to it. "
               "Reinstall Claude Code with its native installer (claude.exe) or run `npm install -g "
               "@anthropic-ai/claude-code` again.")


def claude_command(exe, env=None) -> list:
    """The CLI as a command list. A `.py` / `.sh` (the test stand-ins) run on this interpreter / with bash, like
    wnc_installer.base.stand_in_command. A `.cmd` / `.bat` npm shim is resolved to the program it starts, next to it in
    node_modules/@anthropic-ai/claude-code: bin/claude.exe, else `node cli.js`; when neither is found it is refused
    (RuntimeError with the way out), never run through cmd.exe (BatBadBut: JSON on argv would be re-parsed by cmd)."""
    p = str(exe)
    low = p.lower()
    if low.endswith(".py"):
        return [sys.executable, "-B", p]
    if low.endswith(".sh"):
        return ["bash", p]
    if not is_batch(p):
        return [p]
    env = os.environ if env is None else env
    shim = Path(p).parent
    pkg = shim / "node_modules" / "@anthropic-ai" / "claude-code"
    native = pkg / "bin" / "claude.exe"
    if native.is_file():
        return [str(native)]
    cli_js = pkg / "cli.js"
    if cli_js.is_file():
        node = shim / "node.exe"
        node = str(node) if node.is_file() else shutil.which("node", path=env.get("PATH"))
        if node:
            return [node, str(cli_js)]
    raise RuntimeError(CMD_REFUSED)
