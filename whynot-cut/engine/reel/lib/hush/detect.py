# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: silence detection maths (Python twin of adobe/tools/hush/src/js/detect.js).

The JavaScript is the reference; this twin gives `reel hush` the same plan the panel shows. Same names in snake_case,
same dict keys (s, e, kind, label, threshold, minSilence, padBefore, padAfter, minCut ...), so results are directly
comparable as JSON. Bit-faithful rules: JS Math.round is floor(x + 0.5) (never round()), expressions keep the JS
operation order, sums are plain loops (Python 3.12's sum() of floats is compensated, the JS loop is not), the envelope
is float32, and the comparisons use float64 values of those float32 numbers.
A range's `label` is omitted from the result when it is None (JS: undefined, dropped by JSON).
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

import numpy as np

from .wav import hop_levels, js_round

HOP = 0.01  # envelope resolution: 10 ms
SIMPLE = {"soft": 25, "medium": 50, "strong": 80}

__all__ = ["HOP", "SIMPLE", "envelope", "percentile", "stats", "from_intensity", "silences", "cuts_from_silences",
           "combine", "snap", "total", "plan", "fmt"]


def _values(env):
    """The envelope as a list of Python floats (float32 values widen exactly)."""
    if isinstance(env, np.ndarray):
        return env.astype(np.float64).tolist()
    return [float(x) for x in env]


def envelope(samples, sample_rate, hop=None):
    """RMS level per hop in dBFS (floor -100), float32."""
    hop = hop or HOP
    x = np.asarray(samples, dtype=np.float32)
    n = max(1, js_round(sample_rate * hop))
    return hop_levels(lambda f0, f1: x[f0:f1].astype(np.float64), len(x), n)


def percentile(env, p):
    a = sorted(_values(env))
    return a[min(len(a) - 1, math.floor(p * len(a)))] if a else -100


def stats(env):
    """Noise floor (10th percentile, not below -70 dB) and speech level (90th percentile)."""
    return {"floor": max(-70, percentile(env, 0.10)), "speech": percentile(env, 0.90)}


def from_intensity(intensity, st):
    """Simple mode: one 0..100 intensity -> detection settings, adapted to this clip's levels (PRD FR-10)."""
    t = max(0, min(100, intensity)) / 100
    span = max(6, st["speech"] - st["floor"])
    pad = 0.18 - 0.12 * t
    return {
        "threshold": js_round((st["floor"] + span * (0.15 + 0.30 * t)) * 10) / 10,
        "minSilence": js_round((0.9 - 0.65 * t) * 100) / 100,
        "padBefore": js_round(pad * 100) / 100,
        "padAfter": js_round(pad * 100) / 100,
    }


def silences(env, threshold, min_silence, hop=None):
    """Runs below threshold lasting >= min_silence; clicks shorter than 30 ms inside a silence are ignored."""
    hop = hop or HOP
    a = _values(env)
    n = len(a)
    out, start, blip, max_blip = [], -1, 0, js_round(0.03 / hop)
    for i in range(n + 1):
        quiet = i < n and a[i] < threshold
        if quiet:
            if start < 0:
                start = i
            blip = 0
        elif start >= 0:
            blip += 1
            if blip > max_blip or i == n:
                end = i - blip + 1
                if (end - start) * hop >= min_silence:
                    out.append([start * hop, end * hop])
                start, blip = -1, 0
    return out


def cuts_from_silences(sil, o, length):
    """Silence -> cut range, leaving padding next to speech; no pad where the silence touches the range edge."""
    out = []
    for r in sil:
        s = 0 if r[0] <= 0.001 else r[0] + o["padAfter"]
        e = length if r[1] >= length - 0.001 else r[1] - o["padBefore"]
        if e - s >= (o.get("minCut") or 0.08):
            out.append({"s": s, "e": e, "kind": "silence"})
    return out


def _range(r):
    out = {"s": r["s"], "e": r["e"]}
    if r.get("kind") is not None:
        out["kind"] = r["kind"]
    if r.get("label") is not None:
        out["label"] = r["label"]
    return out


def combine(ranges, join_gap):
    """Union of ranges; filler cuts also swallow a gap up to join_gap so no sliver of padding is left beside them."""
    a = sorted(ranges, key=lambda x: x["s"])
    out = []
    for item in a:
        r = _range(item)
        last = out[-1] if out else None
        gap = r["s"] - last["e"] if last else math.inf
        join = last is not None and (gap <= 0.0005 or (gap <= join_gap and (r.get("kind") == "filler"
                                                                           or last.get("kind") == "filler")))
        if join:
            last["e"] = max(last["e"], r["e"])
            if r.get("kind") == "filler":
                last["kind"] = "filler"
                last["label"] = (last["label"] + " " if last.get("label") else "") + (r.get("label") or "")
        else:
            out.append(r)
    return out


def snap(ranges, fps, min_frames=None):
    """Align to whole frames (inward), drop anything shorter than min_frames (default 2)."""
    out = []
    min_frames = min_frames or 2
    for r in ranges:
        s = math.ceil(r["s"] * fps - 1e-6) / fps  # round inward: the cut never reaches into speech
        e = math.floor(r["e"] * fps + 1e-6) / fps
        if (e - s) * fps >= min_frames - 0.001:
            item = {"s": s, "e": e}
            if r.get("kind") is not None:
                item["kind"] = r["kind"]
            if r.get("label") is not None:
                item["label"] = r["label"]
            out.append(item)
    return out


def total(ranges):
    t = 0
    for r in ranges:  # a plain loop: sum() of floats is compensated in Python 3.12, the JS loop is not
        t += r["e"] - r["s"]
    return t


def plan(env, settings, fillers, length, fps):
    """The full plan: env + settings + chosen fillers -> frame-aligned cuts."""
    sil = silences(env, settings["threshold"], settings["minSilence"])
    cuts = cuts_from_silences(sil, settings, length)
    allr = cuts + list(fillers or [])
    joined = combine(allr, settings["padBefore"] + settings["padAfter"] + 0.05)
    snapped = snap(joined, fps, 2)
    return {"silences": sil, "cuts": snapped, "removed": total(snapped), "before": length,
            "after": length - total(snapped)}


def fmt(sec):
    """m:ss.s with the seconds rounded to 0.1 before the minutes are split (the port's fix: 59.96 -> 1:00.0)."""
    sec = max(0, sec)
    m = math.floor(sec / 60)
    s = sec - m * 60
    t = format(Decimal(s).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")  # JS toFixed(1): exact, half up
    if float(t) >= 60:
        m += 1
        t = "0.0"
    return str(m) + ":" + ("0" if float(t) < 10 else "") + t
