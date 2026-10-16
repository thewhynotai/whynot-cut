"""Perf marks of `reel serve` and the panel (3.0 Addendum G2 hardening H3; budgets S1 / S2 / S3).

One local JSON line per mark in <home>/logs/perf.jsonl:  {"t": <epoch ms>, "mark": "<name>", "ms"?: <n>, "rid"?: "<id>"}
    t     epoch milliseconds (an integer): the daemon's clock for its own marks, the panel's for the panel's;
    mark  one of MARKS: the daemon's SERVE_MARKS or the panel's PANEL_MARKS (session.schema.json perf_mark);
    ms    the duration the mark closes (0 .. MS_MAX, one decimal): since cmd.received for the cmd.* marks after it,
          since the hello for link.welcome_sent, since panel.boot for the panel's boot marks, since ui.click for
          ui.paint;
    rid   pairs marks: the request id of a command, a click sample's id (c-12). RID_RE: a letter or digit, then letters,
          digits, '.', '_', '-', at most 48 characters, so it can hold no path, no space, no name in another script and
          not the 64-character engine token. A rid that does not fit is dropped; the mark is kept.
Every other key is dropped: a line can carry no token, no path, no client or item name (G-ENG-DATA rule 3).
Size: one file of at most MAX_BYTES; past it the file becomes perf.jsonl.1 (the older one is replaced) and a new one
starts, so the folder holds at most 2 x MAX_BYTES. Writes are appends of whole lines under a lock; a failing disk is
logged once and never fails the caller (a mark is never worth a failed command). perf_report.py reads both files.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from pathlib import Path

__all__ = ["SERVE_MARKS", "PANEL_MARKS", "MARKS", "MAX_BYTES", "BATCH_MAX", "MS_MAX", "RID_RE", "perf_path", "clean",
           "PerfLog", "read"]

log = logging.getLogger(__name__)

SERVE_MARKS = ("cmd.received", "cmd.queued", "cmd.claimed", "cmd.first_progress", "cmd.result", "link.welcome_sent")
PANEL_MARKS = ("panel.boot", "panel.first_paint", "link.welcome", "link.first_state", "panel.usable", "ui.click",
               "ui.paint")
MARKS = SERVE_MARKS + PANEL_MARKS
MAX_BYTES = 512 * 1024            # one file; with the rotated one, at most 1 MiB on disk
BATCH_MAX = 50                   # marks in one panel `perf` message (session.schema.json perf.marks maxItems)
MS_MAX = 3_600_000               # an hour: anything longer is not a latency
T_MAX = 10 ** 14                 # epoch ms (year 5138): session.schema.json perf_mark.t maximum
RID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}")
FILE = "perf.jsonl"


def perf_path(home) -> Path:
    return Path(home) / "logs" / FILE


def _num(v, hi):
    """A finite number in [0, hi] (never a bool), else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if not math.isfinite(v) or v < 0 or v > hi:
        return None
    return v


def clean(entry, allowed=MARKS) -> dict | None:
    """The line for one mark: {t, mark, ms?, rid?} with every value checked, or None when the mark or its time is not
    usable. Keys other than these four are dropped; a bad ms or rid is left out."""
    if not isinstance(entry, dict):
        return None
    mark, t = entry.get("mark"), _num(entry.get("t"), T_MAX)
    if not isinstance(mark, str) or mark not in allowed or t is None:
        return None
    out: dict = {"t": int(round(t)), "mark": mark}
    ms = _num(entry.get("ms"), MS_MAX)
    if ms is not None:
        out["ms"] = round(ms, 1) if isinstance(ms, float) else ms
    rid = entry.get("rid")
    if isinstance(rid, str) and RID_RE.fullmatch(rid):
        out["rid"] = rid
    return out


class PerfLog:
    """The daemon's perf file. mark() for the daemon's own marks, extend() for a panel batch."""

    def __init__(self, home, *, max_bytes: int = MAX_BYTES, clock=time.time):
        self.path = perf_path(home)
        self.max_bytes = max_bytes
        self.clock = clock
        self._lock = threading.Lock()
        self._failed = False

    def mark(self, mark: str, *, ms=None, rid=None) -> bool:
        """Append one daemon mark (t = now). False when the mark is not one of MARKS or the write failed."""
        line = clean({"mark": mark, "t": self.clock() * 1000, "ms": ms, "rid": rid})
        return line is not None and self._write([line])

    def extend(self, entries, allowed=PANEL_MARKS) -> int:
        """Append the usable marks of a panel batch (at most BATCH_MAX, panel marks only). Returns how many."""
        if not isinstance(entries, (list, tuple)):
            return 0
        lines = [x for x in (clean(e, allowed) for e in entries[:BATCH_MAX]) if x is not None]
        return len(lines) if lines and self._write(lines) else 0

    def _write(self, lines: list[dict]) -> bool:
        data = "".join(json.dumps(x, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n" for x in lines)
        raw = data.encode("ascii")
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    size = self.path.stat().st_size
                except FileNotFoundError:
                    size = 0
                if size and size + len(raw) > self.max_bytes:
                    os.replace(self.path, self.path.with_name(FILE + ".1"))
                with open(self.path, "ab") as fh:
                    fh.write(raw)
            return True
        except (OSError, ValueError) as e:
            if not self._failed:
                self._failed = True
                log.warning("reel serve: the perf log could not be written (%s); perf marks are skipped",
                            type(e).__name__)
            return False


def read(home, since_ms: float | None = None) -> list[dict]:
    """Every usable mark of perf.jsonl.1 then perf.jsonl (oldest first), at or after since_ms when given. Lines that are
    not JSON, not an object or not a known mark are skipped."""
    p = perf_path(home)
    out: list[dict] = []
    for f in (p.with_name(FILE + ".1"), p):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            try:
                line = clean(json.loads(raw))
            except (ValueError, RecursionError):
                continue
            if line is not None and (since_ms is None or line["t"] >= since_ms):
                out.append(line)
    return out
