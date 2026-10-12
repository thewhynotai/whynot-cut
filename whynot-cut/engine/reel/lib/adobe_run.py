"""Run an ExtendScript (.jsx) inside After Effects or Photoshop on macOS or Windows (opt-in extras only).

macOS: AppleScript (`DoScriptFile` / `do javascript file`), as verified in production.
Windows: After Effects via `AfterFX.exe -r <jsx>` (hands the script to the running instance, or starts AE);
Photoshop via its COM automation object (`Photoshop.Application.DoJavaScriptFile`) from PowerShell.

Success is never judged from the return value (AE's DoScript always prints 0): callers pass `done()`, a check on the
files the script must write, and these runners wait for it.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from . import plat
from .common import run


def app_name(key: str) -> str | None:
    a = plat.newest_app(key)
    return a["name"] if a else None


def _as_string(s: str) -> str:
    """An AppleScript string literal (quotes and backslashes escaped)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def osascript_argv(app: str, command: str, timeout: int, *args) -> list[str]:
    """osascript with the `on run argv` form (3.0 T2.15, review §10): the script file path travels as an argument,
    never inside the AppleScript source, so a `"` in a client folder name cannot end the string and run code. The app
    name stays a literal (discovered by plat, escaped): AppleScript needs it at compile time for DoScriptFile."""
    return ["osascript", "-e", "on run argv", "-e", f"with timeout of {int(timeout)} seconds",
            "-e", f"tell application {_as_string(app)} to {command}", "-e", "end timeout", "-e", "end run",
            *[str(a) for a in args]]


def run_after_effects(jsx: Path, timeout: int, done: Callable[[], bool] | None = None) -> dict:
    app = plat.newest_app("after_effects")
    if not app:
        return {"status": "UNSUPPORTED", "msg": "After Effects not installed"}
    refused = plat.sandbox_refusal("launch After Effects")                                   # G79: never in tests
    if refused:
        return {"status": "REFUSED", "msg": refused["error"], "how": refused["how"]}
    t0 = time.time()
    if plat.IS_MAC:
        p = run(osascript_argv(app["name"], "DoScriptFile (item 1 of argv)", timeout, jsx),
                check=False, timeout=timeout + 30)
        res = {"returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    else:
        # -r returns at once when AE is already running; when it has to start AE the launcher keeps running, so we
        # never wait on the process itself, only on the files the script writes.
        subprocess.Popen([app["exe"], "-r", str(jsx)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = {"returncode": None, "stdout": "", "stderr": "", "launched": app["exe"]}
        while done is not None and time.time() - t0 < timeout and not done():
            time.sleep(2)
    res.update(app=app["name"], elapsed_s=round(time.time() - t0, 1))
    return res


def run_photoshop(jsx: Path, timeout: int) -> dict:
    app = plat.newest_app("photoshop")
    if not app:
        return {"status": "UNSUPPORTED", "msg": "Photoshop not installed"}
    refused = plat.sandbox_refusal("launch Photoshop")                                       # G79: never in tests
    if refused:
        return {"status": "REFUSED", "msg": refused["error"], "how": refused["how"]}
    t0 = time.time()
    if plat.IS_MAC:
        p = run(osascript_argv(app["name"], "do javascript (POSIX file (item 1 of argv) as alias)", timeout, jsx),
                check=False, timeout=timeout + 30)
    else:
        ps = ("$ErrorActionPreference='Stop'; $app = New-Object -ComObject Photoshop.Application; "
              f"$r = $app.DoJavaScriptFile('{str(jsx).replace(chr(39), chr(39) * 2)}'); Write-Output $r")
        exe = "powershell"
        p = run([exe, "-NoProfile", "-NonInteractive", "-Command", ps], check=False, timeout=timeout + 30)
    return {"app": app["name"], "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip(),
            "elapsed_s": round(time.time() - t0, 1)}


def aerender() -> str | None:
    p = plat.aerender_path()
    return str(p) if p else None
