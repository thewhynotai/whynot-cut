# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Kalam: the tool's folder in the engine home, <engine home>/tools/kalam/ (A6b; upstream: %LOCALAPPDATA%\\Kalam
and ~/Library/Application Support/Kalam, engine.js).

    settings.json           the user's choices (private)
    logs/whynot-kalam.log   one line per event, ISO time first; never anything but what the caller passes
    cache/                  the MOGRT gallery index and thumbnails (lib/kalam/mogrt.py)
    models/                 the Kalam model pack (CTranslate2 Whisper copies, Parakeet ONNX; lib/kalam/setup_models.py)
    hf/                     the Hugging Face cache of the aligner (HF_HOME)

The settings, the log and the per-run files are user-only (serve.security.private_dir / open_private: POSIX 0700 / 0600,
Windows a protected DACL for the current user), the helpers `reel serve` and the Hush / Tidy stores use; cache/ (the MOGRT
index and thumbnails written by lib/kalam/mogrt.py, nothing secret) uses default permissions, written atomically; text is
UTF-8 with \\n line ends and no BOM.
Secrets: the API key reaches the engine only in the per-run settings file, which `take_settings` deletes right after
reading it (A6b gate 3); `redact` / `report_text` keep keys and settings out of every report (Kalam FR-24 rule).
`safe_name` is the JS port's `KalamPlatform.safeName` (adobe/tools/kalam/src/js/platform.js) plus two Windows gaps its review
found: control characters U+0000-U+001F become "-", and CONIN$ / CONOUT$ are reserved device names.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .. import plat

__all__ = ["Store", "default_models_dir", "safe_name", "take_settings", "redact"]

_FORBIDDEN = re.compile('[\\\\/:*?"<>|\\x00-\\x1f]')
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$)", re.IGNORECASE | re.ASCII)


def safe_name(s) -> str:
    """a file name every OS accepts: Windows forbids \\ / : * ? " < > |, control characters, trailing dots and spaces and
    the device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9, CONIN$, CONOUT$; also with an extension: nul.srt); an empty
    result is "_" """
    n = _FORBIDDEN.sub("-", str(s)).rstrip(". ")
    dot = n.find(".")
    base = n if dot < 0 else n[:dot]
    if _RESERVED.fullmatch(base.rstrip(" ")):
        n = base + "_" + n[len(base):]
    return n or "_"


_SECRET_NAMES = {"apikey", "authtoken", "accesstoken", "token", "password", "secret", "settings", "rules", "glossary"}


def _secret_name(key) -> bool:
    return re.sub(r"[^a-z0-9]", "", str(key).lower()) in _SECRET_NAMES


def redact(obj):
    """a copy of obj (dicts / lists) without the entries named like a key, token, password or settings content, at every
    depth; the input is not modified"""
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items() if not _secret_name(k)}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def _is_reparse(path) -> bool:
    """a symbolic link, or on Windows any reparse point (junction, symlink, mount point)"""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def take_settings(path, store=None) -> dict:
    """Read the per-run settings file (JSON, UTF-8, a BOM is accepted) and DELETE it, whatever the content is: the API key
    in it must not stay on disk (A6b gate 3). OSError when it cannot be read or deleted, ValueError when it is not a JSON
    object. PermissionError, with nothing read or deleted, unless the file really lies in the store's run folder
    (<engine home>/tools/kalam/run) or the temp folder (resolved: no ".." or link can lead out), is not a link / reparse
    point, and is not the persistent settings.json: the engine must never delete a file it was merely pointed at."""
    store = store or Store()
    p = Path(path)
    if _is_reparse(p):
        raise PermissionError("refusing to read a link as the per-run settings file: %s" % p.name)
    real = Path(os.path.realpath(p))
    if real == Path(os.path.realpath(store.settings_file)):
        raise PermissionError("refusing to take the persistent settings file: only a per-run settings file is deleted")
    roots = [Path(os.path.realpath(r)) for r in (store.run_dir, tempfile.gettempdir())]
    if not any(real == r or real.is_relative_to(r) for r in roots):
        raise PermissionError("the per-run settings file must be in %s or the temp folder (not %s)" % (store.run_dir, p.parent))
    raw = p.read_bytes()
    try:
        p.unlink()
    except OSError:
        try:
            p.write_bytes(b"")              # cannot delete: at least empty it, then say so
        except OSError:
            pass
        raise OSError("could not delete the settings file after reading it: %s" % p.name) from None
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("the settings file is not a JSON object")
    return data


