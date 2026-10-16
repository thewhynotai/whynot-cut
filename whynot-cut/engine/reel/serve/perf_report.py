"""The p95 of each speed budget from the perf marks (3.0 Addendum G2 hardening H3).

    python -m serve.perf_report [--since <ISO time>] [--home <engine home>]     (engine/reel on sys.path)
    python <plugin>/engine/reel/serve/perf_report.py [...]
    reel perf-report [...]                                                      (the CLI wrapper calls main(argv))

Budgets (docs/adobe/g2-reliability-speed-gaps.md):
    S1  first usable state   panel.boot -> panel.usable (the first engine state on screen); link.first_state when no
                             panel.usable mark exists                                                     <= 1500 ms
    S2  click to paint       ui.click -> ui.paint (sampled clicks)                                         <=  100 ms
    S3  command to progress  cmd.received -> cmd.first_progress (the first progress the requester sees)    <= 2000 ms
A sample is the end mark's `ms`; an end mark without one is paired with its start: the same rid (S2, S3), or the
latest panel.boot before it (S1). p95 is the nearest rank: the ceil(0.95 n)-th smallest sample.
Prints a plain table and exits 0 when every budget with samples is met (no samples = "no data", not a miss), 1 when a
p95 is over its budget, 2 on a usage error (an unreadable --since).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

if not __package__:                       # run as a file: engine/reel on sys.path, never this folder itself
    _here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path if not p or Path(p).resolve() != _here]
    sys.path.insert(0, str(_here.parent))
    from serve import perf                # noqa: E402
else:
    from . import perf

__all__ = ["BUDGETS", "LABELS", "p95", "samples", "report", "format_table", "main"]

BUDGETS = {"S1": 1500, "S2": 100, "S3": 2000}
LABELS = {"S1": "first usable state (panel.boot -> panel.usable)",
          "S2": "click to paint (ui.click -> ui.paint)",
          "S3": "command to first progress (cmd.received -> cmd.first_progress)"}


def p95(values) -> float | None:
    """Nearest-rank 95th percentile; None for no values."""
    xs = sorted(values)
    if not xs:
        return None
    rank = (95 * len(xs) + 99) // 100                # ceil(0.95 n) in integers: no float rounding at the edges
    return xs[max(1, rank) - 1]


def _durations(marks: list[dict], start: str, end: str, *, by_rid: bool) -> list[float]:
    out: list[float] = []
    last_start: dict = {}                            # rid (or None) -> the t of its latest start mark
    for m in sorted(marks, key=lambda x: x["t"]):
        key = m.get("rid") if by_rid else None
        if m["mark"] == start:
            last_start[key] = m["t"]
        elif m["mark"] == end:
            if "ms" in m:
                out.append(m["ms"])
            elif (by_rid and key is None) or key not in last_start:
                continue
            else:
                out.append(m["t"] - last_start[key])
    return out


def samples(marks: list[dict]) -> dict[str, list[float]]:
    s1 = _durations(marks, "panel.boot", "panel.usable", by_rid=False)
    if not s1:
        s1 = _durations(marks, "panel.boot", "link.first_state", by_rid=False)
    return {"S1": s1,
            "S2": _durations(marks, "ui.click", "ui.paint", by_rid=True),
            "S3": _durations(marks, "cmd.received", "cmd.first_progress", by_rid=True)}


def report(marks: list[dict]) -> list[dict]:
    """One row per budget: {id, label, budget_ms, n, p95_ms, ok} (ok None: no samples)."""
    rows = []
    for bid, xs in samples(marks).items():
        v = p95(xs)
        rows.append({"id": bid, "label": LABELS[bid], "budget_ms": BUDGETS[bid], "n": len(xs), "p95_ms": v,
                     "ok": None if v is None else v <= BUDGETS[bid]})
    return rows


def _num(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def format_table(rows: list[dict]) -> str:
    head = ("budget", "what", "samples", "p95 ms", "limit ms", "verdict")
    body = [(r["id"], r["label"], str(r["n"]), "-" if r["p95_ms"] is None else _num(r["p95_ms"]), str(r["budget_ms"]),
             "no data" if r["ok"] is None else ("ok" if r["ok"] else "MISS")) for r in rows]
    widths = [max(len(x[i]) for x in [head, *body]) for i in range(len(head))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*head), fmt.format(*("-" * w for w in widths)), *(fmt.format(*b) for b in body)]
    return "\n".join(x.rstrip() for x in lines)


def _since_ms(text: str) -> float:
    t = _dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00").replace("z", "+00:00"))
    if t.tzinfo is None:
        t = t.astimezone()                           # a local time without an offset: this machine's zone
    return t.timestamp() * 1000


def main(argv=None, *, out=None) -> int:
    """`reel perf-report` / `python -m serve.perf_report`: prints the table; 0 = every budget met (or no data), 1 = a
    miss, 2 = a usage error."""
    out = out if out is not None else sys.stdout
    ap = argparse.ArgumentParser(prog="reel perf-report", description="p95 of the WhyNot Cut speed budgets S1-S3 from "
                                 "<engine home>/logs/perf.jsonl")
    ap.add_argument("--since", default=None, help="only marks at or after this ISO time (e.g. 2026-10-16T09:00:00Z)")
    ap.add_argument("--home", default=None, help=argparse.SUPPRESS)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0) if e.code in (0, None) else 2
    since = None
    if a.since:
        try:
            since = _since_ms(a.since)
        except (ValueError, OverflowError, OSError):
            print(f"--since is not an ISO time: {a.since[:64]!r}", file=out)
            return 2
    if a.home:
        home = Path(a.home)
    else:
        try:
            from lib.plat import engine_home
        except ImportError:                          # run as reel.serve.perf_report from engine/: put engine/reel first
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from lib.plat import engine_home
        home = engine_home()
    rows = report(perf.read(home, since))
    print(format_table(rows), file=out)
    return 1 if any(r["ok"] is False for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
