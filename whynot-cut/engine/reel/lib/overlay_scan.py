"""Intake overlay scan: finds name supers / lower thirds burned into a finished episode (field test G65).

The 6-frame intake sheet is too sparse for them: a name super is on screen for ~3 s, usually starts right at a camera
cut, and a guest's super can come at 16:55, long after the first minutes. So the whole episode is scanned once at one
thumbnail (320x180) per second, and every moment where a *bar* appears or disappears in the lower half of the frame
is nominated; the intake-inspector then looks at those frames (and at a regular sample of the first three minutes).

What it looks for (numpy only; no new dependency): a lower third is a rectangle painted over the picture, so when it
appears TWO long, parallel, horizontal colour edges (its top and bottom) appear together, a few percent of the frame
height apart. Frame t is compared with the frames REF_S seconds before and after it (the super is gone by then):
  * a side where almost the whole picture differs (a cut, a full-screen card) is ignored; the other side still
    works, so a super that starts exactly at a camera cut is found;
  * edges that exist in one frame and not in the other (within one row) are "new"; a bar is a pair of new edges at
    a distance of DMIN..DMAX rows that overlap over at least LW columns;
  * the frame that owns the new edges is the one that shows the bar, so the event knows which of the two it is;
  * a bar that holds for 2+ seconds is an event; events within a few seconds of each other merge.
Hands, heads and torsos move without producing long straight edges, so they are not nominated; a static overlay
(a logo that never leaves) is the overview sheet's job. Burned subtitles and card transitions can still show up
as candidates: that costs the inspector one more tile, never a missed super.

Measured on a real 34:41 podcast (1080p H.264) with two name supers (3 s each, at 01:26 and 16:53, both starting at
a camera cut): they came out as the two strongest of 11 events, and the whole scan took about 70 s (decoding is ~85 %
of it). Memory stays small (chunks of 5 minutes) and a time budget ends the scan early (`complete: false`).
"""
from __future__ import annotations

import subprocess
import time

import numpy as np

from .common import ffmpeg_exe

TH_W, TH_H = 320, 180            # thumbnail size the scan works on
STEP_S = 1.0                     # one thumbnail per second
REF_S = 4                        # compare with the frames this many seconds before / after
TAU = 28                         # a pixel "changed" when some channel moved by more than this (0-255)
G_MAX = 0.18                     # a side where more than this fraction of the frame changed is a cut/card: ignored
LOW_FRAC = 0.5                   # only the lower half of the frame is searched
TE = 20                          # colour step across a row that makes a horizontal edge pixel
LW = 48                          # an edge run is at least this many columns (15 % of the width), COV of them edge
COV = 0.8
DMIN, DMAX = 7, 30               # top-to-bottom distance of a bar in rows (4-17 % of the frame height)
FULL_COLS = 96 - LW + 1          # a bar >= 96 px wide (30 %) puts this many start columns on both edges: score 1.0
MIN_SCORE = 0.35                 # pair score for a hit
MERGE_GAP_S = REF_S + 2          # hits this close (and overlapping) belong to one event
MIN_SUPPORT = 2                  # distinct seconds a bar must show for to be an event
MAX_EVENTS = 12
HEAD_S, HEAD_STEP_S = 180.0, 10.0      # name supers live in the first minutes: a regular sample there as well
CHUNK_S = 300.0
BUDGET_S = 300.0


def dense_times(duration_s: float, head_s: float = HEAD_S, step_s: float = HEAD_STEP_S) -> list[float]:
    """Regular sample of the first `head_s` seconds (every `step_s`, starting half a step in), clear of the end."""
    out, t = [], step_s / 2
    limit = min(head_s, duration_s - 1.0)
    while t < limit:
        out.append(round(t, 3))
        t += step_s
    return out


def tc(t_s: float) -> str:
    s = int(round(t_s))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# --------------------------------------------------------------------------- decoding
def decode_thumbs(src, start_s: float, length_s: float) -> np.ndarray:
    """(n, 180, 320, 3) uint8: one frame per second of src from start_s (ffmpeg decodes the video once)."""
    cmd = [ffmpeg_exe(), "-nostdin", "-v", "error", "-ss", f"{max(0.0, start_s):.3f}", "-i", str(src),
           "-t", f"{length_s:.3f}", "-an", "-sn", "-vf", f"fps=1,scale={TH_W}:{TH_H}:flags=area,format=rgb24",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=False).stdout
    fs = TH_W * TH_H * 3
    n = len(raw) // fs
    return np.frombuffer(raw[:n * fs], dtype=np.uint8).reshape(n, TH_H, TH_W, 3)


# --------------------------------------------------------------------------- detector
def _long_edges(img: np.ndarray) -> np.ndarray:
    """bool (rows, W-LW+1): a horizontal edge run of LW columns starts here (lower half of the frame)."""
    low = int(TH_H * LOW_FRAC)
    y = img[low - 1:].astype(np.int16)
    dy = np.abs(y[2:] - y[:-2]).max(axis=2)                    # colour step across the row, any channel
    cs = np.zeros((dy.shape[0], dy.shape[1] + 1), dtype=np.float32)
    cs[:, 1:] = (dy > TE).cumsum(1)
    return ((cs[:, LW:] - cs[:, :-LW]) / LW) >= COV


def _grown(x: np.ndarray) -> np.ndarray:
    """x with every True also set one row above and below (edges are matched within one row)."""
    g = x.copy()
    g[1:] |= x[:-1]
    g[:-1] |= x[1:]
    return g