def _security():
    from serve import security      # engine/reel is on sys.path wherever lib is importable as a package
    return security


def default_models_dir() -> Path:
    """<engine home>/tools/kalam/models: the Kalam model pack (never inside the plugin folder, never vendored)"""
    return plat.engine_home() / "tools" / "kalam" / "models"


class Store:
    def __init__(self, engine_home=None):
        self.engine_home = Path(engine_home) if engine_home else plat.engine_home()
        self.home = self.engine_home / "tools" / "kalam"
        self.logs = self.home / "logs"
        self.cache_dir = self.home / "cache"
        self.models_dir = self.home / "models"
        self.hf_dir = self.home / "hf"
        self.run_dir = self.home / "run"          # the per-run settings files (take_settings deletes them)
        self.settings_file = self.home / "settings.json"
        self.log_file = self.logs / "whynot-kalam.log"

    def _dir(self, path: Path) -> Path:
        sec = _security()
        sec.private_dir(self.home)       # parents first: every folder under tools/kalam is user-only
        return sec.private_dir(path)

    def write_private(self, path, data: bytes) -> bool:
        """Atomic: a temp file that is user-only from its first byte, then replace. False on failure (nothing changed)."""
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        try:
            sec = _security()
            self._dir(path.parent)
            fd = sec.open_private(tmp, os.O_WRONLY | os.O_TRUNC)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
            return True
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            return False

    # ----- the per-run settings file (the API key travels in it; the engine deletes it after reading)
    def ensure_run_dir(self) -> Path:
        """<engine home>/tools/kalam/run/, created user-only (the parents too)"""
        sec = _security()
        sec.private_dir(self.home)
        return sec.private_dir(self.run_dir)

    def new_run_settings(self, settings: dict) -> Path:
        """Write `settings` (UTF-8, LF) to a new kalam-run-<random>.json in the run folder, user-only from its first byte,
        and return its path: what a caller hands to `python -m lib.kalam.engine run --settings`. The engine deletes the file
        after reading it; if the engine refuses it, the caller deletes it."""
        sec = _security()
        folder = self.ensure_run_dir()
        data = (json.dumps(settings, ensure_ascii=False) + "\n").encode("utf-8")
        path = folder / ("kalam-run-%s.json" % secrets.token_hex(8))
        fd = sec.open_private(path, os.O_WRONLY | os.O_EXCL)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    # ----- log
    def log(self, msg) -> bool:
        """Append "<ISO time>  <msg>" (newlines of msg become spaces; a character UTF-8 cannot hold, such as a lone
        surrogate, is written as a backslash escape). Never raises, whatever goes wrong: a log must not stop a run."""
        try:
            sec = _security()
            self._dir(self.logs)
            line = "%s  %s\n" % (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                                 re.sub(r"[\r\n]+", " ", str(msg)))
            fd = sec.open_private(self.log_file, os.O_WRONLY | os.O_APPEND)
            with os.fdopen(fd, "ab") as f:
                f.write(line.encode("utf-8", "backslashreplace"))
            return True
        except Exception:                      # noqa: BLE001
            return False

    def log_tail(self, n: int = 20) -> list:
        try:
            return self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError:
            return []

    # ----- settings (the user's saved choices; the per-run file with the API key is take_settings')
    def load_settings(self, defaults=None) -> dict:
        """`defaults` with the saved settings on top; the defaults alone when there is no usable file."""
        out = dict(defaults or {})
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return out
        if isinstance(data, dict):
            out.update(data)
        return out

    def save_settings(self, settings: dict) -> bool:
        try:
            text = json.dumps(settings, ensure_ascii=False, indent=1)
        except (TypeError, ValueError):
            return False
        return self.write_private(self.settings_file, (text + "\n").encode("utf-8"))

    # ----- report (what the editor copies into a message): never settings, never keys
    def report_text(self, report: dict, secrets=(), log_lines: int = 20) -> str:
        """Plain text of a doctor / run report plus the log tail, LF line ends. Entries named like a key, token or
        settings content are dropped at every depth (`redact`) and any literal in `secrets` is removed from the text."""
        lines = ["WhyNot Kalam report"]
        for k, v in redact(report).items():
            lines.append("%s: %s" % (k, json.dumps(v, ensure_ascii=False, sort_keys=True)))
        tail = self.log_tail(log_lines)
        if tail:
            lines.append("log:")
            lines += ["  " + t for t in tail]
        text = "\n".join(lines) + "\n"
        for s in secrets:
            if s:
                text = text.replace(str(s), "***")
        return text
