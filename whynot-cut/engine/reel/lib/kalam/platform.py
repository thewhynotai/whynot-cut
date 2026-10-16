# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (kalam/platform.py); see adobe/tools/README.md. Changes to the upstream file
# (portability audit §3.1/§5), everything else is unchanged:
#   * claude_candidates: the POSIX strings are built with PurePosixPath (upstream built them with Path, which renders
#     "\Users\x\.local\bin\claude" on Windows); the Windows list is unchanged;
#   * new: claude_install_candidates / runnable / claude_command, the WhyNot Cut Claude Code discovery rules ported with a
#     parity test against installer/core/wnc_installer/claude.py (the engine never imports the installer: see the note
#     above claude_install_candidates);
#   * new: absolute_only. shutil.which() also looks in the current folder on Windows (unless the process has
#     NoDefaultCurrentDirectoryInExePath), so the candidate list keeps the installer's parity but whatever starts a program
#     (correct.find_claude_code, claude_command's node) keeps only absolute paths (Task 10 review I1);
#   * new: find_on_path / iter_on_path. A planted claude.exe in the cwd would be `which`'s first hit, be dropped by that
#     filter and hide the real CLI further down PATH, so find_claude_code and claude_command search every ABSOLUTE PATH
#     folder themselves (PATHEXT order on Windows; relative and empty PATH entries skipped). The candidate RULES are the
#     installer's (claude_install_candidates is unchanged); only the `which` function it calls is replaced
#     (`which=` parameter), and for absolute PATH entries the walk returns what shutil.which returns (tested).
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


def claude_install_candidates(env, home, windows: bool, sandbox: bool = False, which=None) -> list:
    """Every Claude Code CLI file on this machine, best first: $CLAUDE_CLI, `claude` on PATH, the fixed native / npm
    install paths, then the CLIs bundled with the desktop app (newest version first). In a sandbox only $WNC_CLAUDE_CLI
    (the test switch) and the bundles under the (fake) home are searched. `which(name, path=)` defaults to
    shutil.which (the installer's rule); correct.find_claude_code passes the cwd-proof PATH walk instead."""
    home = Path(home)
    which = shutil.which if which is None else which
    exe = "claude.exe" if windows else "claude"
    out = []
    if sandbox:
        if env.get("WNC_CLAUDE_CLI"):
            out.append(Path(env["WNC_CLAUDE_CLI"]))
        appdata = home / "AppData" / "Roaming"
    else:
        if env.get("CLAUDE_CLI"):
            out.append(Path(env["CLAUDE_CLI"]))
        found_on_path = which("claude", path=env.get("PATH"))
        if found_on_path:
            out.append(Path(found_on_path))
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


def absolute_only(paths) -> list:
    """the entries that are absolute paths (str or Path), in order: a CWD-relative `claude.exe` / `node.exe` (what
    shutil.which returns for a program planted in the current folder on Windows) is never started"""
    out = []
    for p in paths:
        s = str(p) if p else ""
        if s and os.path.isabs(s) and Path(s).is_absolute():
            out.append(p)
    return out


def iter_on_path(name: str, path, windows=None, env=None):
    """every runnable `name` in the ABSOLUTE folders of `path` (an os.pathsep list), folder by folder, PATHEXT order inside
    a folder on Windows. Empty, relative and drive-relative entries are skipped: the current folder is never searched
    (shutil.which searches it first on Windows, so a planted file there would win and, once dropped, hide the real one)."""
    windows = is_windows() if windows is None else windows
    env = os.environ if env is None else env
    names = [name]
    if windows:
        exts = [e.strip() for e in (env.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD").split(";") if e.strip()]
        names = []
        for e in exts:
            for variant in (e, e.lower()):
                if name + variant not in names:
                    names.append(name + variant)
    for entry in str(path or "").split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry) or not Path(entry).is_absolute():
            continue
        seen = set()
        for n in names:
            f = os.path.join(entry, n)
            if runnable(f, env, windows) and os.path.normcase(f) not in seen:
                seen.add(os.path.normcase(f))
                yield f


def find_on_path(name: str, path, windows=None, env=None):
    """the first iter_on_path hit, or None"""
    return next(iter_on_path(name, path, windows, env), None)


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


class CmdShimRefused(RuntimeError):
    """a `.cmd` npm shim that cannot be resolved to a program we may start; str(e) is the how (the way out)"""
    code = "cmd_shim_refused"


CMD_REFUSED = ("Claude Code is installed as a .cmd shim (npm). Windows would start it through cmd.exe, which is not safe "
               "with the caption text on the command line, and its cli.js / claude.exe was not found next to it. "
               "Reinstall Claude Code with its native installer (claude.exe) or run `npm install -g "
               "@anthropic-ai/claude-code` again.")


NODE_REFUSED = ("Claude Code is installed as an npm shim that runs on Node.js (cli.js), but no usable Node.js was found: "
                "the only `node` on PATH is a .cmd/.bat file or not an absolute path (a program in the current folder is "
                "never used). Install Node.js (nodejs.org) so that node.exe is on PATH, or reinstall Claude Code with its "
                "native installer (claude.exe).")


def claude_command(exe, env=None, windows=None) -> list:
    """The CLI as a command list. A `.py` / `.sh` (the test stand-ins) run on this interpreter / with bash, like
    wnc_installer.base.stand_in_command. A `.cmd` / `.bat` npm shim is resolved to the program it starts, next to it in
    node_modules/@anthropic-ai/claude-code: bin/claude.exe, else `node cli.js`; when neither is found it is refused
    (CmdShimRefused, a RuntimeError, with the way out), never run through cmd.exe (BatBadBut: JSON on argv would be re-parsed by cmd)."""
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
        beside = shim / "node.exe"
        found = [beside] if beside.is_file() else []
        found += [n for n in iter_on_path("node", env.get("PATH"), windows, env) if not is_batch(n)]
        usable = [str(n) for n in absolute_only(found) if not is_batch(n)]      # I1: never a CWD-relative node
        if usable:
            return [usable[0], str(cli_js)]
        raise CmdShimRefused(NODE_REFUSED)
    raise CmdShimRefused(CMD_REFUSED)
