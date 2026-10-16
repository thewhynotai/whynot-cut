"""Perf marks of `reel serve` and the panel (3.0 Addendum G2 hardening H3; budgets S1 / S2 / S3).

One local JSON line per mark in <home>/logs/perf.jsonl:  {"t": <epoch ms>, "mark": "<name>", "ms"?: <n>, "rid"?: "<h>",
"s"?: "<session>"}
    t     epoch milliseconds (an integer): the daemon's clock for its own marks, the panel's for the panel's;
    mark  one of MARKS: the daemon's SERVE_MARKS or the panel's PANEL_MARKS (session.schema.json perf_mark);
    ms    the duration the mark closes (0 .. MS_MAX, one decimal): since cmd.received for the cmd.* marks after it,
          since the hello for link.welcome_sent, since panel.boot for the panel's boot marks, since ui.click for
          ui.paint;
    rid   pairs marks (a command's request id, a click sample's id), written ONLY as a 12-hex HMAC-SHA256 under a salt
          made for this daemon run (PerfLog.rid): a CLI id that holds a name, or a prefix of the token, never reaches
          the file. Pairing works within a run, which is all perf_report needs. A raw id must first fit RID_RE (a letter
          or digit, then letters, digits, '.', '_', '-', at most 64), else the rid is dropped and the mark kept;
    s     the panel session the mark came from (PerfLog.new_session: this run's 6-hex tag + a counter), so the report
          pairs a panel's marks with that panel's own boot, never another's.
Every other key is dropped: a line can carry no token, no path, no client or item name (G-ENG-DATA rule 3).
Writes leave the caller at once: lines go through a bounded queue (QUEUE_MAX batches; a full queue drops the batch and
counts it) to one daemon writer thread, so the event loop never waits on the disk. flush() waits for what is queued;
close() writes it and stops the thread (App.close, within its budget).
Size: one file of at most MAX_BYTES; past it the file becomes perf.jsonl.1 (the older one is replaced) and a new one
starts. When Windows refuses the rename (WinError 32: a reader or the antivirus holds the file), the line is appended
anyway while the file stays under 2 x MAX_BYTES; past that it is skipped. A refused rename is tried again only after
RENAME_RETRY_S (on the monotonic clock), never once per line. A failing disk is logged once per failing
episode (a good write ends the episode) and never fails the caller. perf_report.py reads both files.
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import logging
import math
import os
import queue
import re
import secrets
import threading
import time
from pathlib import Path

__all__ = ["SERVE_MARKS", "PANEL_MARKS", "MARKS", "MAX_BYTES", "BATCH_MAX", "MS_MAX", "QUEUE_MAX", "RID_RE",
           "perf_path", "clean", "PerfLog", "read"]

log = logging.getLogger(__name__)

SERVE_MARKS = ("cmd.received", "cmd.queued", "cmd.claimed", "cmd.first_progress", "cmd.result", "link.welcome_sent")
PANEL_MARKS = ("panel.boot", "panel.first_paint", "link.welcome", "link.first_state", "panel.usable", "ui.click",
               "ui.paint")
MARKS = SERVE_MARKS + PANEL_MARKS
MAX_BYTES = 512 * 1024            # one file; with the rotated one at most 1 MiB on disk (2 x while a rename is refused)
BATCH_MAX = 50                   # marks in one panel `perf` message (session.schema.json perf.marks maxItems)
MS_MAX = 3_600_000               # an hour: anything longer is not a latency
T_MAX = 10 ** 14                 # epoch ms (year 5138): session.schema.json perf_mark.t maximum
QUEUE_MAX = 256                  # batches waiting for the writer thread
RENAME_RETRY_S = 5.0             # a refused rotation is tried again after this
RID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SID_RE = re.compile(r"[0-9a-f]{6}-[0-9]{1,9}")
FILE = "perf.jsonl"
_STOP = object()


def perf_path(home) -> Path:
    return Path(home) / "logs" / FILE


def _num(v, hi):
    """A finite number in [0, hi] (never a bool), else None. A huge int (math.isfinite raises OverflowError) is None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        if not math.isfinite(v) or v < 0 or v > hi:
            return None
    except OverflowError:
        return None
    return v


def clean(entry, allowed=MARKS) -> dict | None:
    """The line for one mark: {t, mark, ms?, rid?, s?} with every value checked, or None when the mark or its time is
    not usable. Other keys are dropped; a bad ms, rid or s is left out. (No hashing here: PerfLog hashes a raw rid.)"""
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
    s = entry.get("s")
    if isinstance(s, str) and SID_RE.fullmatch(s):
        out["s"] = s
    return out


