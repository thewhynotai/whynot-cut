# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: the tool's folder in the engine home, <engine home>/tools/hush/ (A6b; upstream: ~/Library/Application
Support/Hush, engine.js).

    settings.json           the user's choices (E.readJSON / E.writeJSON 'settings.json')
    presets.json            FR-24: a list of {name, adv} (the upstream shape), saved and loaded by name
    logs/whynot-hush.log    one line per event, ISO time first (E.log); never anything but what the caller passes
    cache/scan-<key>.json   the last 3 scans (PRD 12: "Cache keeps the last 3 scans"; engine.js cleanCache)
    last-scan.json          the scan `reel hush scan` writes without --out; `reel hush plan` reads it by default

A scan is keyed by sequence id + range + track set + the sha256 of the exported audio (Addendum A3 #3), so a changed
cut, range, track choice or audio never reuses an old scan. Everything is user-only (serve.security.private_dir /
open_private: POSIX 0700 / 0600, Windows a protected DACL for the current user), the helpers `reel serve` and the Tidy
store use; JSON is UTF-8 with \\n line ends and no BOM. Same layout and helpers as lib/tidy/store.py (written
separately; the two can share a base class later).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import plat

__all__ = ["Store", "KEEP_SCANS", "home", "log", "load_settings", "save_settings"]

KEEP_SCANS = 3
_KEY = re.compile(r"^[0-9a-f]{64}$")


def _security():
    from serve import security      # engine/reel is on sys.path wherever lib is importable as a package
    return security


def _canon_tracks(tracks):
    """A track set in a canonical form: a list of names (sorted, no repeats) or {group: such a list}."""
    if isinstance(tracks, dict):
        return {str(k): sorted({str(x) for x in v}) for k, v in sorted(tracks.items(), key=lambda kv: str(kv[0]))}
    return sorted({str(x) for x in (tracks or [])})


def _num(x):
    x = float(x)
    return int(x) if x == int(x) else x     # 0 and 0.0 are the same range edge


class Store:
    def __init__(self, engine_home=None):
        self.engine_home = Path(engine_home) if engine_home else plat.engine_home()
        self.home = self.engine_home / "tools" / "hush"
        self.logs = self.home / "logs"
        self.cache_dir = self.home / "cache"
        self.settings_file = self.home / "settings.json"
        self.presets_file = self.home / "presets.json"
        self.log_file = self.logs / "whynot-hush.log"
        self.last_scan_file = self.home / "last-scan.json"   # `reel hush scan` without --out; `plan` reads it by default

    def _dir(self, path: Path) -> Path:
        sec = _security()
        sec.private_dir(self.home)       # parents first: every folder under tools/hush is user-only
        return sec.private_dir(path)

    def write_private(self, path, data: bytes) -> bool:
        """Atomic: a temp file that is user-only from its first byte, then replace. False on failure (nothing changed).
        `path` must be inside the Hush folder."""
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

    def _write_json(self, path: Path, data, compact: bool = False) -> bool:
        try:
            text = json.dumps(data, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 1}))
        except (TypeError, ValueError):
            return False
        return self.write_private(path, (text + "\n").encode("utf-8"))

    @staticmethod
    def _read_json(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

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
        data = self._read_json(self.settings_file, None)
        if isinstance(data, dict):
            out.update(data)
        return out

    def save_settings(self, settings: dict) -> bool:
        return self._write_json(self.settings_file, settings)

    # ----- presets (FR-24)
    def list_presets(self) -> list:
        data = self._read_json(self.presets_file, [])
        return [p for p in data if isinstance(p, dict) and isinstance(p.get("name"), str)] if isinstance(data, list) else []

    def save_preset(self, name, adv: dict) -> bool:
        """Save the advanced settings under `name` (an existing preset of that name is replaced, like the panel does)."""
        name = str(name or "").strip()
        if not name:
            return False
        presets = [p for p in self.list_presets() if p["name"] != name]
        presets.append({"name": name, "adv": dict(adv)})
        return self._write_json(self.presets_file, presets)

    def get_preset(self, name):
        for p in self.list_presets():
            if p["name"] == name:
                return p.get("adv")
        return None

    def delete_preset(self, name) -> bool:
        """True when a preset of that name existed and is gone."""
        presets = self.list_presets()
        rest = [p for p in presets if p["name"] != name]
        return len(rest) != len(presets) and self._write_json(self.presets_file, rest)

    # ----- scan cache
    @staticmethod
    def audio_sha256(path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def cache_key(sequence, range_, tracks, audio_sha256: str) -> str:
        """sha256 of the canonical JSON of (sequence id, range start/end, track set, audio sha256)."""
        start, end = range_
        parts = {"sequence": str(sequence), "range": [_num(start), _num(end)], "tracks": _canon_tracks(tracks),
                 "audio": str(audio_sha256)}
        return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                              .encode("utf-8")).hexdigest()

    def _entries(self) -> list:
        """[(saved_at, key)] of the valid entries, newest first."""
        out = []
        for p in self.cache_dir.glob("scan-*.json"):
            key = p.name[len("scan-"):-len(".json")]
            data = self._read_json(p, None)
            if _KEY.match(key) and isinstance(data, dict) and data.get("key") == key and "saved_at" in data:
                out.append((data["saved_at"], key))
        return sorted(out, reverse=True)

    def cache_list(self) -> list:
        """The cached scan keys, newest first."""
        return [k for _, k in self._entries()]

    def cache_get(self, key):
        """The cached scan of `key` (what cache_put stored), or None."""
        if not isinstance(key, str) or not _KEY.match(key):
            return None
        data = self._read_json(self.cache_dir / ("scan-%s.json" % key), None)
        return data.get("scan") if isinstance(data, dict) and data.get("key") == key else None

    def cache_put(self, key, scan) -> bool:
        """Store a scan under `key` (JSON-able), then keep only the newest KEEP_SCANS entries."""
        if not isinstance(key, str) or not _KEY.match(key):
            return False
        newest = max([t for t, _ in self._entries()] or [0])
        saved_at = max(time.time_ns(), newest + 1)       # strictly newer than everything cached: a total order
        ok = self._write_json(self.cache_dir / ("scan-%s.json" % key), {"key": key, "saved_at": saved_at, "scan": scan})
        for _, old in self._entries()[KEEP_SCANS:]:
            try:
                (self.cache_dir / ("scan-%s.json" % old)).unlink()
            except OSError:
                pass
        return ok


def home() -> Path:
    return Store().home


def log(msg) -> bool:
    return Store().log(msg)


def load_settings(defaults=None) -> dict:
    return Store().load_settings(defaults)


def save_settings(settings: dict) -> bool:
    return Store().save_settings(settings)
