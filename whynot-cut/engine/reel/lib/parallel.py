"""Small thread-pool helper for work that is already a subprocess (ffmpeg) or releases the GIL (PIL, NumPy).

`parallel_map` keeps the INPUT order of the results and collects an error per item instead of stopping at the first one,
so a command that renders several files reports each one exactly as the sequential loop did. Every task runs in a copy
of the caller's contextvars (3.0 T2.17): the Context a `reel serve` request bound with `use_context` is the one the
workers see, never the process-wide fallback.
"""
from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor

DEFAULT_WORKERS = 3          # ffmpeg encodes use several threads themselves: 3-4 jobs saturate a laptop, more only compete


def parallel_map(fn, items, workers: int = DEFAULT_WORKERS) -> list:
    """[(True, fn(item)) | (False, the exception fn raised)] in the order of `items`.
    Only `Exception`s are collected: SystemExit / KeyboardInterrupt still end the command (after the running tasks)."""
    items = list(items)

    def call(item):
        try:
            return True, fn(item)
        except Exception as e:  # noqa: BLE001  (reported per item by the caller)
            return False, e
    if workers <= 1 or len(items) <= 1:
        return [call(i) for i in items]
    with ThreadPoolExecutor(max_workers=min(workers, len(items)), thread_name_prefix="wnc") as pool:
        futs = [pool.submit(contextvars.copy_context().run, call, i) for i in items]
        return [f.result() for f in futs]
