# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Tidy: the tool's folder in the engine home, <engine home>/tools/tidy/ (A6b; upstream: ~/Library/Application
Support/Tidy, E.HOME).

    settings.json           the user's choices (E.loadSettings / E.saveSettings)
    logs/whynot-tidy.log    one line per event, ISO time first (E.log); never anything but what the caller passes
    sync/<tag>.wav          temporary WAVs of the sound sync (E.tempWav / E.removeFile): the caller removes them in a
                            `finally` with remove(path)

Everything is user-only (serve.security.private_dir / open_private: POSIX 0700 / 0600, Windows a protected DACL for
the current user), the same helpers `reel serve` uses for its own files.
NOTE: written standalone. The WhyNot Hush store (Task 7) had not landed when this was written; the two tools can share
one base class later, the file layout and the helpers they call are the same.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .. import plat

__all__ = ["Store", "home", "settings_path", "log", "load_settings", "save_settings", "temp_wav", "remove"]


def _security():
    from serve import security      # engine/reel is on sys.path wherever lib is importable as a package
    return security


class Store:
    def __init__(self, engine_home=None):
        self.engine_home = Path(engine_home) if engine_home else plat.engine_home()
        self.home = self.engine_home / "tools" / "tidy"
        self.logs = self.home / "logs"
        self.sync_dir = self.home / "sync"
        self.settings_file = self.home / "settings.json"
        self.log_file = self.logs / "whynot-tidy.log"

    def _dir(self, path: Path) -> Path:
        sec = _security()
        sec.private_dir(self.home)       # parents first: every folder under tools/tidy is user-only
        return sec.private_dir(path)

    # ----- log
    def log(self, msg) -> bool:
        """Append "<ISO time>  <msg>" (newlines of msg become spaces). Never raises: a log must not stop a run."""
        try:
            sec = _security()
            self._dir(self.logs)
            line = "%s  %s\n" % (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                                 re.sub(r"[\r\n]+", " ", str(msg)))
            fd = sec.open_private(self.log_file, os.O_WRONLY | os.O_APPEND)
            with os.fdopen(fd, "ab") as f:
                f.write(line.encode("utf-8"))
            return True
        except OSError:
            return False

    # ----- settings
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
        """Write settings.json atomically (a temp file, user-only from the first byte, then replace). False on failure."""
        tmp = self.settings_file.with_name("settings.json.tmp")
        try:
            sec = _security()
            self._dir(self.home)
            fd = sec.open_private(tmp, os.O_WRONLY | os.O_TRUNC)
            with os.fdopen(fd, "wb") as f:
                f.write(json.dumps(settings).encode("utf-8"))
            os.replace(tmp, self.settings_file)
            return True
        except (OSError, TypeError, ValueError):
            try:
                tmp.unlink()
            except OSError:
                pass
            return False

    # ----- temporary sync WAVs
    def temp_wav(self, tag) -> Path:
        """<home>/sync/<tag>.wav (the folder is created user-only); the tag is reduced to letters, digits . _ -."""
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(tag)).strip(".") or "tmp"
        return self._dir(self.sync_dir) / (safe + ".wav")

    def remove(self, path) -> bool:
        """Delete a temporary file. Only files directly inside sync/ are ever removed (anything else: False, untouched).
        True when the file is gone afterwards."""
        try:
            p = Path(path)
            if p.parent.resolve() != self.sync_dir.resolve():
                return False
            p.unlink(missing_ok=True)
            return not p.exists()
        except OSError:
            return False


def home() -> Path:
    return Store().home


def settings_path() -> Path:
    return Store().settings_file


def log(msg) -> bool:
    return Store().log(msg)


def load_settings(defaults=None) -> dict:
    return Store().load_settings(defaults)


def save_settings(settings: dict) -> bool:
    return Store().save_settings(settings)


def temp_wav(tag) -> Path:
    return Store().temp_wav(tag)


def remove(path) -> bool:
    return Store().remove(path)