def _pair(new: np.ndarray) -> tuple[float, tuple | None]:
    """Best pair of NEW edges DMIN..DMAX rows apart: (score 0-1, (row, distance, first col, last col))."""
    wide = _grown(new)                                         # the lower edge may sit one row off
    best, where = 0.0, None
    for d in range(DMIN, DMAX + 1):
        both = new[:-d] & wide[d:]
        cnt = both.sum(axis=1)
        r = int(np.argmax(cnt))
        sc = float(cnt[r]) / FULL_COLS
        if sc > best:
            cols = np.flatnonzero(both[r])
            best, where = sc, (r, d, int(cols[0]), int(cols[-1]))
    return min(best, 1.0), where


def _hits(frames: np.ndarray, base_s: float, lo_s: float, hi_s: float, step_s: float = STEP_S) -> list[dict]:
    """Bar hits for the frames whose time is in [lo_s, hi_s) (frames outside it only serve as comparison)."""
    n, k = len(frames), max(1, int(round(REF_S / step_s)))
    low = int(TH_H * LOW_FRAC)
    edges: dict[int, np.ndarray] = {}

    def edge(i):
        if i not in edges:
            edges[i] = _long_edges(frames[i])
        return edges[i]

    out = []
    for i in range(n):
        t = base_s + i * step_s
        if t < lo_s - 1e-6 or t >= hi_s - 1e-6:
            continue
        cur = frames[i].astype(np.int16)
        best = None
        for j in (i - k, i + k):
            if j < 0 or j >= n:
                continue
            if (np.abs(cur - frames[j]).max(axis=2) > TAU).mean() > G_MAX:   # a cut / card on that side: no evidence
                continue
            et, er = edge(i), edge(j)
            for owner, new in ((i, et & ~_grown(er)), (j, er & ~_grown(et))):   # the frame that owns the new edges
                sc, where = _pair(new)
                if where and (best is None or sc > best[0]):
                    best = (sc, where, owner, j if owner == i else i)
        if best and best[0] >= MIN_SCORE:
            sc, (r, d, c0, c1), owner, other = best
            out.append({"t": t, "bar_s": base_s + owner * step_s, "ref_s": base_s + other * step_s, "score": sc,
                        "box": (c0 / TH_W, (low + r) / TH_H, (c1 + LW) / TH_W, (low + r + d + 2) / TH_H)})
    return out


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def group_events(hits: list[dict], min_support: int = MIN_SUPPORT) -> list[dict]:
    """Hits whose bar frames are close in time and overlap are one event; best first."""
    events = []
    for h in sorted(hits, key=lambda x: x["bar_s"]):
        for ev in events:
            if h["bar_s"] - ev["end_s"] <= MERGE_GAP_S and _iou(ev["_box"], h["box"]) >= 0.3:
                ev["_hits"].append(h)
                ev["end_s"] = h["bar_s"]
                break
        else:
            events.append({"start_s": h["bar_s"], "end_s": h["bar_s"], "_box": h["box"], "_hits": [h]})
    out = []
    for ev in events:
        hs = ev.pop("_hits")
        ev.pop("_box")
        if len({round(x["bar_s"]) for x in hs}) < min_support:
            continue
        top = sorted(hs, key=lambda x: -x["score"])
        b = top[0]
        out.append({"t_s": round(b["bar_s"], 3), "ref_s": round(b["ref_s"], 3), "start_s": round(ev["start_s"], 3),
                    "end_s": round(ev["end_s"], 3), "tc": tc(ev["start_s"]),
                    "score": round(float(np.mean([x["score"] for x in top[:2]])), 3),
                    "support": len({round(x["bar_s"]) for x in hs}), "box": [round(v, 3) for v in b["box"]]})
    out.sort(key=lambda e: -e["score"])
    return out


def detect_events(frames: np.ndarray, step_s: float = STEP_S, base_s: float = 0.0) -> list[dict]:
    """Overlay events in one-per-`step_s` thumbnails (n, 180, 320, 3), best first. `t_s` is a frame that shows the
    bar, `ref_s` one that does not."""
    return group_events(_hits(frames, base_s, base_s, base_s + len(frames) * step_s + 1, step_s))


# --------------------------------------------------------------------------- whole-file scan
def scan_video(src, duration_s: float, *, decode=None, clock=time.monotonic, budget_s: float = BUDGET_S,
               chunk_s: float = CHUNK_S, max_events: int = MAX_EVENTS) -> dict:
    """Scan src in chunks (memory stays small; the budget can stop it between chunks). `decode(src, start_s,
    length_s)` returns the thumbnails and is replaceable for tests."""
    decode = decode or decode_thumbs
    t0 = clock()
    hits, c0, complete = [], 0.0, True
    while c0 < duration_s - 1e-6:
        if c0 > 0 and clock() - t0 > budget_s:
            complete = False
            break
        c1 = min(duration_s, c0 + chunk_s)
        d0, d1 = max(0.0, c0 - REF_S), min(duration_s, c1 + REF_S)
        fr = decode(src, d0, d1 - d0)
        if len(fr):
            hits += _hits(fr, d0, c0, c1)
        c0 = c1
    events = group_events(hits)[:max_events]
    return {"events": events, "scanned_s": round(min(c0, duration_s), 1), "duration_s": round(float(duration_s), 1),
            "complete": complete, "elapsed_s": round(clock() - t0, 1), "step_s": STEP_S, "ref_s": REF_S,
            "budget_s": budget_s}
