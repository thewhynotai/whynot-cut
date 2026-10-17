# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Background `reel` work at a lower priority so Premiere stays smooth (Phase 4 T4.11, G13-RUN).

The preferences setting `background_priority` (below_normal | normal, default below_normal) decides; the environment
variable WHYNOT_PRIORITY (same values) beats it: the developer's PC and the test suite run at normal
(tests/_isolation.py). Windows: SetPriorityClass(BELOW_NORMAL_PRIORITY_CLASS); macOS and Linux: niceness 10. Child
processes (ffmpeg, Whisper) inherit it. `reel serve` (the panel's engine) is never lowered: cli.main skips it.
The engine never RAISES its own priority: a process already at that level or lower is left alone. A refusal is
ignored ("unsupported"); nothing is printed (stdout is the CLI's JSON). Standard library only.
"""
from __future__ import annotations

import os
import sys

ENV = "WHYNOT_PRIORITY"
CHOICES = ("below_normal", "normal")
DEFAULT = "below_normal"
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
_WIN_LOWER = {0x40, 0x4000}          # IDLE, BELOW_NORMAL: already at or under what we would set
NICE = 10


def _choice(v) -> str | None:
    s = v.strip().lower() if isinstance(v, str) else None
    return s if s in CHOICES else None


def wanted(setting=None, env=None) -> str:
    """below_normal | normal: WHYNOT_PRIORITY, else the setting (read from the preferences when None), else the
    default. An invalid value at any level is skipped, never an error."""
    env = os.environ if env is None else env
    got = _choice(env.get(ENV))
    if got:
        return got
    if setting is None:
        try:
            from . import settings as S
            setting = S.load().get("background_priority")
        except Exception:  # noqa: BLE001  a damaged preferences file never stops a job: the default applies
            setting = None
    return _choice(setting) or DEFAULT


def _kernel32():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k.GetPriorityClass.restype = wintypes.DWORD
    k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.SetPriorityClass.restype = wintypes.BOOL
    return k


def _win_get(kernel32=None) -> int:
    k = kernel32 or _kernel32()
    return int(k.GetPriorityClass(k.GetCurrentProcess()))


def _win_set(cls: int, kernel32=None) -> None:
    k = kernel32 or _kernel32()
    if not k.SetPriorityClass(k.GetCurrentProcess(), cls):
        raise OSError("SetPriorityClass refused")


def apply(setting: str | None = None, *, os_name: str | None = None, setter=None, env=None, getter=None) -> str:
    """Lower this process (and so its children) to BelowNormal unless the setting or WHYNOT_PRIORITY says normal.
    Returns "below_normal", "normal" or "unsupported". Never raises. `setter` / `getter` replace the OS calls (tests:
    an injected setter with no getter means "the current priority is unknown", so the call is made). A process that
    imported tests/_isolation (the test runner) is never lowered by a real OS call, whatever its environment."""
    if wanted(setting, env) == "normal":
        return "normal"
    if setter is None and "_isolation" in sys.modules:
        return "normal"
    osn = os_name or os.name
    try:
        if osn == "nt":
            cur = getter() if getter else (None if setter else _win_get())
            if cur in _WIN_LOWER:
                return "below_normal"
            (setter or _win_set)(BELOW_NORMAL_PRIORITY_CLASS)
            return "below_normal"
        if osn == "posix":                 # macOS and Linux: os.nice is relative, so raise it only up to 10
            cur = getter() if getter else (0 if setter else os.nice(0))
            if cur < NICE:
                (setter or os.nice)(NICE - cur)
            return "below_normal"
    except Exception:  # noqa: BLE001  refused (permissions, sandbox, no os.nice): ignored, the job runs as it is
        return "unsupported"
    return "unsupported"