class PerfLog:
    """The daemon's perf file. mark() for the daemon's own marks, extend() for a panel batch; both return at once."""

    def __init__(self, home, *, max_bytes: int = MAX_BYTES, clock=time.time, queue_max: int = QUEUE_MAX,
                 mono=time.monotonic):
        self.path = perf_path(home)
        self.max_bytes = max_bytes
        self.clock = clock
        self.mono = mono                                  # the rename back-off and close()'s deadline
        self._rename_after = None                         # mono time before which a refused rename is not retried
        self.dropped = 0                                  # marks lost to a full queue
        self._salt = secrets.token_bytes(16)              # this run's: a rid hash means nothing after a restart
        self._run = secrets.token_hex(3)
        self._sessions = itertools.count(1)
        self._q: queue.Queue = queue.Queue(maxsize=max(1, queue_max))
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._failed = False

    # -------------------------------------------------------------------------------------------- ids
    def rid(self, raw: str) -> str:
        """What the file holds for a request or sample id: 12 hex of an HMAC under this run's salt."""
        return hmac.new(self._salt, raw.encode("utf-8"), hashlib.sha256).hexdigest()[:12]

    def new_session(self) -> str:
        """A tag for one panel session's marks (this run's 6 hex + a counter): never the session id itself."""
        return f"{self._run}-{next(self._sessions)}"

    def _line(self, entry, allowed, session=None) -> dict | None:
        line = clean(entry, allowed)
        if line is None:
            return None
        line.pop("s", None)                               # a session tag comes from the daemon, never the entry
        if "rid" in line:
            line["rid"] = self.rid(line["rid"])
        if session is not None and SID_RE.fullmatch(session):
            line["s"] = session
        return line

    # -------------------------------------------------------------------------------------------- queueing
    def mark(self, mark: str, *, ms=None, rid=None) -> bool:
        """Queue one daemon mark (t = now). False when the mark is not one of MARKS, the queue is full or the log is
        closed."""
        line = self._line({"mark": mark, "t": self.clock() * 1000, "ms": ms, "rid": rid}, MARKS)
        return line is not None and self._enqueue([line])

    def extend(self, entries, allowed=PANEL_MARKS, session: str | None = None) -> int:
        """Queue the usable marks of a panel batch (at most BATCH_MAX, panel marks only), tagged with the session.
        Returns how many."""
        if not isinstance(entries, (list, tuple)):
            return 0
        lines = [x for x in (self._line(e, allowed, session) for e in entries[:BATCH_MAX]) if x is not None]
        return len(lines) if lines and self._enqueue(lines) else 0

    def _enqueue(self, lines: list[dict]) -> bool:
        with self._lock:
            if self._closed:
                return False
            try:
                self._q.put_nowait(lines)
            except queue.Full:
                self.dropped += len(lines)
                return False
            if self._thread is None:
                self._thread = threading.Thread(target=self._run_writer, name="reel-serve-perf", daemon=True)
                self._thread.start()
        return True

    def flush(self, timeout: float = 2.0) -> bool:
        """Wait until every line queued before this call is written (or dropped by a failing disk). False on timeout."""
        with self._lock:
            thread = self._thread
        if thread is None or not thread.is_alive():
            return True
        deadline = self.mono() + timeout
        done = threading.Event()
        try:
            self._q.put(done, timeout=timeout)            # never under the lock: marks keep queueing (or dropping)
        except queue.Full:
            return False
        return done.wait(max(0.0, deadline - self.mono()))

    def close(self, timeout: float = 0.5) -> None:
        """Write what is queued and stop the writer within ONE deadline of `timeout` seconds (queueing the stop and
        the join share it; the thread is a daemon either way). Later marks are refused."""
        deadline = self.mono() + timeout
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is None or not thread.is_alive():
            return
        try:
            self._q.put(_STOP, timeout=timeout)
        except queue.Full:
            return
        thread.join(max(0.0, deadline - self.mono()))

    def _run_writer(self) -> None:
        while True:
            item = self._q.get()
            if item is _STOP:
                return
            if isinstance(item, threading.Event):
                item.set()
                continue
            batch = list(item)
            while len(batch) < 4 * BATCH_MAX:             # whatever else is waiting: one open for all of it
                try:
                    nxt = self._q.get_nowait()
                except queue.Empty:
                    break
                if nxt is _STOP or isinstance(nxt, threading.Event):
                    self._write(batch)
                    batch = []
                    if nxt is _STOP:
                        return
                    nxt.set()
                    continue
                batch.extend(nxt)
            if batch:
                self._write(batch)

    # -------------------------------------------------------------------------------------------- the file
    def _fail(self, e: BaseException, what: str) -> None:
        if not self._failed:
            self._failed = True
            log.warning("reel serve: the perf log %s (%s); perf marks are skipped meanwhile", what, type(e).__name__)

    def _append(self, raw: bytes) -> None:
        with open(self.path, "ab") as fh:
            fh.write(raw)

    def _rotate(self, size: int, n: int) -> int | None:
        """Make room for n more bytes: the new size (0 after a rotation), or None when the line must be skipped. A
        refused rename is not tried again before RENAME_RETRY_S has passed."""
        err: OSError | None = None
        if self._rename_after is None or self.mono() >= self._rename_after:
            try:
                os.replace(self.path, self.path.with_name(FILE + ".1"))
                self._rename_after = None
                return 0
            except OSError as e:                          # WinError 32: a reader or the antivirus holds it
                err = e
                self._rename_after = self.mono() + RENAME_RETRY_S
        if size + n > 2 * self.max_bytes:
            self._fail(err or PermissionError("rename refused"), "could not be rotated and is full")
            return None
        if err is not None:
            self._fail(err, "could not be rotated (appending meanwhile)")
        return size

    def _write(self, lines: list[dict]) -> bool:
        """Append the lines, rotating whenever the next one would pass the cap (so a file never holds more than
        max_bytes, or 2 x while a rotation is refused). A write that lands in a normal-size file ends a failing
        episode."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                size = self.path.stat().st_size
            except FileNotFoundError:
                size = 0
            chunk = b""
            for x in lines:
                b = (json.dumps(x, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
                if size + len(chunk) + len(b) > self.max_bytes and size + len(chunk) > 0:
                    if chunk:
                        self._append(chunk)
                        size, chunk = size + len(chunk), b""
                    room = self._rotate(size, len(b))
                    if room is None:
                        continue
                    size = room
                chunk += b
            if chunk:
                self._append(chunk)
                size += len(chunk)
        except (OSError, ValueError) as e:
            self._fail(e, "could not be written")
            return False
        if self._failed and size <= self.max_bytes:
            self._failed = False                          # a good write in a normal-size file ends the episode
        return True


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
            except (ValueError, RecursionError, OverflowError):
                continue
            if line is not None and (since_ms is None or line["t"] >= since_ms):
                out.append(line)
    return out
