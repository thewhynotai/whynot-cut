"""Small thread-pool helper for work that is already a subprocess (ffmpeg) or releases the GIL (PIL, NumPy).

`parallel_map` keeps the INPUT order of the results and collects an error per item instead of stopping at the first one,
so a command that renders several files reports each one exactly as the sequential loop did. Every task runs in a copy
of the caller's contextvars (3.0 T2.17): the Context a `reel serve` request bound with `use_context` is the one the
workers see, never the process-wide fallback.

Interrupting (Ctrl+C, 3.0 T2.14 review I1): the caller waits in short slices, so Windows delivers the KeyboardInterrupt
at once; then no queued item starts, the processes the running items registered with `track()` are killed (with their
children), and `cancelled()` turns true inside the workers so they stop at their next check.
"""
from __future__ import annotations

import contextvars
import subprocess
import sys
import threading
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait

DEFAULT_WORKERS = 3          # ffmpeg encodes use several threads themselves: 3-4 jobs saturate a laptop, more only compete
POLL_S = 0.1                 # the caller wakes this often (a blocked wait cannot take Ctrl+C on Windows)


class Cancelled(Exception):
    """The map was interrupted before this item ran (or while it ran, at a `check()`)."""


class _Run:
    """One parallel_map call: its cancel flag and the live child processes of its workers."""

    def __init__(self):
        self.event = threading.Event()
        self.procs: set = set()
        self.lock = threading.Lock()

    def cancel(self):
        self.event.set()
        with self.lock:
            procs = list(self.procs)
        for p in procs:
            kill_tree(p)


_RUN: contextvars.ContextVar = contextvars.ContextVar("wnc_parallel_run", default=None)


def cancelled() -> bool:
    """True inside a worker whose parallel_map was interrupted."""
    run = _RUN.get()
    return bool(run and run.event.is_set())


def check() -> None:
    """Raise Cancelled when the surrounding parallel_map was interrupted (a long worker calls it between steps)."""
    if cancelled():
        raise Cancelled("interrupted")


def track(proc):
    """Register a child process of this worker: it is killed when the map is interrupted. Killed at once when the map
    already was. -> proc. Outside a parallel_map it does nothing."""
    run = _RUN.get()
    if run is not None:
        with run.lock:
            run.procs.add(proc)
        if run.event.is_set():
            kill_tree(proc)
    return proc


def untrack(proc) -> None:
    run = _RUN.get()
    if run is not None:
        with run.lock:
            run.procs.discard(proc)


def kill_tree(proc) -> None:
    """Kill a child process and whatever it started (Windows: taskkill /T; elsewhere the process itself, ffmpeg starts
    no children). Never raises."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()                      # taskkill could not start (process-creation load) or not Windows
    except OSError:
        pass


def parallel_map(fn, items, workers: int = DEFAULT_WORKERS) -> list:
    """[(True, fn(item)) | (False, the exception fn raised)] in the order of `items`.
    Only `Exception`s are collected. A KeyboardInterrupt / SystemExit in the caller cancels the items not started yet,
    kills the processes the running ones registered with `track()` and is re-raised at once (the running worker
    threads end on their own: their processes are gone and `check()` raises)."""
    items = list(items)
    run = _Run()

    def call(item):
        if run.event.is_set():           # dequeued after the interrupt, before shutdown cancelled it: do not start
            return False, Cancelled("interrupted")
        try:
            return True, fn(item)
        except Exception as e:  # noqa: BLE001  (reported per item by the caller)
            return False, e
    if workers <= 1 or len(items) <= 1:
        return [call(i) for i in items]
    pool = ThreadPoolExecutor(max_workers=min(workers, len(items)), thread_name_prefix="wnc")
    token = _RUN.set(run)
    try:
        futs = [pool.submit(contextvars.copy_context().run, call, i) for i in items]
    finally:
        _RUN.reset(token)
    try:
        pending = set(futs)
        while pending:
            _done, pending = wait(pending, timeout=POLL_S, return_when=FIRST_EXCEPTION)
        res = [f.result() for f in futs]
    except BaseException:
        run.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    return res
